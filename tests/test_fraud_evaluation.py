import asyncio

import pytest
from pydantic import ValidationError

from app.schemas.analysis import AnalyzeRequest
from app.services.fraud_analysis import analyze_fraud
from evaluation.fraud_benchmark import check_minimum_quality, evaluate_golden_set
from evaluation.fraud_golden import FraudGoldenCase, load_golden_cases
from scripts.evaluate_fraud_engine import measure_asgi_latency, percentile


def test_golden_set_is_synthetic_versioned_and_covers_every_state() -> None:
    cases = load_golden_cases()

    assert len(cases) == 61
    assert all(case.synthetic for case in cases)
    assert len({case.case_id for case in cases}) == len(cases)
    assert {case.state.value for case in cases} == {
        "received_only",
        "clicked_link",
        "shared_personal_info",
        "shared_account_access",
        "installed_app",
        "received_unknown_money",
        "transferred_money",
    }
    state_counts = {
        state: sum(case.state.value == state for case in cases)
        for state in {case.state.value for case in cases}
    }
    assert min(state_counts.values()) >= 3


def test_scenario_engine_meets_bootstrap_quality_gate_without_claiming_llm() -> None:
    report = evaluate_golden_set(load_golden_cases())

    assert check_minimum_quality(report) == []
    assert report["llm_only"]["status"] == "not_run"  # type: ignore[index]
    assert report["proposed_hybrid"]["status"] == "not_implemented"  # type: ignore[index]
    assert report["dataset"]["held_out"] is False  # type: ignore[index]
    assert len(report["dataset"]["normalized_sha256"]) == 64  # type: ignore[index]


def test_known_bootstrap_errors_remain_visible_in_report() -> None:
    report = evaluate_golden_set(load_golden_cases())
    engine = report["scenario_engine_v0_1"]  # type: ignore[assignment]
    errors = engine["errors"]  # type: ignore[index]

    assert errors == {
        "false_positive_case_ids": ["fg-049"],
        "false_negative_case_ids": ["fg-046", "fg-047"],
    }


def test_explicit_prevention_context_is_not_classified_as_fraud() -> None:
    prevention_messages = (
        "OTP와 비밀번호는 누구에게도 절대 알려주지 마세요.",
        "경찰과 금융기관은 안전계좌 송금을 요구하지 않습니다.",
        "출처가 불분명한 앱 설치나 원격제어를 허용하지 마세요.",
        "제가 신청한 카드 배송 조회를 공식 앱에서 확인했습니다.",
    )

    for text in prevention_messages:
        response = analyze_fraud(AnalyzeRequest(text=text))
        assert response.fraud_types == []


def test_prevention_phrase_does_not_hide_a_later_direct_request() -> None:
    response = analyze_fraud(
        AnalyzeRequest(
            text=(
                "OTP는 알려주지 마세요. 하지만 지금 본인 확인을 위해 "
                "인증번호를 답장해 주세요."
            )
        )
    )

    assert "account_access_request" in response.fraud_types
    assert "DO_NOT_SHARE_ACCESS" in {action.code for action in response.actions}


@pytest.mark.parametrize(
    ("text", "fraud_type"),
    (
        (
            "경찰은 안전계좌 송금을 요구하지 않습니다. 하지만 지금 안전계좌로 보내 주세요.",
            "authority_impersonation",
        ),
        (
            "앱 설치는 위험하니 설치하지 마세요. 하지만 이 보안 앱 설치는 지금 설치하세요.",
            "smishing_malware",
        ),
    ),
)
def test_safety_sentence_cannot_mask_a_following_direct_instruction(
    text: str, fraud_type: str
) -> None:
    response = analyze_fraud(AnalyzeRequest(text=text))

    assert fraud_type in response.fraud_types


def test_nearest_rank_percentile_is_deterministic() -> None:
    assert percentile([4.0, 1.0, 3.0, 2.0], 0.50) == 2.0
    assert percentile([4.0, 1.0, 3.0, 2.0], 0.95) == 4.0


def test_golden_case_rejects_labels_outside_public_contract() -> None:
    payload = load_golden_cases()[0].model_dump()
    payload["expected_fraud_types"] = ["invented_type"]

    with pytest.raises(ValidationError, match="unknown fraud type labels"):
        FraudGoldenCase.model_validate(payload)


def test_latency_measurement_uses_the_supplied_case_collection() -> None:
    report = asyncio.run(measure_asgi_latency(load_golden_cases()[:1], repeats=2))

    assert report["sample_count"] == 2
    assert report["scope"] == "in_process_asgi_without_network_or_tls"
