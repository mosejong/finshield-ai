"""정리 스케줄러 설정 배선."""

import os
import tempfile
from collections.abc import Mapping
from pathlib import Path

from sqlalchemy.exc import ArgumentError

from app.core.runtime_secrets import (
    RuntimeSecretConfigurationError,
    resolve_database_url,
)
from app.db.session import build_engine, build_session_factory
from app.repositories.auth_sessions import SqlAlchemyAuthSessionRepository
from app.repositories.rate_limits import SqlAlchemyRateLimitRepository
from app.services.data_retention import (
    HEARTBEAT_FILENAME,
    RetentionHeartbeat,
    RetentionRunner,
    RetentionScheduler,
)

LOCAL_ENVIRONMENTS = frozenset({"development", "test"})

DEFAULT_INTERVAL_SECONDS = 3600
MIN_INTERVAL_SECONDS = 60
MAX_INTERVAL_SECONDS = 86_400


class RetentionConfigurationError(RuntimeError):
    pass


def read_interval_seconds(values: Mapping[str, str] | None = None) -> int:
    settings = values if values is not None else os.environ
    raw_value = settings.get("FINSHIELD_RETENTION_INTERVAL_SECONDS", "").strip()
    if not raw_value:
        return DEFAULT_INTERVAL_SECONDS
    try:
        interval = int(raw_value)
    except ValueError as exc:
        raise RetentionConfigurationError(
            "FINSHIELD_RETENTION_INTERVAL_SECONDS must be an integer"
        ) from exc
    if interval < MIN_INTERVAL_SECONDS or interval > MAX_INTERVAL_SECONDS:
        # 아래로는 DB 를 두드리기만 하고 지울 것이 없다. 위로는 삭제 약속과
        # 실제 삭제 시점의 간격이 하루를 넘어간다.
        raise RetentionConfigurationError(
            "FINSHIELD_RETENTION_INTERVAL_SECONDS must be between "
            f"{MIN_INTERVAL_SECONDS} and {MAX_INTERVAL_SECONDS}"
        )
    return interval


def heartbeat_max_age_seconds(interval_seconds: int) -> int:
    """이 시간이 지나도록 성공 기록이 없으면 고장으로 본다.

    한 주기를 놓치는 것은 일시적인 DB 문제로도 일어난다. 두 주기를 연속으로
    넘기면 그건 저절로 낫지 않는다. 여유 60초는 실행 시간과 healthcheck
    주기가 어긋나는 폭이다.
    """
    return interval_seconds * 2 + 60


def build_heartbeat(values: Mapping[str, str] | None = None) -> RetentionHeartbeat:
    settings = values if values is not None else os.environ
    configured = settings.get("FINSHIELD_RETENTION_HEARTBEAT_PATH", "").strip()
    if configured:
        return RetentionHeartbeat(Path(configured))
    # 컨테이너는 read_only 라 쓸 수 있는 곳이 tmpfs 뿐이다. 재시작하면
    # 사라지는데, 재시작 직후에는 어차피 새로 정리를 돌리므로 맞는 동작이다.
    return RetentionHeartbeat(Path(tempfile.gettempdir()) / HEARTBEAT_FILENAME)


def build_retention_runner(
    values: Mapping[str, str] | None = None,
) -> RetentionRunner:
    settings = values if values is not None else os.environ
    app_env = settings.get("APP_ENV", "development").strip().lower()
    try:
        database_url = resolve_database_url(settings)
    except RuntimeSecretConfigurationError as exc:
        raise RetentionConfigurationError(
            "retention database configuration is invalid"
        ) from exc

    if not database_url:
        # in-memory 저장소를 상대로 돌면 아무것도 지우지 않으면서 매번
        # 성공을 기록한다. 보존기간이 지켜지고 있다는 잘못된 신호가 정리가
        # 아예 없는 것보다 나쁘다.
        raise RetentionConfigurationError(
            "scheduled retention requires DATABASE_URL"
        )
    if app_env not in LOCAL_ENVIRONMENTS and not database_url.startswith(
        "postgresql+psycopg://"
    ):
        raise RetentionConfigurationError(
            "deployed retention requires PostgreSQL with psycopg"
        )

    try:
        # 두 repository 가 engine 하나를 같이 쓴다. 같은 DB 를 보는 같은
        # 프로세스라 연결 pool 을 나눌 이유가 없다.
        session_factory = build_session_factory(build_engine(database_url))
    except (ArgumentError, TypeError, ValueError) as exc:
        raise RetentionConfigurationError(
            "retention storage configuration is invalid"
        ) from exc

    return RetentionRunner(
        auth_sessions=SqlAlchemyAuthSessionRepository(session_factory),
        rate_limits=SqlAlchemyRateLimitRepository(session_factory),
    )


def build_retention_scheduler(
    values: Mapping[str, str] | None = None,
) -> RetentionScheduler:
    settings = values if values is not None else os.environ
    return RetentionScheduler(
        build_retention_runner(settings),
        interval_seconds=read_interval_seconds(settings),
        heartbeat=build_heartbeat(settings),
    )
