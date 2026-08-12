from fastapi import APIRouter

from app.core.risk_engine import analyze_rules, risk_level
from app.schemas.analysis import AnalyzeRequest, AnalyzeResponse

router = APIRouter(tags=["analysis"])


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    score, signals = analyze_rules(request.text)

    return AnalyzeResponse(
        risk_score=score,
        risk_level=risk_level(score),
        signals=signals,
        scenario=request.state,
        disclaimer=(
            "현재 결과는 연구용 초기 위험 신호 분석이며 금융·법률 판단을 대신하지 않습니다."
        ),
    )
