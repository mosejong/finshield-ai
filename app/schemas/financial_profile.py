from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AgeBand(str, Enum):
    UNDER_20 = "under_20"
    AGE_20_29 = "20_29"
    AGE_30_39 = "30_39"
    AGE_40_49 = "40_49"
    AGE_50_59 = "50_59"
    AGE_60_PLUS = "60_plus"


class EmploymentStatus(str, Enum):
    EMPLOYED = "employed"
    SELF_EMPLOYED = "self_employed"
    UNEMPLOYED = "unemployed"
    STUDENT = "student"
    RETIRED = "retired"
    OTHER = "other"


class MaritalStatus(str, Enum):
    SINGLE = "single"
    MARRIED = "married"
    OTHER = "other"
    PREFER_NOT_TO_SAY = "prefer_not_to_say"


class DebtCategory(str, Enum):
    MORTGAGE = "mortgage"
    RENT_DEPOSIT = "rent_deposit"
    CREDIT_LOAN = "credit_loan"
    SECURED_LOAN = "secured_loan"
    STUDENT_LOAN = "student_loan"
    AUTO_LOAN = "auto_loan"
    BUSINESS_LOAN = "business_loan"
    CARD_LOAN = "card_loan"
    OTHER = "other"


class ProfileRepaymentType(str, Enum):
    EQUAL_PRINCIPAL_AND_INTEREST = "equal_principal_and_interest"
    EQUAL_PRINCIPAL = "equal_principal"
    INTEREST_ONLY = "interest_only"
    BULLET = "bullet"
    OTHER = "other"


class CreditScoreBand(str, Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    UNKNOWN = "unknown"


class BusinessRevenueBand(str, Enum):
    UNDER_30M = "under_30m"
    FROM_30M_TO_100M = "30m_100m"
    FROM_100M_TO_500M = "100m_500m"
    OVER_500M = "over_500m"
    UNKNOWN = "unknown"


class FinancialGoal(str, Enum):
    HOUSING = "housing"
    EMERGENCY_CASH = "emergency_cash"
    DEBT_REFINANCE = "debt_refinance"
    LIVING_EXPENSE = "living_expense"
    STARTUP_BUSINESS = "startup_business"
    VEHICLE = "vehicle"
    ASSET_BUILDING = "asset_building"
    OTHER = "other"


class LoanItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: DebtCategory
    balance: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    annual_rate: Decimal = Field(ge=0, le=100, max_digits=7, decimal_places=4)
    remaining_months: int = Field(ge=1, le=600)
    repayment_type: ProfileRepaymentType


class FinancialProfile(BaseModel):
    """Minimum financial profile for deterministic filtering and calculations.

    Exact identity, account, authentication, and full-card data are intentionally
    excluded. Unknown fields are rejected so sensitive data is not silently kept.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    age_band: AgeBand
    employment_status: EmploymentStatus
    household_size: int = Field(ge=1, le=20)
    dependents_count: int = Field(default=0, ge=0, le=19)
    marital_status: MaritalStatus | None = None
    region: str | None = Field(default=None, min_length=1, max_length=50)

    monthly_net_income: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    monthly_fixed_expenses: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    monthly_variable_expenses: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    liquid_assets: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    emergency_fund_target_months: int = Field(ge=0, le=60)

    total_debt: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    monthly_debt_payment: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    loan_items: list[LoanItem] = Field(default_factory=list, max_length=100)

    credit_score_band: CreditScoreBand = CreditScoreBand.UNKNOWN
    business_owner: bool = False
    business_age_months: int | None = Field(default=None, ge=0, le=1200)
    annual_business_revenue_band: BusinessRevenueBand | None = None

    goal: FinancialGoal

    @model_validator(mode="after")
    def validate_profile_consistency(self) -> "FinancialProfile":
        if self.dependents_count >= self.household_size:
            raise ValueError("dependents_count must be smaller than household_size")

        detailed_debt = sum((item.balance for item in self.loan_items), Decimal("0"))
        if detailed_debt > self.total_debt:
            raise ValueError("loan item balances cannot exceed total_debt")

        if self.total_debt == 0 and self.monthly_debt_payment != 0:
            raise ValueError("monthly_debt_payment must be zero when total_debt is zero")

        has_business_detail = (
            self.business_age_months is not None
            or self.annual_business_revenue_band is not None
        )
        if has_business_detail and not self.business_owner:
            raise ValueError("business details require business_owner=true")

        return self


class FinancialProfileResource(BaseModel):
    """Server-managed wrapper around the validated minimum profile."""

    model_config = ConfigDict(extra="forbid")

    profile_id: UUID
    profile: FinancialProfile
    created_at: datetime
    updated_at: datetime
