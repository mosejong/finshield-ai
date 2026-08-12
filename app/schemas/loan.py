from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.finance.loan_calculator import RepaymentType


class LoanSimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    principal: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    annual_interest_rate: Decimal = Field(
        ge=0, le=100, max_digits=7, decimal_places=4
    )
    months: int = Field(ge=1, le=600)
    repayment_type: RepaymentType


class PaymentScheduleItem(BaseModel):
    month: int = Field(ge=1)
    principal_payment: Decimal = Field(ge=0, decimal_places=2)
    interest_payment: Decimal = Field(ge=0, decimal_places=2)
    payment: Decimal = Field(ge=0, decimal_places=2)
    remaining_principal: Decimal = Field(ge=0, decimal_places=2)


class LoanSimulationResponse(BaseModel):
    principal: Decimal = Field(gt=0, decimal_places=2)
    annual_interest_rate: Decimal = Field(ge=0, le=100)
    months: int = Field(ge=1, le=600)
    repayment_type: RepaymentType
    monthly_payment: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    schedule: list[PaymentScheduleItem]
    total_repayment: Decimal = Field(gt=0, decimal_places=2)
    total_interest: Decimal = Field(ge=0, decimal_places=2)
    assumptions: list[str]
