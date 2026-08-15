import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.core.rate_limit import (
    RateLimitConfigurationError,
    build_rate_limit_service,
    rate_limit_enabled,
    reset_rate_limit_service,
)
from app.db.session import build_engine, build_session_factory
from app.main import app as main_app
from app.repositories.rate_limits import (
    InMemoryRateLimitRepository,
    RateLimitRepository,
    RateLimitStorageError,
    SqlAlchemyRateLimitRepository,
)
from app.services.rate_limits import (
    DEFAULT_POLICIES,
    RateLimitPolicy,
    RateLimitService,
)

SECRET = "x" * 40
NOW = datetime(2026, 8, 14, 12, 0, 30, tzinfo=timezone.utc)


def _service(
    repository: RateLimitRepository | None = None,
    *,
    policies=DEFAULT_POLICIES,
    now: datetime = NOW,
) -> RateLimitService:
    return RateLimitService(
        repository or InMemoryRateLimitRepository(),
        secret=SECRET,
        policies=policies,
        clock=lambda: now,
    )


# --- 정책 선택 ------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("POST", "/api/v1/auth/session", "auth_session"),
        ("DELETE", "/api/v1/auth/session", "write"),
        ("POST", "/api/v1/analyze", "analyze"),
        ("POST", "/api/v1/profiles", "write"),
        ("GET", "/api/v1/products", "read"),
        ("GET", "/health", None),
        ("GET", "/readyz", None),
        ("GET", "/docs", None),
    ],
)
def test_policy_selection(method: str, path: str, expected: str | None) -> None:
    policy = _service().select_policy(method, path)
    assert (policy.name if policy else None) == expected


def test_health_checks_are_never_limited() -> None:
    """컨테이너 healthcheck 가 주기적으로 때리는 경로다.

    여기에 한도를 걸면 서비스가 스스로를 unhealthy 로 만들고 재시작 루프에
    빠진다.
    """
    service = _service()
    for _ in range(1_000):
        decision = service.check(method="GET", path="/health", client_ip="203.0.113.7")
        assert decision.allowed


# --- 계수 ----------------------------------------------------------------


def test_requests_are_allowed_up_to_the_limit_then_rejected() -> None:
    policy = RateLimitPolicy(
        name="analyze",
        limit=3,
        window_seconds=60,
        path_prefix="/api/v1/analyze",
        exact_path=True,
    )
    service = _service(policies=(policy,))

    outcomes = [
        service.check(method="POST", path="/api/v1/analyze", client_ip="203.0.113.7")
        for _ in range(5)
    ]

    assert [outcome.allowed for outcome in outcomes] == [True, True, True, False, False]
    assert [outcome.remaining for outcome in outcomes] == [2, 1, 0, 0, 0]


def test_different_clients_do_not_share_a_bucket() -> None:
    policy = RateLimitPolicy(
        name="analyze",
        limit=1,
        window_seconds=60,
        path_prefix="/api/v1/analyze",
        exact_path=True,
    )
    service = _service(policies=(policy,))

    assert service.check(
        method="POST", path="/api/v1/analyze", client_ip="203.0.113.7"
    ).allowed
    assert service.check(
        method="POST", path="/api/v1/analyze", client_ip="198.51.100.2"
    ).allowed
    assert not service.check(
        method="POST", path="/api/v1/analyze", client_ip="203.0.113.7"
    ).allowed


def test_policies_are_counted_separately() -> None:
    repository = InMemoryRateLimitRepository()
    service = _service(repository)

    for _ in range(25):
        service.check(method="POST", path="/api/v1/analyze", client_ip="203.0.113.7")

    # analyze 를 25번 써도 세션 발급 한도는 그대로여야 한다.
    decision = service.check(
        method="POST", path="/api/v1/auth/session", client_ip="203.0.113.7"
    )
    assert decision.allowed
    assert decision.remaining == 19


