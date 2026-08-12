from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.api.routes.analysis import router as analysis_router
from app.api.routes.loans import router as loans_router

app = FastAPI(
    title="FinShield AI",
    description="AI-powered financial social-engineering risk prevention MVP",
    version="0.1.0",
)

app.include_router(health_router)
app.include_router(analysis_router, prefix="/api/v1")
app.include_router(loans_router, prefix="/api/v1")
