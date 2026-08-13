from decimal import Decimal

from app.domain.finance.profile_metrics import (
    ProfileMetricValues,
    calculate_profile_metrics,
)
from app.schemas.financial_profile import FinancialProfileResource
from app.schemas.profile_metrics import (
    ProfileMetricCalculation,
    ProfileMetricDisplay,
    ProfileMetricsResponse,
)


DISCLAIMER = (
    "이 지표는 입력한 값으로 현재 흐름을 이해하기 위한 참고 계산입니다. "
    "은행의 공식 DSR, 대출 심사, 투자 적합성 판단이 아닙니다."
)
ASSUMPTIONS = [
    "월 현금흐름은 월 순소득에서 고정지출, 생활비, 월 부채상환액을 차감합니다.",
    (
        "비상자금 기간은 유동자산을 고정지출과 생활비 합계로 나눕니다. "
        "월 부채상환액은 분모에 포함하지 않습니다."
    ),
    (
        "월소득 대비 상환액은 월 부채상환액을 월 순소득으로 나눈 "
        "서비스 참고값이며 공식 DSR이 아닙니다."
    ),
]


def build_profile_metrics(resource: FinancialProfileResource) -> ProfileMetricsResponse:
    values = calculate_profile_metrics(resource.profile)
    return ProfileMetricsResponse(
        profile_id=resource.profile_id,
        profile_updated_at=resource.updated_at,
        summary=_summary(values, resource.profile.emergency_fund_target_months),
        metrics=_display_metrics(
            values, resource.profile.emergency_fund_target_months
        ),
        calculation=ProfileMetricCalculation(
            monthly_disposable_cashflow=values.monthly_disposable_cashflow,
            monthly_debt_payment_ratio_percent=(
                values.monthly_debt_payment_ratio_percent
            ),
            emergency_fund_coverage_months=(
                values.emergency_fund_coverage_months
            ),
            essential_monthly_expenses=values.essential_monthly_expenses,
            emergency_fund_target_amount=values.emergency_fund_target_amount,
            emergency_fund_gap=values.emergency_fund_gap,
        ),
        assumptions=ASSUMPTIONS,
        disclaimer=DISCLAIMER,
    )


def _display_metrics(
    values: ProfileMetricValues,
    emergency_fund_target_months: int,
) -> list[ProfileMetricDisplay]:
    cashflow = values.monthly_disposable_cashflow
    coverage = values.emergency_fund_coverage_months
    ratio = values.monthly_debt_payment_ratio_percent

    cashflow_tone = (
        "positive" if cashflow > 0 else "caution" if cashflow < 0 else "neutral"
    )
    coverage_tone = "neutral"
    if coverage is not None and emergency_fund_target_months > 0:
        coverage_tone = "positive" if values.emergency_fund_gap == 0 else "caution"

    return [
        ProfileMetricDisplay(
            key="disposable_cashflow",
            label="매달 남는 돈",
            display=_money(cashflow),
            hint="월 순소득에서 고정지출·생활비·월 부채상환액을 빼고 남는 금액입니다.",
            tone=cashflow_tone,
            caveat="일회성 수입·지출과 아직 입력하지 않은 비용은 포함하지 않습니다.",
        ),
        ProfileMetricDisplay(
            key="debt_payment_ratio",
            label="월소득 대비 빚 상환액",
            display=f"{ratio}%" if ratio is not None else "계산 불가",
            hint="월 순소득 중 월 부채상환액이 차지하는 비율입니다.",
            tone="neutral",
            caveat=(
                "은행이 대출 심사에 쓰는 공식 DSR과 계산 방식이 다릅니다."
                if ratio is not None
                else "월 순소득이 0원이어서 비율을 계산하지 않았습니다. 공식 DSR이 아닙니다."
            ),
        ),
        ProfileMetricDisplay(
            key="emergency_fund_coverage",
            label="비상금으로 버틸 수 있는 기간",
            display=f"{coverage}개월" if coverage is not None else "계산 불가",
            hint="유동자산을 월 고정지출과 생활비 합계로 나눈 기간입니다.",
            tone=coverage_tone,
            caveat=(
                "월 부채상환액은 이 기간 계산의 분모에 포함하지 않습니다."
                if coverage is not None
                else "고정지출과 생활비 합계가 0원이어서 기간을 계산하지 않았습니다."
            ),
        ),
    ]


def _summary(values: ProfileMetricValues, target_months: int) -> str:
    cashflow = values.monthly_disposable_cashflow
    if cashflow > 0:
        cashflow_text = f"월 지출과 상환 후 {_money(cashflow)}이 남습니다."
    elif cashflow < 0:
        cashflow_text = f"월 지출과 상환이 소득보다 {_money(abs(cashflow))} 많습니다."
    else:
        cashflow_text = "월 지출과 상환 후 남는 금액이 0원입니다."

    coverage = values.emergency_fund_coverage_months
    coverage_text = (
        f"비상금은 생활비 기준 {coverage}개월치이며 입력한 목표는 {target_months}개월입니다."
        if coverage is not None
        else "생활비 합계가 0원이어서 비상금 기간은 계산하지 않았습니다."
    )

    ratio = values.monthly_debt_payment_ratio_percent
    ratio_text = (
        f"월소득 대비 상환액은 {ratio}%입니다."
        if ratio is not None
        else "월 순소득이 0원이어서 상환 비율은 계산하지 않았습니다."
    )
    return " ".join([cashflow_text, coverage_text, ratio_text])


def _money(value: Decimal) -> str:
    formatted = f"{value:,.2f}".rstrip("0").rstrip(".")
    return f"{formatted}원"
