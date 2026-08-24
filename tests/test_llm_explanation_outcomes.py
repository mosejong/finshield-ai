"""설명이 없는 이유를 셀 수 있는지 검사한다.

`docs/34` 9절이 두 줄을 적어 뒀다. **안전 필터 차단율을 모른다**, 그리고 **이 계층은
아무것도 기록하지 않는다.** 두 줄은 같은 줄이었다 - 실패가 전부 `None` 하나로
접혔으니 셀 것이 없었다.

이 파일이 지키는 것은 넷이다.

1. **사유가 갈린다.** 프로바이더가 낼 수 있는 실패마다 다른 이름이 붙는다. 표가
   비어 있으면 계측이 있어도 숫자는 못 읽는다.
2. **어휘가 닫혀 있다.** 응답 본문에서 온 문자열은 로그에도 지표에도 나가지
   않는다. 새 `finishReason` 이 와도 새 라벨이 생기지 않는다.
3. **개인정보가 지나가지 않는다.** `ADR 0006` 이 요구하는 형태 - 개수와 성패뿐이다.
4. **세는 자리가 하나다.** 순수한 `explain_analysis` 는 세지 않고, 조립하는
   `explain_with_fallback` 만 센다. 그래야 `evaluation/` 을 돌려도 운영 지표가
   움직이지 않는다.

마지막으로 **차단율이 실제로 계산되는지**를 검사한다. 계측을 넣고도 숫자를 못 뽑는
경우가 있고, 그러면 넣지 않은 것과 같다.
"""

from __future__ import annotations

import ast
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.clients.google_ai_studio import GoogleAiStudioProvider
from app.core.observability import explanation_metrics
from app.main import app
from app.schemas.analysis import AnalyzeRequest, AnalyzeResponse, UserState
from app.services.fraud_analysis import analyze_fraud
from app.services.llm import (
    BLOCKED_OUTCOMES,
    ExplanationAttempt,
    ExplanationOutcome,
    LlmContract,
    LlmUnavailable,
    StubProvider,
    explain_analysis,
)
from app.services.llm.explanation import fraud_explanation_contract
from app.services.llm.runtime import (
    EXPLANATION_FALLBACK_MODEL,
    EXPLANATION_MODEL,
    ExplanationRuntime,
    build_explanation_runtime,
    explain_with_fallback,
)

API_KEY = "test-key-not-a-real-one"

# 사기 문자 형태. 개인정보를 일부러 넣어 뒀다 - 이 문자열의 어느 조각도 로그와
# 지표에 나타나지 않아야 한다.
SUSPICIOUS_TEXT = (
    "[금융감독원] 귀하의 계좌가 대포통장으로 이용되었습니다. "
    "안전계좌로 즉시 이체하지 않으면 형사처벌 대상입니다. "
    "본인확인 900101-1234567 계좌 110-234-567890"
)


@pytest.fixture(autouse=True)
def _clean_metrics() -> Iterator[None]:
    """지표는 프로세스 전역이다. 테스트 사이에 비워 두지 않으면 순서에 따라 값이 는다."""
    explanation_metrics.reset()
    yield
    explanation_metrics.reset()


@pytest.fixture
def verdict() -> AnalyzeResponse:
    return analyze_fraud(
        AnalyzeRequest(text=SUSPICIOUS_TEXT, state=UserState.SHARED_ACCOUNT_ACCESS)
    )


@pytest.fixture
def contract() -> LlmContract:
    return fraud_explanation_contract(
        provider="google_ai_studio", model="gemini-2.5-flash"
    )


@contextmanager
def capture_llm_logs() -> Iterator[list[logging.LogRecord]]:
    """`finshield.llm` 이 실제로 내보낸 줄을 모은다.

    레벨을 여기서 올려 두는 이유는, 이 파일이 `install_observability` 를 거치지 않고
    함수를 직접 부르기도 하기 때문이다. 레벨이 낮아 줄이 사라지면 "개인정보가 없다"
    라는 검사가 아무것도 증명하지 않게 된다.
    """
    records: list[logging.LogRecord] = []

    class CollectingHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger("finshield.llm")
    handler = CollectingHandler()
    previous_level = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)


def _provider_with(handler: Any) -> GoogleAiStudioProvider:
    return GoogleAiStudioProvider(
        API_KEY, client=httpx.Client(transport=httpx.MockTransport(handler))
    )


