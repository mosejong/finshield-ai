"""LLM 단독 판정자. **제품에는 없는 것이다.**

이 파일이 `app/` 이 아니라 `evaluation/` 에 있는 것이 설계의 전부다. 제품에서
LLM 은 이미 정해진 판정을 문장으로 옮길 뿐이고, 그 경계는
`app/services/llm/explanation.py` 가 `str | None` 을 돌려주는 것으로 강제된다.
여기 있는 판정자는 그 경계를 일부러 없앤 **비교 대상**이다 - 같은 모델에게
규칙 엔진의 일을 통째로 시켜 보고, 그 결과를 규칙 엔진과 나란히 놓기 위해서만
존재한다. 그래서 요청 경로에서 import 하지 않고, `app/` 어디에서도 부르지
않는다.

측정을 이렇게까지 하는 이유는 `CLAUDE.md` 의 Evaluation 절이 Rule-only /
LLM-only / Hybrid 비교를 요구하기 때문이고, 더 실질적으로는 "그냥 LLM 한테
시키면 되지 않나" 라는 질문에 문장이 아니라 숫자로 답하기 위해서다.

**공정하게 진다/이긴다.** 모델에게 규칙 엔진과 같은 입력(원문·persona·state)을
주고, 같은 출력 어휘(사기 유형 6개, 위험 수준 3단계, 행동 코드 11개)를 준다.
어휘를 숨긴 채 자유서술을 시키면 채점이 불가능하고, 그렇게 얻은 낮은 점수는
모델의 성능이 아니라 프롬프트의 결함이다.

`prompts.py` 와 같은 방식으로 프롬프트를 sha256 으로 고정한다. 한 글자 고치면
테스트가 깨지고, 고친 사람이 유료 호출을 다시 돌리게 된다.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.domain.fraud.classification import FRAUD_TYPE_ORDER
from app.domain.fraud.policy import ACTION_POLICIES
from app.services.llm.contract import LlmContract
from app.services.llm.minimization import minimize_for_provider
from app.services.llm.provider import LlmProvider, LlmUnavailable

FRAUD_JUDGE_PROMPT_ID = "fraud_judge_v1"

# 판정 결과를 저장소에 커밋한다. 그래야 CI 와 심사자가 유료 호출 없이 같은 표를
# 다시 만들 수 있고, 어떤 데이터·어떤 모델·어떤 프롬프트로 잰 숫자인지 파일
# 하나로 확인된다.
JUDGE_RUN_PATH = (
    Path(__file__).with_name("results") / "llm-judge-fraud-v0.1.json"
)

# state 코드를 그대로 보내면 모델이 무슨 뜻인지 추측해야 한다. 규칙 엔진은
# `STATE_ACTIONS` 로 이 의미를 정확히 알고 있으므로, 모델에게도 같은 뜻을 준다.
# 여기서 아끼면 비교가 규칙 대 모델이 아니라 규칙 대 "설명을 덜 받은 모델" 이 된다.
STATE_GLOSSARY: tuple[tuple[str, str], ...] = (
    ("received_only", "메시지를 받기만 했고 아직 아무것도 하지 않았다"),
    ("clicked_link", "메시지에 있는 링크를 눌렀다"),
    ("shared_personal_info", "이름·연락처 같은 개인정보를 알려 줬다"),
    ("shared_account_access", "비밀번호·OTP·통장·카드 등 금융 접근수단을 넘겼다"),
    ("installed_app", "상대방이 보낸 앱이나 프로그램을 설치했다"),
    ("received_unknown_money", "출처를 모르는 돈이 계좌로 들어왔다"),
    ("transferred_money", "상대방이 말한 곳으로 돈을 보냈다"),
)

PERSONA_GLOSSARY: tuple[tuple[str, str], ...] = (
    ("early_career", "사회초년생"),
    ("small_business", "소상공인"),
    ("unknown", "알 수 없음"),
)

# 유형 정의는 `classification.py` 가 어떤 신호를 어떤 유형으로 묶는지를 한국어로
# 옮긴 것이다. 규칙 엔진이 쓰는 정의와 다른 정의를 주면 두 결과를 같은 표에
# 올릴 수 없다.
FRAUD_TYPE_GLOSSARY: tuple[tuple[str, str], ...] = (
    (
        "authority_impersonation",
        "수사기관·금융감독기관·공공기관 직원을 사칭한다",
    ),
    (
        "loan_policy_impersonation",
        "정부·정책자금, 저금리 대환 같은 대출 조건을 미끼로 접근한다",
    ),
    # `advance_fee_demand`·`investment_scheme`·`acquaintance_impersonation`·
    # `isolation_coercion` 은 여기 없다. 이 프롬프트를 고치면 sha256 이 바뀌고,
    # 이미 돈을 주고 받아 둔 판정 결과가 어떤 프롬프트에서 나왔는지 알 수 없게
    # 된다. 유형을 늘리려면 프롬프트를 버전으로 올리고 유료 재실행을 해야 한다.
    # 그때까지 LLM 단독 판정은 6종 기준이고, 새 유형 **네 개**의 llm_only
    # 지표는 0 이다. 규칙 엔진이 이기는 것처럼 보이는 자리가 넷이라는 뜻이므로,
    # 이 숫자를 비교표에 쓸 때는 프롬프트 버전을 함께 적는다.
    (
        "account_access_request",
        "비밀번호·OTP·인증번호·통장·카드 등 인증정보나 금융 접근수단을 요구한다",
    ),
    (
        "money_mule_transfer",
        "들어온 돈을 다시 보내라고 하거나 계좌를 빌려 달라고 한다",
    ),
    (
        "smishing_malware",
        "링크 접속, 앱 설치, 원격제어 허용을 유도한다",
    ),
    (
        "card_delivery_impersonation",
        "신청한 적 없는 카드 발급·배송을 알리며 확인을 유도한다",
    ),
)


def _bullets(pairs: Iterable[tuple[str, str]]) -> str:
    return "\n".join(f"- {code}: {gloss}" for code, gloss in pairs)


FRAUD_JUDGE_PROMPT = """당신은 한국어 금융사기 의심 메시지를 분류한다. 아래 메시지 하나만 보고 판정한다.

