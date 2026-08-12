from decimal import Decimal

import pytest

from app.domain.finance.loan_calculator import RepaymentType, simulate_loan


def test_equal_principal_and_interest_normal_rate() -> None:
    result = simulate_loan(
        principal=Decimal("100000.00"),
        annual_interest_rate=Decimal("5.0000"),
        months=12,
        repayment_type=RepaymentType.EQUAL_PRINCIPAL_AND_INTEREST,
    )

    assert result.monthly_payment == Decimal("8560.75")
    assert result.total_repayment == Decimal("102728.98")
    assert result.total_interest == Decimal("2728.98")
    assert len(result.schedule) == 12
    assert result.schedule[-1].remaining_principal == Decimal("0.00")


@pytest.mark.parametrize(
    ("repayment_type", "expected_monthly_payment"),
    [
        (RepaymentType.EQUAL_PRINCIPAL_AND_INTEREST, Decimal("100.00")),
        (RepaymentType.EQUAL_PRINCIPAL, None),
    ],
)
def test_zero_percent_interest(
    repayment_type: RepaymentType, expected_monthly_payment
) -> None:
    result = simulate_loan(
        principal=Decimal("1200.00"),
        annual_interest_rate=Decimal("0"),
        months=12,
        repayment_type=repayment_type,
    )

    assert result.monthly_payment == expected_monthly_payment
    assert result.total_repayment == Decimal("1200.00")
    assert result.total_interest == Decimal("0.00")
    assert all(item.interest_payment == 0 for item in result.schedule)


@pytest.mark.parametrize("months", [1, 600])
def test_short_and_long_terms(months: int) -> None:
    result = simulate_loan(
        principal=Decimal("300000.00"),
        annual_interest_rate=Decimal("3.2500"),
        months=months,
        repayment_type=RepaymentType.EQUAL_PRINCIPAL_AND_INTEREST,
    )

    assert len(result.schedule) == months
    assert result.schedule[-1].remaining_principal == Decimal("0.00")


@pytest.mark.parametrize(
    ("principal", "rate", "months"),
    [
        (Decimal("-1"), Decimal("5"), 12),
        (Decimal("1000"), Decimal("-0.01"), 12),
        (Decimal("1000"), Decimal("5"), 0),
        (Decimal("1000"), Decimal("5"), 601),
    ],
)
def test_invalid_inputs_raise_value_error(
    principal: Decimal, rate: Decimal, months: int
) -> None:
    with pytest.raises(ValueError):
        simulate_loan(
            principal=principal,
            annual_interest_rate=rate,
            months=months,
            repayment_type=RepaymentType.EQUAL_PRINCIPAL_AND_INTEREST,
        )


def test_equal_principal_reduces_interest_faster_than_annuity() -> None:
    annuity = simulate_loan(
        Decimal("100000.00"),
        Decimal("5"),
        12,
        RepaymentType.EQUAL_PRINCIPAL_AND_INTEREST,
    )
    equal_principal = simulate_loan(
        Decimal("100000.00"),
        Decimal("5"),
        12,
        RepaymentType.EQUAL_PRINCIPAL,
    )

    assert equal_principal.total_interest < annuity.total_interest
    assert equal_principal.schedule[0].payment > annuity.schedule[0].payment
    assert equal_principal.schedule[-1].payment < annuity.schedule[-1].payment


def test_rounding_edge_case_reconciles_schedule_totals() -> None:
    result = simulate_loan(
        Decimal("1000.01"),
        Decimal("4.3750"),
        7,
        RepaymentType.EQUAL_PRINCIPAL_AND_INTEREST,
    )

    principal_total = sum(
        (item.principal_payment for item in result.schedule), Decimal("0")
    )
    payment_total = sum((item.payment for item in result.schedule), Decimal("0"))
    assert principal_total == Decimal("1000.01")
    assert payment_total == result.total_repayment
    assert result.total_repayment == result.principal + result.total_interest
    assert result.schedule[-1].remaining_principal == Decimal("0.00")
    assert all(
        value == value.quantize(Decimal("0.01"))
        for item in result.schedule
        for value in (
            item.principal_payment,
            item.interest_payment,
            item.payment,
            item.remaining_principal,
        )
    )


def test_small_principal_is_cleared_without_residual() -> None:
    result = simulate_loan(
        Decimal("0.01"),
        Decimal("0"),
        2,
        RepaymentType.EQUAL_PRINCIPAL_AND_INTEREST,
    )

    assert result.monthly_payment == Decimal("0.01")
    assert [item.payment for item in result.schedule] == [
        Decimal("0.01"),
        Decimal("0.00"),
    ]
    assert result.total_repayment == Decimal("0.01")
    assert result.schedule[-1].remaining_principal == Decimal("0.00")


def test_sub_cent_principal_is_rejected_by_domain() -> None:
    with pytest.raises(ValueError, match="principal"):
        simulate_loan(
            Decimal("0.001"),
            Decimal("0"),
            1,
            RepaymentType.EQUAL_PRINCIPAL,
        )


@pytest.mark.parametrize("non_finite", [Decimal("NaN"), Decimal("Infinity")])
def test_non_finite_inputs_are_rejected_by_domain(non_finite: Decimal) -> None:
    with pytest.raises(ValueError, match="finite"):
        simulate_loan(
            non_finite,
            Decimal("5"),
            12,
            RepaymentType.EQUAL_PRINCIPAL,
        )
