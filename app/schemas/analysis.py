from enum import Enum

from pydantic import BaseModel, Field


class Persona(str, Enum):
    EARLY_CAREER = "early_career"
    SMALL_BUSINESS = "small_business"
    UNKNOWN = "unknown"


class UserState(str, Enum):
    RECEIVED_ONLY = "received_only"
    CLICKED_LINK = "clicked_link"
    SHARED_PERSONAL_INFO = "shared_personal_info"
    SHARED_ACCOUNT_ACCESS = "shared_account_access"
    INSTALLED_APP = "installed_app"
    RECEIVED_UNKNOWN_MONEY = "received_unknown_money"
    TRANSFERRED_MONEY = "transferred_money"


class AnalyzeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10000)
    persona: Persona = Persona.UNKNOWN
    state: UserState = UserState.RECEIVED_ONLY
    url: str | None = None


class RiskSignal(BaseModel):
    code: str
    label: str
    weight: int


class AnalyzeResponse(BaseModel):
    risk_score: int = Field(ge=0, le=100)
    risk_level: str
    signals: list[RiskSignal]
    scenario: UserState
    disclaimer: str
