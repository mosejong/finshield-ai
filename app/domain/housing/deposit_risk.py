"""전세보증금 위험 점검의 계산부.

여기에는 판단이 없다. 나눗셈 하나와 날짜 덧셈 하나뿐이다. 그 둘을 규칙·문구와
분리해 둔 이유는 **틀렸을 때 어디가 틀렸는지 한 곳만 보면 되게** 하려는 것이다.

LLM 이 개입할 자리는 이 파일에 없다.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP, localcontext

from app.schemas.housing import DepositCheck, LeaseStage


# 부채비율 구간 경계. **이 서비스가 정한 보수적 기준이며 공식 기준이 아니다.**
# 어떤 기관도 이 숫자를 고시하지 않았다. 응답의 `band_is_service_rule` 이
# 같은 사실을 사용자 쪽에도 남긴다.
ELEVATED_RATIO_PERCENT = Decimal("60")
HIGH_RATIO_PERCENT = Decimal("80")

RATIO_FORMULA = "(선순위 채권최고액 + 보증금) ÷ 주택가격 × 100"

RATIO_QUANTUM = Decimal("0.1")

# 잔금을 치르고 실제로 살기 시작한 뒤의 단계들.
# 주택임대차보호법 제3조 제1항의 대항요건은 "주택의 인도와 주민등록" 둘 다다.
# 전입신고만으로는 요건이 차지 않으므로 인도 여부를 단계로 확인한다.
OCCUPIED_STAGES: frozenset[LeaseStage] = frozenset(
    {
        LeaseStage.BALANCE_PAID,
        LeaseStage.MOVED_IN,
        LeaseStage.LEASE_ENDING,
        LeaseStage.DEPOSIT_UNRETURNED,
    }
)


@dataclass(frozen=True)
class RatioResult:
    ratio_percent: Decimal | None
    band: str


@dataclass(frozen=True)
class ProtectionResult:
    opposing_power_effective_on: date | None
    has_opposing_power_requirements: bool
    has_priority_repayment_requirements: bool


def compute_ratio(
    deposit_krw: int,
    property_price_krw: int | None,
    senior_lien_krw: int | None,
) -> RatioResult:
    """부채비율을 구한다. 모르는 값이 하나라도 있으면 계산하지 않는다.

    선순위 채권최고액을 모를 때 0 으로 두고 계산하면 비율이 실제보다 **낮게**
    나온다. 즉 등기부를 아직 안 본 사람에게 가장 안전해 보이는 숫자를 준다.
    정확히 반대로 가야 하므로, 모르면 `unknown` 을 돌려주고 확인을 행동으로 민다.
    """
    if property_price_krw is None or property_price_krw <= 0:
        return RatioResult(None, "unknown")
    if senior_lien_krw is None:
        return RatioResult(None, "unknown")

    with localcontext() as context:
        context.prec = 28
        ratio = (
            (Decimal(senior_lien_krw) + Decimal(deposit_krw))
            / Decimal(property_price_krw)
            * Decimal(100)
        ).quantize(RATIO_QUANTUM, rounding=ROUND_HALF_UP)

    if ratio > HIGH_RATIO_PERCENT:
        band = "high"
    elif ratio > ELEVATED_RATIO_PERCENT:
        band = "elevated"
    else:
        band = "low"
    return RatioResult(ratio, band)


def compute_protection(
    stage: LeaseStage,
    completed_checks: set[DepositCheck],
    move_in_reported_on: date | None,
) -> ProtectionResult:
    """대항력·우선변제권 요건 충족 여부.

    대항력 발생일만 날짜로 돌려준다. 주택임대차보호법 제3조 제1항이
    "주택의 인도와 주민등록을 마친 때에는 그 다음 날부터" 라고 정하고 있어
    날짜 계산이 법문에서 그대로 나온다.

    우선변제권은 참/거짓만 돌려준다. 요건(대항요건 + 확정일자)은 명확하지만
    **취득 시점**을 날짜 하나로 단정하려면 법문에 없는 해석을 얹어야 한다.
    근거 없는 날짜를 화면에 띄우는 것보다 요건 충족만 말하는 편이 정확하다.
    """
    occupied = stage in OCCUPIED_STAGES
    reported = DepositCheck.MOVE_IN_REPORTED in completed_checks
    has_opposing = occupied and reported

    effective_on: date | None = None
    if has_opposing and move_in_reported_on is not None:
        effective_on = move_in_reported_on + timedelta(days=1)

    has_priority = has_opposing and (
        DepositCheck.CONFIRMED_DATE_OBTAINED in completed_checks
    )

    return ProtectionResult(
        opposing_power_effective_on=effective_on,
        has_opposing_power_requirements=has_opposing,
        has_priority_repayment_requirements=has_priority,
    )
