import json
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from app.schemas.analysis import AnalyzeRequest, Persona, UserState


GOLDEN_SET_PATH = Path(__file__).with_name("data") / "fraud_golden_v0.1.jsonl"
RISK_RANK = {"low": 0, "medium": 1, "high": 2}
FRAUD_TYPE_CODES = {
    "authority_impersonation",
    "loan_policy_impersonation",
    "account_access_request",
    "money_mule_transfer",
    "smishing_malware",
    "card_delivery_impersonation",
}
ACTION_CODES = {
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
}


class FraudGoldenCase(BaseModel):
    case_id: str = Field(pattern=r"^fg-[0-9]{3}$")
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


def _validate_collection(cases: Iterable[FraudGoldenCase]) -> None:
    materialized = list(cases)
    case_ids = [case.case_id for case in materialized]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("golden case IDs must be unique")
    covered_states = {case.state for case in materialized}
    if covered_states != set(UserState):
        missing = sorted(state.value for state in set(UserState) - covered_states)
        raise ValueError(f"golden set must cover every UserState; missing={missing}")
    if len(materialized) < 36:
        raise ValueError("fraud golden v0.1 requires at least 36 cases")
