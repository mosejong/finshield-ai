from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.core.observability import explanation_metrics, request_metrics


router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/metrics", include_in_schema=False, response_class=PlainTextResponse)
def metrics() -> PlainTextResponse:
    """프로세스 로컬 지표. 새 엔드포인트를 만들지 않는다.

    설명 계층 지표를 여기에 붙이는 것은 의도다. 엔드포인트를 새로 열면 그것이
    새 외부 표면이고, `CLAUDE.md` 의 보안 검토 대상이 된다. 붙이는 쪽은 이미
    `include_in_schema=False` 로 스키마에서 빠져 있고 배포에서 리버스 프록시가
    막는 경로다 - 지킬 자리를 하나 더 만들지 않는다.
    """
    return PlainTextResponse(
        request_metrics.prometheus_text() + explanation_metrics.prometheus_text(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
