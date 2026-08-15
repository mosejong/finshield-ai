import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.data_retention import (
    DEFAULT_INTERVAL_SECONDS,
    RetentionConfigurationError,
    build_heartbeat,
    build_retention_runner,
    build_retention_scheduler,
    heartbeat_max_age_seconds,
    read_interval_seconds,
)
from app.db.base import Base
from app.db.models import AuthSessionRecord, FinancialProfileRecord, UserRecord
from app.db.session import build_engine, build_session_factory
from app.repositories.auth_sessions import (
    InMemoryAuthSessionRepository,
    SqlAlchemyAuthSessionRepository,
)
from app.repositories.rate_limits import (
    InMemoryRateLimitRepository,
    SqlAlchemyRateLimitRepository,
)
from app.services.data_retention import (
    RetentionHeartbeat,
    RetentionRunner,
    RetentionScheduler,
    logger as retention_logger,
)
from scripts import run_retention_scheduler

NOW = datetime(2026, 8, 15, 9, 0, tzinfo=timezone.utc)


class _BrokenRepository:
    def cleanup_expired(self, *, now: datetime, execute: bool):
        raise RuntimeError("session=abc123 user=42 could not be deleted")


def _runner(
    *,
    auth_sessions=None,
    rate_limits=None,
    now: datetime = NOW,
) -> RetentionRunner:
    return RetentionRunner(
        auth_sessions=auth_sessions or InMemoryAuthSessionRepository(),
        rate_limits=rate_limits or InMemoryRateLimitRepository(),
        clock=lambda: now,
    )


def _scheduler(
    runner: RetentionRunner,
    heartbeat: RetentionHeartbeat,
    *,
    interval_seconds: int = 3600,
    sleep=lambda _seconds: None,
) -> RetentionScheduler:
    return RetentionScheduler(
        runner,
        interval_seconds=interval_seconds,
        heartbeat=heartbeat,
        sleep=sleep,
    )


@pytest.fixture
def captured_logs() -> list[str]:
    records: list[str] = []

    class _Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    handler = _Collector()
    retention_logger.addHandler(handler)
    previous_level = retention_logger.level
    retention_logger.setLevel(logging.INFO)
    try:
        yield records
    finally:
        retention_logger.removeHandler(handler)
        retention_logger.setLevel(previous_level)


# --- heartbeat ------------------------------------------------------------


def test_heartbeat_without_a_recorded_success_is_not_fresh(tmp_path: Path) -> None:
    heartbeat = RetentionHeartbeat(tmp_path / "beat")

    assert heartbeat.seconds_since_success() is None
    assert heartbeat.is_fresh(max_age_seconds=3600) is False


def test_heartbeat_records_the_time_of_a_success(tmp_path: Path) -> None:
    heartbeat = RetentionHeartbeat(tmp_path / "beat", clock=lambda: NOW)
    heartbeat.mark_success()

    assert heartbeat.seconds_since_success() == 0
    assert heartbeat.is_fresh(max_age_seconds=60) is True


def test_heartbeat_goes_stale_after_the_allowed_age(tmp_path: Path) -> None:
    reading_at = NOW
    heartbeat = RetentionHeartbeat(tmp_path / "beat", clock=lambda: reading_at)
    heartbeat.mark_success()

    reading_at = NOW + timedelta(seconds=7300)

    assert heartbeat.is_fresh(max_age_seconds=7260) is False


def test_unreadable_heartbeat_counts_as_no_success(tmp_path: Path) -> None:
    """읽을 수 없는 기록을 신선하다고 보면 고장이 healthy 로 보인다."""
    path = tmp_path / "beat"
    path.write_text("not-a-timestamp", encoding="utf-8")
    heartbeat = RetentionHeartbeat(path)

    assert heartbeat.seconds_since_success() is None
    assert heartbeat.is_fresh(max_age_seconds=3600) is False


def test_heartbeat_write_leaves_no_partial_file(tmp_path: Path) -> None:
    heartbeat = RetentionHeartbeat(tmp_path / "beat", clock=lambda: NOW)
    heartbeat.mark_success()
    heartbeat.mark_success()

    assert sorted(item.name for item in tmp_path.iterdir()) == ["beat"]


# --- 실행 -----------------------------------------------------------------


