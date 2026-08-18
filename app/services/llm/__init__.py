"""LLM 설명 계층.

이 패키지 밖에서 프로바이더를 직접 부르지 않는다. 최소화되지 않은 원문이 나가는
경로를 하나로 묶어 두기 위해서다.
"""

from app.services.llm.contract import LlmContract, LlmContractError
from app.services.llm.explanation import explain_analysis
from app.services.llm.minimization import MinimizedText, minimize_for_provider
from app.services.llm.provider import LlmProvider, LlmUnavailable, StubProvider
from app.services.llm.validation import LlmOutputRejected, validate_explanation

__all__ = [
    "LlmContract",
    "LlmContractError",
    "LlmOutputRejected",
    "LlmProvider",
    "LlmUnavailable",
    "MinimizedText",
    "StubProvider",
    "explain_analysis",
    "minimize_for_provider",
    "validate_explanation",
]
