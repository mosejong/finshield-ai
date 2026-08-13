import os
from collections.abc import Mapping

from sqlalchemy.exc import ArgumentError

from app.db.session import build_engine, build_session_factory
from app.repositories.financial_profiles import (
    FinancialProfileRepository,
    InMemoryFinancialProfileRepository,
    SqlAlchemyFinancialProfileRepository,
)
from app.security.profile_encryption import ProfileEncryptionKeyring


class ProfileStorageConfigurationError(RuntimeError):
    pass


def build_financial_profile_repository(
    environ: Mapping[str, str] | None = None,
) -> FinancialProfileRepository:
    values = environ if environ is not None else os.environ
    app_env = values.get("APP_ENV", "development").strip().lower()
    database_url = values.get("DATABASE_URL", "").strip()
    encryption_keys = values.get("PROFILE_ENCRYPTION_KEYS", "").strip()

    local_environments = {"development", "test"}

    if not database_url and not encryption_keys:
        if app_env not in local_environments:
            raise ProfileStorageConfigurationError(
                "deployed environments require DATABASE_URL and "
                "PROFILE_ENCRYPTION_KEYS"
            )
        return InMemoryFinancialProfileRepository()

    if not database_url or not encryption_keys:
        raise ProfileStorageConfigurationError(
            "DATABASE_URL and PROFILE_ENCRYPTION_KEYS must be configured together"
        )

    if app_env not in local_environments and not database_url.startswith(
        "postgresql+psycopg://"
    ):
        raise ProfileStorageConfigurationError(
            "deployed financial profiles require PostgreSQL with psycopg"
        )

    try:
        keyring = ProfileEncryptionKeyring.from_comma_separated(encryption_keys)
        engine = build_engine(database_url)
    except (ArgumentError, TypeError, ValueError) as exc:
        raise ProfileStorageConfigurationError(
            "financial profile storage configuration is invalid"
        ) from exc

    return SqlAlchemyFinancialProfileRepository(
        build_session_factory(engine),
        keyring,
    )
