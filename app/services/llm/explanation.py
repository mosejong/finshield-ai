"""결정론 판정을 문장으로 옮기는 경계.

이 함수가 `str | None` 을 돌려주는 것이 설계의 핵심이다. `AnalyzeResponse` 를 받아
`AnalyzeResponse` 를 돌려주지 않으므로, 모델이 무엇을 말하든 위험 수준·점수·
시나리오·권고 행동을 **구조적으로** 바꿀 수 없다. `CLAUDE.md` 의 첫 번째
non-negotiable 을 주석이 아니라 타입으로 지킨다.

검증에 실패하면 설명 없이 간다. 설명이 없는 결과는 불편하지만, 검증을 통과하지
못한 설명이 붙은 결과는 위험하다.

여기서 사용자 원문이 세 겹을 지난다. `minimization.py` 가 개인정보를 걷어내고,
`untrusted.py` 가 모델을 향한 지시를 무력화하고, `validation.py` 가 나온 문장을
다시 본다. 판정은 이미 계산이 끝나서 인자로 들어오므로, 앞의 두 겹이 원문을
어떻게 고치든 **위험 수준은 영향을 받지 않는다** - 신호 탐지는 이 함수보다 먼저
끝났다.
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
from app.services.llm.untrusted import neutralize_instructions
from app.services.llm.validation import LlmOutputRejected, validate_explanation

MAX_EXPLANATION_CHARS = 600

# 프롬프트에서 계산하지 않고 적어 둔다. 계산하면 항상 일치해서 검사가 아무것도
# 증명하지 못한다 - 이 저장소가 `[ -w ]` 와 백업 SQL 검사에서 이미 두 번 밟은
# 함정이다. 프롬프트를 고치면 이 상수가 안 맞아 테스트가 깨지는 것이 목적이다.
FRAUD_EXPLANATION_PROMPT_SHA256 = (
    "d687b79c97118a269ba890907343677124bb44ea4347476e35efc98b949f3a48"
)


DEFAULT_TIMEOUT_SECONDS = 8.0


def fraud_explanation_contract(
    *,
    provider: str,
    model: str,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> LlmContract:
    """설명용 고정 계약. provider·model·timeout 만 다르고 나머지는 고정이다.

    timeout 이 인자인 이유는 모델마다 걸리는 시간이 자릿수로 다르기 때문이다
    (`docs/34` 2절 실측). 하나로 묶으면 둘 중 하나가 손해를 본다 - 느린 모델에
    맞추면 빠른 모델이 죽었을 때 그만큼 오래 기다리고, 빠른 모델에 맞추면 느린
    모델은 항상 잘린다. 대체 모델까지 두 번 기다릴 수 있으므로 합계를 보고 정한다.

    prompt·max_input_chars·temperature 는 인자가 아니다. 그쪽이 바뀌면 그 전에 잰
    벤치마크가 이 시스템을 설명하지 않는다.
    """
    return LlmContract(
        provider=provider,
        model=model,
        prompt_id=FRAUD_EXPLANATION_PROMPT_ID,
        prompt_sha256=FRAUD_EXPLANATION_PROMPT_SHA256,
        max_input_chars=4_000,
        timeout_seconds=timeout_seconds,
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

    # 순서가 의미를 갖는다. 개인정보를 먼저 걷어내고, 그다음 모델을 향한 지시를
    # 무력화한다. 반대로 하면 `[전화번호]` 로 바뀔 자리가 지시문 자리표시자 안에
    # 숨어 버려서 무엇이 지워졌는지 두 계층의 건수가 어긋난다.
    #
    # 둘 다 **프롬프트가 아니라 값**을 고친다. 그래서 `FRAUD_EXPLANATION_PROMPT`
    # 의 sha256 이 그대로고, 이 변경은 `evaluation/` 재실행을 요구하지 않는다.
    minimized = minimize_for_provider(message)
    neutralized = neutralize_instructions(minimized.text)
    signals, actions, sources = _grounded_blocks(response)

    prompt = FRAUD_EXPLANATION_PROMPT.format(
        risk_level=response.risk_level,
        scenario=response.scenario.value,
        signals=signals,
        actions=actions,
        sources=sources,
        message=neutralized.text[: contract.max_input_chars],
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
            risk_level=response.risk_level,
        )
    except LlmOutputRejected:
        return None
