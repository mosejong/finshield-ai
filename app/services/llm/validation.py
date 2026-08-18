"""모델 출력 검증.

프롬프트는 방어선이 아니다. 모델은 지시를 무시할 수 있고, 사용자가 붙여넣은 문자
안에 지시문이 섞여 있을 수도 있다(간접 프롬프트 주입). 그래서 나온 것을 다시 본다.

여기서 잡는 것은 **없는 것을 만들어 낸 경우** 다.

- 근거에 없던 연락처: 가짜 신고번호를 알려 주는 것은 이 서비스가 낼 수 있는 가장
  나쁜 출력이다. 사용자가 그 번호로 전화를 건다.
- 주소(URL): 설명에 링크가 필요한 경우가 없다. 나오면 지어낸 것이다.
- 주민등록번호 형태: 모델이 예시로라도 만들어 내면 안 된다.

한계도 분명하다. 이것은 사실 검증기가 아니다. 문장이 틀렸는지는 판단하지 못하고,
**근거에 없는 연락처와 주소가 새로 등장했는지** 만 본다.
"""

from __future__ import annotations

import re

_URL_PATTERN = re.compile(r"(?:https?://|www\.)\S+|\b[\w-]+\.(?:com|net|kr|co\.kr|io|link)\b", re.IGNORECASE)
_RRN_PATTERN = re.compile(r"\b\d{6}\s?[-~]\s?[1-8]\d{6}\b")

# 연락처로 읽힐 수 있는 숫자. 뒤에 단위가 붙으면 금액이므로 제외한다.
_CONTACT_PATTERN = re.compile(
    r"\b(?:1\d{2,3}|0\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4})\b"
    r"(?!\s*(?:원|만|억|천|개|명|년|월|일|번|차|%|퍼센트|건))"
)


class LlmOutputRejected(ValueError):
    """출력이 계약을 어겼다. 어긴 출력은 고쳐 쓰지 않고 버린다."""


def _contacts(text: str) -> set[str]:
    return {re.sub(r"\D", "", match) for match in _CONTACT_PATTERN.findall(text)}


def validate_explanation(output: str, *, grounded_text: str, max_chars: int) -> str:
    explanation = output.strip()
    if not explanation:
        raise LlmOutputRejected("empty explanation")
    if len(explanation) > max_chars:
        raise LlmOutputRejected(
            f"explanation is {len(explanation)} characters, limit is {max_chars}"
        )
    if _URL_PATTERN.search(explanation):
        raise LlmOutputRejected("explanation introduced a URL")
    if _RRN_PATTERN.search(explanation):
        raise LlmOutputRejected("explanation contains a resident registration number")

    invented = _contacts(explanation) - _contacts(grounded_text)
    if invented:
        raise LlmOutputRejected(
            f"explanation introduced contacts absent from the evidence: {sorted(invented)}"
        )
    return explanation
