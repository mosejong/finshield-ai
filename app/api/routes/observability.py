from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.core.observability import request_metrics


router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/metrics", include_in_schema=False, response_class=PlainTextResponse)
def metrics() -> PlainTextResponse:
    return PlainTextResponse(
        request_metrics.prometheus_text(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
