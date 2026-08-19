"""골든셋 61건을 모델에게 통째로 판정시킨다. **유료 호출이 나간다.**

`scripts/evaluate_fraud_engine.py` 와 일부러 분리했다. 저쪽은 CI 가 매 푸시마다
돌리는 명령이고, 네트워크도 비용도 없어야 한다. 이 스크립트가 만든 결과 파일을
저장소에 커밋해 두면 저쪽은 그 파일을 읽어 같은 표를 다시 만든다 - 측정은 한 번,
재현은 무한이다.

사용:

    FINSHIELD_LLM_PROVIDER=google_ai_studio \\
    GEMINI_API_KEY_FILE=secrets/gemini_api_key.txt \\
    python -m scripts.run_llm_fraud_judge

`--limit` 으로 몇 건만 먼저 돌려 프롬프트가 의도대로 나가는지 확인한 뒤 전체를
돌리는 것을 권한다. 61건을 잘못된 프롬프트로 태우는 것보다 3건이 싸다.

이 스크립트는 원문도, 모델 응답 본문도 출력하지 않는다. 진행 상황은 건수와
성공·실패로만 찍는다(`adr/0006-privacy-safe-observability.md`).
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from app.clients.google_ai_studio import (
    GoogleAiStudioConfigurationError,
    build_google_ai_studio_provider,
)
from app.services.llm.provider import LlmProvider, StubProvider
from evaluation.fraud_benchmark import normalized_dataset_sha256
from evaluation.fraud_golden import GOLDEN_SET_PATH, load_golden_cases
from evaluation.llm_judge import (
    JUDGE_MODEL,
    JUDGE_RUN_PATH,
    FRAUD_JUDGE_PROMPT_ID,
    FRAUD_JUDGE_PROMPT_SHA256,
    LlmJudgeRun,
    fraud_judge_contract,
    judge_case,
    merge_judgements,
)

PROVIDER_SETTING = "FINSHIELD_LLM_PROVIDER"


def _build_provider(environ: Mapping[str, str]) -> tuple[LlmProvider, str]:
    """켜져 있지 않으면 돌지 않는다.

    `llm/runtime.py` 의 스위치를 그대로 존중한다. 스크립트가 자기만의 켜는 길을
    가지면, 꺼 놓은 배포에서도 유료 호출이 나가는 경로가 하나 더 생긴다.
    """
    selected = environ.get(PROVIDER_SETTING, "").strip().lower()
    if selected == "stub":
        # 프롬프트 조립과 파일 쓰기까지를 돈 없이 한 번 통과시켜 보는 용도다.
        return StubProvider(response='{"is_fraud": false, "fraud_types": [], '
                            '"risk_level": "low", "actions": []}'), "stub"
    if selected != "google_ai_studio":
        raise SystemExit(
            f"{PROVIDER_SETTING} 가 google_ai_studio 여야 한다 (현재: {selected!r}). "
            "유료 호출이 나가는 스크립트라 기본값으로는 돌지 않는다."
        )
    try:
        return build_google_ai_studio_provider(environ), "google_ai_studio"
    except GoogleAiStudioConfigurationError as exc:
        raise SystemExit(f"API 키를 읽지 못했다: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=GOLDEN_SET_PATH)
    parser.add_argument("--output", type=Path, default=JUDGE_RUN_PATH)
    parser.add_argument("--model", default=JUDGE_MODEL)
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
    parser.add_argument(
        "--resume",
        action="store_true",
        help="기존 결과 파일에 성공으로 남아 있는 사례는 다시 부르지 않는다.",
    )
    args = parser.parse_args()

    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1")

    cases = load_golden_cases(args.dataset)
    dataset_sha256 = normalized_dataset_sha256(cases)

    previous = []
    if args.resume and args.output.exists():
        stored = LlmJudgeRun.model_validate_json(
            args.output.read_text(encoding="utf-8")
        )
        if stored.dataset_sha256 != dataset_sha256:
            raise SystemExit(
                "기존 결과가 다른 골든셋에서 나왔다. --resume 을 빼고 전부 다시 부른다."
            )
        previous = [judgement for judgement in stored.judgements if judgement.ok]
        done = {judgement.case_id for judgement in previous}
        cases = [case for case in cases if case.case_id not in done]
        print(f"resume: {len(done)}건 건너뜀, {len(cases)}건 남음")

    if args.limit:
        cases = cases[: args.limit]

    provider, provider_name = _build_provider(os.environ)
    contract = fraud_judge_contract(provider=provider_name, model=args.model)

    print(f"판정 시작: {len(cases)}건, model={args.model}, 동시 {args.concurrency}")
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        judgements = list(
            pool.map(
                lambda case: judge_case(
                    case_id=case.case_id,
                    persona=case.persona.value,
                    state=case.state.value,
                    message=case.text,
                    provider=provider,
                    contract=contract,
                    clock=perf_counter,
                ),
                cases,
            )
        )

    failures = [judgement for judgement in judgements if not judgement.ok]
    print(f"성공 {len(judgements) - len(failures)}건, 실패 {len(failures)}건")
    for judgement in failures:
        # 사유의 **종류**만 찍는다. 응답 본문은 찍지 않는다.
        print(f"  {judgement.case_id}: {judgement.failure}")

    run = LlmJudgeRun(
        judged_at=datetime.now(UTC).isoformat(timespec="seconds"),
        dataset_id="fraud_golden_v0.1",
        dataset_sha256=dataset_sha256,
        provider=provider_name,
        model=args.model,
        prompt_id=FRAUD_JUDGE_PROMPT_ID,
        prompt_sha256=FRAUD_JUDGE_PROMPT_SHA256,
        temperature=contract.temperature,
        judgements=merge_judgements(previous, judgements),
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            run.model_dump(), ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"기록: {args.output} ({len(run.judgements)}건)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
