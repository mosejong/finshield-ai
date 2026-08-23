from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass
from hashlib import sha256
from math import ceil

from app.domain.fraud.signals import detect_legacy_signals
from app.schemas.analysis import AnalyzeResponse
from app.services.fraud_analysis import analyze_fraud
from evaluation.fraud_golden import FraudGoldenCase, RISK_RANK, is_held_out
from evaluation.llm_judge import LlmJudgement, LlmJudgeRun


FRAUD_TYPES = (
    "authority_impersonation",
    "acquaintance_impersonation",
    "loan_policy_impersonation",
    "investment_scheme",
    "advance_fee_demand",
    "account_access_request",
    "money_mule_transfer",
    "smishing_malware",
    "card_delivery_impersonation",
    # v0.7 동결 시점에는 엔진이 내지 못하는 유형이다. 그래도 여기 적는다 -
    # 빠져 있으면 per-type 표에서 통째로 사라져, 동결 시점 f1 이 0.0 이라는
    # 사실 자체가 기록되지 않는다. 출발점이 없으면 수정의 값도 없다.
    "isolation_coercion",
)


@dataclass(frozen=True)
class BinaryMetrics:
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    precision: float
    recall: float
    f1: float
    false_positive_rate: float
    accuracy: float


def evaluate_golden_set(
    cases: list[FraudGoldenCase],
    *,
    llm_run: LlmJudgeRun | None = None,
    dataset_id: str = "fraud_golden_v0.1",
) -> dict[str, object]:
    responses = [analyze_fraud(case.request()) for case in cases]
    scenario_predictions = [bool(response.fraud_types) for response in responses]
    legacy_predictions = [bool(detect_legacy_signals(case.text)) for case in cases]
    truth = [case.is_fraud for case in cases]
    dataset_sha256 = normalized_dataset_sha256(cases)

    engine = {
        "scope": "deterministic signals, taxonomy, state policy and evidence",
        "binary": asdict(_binary_metrics(truth, scenario_predictions)),
        "errors": _binary_error_case_ids(cases, scenario_predictions),
        "fraud_types": _fraud_type_metrics(cases, responses),
        "required_signal_coverage": _required_signal_coverage(cases, responses),
        "scenario_policy_accuracy": _scenario_policy_accuracy(cases, responses),
        "risk_ceiling_accuracy": _risk_ceiling_accuracy(cases, responses),
        "required_action_coverage": _required_action_coverage(cases, responses),
        "evidence_coverage": _evidence_coverage(responses),
    }

    return {
        "dataset": {
            "id": dataset_id,
            "normalized_sha256": dataset_sha256,
            "case_count": len(cases),
            "positive_count": sum(truth),
            "negative_count": len(cases) - sum(truth),
            "persona_counts": dict(
                sorted(Counter(case.persona.value for case in cases).items())
            ),
            "state_counts": dict(
                sorted(Counter(case.state.value for case in cases).items())
            ),
            "source_kind": "locally_authored_synthetic_reviewed",
            "held_out": is_held_out(cases),
        },
        "legacy_rule_v0": {
            "scope": "legacy five-keyword public compatibility baseline",
            "binary": asdict(_binary_metrics(truth, legacy_predictions)),
            "errors": _binary_error_case_ids(cases, legacy_predictions),
        },
        "scenario_engine_v0_1": engine,
        "llm_only": _llm_only_section(cases, llm_run, dataset_sha256),
        "hybrid_v0_1": _hybrid_section(
            cases, engine, truth, scenario_predictions, llm_run, dataset_sha256
        ),
    }