def test_unidentified_clients_share_one_bucket() -> None:
    """식별 실패를 통과로 처리하면 위조 한 번으로 제한을 벗어난다."""
    policy = RateLimitPolicy(
        name="analyze",
        limit=1,
        window_seconds=60,
        path_prefix="/api/v1/analyze",
        exact_path=True,
    )
    service = _service(policies=(policy,))

    assert service.check(
        method="POST", path="/api/v1/analyze", client_ip=None
    ).allowed
    assert not service.check(
        method="POST", path="/api/v1/analyze", client_ip=None
    ).allowed


def test_window_boundary_resets_the_counter() -> None:
    policy = RateLimitPolicy(
        name="analyze",
        limit=1,
        window_seconds=60,
        path_prefix="/api/v1/analyze",
        exact_path=True,
    )
    repository = InMemoryRateLimitRepository()

    first = RateLimitService(
        repository, secret=SECRET, policies=(policy,), clock=lambda: NOW
    )
    assert first.check(
        method="POST", path="/api/v1/analyze", client_ip="203.0.113.7"
    ).allowed
    assert not first.check(
        method="POST", path="/api/v1/analyze", client_ip="203.0.113.7"
    ).allowed

    later = RateLimitService(
        repository,
        secret=SECRET,
        policies=(policy,),
        clock=lambda: NOW + timedelta(seconds=60),
    )
    assert later.check(
        method="POST", path="/api/v1/analyze", client_ip="203.0.113.7"
    ).allowed


def test_retry_after_points_at_the_end_of_the_window() -> None:
    policy = RateLimitPolicy(
        name="analyze",
        limit=1,
        window_seconds=60,
        path_prefix="/api/v1/analyze",
        exact_path=True,
    )
    service = _service(policies=(policy,))
    service.check(method="POST", path="/api/v1/analyze", client_ip="203.0.113.7")
    decision = service.check(
        method="POST", path="/api/v1/analyze", client_ip="203.0.113.7"
    )

    # NOW 는 12:00:30 이고 window 는 12:00:00~12:01:00 이다.
    assert decision.retry_after_seconds == 30
    assert decision.reset_at == datetime(2026, 8, 14, 12, 1, tzinfo=timezone.utc)


def test_retry_after_is_never_zero() -> None:
    """`Retry-After: 0` 은 즉시 재시도해도 된다는 뜻이라 재시도 폭풍을 부른다."""
    policy = RateLimitPolicy(
        name="analyze",
        limit=1,
        window_seconds=60,
        path_prefix="/api/v1/analyze",
        exact_path=True,
    )
    at_boundary = datetime(2026, 8, 14, 12, 0, 59, 999_000, tzinfo=timezone.utc)
    service = _service(policies=(policy,), now=at_boundary)
    service.check(method="POST", path="/api/v1/analyze", client_ip="203.0.113.7")
    decision = service.check(
        method="POST", path="/api/v1/analyze", client_ip="203.0.113.7"
    )
    assert decision.retry_after_seconds == 1


# --- 개인정보 ------------------------------------------------------------


def test_stored_key_does_not_contain_the_address() -> None:
    """rate limit 때문에 접속 기록을 남기게 되면 안 된다."""
    repository = InMemoryRateLimitRepository()
    service = _service(repository)
    service.check(method="POST", path="/api/v1/analyze", client_ip="203.0.113.7")

    stored = list(repository._counters)
    assert stored
    for bucket_key, _ in stored:
        assert "203.0.113.7" not in bucket_key


def test_bucket_key_depends_on_the_secret() -> None:
    """단순 해시면 IPv4 는 표를 만들어 되돌릴 수 있다."""
    left = InMemoryRateLimitRepository()
    right = InMemoryRateLimitRepository()
    RateLimitService(left, secret="a" * 40, clock=lambda: NOW).check(
        method="POST", path="/api/v1/analyze", client_ip="203.0.113.7"
    )
    RateLimitService(right, secret="b" * 40, clock=lambda: NOW).check(
        method="POST", path="/api/v1/analyze", client_ip="203.0.113.7"
    )
    assert set(left._counters) != set(right._counters)


