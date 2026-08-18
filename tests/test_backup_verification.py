"""복원 검증이 "열린다" 를 기준으로 판정하는지 확인한다.

기존 CI 복원 검사는 알려진 금융 값이 평문으로 보이지 않는지만 봤다. 그
기준은 무작위 바이트열도 통과시킨다. 아래 테스트들은 그 차이를 고정한다 -
특히 **키를 잃은 백업이 실패로 나오는지**.
"""

from datetime import UTC, datetime
import json
import os
from dataclasses import asdict
from pathlib import Path
from uuid import UUID, uuid4

from cryptography.fernet import Fernet
import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.backup_verification import (
    RestoreVerificationConfigurationError,
    verify_from_environment,
)
from app.db.base import Base
from app.db.models import FinancialProfileRecord, UserRecord
from app.db.session import build_engine, build_session_factory
from app.schemas.financial_profile import FinancialProfile
from app.security.profile_encryption import ProfileEncryptionKeyring
from app.services.backup_verification import verify_restored_profiles

OWNER_ID = UUID("00000000-0000-0000-0000-000000000001")
STORED_AT = datetime(2026, 8, 15, tzinfo=UTC)


def sample_profile() -> FinancialProfile:
    return FinancialProfile.model_validate(
        {
            "age_band": "20_29",
            "employment_status": "employed",
            "household_size": 2,
            "dependents_count": 1,
            "region": "서울",
            "monthly_net_income": "3500000.00",
            "monthly_fixed_expenses": "1200000.00",
            "monthly_variable_expenses": "600000.00",
            "liquid_assets": "10000000.00",
            "emergency_fund_target_months": 6,
            "total_debt": "5000000.00",
            "monthly_debt_payment": "250000.00",
            "loan_items": [
                {
                    "category": "credit_loan",
                    "balance": "5000000.00",
                    "annual_rate": "5.2500",
                    "remaining_months": 24,
                    "repayment_type": "equal_principal_and_interest",
                }
            ],
            "credit_score_band": "good",
            "business_owner": False,
            "goal": "debt_refinance",
        }
    )


def build_database(url: str = "sqlite+pysqlite://") -> tuple[Engine, sessionmaker[Session]]:
    engine = build_engine(url)
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)
    with session_factory() as session:
        session.add(
            UserRecord(
                user_id=str(OWNER_ID),
                kind="anonymous",
                status="active",
                created_at=STORED_AT,
            )
        )
        session.commit()
    return engine, session_factory


def store_profile(
    session_factory: sessionmaker[Session],
    keyring: ProfileEncryptionKeyring,
    *,
    profile_id: UUID | None = None,
    sealed_as: UUID | None = None,
) -> UUID:
    """행 하나를 만든다.

    `sealed_as` 는 봉투 안에 적히는 profile_id 다. 기본값은 행의 것과 같다.
    다르게 주면 dump/복원 과정에서 행 결합이 깨진 상황을 흉내낸다.
    """
    profile_id = profile_id or uuid4()
    encrypted = keyring.encrypt(sample_profile(), sealed_as or profile_id)
    with session_factory() as session:
        session.add(
            FinancialProfileRecord(
                profile_id=str(profile_id),
                owner_user_id=str(OWNER_ID),
                encrypted_profile=encrypted.ciphertext,
                encryption_key_id=encrypted.key_id,
                created_at=STORED_AT,
                updated_at=STORED_AT,
            )
        )
        session.commit()
    return profile_id


def overwrite_ciphertext(
    session_factory: sessionmaker[Session], profile_id: UUID, blob: bytes
) -> None:
    with session_factory() as session:
        record = session.get(FinancialProfileRecord, str(profile_id))
        assert record is not None
        record.encrypted_profile = blob
        session.commit()


def test_rows_that_open_are_recoverable() -> None:
    keyring = ProfileEncryptionKeyring([Fernet.generate_key().decode()])
    _, session_factory = build_database()
    for _ in range(3):
        store_profile(session_factory, keyring)

    verification = verify_restored_profiles(session_factory, keyring)

    assert verification.profiles == 3
    assert verification.decrypted == 3
    assert verification.failed == 0
    assert verification.unavailable_key_ids == ()
    assert verification.recoverable


