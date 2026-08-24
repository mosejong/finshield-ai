"""AI Studio 프로바이더 테스트.

전부 `httpx.MockTransport` 로 돈다. 실제 키도, 네트워크도, 크레딧도 쓰지 않는다.
확인하는 것은 "Gemini 가 좋은 답을 하는가" 가 아니라 **우리가 무엇을 보내고,
무엇이 잘못됐을 때 어떻게 접히는가** 다.

프로바이더 쪽에서 가장 중요한 성질은 하나다. **실패는 전부 `LlmUnavailable` 로
수렴한다.** 어떤 실패든 설명이 비고 판정은 그대로 나간다. 새로운 예외 타입이
여기서 새어 나가면 그 경로가 깨진다.

타입은 하나로 수렴하되 **사유는 갈린다.** 예외에 붙는 `ExplanationOutcome` 이
어느 실패인지 말해 주고, 그것만이 로그와 지표로 나간다. 사유별 대응표는
`tests/test_llm_explanation_outcomes.py` 가 따로 지킨다.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.clients.google_ai_studio import (
    API_BASE_URL,
    MAX_OUTPUT_TOKENS,
    THINKING_LEVEL,
    GoogleAiStudioConfigurationError,
    GoogleAiStudioProvider,
    build_google_ai_studio_provider,
)
from app.schemas.analysis import AnalyzeRequest, UserState
from app.services.fraud_analysis import analyze_fraud
from app.services.llm import (
    ExplanationOutcome,
    LlmContract,
    LlmUnavailable,
    explain_analysis,
)
from app.services.llm.explanation import fraud_explanation_contract

API_KEY = "test-key-not-a-real-one"

SUSPICIOUS_TEXT = (
    "[금융감독원] 귀하의 계좌가 대포통장으로 이용되었습니다. "
    "안전계좌로 즉시 이체하지 않으면 형사처벌 대상입니다. "
    "본인확인 900101-1234567 계좌 110-234-567890"
)


@pytest.fixture
def contract() -> LlmContract:
    return fraud_explanation_contract(
        provider="google_ai_studio", model="gemini-2.5-flash"
    )


def _ok_body(text: str = "이 문자는 정상 절차와 다릅니다.") -> dict[str, Any]:
    return {
        "candidates": [
            {"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}
        ]
    }


def _provider_with(
    handler: Any, *, api_key: str = API_KEY
) -> GoogleAiStudioProvider:
    return GoogleAiStudioProvider(
        api_key, client=httpx.Client(transport=httpx.MockTransport(handler))
    )


# --- 정상 경로와 요청 모양 -------------------------------------------------


def test_returns_the_model_text(contract: LlmContract) -> None:
    provider = _provider_with(lambda request: httpx.Response(200, json=_ok_body()))
    assert provider.generate(contract=contract, prompt="설명해줘") == (
        "이 문자는 정상 절차와 다릅니다."
    )


def test_request_carries_the_key_in_a_header_not_the_url(
    contract: LlmContract,
) -> None:
    """키가 URL 에 실리면 로그·프록시·오류 보고서에 남는다."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_ok_body())

    _provider_with(handler).generate(contract=contract, prompt="설명해줘")

    (request,) = seen
    assert request.headers["x-goog-api-key"] == API_KEY
    assert API_KEY not in str(request.url)
    assert "key=" not in str(request.url)


def test_request_targets_the_contract_model_and_settings(
    contract: LlmContract,
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_ok_body())

    _provider_with(handler).generate(contract=contract, prompt="설명해줘")

    (request,) = seen
    assert request.method == "POST"
    assert str(request.url) == f"{API_BASE_URL}/gemini-2.5-flash:generateContent"

    body = json.loads(request.content)
    assert body["contents"][0]["parts"][0]["text"] == "설명해줘"
    assert body["generationConfig"]["temperature"] == contract.temperature
    assert body["generationConfig"]["maxOutputTokens"] == MAX_OUTPUT_TOKENS
    assert body["generationConfig"]["thinkingConfig"] == {
        "thinkingLevel": THINKING_LEVEL
    }


