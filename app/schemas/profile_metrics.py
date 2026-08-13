from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


ProfileMetricKey = Literal[
    "disposable_cashflow",
    "debt_payment_ratio",
    "emergency_fund_coverage",
]
ProfileMetricTone = Literal["positive", "neutral", "caution"]


class ProfileMetricDisplay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: ProfileMetricKey
    label: str = Field(min_length=1)
    display: str = Field(min_length=1)
    hint: str = Field(min_length=1)
    tone: ProfileMetricTone
    caveat: str | None = None


class ProfileMetricCalculation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    monthly_disposable_cashflow: Decimal = Field(decimal_places=2)
    monthly_debt_payment_ratio_percent: Decimal | None = Field(
        default=None, ge=0, decimal_places=1
    )
    emergency_fund_coverage_months: Decimal | None = Field(
        default=None, ge=0, decimal_places=1
    )
    essential_monthly_expenses: Decimal = Field(ge=0, decimal_places=2)
    emergency_fund_target_amount: Decimal = Field(ge=0, decimal_places=2)
    emergency_fund_gap: Decimal = Field(ge=0, decimal_places=2)


class ProfileMetricsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["0.1"] = "0.1"
    profile_id: UUID
    profile_updated_at: datetime
    summary: str = Field(min_length=1)
    metrics: list[ProfileMetricDisplay] = Field(min_length=3, max_length=3)
    calculation: ProfileMetricCalculation
    assumptions: list[str] = Field(min_length=3)
    disclaimer: str = Field(min_length=1)