def test_an_empty_restore_is_not_a_pass() -> None:
    """스키마만 돌아온 복원은 복구 가능성에 대해 아무것도 증명하지 않는다.

    행이 0 건인데 성공으로 처리하면, 백업이 빈 DB 를 담고 있어도 리허설은
    매번 초록불이 된다.
    """
    keyring = ProfileEncryptionKeyring([Fernet.generate_key().decode()])
    _, session_factory = build_database()

    verification = verify_restored_profiles(session_factory, keyring)

    assert verification.profiles == 0
    assert not verification.recoverable


def test_a_backup_without_its_key_fails_and_names_the_key() -> None:
    """P0-3 의 핵심. DB 만 돌아오고 키를 잃으면 복구가 아니다.

    기존 검사는 여기서 통과했다. 행은 멀쩡히 복원됐고 평문도 안 보이기
    때문이다. 실제로는 열 수 없는 바이트열만 남은 상태다.
    """
    writer = ProfileEncryptionKeyring([Fernet.generate_key().decode()])
    lost_key_reader = ProfileEncryptionKeyring([Fernet.generate_key().decode()])
    _, session_factory = build_database()
    store_profile(session_factory, writer)

    verification = verify_restored_profiles(session_factory, lost_key_reader)

    assert verification.profiles == 1
    assert verification.decrypted == 0
    assert verification.failed == 1
    # 어느 세대 키가 없는지까지 나와야 "잘못된 키 파일을 들고 왔다" 를
    # 바로 짚을 수 있다.
    assert verification.unavailable_key_ids == (writer.active_key_id,)
    assert not verification.recoverable


def test_random_bytes_do_not_pass_as_a_backup() -> None:
    """옛 기준과 새 기준이 갈리는 지점을 그대로 고정한다."""
    keyring = ProfileEncryptionKeyring([Fernet.generate_key().decode()])
    _, session_factory = build_database()
    profile_id = store_profile(session_factory, keyring)
    overwrite_ciphertext(session_factory, profile_id, os.urandom(256))

    with session_factory() as session:
        stored = session.scalar(select(FinancialProfileRecord))
        assert stored is not None
        # 옛 기준("평문 금융 값이 안 보인다")으로는 통과한다.
        assert b"3500000" not in stored.encrypted_profile

    # 새 기준으로는 실패한다.
    assert not verify_restored_profiles(session_factory, keyring).recoverable


def test_a_single_flipped_byte_fails() -> None:
    keyring = ProfileEncryptionKeyring([Fernet.generate_key().decode()])
    _, session_factory = build_database()
    profile_id = store_profile(session_factory, keyring)
    with session_factory() as session:
        original = session.get(FinancialProfileRecord, str(profile_id))
        assert original is not None
        blob = original.encrypted_profile
    overwrite_ciphertext(session_factory, profile_id, blob[:-1] + bytes([blob[-1] ^ 1]))

    verification = verify_restored_profiles(session_factory, keyring)

    assert verification.failed == 1
    assert not verification.recoverable


def test_a_broken_row_binding_fails_with_the_key_present() -> None:
    """복호화 성공은 "행이 제자리에 있다" 까지 증명한다.

    봉투 안의 profile_id 가 행의 것과 다르면 실패한다. 키는 멀쩡하므로
    `unavailable_key_ids` 는 비어 있어야 한다 - 진단이 엉뚱한 곳을 가리키면
    안 된다.
    """
    keyring = ProfileEncryptionKeyring([Fernet.generate_key().decode()])
    _, session_factory = build_database()
    store_profile(session_factory, keyring, sealed_as=uuid4())

    verification = verify_restored_profiles(session_factory, keyring)

    assert verification.failed == 1
    assert verification.unavailable_key_ids == ()
    assert not verification.recoverable