def test_dry_run_reports_candidates_without_deleting() -> None:
    sessions = InMemoryAuthSessionRepository()
    sessions.create(
        token_hash="a" * 64,
        user_id=uuid4(),
        created_at=NOW - timedelta(days=40),
        expires_at=NOW - timedelta(days=10),
    )
    runner = _runner(auth_sessions=sessions)

    preview = runner.run_once(execute=False)
    assert preview.expired_sessions == 1
    assert preview.executed is False

    again = runner.run_once(execute=False)
    assert again.expired_sessions == 1


def test_run_once_deletes_expired_sessions_and_closed_windows() -> None:
    sessions = InMemoryAuthSessionRepository()
    sessions.create(
        token_hash="b" * 64,
        user_id=uuid4(),
        created_at=NOW - timedelta(days=40),
        expires_at=NOW - timedelta(days=10),
    )
    counters = InMemoryRateLimitRepository()
    counters.increment(
        bucket_key="c" * 64,
        window_start=NOW - timedelta(minutes=5),
        window_end=NOW - timedelta(minutes=4),
    )
    runner = _runner(auth_sessions=sessions, rate_limits=counters)

    summary = runner.run_once()

    assert summary.expired_sessions == 1
    assert summary.anonymous_users == 1
    assert summary.rate_limit_counters == 1
    assert summary.executed is True
    assert runner.run_once().expired_sessions == 0


def test_active_sessions_and_open_windows_survive() -> None:
    sessions = InMemoryAuthSessionRepository()
    sessions.create(
        token_hash="d" * 64,
        user_id=uuid4(),
        created_at=NOW,
        expires_at=NOW + timedelta(days=30),
    )
    counters = InMemoryRateLimitRepository()
    counters.increment(
        bucket_key="e" * 64,
        window_start=NOW,
        window_end=NOW + timedelta(minutes=1),
    )

    summary = _runner(auth_sessions=sessions, rate_limits=counters).run_once()

    assert summary.expired_sessions == 0
    assert summary.anonymous_users == 0
    assert summary.rate_limit_counters == 0


def test_expired_session_removes_the_owned_profile(tmp_path: Path) -> None:
    """정리가 실제로 지우는 것은 세션 행이 아니라 그 사람의 금융정보다."""
    engine = build_engine(f"sqlite+pysqlite:///{tmp_path / 'retention.db'}")
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)
    user_id = uuid4()
    with session_factory() as session:
        session.add(
            UserRecord(
                user_id=str(user_id),
                kind="anonymous",
                status="active",
                created_at=NOW - timedelta(days=40),
            )
        )
        # users 가 먼저 들어가야 아래 두 행의 외래키가 성립한다.
        session.flush()
        session.add(
            AuthSessionRecord(
                token_hash="f" * 64,
                user_id=str(user_id),
                created_at=NOW - timedelta(days=40),
                expires_at=NOW - timedelta(days=10),
            )
        )
        session.add(
            FinancialProfileRecord(
                profile_id=str(uuid4()),
                owner_user_id=str(user_id),
                encrypted_profile=b"ciphertext",
                encryption_key_id="k1",
                created_at=NOW - timedelta(days=40),
                updated_at=NOW - timedelta(days=40),
            )
        )
        session.commit()

    runner = RetentionRunner(
        auth_sessions=SqlAlchemyAuthSessionRepository(session_factory),
        rate_limits=SqlAlchemyRateLimitRepository(session_factory),
        clock=lambda: NOW,
    )
    summary = runner.run_once()

    assert summary.financial_profiles == 1
    with session_factory() as session:
        remaining = session.scalar(
            select(func.count()).select_from(FinancialProfileRecord)
        )
    assert remaining == 0


# --- 스케줄러 -------------------------------------------------------------


def test_successful_cycle_marks_the_heartbeat(tmp_path: Path) -> None:
    heartbeat = RetentionHeartbeat(tmp_path / "beat")
    scheduler = _scheduler(_runner(), heartbeat)

    assert scheduler.run_cycle() is True
    assert heartbeat.is_fresh(max_age_seconds=60) is True
    assert scheduler.consecutive_failures == 0


