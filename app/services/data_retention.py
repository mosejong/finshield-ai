"""만료 데이터 정리를 주기적으로 실행한다.

보존기간이 문서에만 있고 아무도 실행하지 않으면 두 가지가 같이 일어난다.
개인정보 보존 약속 위반, 그리고 DB 무한 증가. `adr/0004` 가 약속한 정리를
실제로 이행하는 쪽이 이 모듈이다.

이행이 멈췄을 때 그것을 드러내는 방법은 heartbeat 파일이다. **성공한 실행만**
시각을 남기고 컨테이너 healthcheck 가 그 시각이 오래됐는지를 본다. 로그만
남기면 아무도 보지 않는 동안 몇 주씩 정리가 멈춰 있을 수 있다. 계속 실패하는
loop 도 돌기는 돌기 때문에 "프로세스가 살아 있음" 은 신호가 되지 못한다.
"""

import json
import logging
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from time import sleep as _sleep

from app.core.observability import configure_json_logger
from app.repositories.auth_sessions import AuthSessionRepository
from app.repositories.rate_limits import RateLimitRepository

logger = logging.getLogger("finshield.retention")

HEARTBEAT_FILENAME = "finshield-retention-heartbeat"


@dataclass(frozen=True)
class RetentionRunSummary:
    expired_sessions: int
    anonymous_users: int
    financial_profiles: int
    rate_limit_counters: int
    executed: bool


class RetentionHeartbeat:
    """마지막으로 정리에 성공한 시각만 기록한다."""

    def __init__(
        self,
        path: Path,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._path = path
        self._clock = clock or (lambda: datetime.now(UTC))

    @property
    def path(self) -> Path:
        return self._path

    def mark_success(self) -> None:
        # healthcheck 가 쓰는 도중에 읽으면 잘린 내용을 보고 멀쩡한 실행을
        # 실패로 판정한다. 임시 파일에 쓰고 원자적으로 바꿔치운다.
        temporary = self._path.with_name(f"{self._path.name}.tmp")
        temporary.write_text(self._clock().isoformat(), encoding="utf-8")
        os.replace(temporary, self._path)

    def seconds_since_success(self) -> float | None:
        """마지막 성공 이후 흐른 시간. 기록이 없거나 읽을 수 없으면 None."""
        try:
            raw = self._path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        try:
            recorded = datetime.fromisoformat(raw)
        except ValueError:
            return None
        if recorded.tzinfo is None or recorded.utcoffset() is None:
            return None
        return (self._clock() - recorded).total_seconds()

    def is_fresh(self, *, max_age_seconds: float) -> bool:
        elapsed = self.seconds_since_success()
        # 기록이 없으면 아직 한 번도 성공하지 못한 것이다. 기동 직후의 공백은
        # healthcheck 의 start_period 가 덮는다.
        if elapsed is None:
            return False
        return elapsed <= max_age_seconds


class RetentionRunner:
    """정리 1회를 실행한다.

    service 가 아니라 repository 를 직접 받는다. 삭제는 `window_end`·
    `expires_at` 비교뿐이라 rate limit 의 HMAC 비밀이나 세션 TTL·쿠키 설정이
    필요 없다. service 를 거치면 정리가 그 설정값에 묶여서, 예를 들어 rate
    limit 을 끄고 비밀을 내리면 정리까지 같이 멈춘다.
    """

    def __init__(
        self,
        *,
        auth_sessions: AuthSessionRepository,
        rate_limits: RateLimitRepository,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._auth_sessions = auth_sessions
        self._rate_limits = rate_limits
        self._clock = clock or (lambda: datetime.now(UTC))

    def run_once(self, *, execute: bool = True) -> RetentionRunSummary:
        now = self._clock()
        # 개인정보가 먼저다. 뒤 단계가 실패해도 보존기간 약속은 이미 지켜져
        # 있어야 한다. rate limit 카운터는 식별자를 담지 않으므로 뒤에 둔다.
        sessions = self._auth_sessions.cleanup_expired(now=now, execute=execute)
        counters = self._rate_limits.cleanup_expired(now=now, execute=execute)
        return RetentionRunSummary(
            expired_sessions=sessions.expired_sessions,
            anonymous_users=sessions.anonymous_users,
            financial_profiles=sessions.financial_profiles,
            rate_limit_counters=counters.counters,
            executed=execute,
        )


class RetentionScheduler:
    def __init__(
        self,
        runner: RetentionRunner,
        *,
        interval_seconds: int,
        heartbeat: RetentionHeartbeat,
        sleep: Callable[[float], None] = _sleep,
    ) -> None:
        self._runner = runner
        self._interval_seconds = interval_seconds
        self._heartbeat = heartbeat
        self._sleep = sleep
        self._consecutive_failures = 0

    @property
    def interval_seconds(self) -> int:
        return self._interval_seconds

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def run_cycle(self) -> bool:
        """정리 1회 + 결과 기록. 성공하면 True."""
        started_at = perf_counter()
        try:
            summary = self._runner.run_once()
        except Exception as exc:
            self._consecutive_failures += 1
            # 예외 메시지는 남기지 않는다. SQLAlchemy 는 실패한 문장과 바인딩
            # 값을 메시지에 붙이는데, 그러면 정리 로그가 개인정보 유출 경로가
            # 된다. 종류만 남기고 상세는 DB 로그에서 본다.
            _log(
                logging.ERROR,
                status="failed",
                error_type=type(exc).__name__,
                consecutive_failures=self._consecutive_failures,
                duration_ms=_elapsed_ms(started_at),
            )
            return False

        self._consecutive_failures = 0
        # 성공을 먼저 기록한다. 로그 handler 가 실패해도 healthcheck 는
        # 정리가 끝났다는 사실을 알아야 한다.
        self._heartbeat.mark_success()
        _log(
            logging.INFO,
            status="succeeded",
            duration_ms=_elapsed_ms(started_at),
            **asdict(summary),
        )
        return True

    def run_forever(self) -> None:
        # 첫 실행을 미루지 않는다. 배포 직후 한 주기를 통째로 기다리면
        # 그동안은 보존기간이 지켜지지 않는 상태로 서비스가 떠 있는 것이다.
        while True:
            self.run_cycle()
            # 실패해도 같은 간격으로 다시 시도한다. 정리는 급한 작업이 아니라
            # backoff 로 얻을 것이 없고, 간격이 흔들리면 heartbeat 신선도
            # 기준까지 같이 흔들린다.
            self._sleep(self._interval_seconds)


def configure_retention_logger() -> None:
    configure_json_logger(logger)


def _log(level: int, **fields: object) -> None:
    logger.log(
        level,
        json.dumps(
            {
                "event": "retention_run",
                "service": "finshield-retention",
                "timestamp": datetime.now(UTC).isoformat(),
                **fields,
            },
            separators=(",", ":"),
            sort_keys=True,
        ),
    )


def _elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 3)
