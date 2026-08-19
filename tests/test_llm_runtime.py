"""설명 계층의 조립과 모델 순서를 검사한다.

`explanation.py` 는 이미 따로 검사된다. 여기서 보는 것은 **그 위의 정책**이다 -
언제 켜지는가, 어떤 모델을 어떤 순서로 쓰는가, 그리고 무엇이 조용히 꺼지지
않는가.

마지막 항목이 이 파일의 이유다. 설정이 틀렸을 때 서비스가 정상으로 보이면서
"왜 위험한지" 만 영영 비어 있는 상태가 가장 나쁘다. 그 상태를 만들 수 있는
경로마다 테스트를 하나씩 둔다.
"""

from __future__ import annotations

import pytest

from app.schemas.analysis import AnalyzeRequest, AnalyzeResponse
from app.services.fraud_analysis import analyze_fraud
from app.services.llm.contract import LlmContract
from app.services.llm.provider import LlmUnavailable
from app.services.llm.runtime import (
    EXPLANATION_FALLBACK_MODEL,
    EXPLANATION_MODEL,
    ExplanationRuntime,
    LlmRuntimeConfigurationError,
    build_explanation_runtime,
    explain_with_fallback,
)

MESSAGE = "금융감독원입니다. 계좌가 범죄에 연루되어 즉시 이체가 필요합니다."


@pytest.fixture
def verdict() -> AnalyzeResponse:
    return analyze_fraud(AnalyzeRequest(text=MESSAGE))


class _ScriptedProvider:
    """모델별로 성공/실패를 지정할 수 있는 프로바이더.

    실패를 흉내 내는 것이 요점이라 네트워크를 쓰지 않는다.
    """

    def __init__(self, answers: dict[str, str | None]) -> None:
        self._answers = answers
        self.asked: list[str] = []

    @property
    def name(self) -> str:
        return "google_ai_studio"

    def generate(self, *, contract: LlmContract, prompt: str) -> str:
        self.asked.append(contract.model)
        answer = self._answers.get(contract.model)
        if answer is None:
            raise LlmUnavailable(f"{contract.model} is unavailable")
        return answer


def _runtime_with(provider: _ScriptedProvider) -> ExplanationRuntime:
    """운영과 같은 계약 순서로 조립한다.

    계약을 손으로 만들지 않고 `build_explanation_runtime` 을 쓰는 이유는, 순서가
    바뀌면 이 테스트도 같이 따라가야 하기 때문이다. 순서를 여기서 다시 적으면
    운영이 바뀌어도 테스트는 옛 순서를 계속 통과시킨다.
    """
    real = build_explanation_runtime(
        {"FINSHIELD_LLM_PROVIDER": "google_ai_studio", "GEMINI_API_KEY": "test-key"}
    )
    assert real is not None
    return ExplanationRuntime(provider=provider, contracts=real.contracts)


def test_the_layer_is_off_unless_someone_turns_it_on() -> None:
    """기본값이 켜짐이면, 키를 안 넣은 환경이 첫 요청에서 터진다."""
    assert build_explanation_runtime({}) is None


def test_a_typo_in_the_provider_name_is_refused() -> None:
    """`gogole_ai_studio` 를 조용히 off 로 처리하면 아무도 오타를 못 찾는다."""
    with pytest.raises(LlmRuntimeConfigurationError):
        build_explanation_runtime({"FINSHIELD_LLM_PROVIDER": "gogole_ai_studio"})


def test_turning_it_on_without_a_key_is_an_error_not_a_silent_off() -> None:
    """켜 놓고 안 되는 것과 끈 것은 다른 상태다.

    둘을 같게 처리하면 배포에서 키를 빠뜨렸을 때 서비스가 정상으로 보인다.
    """
    with pytest.raises(LlmRuntimeConfigurationError):
        build_explanation_runtime({"FINSHIELD_LLM_PROVIDER": "google_ai_studio"})


def test_the_models_come_from_code_not_the_environment() -> None:
    """모델을 환경변수로 못 바꾼다.

    `contract.py` 가 계약을 고정하는 이유가 그것이다 - 모델이 배포마다 다르면
    `evaluation/` 이 낸 숫자가 어느 모델의 것인지 알 수 없다. 여기서는 그럴듯한
    이름의 환경변수를 넣어 두고, 그래도 코드 상수가 이기는지 본다.
    """
    runtime = build_explanation_runtime(
        {
            "FINSHIELD_LLM_PROVIDER": "google_ai_studio",
            "GEMINI_API_KEY": "test-key",
            "FINSHIELD_LLM_MODEL": "gemini-1.0-pro",
            "GEMINI_MODEL": "gemini-1.0-pro",
        }
    )

    assert runtime is not None
    assert [contract.model for contract in runtime.contracts] == [
        EXPLANATION_MODEL,
        EXPLANATION_FALLBACK_MODEL,
    ]


