from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections.abc import Callable
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Engine, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.profile_storage import (
    ProfileStorageConfigurationError,
    build_financial_profile_repository,
)
from app.api.routes.auth import get_current_session
from app.api.routes.profiles import get_financial_profile_service
from app.main import app
from app.db.base import Base
from app.db.models import FinancialProfileRecord, UserRecord
from app.db.session import build_engine, build_session_factory
from app.repositories.financial_profiles import (
    FinancialProfileNotFoundError,
    FinancialProfileStorageError,
    InMemoryFinancialProfileRepository,
    SqlAlchemyFinancialProfileRepository,
)
from app.schemas.financial_profile import FinancialGoal, FinancialProfile
from app.schemas.auth import SessionPrincipal
from app.security.profile_encryption import (
    ProfileDecryptionError,
    ProfileEncryptionConfigurationError,
    ProfileEncryptionKeyring,
)
from app.services.financial_profiles import FinancialProfileService


TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
OTHER_USER_ID = UUID("00000000-0000-0000-0000-000000000002")


def principal_override() -> SessionPrincipal:
    now = datetime(2026, 8, 13, tzinfo=timezone.utc)
    return SessionPrincipal(
        user_id=TEST_USER_ID,
        created_at=now,
        expires_at=now + timedelta(days=30),
    )


def valid_profile() -> FinancialProfile:
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


def build_repository(
    keys: list[str] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> tuple[
    SqlAlchemyFinancialProfileRepository,
    sessionmaker[Session],
    Engine,
    ProfileEncryptionKeyring,
]:
    engine = build_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)
    now = datetime(2026, 8, 13, tzinfo=timezone.utc)
    with session_factory() as session:
        session.add_all(
            [
                UserRecord(
                    user_id=str(user_id),
                    kind="anonymous",
                    status="active",
                    created_at=now,
                )
                for user_id in (TEST_USER_ID, OTHER_USER_ID)
            ]
        )
        session.commit()
    keyring = ProfileEncryptionKeyring(keys or [Fernet.generate_key().decode()])
    repository = SqlAlchemyFinancialProfileRepository(
        session_factory,
        keyring,
        clock=clock,
    )
    return repository, session_factory, engine, keyring


def test_keyring_encrypts_and_authenticates_profile() -> None:
    keyring = ProfileEncryptionKeyring([Fernet.generate_key().decode()])
    profile_id = uuid4()
    encrypted = keyring.encrypt(valid_profile(), profile_id)

    assert b"3500000" not in encrypted.ciphertext
    assert b"debt_refinance" not in encrypted.ciphertext
    assert (
        keyring.decrypt(encrypted.ciphertext, encrypted.key_id, profile_id)
        == valid_profile()
    )

    tampered = encrypted.ciphertext[:-1] + bytes([encrypted.ciphertext[-1] ^ 1])
    with pytest.raises(ProfileDecryptionError, match="could not be verified"):
        keyring.decrypt(tampered, encrypted.key_id, profile_id)

    with pytest.raises(ProfileDecryptionError, match="could not be verified"):
        keyring.decrypt(encrypted.ciphertext, encrypted.key_id, uuid4())


def test_keyring_rejects_missing_and_invalid_keys() -> None:
    with pytest.raises(ProfileEncryptionConfigurationError):
        ProfileEncryptionKeyring([])
    with pytest.raises(ProfileEncryptionConfigurationError, match="invalid Fernet"):
        ProfileEncryptionKeyring(["not-a-key"])

    writer = ProfileEncryptionKeyring([Fernet.generate_key().decode()])
    profile_id = uuid4()
    encrypted = writer.encrypt(valid_profile(), profile_id)
    reader = ProfileEncryptionKeyring([Fernet.generate_key().decode()])
    with pytest.raises(ProfileDecryptionError, match="unavailable"):
        reader.decrypt(encrypted.ciphertext, encrypted.key_id, profile_id)


