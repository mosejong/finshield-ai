"""설명 계층을 코퍼스 하나에 통째로 태우고, 시도마다 무슨 일이 났는지 적는다.

`docs/34` 9절이 두 번 같은 말을 적어 뒀다 — **분모가 0 이다.** 2026-08-24 에
`outcomes.py` 의 닫힌 어휘가 들어갔고, `observability.py` 의 카운터가 붙었고,
`REJECTION_OUTCOMES` 와 `BLOCKED_OUTCOMES` 까지 미리 정의돼 있었다. 그래도 숫자가
없었던 이유는 계측이 없어서가 아니라 **아무도 유료로 한 번 돌리지 않아서**다.
이 파일이 그 한 번을 파일로 남기는 자리다.

열세 회차 동안 잰 것은 전부 탐지와 행동이다. 사용자가 화면에서 실제로 읽는
문장은 한 번도 채점되지 않았다.

## 무엇을 재는가

`validate_explanation` 이 이미 결정론적으로 잡는 것들이다. 여기서 새로 판단하는
것은 하나도 없다 — 검증기가 버린 것을 **세기만** 한다.

- **근거 이탈률.** 근거에 없던 연락처, 설명에 있을 이유가 없는 URL, 주민등록번호
  형태, 그리고 판정이 `medium` 이상인데 안심시키는 문장. `REJECTION_OUTCOMES`.
- **안전 필터 차단율.** 우리 요청이 거부된 것(`prompt_blocked`)과 모델이 스스로
  멈춘 것(`safety_blocked`)을 나눠 센다. 9절이 걱정한 것은 앞쪽이었다.
- **시도별 소요시간.** 모델마다 따로 낸다. `runtime.py` 의 예산(주 14초 / 대체
  6초)이 실측에 맞는지는 이 표로만 확인된다.
- **대체 모델 사용률.** 주 모델이 얼마나 자주 못 답하는가.

## 왜 LLM 판정자를 쓰지 않는가

`llm_judge.py` 는 모델에게 사기 여부를 묻는다. 여기서 물을 것은 "이 문장이 근거를
벗어났는가" 인데, 그것을 모델에게 물으면 **지어내는 쪽과 채점하는 쪽이 같은 성질**
이 된다. 모델이 없는 신고번호를 만들어 내는 실패를, 같은 계열의 모델이 알아볼
것이라는 근거가 없다. 그래서 채점은 전부 정규식이고, 그 정규식은 제품이 실제로
쓰는 바로 그 함수다. **재는 자와 막는 자가 같아야 이 숫자가 제품을 설명한다.**

한계도 같이 온다. 이 파일은 문장이 **읽을 만한가**를 재지 않는다. 사회초년생이
이해할 수 있는 문장인지, 겁을 주는지, 행동을 정확히 가리키는지는 여기 없다.
`validate_explanation` 의 docstring 이 스스로 적어 둔 것과 같은 한계다 — 이것은
사실 검증기가 아니다.

## 재현

`explain_with_fallback` 을 부르지 않고 계약 순서를 여기서 돈다. 그쪽은 Prometheus
카운터를 건드리는 자리이고, `runtime.py` 가 그 카운터를 `explanation.py` 가 아니라
자기에게 둔 이유가 **평가가 운영 지표를 오염시키지 않게** 하기 위해서였다. 같은
규율을 반대편에서도 지킨다.

대신 프로바이더·모델·타임아웃·순서를 하나도 여기서 정하지 않는다. 전부
`build_explanation_runtime()` 이 만든 `ExplanationRuntime` 에서 온다. 루프만
우리 것이고, 그 루프가 하는 일은 운영 루프가 Prometheus 로 보내는 것과 같은
정보를 파일로 보내는 것뿐이다. 두 루프가 어긋나지 않는지는 테스트가 본다.

결과 파일에는 **설명 문장이 들어가지 않는다.** 길이만 남긴다. 골든셋이 합성
문장이라 개인정보 문제는 없지만, 모델 출력 본문을 저장소에 넣기 시작하면 다음에
실제 사용자 문장으로 같은 것을 돌릴 때 그 규칙이 이미 무너져 있다
(`adr/0006-privacy-safe-observability.md`).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from pathlib import Path
from time import perf_counter

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.analysis import AnalyzeResponse
from app.services.llm.contract import LlmContract
from app.services.llm.explanation import explain_analysis
from app.services.llm.outcomes import (
    BLOCKED_OUTCOMES,
    REJECTION_OUTCOMES,
    ExplanationOutcome,
)
from app.services.llm.provider import LlmProvider
from evaluation.fraud_golden import CASE_ID_PATTERN

#: 2026-08-25 에 잰 두 셋. 판정 결과와 마찬가지로 셋마다 파일을 나눈다 — sha256 이
#: 다르고, 한 파일에 섞으면 어느 셋의 숫자인지 구분할 수 없다.
#:
#: **이름에 지시문 판이 들어간다.** 셋이 같아도 프롬프트가 다르면 다른 숫자다.
#: 프롬프트 v2 를 만든 날 이 파일들을 덮어썼다면, `docs/34` 13절이 인용하는 값이
#: 조용히 사라지고 문서가 없는 숫자를 가리켰을 것이다.
_RESULTS = Path(__file__).with_name("results")

#: 배포된 지시문으로 잰 것. 벤치마크 보고서가 쓰는 값이다.
EXPLANATION_PROBE_V1_2_PATH = (
    _RESULTS / "explanation-probe-fraud-holdout-v1.2-prompt-v2.json"
)
EXPLANATION_PROBE_V1_3_PATH = (
    _RESULTS / "explanation-probe-fraud-holdout-v1.3-prompt-v2.json"
)

#: 같은 지시문·같은 셋을 한 번 더 잰 것. **표가 실행마다 얼마나 흔들리는지 모르면
#: 두 지시문의 차이가 개선인지 잡음인지 말할 수 없다.** temperature 0.0 은 결정론을
#: 보장하지 않고, 여기서 세는 값들은 한 자릿수다 — 1 과 3 의 차이에 이야기를 붙이기
#: 전에 같은 조건이 얼마나 움직이는지를 먼저 봐야 한다.
EXPLANATION_PROBE_V1_2_REPEAT_PATH = (
    _RESULTS / "explanation-probe-fraud-holdout-v1.2-prompt-v2-repeat.json"
)
EXPLANATION_PROBE_V1_3_REPEAT_PATH = (
    _RESULTS / "explanation-probe-fraud-holdout-v1.3-prompt-v2-repeat.json"
)

#: 직전 지시문으로 잰 것. 비교 대상으로만 남는다 — 이 숫자가 프롬프트 v2 를 부른
#: 근거이므로, 고친 뒤의 값만 남기면 무엇이 나아졌는지 아무도 확인할 수 없다.
EXPLANATION_PROBE_V1_2_BASELINE_PATH = (
    _RESULTS / "explanation-probe-fraud-holdout-v1.2-prompt-v1.json"
)
EXPLANATION_PROBE_V1_3_BASELINE_PATH = (
    _RESULTS / "explanation-probe-fraud-holdout-v1.3-prompt-v1.json"
)

#: 배포된 지시문에서 나온 실행 전부. 보고서가 쓸 수 있는 것은 이쪽뿐이다.
DEPLOYED_PROMPT_RUNS = (
    EXPLANATION_PROBE_V1_2_PATH,
    EXPLANATION_PROBE_V1_2_REPEAT_PATH,
    EXPLANATION_PROBE_V1_3_PATH,
    EXPLANATION_PROBE_V1_3_REPEAT_PATH,
)

#: 직전 지시문에서 나온 실행. 문서가 인용하는 값이며 보고서는 쓰지 않는다.
BASELINE_PROMPT_RUNS = (
    EXPLANATION_PROBE_V1_2_BASELINE_PATH,
    EXPLANATION_PROBE_V1_3_BASELINE_PATH,
)


class ProbeAttempt(BaseModel):
    """계약 하나에 대한 시도 하나.

    `explain_with_fallback` 이 요청마다 `observe_attempt` 로 보내는 것과 같은 세 값
    이다. 여기서는 그것이 파일에 남는다.
    """

    model_config = ConfigDict(frozen=True)

    model: str
    outcome: ExplanationOutcome
    duration_ms: float


class ProbeCase(BaseModel):
    """사례 하나의 결과.

    `risk_level` 을 같이 적는 이유는 `rejected_contradicts_verdict` 검사가
    `medium` 이상에서만 돌기 때문이다. 그 검사의 분모는 전체 건수가 아니라
    **검사가 실제로 돈 건수**이고, 등급을 안 적어 두면 그 분모를 나중에 계산할
    수 없다.
    """

    model_config = ConfigDict(frozen=True)

    case_id: str = Field(pattern=CASE_ID_PATTERN)
    risk_level: str
    attempts: tuple[ProbeAttempt, ...]
    #: 마지막 시도의 사유. 성공이면 `ok` 다. `ExplanationResult.outcome` 과 같은 규칙.
    outcome: ExplanationOutcome
    #: 성공한 모델. 실패하면 `None` — 어느 모델이 답했는지 모르는 설명은 쓸 수 없다.
    model: str | None = None
    #: 통과한 문장의 길이. 본문은 남기지 않는다.
    chars: int | None = None

    @property
    def explained(self) -> bool:
        return self.outcome is ExplanationOutcome.OK


class ExplanationProbeRun(BaseModel):
    """한 번의 실행 전체.

    `contracts` 에 모델 순서를 적어 두는 이유는, 대체 모델 사용률이라는 숫자가
    **순서가 무엇이었는지 모르면 뜻이 없기** 때문이다.
    """

    model_config = ConfigDict(frozen=True)

    probed_at: str
    dataset_id: str
    dataset_sha256: str
    provider: str
    contracts: tuple[str, ...]
    prompt_id: str
    prompt_sha256: str
    temperature: float
    max_chars: int
    cases: tuple[ProbeCase, ...]


def probe_case(
    case_id: str,
    response: AnalyzeResponse,
    message: str,
    *,
    provider: LlmProvider,
    contracts: tuple[LlmContract, ...],
    clock: Callable[[], float] = perf_counter,
) -> ProbeCase:
    """계약 순서대로 시도하고, 처음 성공한 곳에서 멈춘다.

    멈추는 규칙이 `explain_with_fallback` 과 같아야 한다. 여기서 전부 시도해 버리면
    대체 모델 호출 수가 운영보다 부풀고, 그 숫자로 비용을 예측할 수 없게 된다.
    """
    attempts: list[ProbeAttempt] = []
    outcome = ExplanationOutcome.UNSPECIFIED
    for contract in contracts:
        started_at = clock()
        attempt = explain_analysis(
            response, message, provider=provider, contract=contract
        )
        duration_ms = (clock() - started_at) * 1000
        outcome = attempt.outcome
        attempts.append(
            ProbeAttempt(
                model=contract.model, outcome=outcome, duration_ms=duration_ms
            )
        )
        if attempt.text is not None:
            return ProbeCase(
                case_id=case_id,
                risk_level=response.risk_level,
                attempts=tuple(attempts),
                outcome=outcome,
                model=contract.model,
                chars=len(attempt.text),
            )

    return ProbeCase(
        case_id=case_id,
        risk_level=response.risk_level,
        attempts=tuple(attempts),
        outcome=outcome,
    )


def _percentile(values: list[float], fraction: float) -> float | None:
    """`fraud_benchmark` 와 같은 규칙 — 분모가 0 이면 `None` 이다.

    0 을 적으면 "재지 않았다" 가 "0 밀리초였다" 로 읽힌다. 이 파일의 존재 이유가
    분모 0 을 없애는 것인데, 그 자리에 0 을 써 넣으면 같은 함정을 한 겹 안쪽에
    다시 파는 것이다.
    """
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(fraction * len(ordered)))
    return round(ordered[index], 1)


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def summarize(run: ExplanationProbeRun) -> dict[str, object]:
    """`docs/34` 9절이 요구한 값들을 계산한다.

    시도와 결과를 나눠 세는 것은 `runtime.py` 의 결정 그대로다. 시도만 세면 "설명이
    결국 비었다" 를, 결과만 세면 "주 모델이 얼마나 막히는가" 를 계산할 수 없다.
    """
    cases = list(run.cases)
    total = len(cases)
    attempts = [attempt for case in cases for attempt in case.attempts]

    explained = sum(1 for case in cases if case.explained)
    fell_back = sum(1 for case in cases if len(case.attempts) > 1)
    # 대체 모델까지 갔는데도 못 낸 경우. 여기가 사용자에게 빈 화면이 나간 건수다.
    unexplained = [case for case in cases if not case.explained]

    per_model: dict[str, dict[str, object]] = {}
    for model in run.contracts:
        model_attempts = [attempt for attempt in attempts if attempt.model == model]
        durations = [attempt.duration_ms for attempt in model_attempts]
        per_model[model] = {
            "attempts": len(model_attempts),
            "ok": sum(
                1
                for attempt in model_attempts
                if attempt.outcome is ExplanationOutcome.OK
            ),
            "outcomes": dict(
                sorted(Counter(a.outcome.value for a in model_attempts).items())
            ),
            "p50_ms": _percentile(durations, 0.5),
            "p95_ms": _percentile(durations, 0.95),
        }

    # `rejected_contradicts_verdict` 의 분모는 전체가 아니다. `low` 에서는 그 검사가
    # 아예 돌지 않으므로, 전체로 나누면 검사가 실제보다 순한 것처럼 보인다.
    verdict_checked = [
        attempt
        for case in cases
        if case.risk_level in {"medium", "high"}
        for attempt in case.attempts
    ]

    accepted_chars = [case.chars for case in cases if case.chars is not None]

    return {
        "cases": total,
        "attempts": len(attempts),
        "explained": explained,
        "explained_rate": _rate(explained, total),
        "fell_back_to_second_model": fell_back,
        "fallback_rate": _rate(fell_back, total),
        "unexplained": [
            {"case_id": case.case_id, "outcome": case.outcome.value}
            for case in unexplained
        ],
        # 근거 이탈률. 분모는 시도다 — 모델이 계약을 어긴 비율이지, 사용자가 설명을
        # 못 본 비율이 아니다. 뒤쪽은 `explained_rate` 가 말한다.
        "grounding_departures": sum(
            1 for attempt in attempts if attempt.outcome in REJECTION_OUTCOMES
        ),
        "grounding_departure_rate": _rate(
            sum(1 for attempt in attempts if attempt.outcome in REJECTION_OUTCOMES),
            len(attempts),
        ),
        "invented_contacts": sum(
            1
            for attempt in attempts
            if attempt.outcome is ExplanationOutcome.REJECTED_INVENTED_CONTACT
        ),
        "contradicted_verdict": sum(
            1
            for attempt in verdict_checked
            if attempt.outcome is ExplanationOutcome.REJECTED_CONTRADICTS_VERDICT
        ),
        "verdict_check_ran_on_attempts": len(verdict_checked),
        # 안전 필터 차단율. 요청이 막힌 것과 응답이 막힌 것을 나눠 둔다.
        "safety_blocks": sum(
            1 for attempt in attempts if attempt.outcome in BLOCKED_OUTCOMES
        ),
        "safety_block_rate": _rate(
            sum(1 for attempt in attempts if attempt.outcome in BLOCKED_OUTCOMES),
            len(attempts),
        ),
        "prompt_blocked": sum(
            1
            for attempt in attempts
            if attempt.outcome is ExplanationOutcome.PROMPT_BLOCKED
        ),
        "safety_blocked": sum(
            1
            for attempt in attempts
            if attempt.outcome is ExplanationOutcome.SAFETY_BLOCKED
        ),
        "attempt_outcomes": dict(
            sorted(Counter(attempt.outcome.value for attempt in attempts).items())
        ),
        "result_outcomes": dict(
            sorted(Counter(case.outcome.value for case in cases).items())
        ),
        "per_model": per_model,
        "explanation_chars": {
            "limit": run.max_chars,
            "p50": _percentile([float(c) for c in accepted_chars], 0.5),
            "p95": _percentile([float(c) for c in accepted_chars], 0.95),
            "max": max(accepted_chars) if accepted_chars else None,
        },
    }