def _responder(*, status: int = 200, body: Any = None, text: str | None = None) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        if text is not None:
            return httpx.Response(status, text=text)
        return httpx.Response(status, json=body)

    return handler


def _raiser(error: Exception) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    return handler


def _candidate(text: str, *, finish_reason: str = "STOP") -> dict[str, Any]:
    return {
        "candidates": [
            {"content": {"parts": [{"text": text}]}, "finishReason": finish_reason}
        ]
    }


class _OutcomeProvider:
    """지정한 사유로 실패하거나 지정한 문장을 돌려주는 프로바이더.

    프로바이더 응답을 우리 어휘로 옮기는 표는 아래 `test_every_failure_mode…` 가
    실제 HTTP 모양으로 검사한다. 이 프로바이더는 **세는 쪽**을 검사할 때 쓴다 -
    사유를 골라 놓고 지표가 그것을 어떻게 쌓는지 보는 것이다.
    """

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


def _runtime_with(provider: Any) -> ExplanationRuntime:
    real = build_explanation_runtime(
        {"FINSHIELD_LLM_PROVIDER": "google_ai_studio", "GEMINI_API_KEY": API_KEY}
    )
    assert real is not None
    return ExplanationRuntime(provider=provider, contracts=real.contracts)


def _attempt_counts() -> dict[tuple[str, str], int]:
    """노출 문서를 다시 파싱해서 센다.

    내부 Counter 를 들여다보지 않는 이유는, 운영에서 읽히는 것이 이 텍스트이기
    때문이다. 카운터는 맞는데 노출이 깨진 상태를 잡으려면 노출을 읽어야 한다.
    """
    counts: dict[tuple[str, str], int] = {}
    for line in explanation_metrics.prometheus_text().splitlines():
        if not line.startswith("finshield_llm_explanation_attempts_total{"):
            continue
        labels, _, value = line.partition("} ")
        model = labels.split('model="', 1)[1].split('"', 1)[0]
        outcome = labels.split('outcome="', 1)[1].split('"', 1)[0]
        counts[(model, outcome)] = int(value)
    return counts


def _result_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for line in explanation_metrics.prometheus_text().splitlines():
        if not line.startswith("finshield_llm_explanation_results_total{"):
            continue
        labels, _, value = line.partition("} ")
        outcome = labels.split('outcome="', 1)[1].split('"', 1)[0]
        counts[outcome] = int(value)
    return counts


# --- 사유가 갈리는가 -------------------------------------------------------


