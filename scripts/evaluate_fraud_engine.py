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
from evaluation.fraud_benchmark import check_minimum_quality, evaluate_golden_set
from evaluation.fraud_golden import FraudGoldenCase, GOLDEN_SET_PATH, load_golden_cases


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=GOLDEN_SET_PATH)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--performance-repeats", type=int, default=0)
    args = parser.parse_args()

    if args.performance_repeats < 0:
        parser.error("--performance-repeats must be zero or greater")

    cases = load_golden_cases(args.dataset)
    report = {
        "report_version": "fraud_benchmark_v0.1",
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        **evaluate_golden_set(cases),
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
