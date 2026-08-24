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
# 고쳤다면 v0.4 는 성능이 아니라 기억을 재는 자가 된다. v0.5 는 절 범위 수정을
# 재면서 소진되었다. v0.6 은 그 뒤에 남은 세 결함을 고치기 전에 얼린 셋이다.
#
# v0.6 은 앞선 셋들과 방향이 반대다. v0.2~v0.5 가 잰 수정은 전부 **넓히는**
# 것이었고, 넓히기의 값은 정상 문장에서 치러지므로 부정 사례로 재면 됐다.
# 이번 세 수정 중 둘은 **좁히는** 것이다 - 기관 게이트에 민감 요구 조건을
# 걸고, 공식 창구 안내 절을 요구에서 뺀다. 좁히기의 값은 **사기 쪽에서**
# 치러진다. 그래서 이 셋은 좁히기가 끊을 수 있는 양성 사례를 함께 담는다.
#
# v0.7 은 v0.6 이 남긴 세 결함을 고치기 전에 얼린 셋이고, 방향이 또 다르다.
# 세 수정 중 하나(`HIGH_RISK_SIGNAL_COMBINATIONS` 확장)는 **등급을 올린다.**
# 넓히기는 정상 문장으로, 좁히기는 사기 문장으로 값을 쟀는데 **등급을 올리는
# 수정의 값을 잴 자리는 지금까지 없었다** - `expected_min_risk` 는 바닥만
# 보므로 모든 문자를 high 로 찍는 엔진이 만점을 받는다. v0.7 이 천장을
# 들고 온 이유이고, 천장은 **정상 문장에만** 선언한다. 사기를 필요 이상으로
# 높게 매기는 것은 결함이 아니라 신중함이다.
#
# v0.8 은 v0.7 이 남긴 일곱 건의 미탐을 고치기 전에 얼린 셋이고, 방향이
# v0.6·v0.7 과 또 다르다. 이번 여섯 수정은 **거의 전부 넓히기**다 - 권한
# 위임 요구, 재전달 어형, 예방 표지 축소, 지검 자칭, 높임 어미 송금. 넓히기의
# 값은 정상 문장에서 치러지므로, 이 셋의 안전장치는 부정 사례를 **넓히기가
# 깨질 바로 그 자리에** 놓는 것이다. 권한 위임은 실재하는 제도이고("위임장을
# 지참하고 지점에 방문하셔야"), 정산금은 관리비 고지서의 낱말이며, 지검은
# 지명이 붙은 고유명사라 일상 대화에 그대로 나온다.
#
# 예방 표지를 **좁히는** 수정 하나가 섞여 있다(`드리지 않`). 좁히기의 값은
# 사기가 아니라 정상 쪽에서 치러진다 - 억제를 풀면 진짜 예방 안내문이
# 사기로 올라간다. 그래서 정상 36건 중 여섯 건이 진짜 예방 안내문이다.
#
# v0.9 는 v0.8 이 남긴 결함을 고치기 전에 얼린 셋이고, 방향이 또 다르다.
# v0.8 에서 이진 판정이 만점이 되면서 남은 변별력이 **이름·행동·등급**으로만
# 옮겨 갔다. 사기/정상 사례를 더 넣는 것으로는 이 셋에서 아무것도 재지
# 못한다. 그래서 이번 셋은 **확인 행동이 어디로 가리키는가**를 겨냥한다 -
# 자칭을 한 메시지와 하지 않은 메시지를 같은 신호 위에 짝지어 놓고, 각
# 사례가 내면 안 되는 행동을 `forbidden_action_codes` 로 함께 적는다.
#
# 넓히기도 좁히기도 올리기도 아닌 **갈아 끼우기**라서, 값은 양쪽에서
# 치러진다. 자칭이 없는 쪽으로 너무 돌면 기관 사칭 열 건이 공식 창구를
# 잃고, 자칭 쪽으로 너무 돌면 지인 사칭 네 건이 v0.4 회귀가 된다.
#
# v1.0 은 **앞선 회차들이 이름으로 적어 둔 결함만** 재는 셋이다. 새로
# 상상한 사기 어형이 아니라 v0.9 §9 가 다음 회차 몫으로 남긴 목록이
# 그대로 다섯 그룹이 됐다 - 우언적 금지 어형, 자기 경로 제한, 숫자로 적은
# 기한, 띄어 쓴 `대환 대출`, 고립 요구만 든 조건부 자칭.
#
# 다섯 수정이 **전부 넓히기**라서 값은 한 방향으로만 치러진다. 그래서 이
# 셋은 사기보다 정상을 세게 짠다 - 정상 34건 전부가 천장을 선언하고, 그중
# 스물여덟 건이 **넓히려는 바로 그 어형을 쓰는 정상 문장**이다. 예방
# 안내문은 금지형으로 위험한 행동을 입에 올리고, 정상 공지는 창구를
# `…에서만` 으로 제한하며, 청구서는 오늘 자정을 말하고, 은행은 대환 대출을
# 안내한다. 넓히기가 한 칸이라도 넘치면 그 자리에서 바로 드러난다.
HOLDOUT_V0_2_PATH = Path(__file__).with_name("data") / "fraud_holdout_v0.2.jsonl"
HOLDOUT_V0_3_PATH = Path(__file__).with_name("data") / "fraud_holdout_v0.3.jsonl"
HOLDOUT_V0_4_PATH = Path(__file__).with_name("data") / "fraud_holdout_v0.4.jsonl"
HOLDOUT_V0_5_PATH = Path(__file__).with_name("data") / "fraud_holdout_v0.5.jsonl"
HOLDOUT_V0_6_PATH = Path(__file__).with_name("data") / "fraud_holdout_v0.6.jsonl"
HOLDOUT_V0_7_PATH = Path(__file__).with_name("data") / "fraud_holdout_v0.7.jsonl"
HOLDOUT_V0_8_PATH = Path(__file__).with_name("data") / "fraud_holdout_v0.8.jsonl"
HOLDOUT_V0_9_PATH = Path(__file__).with_name("data") / "fraud_holdout_v0.9.jsonl"
HOLDOUT_V1_0_PATH = Path(__file__).with_name("data") / "fraud_holdout_v1.0.jsonl"
HOLDOUT_V1_1_PATH = Path(__file__).with_name("data") / "fraud_holdout_v1.1.jsonl"
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
    # v0.7 에서 선언한다. **엔진은 아직 이 유형을 내지 못한다.**
    #
    # 라벨 어휘가 엔진보다 앞서는 것은 v0.4 에서 이미 한 일이다(투자·지인
    # 사칭). 셋을 먼저 얼리려면 라벨이 먼저 있어야 하고, 동결 시점 baseline
    # 에서 이 유형의 f1 이 0.0 으로 찍히는 것이 정확한 출발점이다.
    #
    # `secrecy_isolation` 신호는 v0.1 부터 있었지만 대응하는 유형이 없었다.
    # 이진 판정이 `bool(fraud_types)` 이므로, **유형이 없는 신호는 등급만
    # 올리고 판정은 정상으로 내보낸다.** v0.6 `fh-454` 가 그렇게 미탐이 됐다.
    "isolation_coercion",
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
    # v0.7. **재는 자에 천장이 없었다.**
    #
    # `expected_min_risk` 는 바닥만 정한다. 그래서 등급을 올리는 수정은 이
    # 셋의 어떤 지표에서도 점수를 잃을 수 없다 - 모든 문자를 high 로 찍는
    # 엔진이 상태 정책 정확도 1.0 을 받는다. 넓히기의 값을 부정 사례로
    # 재고 좁히기의 값을 양성 사례로 재 왔으면서, **등급을 올리는 수정의
    # 값을 잴 자리는 아예 없었다.**
    #
    # 이 회차가 `HIGH_RISK_SIGNAL_COMBINATIONS` 를 넓히므로 여기서 닫는다.
    # 비워 두면 제약이 없다. v0.1~v0.6 은 비어 있고, 그래서 그 셋들의
    # `risk_ceiling_accuracy` 는 1.0 이 아니라 **null** 로 나간다 - 재지
    # 않은 것을 만점으로 적으면 그것이 곧 지어낸 근거다.
    expected_max_risk: str | None = Field(default=None, pattern=r"^(low|medium|high)$")
    required_action_codes: list[str] = Field(default_factory=list)
    # v0.9. **행동 쪽에도 천장이 없었다.**
    #
    # `required_action_coverage` 는 `required <= predicted` 만 센다. 그래서
    # 행동을 **더 내보내는** 수정은 이 셋의 어떤 지표에서도 점수를 잃을 수
    # 없다 - 모든 메시지에 열두 행동을 전부 붙이는 엔진이 coverage 1.0 을
    # 받는다. v0.7 이 등급에서 발견한 것과 같은 모양이고, 이번 회차가
    # 행동을 **갈아 끼우므로**(자칭에 따라 확인 수단이 달라진다) 여기서
    # 닫는다.
    #
    # 행동이 하나 더 붙는 것은 등급이 한 칸 높은 것보다 조용히 나쁘다.
    # 이름을 대지 않은 상대에게 "공식 대표번호로 확인하세요" 라고 하면
    # 사용자는 **존재하지 않는 창구**를 찾다가 결국 메시지에 적힌 번호로
    # 건다. 틀린 행동은 없는 행동보다 나쁘다.
    forbidden_action_codes: list[str] = Field(default_factory=list)
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
        unknown_forbidden = set(self.forbidden_action_codes) - ACTION_CODES
        if unknown_forbidden:
            raise ValueError(f"unknown action labels: {sorted(unknown_forbidden)}")
        contradictory = set(self.required_action_codes) & set(
            self.forbidden_action_codes
        )
        if contradictory:
            raise ValueError(
                "an action cannot be both required and forbidden: "
                f"{sorted(contradictory)}"
            )
        unemittable = set(self.required_signal_codes) - SIGNAL_CODES
        if unemittable:
            raise ValueError(
                "required_signal_codes must name codes the response can carry; "
                f"unemittable: {sorted(unemittable)}"
            )
        if (
            self.expected_max_risk is not None
            and RISK_RANK[self.expected_max_risk] < RISK_RANK[self.expected_min_risk]
        ):
            raise ValueError(
                "expected_max_risk must not be below expected_min_risk"
            )
        if len(self.expected_fraud_types) != len(set(self.expected_fraud_types)):
            raise ValueError("expected_fraud_types must not contain duplicates")
        if len(self.required_signal_codes) != len(set(self.required_signal_codes)):
            raise ValueError("required_signal_codes must not contain duplicates")
        if len(self.required_action_codes) != len(set(self.required_action_codes)):
            raise ValueError("required_action_codes must not contain duplicates")
        if len(self.forbidden_action_codes) != len(set(self.forbidden_action_codes)):
            raise ValueError("forbidden_action_codes must not contain duplicates")
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
