from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.routes.profiles import get_financial_profile_service
from app.domain.finance.profile_metrics import calculate_profile_metrics
from app.main import app
from app.repositories.financial_profiles import InMemoryFinancialProfileRepository
from app.schemas.financial_profile import FinancialProfile
from app.services.financial_profiles import FinancialProfileService


def profile_data(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "age_band": "20_29",
        "employment_status": "employed",
        "household_size": 1,
        "dependents_count": 0,
        "monthly_net_income": "3500000.00",
        "monthly_fixed_expenses": "1200000.00",
        "monthly_variable_expenses": "600000.00",
        "liquid_assets": "10000000.00",
        "emergency_fund_target_months": 6,
        "total_debt": "5000000.00",
        "monthly_debt_payment": "250000.00",
        "loan_items": [],
        "credit_score_band": "good",
        "business_owner": False,
        "goal": "debt_refinance",
    }
    data.update(overrides)
    return data


def test_profile_metrics_calculation_is_deterministic() -> None:
    values = calculate_profile_metrics(FinancialProfile.model_validate(profile_data()))

    assert values.monthly_disposable_cashflow == Decimal("1450000.00")
    assert values.monthly_debt_payment_ratio_percent == Decimal("7.1")
    assert values.emergency_fund_coverage_months == Decimal("5.6")
    assert values.essential_monthly_expenses == Decimal("1800000.00")
    assert values.emergency_fund_target_amount == Decimal("10800000.00")
    assert values.emergency_fund_gap == Decimal("800000.00")


def test_profile_metrics_round_half_up_at_one_decimal() -> None:
    profile = FinancialProfile.model_validate(
        profile_data(
            monthly_net_income="6.00",
            monthly_fixed_expenses="6.00",
            monthly_variable_expenses="0.00",
            liquid_assets="1.00",
            total_debt="1.00",
            monthly_debt_payment="1.00",
        )
    )

    values = calculate_profile_metrics(profile)

    assert values.monthly_debt_payment_ratio_percent == Decimal("16.7")
    assert values.emergency_fund_coverage_months == Decimal("0.2")


def test_profile_metrics_do_not_invent_values_for_zero_denominators() -> None:
    profile = FinancialProfile.model_validate(
        profile_data(
            monthly_net_income="0.00",
            monthly_fixed_expenses="0.00",
            monthly_variable_expenses="0.00",
            liquid_assets="1000.00",
            total_debt="0.00",
            monthly_debt_payment="0.00",
        )
    )

    values = calculate_profile_metrics(profile)

    assert values.monthly_debt_payment_ratio_percent is None
    assert values.emergency_fund_coverage_months is None
    assert values.emergency_fund_gap == Decimal("0.00")


@pytest.fixture
def metrics_client() -> TestClient:
    service = FinancialProfileService(InMemoryFinancialProfileRepository())
    app.dependency_overrides[get_financial_profile_service] = lambda: service
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_financial_profile_service, None)


def test_profile_metrics_endpoint_returns_display_and_audit_values(
    metrics_client: TestClient,
) -> None:
    created = metrics_client.post("/api/v1/profiles", json=profile_data()).json()
    profile_id = UUID(created["profile_id"])

    response = metrics_client.get(f"/api/v1/profiles/{profile_id}/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "0.1"
    assert body["profile_id"] == str(profile_id)
    assert body["profile_updated_at"] == created["updated_at"]
    assert [metric["key"] for metric in body["metrics"]] == [
        "disposable_cashflow",
        "debt_payment_ratio",
        "emergency_fund_coverage",
    ]
    assert [metric["display"] for metric in body["metrics"]] == [
        "1,450,000원",
        "7.1%",
        "5.6개월",
    ]
    assert body["metrics"][2]["tone"] == "caution"
    assert all(metric["caveat"] for metric in body["metrics"])
    assert body["calculation"] == {
        "monthly_disposable_cashflow": "1450000.00",
        "monthly_debt_payment_ratio_percent": "7.1",
        "emergency_fund_coverage_months": "5.6",
        "essential_monthly_expenses": "1800000.00",
        "emergency_fund_target_amount": "10800000.00",
        "emergency_fund_gap": "800000.00",
    }
    assert "공식 DSR" in body["disclaimer"]


def test_profile_metrics_endpoint_handles_negative_and_unavailable_values(
    metrics_client: TestClient,
) -> None:
    created = metrics_client.post(
        "/api/v1/profiles",
        json=profile_data(
            monthly_net_income="0.00",
            monthly_fixed_expenses="0.00",
            monthly_variable_expenses="0.00",
            liquid_assets="0.00",
            total_debt="0.00",
            monthly_debt_payment="0.00",
        ),
    ).json()

    response = metrics_client.get(
        f"/api/v1/profiles/{created['profile_id']}/metrics"
    )

    assert response.status_code == 200
    metrics = response.json()["metrics"]
    assert metrics[1]["display"] == "계산 불가"
    assert metrics[2]["display"] == "계산 불가"


def test_emergency_fund_tone_uses_exact_target_gap_not_rounded_coverage(
    metrics_client: TestClient,
) -> None:
    created = metrics_client.post(
        "/api/v1/profiles",
        json=profile_data(
            monthly_fixed_expenses="1000.00",
            monthly_variable_expenses="0.00",
            liquid_assets="999.99",
            emergency_fund_target_months=1,
            total_debt="0.00",
            monthly_debt_payment="0.00",
        ),
    ).json()

    body = metrics_client.get(
        f"/api/v1/profiles/{created['profile_id']}/metrics"
    ).json()

    assert body["calculation"]["emergency_fund_coverage_months"] == "1.0"
    assert body["calculation"]["emergency_fund_gap"] == "0.01"
    assert body["metrics"][2]["tone"] == "caution"


def test_profile_metrics_endpoint_returns_404_for_unknown_profile(
    metrics_client: TestClient,
) -> None:
    response = metrics_client.get(f"/api/v1/profiles/{uuid4()}/metrics")

    assert response.status_code == 404
    assert response.json() == {"detail": "financial profile not found"}


def test_profile_metrics_openapi_contract_is_published(
    metrics_client: TestClient,
) -> None:
    schema = metrics_client.get("/openapi.json").json()
    operation = schema["paths"]["/api/v1/profiles/{profile_id}/metrics"]["get"]

    assert operation["responses"]["200"]["content"]["application/json"]["schema"]
    response_schema = schema["components"]["schemas"]["ProfileMetricsResponse"]
    assert {"metrics", "calculation", "assumptions", "disclaimer"}.issubset(
        response_schema["required"]
    )