def test_sql_repository_persists_only_ciphertext_and_survives_new_instance() -> None:
    repository, session_factory, _, keyring = build_repository()
    profile = valid_profile()
    repository.verify()
    created = repository.create(profile, TEST_USER_ID)

    with session_factory() as session:
        stored = session.scalar(select(FinancialProfileRecord))
        assert stored is not None
        assert stored.profile_id == str(created.profile_id)
        assert b"3500000" not in stored.encrypted_profile
        assert b"debt_refinance" not in stored.encrypted_profile
        assert len(stored.encryption_key_id) == 32

    restarted_repository = SqlAlchemyFinancialProfileRepository(
        session_factory,
        keyring,
    )
    assert restarted_repository.get(created.profile_id, TEST_USER_ID) == created


def test_sql_repository_crud_and_timestamp_contract() -> None:
    initial_time = datetime(2026, 8, 13, 4, 0, tzinfo=timezone.utc)
    repository, _, _, _ = build_repository(clock=lambda: initial_time)
    created = repository.create(valid_profile(), TEST_USER_ID)

    replacement = valid_profile().model_copy(update={"goal": FinancialGoal.ASSET_BUILDING})
    replaced = repository.replace(created.profile_id, replacement, TEST_USER_ID)

    assert replaced.created_at == created.created_at
    assert replaced.updated_at > created.updated_at
    assert (
        repository.get(created.profile_id, TEST_USER_ID).profile.goal
        is FinancialGoal.ASSET_BUILDING
    )

    repository.delete(created.profile_id, TEST_USER_ID)
    with pytest.raises(FinancialProfileNotFoundError):
        repository.get(created.profile_id, TEST_USER_ID)


def test_key_rotation_reads_old_rows_and_uses_active_key_on_replace() -> None:
    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()
    old_repository, session_factory, _, _ = build_repository([old_key])
    created = old_repository.create(valid_profile(), TEST_USER_ID)

    rotating_keyring = ProfileEncryptionKeyring([new_key, old_key])
    rotating_repository = SqlAlchemyFinancialProfileRepository(
        session_factory, rotating_keyring
    )
    assert (
        rotating_repository.get(created.profile_id, TEST_USER_ID).profile
        == valid_profile()
    )

    rotating_repository.replace(created.profile_id, valid_profile(), TEST_USER_ID)
    with session_factory() as session:
        stored = session.get(FinancialProfileRecord, str(created.profile_id))
        assert stored is not None
        assert stored.encryption_key_id == rotating_keyring.active_key_id


def test_corrupted_ciphertext_fails_closed_as_storage_error() -> None:
    repository, session_factory, _, _ = build_repository()
    created = repository.create(valid_profile(), TEST_USER_ID)
    with session_factory() as session:
        stored = session.get(FinancialProfileRecord, str(created.profile_id))
        assert stored is not None
        stored.encrypted_profile = b"corrupted"
        session.commit()

    with pytest.raises(FinancialProfileStorageError, match="decryption failed"):
        repository.get(created.profile_id, TEST_USER_ID)


def test_ciphertext_cannot_be_swapped_between_profile_rows() -> None:
    repository, session_factory, _, _ = build_repository()
    first = repository.create(valid_profile(), TEST_USER_ID)
    second = repository.create(
        valid_profile().model_copy(update={"goal": FinancialGoal.ASSET_BUILDING}),
        TEST_USER_ID,
    )
    with session_factory() as session:
        first_row = session.get(FinancialProfileRecord, str(first.profile_id))
        second_row = session.get(FinancialProfileRecord, str(second.profile_id))
        assert first_row is not None
        assert second_row is not None
        second_row.encrypted_profile = first_row.encrypted_profile
        second_row.encryption_key_id = first_row.encryption_key_id
        session.commit()

    with pytest.raises(FinancialProfileStorageError, match="decryption failed"):
        repository.get(second.profile_id, TEST_USER_ID)