@pytest.mark.parametrize(
    ("handler", "expected"),
    [
        # 성공
        (
            _responder(body=_candidate("이 문자는 정상 절차와 다릅니다.")),
            ExplanationOutcome.OK,
        ),
        # 프로바이더에 닿지 못했다. 타임아웃은 **우리 예산 이야기**라 따로 센다.
        (_raiser(httpx.TimeoutException("timed out")), ExplanationOutcome.TIMEOUT),
        (_raiser(httpx.ConnectError("refused")), ExplanationOutcome.TRANSPORT_ERROR),
        (_raiser(httpx.ReadError("reset")), ExplanationOutcome.TRANSPORT_ERROR),
        (_responder(status=429, body={"error": {}}), ExplanationOutcome.HTTP_ERROR),
        (_responder(status=500, body={"error": {}}), ExplanationOutcome.HTTP_ERROR),
        # 응답이 왔지만 모양을 모른다
        (_responder(text="<html>nope</html>"), ExplanationOutcome.MALFORMED_BODY),
        (_responder(body=[]), ExplanationOutcome.MALFORMED_BODY),
        (_responder(body={"candidates": []}), ExplanationOutcome.MALFORMED_BODY),
        (
            _responder(body={"candidates": [{"content": {}, "finishReason": "STOP"}]}),
            ExplanationOutcome.MALFORMED_BODY,
        ),
        # 요청이 막힌 것과 응답이 막힌 것을 나눈다
        (
            _responder(body={"promptFeedback": {"blockReason": "SAFETY"}}),
            ExplanationOutcome.PROMPT_BLOCKED,
        ),
        (
            _responder(body={"promptFeedback": {"blockReason": "PROHIBITED_CONTENT"}}),
            ExplanationOutcome.PROMPT_BLOCKED,
        ),
        (
            _responder(body=_candidate("", finish_reason="SAFETY")),
            ExplanationOutcome.SAFETY_BLOCKED,
        ),
        (
            _responder(body=_candidate("이 문자는 정상 절차와 다르", finish_reason="MAX_TOKENS")),
            ExplanationOutcome.TRUNCATED,
        ),
        (
            _responder(body=_candidate("", finish_reason="RECITATION")),
            ExplanationOutcome.RECITATION_BLOCKED,
        ),
        (
            _responder(body=_candidate("", finish_reason="SOMETHING_NEW")),
            ExplanationOutcome.STOPPED_EARLY,
        ),
        (_responder(body=_candidate("   ")), ExplanationOutcome.EMPTY_TEXT),
        # 모델이 답했지만 출력 검증이 버렸다 - 여기부터가 설명 품질이다
        (
            _responder(body=_candidate("자세한 내용은 https://example.com 에서 보세요.")),
            ExplanationOutcome.REJECTED_URL,
        ),
        (
            _responder(body=_candidate("예를 들어 900101-1234567 같은 번호입니다.")),
            ExplanationOutcome.REJECTED_RRN,
        ),
        (_responder(body=_candidate("가" * 700)), ExplanationOutcome.REJECTED_TOO_LONG),
        (
            _responder(body=_candidate("이 문자는 안전합니다.")),
            ExplanationOutcome.REJECTED_CONTRADICTS_VERDICT,
        ),
        (
            _responder(body=_candidate("지금 당장 02-9999-8888 로 전화하세요.")),
            ExplanationOutcome.REJECTED_INVENTED_CONTACT,
        ),
    ],
)
def test_every_failure_mode_has_its_own_name(
    verdict: AnalyzeResponse,
    contract: LlmContract,
    handler: Any,
    expected: ExplanationOutcome,
) -> None:
    """실패 하나하나가 다른 이름으로 나온다.

    이 표가 이 회차의 전부다. 계측을 붙여도 실패가 한 칸에 뭉쳐 있으면 숫자를 읽을
    수 없다 - "설명이 40% 비어 있다" 는 안전 필터 문제일 수도, 우리 토큰 예산
    문제일 수도, 모델이 없는 신고번호를 지어내는 문제일 수도 있고 대응은 셋 다
    다르다.
    """
    attempt = explain_analysis(
        verdict, SUSPICIOUS_TEXT, provider=_provider_with(handler), contract=contract
    )

    assert attempt.outcome is expected
    assert (attempt.text is not None) is (expected is ExplanationOutcome.OK)


def test_an_empty_model_reply_is_named_where_it_is_seen(
    verdict: AnalyzeResponse,
) -> None:
    """빈 문장은 프로바이더가 먼저 잡으므로 `REJECTED_EMPTY` 는 그쪽 경로로는 안 온다.

    `_extract_text` 가 빈 텍스트를 `EMPTY_TEXT` 로 이미 막기 때문이다. 그래도 검증
    쪽 칸을 지우지 않는 이유는, 그 검사가 프로바이더와 무관하게 자기 계약을 지켜야
    하기 때문이다 - 공백만 돌려주는 프로바이더가 새로 생겼을 때 검증이 통과하면 빈
    설명이 화면에 나간다.
    """
    stub_contract = fraud_explanation_contract(provider="stub", model="stub-1")

    attempt = explain_analysis(
        verdict,
        SUSPICIOUS_TEXT,
        provider=StubProvider(response="   "),
        contract=stub_contract,
    )

    assert attempt.outcome is ExplanationOutcome.REJECTED_EMPTY


def test_a_blocked_prompt_is_not_a_broken_body(
    verdict: AnalyzeResponse, contract: LlmContract
) -> None:
    """후보가 없는 두 경우를 나눈다.

    사기 문자를 그대로 모델에 보내는 서비스라 **정상 입력이 요청 단계에서 막힐 수
    있다.** 그건 우리 프롬프트를 고쳐야 하는 신호다. 응답 모양이 바뀐 것은 클라이언트
    코드를 고쳐야 하는 신호다. 같은 칸에 세면 둘 중 어느 쪽인지 알 수 없고, 그러면
    아무 조치도 못 한다.
    """
    blocked = explain_analysis(
        verdict,
        SUSPICIOUS_TEXT,
        provider=_provider_with(
            _responder(body={"promptFeedback": {"blockReason": "SAFETY"}})
        ),
        contract=contract,
    )
    shapeless = explain_analysis(
        verdict,
        SUSPICIOUS_TEXT,
        provider=_provider_with(_responder(body={"candidates": []})),
        contract=contract,
    )

    assert blocked.outcome is ExplanationOutcome.PROMPT_BLOCKED
    assert shapeless.outcome is ExplanationOutcome.MALFORMED_BODY
    assert blocked.outcome is not shapeless.outcome