def test_rows_from_two_key_generations_all_open() -> None:
    """로테이션 중에 뜬 백업이 통째로 실패로 보이면 안 된다."""
    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()
    _, session_factory = build_database()
    store_profile(session_factory, ProfileEncryptionKeyring([old_key]))
    store_profile(session_factory, ProfileEncryptionKeyring([new_key]))

    verification = verify_restored_profiles(
        session_factory, ProfileEncryptionKeyring([new_key, old_key])
    )

    assert verification.profiles == 2
    assert verification.decrypted == 2
    assert len(verification.key_ids) == 2
    assert verification.recoverable


def test_one_missing_generation_is_enough_to_fail() -> None:
    """표본만 열어보면 놓치는 경우다. 절반은 열리고 절반은 안 열린다."""
    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()
    old_keyring = ProfileEncryptionKeyring([old_key])
    _, session_factory = build_database()
    store_profile(session_factory, old_keyring)
    store_profile(session_factory, ProfileEncryptionKeyring([new_key]))

    verification = verify_restored_profiles(
        session_factory, ProfileEncryptionKeyring([new_key])
    )

    assert verification.decrypted == 1
    assert verification.unavailable_key_ids == (old_keyring.active_key_id,)
    assert not verification.recoverable


def test_the_report_carries_no_financial_plaintext() -> None:
    """리허설 출력은 로그·CI 아티팩트에 남는다. 프로필이 새면 안 된다."""
    keyring = ProfileEncryptionKeyring([Fernet.generate_key().decode()])
    _, session_factory = build_database()
    store_profile(session_factory, keyring)

    rendered = json.dumps(
        asdict(verify_restored_profiles(session_factory, keyring)), ensure_ascii=False
    )

    for secret in ("3500000", "debt_refinance", "서울", "credit_loan"):
        assert secret not in rendered


def environment(tmp_path: Path, **overrides: str) -> dict[str, str]:
    values = {
        "APP_ENV": "test",
        "DATABASE_URL": f"sqlite+pysqlite:///{(tmp_path / 'restored.db').as_posix()}",
        "PROFILE_ENCRYPTION_KEYS": Fernet.generate_key().decode(),
    }
    values.update(overrides)
    return {key: value for key, value in values.items() if value}


def test_environment_wiring_reports_the_database_it_read(tmp_path: Path) -> None:
    """어느 DB 를 읽었는지 출력에 남는다.

    리허설이라고 생각하면서 운영 DB 를 읽고 "복구 가능" 이라고 결론 내는
    실수를 출력만 보고 잡을 수 있어야 한다.
    """
    key = Fernet.generate_key().decode()
    database = tmp_path / "restored.db"
    _, session_factory = build_database(f"sqlite+pysqlite:///{database.as_posix()}")
    store_profile(session_factory, ProfileEncryptionKeyring([key]))

    verification, name = verify_from_environment(
        environment(tmp_path, PROFILE_ENCRYPTION_KEYS=key)
    )

    assert verification.recoverable
    assert name.endswith("restored.db")


def test_verification_refuses_to_run_without_a_database(tmp_path: Path) -> None:
    with pytest.raises(RestoreVerificationConfigurationError, match="DATABASE_URL"):
        verify_from_environment(environment(tmp_path, DATABASE_URL=""))


def test_verification_refuses_to_run_without_keys(tmp_path: Path) -> None:
    """키 없이 돌면 전부 "열 수 없음" 이 된다. 그것을 백업 문제로 읽으면
    엉뚱한 곳을 파게 되므로 아예 시작하지 않는다."""
    with pytest.raises(
        RestoreVerificationConfigurationError, match="PROFILE_ENCRYPTION_KEYS"
    ):
        verify_from_environment(environment(tmp_path, PROFILE_ENCRYPTION_KEYS=""))


def test_verification_rejects_invalid_keys(tmp_path: Path) -> None:
    with pytest.raises(RestoreVerificationConfigurationError, match="keys are invalid"):
        verify_from_environment(
            environment(tmp_path, PROFILE_ENCRYPTION_KEYS="not-a-fernet-key")
        )


def test_deployed_verification_requires_postgresql(tmp_path: Path) -> None:
    """운영에서 sqlite 를 읽고 통과하면 검증한 대상이 백업이 아니다."""
    with pytest.raises(RestoreVerificationConfigurationError, match="PostgreSQL"):
        verify_from_environment(environment(tmp_path, APP_ENV="production"))
