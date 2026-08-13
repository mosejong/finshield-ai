import os
from collections.abc import Mapping
from datetime import timedelta

from sqlalchemy.exc import ArgumentError

from app.core.runtime_secrets import (
    RuntimeSecretConfigurationError,
    resolve_database_url,
)
from app.db.session import build_engine, build_session_factory
from app.repositories.auth_sessions import (
    AuthSessionRepository,
    InMemoryAuthSessionRepository,
    SqlAlchemyAuthSessionRepository,
)
from app.services.auth_sessions import AuthSessionService


class AuthSessionConfigurationError(RuntimeError):
    pass


def build_auth_session_service(
    environ: Mapping[str, str] | None = None,
) -> AuthSessionService:
    values = environ if environ is not None else os.environ
    app_env = values.get("APP_ENV", "development").strip().lower()
    try:
        database_url = resolve_database_url(values)
    except RuntimeSecretConfigurationError as exc:
        raise AuthSessionConfigurationError(
            "authentication database configuration is invalid"
        ) from exc
    local_environments = {"development", "test"}

    if not database_url:
        if app_env not in local_environments:
            raise AuthSessionConfigurationError(
                "deployed environments require DATABASE_URL for authentication"
            )
        repository: AuthSessionRepository = InMemoryAuthSessionRepository()
    else:
        if app_env not in local_environments and not database_url.startswith(
            "postgresql+psycopg://"
        ):
            raise AuthSessionConfigurationError(
                "deployed authentication requires PostgreSQL with psycopg"
            )
        try:
            repository = SqlAlchemyAuthSessionRepository(
                build_session_factory(build_engine(database_url))
            )
        except (ArgumentError, TypeError, ValueError) as exc:
            raise AuthSessionConfigurationError(
                "authentication storage configuration is invalid"
            ) from exc

    ttl_seconds = _read_ttl_seconds(values)
    return AuthSessionService(
        repository,
        ttl=timedelta(seconds=ttl_seconds),
        cookie_secure=app_env not in local_environments,
    )


def _read_ttl_seconds(values: Mapping[str, str]) -> int:
    raw_value = values.get("AUTH_SESSION_TTL_SECONDS", "2592000").strip()
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise AuthSessionConfigurationError(
            "AUTH_SESSION_TTL_SECONDS must be an integer"
        ) from exc
    if value < 300 or value > 31_536_000:
        raise AuthSessionConfigurationError(
            "AUTH_SESSION_TTL_SECONDS must be between 300 and 31536000"
        )
    return value
