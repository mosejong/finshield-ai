from copy import deepcopy
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.financial_profile import FinancialProfile


def valid_profile_data():
    return {
        "age_band": "20_29",
        "employment_status": "employed",
        "household_size": 2,
        "dependents_count": 1,
        "monthly_net_income": "3500000.00",
        "monthly_fixed_expenses": "1200000.00",
        "monthly_variable_expenses": "600000.00",
        "liquid_assets": "10000000.00",
        "emergency_fund_target_months": 6,
        "total_debt": "5000000.00",
        "monthly_debt_payment": "250000.00",
        "loan_items": [
            {
                "category": "credit_loan",
                "balance": "5000000.00",
                "annual_rate": "5.2500",
                "remaining_months": 24,
                "repayment_type": "equal_principal_and_interest",
            }
        ],
        "credit_score_band": "good",
        "business_owner": False,
        "goal": "debt_refinance",
    }


def test_financial_profile_accepts_mvp_fields() -> None:
    profile = FinancialProfile.model_validate(valid_profile_data())

    assert profile.monthly_net_income == Decimal("3500000.00")
    assert profile.loan_items[0].annual_rate == Decimal("5.2500")
    assert profile.marital_status is None
    assert profile.region is None


def test_financial_profile_accepts_zero_debt_boundary() -> None:
    data = valid_profile_data()
    data.update(
        {
            "household_size": 1,
            "dependents_count": 0,
            "monthly_net_income": "0.00",
            "total_debt": "0.00",
            "monthly_debt_payment": "0.00",
            "loan_items": [],
            "emergency_fund_target_months": 0,
        }
    )

    profile = FinancialProfile.model_validate(data)
    assert profile.total_debt == Decimal("0.00")


@pytest.mark.parametrize(
    "field_name",
    [
        "resident_registration_number",
        "account_password",
        "otp",
        "full_card_number",
        "internet_banking_credentials",
        "gender",
    ],
)
def test_financial_profile_rejects_sensitive_or_unapproved_fields(
    field_name: str,
) -> None:
    data = valid_profile_data()
    data[field_name] = "must-not-be-stored"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        FinancialProfile.model_validate(data)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("monthly_net_income", "-0.01"),
        ("monthly_fixed_expenses", "-0.01"),
        ("liquid_assets", "-0.01"),
        ("total_debt", "-0.01"),
        ("household_size", 0),
        ("emergency_fund_target_months", 61),
    ],
)
def test_financial_profile_rejects_out_of_range_values(
    field_name: str, invalid_value: object
) -> None:
    data = valid_profile_data()
    data[field_name] = invalid_value

    with pytest.raises(ValidationError):
        FinancialProfile.model_validate(data)


def test_financial_profile_rejects_inconsistent_dependents() -> None:
    data = valid_profile_data()
    data["household_size"] = 2
    data["dependents_count"] = 2

    with pytest.raises(ValidationError, match="dependents_count"):
        FinancialProfile.model_validate(data)


def test_financial_profile_rejects_loan_balance_above_total_debt() -> None:
    data = valid_profile_data()
    data["total_debt"] = "4999999.99"

    with pytest.raises(ValidationError, match="cannot exceed total_debt"):
        FinancialProfile.model_validate(data)


def test_financial_profile_rejects_business_details_for_non_owner() -> None:
    data = deepcopy(valid_profile_data())
    data["business_age_months"] = 12

    with pytest.raises(ValidationError, match="business_owner=true"):
        FinancialProfile.model_validate(data)
