from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from app.api.routes.auth import get_auth_session_service
from app.api.routes.profiles import get_financial_profile_service
from app.core.auth_sessions import (
    AuthSessionConfigurationError,
    build_auth_session_service,
)
from app.db.base import Base
from app.db.models import AuthSessionRecord, UserRecord
from app.db.session import build_engine, build_session_factory
from app.main import app
from app.repositories.auth_sessions import (
    AuthSessionNotFoundError,
    AuthSessionStorageError,
    InMemoryAuthSessionRepository,
    SqlAlchemyAuthSessionRepository,
)
from app.repositories.financial_profiles import InMemoryFinancialProfileRepository
from app.services.auth_sessions import AuthSessionService
from app.services.financial_profiles import FinancialProfileService


NOW = datetime(2026, 8, 13, 6, 0, tzinfo=timezone.utc)


def build_service(
    *,
    now: datetime = NOW,
    secure: bool = False,
) -> AuthSessionService:
    return AuthSessionService(
        InMemoryAuthSessionRepository(),
        ttl=timedelta(days=30),
        cookie_secure=secure,
        clock=lambda: now,
    )


def valid_profile_data() -> dict[str, object]:
    return {
        "age_band": "20_29",
        "employment_status": "employed",
        "household_size": 1,
        "dependents_count": 0,
        "monthly_net_income": "3500000.00",
        "monthly_fixed_expenses": "1200000.00",
        "monthly_variable_expenses": "600000.00",
        "liquid_assets": "10000000.00",
        "emergency_fund_target_months": 6,
        "total_debt": "0.00",
        "monthly_debt_payment": "0.00",
        "loan_items": [],
        "credit_score_band": "good",
        "business_owner": False,
        "goal": "asset_building",
    }


def test_service_bootstrap_reuses_valid_token_and_rejects_expired_token() -> None:
    now = [NOW]
    service = AuthSessionService(
        InMemoryAuthSessionRepository(),
        ttl=timedelta(minutes=5),
        clock=lambda: now[0],
    )

    issued = service.bootstrap(None)
    assert issued.raw_token is not None
    assert service.authenticate(issued.raw_token) == issued.principal

    reused = service.bootstrap(issued.raw_token)
    assert reused.raw_token is None
    assert reused.principal == issued.principal

    now[0] += timedelta(minutes=5)
    with pytest.raises(AuthSessionNotFoundError):
        service.authenticate(issued.raw_token)


def test_service_revoke_and_invalid_token_fail_closed() -> None:
    service = build_service()
    issued = service.bootstrap(None)
    assert issued.raw_token is not None

    service.revoke(issued.raw_token)
    with pytest.raises(AuthSessionNotFoundError):
        service.authenticate(issued.raw_token)
    with pytest.raises(AuthSessionNotFoundError):
        service.authenticate("short")


def test_sql_storage_persists_only_token_hash_and_survives_service_restart() -> None:
    engine = build_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)
    repository = SqlAlchemyAuthSessionRepository(session_factory)
    service = AuthSessionService(repository, clock=lambda: NOW)

    issued = service.bootstrap(None)
    assert issued.raw_token is not None
    expected_hash = sha256(issued.raw_token.encode("utf-8")).hexdigest()

    with session_factory() as session:
        stored_session = session.scalar(select(AuthSessionRecord))
        stored_user = session.scalar(select(UserRecord))
        assert stored_session is not None
        assert stored_user is not None
        assert stored_session.token_hash == expected_hash
        assert stored_session.token_hash != issued.raw_token
        assert len(stored_session.token_hash) == 64

    restarted = AuthSessionService(repository, clock=lambda: NOW)
    assert restarted.authenticate(issued.raw_token) == issued.principal


def test_sql_storage_verify_rejects_partial_migration() -> None:
    engine = build_engine("sqlite+pysqlite://")
    UserRecord.__table__.create(engine)
    AuthSessionRecord.__table__.create(engine)
    repository = SqlAlchemyAuthSessionRepository(build_session_factory(engine))

    with pytest.raises(AuthSessionStorageError, match="migration"):
        repository.verify()


def test_deployed_auth_configuration_fails_closed() -> None:
    with pytest.raises(AuthSessionConfigurationError, match="DATABASE_URL"):
        build_auth_session_service({"APP_ENV": "production"})
    with pytest.raises(AuthSessionConfigurationError, match="PostgreSQL"):
        build_auth_session_service(
            {
                "APP_ENV": "production",
                "DATABASE_URL": "sqlite+pysqlite://",
            }
        )
    with pytest.raises(AuthSessionConfigurationError, match="integer"):
        build_auth_session_service(
            {
                "APP_ENV": "development",
                "AUTH_SESSION_TTL_SECONDS": "invalid",
            }
        )


def test_auth_api_sets_strict_http_only_cookie_without_returning_token() -> None:
    service = build_service()
    app.dependency_overrides[get_auth_session_service] = lambda: service
    try:
        with TestClient(app) as client:
            created = client.post("/api/v1/auth/session")
            assert created.status_code == 201
            cookie = created.headers["set-cookie"].lower()
            assert "finshield_session=" in cookie
            assert "httponly" in cookie
            assert "samesite=strict" in cookie
            assert "secure" not in cookie
            assert "token" not in created.json()

            current = client.get("/api/v1/auth/session")
            assert current.status_code == 200
            assert current.json()["user_id"] == created.json()["user_id"]

            deleted = client.delete("/api/v1/auth/session")
            assert deleted.status_code == 204
            assert "httponly" in deleted.headers["set-cookie"].lower()
            assert client.get("/api/v1/auth/session").status_code == 401
    finally:
        app.dependency_overrides.pop(get_auth_session_service, None)


def test_production_cookie_has_secure_attribute() -> None:
    service = build_service(secure=True)
    app.dependency_overrides[get_auth_session_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/auth/session")
    finally:
        app.dependency_overrides.pop(get_auth_session_service, None)

    assert "secure" in response.headers["set-cookie"].lower()


def test_profile_routes_require_session_and_hide_other_owners_records() -> None:
    auth_service = build_service()
    profile_service = FinancialProfileService(InMemoryFinancialProfileRepository())
    app.dependency_overrides[get_auth_session_service] = lambda: auth_service
    app.dependency_overrides[get_financial_profile_service] = lambda: profile_service
    try:
        with TestClient(app) as unauthenticated:
            assert (
                unauthenticated.get(f"/api/v1/profiles/{uuid4()}").status_code
                == 401
            )

        with TestClient(app) as owner, TestClient(app) as other:
            assert owner.post("/api/v1/auth/session").status_code == 201
            assert other.post("/api/v1/auth/session").status_code == 201
            created = owner.post("/api/v1/profiles", json=valid_profile_data())
            assert created.status_code == 201
            profile_id = UUID(created.json()["profile_id"])

            assert other.get(f"/api/v1/profiles/{profile_id}").status_code == 404
            assert (
                other.put(
                    f"/api/v1/profiles/{profile_id}",
                    json=valid_profile_data(),
                ).status_code
                == 404
            )
            assert (
                other.get(f"/api/v1/profiles/{profile_id}/metrics").status_code
                == 404
            )
            assert other.delete(f"/api/v1/profiles/{profile_id}").status_code == 404
            assert owner.get(f"/api/v1/profiles/{profile_id}").status_code == 200
    finally:
        app.dependency_overrides.pop(get_auth_session_service, None)
        app.dependency_overrides.pop(get_financial_profile_service, None)
