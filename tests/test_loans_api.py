from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_simulate_loan_endpoint_returns_schedule_and_assumptions() -> None:
    response = client.post(
        "/api/v1/loans/simulate",
        json={
            "principal": "1200.00",
            "annual_interest_rate": "0",
            "months": 12,
            "repayment_type": "equal_principal_and_interest",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["monthly_payment"] == "100.00"
    assert body["total_repayment"] == "1200.00"
    assert body["total_interest"] == "0.00"
    assert len(body["schedule"]) == 12
    assert body["schedule"][-1]["remaining_principal"] == "0.00"
    assert any("ROUND_HALF_UP" in item for item in body["assumptions"])
    assert any("excluded" in item for item in body["assumptions"])


def test_simulate_loan_endpoint_rejects_invalid_input() -> None:
    response = client.post(
        "/api/v1/loans/simulate",
        json={
            "principal": "-1.00",
            "annual_interest_rate": "5",
            "months": 12,
            "repayment_type": "equal_principal",
        },
    )

    assert response.status_code == 422


def test_simulate_loan_endpoint_rejects_unknown_fields() -> None:
    response = client.post(
        "/api/v1/loans/simulate",
        json={
            "principal": "1000.00",
            "annual_interest_rate": "5",
            "months": 12,
            "repayment_type": "equal_principal",
            "otp": "123456",
        },
    )

    assert response.status_code == 422


def test_openapi_contains_loan_simulation_schema() -> None:
    schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/api/v1/loans/simulate"]["post"]

    assert operation["requestBody"]["required"] is True
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]
