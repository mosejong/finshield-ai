from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class ProductEligibility(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_text: str | None = Field(default=None, max_length=1200)
    detailed_conditions_text: str | None = Field(default=None, max_length=4000)
    age_text: str | None = Field(default=None, max_length=4000)
    income_text: str | None = Field(default=None, max_length=1200)
    annual_income_text: str | None = Field(default=None, max_length=1200)
    credit_score_text: str | None = Field(default=None, max_length=1200)
    region_text: str | None = Field(default=None, max_length=1200)


class FinancialProduct(BaseModel):
    """Normalized official product data without inferred rates or eligibility."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=100)
    source_product_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=1200)
    category: str | None = Field(default=None, max_length=400)
    category_detail: str | None = Field(default=None, max_length=3000)
    loan_limit_text: str | None = Field(default=None, max_length=1200)
    interest_rate_type: str | None = Field(default=None, max_length=1200)
    interest_rate_text: str | None = Field(default=None, max_length=1200)
    max_total_term_text: str | None = Field(default=None, max_length=1200)
    max_grace_term_text: str | None = Field(default=None, max_length=1200)
    max_repayment_term_text: str | None = Field(default=None, max_length=1200)
    repayment_method_text: str | None = Field(default=None, max_length=1200)
    purpose_text: str | None = Field(default=None, max_length=1200)
    offering_institution: str | None = Field(default=None, max_length=1200)
    handling_institution_text: str | None = Field(default=None, max_length=4000)
    application_method_text: str | None = Field(default=None, max_length=1200)
    active: bool | None = None
    eligibility: ProductEligibility
    source_base_month: str | None = Field(
        default=None,
        pattern=r"^\d{6}$",
    )
    source_file_written_at: str | None = Field(
        default=None,
        pattern=r"^\d{12}$",
    )
    fetched_at: datetime
    source_reference: HttpUrl


class ProductCatalogIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy: Literal["provider_base_month_sequence"]
    source_id_unique: Literal[True]
    unique_source_id_count: int = Field(ge=0)
    normalized_name_duplicate_groups: int = Field(ge=0)
    name_only_dedup_applied: Literal[False]


class ProductCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    page_no: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_count: int = Field(ge=0)
    source_base_month: str = Field(pattern=r"^\d{6}$")
    fetched_at: datetime
    source_reference: HttpUrl
    identity: ProductCatalogIdentity
    items: list[FinancialProduct]


ProductSourceId = Annotated[
    str,
    Field(min_length=8, max_length=100, pattern=r"^\d{6}:\d+$"),
]


class ProductComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_ids: list[ProductSourceId] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def validate_product_ids(self) -> Self:
        if len(set(self.product_ids)) != 2:
            raise ValueError("product_ids must contain two distinct IDs")
        return self


class ProductComparisonResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1)
    source_base_month: str = Field(pattern=r"^\d{6}$")
    fetched_at: datetime
    source_reference: HttpUrl
    items: list[FinancialProduct] = Field(min_length=2, max_length=2)
    disclaimer: str = Field(min_length=1)
