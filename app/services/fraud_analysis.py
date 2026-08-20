from app.domain.fraud.classification import classify_fraud_types
from app.domain.fraud.policy import determine_risk_level, select_actions
from app.domain.fraud.signals import (
    baseline_score,
    contains_url,
    detect_canonical_signals,
    detect_legacy_signals,
    project_public_signals,
)
from app.domain.fraud.sources import sources_for_actions
from app.schemas.analysis import AnalyzeRequest, AnalyzeResponse, UserState


FRAUD_TYPE_LABELS: dict[str, str] = {
    "authority_impersonation": "기관 사칭",
    "loan_policy_impersonation": "대출·정책금융 사칭",
    "advance_fee_demand": "선입금·수수료 요구",
    "account_access_request": "계좌·인증수단 접근 요구",
    "money_mule_transfer": "자금 수취·재전달 요구",
    "smishing_malware": "스미싱·악성 앱 유도",
    "card_delivery_impersonation": "카드 배송 사칭",
}

URGENT_STATES = {
    UserState.SHARED_ACCOUNT_ACCESS,
    UserState.INSTALLED_APP,
    UserState.RECEIVED_UNKNOWN_MONEY,
    UserState.TRANSFERRED_MONEY,
}


def _build_summary(
    fraud_types: list[str], state: UserState, url_was_provided: bool
) -> str:
    if fraud_types:
        labels = ", ".join(FRAUD_TYPE_LABELS[fraud_type] for fraud_type in fraud_types)
        base = f"입력에서 {labels} 관련 위험 신호가 확인되었습니다."
    else:
        base = "현재 입력에서 명시적인 사기 위험 신호는 확인되지 않았습니다."

    if state in URGENT_STATES:
        base = f"{base} 이미 취한 행동에 맞춘 긴급 대응을 우선 확인하세요."
    elif state is not UserState.RECEIVED_ONLY:
        base = f"{base} 이미 취한 행동에 맞춘 대응 절차를 확인하세요."
    else:
        base = f"{base} 확정 판정이 아니므로 공식 채널을 통한 확인이 필요할 수 있습니다."

    if url_was_provided:
        return f"{base} URL에 접속하거나 평판을 확인하지 않아 안전 여부를 보증하지 않습니다."
    return base


def analyze_fraud(request: AnalyzeRequest) -> AnalyzeResponse:
    canonical_signals = detect_canonical_signals(request.text, request.url)
    legacy_signals = detect_legacy_signals(request.text)
    score = baseline_score(legacy_signals)
    fraud_types = classify_fraud_types(canonical_signals)
    level = determine_risk_level(score, canonical_signals, request.state)
    actions = select_actions(canonical_signals, request.state)
    official_sources = sources_for_actions(actions)
    public_signals = project_public_signals(canonical_signals)

    return AnalyzeResponse(
        risk_score=score,
        risk_level=level,
        signals=public_signals,
        scenario=request.state,
        disclaimer=(
            "현재 결과는 실험적 규칙 기반 위험 신호 분석이며 범죄 확정, "
            "금융·법률 판단 또는 공식 신고 절차를 대신하지 않습니다."
        ),
        fraud_types=fraud_types,
        summary=_build_summary(
            fraud_types,
            request.state,
            contains_url(request.text, request.url),
        ),
        actions=actions,
        official_sources=official_sources,
    )
