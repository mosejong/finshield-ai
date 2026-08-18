"""복원 검증에 필요한 것들을 환경변수에서 조립한다."""

import os
from collections.abc import Mapping

from sqlalchemy.exc import ArgumentError
from sqlalchemy.engine import make_url

from app.core.runtime_secrets import (
    RuntimeSecretConfigurationError,
    resolve_database_url,
    resolve_profile_encryption_keys,
)
from app.db.session import build_engine, build_session_factory
from app.security.profile_encryption import (
    ProfileEncryptionConfigurationError,
    ProfileEncryptionKeyring,
)
from app.services.backup_verification import (
    RestoreVerification,
    verify_restored_profiles,
)

LOCAL_ENVIRONMENTS = frozenset({"development", "test"})


class RestoreVerificationConfigurationError(RuntimeError):
    pass


def verify_from_environment(
    values: Mapping[str, str] | None = None,
) -> tuple[RestoreVerification, str]:
    """검증 결과와 실제로 읽은 데이터베이스 이름을 함께 돌려준다.

    이름을 같이 내보내는 이유는, 리허설이라고 생각하면서 운영 DB 를 읽어놓고
    "복구 가능함" 이라는 결론을 내리는 실수가 가능하기 때문이다. 출력만 보고
    어느 DB 였는지 알 수 있어야 한다.
    """
    settings = values if values is not None else os.environ
    app_env = settings.get("APP_ENV", "development").strip().lower()

    try:
        database_url = resolve_database_url(settings)
        encryption_keys = resolve_profile_encryption_keys(settings)
    except RuntimeSecretConfigurationError as exc:
        raise RestoreVerificationConfigurationError(
            "restore verification secret configuration is invalid"
        ) from exc

    if not database_url:
        raise RestoreVerificationConfigurationError(
            "restore verification requires DATABASE_URL or database components"
        )
    if not encryption_keys:
        # 키 없이 돌면 모든 행이 "열 수 없음" 으로 나온다. 그것을 백업 문제로
        # 읽으면 엉뚱한 곳을 파게 된다. 애초에 검증을 시작하지 않는다.
        raise RestoreVerificationConfigurationError(
            "restore verification requires PROFILE_ENCRYPTION_KEYS"
        )
    if app_env not in LOCAL_ENVIRONMENTS and not database_url.startswith(
        "postgresql+psycopg://"
    ):
        raise RestoreVerificationConfigurationError(
            "deployed restore verification requires PostgreSQL with psycopg"
        )

    try:
        keyring = ProfileEncryptionKeyring.from_comma_separated(encryption_keys)
    except ProfileEncryptionConfigurationError as exc:
        raise RestoreVerificationConfigurationError(
            "restore verification encryption keys are invalid"
        ) from exc

    try:
        engine = build_engine(database_url)
        database_name = make_url(database_url).database or ""
    except (ArgumentError, TypeError, ValueError) as exc:
        raise RestoreVerificationConfigurationError(
            "restore verification database configuration is invalid"
        ) from exc

    try:
        verification = verify_restored_profiles(build_session_factory(engine), keyring)
    finally:
        engine.dispose()
    return verification, database_name