def test_the_worst_case_wait_is_bounded_and_the_fallback_is_the_shorter_one() -> None:
    """대체 모델까지 가면 두 번 기다린다. 그 합이 이 계층의 최대 지연이다.

    타임아웃을 모델마다 따로 두는 순간, 둘을 더한 값이 사용자가 볼 수 있는 최대
    대기 시간이 된다. 각각을 넉넉하게 잡다 보면 합이 조용히 커진다 - 그래서 합에
    상한을 건다.

    대체 모델 쪽이 더 짧아야 하는 이유는 순서 때문이다. 주 모델이 시간을 다 쓴
    뒤에야 대체 모델이 시작하므로, 뒤에 오는 쪽이 길면 이미 오래 기다린 사람을
    더 오래 기다리게 한다.
    """
    runtime = build_explanation_runtime(
        {"FINSHIELD_LLM_PROVIDER": "google_ai_studio", "GEMINI_API_KEY": "test-key"}
    )
    assert runtime is not None

    timeouts = [contract.timeout_seconds for contract in runtime.contracts]
    assert sum(timeouts) <= 20.0
    assert timeouts == sorted(timeouts, reverse=True)


def test_the_first_model_answers_and_the_second_is_never_asked(
    verdict: AnalyzeResponse,
) -> None:
    """주 모델이 답하면 유료 호출이 한 번만 나가야 한다."""
    provider = _ScriptedProvider({EXPLANATION_MODEL: "요구 자체가 정상 절차에 없습니다."})

    result = explain_with_fallback(verdict, MESSAGE, runtime=_runtime_with(provider))

    assert result.text == "요구 자체가 정상 절차에 없습니다."
    assert result.model == EXPLANATION_MODEL
    assert provider.asked == [EXPLANATION_MODEL]


def test_the_fallback_answers_when_the_first_model_is_down(
    verdict: AnalyzeResponse,
) -> None:
    provider = _ScriptedProvider(
        {
            EXPLANATION_MODEL: None,
            EXPLANATION_FALLBACK_MODEL: "정상 절차에 없는 요구입니다.",
        }
    )

    result = explain_with_fallback(verdict, MESSAGE, runtime=_runtime_with(provider))

    assert result.text == "정상 절차에 없는 요구입니다."
    assert result.model == EXPLANATION_FALLBACK_MODEL
    assert provider.asked == [EXPLANATION_MODEL, EXPLANATION_FALLBACK_MODEL]


def test_the_answering_model_is_recorded_not_the_configured_one(
    verdict: AnalyzeResponse,
) -> None:
    """대체 모델이 답했는데 주 모델 이름을 기록하면 평가가 오염된다."""
    provider = _ScriptedProvider(
        {EXPLANATION_MODEL: None, EXPLANATION_FALLBACK_MODEL: "요구가 이상합니다."}
    )

    result = explain_with_fallback(verdict, MESSAGE, runtime=_runtime_with(provider))

    assert result.model != EXPLANATION_MODEL


def test_every_model_failing_yields_no_explanation(verdict: AnalyzeResponse) -> None:
    """설명이 없는 것은 정상 결과다. 예외로 올리면 판정까지 같이 죽는다."""
    provider = _ScriptedProvider({})

    result = explain_with_fallback(verdict, MESSAGE, runtime=_runtime_with(provider))

    assert result.text is None
    assert result.model is None


def test_output_that_invents_a_hotline_is_dropped_and_falls_through(
    verdict: AnalyzeResponse,
) -> None:
    """근거에 없는 연락처를 지어내면 그 모델의 답은 버린다.

    `validate_explanation` 이 잡는 것을 여기서 다시 검사하는 이유는, 거부가
    **대체 모델 시도로 이어지는지**가 이 계층의 동작이기 때문이다.
    """
    provider = _ScriptedProvider(
        {
            EXPLANATION_MODEL: "즉시 02-1234-5678 로 신고하세요.",
            EXPLANATION_FALLBACK_MODEL: "정상 절차에 없는 요구입니다.",
        }
    )

    result = explain_with_fallback(verdict, MESSAGE, runtime=_runtime_with(provider))

    assert result.model == EXPLANATION_FALLBACK_MODEL
    assert "1234" not in (result.text or "")
