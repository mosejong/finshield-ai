import json
import logging

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.observability import install_observability, request_metrics


def observed_app() -> FastAPI:
    app = FastAPI()
    install_observability(app)

    @app.post("/profiles/{profile_id}")
    async def profile(profile_id: str, request: Request) -> dict[str, str]:
        await request.body()
        return {"profile_id": profile_id}

    return app


def test_request_log_uses_route_template_and_excludes_pii(
) -> None:
    request_metrics.reset()
    secret_id = "123e4567-e89b-12d3-a456-426614174000"
    secret_body = "account=110-123-456789&income=2800000"
    secret_cookie = "finshield_session=raw-secret-token"
    records: list[logging.LogRecord] = []

    class CollectingHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = CollectingHandler()
    logger = logging.getLogger("finshield.request")
    logger.addHandler(handler)
    try:
        response = TestClient(observed_app()).post(
            f"/profiles/{secret_id}?message=private-text",
            content=secret_body,
            headers={
                "Cookie": secret_cookie,
                "Authorization": "Bearer private-auth-token",
                "X-Request-ID": "request-safe-123",
            },
        )
    finally:
        logger.removeHandler(handler)

    event = json.loads(records[-1].message)
    assert event == {
        "duration_ms": event["duration_ms"],
        "event": "http_request",
        "method": "POST",
        "request_id": "request-safe-123",
        "route": "/profiles/{profile_id}",
        "service": "finshield-api",
        "status_code": 200,
        "timestamp": event["timestamp"],
    }
    rendered = records[-1].message
    for secret in (
        secret_id,
        secret_body,
        secret_cookie,
        "private-text",
        "private-auth-token",
    ):
        assert secret not in rendered
    assert response.headers["x-request-id"] == "request-safe-123"
    assert response.headers["server-timing"].startswith("app;dur=")


def test_invalid_request_id_is_replaced_and_metrics_have_bounded_labels() -> None:
    request_metrics.reset()
    response = TestClient(observed_app()).post(
        "/profiles/private-id",
        content="secret",
        headers={"X-Request-ID": "bad id injected"},
    )

    generated = response.headers["x-request-id"]
    assert len(generated) == 32
    assert generated.isalnum()
    metrics = request_metrics.prometheus_text()
    assert 'route="/profiles/{profile_id}"' in metrics
    assert "private-id" not in metrics
    assert "secret" not in metrics