def _llm_only_section(
    cases: list[FraudGoldenCase],
    run: LlmJudgeRun | None,
    dataset_sha256: str,
) -> dict[str, object]:
    """모델 단독 판정 구간.

    비어 있는 상태를 두 가지로 나눈다. **한 번도 돌리지 않은 것**과 **다른
    데이터로 돌린 것**은 다르다. 후자를 그대로 실으면 골든셋을 고친 뒤에도 옛
    숫자가 새 데이터의 성능인 척 남는다 - 프롬프트를 sha256 으로 고정한 것과
    같은 이유로 여기도 sha256 을 본다.
    """
    if run is None:
        return {
            "status": "not_run",
            "reason": (
                "판정 실행 결과 파일이 없다. "
                "`python -m scripts.run_llm_fraud_judge` 가 유료 호출로 만든다."
            ),
        }
    if run.dataset_sha256 != dataset_sha256:
        return {
            "status": "stale",
            "reason": (
                "판정 실행 결과가 지금 골든셋과 다른 데이터에서 나왔다. "
                "다시 돌리거나, 비교를 포기하고 결과 파일을 지운다."
            ),
            "judged_dataset_sha256": run.dataset_sha256,
            "current_dataset_sha256": dataset_sha256,
        }

    judgements = _aligned_judgements(cases, run)
    predictions = [judgement.is_fraud for judgement in judgements]
    failures = [judgement for judgement in judgements if not judgement.ok]
    latencies = [judgement.latency_ms for judgement in judgements if judgement.ok]

    return {
        "status": "measured",
        "scope": (
            "the model alone decides fraud, type, risk level and actions "
            "from the message, persona and user state"
        ),
        "contract": {
            "provider": run.provider,
            "model": run.model,
            "prompt_id": run.prompt_id,
            "prompt_sha256": run.prompt_sha256,
            "temperature": run.temperature,
        },
        "run": {
            "judged_at": run.judged_at,
            "dataset_sha256": run.dataset_sha256,
            "case_count": len(judgements),
            "failure_count": len(failures),
            "failure_kinds": dict(
                sorted(Counter(judgement.failure for judgement in failures).items())
            ),
            "invented_code_count": sum(
                len(judgement.dropped_codes) for judgement in judgements
            ),
            "p50_ms": _percentile(latencies, 0.50),
            "p95_ms": _percentile(latencies, 0.95),
        },
        "failure_policy": (
            "답하지 못한 호출은 '경고 없음'으로 집계한다. "
            "빼고 채점하면 모델이 답한 것만 고른 점수가 된다."
        ),
        "binary": asdict(_binary_metrics([case.is_fraud for case in cases], predictions)),
        "errors": _binary_error_case_ids(cases, predictions),
        "fraud_types": _judged_fraud_type_metrics(cases, judgements),
        "scenario_policy_accuracy": _judged_scenario_policy_accuracy(cases, judgements),
        "required_action_coverage": _judged_action_coverage(cases, judgements),
        "evidence_coverage": 0.0,
        "evidence_note": (
            "0.0 은 측정 실패가 아니라 구조다. 이 경로에는 행동을 뒷받침하는 "
            "공식 출처가 없다 - 모델은 근거 ID 를 만들지 않고, 만들게 하면 "
            "그것이야말로 지어낸 근거다."
        ),
        "not_measured": {
            "required_signal_coverage": (
                "signal 코드는 내부 표현이라 제품 출력 어휘가 아니다. "
                "모델에게 주지 않았으므로 채점하지 않는다."
            )
        },
    }


