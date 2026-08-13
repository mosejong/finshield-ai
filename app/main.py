from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.http_security import (
    install_http_security,
    verify_http_security_configuration,
)
from app.core.observability import install_observability
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
    verify_auth_session_storage()
    verify_financial_profile_storage()
    yield


app = FastAPI(
    title="FinShield AI",
    description="AI-powered financial social-engineering risk prevention MVP",
    version="0.1.0",
    lifespan=lifespan,
)
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
