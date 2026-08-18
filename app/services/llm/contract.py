"""LLM 프로바이더 계약.

이 저장소에서 LLM 은 판정자가 아니다. 결정론 엔진이 이미 만든 결과를 문장으로
설명할 뿐이고, 그 경계는 문서가 아니라 이 패키지의 타입과 검증으로 강제한다.

계약을 "고정한다" 는 것은 세 가지를 뜻한다.

- provider 와 model 이 코드에 박혀 있고 환경변수로 조용히 바뀌지 않는다.
- prompt 본문의 sha256 이 계약에 적혀 있다. 프롬프트를 한 글자 고치면 테스트가
  깨지고, 고친 사람이 벤치마크를 다시 돌리게 된다.
- 셋 중 하나라도 바뀌면 그 전에 측정한 숫자는 더 이상 이 시스템을 설명하지 않는다.

`evaluation/fraud_benchmark.py` 가 `llm_only.status = "not_run"` 의 사유로 적어 둔
"No pinned model, prompt, provider contract" 가 이 파일이 메우려는 자리다.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

# 여기 없는 provider 는 쓸 수 없다. 오타 하나로 엉뚱한 곳에 원문이 나가는 것을
# 막는 것이 목적이므로, 새 provider 를 넣는 것은 의도적인 코드 변경이어야 한다.
KNOWN_PROVIDERS = frozenset({"google_ai_studio", "google_vertex", "stub"})

# AnalyzeRequest.text 의 상한과 같다. 프로바이더로 나가는 양이 사용자가 넣을 수
# 있는 양보다 커질 이유가 없다.
MAX_ALLOWED_INPUT_CHARS = 10_000


class LlmContractError(ValueError):
    """계약 자체가 잘못된 경우.

    요청을 받은 뒤가 아니라 import 시점에 드러나야 한다. 잘못된 계약으로 한 번이라도
    호출이 나가면 그 호출은 되돌릴 수 없다.
    """


@dataclass(frozen=True)
class LlmContract:
    provider: str
    model: str
    prompt_id: str
    prompt_sha256: str
    max_input_chars: int
    timeout_seconds: float
    temperature: float

    def __post_init__(self) -> None:
        if self.provider not in KNOWN_PROVIDERS:
            raise LlmContractError(
                f"unknown provider {self.provider!r}; "
                f"known: {sorted(KNOWN_PROVIDERS)}"
            )
        if not self.model.strip():
            raise LlmContractError("model must not be empty")
        if not self.prompt_id.strip():
            raise LlmContractError("prompt_id must not be empty")
        if len(self.prompt_sha256) != 64 or not all(
            character in "0123456789abcdef" for character in self.prompt_sha256
        ):
            raise LlmContractError("prompt_sha256 must be 64 lowercase hex characters")
        if not 0 < self.max_input_chars <= MAX_ALLOWED_INPUT_CHARS:
            raise LlmContractError(
                f"max_input_chars must be in 1..{MAX_ALLOWED_INPUT_CHARS}"
            )
        if not 0 < self.timeout_seconds <= 30:
            raise LlmContractError("timeout_seconds must be in 0..30")
        if not 0.0 <= self.temperature <= 1.0:
            raise LlmContractError("temperature must be in 0.0..1.0")

    def verify_prompt(self, prompt_template: str) -> None:
        """프롬프트 본문이 계약에 적힌 것과 같은지 확인한다.

        이 검사가 없으면 "고정된 prompt" 는 주석에 불과하다. 골든셋을 sha256 으로
        고정해 둔 것과 같은 이유다 (`evaluation/fraud_benchmark.py` 의
        `dataset.normalized_sha256`).
        """
        digest = hashlib.sha256(prompt_template.encode("utf-8")).hexdigest()
        if digest != self.prompt_sha256:
            raise LlmContractError(
                f"prompt {self.prompt_id} does not match the pinned hash: "
                f"expected {self.prompt_sha256}, got {digest}. "
                "프롬프트를 고쳤다면 계약의 sha256 을 갱신하고 벤치마크를 다시 돌린다."
            )
