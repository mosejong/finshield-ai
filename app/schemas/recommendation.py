from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.financial_profile import FinancialProfile
from app.schemas.product import FinancialProduct


MatchStatus = Literal["potential_match", "mismatch", "needs_review"]


class ProductRecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: FinancialProfile


class ProductMatchReason(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule: Literal["goal_purpose", "eligibility_manual_review"]
    status: MatchStatus
    message: str = Field(min_length=1, max_length=500)
    source_field: Literal["purpose_text", "eligibility"]


class ProductMatchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: MatchStatus
    product: FinancialProduct
    reasons: list[ProductMatchReason] = Field(min_length=1)


class ProductRecommendationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    potential_match: int = Field(ge=0)
    mismatch: int = Field(ge=0)
    needs_review: int = Field(ge=0)


class ProductRecommendationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    source_base_month: str = Field(pattern=r"^\d{6}$")
    total_count: int = Field(ge=0)
    page_no: int = Field(ge=1)
    page_size: int = Field(ge=1)
    summary: ProductRecommendationSummary
    disclaimer: str
    results: list[ProductMatchResult]