def test_failed_cycle_leaves_the_heartbeat_untouched(tmp_path: Path) -> None:
    """실패한 실행이 heartbeat 를 갱신하면 고장난 loop 가 healthy 로 보인다."""
    heartbeat = RetentionHeartbeat(tmp_path / "beat")
    scheduler = _scheduler(_runner(auth_sessions=_BrokenRepository()), heartbeat)

    assert scheduler.run_cycle() is False
    assert heartbeat.seconds_since_success() is None


def test_repeated_failures_are_counted_and_reset_on_recovery(
    tmp_path: Path,
    captured_logs: list[str],
) -> None:
    heartbeat = RetentionHeartbeat(tmp_path / "beat")
    broken = _runner(auth_sessions=_BrokenRepository())
    scheduler = _scheduler(broken, heartbeat)

    scheduler.run_cycle()
    scheduler.run_cycle()
    assert scheduler.consecutive_failures == 2
    assert json.loads(captured_logs[-1])["consecutive_failures"] == 2

    healthy = _scheduler(_runner(), heartbeat)
    healthy.run_cycle()
    assert healthy.consecutive_failures == 0


def test_run_forever_runs_before_the_first_sleep(tmp_path: Path) -> None:
    """배포 직후 한 주기를 통째로 기다리면 그동안 보존기간이 안 지켜진다."""
    order: list[str] = []

    class _Recorder(InMemoryAuthSessionRepository):
        def cleanup_expired(self, *, now: datetime, execute: bool):
            order.append("cleanup")
            return super().cleanup_expired(now=now, execute=execute)

    class _Stop(Exception):
        pass

    def sleep(seconds: float) -> None:
        order.append(f"sleep:{seconds:g}")
        if len(order) >= 4:
            raise _Stop

    scheduler = _scheduler(
        _runner(auth_sessions=_Recorder()),
        RetentionHeartbeat(tmp_path / "beat"),
        interval_seconds=900,
        sleep=sleep,
    )
    with pytest.raises(_Stop):
        scheduler.run_forever()

    assert order == ["cleanup", "sleep:900", "cleanup", "sleep:900"]


def test_a_failing_cycle_does_not_stop_the_loop(tmp_path: Path) -> None:
    """DB 가 잠깐 흔들렸다고 정리가 영구히 멈추면 안 된다."""
    cycles = 0

    class _FlakyRepository(InMemoryAuthSessionRepository):
        def cleanup_expired(self, *, now: datetime, execute: bool):
            nonlocal cycles
            cycles += 1
            if cycles == 1:
                raise RuntimeError("temporary outage")
            return super().cleanup_expired(now=now, execute=execute)

    class _Stop(Exception):
        pass

    def sleep(_seconds: float) -> None:
        if cycles >= 2:
            raise _Stop

    heartbeat = RetentionHeartbeat(tmp_path / "beat")
    scheduler = _scheduler(
        _runner(auth_sessions=_FlakyRepository()),
        heartbeat,
        sleep=sleep,
    )
    with pytest.raises(_Stop):
        scheduler.run_forever()

    assert cycles == 2
    assert heartbeat.is_fresh(max_age_seconds=60) is True


# --- 로그 -----------------------------------------------------------------


def test_success_log_carries_counts_and_no_identifiers(
    tmp_path: Path,
    captured_logs: list[str],
) -> None:
    sessions = InMemoryAuthSessionRepository()
    user_id = uuid4()
    token_hash = "9" * 64
    sessions.create(
        token_hash=token_hash,
        user_id=user_id,
        created_at=NOW - timedelta(days=40),
        expires_at=NOW - timedelta(days=10),
    )
    scheduler = _scheduler(
        _runner(auth_sessions=sessions),
        RetentionHeartbeat(tmp_path / "beat"),
    )

    scheduler.run_cycle()

    assert len(captured_logs) == 1
    entry = json.loads(captured_logs[0])
    assert entry["event"] == "retention_run"
    assert entry["status"] == "succeeded"
    assert entry["expired_sessions"] == 1
    assert entry["anonymous_users"] == 1
    for identifier in (str(user_id), token_hash):
        assert identifier not in captured_logs[0]


def test_failure_log_drops_the_exception_message(
    tmp_path: Path,
    captured_logs: list[str],
) -> None:
    """SQLAlchemy 는 실패한 문장과 바인딩 값을 메시지에 붙인다."""
    scheduler = _scheduler(
        _runner(auth_sessions=_BrokenRepository()),
        RetentionHeartbeat(tmp_path / "beat"),
    )

    scheduler.run_cycle()

    entry = json.loads(captured_logs[0])
    assert entry["status"] == "failed"
    assert entry["error_type"] == "RuntimeError"
    assert "abc123" not in captured_logs[0]
    assert "user=42" not in captured_logs[0]


