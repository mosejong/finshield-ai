import os
from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


class HttpSecurityConfigurationError(RuntimeError):
    pass


API_CONTENT_SECURITY_POLICY = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"


def verify_http_security_configuration(
    values: Mapping[str, str] | None = None,
) -> None:
    settings = values if values is not None else os.environ
    app_env = settings.get("APP_ENV", "development").strip().lower()
    trusted_hosts = _trusted_hosts(settings)
    if app_env not in {"development", "test"} and not trusted_hosts:
        raise HttpSecurityConfigurationError(
            "deployed environments require FINSHIELD_TRUSTED_HOSTS"
        )


def install_http_security(app: FastAPI) -> None:
    app.add_middleware(HttpSecurityMiddleware)


class HttpSecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        app_env = os.getenv("APP_ENV", "development").strip().lower()
        if app_env not in {"development", "test"}:
            trusted_hosts = _trusted_hosts(os.environ)
            host = request.headers.get("host", "").partition(":")[0].lower()
            if not host or host not in trusted_hosts:
                response: Response = JSONResponse(
                    {"detail": "invalid host"},
                    status_code=400,
                )
                return _secure_response(response, deployed=True)

        response = await call_next(request)
        return _secure_response(
            response,
            deployed=app_env not in {"development", "test"},
        )


def _trusted_hosts(values: Mapping[str, str]) -> frozenset[str]:
    raw_value = values.get("FINSHIELD_TRUSTED_HOSTS", "")
    hosts = {
        value.strip().lower().partition(":")[0]
        for value in raw_value.split(",")
        if value.strip()
    }
    if "*" in hosts:
        raise HttpSecurityConfigurationError(
            "FINSHIELD_TRUSTED_HOSTS cannot contain a wildcard"
        )
    return frozenset(hosts)


def _secure_response(response: Response, *, deployed: bool) -> Response:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = API_CONTENT_SECURITY_POLICY
    response.headers["Cross-Origin-Resource-Policy"] = "same-site"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    if deployed:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response
