"""설명 계층을 셋 하나에 통째로 태운다. **유료 호출이 나간다.**

`docs/34` 9절의 "분모를 채우는 일" 이 이 스크립트다. 계측은 2026-08-24 에 들어갔고
어휘도 집합도 준비돼 있었지만, 유료 실행을 하지 않았으므로 모든 비율의 분모가 0
이었다. 계측이 있다는 것과 측정했다는 것은 다르다.

사용:

    FINSHIELD_LLM_PROVIDER=google_ai_studio \\
    GEMINI_API_KEY_FILE=secrets/gemini_api_key.txt \\
    python -m scripts.run_explanation_probe \\
      --dataset evaluation/data/fraud_holdout_v1.3.jsonl \\
      --output evaluation/results/explanation-probe-fraud-holdout-v1.3.json

`--dataset` 과 `--output` 에 기본값을 주지 않았다. `run_llm_fraud_judge` 는 기본
출력이 개발셋 결과라 홀드아웃을 돌릴 때 덮어쓸 수 있었고, 그 함정을 한 번 밟은
뒤로는 같은 모양을 다시 만들지 않는다. 어느 셋을 재는지 매번 적게 한다.

`--limit` 으로 몇 건만 먼저 돌려 볼 것. 대체 모델까지 가면 사례 하나가 호출 둘이다.

프로바이더·모델·타임아웃·순서를 이 스크립트가 정하지 않는다. 전부
`build_explanation_runtime()` 에서 온다 — 스크립트가 자기만의 조립 경로를 가지면,
여기서 잰 숫자가 배포된 것과 다른 구성의 숫자가 된다.

이 스크립트는 원문도, 모델이 만든 설명 문장도 출력하지 않고 저장하지도 않는다.
남는 것은 건수·사유·소요시간·글자 수뿐이다
(`adr/0006-privacy-safe-observability.md`).
"""

from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from app.services.fraud_analysis import analyze_fraud
from app.services.llm.explanation import (
    EXPLANATION_CALL_POLICY,
    MAX_EXPLANATION_CHARS,
)
from app.services.llm.runtime import (
    PROVIDER_SETTING,
    LlmRuntimeConfigurationError,
    build_explanation_runtime,
)
from evaluation.explanation_probe import ExplanationProbeRun, probe_case, summarize
from evaluation.fraud_benchmark import normalized_dataset_sha256
from evaluation.fraud_golden import load_golden_cases


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="앞에서 N건만 부른다. 0 이면 전부. 프롬프트 확인용.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="동시 호출 수. 올리면 빨라지지만 429 를 받을 확률도 올라간다.",
    )
    args = parser.parse_args()

    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1")

    selected = os.environ.get(PROVIDER_SETTING, "").strip().lower()
    if selected not in {"google_ai_studio", "stub"}:
        raise SystemExit(
            f"{PROVIDER_SETTING} 가 google_ai_studio 여야 한다 (현재: {selected!r}). "
            "유료 호출이 나가는 스크립트라 기본값으로는 돌지 않는다. "
            "배관만 확인하려면 stub."
        )

    try:
        runtime = build_explanation_runtime(os.environ)
    except LlmRuntimeConfigurationError as exc:
        raise SystemExit(f"설명 런타임을 조립하지 못했다: {exc}") from exc
    if runtime is None:
        raise SystemExit("설명 계층이 꺼져 있다.")

    cases = load_golden_cases(args.dataset)
    dataset_sha256 = normalized_dataset_sha256(cases)
    if args.limit:
        cases = cases[: args.limit]

    # 판정은 결정론이고 네트워크가 없다. 먼저 전부 계산해 두면, 유료 구간에서
    # 엔진 예외가 터져 이미 태운 호출을 잃는 일이 없다.
    responses = [analyze_fraud(case.request()) for case in cases]

    models = tuple(contract.model for contract in runtime.contracts)
    print(f"설명 시작: {len(cases)}건, models={models}, 동시 {args.concurrency}")

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        probed = list(
            pool.map(
                lambda pair: probe_case(
                    pair[0].case_id,
                    pair[1],
                    pair[0].text,
                    provider=runtime.provider,
                    contracts=runtime.contracts,
                ),
                zip(cases, responses, strict=True),
            )
        )

    first = runtime.contracts[0]
    run = ExplanationProbeRun(
        probed_at=datetime.now(UTC).isoformat(timespec="seconds"),
        dataset_id=args.dataset.stem,
        dataset_sha256=dataset_sha256,
        provider=first.provider,
        contracts=models,
        prompt_id=first.prompt_id,
        prompt_sha256=first.prompt_sha256,
        call_policy=EXPLANATION_CALL_POLICY,
        temperature=first.temperature,
        max_chars=MAX_EXPLANATION_CHARS,
        cases=tuple(probed),
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(run.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )

    report = summarize(run)
    print(f"기록: {args.output} ({len(run.cases)}건)")
    # 사유의 **종류**만 찍는다. 설명 문장은 찍지 않는다.
    print(
        f"  물어본 건수 {report['asked']}/{report['cases']} "
        f"(근거가 없어 안 부름 {report['not_asked_no_evidence']}건)"
    )
    print(
        f"  설명 성공 {report['explained']}/{report['asked']} "
        f"({report['explained_rate']}), 대체 모델 {report['fell_back_to_second_model']}건"
    )
    print(f"  근거 이탈 {report['grounding_departures']}건 "
          f"(지어낸 연락처 {report['invented_contacts']}건)")
    print(f"  안전 필터 차단 {report['safety_blocks']}건 "
          f"(요청 {report['prompt_blocked']} / 응답 {report['safety_blocked']})")
    for model, stats in report["per_model"].items():  # type: ignore[union-attr]
        print(f"  {model}: {stats['ok']}/{stats['attempts']} "
              f"p50 {stats['p50_ms']}ms p95 {stats['p95_ms']}ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