# --- 장애 시 동작 --------------------------------------------------------


def test_storage_failure_allows_the_request() -> None:
    """사기 분석은 안전 기능이다.

    DB 장애로 위험한 문자를 확인하지 못하게 만드는 쪽이, 그동안 한도가
    열리는 것보다 나쁘다.
    """

    class BrokenRepository:
        def verify(self) -> None:
            raise RateLimitStorageError("down")

        def increment(self, **_: object) -> int:
            raise RateLimitStorageError("down")

        def cleanup_expired(self, **_: object):
            raise RateLimitStorageError("down")

    service = _service(BrokenRepository())  # type: ignore[arg-type]
    for _ in range(100):
        assert service.check(
            method="POST", path="/api/v1/analyze", client_ip="203.0.113.7"
        ).allowed


def test_storage_failure_is_logged_without_the_address(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class BrokenRepository:
        def verify(self) -> None:
            raise RateLimitStorageError("down")

        def increment(self, **_: object) -> int:
            raise RateLimitStorageError("down")

        def cleanup_expired(self, **_: object):
            raise RateLimitStorageError("down")

    with caplog.at_level("WARNING", logger="finshield.rate_limit"):
        _service(BrokenRepository()).check(  # type: ignore[arg-type]
            method="POST", path="/api/v1/analyze", client_ip="203.0.113.7"
        )

    assert caplog.records
    assert "203.0.113.7" not in caplog.text


# --- 저장소 --------------------------------------------------------------


def test_in_memory_and_sql_repositories_agree(tmp_path: Path) -> None:
    """두 구현이 다르게 세면 로컬에서 통과한 동작이 배포에서 달라진다."""
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'rate.sqlite3').as_posix()}"
    engine = build_engine(database_url)
    from app.db.base import Base

    Base.metadata.create_all(engine)

    window_start = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)
    window_end = window_start + timedelta(seconds=60)
    repositories: list[RateLimitRepository] = [
        InMemoryRateLimitRepository(),
        SqlAlchemyRateLimitRepository(build_session_factory(engine)),
    ]

    for repository in repositories:
        counts = [
            repository.increment(
                bucket_key="bucket", window_start=window_start, window_end=window_end
            )
            for _ in range(3)
        ]
        assert counts == [1, 2, 3]
        assert (
            repository.increment(
                bucket_key="other", window_start=window_start, window_end=window_end
            )
            == 1
        )
        summary = repository.cleanup_expired(now=window_end, execute=False)
        assert summary.counters == 2
        assert summary.executed is False
        summary = repository.cleanup_expired(now=window_end, execute=True)
        assert summary.executed is True
        assert (
            repository.increment(
                bucket_key="bucket", window_start=window_start, window_end=window_end
            )
            == 1
        )


def test_cleanup_keeps_the_window_that_is_still_open(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'rate.sqlite3').as_posix()}"
    engine = build_engine(database_url)
    from app.db.base import Base

    Base.metadata.create_all(engine)
    repository = SqlAlchemyRateLimitRepository(build_session_factory(engine))

    window_start = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)
    repository.increment(
        bucket_key="bucket",
        window_start=window_start,
        window_end=window_start + timedelta(seconds=60),
    )

    summary = repository.cleanup_expired(
        now=window_start + timedelta(seconds=30), execute=True
    )
    assert summary.counters == 0
    # 아직 열려 있는 window 를 지우면 그 순간 한도가 초기화된다.
    assert (
        repository.increment(
            bucket_key="bucket",
            window_start=window_start,
            window_end=window_start + timedelta(seconds=60),
        )
        == 2
    )