def test_the_token_budget_leaves_room_for_thinking() -> None:
    """예산은 답변 길이가 아니라 사고 + 답변의 합으로 잡는다.

    2026-08-19 에 실제로 밟은 버그다. 예산이 1024 일 때 `gemini-3.6-flash` 는 사고에
    982 토큰을 쓰고 답변에 38 토큰만 남겨 매번 `finishReason: MAX_TOKENS` 가 됐다.
    모델은 멀쩡했고 우리 예산이 작았다. 아래 `test_truncated_output_is_not_shown`
    가 그 잘린 응답을 버리는 것까지는 검사했지만, **버려질 요청을 우리가 보내고
    있다는 것**은 잡지 못했다.

    사고 토큰 실측치가 700~1030 이므로 답변 몫 + 넉넉한 사고 몫을 요구한다. 이 값을
    다시 내리려는 사람은 그 실측을 먼저 뒤집어야 한다.
    """
    observed_thinking_tokens = 1_030
    assert MAX_OUTPUT_TOKENS >= observed_thinking_tokens * 2


# --- 실패는 전부 LlmUnavailable 로 수렴한다 --------------------------------


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500, 503])
def test_error_status_becomes_unavailable(
    contract: LlmContract, status: int
) -> None:
    provider = _provider_with(
        lambda request: httpx.Response(status, json={"error": {"message": "nope"}})
    )
    with pytest.raises(LlmUnavailable, match=f"HTTP {status}"):
        provider.generate(contract=contract, prompt="설명해줘")


def test_error_message_never_leaks_the_key_or_the_body(
    contract: LlmContract,
) -> None:
    """400 응답이 요청 일부를 되돌려 주는 경우가 있다. 그것을 예외에 담지 않는다."""
    provider = _provider_with(
        lambda request: httpx.Response(
            400, json={"error": {"message": f"bad prompt: {SUSPICIOUS_TEXT}"}}
        )
    )
    with pytest.raises(LlmUnavailable) as caught:
        provider.generate(contract=contract, prompt=SUSPICIOUS_TEXT)

    message = str(caught.value)
    assert API_KEY not in message
    assert "900101-1234567" not in message
    assert "대포통장" not in message


@pytest.mark.parametrize(
    "error",
    [
        httpx.TimeoutException("timed out"),
        httpx.ConnectError("refused"),
        httpx.ReadError("reset"),
    ],
)
def test_transport_errors_become_unavailable(
    contract: LlmContract, error: httpx.HTTPError
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    with pytest.raises(LlmUnavailable, match="request failed"):
        _provider_with(handler).generate(contract=contract, prompt="설명해줘")


def test_non_json_body_becomes_unavailable(contract: LlmContract) -> None:
    provider = _provider_with(
        lambda request: httpx.Response(200, text="<html>정상 아님</html>")
    )
    with pytest.raises(LlmUnavailable, match="non-JSON"):
        provider.generate(contract=contract, prompt="설명해줘")


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"candidates": []}, "no candidate"),
        # 안전 필터가 프롬프트 자체를 막으면 candidates 가 아예 없다.
        ({"promptFeedback": {"blockReason": "SAFETY"}}, "no candidate"),
        ({"candidates": [{"finishReason": "MAX_TOKENS"}]}, "stopped early"),
        ({"candidates": [{"finishReason": "SAFETY"}]}, "stopped early"),
        ({"candidates": [{"finishReason": "RECITATION"}]}, "stopped early"),
        ({"candidates": [{"content": {}, "finishReason": "STOP"}]}, "no content parts"),
        (
            {"candidates": [{"content": {"parts": [{"text": "  "}]}, "finishReason": "STOP"}]},
            "empty text",
        ),
        ([], "unexpected payload shape"),
    ],
)
def test_unusable_payloads_become_unavailable(
    contract: LlmContract, body: Any, expected: str
) -> None:
    provider = _provider_with(lambda request: httpx.Response(200, json=body))
    with pytest.raises(LlmUnavailable, match=expected):
        provider.generate(contract=contract, prompt="설명해줘")


def test_truncated_output_is_not_shown(contract: LlmContract) -> None:
    """MAX_TOKENS 로 잘린 문장은 버린다. 반쯤 끊긴 안내가 없는 안내보다 나쁘다."""
    provider = _provider_with(
        lambda request: httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"parts": [{"text": "이 문자는 정상 절차와 다르"}]},
                        "finishReason": "MAX_TOKENS",
                    }
                ]
            },
        )
    )
    with pytest.raises(LlmUnavailable, match="stopped early"):
        provider.generate(contract=contract, prompt="설명해줘")


# --- 계약·설정 방어 --------------------------------------------------------


