"""전세보증금 위험 점검의 입출력 계약.

`analysis` 와 스키마를 합치지 않은 이유: 사기 분석은 **받은 메시지**를 보고,
이 점검은 **내 계약 상태**를 본다. 입력의 성격이 다르고, 하나로 합치면 한쪽
필드가 다른 쪽에서는 항상 비어 있는 응답이 된다.

`OfficialSource` 만 `analysis` 에서 그대로 쓴다. 출처의 모양은 도메인과 무관하고,
따로 두면 같은 뜻의 타입이 둘이 된다.
"""

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.core.clock import today_kst
from app.schemas.analysis import OfficialSource


class LeaseStage(str, Enum):
    """계약 진행 단계.

    뒤로 갈수록 되돌리기 어렵다. 잔금을 치른 뒤에는 "다른 집을 보자" 가
    선택지에서 사라진다. 단계를 입력으로 받는 이유가 이것이다 — 같은 숫자라도
    계약 전과 잔금 후에 해야 할 일이 다르다.
    """

    BEFORE_CONTRACT = "before_contract"
    CONTRACT_SIGNED = "contract_signed"
    BALANCE_PAID = "balance_paid"
    MOVED_IN = "moved_in"
    LEASE_ENDING = "lease_ending"
    DEPOSIT_UNRETURNED = "deposit_unreturned"


class DepositCheck(str, Enum):
    """사용자가 이미 마친 확인·조치.

    "안 한 것" 을 세는 데 쓴다. 하지 않은 확인은 그 자체가 위험 신호다.
    """

    REGISTRY_CHECKED = "registry_checked"
    OWNER_IDENTITY_VERIFIED = "owner_identity_verified"
    TAX_ARREARS_CHECKED = "tax_arrears_checked"
    MOVE_IN_REPORTED = "move_in_reported"
    CONFIRMED_DATE_OBTAINED = "confirmed_date_obtained"
    DEPOSIT_GUARANTEE_JOINED = "deposit_guarantee_joined"


# 1000조 원. 정상 입력의 상한이 아니라 오타·오버플로 방어선이다.
MAX_KRW = 1_000_000_000_000_000


class DepositRiskRequest(BaseModel):
    stage: LeaseStage
    deposit_krw: int = Field(ge=0, le=MAX_KRW)
    # 시세·공시가격 등 사용자가 확인한 주택 가격. 모르면 비운다.
    # 0 을 "모른다" 로 쓰지 않는다 — 0 원짜리 주택과 모르는 것은 다르다.
    property_price_krw: int | None = Field(default=None, ge=0, le=MAX_KRW)
    # 등기부 을구의 근저당권 채권최고액 합계. 확인 전이면 비운다.
    senior_lien_krw: int | None = Field(default=None, ge=0, le=MAX_KRW)
    completed_checks: list[DepositCheck] = Field(default_factory=list, max_length=16)
    # 전입신고를 마친 날. 대항력 발생일 계산에만 쓴다.
    move_in_reported_on: date | None = None

    @model_validator(mode="after")
    def _reject_future_move_in_date(self) -> "DepositRiskRequest":
        if self.move_in_reported_on and self.move_in_reported_on > today_kst():
            raise ValueError("move_in_reported_on must not be in the future")
        return self


class DepositRiskSignal(BaseModel):
    code: str
    label: str
    # 왜 이 신호가 떴는지. 사용자가 자기 입력과 대조할 수 있어야 한다.
    detail: str


class DepositProtection(BaseModel):
    """보호 장치의 현재 상태.

    날짜를 돌려주는 것은 **대항력**뿐이다. 주택임대차보호법 제3조 제1항이
    "그 다음 날부터" 라고 정하고 있어 날짜 계산이 법문에서 바로 나온다.

    우선변제권은 요건 충족 여부만 참/거짓으로 돌려준다. 취득 시점을 날짜로
    단정하려면 법문에 없는 해석을 얹어야 하고, 그건 이 서비스가 할 일이 아니다.
    """

    opposing_power_effective_on: date | None = None
    has_opposing_power_requirements: bool
    has_priority_repayment_requirements: bool


class DepositRatio(BaseModel):
    """(선순위 채권최고액 + 보증금) / 주택가격.

    구간 이름은 **이 서비스의 보수적 기준**이며 공식 기준이 아니다.
    `band_is_service_rule` 이 그것을 응답 안에 박아 둔다 — 화면이 캡처되어
    돌아다녀도 이 사실이 같이 따라가야 한다.
    """

    ratio_percent: float | None = None
    band: Literal["unknown", "low", "elevated", "high"]
    band_is_service_rule: Literal[True] = True
    formula: str


class DepositRiskAction(BaseModel):
    code: Literal[
        "CHECK_REGISTRY",
        "VERIFY_OWNER_IDENTITY",
        "CHECK_TAX_ARREARS",
        "REPORT_MOVE_IN",
        "GET_CONFIRMED_DATE",
        "JOIN_DEPOSIT_GUARANTEE",
        "KEEP_OPPOSING_POWER",
        "APPLY_LEASE_REGISTRATION_ORDER",
        "CHECK_VICTIM_SUPPORT",
    ]
    priority: int = Field(ge=1, le=3)
    title: str
    reason: str
    source_ids: list[str]


class DepositRiskResponse(BaseModel):
    risk_level: Literal["low", "medium", "high"]
    stage: LeaseStage
    summary: str
    ratio: DepositRatio
    protection: DepositProtection
    signals: list[DepositRiskSignal]
    actions: list[DepositRiskAction]
    official_sources: list[OfficialSource]
    disclaimer: str