def _hybrid_section(
    cases: list[FraudGoldenCase],
    engine: dict[str, object],
    truth: list[bool],
    scenario_predictions: list[bool],
    run: LlmJudgeRun | None,
    dataset_sha256: str,
) -> dict[str, object]:
    """실제로 배포된 조합.

    탐지 숫자가 `scenario_engine_v0_1` 과 **같다**. 그것이 결함이 아니라 이
    제품의 주장이다 - 설명 계층은 `AnalyzeResponse` 를 받아 문자열을 돌려주므로
    위험 수준·유형·행동을 구조적으로 바꿀 수 없다. 여기서 두 숫자가 달라지는
    날이 오면 `CLAUDE.md` 의 첫 번째 non-negotiable 이 깨진 것이다.

    그래서 이 구간의 값어치는 `alternatives_considered` 에 있다. "규칙에 판정
    권한을 남긴다" 는 선택을, 다른 선택을 했다면 어떤 숫자가 나왔는지와 함께
    남긴다.
    """
    section: dict[str, object] = {
        "status": "measured",
        "scope": (
            "deterministic engine decides; "
            "the model only rewrites that decision in plain Korean"
        ),
        "detection_identical_to": "scenario_engine_v0_1",
        "why_identical": (
            "explain_analysis 는 AnalyzeResponse 를 받아 str | None 을 돌려준다. "
            "설명 계층은 위험 수준·유형·행동을 구조적으로 바꿀 수 없다 "
            "(app/services/llm/explanation.py)."
        ),
        "binary": engine["binary"],
        "scenario_policy_accuracy": engine["scenario_policy_accuracy"],
        "required_action_coverage": engine["required_action_coverage"],
        "evidence_coverage": engine["evidence_coverage"],
        "explanation_layer": {
            "model": "gemini-3.6-flash",
            "fallback_model": "gemini-3.1-flash-lite",
            "measured_in": "docs/34-llm-explanation-runtime.md",
            "note": (
                "설명 문장의 근거 이탈률과 안전 필터 차단율은 아직 측정하지 "
                "않았다. 여기 숫자는 탐지 성능이며 설명 품질이 아니다."
            ),
        },
    }

    if run is None or run.dataset_sha256 != dataset_sha256:
        section["alternatives_considered"] = {
            "status": "not_run",
            "reason": "모델 판정 결과가 없어 조합을 계산할 수 없다.",
        }
        return section

    judgements = _aligned_judgements(cases, run)
    llm_predictions = [judgement.is_fraud for judgement in judgements]
    union = [rule or model for rule, model in zip(scenario_predictions, llm_predictions, strict=True)]
    intersection = [
        rule and model for rule, model in zip(scenario_predictions, llm_predictions, strict=True)
    ]

    section["alternatives_considered"] = {
        "status": "measured",
        "note": (
            "제품에 넣지 않은 조합이다. 규칙에 판정 권한을 둔 선택을 숫자로 "
            "남기기 위해 같은 예측 벡터로 계산했다. 두 조합 모두 모델이 위험 "
            "수준을 움직이게 하므로 CLAUDE.md 의 non-negotiable 과 충돌한다."
        ),
        "rule_or_llm": {
            "scope": "escalate when either the engine or the model calls it fraud",
            "binary": asdict(_binary_metrics(truth, union)),
            "errors": _binary_error_case_ids(cases, union),
        },
        "rule_and_llm": {
            "scope": "warn only when both agree",
            "binary": asdict(_binary_metrics(truth, intersection)),
            "errors": _binary_error_case_ids(cases, intersection),
        },
    }
    return section


def _aligned_judgements(
    cases: list[FraudGoldenCase], run: LlmJudgeRun
) -> list[LlmJudgement]:
    """사례 순서대로 판정을 줄 세운다. 빠진 사례는 실패로 채운다.

    빠뜨린 사례를 조용히 건너뛰면 분모가 줄어 점수가 올라간다.
    """
    by_case_id = run.by_case_id()
    return [
        by_case_id.get(
            case.case_id,
            LlmJudgement(case_id=case.case_id, ok=False, failure="missing_judgement"),
        )
        for case in cases
    ]


def check_minimum_quality(report: dict[str, object]) -> list[str]:
    engine = report["scenario_engine_v0_1"]
    assert isinstance(engine, dict)
    binary = engine["binary"]
    assert isinstance(binary, dict)
    checks: tuple[tuple[str, float, Callable[[float], bool]], ...] = (
        ("precision", float(binary["precision"]), lambda value: value >= 0.75),
        ("recall", float(binary["recall"]), lambda value: value >= 0.65),
        (
            "false_positive_rate",
            float(binary["false_positive_rate"]),
            lambda value: value <= 0.25,
        ),
        (
            "required_action_coverage",
            float(engine["required_action_coverage"]),
            lambda value: value >= 0.90,
        ),
        (
            "required_signal_coverage",
            float(engine["required_signal_coverage"]),
            lambda value: value >= 0.90,
        ),
        (
            "scenario_policy_accuracy",
            float(engine["scenario_policy_accuracy"]),
            lambda value: value >= 0.90,
        ),
        (
            "evidence_coverage",
            float(engine["evidence_coverage"]),
            lambda value: value == 1.0,
        ),
    )
    failures = [name for name, value, passes in checks if not passes(value)]

    # 게이트는 **우리 엔진만** 본다. 모델 쪽 숫자에 기준선을 걸면 구글이 모델을
    # 바꾼 날 우리 CI 가 빨개지고, 그것은 우리가 고칠 수 있는 종류의 실패가 아니다.
    # 대신 "낡은 비교" 는 막는다 - 골든셋을 고쳤는데 옛 판정 결과가 새 데이터의
    # 성능인 척 남아 있는 상태다. 다시 재거나, 비교를 포기하고 결과 파일을 지운다.
    if report.get("llm_only", {}).get("status") == "stale":  # type: ignore[union-attr]
        failures.append("llm_only_stale")
    return failures


