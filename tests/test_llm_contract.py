"""LLM 설명 계층의 경계 테스트.

여기서 확인하는 것은 "설명이 좋은가" 가 아니다. 그건 벤치마크가 할 일이다.
이 파일은 **모델이 무엇을 하든 넘을 수 없는 선** 만 본다.

- 판정을 못 바꾼다.
- 원문 개인정보가 밖으로 안 나간다.
- 근거에 없는 연락처·주소를 붙여도 사용자에게 안 닿는다.
- 프로바이더가 죽어도 서비스는 답한다.
- 프롬프트를 몰래 못 고친다.

모두 가짜 프로바이더로 검사한다. 네트워크가 필요한 검사였다면 CI 에서 꺼졌을
것이고, 꺼진 검사는 없는 검사다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.schemas.analysis import AnalyzeRequest, AnalyzeResponse, UserState
from app.services.fraud_analysis import analyze_fraud
from app.services.llm import (
    LlmContract,
    LlmContractError,
    LlmOutputRejected,
    LlmUnavailable,
    StubProvider,
    explain_analysis,
    minimize_for_provider,
    validate_explanation,
)
from app.services.llm.explanation import (
    FRAUD_EXPLANATION_PROMPT_SHA256,
    MAX_EXPLANATION_CHARS,
    build_grounded_text,
    fraud_explanation_contract,
)
from app.services.llm.prompts import FRAUD_EXPLANATION_PROMPT

# 실제 사기 문자 형태. 계좌 접근을 요구하는 유형이라 신호·행동이 모두 붙는다.
SUSPICIOUS_TEXT = (
    "[금융감독원] 귀하의 계좌가 대포통장으로 이용되었습니다. "
    "안전계좌로 즉시 이체하지 않으면 형사처벌 대상입니다. "
    "담당수사관 확인: 010-1234-5678"
)


@pytest.fixture
def contract() -> LlmContract:
    return fraud_explanation_contract(provider="stub", model="stub-1")


@pytest.fixture
def response() -> AnalyzeResponse:
    return analyze_fraud(
        AnalyzeRequest(text=SUSPICIOUS_TEXT, state=UserState.SHARED_ACCOUNT_ACCESS)
    )


# --- 계약 자체 -------------------------------------------------------------


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(LlmContractError, match="unknown provider"):
        fraud_explanation_contract(provider="openai", model="gpt-4")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("model", "  "),
        ("prompt_id", ""),
        ("prompt_sha256", "not-a-hash"),
        ("prompt_sha256", "A" * 64),  # 대문자 hex 는 받지 않는다
        ("max_input_chars", 0),
        ("max_input_chars", 10_001),
        ("timeout_seconds", 0.0),
        ("timeout_seconds", 31.0),
        ("temperature", 1.5),
    ],
)
def test_malformed_contract_fields_are_rejected(
    contract: LlmContract, field: str, value: object
) -> None:
    fields: dict[str, object] = {
        "provider": contract.provider,
        "model": contract.model,
        "prompt_id": contract.prompt_id,
        "prompt_sha256": contract.prompt_sha256,
        "max_input_chars": contract.max_input_chars,
        "timeout_seconds": contract.timeout_seconds,
        "temperature": contract.temperature,
        field: value,
    }
    with pytest.raises(LlmContractError):
        LlmContract(**fields)  # type: ignore[arg-type]


def test_pinned_hash_matches_the_shipped_prompt(contract: LlmContract) -> None:
    """계약에 적힌 sha256 이 실제 프롬프트와 같아야 한다."""
    contract.verify_prompt(FRAUD_EXPLANATION_PROMPT)


def test_editing_the_prompt_breaks_the_pin(contract: LlmContract) -> None:
    """이 파일에서 제일 중요한 검사다.

    프롬프트를 고치면 여기서 깨진다. 깨진 사람은 해시를 갱신하면서 자기가
    측정값을 무효화했다는 사실을 알게 된다. 해시를 프롬프트에서 계산했다면
    이 테스트는 영원히 통과했을 것이고, 아무것도 증명하지 못했을 것이다.
    """
    edited = FRAUD_EXPLANATION_PROMPT + " 한 문장 더 덧붙인다."
    with pytest.raises(LlmContractError, match="does not match the pinned hash"):
        contract.verify_prompt(edited)


def test_pinned_hash_is_a_literal_not_a_computation() -> None:
    """상수가 프롬프트에서 계산되지 않고 적혀 있는지 소스로 확인한다."""
    source = Path("app/services/llm/explanation.py").read_text(encoding="utf-8")
    pinned_line = next(
        line for line in source.splitlines() if FRAUD_EXPLANATION_PROMPT_SHA256 in line
    )
    assert '"' in pinned_line
    assert "sha256(" not in pinned_line


# --- 개인정보 최소화 -------------------------------------------------------


def test_minimization_replaces_each_kind_of_identifier() -> None:
    minimized = minimize_for_provider(
        "제 정보는 900101-1234567, 카드 1234-5678-9012-3456, "
        "계좌 110-234-567890, 연락처 010-9876-5432, me@example.com 입니다"
    )
    for placeholder in (
        "[주민등록번호]",
        "[카드번호]",
        "[계좌번호]",
        "[전화번호]",
        "[이메일]",
    ):
        assert placeholder in minimized.text
    for raw in ("900101", "9012-3456", "567890", "9876-5432", "example.com"):
        assert raw not in minimized.text
    assert minimized.removed_total == 5


def test_minimization_keeps_the_signal_bearing_parts() -> None:
    """금액·기관명·URL 은 판단 근거다. 지우면 설명이 근거를 잃는다."""
    minimized = minimize_for_provider(
        "금융감독원입니다. 3000000원을 http://bit.ly/abc 에서 확인하세요"
    )
    assert "금융감독원" in minimized.text
    assert "3000000원" in minimized.text
    assert "http://bit.ly/abc" in minimized.text
    assert minimized.removed_total == 0


def test_provider_never_sees_raw_identifiers(contract: LlmContract) -> None:
    """주장이 아니라 관측이다. 실제로 나간 문자열을 꺼내서 본다."""
    text = f"{SUSPICIOUS_TEXT} 본인확인 900101-1234567 계좌 110-234-567890"
    analysis = analyze_fraud(AnalyzeRequest(text=text, state=UserState.RECEIVED_ONLY))
    provider = StubProvider()

    explain_analysis(analysis, text, provider=provider, contract=contract)

    (sent,) = provider.prompts
    assert "900101-1234567" not in sent
    assert "110-234-567890" not in sent
    assert "010-1234-5678" not in sent
    assert "[주민등록번호]" in sent
    assert "[계좌번호]" in sent
    # 신호는 남아야 한다. 계좌번호를 통째로 지우면 무엇이 요구됐는지도 사라진다.
    assert "안전계좌" in sent


def test_message_is_truncated_to_the_contract_limit(response: AnalyzeResponse) -> None:
    contract = LlmContract(
        provider="stub",
        model="stub-1",
        prompt_id="fraud_explanation_v1",
        prompt_sha256=FRAUD_EXPLANATION_PROMPT_SHA256,
        max_input_chars=50,
        timeout_seconds=8.0,
        temperature=0.0,
    )
    provider = StubProvider()

    explain_analysis(response, "가" * 5_000, provider=provider, contract=contract)

    (sent,) = provider.prompts
    assert "가" * 50 in sent
    assert "가" * 51 not in sent


# --- 출력 검증 -------------------------------------------------------------


def test_official_numbers_from_the_evidence_are_allowed(
    response: AnalyzeResponse,
) -> None:
    grounded = build_grounded_text(response)
    assert "1394" in grounded, "이 시나리오는 1394 안내를 포함해야 한다"

    kept = validate_explanation(
        "이 문자는 정상 절차와 다릅니다. 1394로 상담하세요.",
        grounded_text=grounded,
        max_chars=MAX_EXPLANATION_CHARS,
        risk_level="high",
    )
    assert "1394" in kept


def test_invented_contact_is_rejected(response: AnalyzeResponse) -> None:
    """가장 나쁜 실패다. 사용자가 그 번호로 실제로 전화를 건다."""
    with pytest.raises(LlmOutputRejected, match="contacts absent"):
        validate_explanation(
            "안심하세요. 02-9999-8888 로 전화하면 해결됩니다.",
            grounded_text=build_grounded_text(response),
            max_chars=MAX_EXPLANATION_CHARS,
            risk_level="high",
        )


@pytest.mark.parametrize(
    "output",
    [
        "",
        "   ",
        "자세한 내용은 https://finshield.example.com 에서 확인하세요.",
        "www.fss.or.kr 을 방문하세요.",
        "예시로 900101-1234567 같은 번호를 말합니다.",
    ],
)
def test_malformed_output_is_rejected(response: AnalyzeResponse, output: str) -> None:
    with pytest.raises(LlmOutputRejected):
        validate_explanation(
            output,
            grounded_text=build_grounded_text(response),
            max_chars=MAX_EXPLANATION_CHARS,
            risk_level="high",
        )


def test_over_length_output_is_rejected(response: AnalyzeResponse) -> None:
    with pytest.raises(LlmOutputRejected, match="limit is"):
        validate_explanation(
            "설" * (MAX_EXPLANATION_CHARS + 1),
            grounded_text=build_grounded_text(response),
            max_chars=MAX_EXPLANATION_CHARS,
            risk_level="high",
        )


# --- 실패 처리와 판정 경계 -------------------------------------------------


def test_unavailable_provider_yields_no_explanation(
    response: AnalyzeResponse, contract: LlmContract
) -> None:
    class DeadProvider:
        name = "stub"

        def generate(self, *, contract: LlmContract, prompt: str) -> str:
            raise LlmUnavailable("timeout")

    assert (
        explain_analysis(
            response, SUSPICIOUS_TEXT, provider=DeadProvider(), contract=contract
        )
        is None
    )


def test_stub_refuses_a_contract_for_another_provider(
    response: AnalyzeResponse,
) -> None:
    """실제 프로바이더 계약이 stub 으로 잘못 흘러도 조용히 성공하지 않는다."""
    vertex_contract = fraud_explanation_contract(
        provider="google_vertex", model="gemini-2.0-flash"
    )
    assert (
        explain_analysis(
            response, SUSPICIOUS_TEXT, provider=StubProvider(), contract=vertex_contract
        )
        is None
    )


def test_rejected_output_yields_no_explanation(
    response: AnalyzeResponse, contract: LlmContract
) -> None:
    provider = StubProvider(response="지금 당장 02-9999-8888 로 전화하세요.")
    assert (
        explain_analysis(
            response, SUSPICIOUS_TEXT, provider=provider, contract=contract
        )
        is None
    )


@pytest.mark.parametrize(
    "model_output",
    [
        "이 문자는 안전합니다. 위험하지 않으니 안심하고 이체하세요.",
        "위험 수준: low. 점수 0점.",
        "설명",
        "",
    ],
)
def test_the_verdict_survives_any_model_output(
    contract: LlmContract, model_output: str
) -> None:
    """`CLAUDE.md` 의 첫 번째 non-negotiable 을 타입으로 지킨다.

    `explain_analysis` 는 `AnalyzeResponse` 를 돌려주지 않으므로 모델이 판정을
    뒤집을 경로가 존재하지 않는다. 여기서는 그 경계를 실제로 확인한다 - 모델이
    "안전합니다" 라고 답해도 위험 수준·점수·행동이 그대로인지.
    """
    analysis = analyze_fraud(
        AnalyzeRequest(text=SUSPICIOUS_TEXT, state=UserState.SHARED_ACCOUNT_ACCESS)
    )
    before = analysis.model_dump()

    explanation = explain_analysis(
        analysis,
        SUSPICIOUS_TEXT,
        provider=StubProvider(response=model_output),
        contract=contract,
    )

    assert analysis.model_dump() == before
    assert analysis.risk_level == "high"
    assert explanation is None or isinstance(explanation, str)
