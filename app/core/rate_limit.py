"""rate limit 설정과 미들웨어 설치."""

import os
import secrets
from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import ArgumentError
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.client_identity import resolve_client_ip
from app.core.runtime_secrets import (
    RuntimeSecretConfigurationError,
    read_secret_setting,
    resolve_database_url,
)
from app.db.session import build_engine, build_session_factory
from app.repositories.rate_limits import (
    InMemoryRateLimitRepository,
    RateLimitRepository,
    SqlAlchemyRateLimitRepository,
)
from app.services.rate_limits import RateLimitDecision, RateLimitService

LOCAL_ENVIRONMENTS = frozenset({"development", "test"})


class RateLimitConfigurationError(RuntimeError):
    pass


def rate_limit_enabled(values: Mapping[str, str] | None = None) -> bool:
    settings = values if values is not None else os.environ
    app_env = settings.get("APP_ENV", "development").strip().lower()
    raw_value = settings.get("FINSHIELD_RATE_LIMIT_ENABLED", "").strip().lower()
    if not raw_value:
        # 로컬에서는 기본으로 끈다. 개발 중 새로고침 몇 번에 429 를 맞으면
        # 개발자가 제일 먼저 하는 일이 이 기능을 지우는 것이다.
        return app_env not in LOCAL_ENVIRONMENTS
    if raw_value in {"1", "true", "yes", "on"}:
        return True
    if raw_value in {"0", "false", "no", "off"}:
        return False
    raise RateLimitConfigurationError(
        "FINSHIELD_RATE_LIMIT_ENABLED must be a boolean value"
    )


def build_rate_limit_service(
    environ: Mapping[str, str] | None = None,
) -> RateLimitService:
    values = environ if environ is not None else os.environ
    app_env = values.get("APP_ENV", "development").strip().lower()
    deployed = app_env not in LOCAL_ENVIRONMENTS

    try:
        database_url = resolve_database_url(values)
        secret = read_secret_setting(values, "FINSHIELD_RATE_LIMIT_SECRET")
    except RuntimeSecretConfigurationError as exc:
        raise RateLimitConfigurationError(
            "rate limit configuration is invalid"
        ) from exc

    if not database_url:
        if deployed:
            raise RateLimitConfigurationError(
                "deployed environments require DATABASE_URL for rate limiting"
            )
        repository: RateLimitRepository = InMemoryRateLimitRepository()
    else:
        if deployed and not database_url.startswith("postgresql+psycopg://"):
            # SQLite 는 워커 간 카운터를 공유하지 못한다. 한도가 워커 수만큼
            # 헐거워지는데 겉으로는 정상으로 보인다.
            raise RateLimitConfigurationError(
                "deployed rate limiting requires PostgreSQL with psycopg"
            )
        try:
            repository = SqlAlchemyRateLimitRepository(
                build_session_factory(build_engine(database_url))
            )
        except (ArgumentError, TypeError, ValueError) as exc:
            raise RateLimitConfigurationError(
                "rate limit storage configuration is invalid"
            ) from exc

    if not secret:
        if deployed:
            # 워커마다 다른 비밀을 쓰면 같은 IP 가 워커마다 다른 bucket 으로
            # 흩어져, 공유 카운터를 쓰는 의미가 사라진다.
            raise RateLimitConfigurationError(
                "deployed environments require FINSHIELD_RATE_LIMIT_SECRET"
            )
        secret = secrets.token_urlsafe(32)
    elif len(secret) < 32:
        raise RateLimitConfigurationError(
            "FINSHIELD_RATE_LIMIT_SECRET must be at least 32 characters"
        )

    return RateLimitService(repository, secret=secret)


def verify_rate_limit_configuration(
    values: Mapping[str, str] | None = None,
) -> None:
    settings = values if values is not None else os.environ
    if not rate_limit_enabled(settings):
        return
    build_rate_limit_service(settings).verify_storage()


_service: RateLimitService | None = None


def rate_limit_service() -> RateLimitService:
    global _service
    if _service is None:
        _service = build_rate_limit_service()
    return _service


def reset_rate_limit_service() -> None:
    """캐시된 service 를 버린다.

    설정을 바꿔가며 확인하는 테스트에서만 쓴다. 카운터도 함께 사라지므로
    운영 중에 부르면 그 순간 모든 한도가 초기화된다.
    """
    global _service
    _service = None


def install_rate_limit(app: FastAPI) -> None:
    app.add_middleware(RateLimitMiddleware)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if not rate_limit_enabled():
            return await call_next(request)

        service = rate_limit_service()
        client_ip = resolve_client_ip(request.scope)
        # 저장소 접근은 동기 SQLAlchemy 다. 이벤트 루프에서 그대로 부르면
        # DB 왕복 동안 모든 요청이 멈춘다.
        decision = await run_in_threadpool(
            service.check,
            method=request.method,
            path=request.url.path,
            client_ip=client_ip,
        )

        if not decision.allowed:
            response: Response = JSONResponse(
                {
                    "detail": "too many requests",
                    "policy": decision.policy.name if decision.policy else None,
                    "retry_after_seconds": decision.retry_after_seconds,
                },
                status_code=429,
            )
        else:
            response = await call_next(request)
        return _annotate(response, decision)


def _annotate(response: Response, decision: RateLimitDecision) -> Response:
    if decision.policy is None:
        return response
    response.headers["RateLimit-Limit"] = str(decision.policy.limit)
    response.headers["RateLimit-Remaining"] = str(decision.remaining)
    if decision.reset_at is not None:
        response.headers["RateLimit-Reset"] = str(decision.retry_after_seconds)
    if not decision.allowed:
        response.headers["Retry-After"] = str(decision.retry_after_seconds)
    return response