def test_cleanup_script_also_clears_closed_windows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """보존 정리 명령이 새 테이블을 빠뜨리면 이 테이블만 무한히 자란다."""
    from scripts.cleanup_expired_anonymous_data import main

    database_url = f"sqlite+pysqlite:///{(tmp_path / 'cleanup.sqlite3').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    command.upgrade(Config("alembic.ini"), "head")

    repository = SqlAlchemyRateLimitRepository(
        build_session_factory(build_engine(database_url))
    )
    closed = datetime(2020, 1, 1, tzinfo=timezone.utc)
    repository.increment(
        bucket_key="bucket",
        window_start=closed,
        window_end=closed + timedelta(seconds=60),
    )

    monkeypatch.setattr("sys.argv", ["cleanup_expired_anonymous_data"])
    assert main() == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["rate_limit_counters"] == 1
    assert preview["executed"] is False
    # 미리보기는 아무것도 지우지 않는다.
    assert repository.cleanup_expired(now=NOW, execute=False).counters == 1

    monkeypatch.setattr(
        "sys.argv", ["cleanup_expired_anonymous_data", "--execute"]
    )
    assert main() == 0
    executed = json.loads(capsys.readouterr().out)
    assert executed["executed"] is True
    assert executed["rate_limit_counters"] == 1
    assert repository.cleanup_expired(now=NOW, execute=False).counters == 0


def test_sql_repository_reports_a_missing_migration(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'empty.sqlite3').as_posix()}"
    repository = SqlAlchemyRateLimitRepository(
        build_session_factory(build_engine(database_url))
    )
    with pytest.raises(RateLimitStorageError):
        repository.verify()


def test_migration_creates_the_counter_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'migration.sqlite3').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config("alembic.ini")

    command.upgrade(config, "head")
    repository = SqlAlchemyRateLimitRepository(
        build_session_factory(build_engine(database_url))
    )
    repository.verify()

    command.downgrade(config, "20260813_02")
    with pytest.raises(RateLimitStorageError):
        repository.verify()


# --- 설정 ----------------------------------------------------------------


def test_rate_limiting_is_off_locally_and_on_when_deployed() -> None:
    assert rate_limit_enabled({}) is False
    assert rate_limit_enabled({"APP_ENV": "development"}) is False
    assert rate_limit_enabled({"APP_ENV": "production"}) is True
    assert (
        rate_limit_enabled({"APP_ENV": "development", "FINSHIELD_RATE_LIMIT_ENABLED": "1"})
        is True
    )
    assert (
        rate_limit_enabled({"APP_ENV": "production", "FINSHIELD_RATE_LIMIT_ENABLED": "0"})
        is False
    )


def test_invalid_enable_flag_is_rejected() -> None:
    with pytest.raises(RateLimitConfigurationError):
        rate_limit_enabled({"FINSHIELD_RATE_LIMIT_ENABLED": "maybe"})


def test_deployment_requires_a_shared_secret() -> None:
    """워커마다 다른 비밀이면 같은 IP 가 워커마다 다른 bucket 으로 흩어진다."""
    with pytest.raises(RateLimitConfigurationError):
        build_rate_limit_service(
            {
                "APP_ENV": "production",
                "DATABASE_URL": "postgresql+psycopg://u:p@db:5432/finshield",
            }
        )


def test_deployment_requires_a_database() -> None:
    with pytest.raises(RateLimitConfigurationError):
        build_rate_limit_service(
            {"APP_ENV": "production", "FINSHIELD_RATE_LIMIT_SECRET": SECRET}
        )


def test_deployment_rejects_sqlite() -> None:
    """SQLite 는 워커 간 카운터를 공유하지 못한다.

    한도가 워커 수만큼 헐거워지는데 겉으로는 정상으로 보인다.
    """
    with pytest.raises(RateLimitConfigurationError):
        build_rate_limit_service(
            {
                "APP_ENV": "production",
                "DATABASE_URL": "sqlite+pysqlite:///./limits.sqlite3",
                "FINSHIELD_RATE_LIMIT_SECRET": SECRET,
            }
        )


