from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.schemas.financial_profile import FinancialProfile


ONE_DECIMAL = Decimal("0.1")


@dataclass(frozen=True)
class ProfileMetricValues:
    monthly_disposable_cashflow: Decimal
    monthly_debt_payment_ratio_percent: Decimal | None
    emergency_fund_coverage_months: Decimal | None
    essential_monthly_expenses: Decimal
    emergency_fund_target_amount: Decimal
    emergency_fund_gap: Decimal


def calculate_profile_metrics(profile: FinancialProfile) -> ProfileMetricValues:
    essential_monthly_expenses = (
        profile.monthly_fixed_expenses + profile.monthly_variable_expenses
    )
    monthly_disposable_cashflow = (
        profile.monthly_net_income
        - essential_monthly_expenses
        - profile.monthly_debt_payment
    )

    debt_payment_ratio = None
    if profile.monthly_net_income > 0:
        debt_payment_ratio = (
            profile.monthly_debt_payment
            / profile.monthly_net_income
            * Decimal("100")
        ).quantize(ONE_DECIMAL, rounding=ROUND_HALF_UP)

    emergency_fund_coverage = None
    if essential_monthly_expenses > 0:
        emergency_fund_coverage = (
            profile.liquid_assets / essential_monthly_expenses
        ).quantize(ONE_DECIMAL, rounding=ROUND_HALF_UP)

    target_amount = essential_monthly_expenses * Decimal(
        profile.emergency_fund_target_months
    )
    emergency_fund_gap = max(target_amount - profile.liquid_assets, Decimal("0"))

    return ProfileMetricValues(
        monthly_disposable_cashflow=monthly_disposable_cashflow,
        monthly_debt_payment_ratio_percent=debt_payment_ratio,
        emergency_fund_coverage_months=emergency_fund_coverage,
        essential_monthly_expenses=essential_monthly_expenses,
        emergency_fund_target_amount=target_amount,
        emergency_fund_gap=emergency_fund_gap,
    )
