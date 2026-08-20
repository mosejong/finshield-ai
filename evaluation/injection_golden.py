"""프롬프트 주입 골든셋 로더.

`docs/12` 21행이 요구하는 "Prompt-injection golden set" 이다. `fraud_golden.py`
와 다른 점이 하나 있고, 그 차이가 이 파일이 따로 있는 이유다.

**사기 골든셋은 판정을 잰다. 이쪽은 경계를 잰다.** 여기서 확인하는 것은 "이 문자가
사기인가" 가 아니라 "이 문자에 심긴 지시가 프로바이더까지 도달하는가" 이고, 그
질문은 모델을 부르지 않고 답할 수 있다. 그래서 이 골든셋의 검사는 CI 에서 돈다 -
`fraud_benchmark.py` 와 달리 유료 호출이 없다.

모델이 실제로 넘어가는지(= 지시를 따르는지)는 유료 측정이고, 그쪽은
`docs/devlog/2026-08-20/prompt-injection-boundary.md` 에 날짜와 모델을 붙여
기록한다. 그 숫자를 여기에 두면 CI 가 매번 돈을 쓰거나, 아니면 낡은 숫자가
테스트인 척하게 된다.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

GOLDEN_SET_PATH = Path(__file__).with_name("data") / "injection_golden_v0.1.jsonl"

TECHNIQUES = {
    "direct_override",
    "role_assignment",
    "english_mixed",
    "delimiter_forgery",
    "verdict_forgery",
    "developer_impersonation",
    "output_pinning",
}


class InjectionGoldenCase(BaseModel):
    case_id: str = Field(pattern=r"^pi-[0-9]{3}$")
    technique: str
    text: str = Field(min_length=1, max_length=10_000)
    #: 프로바이더까지 가면 안 되는 조각.
    injected_fragment: str = Field(min_length=1)
    #: 반드시 남아야 하는 조각. 이쪽이 사라지면 설명이 근거를 잃는다.
    evidence_fragment: str = Field(min_length=1)
    expected_min_risk: str = Field(pattern=r"^(low|medium|high)$")
    note: str

    @model_validator(mode="after")
    def validate_case(self) -> "InjectionGoldenCase":
        if self.technique not in TECHNIQUES:
            raise ValueError(f"unknown technique: {self.technique}")
        if self.injected_fragment not in self.text:
            raise ValueError(f"{self.case_id}: injected_fragment is not in text")
        if self.evidence_fragment not in self.text:
            raise ValueError(f"{self.case_id}: evidence_fragment is not in text")
        return self


def load_injection_cases(path: Path = GOLDEN_SET_PATH) -> list[InjectionGoldenCase]:
    cases = [
        InjectionGoldenCase.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    _reject_duplicate_ids(case.case_id for case in cases)
    return cases


def _reject_duplicate_ids(case_ids: Iterable[str]) -> None:
    seen: set[str] = set()
    for case_id in case_ids:
        if case_id in seen:
            raise ValueError(f"duplicate case_id: {case_id}")
        seen.add(case_id)