# --- 어휘가 닫혀 있는가 ---------------------------------------------------


def test_an_unknown_finish_reason_never_becomes_a_label(
    verdict: AnalyzeResponse,
) -> None:
    """프로바이더가 우리 라벨을 정하게 두지 않는다.

    사유 문자열을 그대로 라벨로 쓰면 Gemini 가 새 `finishReason` 을 추가하는 날
    우리 지표에 새 시계열이 생긴다. Prometheus 라벨은 한 번 늘어나면 줄지 않고,
    그 값이 무엇인지는 아무도 미리 검토하지 않았다.
    """
    canary = "CANARY_UNREVIEWED_REASON"
    runtime = _runtime_with(
        _provider_with(_responder(body=_candidate("", finish_reason=canary)))
    )

    with capture_llm_logs() as records:
        result = explain_with_fallback(verdict, SUSPICIOUS_TEXT, runtime=runtime)

    assert result.outcome is ExplanationOutcome.STOPPED_EARLY
    exposition = explanation_metrics.prometheus_text()
    assert canary not in exposition
    assert all(canary not in record.message for record in records)


def test_the_vocabulary_is_safe_as_a_metric_label() -> None:
    """어휘 자체가 노출 형식을 깨지 않는지 본다.

    값에 따옴표나 줄바꿈이 하나 들어가면 `/internal/metrics` 전체가 파싱 불가가
    된다. 사유를 늘리는 사람이 실수할 수 있는 자리라 표 대신 규칙으로 막는다.
    """
    values = [outcome.value for outcome in ExplanationOutcome]

    assert len(values) == len(set(values))
    for value in values:
        assert value.replace("_", "").isalnum()
        assert value.islower()
        assert value == value.strip()