def test_provider_refuses_another_providers_contract() -> None:
    stub_contract = fraud_explanation_contract(provider="stub", model="stub-1")
    provider = _provider_with(lambda request: httpx.Response(200, json=_ok_body()))
    with pytest.raises(LlmUnavailable, match="cannot serve a contract for stub"):
        provider.generate(contract=stub_contract, prompt="설명해줘")


@pytest.mark.parametrize("model", ["../../evil", "gemini flash", "a/b", "x?alt=sse"])
def test_model_names_that_would_change_the_path_are_refused(model: str) -> None:
    """모델명은 URL 경로에 들어간다. 계약이 막는 것은 빈 문자열뿐이므로 여기서 본다."""
    contract = fraud_explanation_contract(
        provider="google_ai_studio", model="gemini-2.5-flash"
    )
    object.__setattr__(contract, "model", model)  # frozen dataclass 우회

    provider = _provider_with(lambda request: httpx.Response(200, json=_ok_body()))
    with pytest.raises(LlmUnavailable, match="unsupported model name"):
        provider.generate(contract=contract, prompt="설명해줘")


@pytest.mark.parametrize("api_key", ["", "   "])
def test_empty_key_fails_at_assembly_not_at_request_time(api_key: str) -> None:
    with pytest.raises(GoogleAiStudioConfigurationError, match="not configured"):
        GoogleAiStudioProvider(api_key)


def test_build_reads_the_key_from_a_secret_file(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = tmp_path / "gemini_api_key.txt"
    secret.write_text(f"{API_KEY}\n", encoding="utf-8")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY_FILE", str(secret))

    provider = build_google_ai_studio_provider()
    assert provider.name == "google_ai_studio"


def test_build_refuses_both_key_and_key_file(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = tmp_path / "gemini_api_key.txt"
    secret.write_text(API_KEY, encoding="utf-8")
    monkeypatch.setenv("GEMINI_API_KEY", API_KEY)
    monkeypatch.setenv("GEMINI_API_KEY_FILE", str(secret))

    with pytest.raises(GoogleAiStudioConfigurationError, match="invalid"):
        build_google_ai_studio_provider()


def test_build_without_any_key_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY_FILE", raising=False)

    with pytest.raises(GoogleAiStudioConfigurationError, match="not configured"):
        build_google_ai_studio_provider()


# --- 전 경로 --------------------------------------------------------------


def test_full_path_sends_no_raw_identifiers_and_keeps_the_verdict(
    contract: LlmContract,
) -> None:
    """최소화부터 출력 검증까지, 실제 HTTP 본문을 꺼내서 확인한다."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_ok_body())

    analysis = analyze_fraud(
        AnalyzeRequest(text=SUSPICIOUS_TEXT, state=UserState.SHARED_ACCOUNT_ACCESS)
    )
    before = analysis.model_dump()

    attempt = explain_analysis(
        analysis,
        SUSPICIOUS_TEXT,
        provider=_provider_with(handler),
        contract=contract,
    )

    assert attempt.text == "이 문자는 정상 절차와 다릅니다."
    assert attempt.outcome is ExplanationOutcome.OK
    assert analysis.model_dump() == before

    (request,) = seen
    sent = request.content.decode("utf-8")
    assert "900101-1234567" not in sent
    assert "110-234-567890" not in sent
    # JSON 은 한글을 \uXXXX 로 이스케이프하므로 디코딩해서 본다.
    sent_prompt = json.loads(request.content)["contents"][0]["parts"][0]["text"]
    assert "[주민등록번호]" in sent_prompt
    assert "[계좌번호]" in sent_prompt
    assert "안전계좌" in sent_prompt


def test_provider_failure_leaves_the_verdict_intact(contract: LlmContract) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    analysis = analyze_fraud(
        AnalyzeRequest(text=SUSPICIOUS_TEXT, state=UserState.SHARED_ACCOUNT_ACCESS)
    )
    before = analysis.model_dump()

    attempt = explain_analysis(
        analysis,
        SUSPICIOUS_TEXT,
        provider=_provider_with(handler),
        contract=contract,
    )

    assert attempt.text is None
    # 타임아웃은 우리 예산 이야기라 다른 전송 오류와 따로 센다(`outcomes.py`).
    assert attempt.outcome is ExplanationOutcome.TIMEOUT
    assert analysis.model_dump() == before
    assert analysis.risk_level == "high"
