from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, localcontext
from enum import Enum


MONEY_QUANTUM = Decimal("0.01")
MAX_MONTHS = 600
MAX_ANNUAL_INTEREST_RATE = Decimal("100")

SIMULATION_ASSUMPTIONS: tuple[str, ...] = (
    "annual_interest_rate is a nominal annual percentage divided by 12",
    "schedule amounts are rounded to 0.01 using ROUND_HALF_UP",
    "the final installment is adjusted to clear the remaining principal",
    "fees, taxes, insurance, and early-repayment charges are excluded",
    "all monetary values use the same currency unit as principal",
)


class RepaymentType(str, Enum):
    EQUAL_PRINCIPAL_AND_INTEREST = "equal_principal_and_interest"
    EQUAL_PRINCIPAL = "equal_principal"


@dataclass(frozen=True)
class PaymentScheduleEntry:
    month: int
    principal_payment: Decimal
    interest_payment: Decimal
    payment: Decimal
    remaining_principal: Decimal


@dataclass(frozen=True)
class LoanSimulation:
    principal: Decimal
    annual_interest_rate: Decimal
    months: int
    repayment_type: RepaymentType
    monthly_payment: Decimal | None
    schedule: tuple[PaymentScheduleEntry, ...]
    total_repayment: Decimal
    total_interest: Decimal
    assumptions: tuple[str, ...]


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _validate_inputs(
    principal: Decimal,
    annual_interest_rate: Decimal,
    months: int,
) -> None:
    if principal <= 0:
        raise ValueError("principal must be greater than zero")
    if annual_interest_rate < 0 or annual_interest_rate > MAX_ANNUAL_INTEREST_RATE:
        raise ValueError("annual_interest_rate must be between 0 and 100")
    if months < 1 or months > MAX_MONTHS:
        raise ValueError("months must be between 1 and 600")


def _equal_principal_and_interest_schedule(
    principal: Decimal,
    monthly_rate: Decimal,
    months: int,
) -> tuple[Decimal, tuple[PaymentScheduleEntry, ...]]:
    if monthly_rate == 0:
        scheduled_payment = _money(principal / Decimal(months))
    else:
        growth = (Decimal("1") + monthly_rate) ** months
        scheduled_payment = _money(
            principal * monthly_rate * growth / (growth - Decimal("1"))
        )

    balance = principal
    entries: list[PaymentScheduleEntry] = []
    for month in range(1, months + 1):
        interest_payment = _money(balance * monthly_rate)
        if month == months:
            principal_payment = balance
        else:
            principal_payment = min(scheduled_payment - interest_payment, balance)
        principal_payment = _money(principal_payment)
        balance = _money(balance - principal_payment)
        payment = _money(principal_payment + interest_payment)
        entries.append(
            PaymentScheduleEntry(
                month=month,
                principal_payment=principal_payment,
                interest_payment=interest_payment,
                payment=payment,
                remaining_principal=balance,
            )
        )

    return scheduled_payment, tuple(entries)


def _equal_principal_schedule(
    principal: Decimal,
    monthly_rate: Decimal,
    months: int,
) -> tuple[PaymentScheduleEntry, ...]:
    regular_principal_payment = _money(principal / Decimal(months))
    balance = principal
    entries: list[PaymentScheduleEntry] = []

    for month in range(1, months + 1):
        interest_payment = _money(balance * monthly_rate)
        principal_payment = (
            balance if month == months else min(regular_principal_payment, balance)
        )
        principal_payment = _money(principal_payment)
        balance = _money(balance - principal_payment)
        payment = _money(principal_payment + interest_payment)
        entries.append(
            PaymentScheduleEntry(
                month=month,
                principal_payment=principal_payment,
                interest_payment=interest_payment,
                payment=payment,
                remaining_principal=balance,
            )
        )

    return tuple(entries)


def simulate_loan(
    principal: Decimal,
    annual_interest_rate: Decimal,
    months: int,
    repayment_type: RepaymentType,
) -> LoanSimulation:
    """Build a deterministic amortization schedule without any LLM involvement."""

    if not principal.is_finite() or not annual_interest_rate.is_finite():
        raise ValueError("principal and annual_interest_rate must be finite")

    principal = _money(principal)
    _validate_inputs(principal, annual_interest_rate, months)

    with localcontext() as context:
        context.prec = 40
        monthly_rate = annual_interest_rate / Decimal("100") / Decimal("12")

        if repayment_type == RepaymentType.EQUAL_PRINCIPAL_AND_INTEREST:
            monthly_payment, schedule = _equal_principal_and_interest_schedule(
                principal, monthly_rate, months
            )
        elif repayment_type == RepaymentType.EQUAL_PRINCIPAL:
            monthly_payment = None
            schedule = _equal_principal_schedule(principal, monthly_rate, months)
        else:
            raise ValueError("unsupported repayment_type")

    total_repayment = _money(sum((entry.payment for entry in schedule), Decimal("0")))
    total_interest = _money(
        sum((entry.interest_payment for entry in schedule), Decimal("0"))
    )

    return LoanSimulation(
        principal=principal,
        annual_interest_rate=annual_interest_rate,
        months=months,
        repayment_type=repayment_type,
        monthly_payment=monthly_payment,
        schedule=schedule,
        total_repayment=total_repayment,
        total_interest=total_interest,
        assumptions=SIMULATION_ASSUMPTIONS,
    )
