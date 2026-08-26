from fastapi import APIRouter

from app.schemas.analysis import (
    AnalyzeRequest,
    AnalyzeResponse,
    ExplanationResponse,
)
from app.services.fraud_analysis import analyze_fraud
from app.services.llm.outcomes import ExplanationOutcome
from app.services.llm.runtime import explain_with_fallback, explanation_runtime

router = APIRouter(tags=["analysis"])


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    return analyze_fraud(request)


@router.post("/analyze/explanation", response_model=ExplanationResponse)
def explain(request: AnalyzeRequest) -> ExplanationResponse:
    """판정을 문장으로 옮긴다. 판정 자체는 여기서도 서버가 다시 만든다.

    클라이언트가 `AnalyzeResponse` 를 보내게 하지 않는 것이 이 라우트의 핵심이다.
    그렇게 하면 위험 수준·신호·권고 행동을 클라이언트가 지어내서 보낼 수 있고,
    모델은 그 지어낸 근거 위에 그럴듯한 문장을 얹어 준다. 결정론 엔진을 두고도
    설명이 조작되는 경로가 생긴다.

    같은 입력에 같은 판정이 나오므로(`analyze_fraud` 는 순수 함수다) 다시 부르는
    비용은 무시할 만하고, 그 대가로 설명은 **항상 서버가 만든 근거**만 설명한다.
    """
    runtime = explanation_runtime()
    if runtime is None:
        return ExplanationResponse(available=False)

    response = analyze_fraud(request)
    result = explain_with_fallback(response, request.text, runtime=runtime)
    return ExplanationResponse(
        available=True,
        asked=result.outcome is not ExplanationOutcome.NOT_ASKED_NO_EVIDENCE,
        explanation=result.text,
        model=result.model,
    )
