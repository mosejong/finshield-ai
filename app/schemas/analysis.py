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


class ExplanationResponse(BaseModel):
    """설명 전용 응답.

    `AnalyzeResponse` 에 필드를 더하지 않고 별도 응답으로 둔 이유가 둘 있다.

    첫째, **지연이다.** 설명 한 문단에 약 8초가 걸린다(2026-08-19 실측,
    `docs/34` 2-1절). 판정에 붙여 놓으면 위험 수준을 보여 주기까지 그 8초를
    기다리게 된다. 지금 문자를 받은 사람에게 가장 나쁜 설계다.

    둘째, **의존 방향이다.** 판정 응답이 설명을 품으면 "설명이 없으면 판정도
    없다" 는 상태가 코드 모양으로 가능해진다. 나눠 두면 그 상태를 만들 수 없다.

    `available` 은 `explanation is None` 과 다르다. 계층이 꺼져 있는 것과, 켜져
    있는데 이번에 문장을 못 만든 것은 화면에서 다르게 보여야 한다.
    """

    available: bool
    explanation: str | None = None
    # 어느 모델이 답했는지 남긴다. 대체 모델로 넘어갔을 수 있고, 그것을 모르면
    # 이 문장이 어느 모델의 것인지 평가에서 다시 세울 수 없다.
    model: str | None = None
