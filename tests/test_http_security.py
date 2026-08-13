from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.core.http_security import (
    HttpSecurityConfigurationError,
    install_http_security,
    verify_http_security_configuration,
)


def security_app() -> FastAPI:
    app = FastAPI()
    install_http_security(app)

    @app.get("/resource")
    def resource() -> dict[str, str]:
        return {"status": "ok"}

    return app


def test_api_security_headers_do_not_enable_hsts_on_local_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    response = TestClient(security_app()).get("/resource")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-security-policy"] == (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "strict-transport-security" not in response.headers


def test_deployed_security_rejects_untrusted_host_and_enables_hsts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("FINSHIELD_TRUSTED_HOSTS", "backend,localhost")
    client = TestClient(security_app())

    rejected = client.get("http://untrusted.example/resource")
    accepted = client.get("http://localhost/resource")

    assert rejected.status_code == 400
    assert rejected.json() == {"detail": "invalid host"}
    assert accepted.status_code == 200
    assert accepted.headers["strict-transport-security"] == (
        "max-age=31536000; includeSubDomains"
    )


def test_deployed_security_configuration_is_fail_closed() -> None:
    with pytest.raises(HttpSecurityConfigurationError, match="TRUSTED_HOSTS"):
        verify_http_security_configuration({"APP_ENV": "production"})
    with pytest.raises(HttpSecurityConfigurationError, match="wildcard"):
        verify_http_security_configuration(
            {"APP_ENV": "production", "FINSHIELD_TRUSTED_HOSTS": "*"}
        )

    verify_http_security_configuration(
        {"APP_ENV": "production", "FINSHIELD_TRUSTED_HOSTS": "backend"}
    )