def test_short_secret_is_rejected() -> None:
    with pytest.raises(RateLimitConfigurationError):
        build_rate_limit_service(
            {
                "APP_ENV": "production",
                "DATABASE_URL": "postgresql+psycopg://u:p@db:5432/finshield",
                "FINSHIELD_RATE_LIMIT_SECRET": "short",
            }
        )


def test_local_build_falls_back_to_in_memory_storage() -> None:
    service = build_rate_limit_service({"APP_ENV": "development"})
    assert service.policies == DEFAULT_POLICIES


# --- 실제 앱 -------------------------------------------------------------


@pytest.fixture()
def limited_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """rate limit 을 켠 실제 앱.

    미들웨어가 `app/main.py` 에 실제로 설치되어 있는지, 신뢰 홉 설정으로
    client 가 구분되는지, migration 으로 만든 실제 테이블에 카운터가
    쌓이는지를 한 번에 본다.
    """
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'limits.sqlite3').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    command.upgrade(Config("alembic.ini"), "head")

    monkeypatch.setenv("FINSHIELD_TRUSTED_PROXY_HOPS", "1")
    monkeypatch.setenv("FINSHIELD_RATE_LIMIT_SECRET", SECRET)
    monkeypatch.setenv("FINSHIELD_RATE_LIMIT_ENABLED", "1")
    reset_rate_limit_service()

    client = TestClient(main_app)
    try:
        yield client
    finally:
        reset_rate_limit_service()


def _analyze(client: TestClient, ip: str):
    return client.post(
        "/api/v1/analyze",
        json={"text": "계좌로 입금받고 다시 보내주세요."},
        headers={"X-Forwarded-For": ip},
    )


def test_analyze_is_limited_end_to_end(limited_client: TestClient) -> None:
    statuses = [_analyze(limited_client, "203.0.113.7").status_code for _ in range(32)]

    assert statuses[:30] == [200] * 30
    assert statuses[30:] == [429, 429]


def test_rejected_response_carries_retry_after_and_security_headers(
    limited_client: TestClient,
) -> None:
    for _ in range(31):
        response = _analyze(limited_client, "198.51.100.2")

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) >= 1
    assert response.headers["RateLimit-Limit"] == "30"
    # rate limit 이 보안 미들웨어 안쪽에 있어야 429 에도 헤더가 붙는다.
    assert response.headers["x-content-type-options"] == "nosniff"


def test_one_client_cannot_lock_out_another(limited_client: TestClient) -> None:
    """이 서비스에서 가장 중요한 성질이다.

    backend 가 보는 peer 는 항상 web 컨테이너 하나라, forwarded 주소를
    쓰지 않으면 공격자 한 명이 전체 사용자를 막아버린다.
    """
    for _ in range(31):
        _analyze(limited_client, "203.0.113.9")

    assert _analyze(limited_client, "203.0.113.9").status_code == 429
    assert _analyze(limited_client, "192.0.2.55").status_code == 200


def test_spoofed_forwarded_prefix_does_not_reset_the_counter(
    limited_client: TestClient,
) -> None:
    """왼쪽에 아무 주소나 붙여 새 bucket 을 얻을 수 있으면 제한이 없는 것과 같다."""
    for index in range(31):
        limited_client.post(
            "/api/v1/analyze",
            json={"text": "계좌로 입금받고 다시 보내주세요."},
            headers={"X-Forwarded-For": f"10.9.9.{index}, 203.0.113.11"},
        )

    response = limited_client.post(
        "/api/v1/analyze",
        json={"text": "계좌로 입금받고 다시 보내주세요."},
        headers={"X-Forwarded-For": "10.1.1.1, 203.0.113.11"},
    )
    assert response.status_code == 429


def test_health_endpoint_survives_a_flood(limited_client: TestClient) -> None:
    for _ in range(300):
        assert limited_client.get("/health").status_code == 200
