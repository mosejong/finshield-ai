import asyncio

import pytest
from pydantic import ValidationError

from app.schemas.analysis import AnalyzeRequest, Persona, UserState
from app.services.fraud_analysis import analyze_fraud
from app.services.llm.contract import LlmContractError
from app.services.llm.provider import LlmProvider, LlmUnavailable
from evaluation.fraud_benchmark import (
    FRAUD_TYPES,
    check_minimum_quality,
    evaluate_golden_set,
    normalized_dataset_sha256,
)
from evaluation.fraud_golden import (
    FraudGoldenCase,
    _validate_collection,
    is_held_out,
    load_golden_cases,
    load_holdout_cases,
)
from evaluation.llm_judge import (
    FRAUD_JUDGE_PROMPT,
    JUDGE_RUN_PATH,
    LlmJudgement,
    LlmJudgeRun,
    build_judge_prompt,
    fraud_judge_contract,
    judge_case,
    parse_judgement,
)
from scripts.evaluate_fraud_engine import load_llm_run, measure_asgi_latency, percentile


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


# --- held-out 셋 ----------------------------------------------------------
#
# 여기에는 **성능 단언이 없다.** 있으면 CI 가 빨개질 때마다 held-out 셋을 보고
# 규칙을 고치게 되고, 그 순간 held-out 이 아니게 된다. 이 셋에 대해 CI 가 지키는
# 것은 라벨 무결성과 개발셋과의 분리뿐이다. 숫자는 사람이 날짜를 붙여 잰다
# (`evaluation/results/fraud-holdout-v0.2.json`).


def test_holdout_set_is_labelled_and_separated_from_the_development_set() -> None:
    holdout = load_holdout_cases()
    development = load_golden_cases()

    assert len(holdout) == 72
    assert is_held_out(holdout)
    assert not is_held_out(development)
    assert all(case.synthetic for case in holdout)
    assert {case.case_id for case in holdout}.isdisjoint(
        case.case_id for case in development
    )
    # 문장이 겹치면 개발셋에서 고친 것이 held-out 점수로 되돌아온다.
    assert {case.text for case in holdout}.isdisjoint(
        case.text for case in development
    )


def test_holdout_covers_every_state_persona_and_fraud_type() -> None:
    holdout = load_holdout_cases()

    assert {case.state.value for case in holdout} == {state.value for state in UserState}
    assert {case.persona.value for case in holdout} == {p.value for p in Persona}
    covered = {t for case in holdout for t in case.expected_fraud_types}
    assert covered == set(FRAUD_TYPES)
    # 부정 사례가 없으면 오탐률을 잴 수 없다.
    assert sum(not case.is_fraud for case in holdout) >= 20


def test_a_dataset_cannot_be_half_held_out() -> None:
    mixed = load_holdout_cases()[:40] + load_golden_cases()[:40]

    with pytest.raises(ValueError, match="entirely held-out or entirely not"):
        _validate_collection(mixed)


def test_a_holdout_case_cannot_be_smuggled_in_under_a_development_id() -> None:
    payload = load_holdout_cases()[0].model_dump()
    payload["case_id"] = "fg-900"

    with pytest.raises(ValueError, match="case ID prefix must match held_out"):
        _validate_collection([FraudGoldenCase.model_validate(payload)])


def test_report_records_which_dataset_it_describes() -> None:
    report = evaluate_golden_set(
        load_holdout_cases(), dataset_id="fraud_holdout_v0.2"
    )

    assert report["dataset"]["id"] == "fraud_holdout_v0.2"  # type: ignore[index]
    assert report["dataset"]["held_out"] is True  # type: ignore[index]


def test_scenario_engine_meets_bootstrap_quality_gate_without_claiming_llm() -> None:
    # 판정 파일을 주지 않은 경로다. 모델 숫자가 없어도 엔진 게이트는 그대로
    # 성립해야 한다 - LLM 은 이 게이트의 전제가 아니다.
    report = evaluate_golden_set(load_golden_cases())

    assert check_minimum_quality(report) == []
    assert report["llm_only"]["status"] == "not_run"  # type: ignore[index]
    assert report["dataset"]["held_out"] is False  # type: ignore[index]
    assert len(report["dataset"]["normalized_sha256"]) == 64  # type: ignore[index]


