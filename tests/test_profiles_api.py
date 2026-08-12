from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.routes.profiles import get_financial_profile_service
from app.main import app
from app.repositories.financial_profiles import (
    FinancialProfileCapacityError,
    InMemoryFinancialProfileRepository,
)
from app.schemas.financial_profile import FinancialGoal, FinancialProfile
from app.services.financial_profiles import FinancialProfileService


def valid_profile_data() -> dict[str, object]:
    return {
        "age_band": "20_29",
        "employment_status": "employed",
        "household_size": 2,
        "dependents_count": 1,
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


@pytest.fixture
def profile_client() -> TestClient:
    service = FinancialProfileService(InMemoryFinancialProfileRepository())
    app.dependency_overrides[get_financial_profile_service] = lambda: service
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_financial_profile_service, None)


def test_profile_crud_flow(profile_client: TestClient) -> None:
    create_response = profile_client.post(
        "/api/v1/profiles", json=valid_profile_data()
    )

    assert create_response.status_code == 201
    created = create_response.json()
    profile_id = UUID(created["profile_id"])
    created_at = datetime.fromisoformat(created["created_at"])
    updated_at = datetime.fromisoformat(created["updated_at"])
    assert created_at.tzinfo is not None
    assert created_at == updated_at
    assert created["profile"]["goal"] == "debt_refinance"

    get_response = profile_client.get(f"/api/v1/profiles/{profile_id}")
    assert get_response.status_code == 200
    assert get_response.json() == created

    replacement = valid_profile_data()
    replacement["goal"] = "asset_building"
    replace_response = profile_client.put(
        f"/api/v1/profiles/{profile_id}", json=replacement
    )

    assert replace_response.status_code == 200
    replaced = replace_response.json()
    assert replaced["profile_id"] == str(profile_id)
    assert replaced["created_at"] == created["created_at"]
    assert datetime.fromisoformat(replaced["updated_at"]) > updated_at
    assert replaced["profile"]["goal"] == "asset_building"

    delete_response = profile_client.delete(f"/api/v1/profiles/{profile_id}")
    assert delete_response.status_code == 204
    assert delete_response.content == b""
    assert profile_client.get(f"/api/v1/profiles/{profile_id}").status_code == 404


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_profile_operations_return_404_for_unknown_id(
    profile_client: TestClient, method: str
) -> None:
    profile_id = uuid4()
    if method == "get":
        response = profile_client.get(f"/api/v1/profiles/{profile_id}")
    elif method == "put":
        response = profile_client.put(
            f"/api/v1/profiles/{profile_id}", json=valid_profile_data()
        )
    else:
        response = profile_client.delete(f"/api/v1/profiles/{profile_id}")

    assert response.status_code == 404
    assert response.json() == {"detail": "financial profile not found"}


def test_profile_endpoint_rejects_malformed_id(profile_client: TestClient) -> None:
    response = profile_client.get("/api/v1/profiles/not-a-uuid")

    assert response.status_code == 422


@pytest.mark.parametrize("method", ["post", "put"])
def test_profile_writes_reject_sensitive_or_server_managed_fields(
    profile_client: TestClient, method: str
) -> None:
    data = valid_profile_data()
    data["otp"] = "123456"

    if method == "post":
        response = profile_client.post("/api/v1/profiles", json=data)
    else:
        created = profile_client.post(
            "/api/v1/profiles", json=valid_profile_data()
        ).json()
        response = profile_client.put(
            f"/api/v1/profiles/{created['profile_id']}", json=data
        )

    assert response.status_code == 422


def test_profile_capacity_is_explicit_service_failure() -> None:
    service = FinancialProfileService(
        InMemoryFinancialProfileRepository(max_profiles=1)
    )
    app.dependency_overrides[get_financial_profile_service] = lambda: service
    try:
        with TestClient(app) as client:
            assert client.post(
                "/api/v1/profiles", json=valid_profile_data()
            ).status_code == 201
            response = client.post("/api/v1/profiles", json=valid_profile_data())
    finally:
        app.dependency_overrides.pop(get_financial_profile_service, None)

    assert response.status_code == 503
    assert response.json() == {"detail": "profile storage capacity reached"}


def test_repository_returns_defensive_copies() -> None:
    repository = InMemoryFinancialProfileRepository()
    profile = FinancialProfile.model_validate(valid_profile_data())
    created = repository.create(profile)

    created.profile.goal = FinancialGoal.ASSET_BUILDING
    fetched = repository.get(created.profile_id)

    assert fetched.profile.goal is FinancialGoal.DEBT_REFINANCE


def test_repository_rejects_naive_clock() -> None:
    repository = InMemoryFinancialProfileRepository(
        clock=lambda: datetime(2026, 8, 12)
    )
    profile = FinancialProfile.model_validate(valid_profile_data())

    with pytest.raises(ValueError, match="timezone-aware"):
        repository.create(profile)


def test_repository_normalizes_timestamp_to_utc() -> None:
    repository = InMemoryFinancialProfileRepository(
        clock=lambda: datetime(2026, 8, 12, tzinfo=timezone.utc)
    )
    record = repository.create(FinancialProfile.model_validate(valid_profile_data()))

    assert record.created_at.tzinfo is timezone.utc


def test_repository_capacity_remains_bounded_under_concurrent_writes() -> None:
    repository = InMemoryFinancialProfileRepository(max_profiles=10)
    profile = FinancialProfile.model_validate(valid_profile_data())

    def create_once() -> bool:
        try:
            repository.create(profile)
        except FinancialProfileCapacityError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=20) as executor:
        outcomes = list(executor.map(lambda _: create_once(), range(20)))

    assert outcomes.count(True) == 10
    assert outcomes.count(False) == 10


def test_profile_openapi_exposes_crud_without_list_endpoint(
    profile_client: TestClient,
) -> None:
    paths = profile_client.get("/openapi.json").json()["paths"]

    assert set(paths["/api/v1/profiles"].keys()) == {"post"}
    assert set(paths["/api/v1/profiles/{profile_id}"].keys()) == {
        "get",
        "put",
        "delete",
    }
