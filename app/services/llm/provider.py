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
from app.services.llm.outcomes import ExplanationOutcome


class LlmUnavailable(RuntimeError):
    """프로바이더에 닿지 못했거나 시간 안에 답하지 않았다.

    이럴 때 설명은 비워 둔다. 결정론 엔진의 판정은 이미 나와 있으므로 사용자는
    위험 수준과 행동 지침을 그대로 받는다. LLM 이 죽어도 서비스는 죽지 않는다.

    `outcome` 이 붙어 있는 이유는 `outcomes.py` 에 적었다. 짧게는, 메시지 문자열은
    아무도 읽지 않으므로 셀 수 있는 것을 하나 들고 와야 한다는 것이다. 메시지는
    남겨 두지만 그쪽은 사람이 디버깅할 때만 보고, 로그와 지표로 나가는 것은
    `outcome` 뿐이다.

    **선택 인자다.** `LlmProvider` 는 Protocol 이라 우리가 쓰지 않은 구현이 이
    예외를 사유 없이 던질 수 있다. 그때 `TypeError` 로 요청을 죽이는 것보다
    `unspecified` 로 세는 쪽이 낫다 - 설명은 없어도 되는 것이고 판정은 이미
    나와 있다. 대신 `app/` 안의 코드는 전부 사유를 붙이며, 그 사실은 테스트가
    지킨다.
    """

    def __init__(
        self,
        message: str = "",
        *,
        outcome: ExplanationOutcome = ExplanationOutcome.UNSPECIFIED,
    ) -> None:
        super().__init__(message)
        self.outcome = outcome


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
                f"StubProvider cannot serve a contract for {contract.provider}",
                outcome=ExplanationOutcome.PROVIDER_MISCONTRACTED,
            )
        self.prompts.append(prompt)
        return self.response
