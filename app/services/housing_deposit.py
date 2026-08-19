"""전세보증금 위험 점검 조립.

계산(`domain/housing/deposit_risk.py`)과 규칙(`domain/housing/policy.py`)의
결과를 응답 모양으로 옮기기만 한다. 여기서 새 판단을 만들지 않는다.
"""

from app.domain.housing.deposit_risk import (
    RATIO_FORMULA,
    compute_protection,
    compute_ratio,
)
from app.domain.housing.policy import (
    detect_signals,
    determine_risk_level,
    select_actions,
)
from app.domain.housing.sources import sources_for_actions
from app.schemas.housing import (
    DepositProtection,
    DepositRatio,
    DepositRiskRequest,
    DepositRiskResponse,
    LeaseStage,
)


DISCLAIMER = (
    "이 점검은 입력한 값에 대한 규칙 기반 확인이며 법률 자문, 계약 안전 보증, "
    "전세사기 여부 판단을 대신하지 않습니다. 위험 구간은 이 서비스가 정한 "
    "보수적 기준이며 공식 기준이 아닙니다."
)

STAGE_LABELS: dict[LeaseStage, str] = {
    LeaseStage.BEFORE_CONTRACT: "계약 전",
    LeaseStage.CONTRACT_SIGNED: "계약 체결 후 잔금 전",
    LeaseStage.BALANCE_PAID: "잔금 지급·입주",
    LeaseStage.MOVED_IN: "전입신고·확정일자 이후",
    LeaseStage.LEASE_ENDING: "계약 종료 예정",
    LeaseStage.DEPOSIT_UNRETURNED: "보증금 미반환",
}

LEVEL_SENTENCES: dict[str, str] = {
    "low": "지금 확인된 범위에서는 큰 문제가 보이지 않습니다.",
    "medium": "지금 확인하고 넘어가야 할 부분이 있습니다.",
    "high": "먼저 처리해야 할 부분이 있습니다.",
}


def _build_summary(level: str, stage: LeaseStage, signal_count: int) -> str:
    """문장을 먼저 준다. 숫자와 구간 이름은 신호·비율 칸에서 따로 본다.

    등급을 겁주는 말로 옮기지 않는다. `high` 도 "먼저 처리해야 할 부분이 있다"
    까지만 말한다 — 사기 피해를 단정하는 문장은 이 서비스가 낼 수 없다.
    """
    head = f"{STAGE_LABELS[stage]} 단계입니다. {LEVEL_SENTENCES[level]}"
    if signal_count == 0:
        return f"{head} 확인이 필요한 항목은 없습니다."
    return f"{head} 확인이 필요한 항목이 {signal_count}건입니다."


def check_deposit_risk(request: DepositRiskRequest) -> DepositRiskResponse:
    completed_checks = set(request.completed_checks)

    ratio = compute_ratio(
        request.deposit_krw, request.property_price_krw, request.senior_lien_krw
    )
    protection = compute_protection(
        request.stage, completed_checks, request.move_in_reported_on
    )
    signals = detect_signals(
        request.stage,
        completed_checks,
        ratio,
        protection,
        has_price=request.property_price_krw is not None
        and request.property_price_krw > 0,
        has_lien=request.senior_lien_krw is not None,
    )
    level = determine_risk_level(signals, request.stage)
    actions = select_actions(signals, request.stage, completed_checks)
    official_sources = sources_for_actions(actions)

    return DepositRiskResponse(
        risk_level=level,
        stage=request.stage,
        summary=_build_summary(level, request.stage, len(signals)),
        ratio=DepositRatio(
            ratio_percent=(
                float(ratio.ratio_percent) if ratio.ratio_percent is not None else None
            ),
            band=ratio.band,
            formula=RATIO_FORMULA,
        ),
        protection=DepositProtection(
            opposing_power_effective_on=protection.opposing_power_effective_on,
            has_opposing_power_requirements=(
                protection.has_opposing_power_requirements
            ),
            has_priority_repayment_requirements=(
                protection.has_priority_repayment_requirements
            ),
        ),
        signals=signals,
        actions=actions,
        official_sources=official_sources,
        disclaimer=DISCLAIMER,
    )