def test_bootstrap_errors_were_fixed_without_deleting_the_hard_cases() -> None:
    # 이 테스트의 원래 목적은 "점수를 좋게 만들려고 어려운 케이스를 지우는 것"을
    # 막는 것이었다. 2026-08-19 어휘 확장(v0.2)으로 세 오류가 실제로 닫혔으므로
    # 목적은 그대로 두고 주장을 바꾼다: 세 케이스가 여전히 셋에 남아 있고,
    # 분모가 61 그대로이며, 그 상태에서 오류 목록이 비어 있어야 한다.
    cases = load_golden_cases()
    case_ids = {case.case_id for case in cases}
    assert {"fg-046", "fg-047", "fg-049"} <= case_ids

    report = evaluate_golden_set(cases)
    engine = report["scenario_engine_v0_1"]  # type: ignore[assignment]
    binary = engine["binary"]  # type: ignore[index]

    counted = (
        binary["true_positive"]
        + binary["true_negative"]
        + binary["false_positive"]
        + binary["false_negative"]
    )
    assert counted == 61

    assert engine["errors"] == {  # type: ignore[index]
        "false_positive_case_ids": [],
        "false_negative_case_ids": [],
    }


def test_previously_failing_cases_are_judged_correctly_one_by_one() -> None:
    # 집계가 아니라 케이스 단위로 못을 박는다. 집계만 보면 어떤 케이스가
    # 왜 통과했는지 알 수 없고, 나중에 어휘를 줄일 때 이 셋이 조용히
    # 되돌아가도 f1 만으로는 눈에 잘 띄지 않는다.
    by_id = {case.case_id: case for case in load_golden_cases()}

    def run(case_id: str):
        case = by_id[case_id]
        return analyze_fraud(AnalyzeRequest(text=case.text, state=case.state))

    fg046 = run("fg-046")
    assert "authority_impersonation" in {signal.code for signal in fg046.signals}
    assert fg046.fraud_types != []

    fg047 = run("fg-047")
    assert "remote_app" in {signal.code for signal in fg047.signals}
    assert fg047.fraud_types != []

    fg049 = run("fg-049")
    assert fg049.signals == []
    assert fg049.fraud_types == []


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


# --- LLM 단독 판정 --------------------------------------------------------
#
# 여기서 지키려는 것은 모델의 점수가 아니라 **집계의 정직성**이다. 모델을
# 유리하게 재는 방법은 셋뿐이고, 셋 다 아래에서 막는다 - 실패한 호출을 빼는 것,
# 빠진 사례를 건너뛰는 것, 다른 데이터로 잰 숫자를 그대로 두는 것.


def _run_with(judgements: list[LlmJudgement], *, dataset_sha256: str) -> LlmJudgeRun:
    return LlmJudgeRun(
        judged_at="2026-08-19T00:00:00+00:00",
        dataset_id="fraud_golden_v0.1",
        dataset_sha256=dataset_sha256,
        provider="google_ai_studio",
        model="gemini-3.6-flash",
        prompt_id="fraud_judge_v1",
        prompt_sha256="0" * 64,
        temperature=0.0,
        judgements=judgements,
    )


def test_llm_numbers_measured_on_another_dataset_are_rejected_not_reused() -> None:
    cases = load_golden_cases()
    stale = _run_with(
        [LlmJudgement(case_id=case.case_id, ok=True, is_fraud=True) for case in cases],
        dataset_sha256="f" * 64,
    )

    report = evaluate_golden_set(cases, llm_run=stale)

    assert report["llm_only"]["status"] == "stale"  # type: ignore[index]
    assert "binary" not in report["llm_only"]  # type: ignore[operator]
    # 게이트가 잡아야 한다. 잡지 않으면 골든셋을 고친 PR 이 옛 숫자를 그대로
    # 끌고 병합된다.
    assert "llm_only_stale" in check_minimum_quality(report)


def test_a_call_that_never_answered_counts_as_no_warning() -> None:
    cases = load_golden_cases()
    run = _run_with(
        [
            LlmJudgement(case_id=case.case_id, ok=False, failure="timeout")
            for case in cases
        ],
        dataset_sha256=normalized_dataset_sha256(cases),
    )

    section = evaluate_golden_set(cases, llm_run=run)["llm_only"]

    assert section["run"]["failure_count"] == len(cases)  # type: ignore[index]
    # 실패를 빼고 채점하면 분모가 0 이 되어 점수가 사라진다. 사용자 입장에서
    # 답이 없는 것은 경고가 없는 것이므로 재현율 0 으로 남는다.
    assert section["binary"]["recall"] == 0.0  # type: ignore[index]


def test_cases_the_model_was_never_asked_about_are_not_dropped() -> None:
    cases = load_golden_cases()
    run = _run_with(
        [LlmJudgement(case_id=cases[0].case_id, ok=True, is_fraud=True)],
        dataset_sha256=normalized_dataset_sha256(cases),
    )

    section = evaluate_golden_set(cases, llm_run=run)["llm_only"]

    assert section["run"]["case_count"] == len(cases)  # type: ignore[index]
    assert section["run"]["failure_kinds"] == {"missing_judgement": len(cases) - 1}  # type: ignore[index]


