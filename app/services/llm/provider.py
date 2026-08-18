"""프로바이더 경계.

프로바이더는 이 Protocol 하나만 만족하면 된다. 그래야 AI Studio 무료 등급에서
Vertex 로 옮기는 일이 설정 변경으로 끝난다(`docs/28` P2-2).

여기에 실제 네트워크 호출은 없다. 계약 경로 전체 - 최소화, 프롬프트 조립, 출력
검증 - 는 프로바이더 없이도 검증할 수 있어야 하고, 실제로 그렇게 테스트한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.services.llm.contract import LlmContract


class LlmUnavailable(RuntimeError):
    """프로바이더에 닿지 못했거나 시간 안에 답하지 않았다.

    이럴 때 설명은 비워 둔다. 결정론 엔진의 판정은 이미 나와 있으므로 사용자는
    위험 수준과 행동 지침을 그대로 받는다. LLM 이 죽어도 서비스는 죽지 않는다.
    """


class LlmProvider(Protocol):
    @property
    def name(self) -> str: ...

    def generate(self, *, contract: LlmContract, prompt: str) -> str: ...


@dataclass
class StubProvider:
    """테스트와 드라이런용.

    호출을 기록하므로 "무엇이 실제로 나갔는가" 를 테스트가 직접 확인할 수 있다.
    개인정보가 빠졌는지를 주장이 아니라 관측으로 검사하기 위한 것이다.
    """

    response: str = "설명"
    prompts: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return "stub"

    def generate(self, *, contract: LlmContract, prompt: str) -> str:
        if contract.provider != "stub":
            raise LlmUnavailable(
                f"StubProvider cannot serve a contract for {contract.provider}"
            )
        self.prompts.append(prompt)
        return self.response
