from fastapi.testclient import TestClient

from app.main import app


def test_liveness_and_readiness_are_distinct() -> None:
    with TestClient(app) as client:
        assert client.get("/health/live").json() == {"status": "alive"}
        assert client.get("/health/ready").json() == {"status": "ready"}


def test_internal_metrics_are_not_in_openapi() -> None:
    with TestClient(app) as client:
        response = client.get("/internal/metrics")
        schema = client.get("/openapi.json").json()

    assert response.status_code == 200
    assert "finshield_http_requests_total" in response.text
    assert "/internal/metrics" not in schema["paths"]