def test_the_shipped_hybrid_detects_exactly_what_the_engine_detects() -> None:
    # 설명 계층은 판정을 바꿀 수 없다. 이 등식이 깨지는 날은 CLAUDE.md 의 첫
    # non-negotiable 이 깨진 날이다.
    report = evaluate_golden_set(load_golden_cases())

    assert report["hybrid_v0_1"]["binary"] == report["scenario_engine_v0_1"]["binary"]  # type: ignore[index]
    assert report["hybrid_v0_1"]["detection_identical_to"] == "scenario_engine_v0_1"  # type: ignore[index]


def test_committed_judgement_run_still_describes_the_committed_dataset() -> None:
    # 커밋된 두 파일이 서로 어긋난 채 병합되는 것을 막는다. 골든셋을 고치고
    # 재측정을 잊으면 여기서 걸린다.
    run = load_llm_run(JUDGE_RUN_PATH)
    if run is None:
        pytest.skip("판정 결과 파일이 없다")

    cases = load_golden_cases()
    assert run.dataset_sha256 == normalized_dataset_sha256(cases)
    assert {judgement.case_id for judgement in run.judgements} == {
        case.case_id for case in cases
    }


# --- 판정 계약 ------------------------------------------------------------


def test_judge_prompt_is_pinned_to_its_hash() -> None:
    contract = fraud_judge_contract(provider="stub")
    contract.verify_prompt(FRAUD_JUDGE_PROMPT)

    with pytest.raises(LlmContractError, match="does not match the pinned hash"):
        contract.verify_prompt(FRAUD_JUDGE_PROMPT + " ")


def test_personal_identifiers_do_not_leave_with_the_judge_prompt() -> None:
    prompt = build_judge_prompt(
        persona="unknown",
        state="received_only",
        message="900101-1234567 계좌 123-456-7890 으로 010-1234-5678 에 연락",
        max_input_chars=4_000,
    )

    assert "900101-1234567" not in prompt
    assert "010-1234-5678" not in prompt
    assert "123-456-7890" not in prompt
    # 무엇이 요구됐는지는 남아야 한다. 통째로 지우면 신호까지 사라진다.
    assert "[계좌번호]" in prompt


def test_a_code_fence_does_not_throw_away_a_valid_judgement() -> None:
    judgement = parse_judgement(
        "fg-001",
        '```json\n{"is_fraud": true, "fraud_types": ["authority_impersonation"], '
        '"risk_level": "high", "actions": ["STOP_CONTACT"]}\n```',
        latency_ms=1.0,
    )

    assert judgement.ok
    assert judgement.fraud_types == ["authority_impersonation"]


def test_codes_outside_the_contract_are_dropped_and_recorded() -> None:
    judgement = parse_judgement(
        "fg-001",
        '{"is_fraud": true, "fraud_types": ["romance_scam"], '
        '"risk_level": "high", "actions": ["CALL_MY_LAWYER", "STOP_CONTACT"]}',
        latency_ms=1.0,
    )

    assert judgement.fraud_types == []
    assert judgement.actions == ["STOP_CONTACT"]
    assert judgement.dropped_codes == ["romance_scam", "CALL_MY_LAWYER"]


@pytest.mark.parametrize(
    ("raw", "failure"),
    (
        ("판정: 사기입니다", "unparsable_json"),
        ("[]", "not_an_object"),
        ('{"is_fraud": true, "risk_level": "critical"}', "unknown_risk_level"),
        ('{"risk_level": "high"}', "missing_is_fraud"),
    ),
)
def test_output_we_cannot_score_is_recorded_as_a_failure(
    raw: str, failure: str
) -> None:
    judgement = parse_judgement("fg-001", raw, latency_ms=1.0)

    assert not judgement.ok
    assert judgement.failure == failure


def test_one_dead_call_does_not_abandon_the_rest_of_the_batch() -> None:
    class DeadProvider:
        name = "stub"

        def generate(self, *, contract: object, prompt: str) -> str:
            raise LlmUnavailable("stub returned HTTP 503")

    provider: LlmProvider = DeadProvider()  # type: ignore[assignment]
    judgement = judge_case(
        case_id="fg-001",
        persona="unknown",
        state="received_only",
        message="검찰입니다. 지금 송금하세요.",
        provider=provider,
        contract=fraud_judge_contract(provider="stub"),
        clock=lambda: 0.0,
    )

    assert not judgement.ok
    assert judgement.failure == "stub returned HTTP 503"
