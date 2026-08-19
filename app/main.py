from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.http_security import (
    install_http_security,
    verify_http_security_configuration,
)
from app.core.client_identity import verify_client_identity_configuration
from app.core.observability import install_observability
from app.core.rate_limit import (
    install_rate_limit,
    verify_rate_limit_configuration,
)
from app.core.request_limits import (
    install_request_limits,
    verify_request_limit_configuration,
)
from app.domain.fraud.sources import verify_official_sources
from app.services.llm.runtime import verify_llm_runtime_configuration
from app.api.routes.account import router as account_router
from app.api.routes.auth import (
    router as auth_router,
    verify_auth_session_storage,
)
from app.api.routes.health import router as health_router
from app.api.routes.guidance import router as guidance_router
from app.api.routes.analysis import router as analysis_router
from app.api.routes.loans import router as loans_router
from app.api.routes.observability import router as observability_router
from app.api.routes.products import router as products_router
from app.api.routes.profiles import (
    router as profiles_router,
    verify_financial_profile_storage,
)
from app.api.routes.recommendations import router as recommendations_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    verify_http_security_configuration()
    verify_request_limit_configuration()
    verify_client_identity_configuration()
    verify_rate_limit_configuration()
    verify_auth_session_storage()
    verify_financial_profile_storage()
    verify_official_sources()
    verify_llm_runtime_configuration()
    yield


app = FastAPI(
    title="FinShield AI",
    description="AI-powered financial social-engineering risk prevention MVP",
    version="0.1.0",
    lifespan=lifespan,
)
# `add_middleware` 는 바깥쪽에 끼워 넣는다. 나중에 부른 것이 더 바깥이다.
# 실행 순서(바깥 -> 안쪽):
#   observability -> http_security -> 본문 크기 제한 -> rate limit -> 라우터
#
# 크기 제한이 rate limit 보다 바깥인 이유: 거대한 본문은 세어보기 전에
# 끊어야 한다. 반대로 두면 한도 조회를 위해 DB 를 왕복하는 동안 본문을
# 계속 받는다.
# 둘 다 http_security 안쪽인 이유: 413·429 응답에도 보안 헤더가 붙어야 한다.
install_rate_limit(app)
install_request_limits(app)
install_http_security(app)
install_observability(app)

app.include_router(health_router)
app.include_router(observability_router)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(account_router, prefix="/api/v1")
app.include_router(guidance_router, prefix="/api/v1")
app.include_router(analysis_router, prefix="/api/v1")
app.include_router(loans_router, prefix="/api/v1")
app.include_router(products_router, prefix="/api/v1")
app.include_router(recommendations_router, prefix="/api/v1")
app.include_router(profiles_router, prefix="/api/v1")