[사기 유형 코드]
{fraud_types}

[위험 수준]
- high: 지금 응하면 금전·계좌 피해로 바로 이어진다
- medium: 정상 절차와 다른 점이 있어 확인이 필요하다
- low: 위험 요소가 보이지 않는다

[권고 행동 코드]
{actions}

[사용자 유형]
{personas}

[사용자가 이미 한 행동]
{states}

[입력]
사용자 유형: {persona}
사용자가 이미 한 행동: {state}
메시지: {message}

[출력 형식]
JSON 객체 하나만 출력한다. 코드블록, 머리말, 설명 문장을 붙이지 않는다.
{{"is_fraud": true, "fraud_types": ["코드"], "risk_level": "high", "actions": ["코드"]}}

규칙:
- 위 목록에 없는 코드를 만들지 않는다.
- 사기가 아니면 is_fraud 는 false 이고 fraud_types 는 빈 배열이다.
- risk_level 은 사용자가 이미 한 행동까지 반영한다.
- actions 에는 이 사용자가 지금 해야 할 행동만 넣는다."""

# 계산하지 않고 적어 둔다. 계산하면 항상 일치해서 검사가 아무것도 증명하지
# 못한다 - `explanation.py` 의 같은 상수와 같은 이유다.
FRAUD_JUDGE_PROMPT_SHA256 = (
    "1fc8d0e92d7e5d5dc78a80e6735207c0c2f4fd2f0912081f1b2459ca0e7cca36"
)

# 제품 설명 계층과 같은 모델을 쓴다. 다른 모델로 재면 "규칙 대 모델" 이 아니라
# "규칙 대 다른 모델" 이 되고, 실제로 배포된 것과 비교가 되지 않는다.
JUDGE_MODEL = "gemini-3.6-flash"

# 설명(14초)보다 길게 준다. 판정은 사용자를 기다리게 하는 호출이 아니라 배치
# 측정이므로, 여기서 짧게 끊으면 모델의 실력이 아니라 우리 인내심을 재게 된다.
JUDGE_TIMEOUT_SECONDS = 30.0

RISK_LEVELS = ("low", "medium", "high")

_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


class LlmJudgement(BaseModel):
    """한 사례에 대한 모델 판정 한 건.

    실패도 판정의 일종으로 기록한다. `ok=False` 인 줄을 빼고 집계하면 "모델이
    답한 것만 골라 채점" 하는 것이 되고, 그것은 LLM 단독 운영의 실제 결과가
    아니다 - 사용자 입장에서 답이 없는 것은 경고가 없는 것과 같다.
    """

    case_id: str = Field(pattern=r"^fg-[0-9]{3}$")
    ok: bool
    is_fraud: bool = False
    fraud_types: list[str] = Field(default_factory=list)
    risk_level: str = Field(default="low", pattern=r"^(low|medium|high)$")
    actions: list[str] = Field(default_factory=list)
    #: 어휘에 없는 코드를 모델이 만들어 낸 경우. 버리되 버린 사실은 남긴다.
    dropped_codes: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0
    #: 실패 원인의 **종류**만 남긴다. 응답 본문과 원문은 남기지 않는다(adr/0006).
    failure: str | None = None


class LlmJudgeRun(BaseModel):
    """유료 호출 한 번의 결과 전체. 이 파일이 있으면 재실행 없이 집계한다."""

    judged_at: str
    dataset_id: str
    dataset_sha256: str
    provider: str
    model: str
    prompt_id: str
    prompt_sha256: str
    temperature: float
    judgements: list[LlmJudgement]

    def by_case_id(self) -> dict[str, LlmJudgement]:
        return {judgement.case_id: judgement for judgement in self.judgements}


def fraud_judge_contract(
    *,
    provider: str,
    model: str = JUDGE_MODEL,
    timeout_seconds: float = JUDGE_TIMEOUT_SECONDS,
) -> LlmContract:
    """판정용 고정 계약.

    `temperature=0.0` 은 설명 계약과 같은 이유다. 0.0 이 결정론을 보장하지는
    않지만, 두 번 돌렸을 때 숫자가 달라지는 폭을 줄이는 유일한 손잡이다.
    """
    return LlmContract(
        provider=provider,
        model=model,
        prompt_id=FRAUD_JUDGE_PROMPT_ID,
        prompt_sha256=FRAUD_JUDGE_PROMPT_SHA256,
        max_input_chars=4_000,
        timeout_seconds=timeout_seconds,
        temperature=0.0,
    )


def build_judge_prompt(
    *, persona: str, state: str, message: str, max_input_chars: int
) -> str:
    """모델에게 실제로 나가는 문자열.

    골든셋은 합성 문장이라 개인정보가 없지만, 그래도 제품과 같은 최소화 경로를
    지난다. 측정 경로가 운영 경로보다 느슨하면 측정한 것이 운영되는 것과
    달라진다.
    """
    minimized = minimize_for_provider(message)
    return FRAUD_JUDGE_PROMPT.format(
        fraud_types=_bullets(FRAUD_TYPE_GLOSSARY),
        actions=_bullets(
            (code, policy.title) for code, policy in ACTION_POLICIES.items()
        ),
        personas=_bullets(PERSONA_GLOSSARY),
        states=_bullets(STATE_GLOSSARY),
        persona=persona,
        state=state,
        message=minimized.text[:max_input_chars],
    )


def parse_judgement(case_id: str, raw: str, *, latency_ms: float) -> LlmJudgement:
    """모델 출력 한 덩어리를 판정으로 옮긴다. 못 옮기면 실패로 기록한다.

    코드블록을 벗겨 주는 것은 관대함이 아니라 공정함이다. ```json 을 붙이는 것은
    형식 지시를 어긴 것이 맞지만, 그것 때문에 사기 판정을 통째로 버리면 모델의
    탐지 성능이 아니라 서식 준수율을 재게 된다. 반면 **어휘에 없는 코드는 버린다** -
    그쪽은 제품이 실제로 쓸 수 없는 출력이다.
    """
    fenced = _FENCE.match(raw)
    body = fenced.group(1) if fenced else raw.strip()

    try:
        payload = json.loads(body)
    except ValueError:
        return LlmJudgement(
            case_id=case_id, ok=False, latency_ms=latency_ms, failure="unparsable_json"
        )
    if not isinstance(payload, dict):
        return LlmJudgement(
            case_id=case_id, ok=False, latency_ms=latency_ms, failure="not_an_object"
        )

    fraud_types, dropped_types = _filter_codes(
        payload.get("fraud_types"), set(FRAUD_TYPE_ORDER)
    )
    actions, dropped_actions = _filter_codes(
        payload.get("actions"), set(ACTION_POLICIES)
    )
    risk_level = payload.get("risk_level")
    if risk_level not in RISK_LEVELS:
        return LlmJudgement(
            case_id=case_id, ok=False, latency_ms=latency_ms, failure="unknown_risk_level"
        )
    is_fraud = payload.get("is_fraud")
    if not isinstance(is_fraud, bool):
        return LlmJudgement(
            case_id=case_id, ok=False, latency_ms=latency_ms, failure="missing_is_fraud"
        )

    return LlmJudgement(
        case_id=case_id,
        ok=True,
        is_fraud=is_fraud,
        fraud_types=fraud_types,
        risk_level=risk_level,
        actions=actions,
        dropped_codes=dropped_types + dropped_actions,
        latency_ms=latency_ms,
    )


def judge_case(
    *,
    case_id: str,
    persona: str,
    state: str,
    message: str,
    provider: LlmProvider,
    contract: LlmContract,
    clock: Any,
) -> LlmJudgement:
    """호출 한 건. 프로바이더가 죽어도 예외를 올리지 않는다.

    61건짜리 배치가 한 건 때문에 통째로 멈추면, 이미 나간 유료 호출이 버려진다.
    """
    contract.verify_prompt(FRAUD_JUDGE_PROMPT)
    prompt = build_judge_prompt(
        persona=persona,
        state=state,
        message=message,
        max_input_chars=contract.max_input_chars,
    )

    started_at = clock()
    try:
        raw = provider.generate(contract=contract, prompt=prompt)
    except LlmUnavailable as exc:
        return LlmJudgement(
            case_id=case_id,
            ok=False,
            latency_ms=(clock() - started_at) * 1000,
            # 예외 메시지에는 상태 코드와 예외 종류만 들어 있다
            # (`google_ai_studio.py`). 그대로 남겨도 원문은 새지 않는다.
            failure=str(exc),
        )
    return parse_judgement(case_id, raw, latency_ms=(clock() - started_at) * 1000)


def _filter_codes(
    value: object, allowed: set[str]
) -> tuple[list[str], list[str]]:
    if not isinstance(value, list):
        return [], []
    kept: list[str] = []
    dropped: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        if item in allowed:
            if item not in kept:
                kept.append(item)
        elif item not in dropped:
            dropped.append(item)
    return kept, dropped


def load_judge_run(payload: Mapping[str, Any]) -> LlmJudgeRun:
    return LlmJudgeRun.model_validate(payload)


def merge_judgements(
    previous: Sequence[LlmJudgement], fresh: Sequence[LlmJudgement]
) -> list[LlmJudgement]:
    """`--resume` 용. 새 판정이 이긴다.

    앞선 실행이 중간에 죽었을 때 성공한 것까지 다시 부르지 않기 위한 것이다.
    유료 호출을 아끼는 장치이지 결과를 고르는 장치가 아니므로, 같은 사례가 두 번
    있으면 항상 새 쪽을 쓴다.
    """
    merged = {judgement.case_id: judgement for judgement in previous}
    merged.update({judgement.case_id: judgement for judgement in fresh})
    return [merged[case_id] for case_id in sorted(merged)]