def _binary_metrics(truth: list[bool], predicted: list[bool]) -> BinaryMetrics:
    pairs = Counter(zip(truth, predicted, strict=True))
    true_positive = pairs[(True, True)]
    false_positive = pairs[(False, True)]
    true_negative = pairs[(False, False)]
    false_negative = pairs[(True, False)]
    precision = _ratio(true_positive, true_positive + false_positive)
    recall = _ratio(true_positive, true_positive + false_negative)
    return BinaryMetrics(
        true_positive=true_positive,
        false_positive=false_positive,
        true_negative=true_negative,
        false_negative=false_negative,
        precision=precision,
        recall=recall,
        f1=_ratio(2 * precision * recall, precision + recall),
        false_positive_rate=_ratio(false_positive, false_positive + true_negative),
        accuracy=_ratio(true_positive + true_negative, len(truth)),
    )


def _binary_error_case_ids(
    cases: list[FraudGoldenCase], predicted: list[bool]
) -> dict[str, list[str]]:
    return {
        "false_positive_case_ids": [
            case.case_id
            for case, prediction in zip(cases, predicted, strict=True)
            if not case.is_fraud and prediction
        ],
        "false_negative_case_ids": [
            case.case_id
            for case, prediction in zip(cases, predicted, strict=True)
            if case.is_fraud and not prediction
        ],
    }


def _fraud_type_metrics(
    cases: list[FraudGoldenCase], responses: list[AnalyzeResponse]
) -> dict[str, dict[str, float | int]]:
    results: dict[str, dict[str, float | int]] = {}
    for fraud_type in FRAUD_TYPES:
        truth = [fraud_type in case.expected_fraud_types for case in cases]
        predicted = [fraud_type in response.fraud_types for response in responses]
        metrics = _binary_metrics(truth, predicted)
        results[fraud_type] = {
            "support": sum(truth),
            "precision": metrics.precision,
            "recall": metrics.recall,
            "f1": metrics.f1,
        }
    return results


def _required_signal_coverage(
    cases: list[FraudGoldenCase], responses: list[AnalyzeResponse]
) -> float:
    required = 0
    present = 0
    for case, response in zip(cases, responses, strict=True):
        predicted = {signal.code for signal in response.signals}
        required += len(case.required_signal_codes)
        present += len(set(case.required_signal_codes) & predicted)
    return _ratio(present, required)


def _scenario_policy_accuracy(
    cases: list[FraudGoldenCase], responses: list[AnalyzeResponse]
) -> float:
    correct = 0
    for case, response in zip(cases, responses, strict=True):
        risk_ok = RISK_RANK[response.risk_level] >= RISK_RANK[case.expected_min_risk]
        actions = {action.code for action in response.actions}
        actions_ok = set(case.required_action_codes) <= actions
        correct += int(risk_ok and actions_ok)
    return _ratio(correct, len(cases))


def _risk_ceiling_accuracy(
    cases: list[FraudGoldenCase], responses: list[AnalyzeResponse]
) -> float | None:
    """등급이 천장을 넘지 않았는가. 천장을 선언한 사례에서만 잰다.

    `scenario_policy_accuracy` 는 바닥만 본다(`>=`). 그래서 등급을 올리는
    수정은 그 지표에서 점수를 잃을 수 없고, 모든 문자를 high 로 찍는 엔진이
    만점을 받는다. 이 지표가 그 반대편이다.

    천장을 선언한 사례가 하나도 없으면 `None` 을 돌려준다. **1.0 이 아니다.**
    재지 않은 것을 만점으로 적으면 v0.1~v0.6 결과 파일이 이 수정을 통과한
    것처럼 보이는데, 그 셋들은 애초에 이것을 재지 않았다.
    """
    graded = [
        (case, response)
        for case, response in zip(cases, responses, strict=True)
        if case.expected_max_risk is not None
    ]
    if not graded:
        return None
    correct = sum(
        RISK_RANK[response.risk_level] <= RISK_RANK[case.expected_max_risk]
        for case, response in graded
    )
    return _ratio(correct, len(graded))


