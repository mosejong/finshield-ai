import json
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from app.domain.fraud.signals import CANONICAL_TO_LEGACY_PUBLIC, SIGNAL_RULES
from app.schemas.analysis import AnalyzeRequest, Persona, UserState


GOLDEN_SET_PATH = Path(__file__).with_name("data") / "fraud_golden_v0.1.jsonl"

# 개발셋과 **파일이 다르다.** 같은 파일에 플래그만 달면 한 번의 실수로 held-out
# 사례가 규칙 수정에 쓰인다. 경계는 코드가 아니라 파일이 지킨다.
#
# held-out 은 버전마다 다른 파일이고, **기본값을 두지 않는다.** "held-out 셋"
# 이라는 이름으로 부를 수 있게 두면 어떤 버전을 쟀는지 기록에 남지 않는다.
# v0.2 는 규칙 수정에 쓰여 소진되었다. v0.3 은 그 수정 이후의 재측정용이고
# 요구 조건 수정을 재면서 함께 소진되었다. v0.4 는 투자·지인 사칭 유형이
# 구현되기 **전에** 얼린 셋이고, 그 유형을 재면서 소진되었다. v0.5 는 v0.4 가
# 찾아낸 여덟 건의 결함을 **고치기 전에** 얼린 셋이다 - 그 결함을 하나라도 먼저
# 고쳤다면 v0.4 는 성능이 아니라 기억을 재는 자가 된다.
HOLDOUT_V0_2_PATH = Path(__file__).with_name("data") / "fraud_holdout_v0.2.jsonl"
HOLDOUT_V0_3_PATH = Path(__file__).with_name("data") / "fraud_holdout_v0.3.jsonl"
HOLDOUT_V0_4_PATH = Path(__file__).with_name("data") / "fraud_holdout_v0.4.jsonl"
HOLDOUT_V0_5_PATH = Path(__file__).with_name("data") / "fraud_holdout_v0.5.jsonl"
RISK_RANK = {"low": 0, "medium": 1, "high": 2}
FRAUD_TYPE_CODES = {
    "authority_impersonation",
    "acquaintance_impersonation",
    "loan_policy_impersonation",
    "investment_scheme",
    "advance_fee_demand",
    "account_access_request",
    "money_mule_transfer",
    "smishing_malware",
    "card_delivery_impersonation",
}
# 사례가 요구하는 신호 코드는 **응답에 실제로 실리는 이름**이어야 한다.
#
# 내부 규칙 이름과 공개 이름이 다르다. `project_public_signals` 가
# `account_access_request` 를 `account_access` 로 바꿔 내보내기 때문에, 내부
# 이름을 요구 조건에 적으면 그 조건은 **어떤 엔진으로도 만족될 수 없다.**
# v0.4 의 11건과 v0.5 의 24건이 그렇게 적혀 있었고, 그동안
# `required_signal_coverage` 는 탐지 성능이 아니라 이름 불일치를 재고 있었다.
# 목록을 손으로 적지 않고 도메인에서 끌어오는 이유가 이것이다 - 손으로 적으면
# 같은 어긋남이 다시 조용히 생긴다.
SIGNAL_CODES = {
    CANONICAL_TO_LEGACY_PUBLIC.get(rule.code, rule.code) for rule in SIGNAL_RULES
} | {"suspicious_link"}
ACTION_CODES = {
    "STOP_CONTACT",
    "DO_NOT_CLICK",
    "DO_NOT_INSTALL",
    "DO_NOT_SHARE_ACCESS",
    "DO_NOT_FORWARD_MONEY",
    "VERIFY_OFFICIAL_CHANNEL",
    "VERIFY_BY_KNOWN_CONTACT",
    "CONTACT_FINANCIAL_INSTITUTION",
    "CONTACT_1394",
    "CONTACT_112",
    "CONTACT_KISA_118",
    "PRESERVE_EVIDENCE",
}


