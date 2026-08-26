"""설명 계층을 켜고 끄는 스위치, 그리고 모델 순서.

`explanation.py` 는 프로바이더와 계약을 **주입받는다**. 그래서 지금까지 이 패키지는
완성돼 있으면서도 요청 경로에 연결되지 않았다 - 누가 그 둘을 만들어 주느냐가
비어 있었다. 이 파일이 그 자리다.

무엇을 환경에 맡기고 무엇을 코드에 박는지가 이 파일의 절반이다.

**환경이 정하는 것: 켜는가.** 배포마다 다르고, 사고가 났을 때 재배포 없이 꺼야
하는 값이다.

**코드가 정하는 것: 어떤 모델인가.** `contract.py` 가 그 이유를 이미 적어 뒀다 -
provider 와 model 이 환경변수로 조용히 움직이면, 그 전에 측정한 벤치마크 숫자가
어느 모델의 것인지 아무도 모르게 된다. 모델을 올리는 것은 코드 변경이어야 하고,
그래야 올린 사람이 `evaluation/` 을 다시 돌리게 된다.

나머지 절반은 **대체 모델**이다. 설명이 없어도 서비스는 돌아가지만, 주 모델이
과부하나 할당량으로 막히는 동안 "왜 위험한지" 가 계속 비어 있는 것도 좋지 않다.
그래서 순서를 정해 두고 앞에서부터 시도한다. 대체 모델도 **똑같이 코드에 박는다** -
안 그러면 지금 보고 있는 설명이 어느 모델에서 나왔는지 모르게 되고, 그것은 위에서
막으려던 문제와 정확히 같은 문제다. 그래서 어느 모델이 답했는지 함께 돌려준다.

기본값이 `off` 인 것도 의도다. 키를 넣지 않은 환경에서 이 계층은 아무 일도 하지
않고, 설명 없는 결과가 나간다. `explain_analysis` 가 문장 없이 사유만 돌려줄 수
있는 설계가 여기까지 이어진다 - 설명은 있으면 좋고 없어도 되는 것이다.

**세는 것도 이 파일이다.** `explanation.py` 는 순수하게 두고, 요청 경로에서만
지나가는 이 자리에서 시도와 결과를 센다. 그래서 `evaluation/` 을 돌려도 운영
지표가 움직이지 않는다. 무엇을 남기고 무엇을 남기지 않는지는
`app/core/observability.py` 의 `ExplanationMetrics` 와 `outcomes.py` 에 적혀 있다 -
개수와 성패뿐이고, 사용자 원문·프롬프트·모델 출력은 한 글자도 지나가지 않는다.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from time import perf_counter

from app.clients.google_ai_studio import (
    GoogleAiStudioConfigurationError,
    build_google_ai_studio_provider,
)
from app.core.observability import explanation_metrics
from app.schemas.analysis import AnalyzeResponse
from app.services.llm.contract import LlmContract
from app.services.llm.explanation import (
    explain_analysis,
    fraud_explanation_contract,
    has_grounded_evidence,
)
from app.services.llm.outcomes import ExplanationOutcome
from app.services.llm.provider import LlmProvider, StubProvider

PROVIDER_SETTING = "FINSHIELD_LLM_PROVIDER"

# 모델은 여기에 박는다. 위 docstring 의 이유가 전부다. 이 문자열을 바꾸는 PR 은
# `evaluation/` 재실행을 동반해야 한다.
#
# 대체 모델이 `-lite` 인 것은 타협이 아니라 선택이다. 주 모델이 막혔을 때 필요한
# 것은 같은 품질이 아니라 **응답이 돌아오는 것**이고, 어차피 출력은
# `validate_explanation` 을 통과해야 한다. 두 모델이 사고(thinking) 여부에서
# 갈리는 것도 의도다 - 같은 성질의 모델 둘을 세워 두면 같은 이유로 함께 죽는다.
EXPLANATION_MODEL = "gemini-3.6-flash"
EXPLANATION_FALLBACK_MODEL = "gemini-3.1-flash-lite"

# 모델별 대기 시간. 하나로 묶지 않는 이유는 `fraud_explanation_contract` 에 적었다.
#
# 실측(2026-08-19, 라우트 전 경로 3회): 주 모델 7.7~8.2초, 대체 모델 1.6~1.9초.
# 여기 값은 각각 그 1.7배쯤이고, **최악의 경우 둘을 더한 만큼 기다린다**(20초).
# 이 합계가 이 계층에서 사용자가 볼 수 있는 최대 지연이며, 그동안에도 판정 화면은
# 이미 그려져 있다(`docs/34` 3절).
EXPLANATION_TIMEOUTS = {
    EXPLANATION_MODEL: 14.0,
    EXPLANATION_FALLBACK_MODEL: 6.0,
}

OFF = "off"

# `KNOWN_PROVIDERS` 와 다르다. 저쪽은 "계약이 가리킬 수 있는 프로바이더" 이고
# 여기는 "이 서비스가 실제로 조립할 수 있는 것" 이다. `google_vertex` 는 계약
# 어휘에는 있지만 구현이 없으므로 여기서는 못 고른다.
SUPPORTED_PROVIDERS = frozenset({OFF, "stub", "google_ai_studio"})


class LlmRuntimeConfigurationError(RuntimeError):
    """설정이 틀렸다. 요청 도중이 아니라 기동 시점에 터져야 한다.

    오타 하나로 설명이 조용히 사라지는 것이 최악이다 - 서비스는 정상으로 보이고
    화면에서 "왜 위험한지" 만 영영 비어 있게 된다.
    """


@dataclass(frozen=True)
class ExplanationRuntime:
    """프로바이더 하나와, 시도할 계약들의 순서."""

    provider: LlmProvider
    contracts: tuple[LlmContract, ...]


@dataclass(frozen=True)
class ExplanationResult:
    """설명과, 그것을 만든 모델, 그리고 왜 그 결과인지.

    `model` 은 `text` 가 있을 때만 채워진다. 어느 모델이 답했는지 모르는 설명은
    평가에서 쓸 수 없다.

    `outcome` 은 항상 채워진다. 성공이면 `OK`, 전부 실패했으면 **마지막 시도의
    사유**다. 마지막을 고르는 것은 임의가 아니다 - 대체 모델까지 갔다면 사용자가
    설명 없는 화면을 보게 된 직접적인 이유는 마지막 실패이고, 앞선 실패들은
    시도 지표에 이미 각각 남아 있다.
    """

    text: str | None
    model: str | None
    outcome: ExplanationOutcome


def _selected_provider(values: Mapping[str, str]) -> str:
    raw = values.get(PROVIDER_SETTING, "").strip().lower()
    if not raw:
        return OFF
    if raw not in SUPPORTED_PROVIDERS:
        raise LlmRuntimeConfigurationError(
            f"{PROVIDER_SETTING} must be one of {sorted(SUPPORTED_PROVIDERS)}"
        )
    return raw


def verify_llm_runtime_configuration(
    values: Mapping[str, str] | None = None,
) -> None:
    """기동 시점 검증.

    `main.py` 의 lifespan 에서 부른다. 여기서 실제로 조립까지 해 보는 이유는,
    키 파일이 없거나 읽히지 않는 상태를 첫 요청이 아니라 지금 알기 위해서다.
    """
    build_explanation_runtime(values)


def build_explanation_runtime(
    values: Mapping[str, str] | None = None,
) -> ExplanationRuntime | None:
    """프로바이더와 계약들을 조립한다. 꺼져 있으면 `None`.

    `None` 은 오류가 아니다. 호출하는 쪽은 설명 없이 동작해야 한다.
    """
    environ = values if values is not None else os.environ
    selected = _selected_provider(environ)
    if selected == OFF:
        return None

    if selected == "stub":
        return ExplanationRuntime(
            provider=StubProvider(),
            contracts=(fraud_explanation_contract(provider="stub", model="stub"),),
        )

    try:
        provider = build_google_ai_studio_provider(environ)
    except GoogleAiStudioConfigurationError as exc:
        # 키가 없는데 프로바이더를 켜 둔 상태다. 조용히 끄면 왜 설명이 안 나오는지
        # 아무도 못 찾는다. 켜 놓고 안 되는 것과 끈 것은 다른 상태다.
        raise LlmRuntimeConfigurationError(
            f"{PROVIDER_SETTING} is google_ai_studio but the API key is missing"
        ) from exc

    return ExplanationRuntime(
        provider=provider,
        contracts=tuple(
            fraud_explanation_contract(
                provider="google_ai_studio",
                model=model,
                timeout_seconds=EXPLANATION_TIMEOUTS[model],
            )
            for model in (EXPLANATION_MODEL, EXPLANATION_FALLBACK_MODEL)
        ),
    )


def explain_with_fallback(
    response: AnalyzeResponse,
    message: str,
    *,
    runtime: ExplanationRuntime,
) -> ExplanationResult:
    """계약 순서대로 시도하고, 처음 성공한 것을 돌려준다.

    **다음 모델로 넘어가는 판단은 여전히 사유를 보지 않는다.** 프로바이더가 죽은
    것이든 출력이 거부된 것이든 호출하는 쪽에서 보면 둘 다 "설명이 없다" 이고,
    어느 쪽이든 다음 모델을 시도할 가치가 있다. 사유로 분기하면 어떤 실패는 대체
    모델을 안 부르게 되고, 그 규칙이 맞는지는 지금 재 볼 숫자가 없다. 사유는
    **세기 위해** 들고 다니는 것이고, 그것으로 흐름을 바꾸는 것은 숫자가 쌓인
    다음 일이다. 대신 비용이 두 배로 나가는 경우가 생기므로 계약 목록은 짧게
    유지한다.

    **세는 자리가 여기인 이유.** `explain_analysis` 는 프로바이더와 계약을 주입받는
    순수한 함수이고, 평가 스크립트도 그것을 직접 부른다. 거기에 카운터를 두면
    `evaluation/` 을 한 번 돌릴 때마다 운영 지표가 수십 건씩 오염된다. 조립하는
    자리는 요청 경로에만 있다.
    """
    # 근거가 없으면 아무 모델도 부르지 않는다. 시도가 0 이므로 `observe_attempt`
    # 도 부르지 않는다 — 일어나지 않은 시도를 세면 대체 모델 사용률과 지연 분포가
    # 전부 틀어진다.
    #
    # 여기가 루프 **앞**인 것이 요점이다. 근거를 보고 분기하지, 실패 사유를 보고
    # 분기하지 않는다. 사유로 분기하기 시작하면 어떤 실패에서 대체 모델을 부를지
    # 말지가 코드 곳곳에 흩어지고, 그 규칙이 맞는지는 잴 숫자가 없다.
    if not has_grounded_evidence(response):
        outcome = ExplanationOutcome.NOT_ASKED_NO_EVIDENCE
        explanation_metrics.observe_result(outcome=outcome.value, attempts=0)
        return ExplanationResult(text=None, model=None, outcome=outcome)

    attempts = 0
    outcome = ExplanationOutcome.UNSPECIFIED
    for contract in runtime.contracts:
        attempts += 1
        started_at = perf_counter()
        attempt = explain_analysis(
            response,
            message,
            provider=runtime.provider,
            contract=contract,
        )
        duration_ms = (perf_counter() - started_at) * 1000
        outcome = attempt.outcome
        explanation_metrics.observe_attempt(
            model=contract.model,
            outcome=attempt.outcome.value,
            attempt=attempts,
            duration_ms=duration_ms,
        )
        if attempt.text is not None:
            explanation_metrics.observe_result(
                outcome=attempt.outcome.value, attempts=attempts
            )
            return ExplanationResult(
                text=attempt.text, model=contract.model, outcome=attempt.outcome
            )

    # 계약 목록이 비어 있으면 시도가 없고 사유도 없다. `unspecified` 가 그 자리다 -
    # 조립이 그런 런타임을 만들지는 않지만, 여기서 값을 지어내지는 않는다.
    explanation_metrics.observe_result(outcome=outcome.value, attempts=attempts)
    return ExplanationResult(text=None, model=None, outcome=outcome)


_runtime: ExplanationRuntime | None = None
_runtime_loaded = False


def explanation_runtime() -> ExplanationRuntime | None:
    """조립 결과를 프로세스당 한 번만 만든다.

    프로바이더가 키 파일을 읽으므로, 요청마다 조립하면 요청마다 디스크를 친다.
    8초짜리 네트워크 호출 옆에서는 사소하지만, 사소한 이유로 파일을 자주 여는
    코드는 나중에 그 파일이 커졌을 때 문제가 된다.
    """
    global _runtime, _runtime_loaded
    if not _runtime_loaded:
        _runtime = build_explanation_runtime()
        _runtime_loaded = True
    return _runtime


def reset_explanation_runtime() -> None:
    """테스트가 환경을 바꾼 뒤 부른다."""
    global _runtime, _runtime_loaded
    _runtime = None
    _runtime_loaded = False