def _required_action_coverage(
    cases: list[FraudGoldenCase], responses: list[AnalyzeResponse]
) -> float:
    required = 0
    present = 0
    for case, response in zip(cases, responses, strict=True):
        predicted = {action.code for action in response.actions}
        required += len(case.required_action_codes)
        present += len(set(case.required_action_codes) & predicted)
    return _ratio(present, required)


def _evidence_coverage(responses: list[AnalyzeResponse]) -> float:
    with_actions = [response for response in responses if response.actions]
    covered = 0
    for response in with_actions:
        source_ids = {source.source_id for source in response.official_sources}
        if all(
            action.source_ids and set(action.source_ids) <= source_ids
            for action in response.actions
        ):
            covered += 1
    return _ratio(covered, len(with_actions))


def _judged_fraud_type_metrics(
    cases: list[FraudGoldenCase], judgements: list[LlmJudgement]
) -> dict[str, dict[str, float | int]]:
    results: dict[str, dict[str, float | int]] = {}
    for fraud_type in FRAUD_TYPES:
        truth = [fraud_type in case.expected_fraud_types for case in cases]
        predicted = [fraud_type in judgement.fraud_types for judgement in judgements]
        metrics = _binary_metrics(truth, predicted)
        results[fraud_type] = {
            "support": sum(truth),
            "precision": metrics.precision,
            "recall": metrics.recall,
            "f1": metrics.f1,
        }
    return results


def _judged_scenario_policy_accuracy(
    cases: list[FraudGoldenCase], judgements: list[LlmJudgement]
) -> float:
    correct = 0
    for case, judgement in zip(cases, judgements, strict=True):
        risk_ok = RISK_RANK[judgement.risk_level] >= RISK_RANK[case.expected_min_risk]
        actions_ok = set(case.required_action_codes) <= set(judgement.actions)
        correct += int(risk_ok and actions_ok)
    return _ratio(correct, len(cases))


def _judged_action_coverage(
    cases: list[FraudGoldenCase], judgements: list[LlmJudgement]
) -> float:
    required = 0
    present = 0
    for case, judgement in zip(cases, judgements, strict=True):
        required += len(case.required_action_codes)
        present += len(set(case.required_action_codes) & set(judgement.actions))
    return _ratio(present, required)


def _percentile(values: list[float], quantile: float) -> float:
    """`scripts.evaluate_fraud_engine.percentile` 과 같은 nearest-rank 다.

    거기서 import 하지 않는 것은 방향 때문이다 - 평가 라이브러리가 스크립트를
    끌어오면 스크립트를 부르지 않는 테스트도 스크립트를 로드하게 된다.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, ceil(len(ordered) * quantile) - 1)
    return round(ordered[index], 3)


def _ratio(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def normalized_dataset_sha256(cases: list[FraudGoldenCase]) -> str:
    """어떤 **사례와 라벨**로 쟀는지를 식별한다.

    `held_out` 은 뺀다. 그것은 사례의 성질이 아니라 파일의 성질이고, 모델에게
    보낸 적도 채점에 쓴 적도 없다. 넣으면 이 필드를 추가한 것만으로 이미
    돈을 주고 받아 둔 판정 결과가 `stale` 이 된다 - 문장도 라벨도 그대로인데.
    파일이 섞이지 않는다는 보장은 `_validate_collection` 이 따로 한다.

    **선언하지 않은 `expected_max_risk` 도 같은 이유로 뺀다.** v0.7 에서
    등급 천장을 라벨에 더했는데, 그것만으로 v0.1~v0.6 과 개발셋의 해시가
    전부 바뀌었다. 그 셋들의 문장도 라벨도 하나 안 움직였고 천장을 선언한
    적도 없다 - 없는 라벨은 라벨이 아니므로 신원에 들어가지 않는다.
    천장을 **선언한** 셋은 해시가 달라지는 것이 맞고, 그래야 그 셋의 출처
    연결이 진짜다.
    """
    normalized = "\n".join(
        case.model_dump_json(
            exclude_none=False, exclude=_identity_excluded_fields(case)
        )
        for case in cases
    ).encode("utf-8")
    return sha256(normalized).hexdigest()


def _identity_excluded_fields(case: FraudGoldenCase) -> set[str]:
    excluded = {"held_out"}
    if case.expected_max_risk is None:
        excluded.add("expected_max_risk")
    return excluded