def test_every_raise_inside_the_app_names_its_reason() -> None:
    """`app/` 안에서 사유 없이 실패를 올리는 자리가 없는지 소스로 확인한다.

    `unspecified` 는 우리가 만드는 값이 아니다 - `LlmProvider` 가 Protocol 이라
    남의 구현이 사유 없이 던질 수 있고, 그때 요청을 죽이지 않으려고 어휘 안에
    칸을 둔 것이다. 우리 코드가 그 칸을 쓰기 시작하면 그 구분이 사라지고,
    "사유를 모른다" 와 "사유를 안 붙였다" 가 같은 숫자가 된다.

    문자열 검색이 아니라 구문 트리로 보는 이유는, 여러 줄에 걸친 호출을 놓치지
    않기 위해서다.
    """
    named = {"LlmUnavailable", "LlmOutputRejected"}
    missing: list[str] = []

    for path in sorted(Path("app").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
                continue
            func = node.exc.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name not in named:
                continue
            if not any(kw.arg == "outcome" for kw in node.exc.keywords):
                missing.append(f"{path}:{node.lineno}")

    assert missing == [], f"사유 없이 올라오는 실패: {missing}"


# --- 개인정보가 지나가지 않는가 -------------------------------------------


def test_nothing_from_the_message_or_the_output_reaches_the_log_or_the_metrics(
    verdict: AnalyzeResponse,
) -> None:
    """`ADR 0006` 이 요구하는 형태인지 실제 출력으로 확인한다.

    주장이 아니라 관측이다. 원문에 주민등록번호와 계좌번호를 넣고, 모델 출력에는
    지어낸 전화번호를 넣고, 그 어느 조각도 로그 줄과 노출 문서에 없는지 본다.
    이 계층이 다루는 문자열은 사기 피해 상황의 원문이라, 한 줄만 새도 그게 곧
    금융 개인정보 유출이다.
    """
    invented_contact = "02-9999-8888"
    runtime = _runtime_with(
        _provider_with(
            _responder(body=_candidate(f"지금 당장 {invented_contact} 로 전화하세요."))
        )
    )

    with capture_llm_logs() as records:
        result = explain_with_fallback(verdict, SUSPICIOUS_TEXT, runtime=runtime)

    assert result.text is None
    assert result.outcome is ExplanationOutcome.REJECTED_INVENTED_CONTACT

    exposition = explanation_metrics.prometheus_text()
    haystack = exposition + "\n".join(record.message for record in records)
    for secret in (
        "900101-1234567",
        "110-234-567890",
        invented_contact,
        "안전계좌",
        "대포통장",
        "금융감독원",
        API_KEY,
    ):
        assert secret not in haystack, secret

    # 남은 줄이 무엇인지도 고정한다. 키가 늘어나는 것은 검토를 거쳐야 하는 변경이다.
    events = [json.loads(record.message) for record in records]
    assert [event["event"] for event in events] == [
        "llm_explanation_attempt",
        "llm_explanation_attempt",
        "llm_explanation_result",
    ]
    assert set(events[0]) == {
        "attempt",
        "duration_ms",
        "event",
        "model",
        "outcome",
        "service",
        "timestamp",
    }
    assert set(events[-1]) == {
        "attempts",
        "event",
        "outcome",
        "service",
        "timestamp",
    }


def test_a_model_name_that_would_break_the_exposition_is_replaced() -> None:
    """라벨은 허용 목록을 통과한 것만 쓴다.

    모델 이름은 코드 상수라 지금은 안전하지만, 문자열인 한 언젠가 다른 값이 들어온다.
    고쳐 쓰지 않고 `other` 로 세는 것이 `ADR 0006` 의 방식이다 - 마스킹은 빠뜨린
    것을 흘리고 허용 목록은 모르는 것을 버린다.
    """
    explanation_metrics.observe_attempt(
        model='gemini"\n evil{x="y"}',
        outcome=ExplanationOutcome.OK.value,
        attempt=1,
        duration_ms=1.0,
    )

    exposition = explanation_metrics.prometheus_text()
    assert 'model="other"' in exposition
    assert "evil" not in exposition
    for line in exposition.splitlines():
        assert line.count('"') % 2 == 0


# --- 세는 자리가 하나인가 -------------------------------------------------


def test_the_pure_layer_does_not_count(
    verdict: AnalyzeResponse, contract: LlmContract
) -> None:
    """`explain_analysis` 는 세지 않는다.

    `evaluation/` 이 이 함수를 직접 부른다. 여기에 카운터를 두면 벤치마크를 한 번
    돌릴 때마다 운영 지표가 수십 건씩 오염되고, 그 지표로 경보를 걸 수 없게 된다.
    """
    for _ in range(3):
        explain_analysis(
            verdict,
            SUSPICIOUS_TEXT,
            provider=_provider_with(_raiser(httpx.TimeoutException("timed out"))),
            contract=contract,
        )

    assert _attempt_counts() == {}
    assert _result_counts() == {}


def test_the_fallback_records_every_attempt_and_one_result(
    verdict: AnalyzeResponse,
) -> None:
    """시도와 결과를 따로 세는 이유를 고정한다.

    대체 모델이 있으므로 요청 하나가 시도 둘을 만들고, 그때 실패 하나와 성공
    하나가 같이 일어난다. 시도만 세면 "설명이 결국 비었다" 를 계산할 수 없고,
    결과만 세면 "주 모델이 얼마나 막히는가" 를 계산할 수 없다.
    """
    provider = _OutcomeProvider(
        {
            EXPLANATION_MODEL: ExplanationOutcome.PROMPT_BLOCKED,
            EXPLANATION_FALLBACK_MODEL: "정상 절차에 없는 요구입니다.",
        }
    )

    result = explain_with_fallback(
        verdict, SUSPICIOUS_TEXT, runtime=_runtime_with(provider)
    )

    assert result.text == "정상 절차에 없는 요구입니다."
    assert result.model == EXPLANATION_FALLBACK_MODEL
    assert result.outcome is ExplanationOutcome.OK
    assert _attempt_counts() == {
        (EXPLANATION_MODEL, "prompt_blocked"): 1,
        (EXPLANATION_FALLBACK_MODEL, "ok"): 1,
    }
    # 시도는 둘, 결과는 하나다.
    assert _result_counts() == {"ok": 1}


def test_a_failed_request_records_the_reason_the_user_saw(
    verdict: AnalyzeResponse,
) -> None:
    """전부 실패하면 결과에 남는 것은 **마지막** 사유다.

    사용자가 설명 없는 화면을 보게 된 직접적인 이유가 그것이고, 앞선 실패는
    시도 지표에 이미 각각 남아 있다.
    """
    provider = _OutcomeProvider(
        {
            EXPLANATION_MODEL: ExplanationOutcome.SAFETY_BLOCKED,
            EXPLANATION_FALLBACK_MODEL: ExplanationOutcome.HTTP_ERROR,
        }
    )

    result = explain_with_fallback(
        verdict, SUSPICIOUS_TEXT, runtime=_runtime_with(provider)
    )

    assert result.text is None
    assert result.model is None
    assert result.outcome is ExplanationOutcome.HTTP_ERROR
    assert _result_counts() == {"http_error": 1}
    assert _attempt_counts() == {
        (EXPLANATION_MODEL, "safety_blocked"): 1,
        (EXPLANATION_FALLBACK_MODEL, "http_error"): 1,
    }


# --- 물어본 숫자가 실제로 나오는가 ----------------------------------------


def test_the_safety_filter_block_rate_is_computable(verdict: AnalyzeResponse) -> None:
    """`docs/34` 9절이 물은 숫자를 실제로 뽑는다.

    계측을 넣고도 숫자를 못 뽑는 경우가 있고, 그러면 넣지 않은 것과 같다. 여기서는
    주 모델 네 번 중 둘이 안전 필터에 막히는 상황을 만들고, 노출 문서만 보고
    차단율 0.5 가 계산되는지 확인한다.
    """
    scripts: list[dict[str, str | ExplanationOutcome]] = [
        {EXPLANATION_MODEL: ExplanationOutcome.PROMPT_BLOCKED},
        {EXPLANATION_MODEL: ExplanationOutcome.SAFETY_BLOCKED},
        {EXPLANATION_MODEL: "정상 절차에 없는 요구입니다."},
        {EXPLANATION_MODEL: "요구 자체가 정상 절차에 없습니다."},
    ]
    for script in scripts:
        explain_with_fallback(
            verdict,
            SUSPICIOUS_TEXT,
            runtime=_runtime_with(_OutcomeProvider(script)),
        )

    counts = _attempt_counts()
    primary = {
        outcome: count for (model, outcome), count in counts.items()
        if model == EXPLANATION_MODEL
    }
    blocked = sum(
        count
        for outcome, count in primary.items()
        if outcome in {member.value for member in BLOCKED_OUTCOMES}
    )

    assert sum(primary.values()) == 4
    assert blocked == 2
    assert blocked / sum(primary.values()) == pytest.approx(0.5)


def test_the_metrics_ride_the_existing_endpoint() -> None:
    """새 엔드포인트를 만들지 않았다.

    엔드포인트를 열면 그것이 새 외부 표면이고 `CLAUDE.md` 의 보안 검토 대상이
    된다. 붙이는 쪽은 이미 스키마에서 빠져 있고 배포에서 프록시가 막는 경로다.
    """
    explanation_metrics.observe_result(
        outcome=ExplanationOutcome.PROMPT_BLOCKED.value, attempts=2
    )

    body = TestClient(app).get("/internal/metrics").text

    assert "finshield_http_requests_total" in body
    assert 'finshield_llm_explanation_results_total{outcome="prompt_blocked"} 1' in body

    llm_paths = [
        route.path  # type: ignore[attr-defined]
        for route in app.routes
        if "llm" in getattr(route, "path", "")
    ]
    assert llm_paths == []


# --- 타입이 거짓말을 못 하게 ----------------------------------------------


def test_an_attempt_cannot_claim_success_without_a_sentence() -> None:
    """`OK` 인데 문장이 없거나, 실패인데 문장이 있는 상태를 만들 수 없다.

    이 둘이 어긋나면 지표는 성공을 세는데 화면은 비어 있다. 그 상태는 계측이 없는
    것보다 나쁘다 - 숫자가 있으니 아무도 안 찾아본다.
    """
    with pytest.raises(ValueError):
        ExplanationAttempt(text=None, outcome=ExplanationOutcome.OK)
    with pytest.raises(ValueError):
        ExplanationAttempt(text="설명", outcome=ExplanationOutcome.TIMEOUT)

    assert ExplanationAttempt(text="설명", outcome=ExplanationOutcome.OK).text == "설명"
