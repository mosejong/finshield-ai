from enum import Enum
from typing import Literal

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
    url: str | None = Field(default=None, max_length=2048)


class RiskSignal(BaseModel):
    code: str
    label: str
    weight: int


class Action(BaseModel):
    code: Literal[
        "STOP_CONTACT",
        "DO_NOT_CLICK",
        "DO_NOT_INSTALL",
        "DO_NOT_SHARE_ACCESS",
        "DO_NOT_FORWARD_MONEY",
        "VERIFY_OFFICIAL_CHANNEL",
        "CONTACT_FINANCIAL_INSTITUTION",
        "CONTACT_1394",
        "CONTACT_112",
        "CONTACT_KISA_118",
        "PRESERVE_EVIDENCE",
    ]
    priority: int = Field(ge=1, le=3)
    title: str
    reason: str
    source_ids: list[str]


class OfficialSource(BaseModel):
    source_id: str
    organization: str
    title: str
    source_url: str
    retrieved_at: str
    supports: list[str]


class AnalyzeResponse(BaseModel):
    risk_score: int = Field(ge=0, le=100)
    risk_level: Literal["low", "medium", "high"]
    signals: list[RiskSignal]
    scenario: UserState
    disclaimer: str
    fraud_types: list[
        Literal[
            "authority_impersonation",
            "loan_policy_impersonation",
            "account_access_request",
            "money_mule_transfer",
            "smishing_malware",
            "card_delivery_impersonation",
        ]
    ]
    summary: str
    actions: list[Action]
    official_sources: list[OfficialSource]