class FraudGoldenCase(BaseModel):
    case_id: str = Field(pattern=r"^(?:fg|fh)-[0-9]{3}$")
    text: str = Field(min_length=1, max_length=10_000)
    persona: Persona
    state: UserState
    url: str | None = Field(default=None, max_length=2048)
    is_fraud: bool
    expected_fraud_types: list[str]
    required_signal_codes: list[str] = Field(default_factory=list)
    expected_min_risk: str = Field(pattern=r"^(low|medium|high)$")
    required_action_codes: list[str] = Field(default_factory=list)
    synthetic: bool = True
    held_out: bool = False
    annotation_note: str

    @model_validator(mode="after")
    def validate_labels(self) -> "FraudGoldenCase":
        if self.is_fraud != bool(self.expected_fraud_types):
            raise ValueError("is_fraud must match whether expected_fraud_types is non-empty")
        if not self.synthetic:
            raise ValueError("v0.1 accepts only locally authored synthetic cases")
        unknown_types = set(self.expected_fraud_types) - FRAUD_TYPE_CODES
        if unknown_types:
            raise ValueError(f"unknown fraud type labels: {sorted(unknown_types)}")
        unknown_actions = set(self.required_action_codes) - ACTION_CODES
        if unknown_actions:
            raise ValueError(f"unknown action labels: {sorted(unknown_actions)}")
        unemittable = set(self.required_signal_codes) - SIGNAL_CODES
        if unemittable:
            raise ValueError(
                "required_signal_codes must name codes the response can carry; "
                f"unemittable: {sorted(unemittable)}"
            )
        if len(self.expected_fraud_types) != len(set(self.expected_fraud_types)):
            raise ValueError("expected_fraud_types must not contain duplicates")
        if len(self.required_signal_codes) != len(set(self.required_signal_codes)):
            raise ValueError("required_signal_codes must not contain duplicates")
        if len(self.required_action_codes) != len(set(self.required_action_codes)):
            raise ValueError("required_action_codes must not contain duplicates")
        return self

    def request(self) -> AnalyzeRequest:
        return AnalyzeRequest(
            text=self.text,
            persona=self.persona,
            state=self.state,
            url=self.url,
        )


def load_golden_cases(path: Path = GOLDEN_SET_PATH) -> list[FraudGoldenCase]:
    cases = [
        FraudGoldenCase.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    _validate_collection(cases)
    return cases


def load_holdout_cases(path: Path) -> list[FraudGoldenCase]:
    """어느 버전인지 반드시 호출부가 말하게 한다. 기본값은 없다."""
    return load_golden_cases(path)


def is_held_out(cases: Iterable[FraudGoldenCase]) -> bool:
    """섞인 셋은 없다. `_validate_collection` 이 이미 거부했다."""
    return any(case.held_out for case in cases)


def _validate_collection(cases: Iterable[FraudGoldenCase]) -> None:
    materialized = list(cases)
    case_ids = [case.case_id for case in materialized]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("golden case IDs must be unique")
    flags = {case.held_out for case in materialized}
    if len(flags) > 1:
        raise ValueError("a dataset must be entirely held-out or entirely not")
    # 접두사와 플래그가 어긋나면 파일 하나가 두 정체성을 갖는다. 그 상태에서
    # `fh-` 사례를 개발셋에 붙여 넣으면 아무도 눈치채지 못한다.
    mislabeled = [
        case.case_id
        for case in materialized
        if case.held_out != case.case_id.startswith("fh-")
    ]
    if mislabeled:
        raise ValueError(f"case ID prefix must match held_out: {sorted(mislabeled)}")
    covered_states = {case.state for case in materialized}
    if covered_states != set(UserState):
        missing = sorted(state.value for state in set(UserState) - covered_states)
        raise ValueError(f"golden set must cover every UserState; missing={missing}")
    if len(materialized) < 36:
        raise ValueError("a fraud evaluation set requires at least 36 cases")
