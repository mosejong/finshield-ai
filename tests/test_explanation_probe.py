"""설명 계층을 코퍼스에 태워 얻은 숫자가 제품을 설명하는지 검사한다.

`test_llm_explanation_outcomes.py` 는 **셀 수 있는가**를 지킨다. 이 파일은 그다음
질문인 **센 것이 배포된 것과 같은가**를 지킨다. 둘은 다른 검사다 - 계측이 완벽해도
평가 스크립트가 자기만의 모델 순서를 들고 있으면, 나온 표는 아무 데도 없는 시스템의
표가 된다.

여기서 고정하는 것은 넷이다.

1. **조립을 평가가 다시 하지 않는다.** 프로바이더·모델·타임아웃·순서는 전부
   `build_explanation_runtime()` 에서 온다.
2. **멈추는 규칙이 같다.** 첫 성공에서 멈춘다. 전부 시도해 버리면 대체 모델 호출
   수가 운영보다 부풀고, 그 숫자로 비용을 예측할 수 없다.
3. **평가는 운영 지표를 건드리지 않는다.** `runtime.py` 가 카운터를 순수 계층이
   아니라 조립 계층에 둔 이유를, 반대편에서도 지킨다.
4. **커밋된 결과 파일이 자기가 잰 셋을 정확히 가리킨다.** 판정 파일에서 이미 한 번
   깨졌던 자리다(`dataset_id` 가 개발셋으로 박혀 있었다).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.observability import explanation_metrics
from app.schemas.analysis import AnalyzeRequest, AnalyzeResponse, UserState
from app.services.fraud_analysis import analyze_fraud
from app.services.llm.contract import LlmContract
from app.services.llm.outcomes import ExplanationOutcome
from app.services.llm.provider import LlmUnavailable
from app.services.llm.runtime import (
    EXPLANATION_FALLBACK_MODEL,
    EXPLANATION_MODEL,
    build_explanation_runtime,
)
from evaluation.explanation_probe import (
    EXPLANATION_PROBE_V1_2_PATH,
    EXPLANATION_PROBE_V1_3_PATH,
    ExplanationProbeRun,
    probe_case,
    summarize,
)
from evaluation.fraud_benchmark import normalized_dataset_sha256
from evaluation.fraud_golden import (
    HOLDOUT_V1_2_PATH,
    HOLDOUT_V1_3_PATH,
    load_golden_cases,
)

API_KEY = "AIzaSy" + "0" * 33

SUSPICIOUS_TEXT = (
    "[금융감독원] 귀하의 계좌가 대포통장으로 이용되었습니다. "
    "안전계좌로 즉시 이체하지 않으면 형사처벌 대상입니다."
)

# 등급이 `low` 로 나오는 문장. "이 문자는 안전합니다" 가 여기서는 맞는 말이므로
# `contradicts_verdict` 가 아예 돌지 않는다.
HARMLESS_TEXT = "이번 달 관리비 고지서가 발송되었습니다."


@pytest.fixture(autouse=True)
def _clean_metrics():
    explanation_metrics.reset()
    yield
    explanation_metrics.reset()


@pytest.fixture
def verdict() -> AnalyzeResponse:
    return analyze_fraud(
        AnalyzeRequest(text=SUSPICIOUS_TEXT, state=UserState.SHARED_ACCOUNT_ACCESS)
    )


def _deployed_contracts() -> tuple[LlmContract, ...]:
    runtime = build_explanation_runtime(
        {"FINSHIELD_LLM_PROVIDER": "google_ai_studio", "GEMINI_API_KEY": API_KEY}
    )
    assert runtime is not None
    return runtime.contracts


class _ScriptedProvider:
    """모델별로 문장을 돌려주거나 지정한 사유로 실패한다."""

    def __init__(self, answers: dict[str, str | ExplanationOutcome]) -> None:
        self._answers = answers
        self.asked: list[str] = []

    @property
    def name(self) -> str:
        return "google_ai_studio"

    def generate(self, *, contract: LlmContract, prompt: str) -> str:
        self.asked.append(contract.model)
        answer = self._answers.get(contract.model, ExplanationOutcome.TIMEOUT)
        if isinstance(answer, ExplanationOutcome):
            raise LlmUnavailable("scripted failure", outcome=answer)
        return answer


# --- 조립을 평가가 다시 하지 않는다 ---------------------------------------


def test_the_probe_asks_the_models_the_deployment_actually_uses() -> None:
    """모델 이름과 순서를 스크립트가 정하지 않는다.

    평가가 자기 목록을 들고 있으면, 배포가 모델을 바꿔도 표는 옛 모델의 숫자를
    계속 보여 준다. `runtime.py` 가 모델을 환경변수가 아니라 코드에 박아 둔 이유가
    그것인데, 평가가 그 결정을 우회하면 같은 구멍이 다시 생긴다.
    """
    contracts = _deployed_contracts()
    provider = _ScriptedProvider({EXPLANATION_MODEL: "정상 절차에 없는 요구입니다."})

    probe_case(
        "fh-1101",
        analyze_fraud(AnalyzeRequest(text=SUSPICIOUS_TEXT)),
        SUSPICIOUS_TEXT,
        provider=provider,
        contracts=contracts,
    )

    assert [contract.model for contract in contracts] == [
        EXPLANATION_MODEL,
        EXPLANATION_FALLBACK_MODEL,
    ]
    assert provider.asked == [EXPLANATION_MODEL]


def test_the_probe_stops_at_the_first_sentence_like_the_request_path_does(
    verdict: AnalyzeResponse,
) -> None:
    """첫 성공에서 멈춘다.

    `explain_with_fallback` 과 같은 규칙이어야 한다. 여기서 전부 시도하면 대체 모델
    호출 수가 운영보다 부풀고, 그 숫자로 비용을 예측할 수 없게 된다.
    """
    provider = _ScriptedProvider(
        {
            EXPLANATION_MODEL: ExplanationOutcome.PROMPT_BLOCKED,
            EXPLANATION_FALLBACK_MODEL: "정상 절차에 없는 요구입니다.",
        }
    )

    case = probe_case(
        "fh-1101",
        verdict,
        SUSPICIOUS_TEXT,
        provider=provider,
        contracts=_deployed_contracts(),
    )

    assert provider.asked == [EXPLANATION_MODEL, EXPLANATION_FALLBACK_MODEL]
    assert [attempt.outcome for attempt in case.attempts] == [
        ExplanationOutcome.PROMPT_BLOCKED,
        ExplanationOutcome.OK,
    ]
    # 실패한 시도도 남는다. 마지막만 남기면 "주 모델이 얼마나 막히는가" 가 사라진다.
    assert case.outcome is ExplanationOutcome.OK
    assert case.model == EXPLANATION_FALLBACK_MODEL
    assert case.chars == len("정상 절차에 없는 요구입니다.")


def test_a_case_nobody_could_explain_keeps_the_last_reason(
    verdict: AnalyzeResponse,
) -> None:
    """전부 실패하면 남는 것은 마지막 사유다. `ExplanationResult` 와 같은 규칙."""
    case = probe_case(
        "fh-1101",
        verdict,
        SUSPICIOUS_TEXT,
        provider=_ScriptedProvider(
            {
                EXPLANATION_MODEL: ExplanationOutcome.SAFETY_BLOCKED,
                EXPLANATION_FALLBACK_MODEL: ExplanationOutcome.HTTP_ERROR,
            }
        ),
        contracts=_deployed_contracts(),
    )

    assert case.outcome is ExplanationOutcome.HTTP_ERROR
    assert case.model is None
    assert case.chars is None
    assert len(case.attempts) == 2


def test_the_probe_does_not_move_the_operational_counters(
    verdict: AnalyzeResponse,
) -> None:
    """평가를 돌려도 운영 지표가 움직이지 않는다.

    `runtime.py` 가 카운터를 `explanation.py` 가 아니라 자기에게 둔 이유의 반대편
    이다. 여기서 `explain_with_fallback` 을 부르면 벤치마크 한 번에 운영 지표가
    수백 건씩 오염되고, 그 지표로는 경보를 걸 수 없다.
    """
    for _ in range(3):
        probe_case(
            "fh-1101",
            verdict,
            SUSPICIOUS_TEXT,
            provider=_ScriptedProvider({EXPLANATION_MODEL: "정상 절차에 없는 요구입니다."}),
            contracts=_deployed_contracts(),
        )

    exposed = explanation_metrics.prometheus_text()
    assert "finshield_llm_explanation_attempts_total{" not in exposed
    assert "finshield_llm_explanation_results_total{" not in exposed


# --- 물어본 숫자가 실제로 나오는가 ----------------------------------------


def _run_over(
    answers: list[dict[str, str | ExplanationOutcome]],
    *,
    text: str = SUSPICIOUS_TEXT,
    state: UserState = UserState.SHARED_ACCOUNT_ACCESS,
) -> ExplanationProbeRun:
    contracts = _deployed_contracts()
    response = analyze_fraud(AnalyzeRequest(text=text, state=state))
    cases = [
        probe_case(
            f"fh-{1100 + index}",
            response,
            text,
            provider=_ScriptedProvider(script),
            contracts=contracts,
        )
        for index, script in enumerate(answers)
    ]
    return ExplanationProbeRun(
        probed_at="2026-08-25T00:00:00+00:00",
        dataset_id="unit",
        dataset_sha256="0" * 64,
        provider="google_ai_studio",
        contracts=tuple(contract.model for contract in contracts),
        prompt_id=contracts[0].prompt_id,
        prompt_sha256=contracts[0].prompt_sha256,
        temperature=contracts[0].temperature,
        max_chars=600,
        cases=tuple(cases),
    )


def test_the_numbers_docs_34_asked_for_come_out() -> None:
    """차단율과 근거 이탈률이 실제로 계산된다.

    계측을 넣고도 숫자를 못 뽑는 경우가 있고, 그러면 넣지 않은 것과 같다. 여기서는
    주 모델 넷 중 하나가 안전 필터에 막히고 하나가 없는 연락처를 지어내는 상황을
    만든다.
    """
    sentence = "정상 절차에 없는 요구입니다."
    report = summarize(
        _run_over(
            [
                {EXPLANATION_MODEL: sentence},
                {EXPLANATION_MODEL: sentence},
                {
                    EXPLANATION_MODEL: ExplanationOutcome.PROMPT_BLOCKED,
                    EXPLANATION_FALLBACK_MODEL: sentence,
                },
                # 근거에 없던 신고번호. 이 서비스가 낼 수 있는 가장 나쁜 출력이다.
                {
                    EXPLANATION_MODEL: "안내는 02-1234-5678 로 확인하십시오.",
                    EXPLANATION_FALLBACK_MODEL: sentence,
                },
            ]
        )
    )

    assert report["cases"] == 4
    assert report["attempts"] == 6
    assert report["explained"] == 4
    assert report["explained_rate"] == 1.0
    assert report["fell_back_to_second_model"] == 2
    assert report["fallback_rate"] == 0.5

    # 분모가 사례가 아니라 시도다. 모델이 계약을 어긴 비율이지, 사용자가 설명을
    # 못 본 비율이 아니다.
    assert report["grounding_departures"] == 1
    assert report["grounding_departure_rate"] == round(1 / 6, 4)
    assert report["invented_contacts"] == 1

    assert report["safety_blocks"] == 1
    assert report["prompt_blocked"] == 1
    assert report["safety_blocked"] == 0
    assert report["safety_block_rate"] == round(1 / 6, 4)

    assert report["per_model"][EXPLANATION_MODEL]["attempts"] == 4
    assert report["per_model"][EXPLANATION_FALLBACK_MODEL]["attempts"] == 2


def test_the_verdict_check_is_not_divided_by_cases_it_never_ran_on() -> None:
    """`rejected_contradicts_verdict` 의 분모는 `medium` 이상뿐이다.

    `low` 에서는 그 검사가 아예 돌지 않는다("위험하지 않습니다" 가 맞는 말이다).
    전체 건수로 나누면 검사가 실제보다 순한 것처럼 보이고, 그 비율로는 프롬프트를
    고칠지 말지 정할 수 없다.
    """
    reassuring = "이 문자는 안전합니다."
    high = summarize(_run_over([{EXPLANATION_MODEL: reassuring}] * 2))
    low = summarize(
        _run_over(
            [{EXPLANATION_MODEL: reassuring}] * 2,
            text=HARMLESS_TEXT,
            state=UserState.RECEIVED_ONLY,
        )
    )

    assert high["verdict_check_ran_on_attempts"] == 4
    assert high["contradicted_verdict"] == 2
    # 같은 문장인데 등급이 `low` 라 검사가 돌지 않았다. 분모도 0 이다.
    assert low["verdict_check_ran_on_attempts"] == 0
    assert low["contradicted_verdict"] == 0


def test_an_unmeasured_rate_is_none_not_zero() -> None:
    """분모가 0 이면 `None` 이다.

    이 파일의 존재 이유가 분모 0 을 없애는 것인데, 그 자리에 0 을 써 넣으면
    "재지 않았다" 가 "0 이었다" 로 읽힌다. `fraud_benchmark` 가 같은 규칙을 쓴다.
    """
    report = summarize(_run_over([{EXPLANATION_MODEL: "정상 절차에 없는 요구입니다."}]))

    assert report["per_model"][EXPLANATION_FALLBACK_MODEL]["attempts"] == 0
    assert report["per_model"][EXPLANATION_FALLBACK_MODEL]["p50_ms"] is None
    assert report["per_model"][EXPLANATION_FALLBACK_MODEL]["p95_ms"] is None


# --- 커밋된 결과가 자기가 잰 셋을 가리키는가 ------------------------------


@pytest.mark.parametrize(
    ("path", "dataset"),
    [
        (EXPLANATION_PROBE_V1_2_PATH, HOLDOUT_V1_2_PATH),
        (EXPLANATION_PROBE_V1_3_PATH, HOLDOUT_V1_3_PATH),
    ],
)
def test_probe_runs_name_the_dataset_they_actually_probed(
    path: Path, dataset: Path
) -> None:
    """이름·sha256·사례 집합이 전부 같은 셋을 가리킨다.

    판정 파일에서 이미 한 번 깨졌던 자리다 - `dataset_id` 가 개발셋으로 박혀 있어서,
    홀드아웃을 잰 파일이 자기를 개발셋이라고 말했다. sha256 이 막아 주지만 사람이
    먼저 읽는 것은 이름이다.
    """
    run = ExplanationProbeRun.model_validate_json(path.read_text(encoding="utf-8"))
    cases = load_golden_cases(dataset)

    assert run.dataset_id == dataset.stem
    assert run.dataset_sha256 == normalized_dataset_sha256(cases)
    assert {case.case_id for case in run.cases} == {case.case_id for case in cases}
    # 배포된 모델 순서로 잰 것이어야 이 숫자가 제품을 설명한다.
    assert run.contracts == (EXPLANATION_MODEL, EXPLANATION_FALLBACK_MODEL)


@pytest.mark.parametrize(
    "path", [EXPLANATION_PROBE_V1_2_PATH, EXPLANATION_PROBE_V1_3_PATH]
)
def test_no_explanation_text_was_committed(path: Path) -> None:
    """결과 파일에 모델이 만든 문장이 없다.

    골든셋은 합성 문장이라 개인정보 문제가 없지만, 모델 출력 본문을 저장소에 넣기
    시작하면 실제 사용자 문장으로 같은 것을 돌릴 때 그 규칙이 이미 무너져 있다.
    길이만 남긴다.
    """
    stored = json.loads(path.read_text(encoding="utf-8"))

    assert set(stored) == set(ExplanationProbeRun.model_fields)
    for case in stored["cases"]:
        assert set(case) <= {
            "case_id",
            "risk_level",
            "attempts",
            "outcome",
            "model",
            "chars",
        }
        for attempt in case["attempts"]:
            assert set(attempt) == {"model", "outcome", "duration_ms"}

    # 어휘 밖의 문자열이 하나도 없어야 한다. 사유는 닫힌 목록이고, 문장은 길이로만
    # 남는다.
    vocabulary = {outcome.value for outcome in ExplanationOutcome}
    for case in stored["cases"]:
        assert case["outcome"] in vocabulary
        assert all(attempt["outcome"] in vocabulary for attempt in case["attempts"])
