from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass
from hashlib import sha256

from app.domain.fraud.signals import detect_legacy_signals
from app.schemas.analysis import AnalyzeResponse
from app.services.fraud_analysis import analyze_fraud
from evaluation.fraud_golden import FraudGoldenCase, RISK_RANK


FRAUD_TYPES = (
    "authority_impersonation",
    "loan_policy_impersonation",
    "account_access_request",
    "money_mule_transfer",
    "smishing_malware",
    "card_delivery_impersonation",
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


def evaluate_golden_set(cases: list[FraudGoldenCase]) -> dict[str, object]:
    responses = [analyze_fraud(case.request()) for case in cases]
    scenario_predictions = [bool(response.fraud_types) for response in responses]
    legacy_predictions = [bool(detect_legacy_signals(case.text)) for case in cases]
    truth = [case.is_fraud for case in cases]

    return {
        "dataset": {
            "id": "fraud_golden_v0.1",
            "normalized_sha256": _normalized_dataset_sha256(cases),
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
            "held_out": False,
        },
        "legacy_rule_v0": {
            "scope": "legacy five-keyword public compatibility baseline",
            "binary": asdict(_binary_metrics(truth, legacy_predictions)),
            "errors": _binary_error_case_ids(cases, legacy_predictions),
        },
        "scenario_engine_v0_1": {
            "scope": "deterministic signals, taxonomy, state policy and evidence",
            "binary": asdict(_binary_metrics(truth, scenario_predictions)),
            "errors": _binary_error_case_ids(cases, scenario_predictions),
            "fraud_types": _fraud_type_metrics(cases, responses),
            "required_signal_coverage": _required_signal_coverage(cases, responses),
            "scenario_policy_accuracy": _scenario_policy_accuracy(cases, responses),
            "required_action_coverage": _required_action_coverage(cases, responses),
            "evidence_coverage": _evidence_coverage(responses),
        },
        "llm_only": {
            "status": "not_run",
            "reason": "No pinned model, prompt, provider contract or safe evaluation budget is configured.",
        },
        "proposed_hybrid": {
            "status": "not_implemented",
            "reason": "The current v0.1 engine is deterministic; an LLM explanation layer is not part of this benchmark.",
        },
    }


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
    return [name for name, value, passes in checks if not passes(value)]


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


def _ratio(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _normalized_dataset_sha256(cases: list[FraudGoldenCase]) -> str:
    normalized = "\n".join(
        case.model_dump_json(exclude_none=False) for case in cases
    ).encode("utf-8")
    return sha256(normalized).hexdigest()
