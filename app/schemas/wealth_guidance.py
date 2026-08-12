from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


WealthModuleCode = Literal[
    "money_flow",
    "saving_plan",
    "debt_credit",
    "investment_risk",
]


class WealthGuidanceSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    organization: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_url: str = Field(pattern=r"^https://")
    retrieved_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    supports: list[WealthModuleCode] = Field(min_length=1)


class WealthGuidanceModule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: WealthModuleCode
    order: int = Field(ge=1, le=4)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    check_questions: list[str] = Field(min_length=1)
    next_action: str = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)


class WealthGuidanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["0.1"]
    scope_disclaimer: str = Field(min_length=1)
    modules: list[WealthGuidanceModule] = Field(min_length=1)
    official_sources: list[WealthGuidanceSource] = Field(min_length=1)