# --- 설정 -----------------------------------------------------------------


def test_interval_defaults_when_unset_or_blank() -> None:
    assert read_interval_seconds({}) == DEFAULT_INTERVAL_SECONDS
    assert (
        read_interval_seconds({"FINSHIELD_RETENTION_INTERVAL_SECONDS": "  "})
        == DEFAULT_INTERVAL_SECONDS
    )


def test_interval_accepts_a_value_inside_the_allowed_range() -> None:
    assert (
        read_interval_seconds({"FINSHIELD_RETENTION_INTERVAL_SECONDS": "300"}) == 300
    )


@pytest.mark.parametrize("value", ["59", "86401", "hourly", "-1"])
def test_interval_outside_the_allowed_range_is_rejected(value: str) -> None:
    with pytest.raises(RetentionConfigurationError):
        read_interval_seconds({"FINSHIELD_RETENTION_INTERVAL_SECONDS": value})


def test_stale_threshold_tolerates_one_missed_cycle() -> None:
    assert heartbeat_max_age_seconds(3600) == 7260


def test_scheduling_without_a_database_is_refused() -> None:
    """in-memory 를 상대로 돌면 아무것도 지우지 않으면서 성공을 기록한다."""
    with pytest.raises(RetentionConfigurationError):
        build_retention_runner({"APP_ENV": "development"})


def test_deployed_scheduling_requires_postgresql() -> None:
    with pytest.raises(RetentionConfigurationError):
        build_retention_runner(
            {"APP_ENV": "production", "DATABASE_URL": "sqlite+pysqlite:///./local.db"}
        )


def test_heartbeat_path_is_configurable(tmp_path: Path) -> None:
    target = tmp_path / "custom-beat"
    heartbeat = build_heartbeat(
        {"FINSHIELD_RETENTION_HEARTBEAT_PATH": str(target)}
    )

    assert heartbeat.path == target


def test_scheduler_is_built_from_the_environment(tmp_path: Path) -> None:
    database = tmp_path / "retention.db"
    Base.metadata.create_all(build_engine(f"sqlite+pysqlite:///{database}"))

    scheduler = build_retention_scheduler(
        {
            "APP_ENV": "development",
            "DATABASE_URL": f"sqlite+pysqlite:///{database}",
            "FINSHIELD_RETENTION_INTERVAL_SECONDS": "120",
            "FINSHIELD_RETENTION_HEARTBEAT_PATH": str(tmp_path / "beat"),
        }
    )

    assert scheduler.interval_seconds == 120
    assert scheduler.run_cycle() is True


# --- 실행 진입점 ----------------------------------------------------------


@pytest.fixture
def cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """`.env` 가 있는 개발 머신에서도 CI 와 같은 환경으로 돌린다."""
    monkeypatch.setattr(run_retention_scheduler, "load_dotenv", lambda **_: None)
    for name in (
        "DATABASE_URL",
        "DATABASE_HOST",
        "FINSHIELD_RETENTION_INTERVAL_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv(
        "FINSHIELD_RETENTION_HEARTBEAT_PATH", str(tmp_path / "beat")
    )
    return run_retention_scheduler.main


def test_health_check_fails_before_the_first_successful_cleanup(cli) -> None:
    assert cli(["--check-heartbeat"]) == 1


def test_health_check_passes_after_a_successful_cleanup(
    cli,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "retention.db"
    Base.metadata.create_all(build_engine(f"sqlite+pysqlite:///{database}"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{database}")

    assert cli(["--once"]) == 0
    assert cli(["--check-heartbeat"]) == 0


def test_health_check_does_not_need_the_database(cli, tmp_path: Path) -> None:
    """DB 가 흔들릴 때 정리 컨테이너까지 unhealthy 로 떨어지면 원인이 흐려진다."""
    RetentionHeartbeat(tmp_path / "beat").mark_success()

    assert cli(["--check-heartbeat"]) == 0


def test_a_misconfigured_scheduler_exits_instead_of_idling(cli) -> None:
    assert cli(["--once"]) == 2
