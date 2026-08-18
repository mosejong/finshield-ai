"""결정론 판정을 문장으로 옮기는 경계.

이 함수가 `str | None` 을 돌려주는 것이 설계의 핵심이다. `AnalyzeResponse` 를 받아
`AnalyzeResponse` 를 돌려주지 않으므로, 모델이 무엇을 말하든 위험 수준·점수·
시나리오·권고 행동을 **구조적으로** 바꿀 수 없다. `CLAUDE.md` 의 첫 번째
non-negotiable 을 주석이 아니라 타입으로 지킨다.

검증에 실패하면 설명 없이 간다. 설명이 없는 결과는 불편하지만, 검증을 통과하지
못한 설명이 붙은 결과는 위험하다.
"""

from __future__ import annotations

from app.schemas.analysis import AnalyzeResponse
from app.services.llm.contract import LlmContract
from app.services.llm.minimization import minimize_for_provider
from app.services.llm.prompts import (
    FRAUD_EXPLANATION_PROMPT,
    FRAUD_EXPLANATION_PROMPT_ID,
)
from app.services.llm.provider import LlmProvider, LlmUnavailable
from app.services.llm.validation import LlmOutputRejected, validate_explanation

MAX_EXPLANATION_CHARS = 600

# 프롬프트에서 계산하지 않고 적어 둔다. 계산하면 항상 일치해서 검사가 아무것도
# 증명하지 못한다 - 이 저장소가 `[ -w ]` 와 백업 SQL 검사에서 이미 두 번 밟은
# 함정이다. 프롬프트를 고치면 이 상수가 안 맞아 테스트가 깨지는 것이 목적이다.
FRAUD_EXPLANATION_PROMPT_SHA256 = (
    "d687b79c97118a269ba890907343677124bb44ea4347476e35efc98b949f3a48"
)


def fraud_explanation_contract(*, provider: str, model: str) -> LlmContract:
    """설명용 고정 계약. provider 와 model 만 다르고 나머지는 고정이다."""
    return LlmContract(
        provider=provider,
        model=model,
        prompt_id=FRAUD_EXPLANATION_PROMPT_ID,
        prompt_sha256=FRAUD_EXPLANATION_PROMPT_SHA256,
        max_input_chars=4_000,
        timeout_seconds=8.0,
        # 벤치마크가 재현 가능해야 한다. 0.0 이 결정론을 보장하지는 않지만,
        # 남는 흔들림을 최소로 줄이는 유일한 손잡이다.
        temperature=0.0,
    )


def _grounded_blocks(response: AnalyzeResponse) -> tuple[str, str, str]:
    signals = "\n".join(f"- {signal.label}" for signal in response.signals) or "- 없음"
    actions = (
        "\n".join(
            f"- ({action.priority}순위) {action.title} — {action.reason}"
            for action in response.actions
        )
        or "- 없음"
    )
    sources = (
        "\n".join(
            f"- {source.organization}: {source.title}"
            for source in response.official_sources
        )
        or "- 없음"
    )
    return signals, actions, sources


def build_grounded_text(response: AnalyzeResponse) -> str:
    """모델에게 보여 준 근거 전체.

    출력 검증의 기준이 된다. 모델에게 보여 준 것과 검증 기준이 어긋나면, 정당한
    설명이 거부되거나 지어낸 연락처가 통과한다. 그래서 같은 함수에서 만든다.
    """
    return "\n".join(_grounded_blocks(response))


def explain_analysis(
    response: AnalyzeResponse,
    message: str,
    *,
    provider: LlmProvider,
    contract: LlmContract,
) -> str | None:
    """설명 문장을 만든다. 만들지 못하면 None.

    None 은 예외 상황이 아니라 정상 결과 중 하나다. 호출하는 쪽은 설명이 없어도
    동작해야 한다.
    """
    contract.verify_prompt(FRAUD_EXPLANATION_PROMPT)

    minimized = minimize_for_provider(message)
    signals, actions, sources = _grounded_blocks(response)

    prompt = FRAUD_EXPLANATION_PROMPT.format(
        risk_level=response.risk_level,
        scenario=response.scenario.value,
        signals=signals,
        actions=actions,
        sources=sources,
        message=minimized.text[: contract.max_input_chars],
    )

    try:
        raw = provider.generate(contract=contract, prompt=prompt)
    except LlmUnavailable:
        return None

    try:
        return validate_explanation(
            raw,
            grounded_text=build_grounded_text(response),
            max_chars=MAX_EXPLANATION_CHARS,
        )
    except LlmOutputRejected:
        return None
