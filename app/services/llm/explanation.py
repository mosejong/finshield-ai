"""결정론 판정을 문장으로 옮기는 경계.

이 함수가 **`AnalyzeResponse` 를 돌려주지 않는 것**이 설계의 핵심이다. 문장 하나만
돌려주므로, 모델이 무엇을 말하든 위험 수준·점수·시나리오·권고 행동을 **구조적으로**
바꿀 수 없다. `CLAUDE.md` 의 첫 번째 non-negotiable 을 주석이 아니라 타입으로 지킨다.

검증에 실패하면 설명 없이 간다. 설명이 없는 결과는 불편하지만, 검증을 통과하지
못한 설명이 붙은 결과는 위험하다.

**그 "없음" 에 이유를 붙인다.** 오래 `str | None` 이었고, `None` 은 열 가지 이상의
서로 다른 사건을 하나로 접었다 - 안전 필터가 우리 요청을 거부한 것, 모델이 답을
만들다 멈춘 것, 우리 토큰 예산이 좁아 잘린 것, 모델이 없는 신고번호를 지어내서
버린 것. 운영에서 이 넷은 완전히 다른 일이고 대응도 다르다. 그래서 이제
`ExplanationAttempt(text, outcome)` 을 돌려준다. **설명이 없는 이유를 모르면 그
이유를 고칠 수 없다.**

이 함수는 여전히 세지 않고 기록하지 않는다. 순수한 계층이 로거를 들고 있으면
테스트가 로그를 켜 놓고 돌아야 하고, 평가 스크립트가 이 함수를 부를 때마다 운영
지표가 오염된다. **세는 것은 조립하는 자리(`runtime.py`)다.**

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
from app.services.llm.outcomes import ExplanationAttempt, ExplanationOutcome
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
    "c7532280daf58884020ccda3e025c3ff2c5e3ad2b23c6881555d4a561b9ed76b"
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


#: 빈 근거 칸에 들어가는 값. 여기 한 곳에서만 정한다 — `has_grounded_evidence` 가
#: 이 값과 비교해서 물어볼지를 정하므로, 두 자리에 따로 적으면 언젠가 어긋난다.
_EMPTY_BLOCK = "- 없음"


def _grounded_blocks(response: AnalyzeResponse) -> tuple[str, str, str]:
    signals = (
        "\n".join(f"- {signal.label}" for signal in response.signals) or _EMPTY_BLOCK
    )
    actions = (
        "\n".join(
            f"- ({action.priority}순위) {action.title} — {action.reason}"
            for action in response.actions
        )
        or _EMPTY_BLOCK
    )
    sources = (
        "\n".join(
            f"- {source.organization}: {source.title}"
            for source in response.official_sources
        )
        or _EMPTY_BLOCK
    )
    return signals, actions, sources


def has_grounded_evidence(response: AnalyzeResponse) -> bool:
    """모델에게 보여 줄 근거가 하나라도 있는가.

    **판단의 근거는 실패 사유가 아니라 근거 자체다.** 거부당한 뒤에 "아, 근거가
    없었구나" 로 되돌아가면 이미 호출값을 치른 뒤이고, 어떤 사유로 되돌아갈지도
    정해야 한다. 그건 `explain_with_fallback` 이 지키는 규칙(사유는 세기 위한
    것이지 분기하기 위한 것이 아니다)을 깨는 자리다. 부르기 전에 근거를 보면
    그 규칙을 건드리지 않는다.

    `_grounded_blocks` 에서 파생시키는 이유는 어긋남을 막기 위해서다. 모델에게
    보여 주는 것, 출력 검증의 기준, 물어볼지 말지의 판단 — 셋이 같은 함수에서
    나와야 한다. 따로 계산하면 언젠가 "보여 준 것은 비었는데 물어보기는 했다" 가
    된다.
    """
    return any(block != _EMPTY_BLOCK for block in _grounded_blocks(response))


#: 언제 모델을 부르는지에 붙인 이름. **프롬프트 sha256 과 같은 목적이다.**
#:
#: 프로브 결과 파일은 셋과 지시문을 적어 두지만, 같은 셋·같은 지시문이라도 "근거가
#: 비어도 물어봤다" 와 "비면 안 물어봤다" 는 완전히 다른 표를 만든다. 적어 두지
#: 않으면 벤치마크가 옛 실행을 `measured` 로 계속 내놓고, 읽는 쪽은 그 표가 지금
#: 배포된 것과 다른 규칙에서 나왔다는 사실 자체를 모른다. 2026-08-25 에 지시문
#: sha256 검사가 막아 준 것과 정확히 같은 종류의 구멍이다.
EXPLANATION_CALL_POLICY = "skip_when_no_evidence"

#: 이 규칙이 들어오기 전의 이름. 저장소에 남아 있는 실행들이 이것으로 읽힌다.
EXPLANATION_CALL_POLICY_ASK_ALWAYS = "ask_always"


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
) -> ExplanationAttempt:
    """설명 문장을 만든다. 만들지 못하면 문장 없이 사유만.

    실패는 예외 상황이 아니라 정상 결과 중 하나다. 호출하는 쪽은 설명이 없어도
    동작해야 한다 - 다만 이제 **왜 없는지**를 함께 받는다.
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

    # 예외의 사유를 그대로 옮긴다. 여기서 다시 판단하지 않는 것이 중요하다 -
    # 사유를 아는 곳은 실패가 일어난 곳이고, 이 자리에서 추측하면 두 곳이 어긋난다.
    try:
        raw = provider.generate(contract=contract, prompt=prompt)
    except LlmUnavailable as exc:
        return ExplanationAttempt(text=None, outcome=exc.outcome)

    try:
        text = validate_explanation(
            raw,
            grounded_text=build_grounded_text(response),
            max_chars=MAX_EXPLANATION_CHARS,
            risk_level=response.risk_level,
        )
    except LlmOutputRejected as exc:
        return ExplanationAttempt(text=None, outcome=exc.outcome)
    return ExplanationAttempt(text=text, outcome=ExplanationOutcome.OK)
