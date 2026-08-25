import argparse
import asyncio
import json
import logging
import math
import platform
from pathlib import Path
from time import perf_counter

import httpx

from app.main import app
from evaluation.explanation_probe import ExplanationProbeRun
from evaluation.fraud_benchmark import check_minimum_quality, evaluate_golden_set
from evaluation.fraud_golden import FraudGoldenCase, GOLDEN_SET_PATH, load_golden_cases
from evaluation.llm_judge import JUDGE_RUN_PATH, LlmJudgeRun


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * quantile) - 1)
    return round(ordered[index], 3)


async def measure_asgi_latency(
    cases: list[FraudGoldenCase], repeats: int
) -> dict[str, float | int | str]:
    samples: list[float] = []
    request_logger = logging.getLogger("finshield.request")
    previous_disabled = request_logger.disabled
    request_logger.disabled = True
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://benchmark"
        ) as client:
            for case in cases[:5]:
                await client.post(
                    "/api/v1/analyze", json=case.request().model_dump(mode="json")
                )
            for _ in range(repeats):
                for case in cases:
                    started_at = perf_counter()
                    response = await client.post(
                        "/api/v1/analyze",
                        json=case.request().model_dump(mode="json"),
                    )
                    response.raise_for_status()
                    samples.append((perf_counter() - started_at) * 1000)
    finally:
        request_logger.disabled = previous_disabled
    return {
        "scope": "in_process_asgi_without_network_or_tls",
        "sample_count": len(samples),
        "p50_ms": percentile(samples, 0.50),
        "p95_ms": percentile(samples, 0.95),
        "max_ms": round(max(samples), 3),
    }


def load_llm_run(path: Path) -> LlmJudgeRun | None:
    """모델 판정 결과를 읽는다. 없으면 `None`, 그러면 LLM 구간은 `not_run` 이다.

    이 스크립트는 **네트워크를 쓰지 않는다.** CI 가 매 푸시마다 돌리는 명령이라
    유료 호출이 여기서 나가면 안 된다. 판정은 `scripts/run_llm_fraud_judge.py`
    가 한 번 하고, 여기는 그 결과 파일을 읽어 집계만 한다.
    """
    if not path.exists():
        return None
    return LlmJudgeRun.model_validate_json(path.read_text(encoding="utf-8"))


def load_explanation_probe(path: Path | None) -> ExplanationProbeRun | None:
    """설명 계층 실행 결과를 읽는다. 없으면 `None`, 그러면 그 칸은 `not_measured`.

    `load_llm_run` 과 같은 규율이다 - 여기서 유료 호출이 나가지 않는다. 설명은
    `scripts/run_explanation_probe.py` 가 한 번 태우고, 이쪽은 그 파일을 읽는다.

    기본값을 주지 않는다. 판정 쪽은 기본 경로가 개발셋 결과라 홀드아웃을 돌릴 때
    엉뚱한 파일을 읽는 문제가 있었고, 그것을 `--dataset` 비교로 무마해야 했다.
    여기서는 처음부터 지정하게 한다.
    """
    if path is None or not path.exists():
        return None
    return ExplanationProbeRun.model_validate_json(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=GOLDEN_SET_PATH)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--performance-repeats", type=int, default=0)
    parser.add_argument(
        "--llm-judgements",
        type=Path,
        default=JUDGE_RUN_PATH,
        help="모델 단독 판정 결과 파일. 없으면 LLM 구간을 not_run 으로 남긴다.",
    )
    parser.add_argument(
        "--explanation-probe",
        type=Path,
        default=None,
        help=(
            "설명 계층 실행 결과 파일. 없으면 explanation_layer 를 "
            "not_measured 로 남긴다."
        ),
    )
    args = parser.parse_args()

    if args.performance_repeats < 0:
        parser.error("--performance-repeats must be zero or greater")

    cases = load_golden_cases(args.dataset)

    # 기본 판정 결과 파일은 **개발셋을 채점한 것**이다. 다른 데이터셋을 돌리면서
    # 그 파일을 그대로 읽으면 sha256 이 어긋나 `stale` 이 뜨고, 품질 게이트는
    # 그것을 "다시 재라" 로 읽는다. 여기서는 낡은 게 아니라 애초에 다른 셋이다.
    # 그 셋의 모델 판정을 보고 싶으면 `--llm-judgements` 로 직접 지정한다.
    judgements = args.llm_judgements
    if args.dataset != GOLDEN_SET_PATH and judgements == JUDGE_RUN_PATH:
        judgements = None

    report = {
        "report_version": "fraud_benchmark_v0.1",
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        **evaluate_golden_set(
            cases,
            llm_run=load_llm_run(judgements) if judgements else None,
            explanation_probe=load_explanation_probe(args.explanation_probe),
            dataset_id=args.dataset.stem,
        ),
    }
    if args.performance_repeats:
        report["api_latency"] = asyncio.run(
            measure_asgi_latency(cases, args.performance_repeats)
        )

    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")

    failures = check_minimum_quality(report)
    if args.check and failures:
        print(f"quality gate failed: {', '.join(failures)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