def test_profile_storage_configuration_is_fail_closed() -> None:
    assert isinstance(
        build_financial_profile_repository({"APP_ENV": "development"}),
        InMemoryFinancialProfileRepository,
    )

    with pytest.raises(ProfileStorageConfigurationError, match="deployed environments"):
        build_financial_profile_repository({"APP_ENV": "production"})
    with pytest.raises(ProfileStorageConfigurationError, match="deployed environments"):
        build_financial_profile_repository({"APP_ENV": "staging"})
    with pytest.raises(ProfileStorageConfigurationError, match="configured together"):
        build_financial_profile_repository(
            {"APP_ENV": "development", "DATABASE_URL": "sqlite+pysqlite://"}
        )
    with pytest.raises(ProfileStorageConfigurationError, match="require PostgreSQL"):
        build_financial_profile_repository(
            {
                "APP_ENV": "production",
                "DATABASE_URL": "sqlite+pysqlite://",
                "PROFILE_ENCRYPTION_KEYS": Fernet.generate_key().decode(),
            }
        )


def test_sql_repository_verify_rejects_missing_migration() -> None:
    engine = build_engine("sqlite+pysqlite://")
    repository = SqlAlchemyFinancialProfileRepository(
        build_session_factory(engine),
        ProfileEncryptionKeyring([Fernet.generate_key().decode()]),
    )

    with pytest.raises(FinancialProfileStorageError, match="migration"):
        repository.verify()


def test_unknown_sql_profile_id_is_not_found() -> None:
    repository, _, _, _ = build_repository()
    with pytest.raises(FinancialProfileNotFoundError):
        repository.get(uuid4(), TEST_USER_ID)


def test_sql_repository_hides_profile_from_other_owner() -> None:
    repository, _, _, _ = build_repository()
    created = repository.create(valid_profile(), TEST_USER_ID)

    with pytest.raises(FinancialProfileNotFoundError):
        repository.get(created.profile_id, OTHER_USER_ID)
    with pytest.raises(FinancialProfileNotFoundError):
        repository.replace(created.profile_id, valid_profile(), OTHER_USER_ID)
    with pytest.raises(FinancialProfileNotFoundError):
        repository.delete(created.profile_id, OTHER_USER_ID)

    assert repository.get(created.profile_id, TEST_USER_ID) == created


def test_api_returns_generic_503_without_storage_details() -> None:
    class UnavailableRepository:
        def get(self, profile_id: object, owner_user_id: object) -> object:
            raise FinancialProfileStorageError(
                "database host and encrypted payload must stay private"
            )

    app.dependency_overrides[get_financial_profile_service] = lambda: (
        FinancialProfileService(UnavailableRepository())  # type: ignore[arg-type]
    )
    app.dependency_overrides[get_current_session] = principal_override
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/profiles/{uuid4()}")
    finally:
        app.dependency_overrides.pop(get_financial_profile_service, None)
        app.dependency_overrides.pop(get_current_session, None)

    assert response.status_code == 503
    assert response.json() == {"detail": "financial profile storage unavailable"}
    assert "database host" not in response.text


def test_alembic_migration_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database_path = tmp_path / "migration.sqlite3"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config("alembic.ini")

    command.upgrade(config, "head")
    engine = build_engine(database_url)
    assert set(inspect(engine).get_table_names()) == {
        "alembic_version",
        "auth_sessions",
        "financial_profiles",
        "users",
    }
    assert {column["name"] for column in inspect(engine).get_columns("financial_profiles")} == {
        "profile_id",
        "encrypted_profile",
        "encryption_key_id",
        "created_at",
        "updated_at",
        "owner_user_id",
    }

    command.downgrade(config, "base")
    assert "financial_profiles" not in inspect(engine).get_table_names()
    command.upgrade(config, "head")
    assert "financial_profiles" in inspect(engine).get_table_names()
