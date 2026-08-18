"""프로바이더로 나가기 전에 원문에서 개인정보를 걷어낸다.

`CLAUDE.md` 의 "Minimize PII" 는 저장에만 걸리는 규칙이 아니다. 외부 프로바이더로
보내는 것은 저장보다 되돌리기 어렵다 - 한 번 나가면 우리 손을 떠난다.

무엇을 남기고 무엇을 지우는지가 이 파일의 전부다.

- 지운다: 주민등록번호, 카드번호, 계좌번호, 전화번호, 이메일
- 남긴다: 금액, 기관명, 말투, URL

URL 을 남기는 이유는 그것이 판단 근거이고 개인정보가 아니기 때문이다. 문자열을
보내는 것은 가져오는 것이 아니므로 `CLAUDE.md` 의 "no arbitrary server-side URL
fetching" 과 충돌하지 않는다.

자리표시자를 남기는 이유는 신호를 보존하기 위해서다. 계좌번호를 통째로 삭제하면
"계좌번호를 요구하는 문자" 라는 사실까지 사라진다. `[계좌번호]` 로 바꾸면 모델은
무엇이 요구됐는지 알면서 실제 값은 못 본다.

한계를 분명히 해 둔다. 사람 이름과 주소는 한국어에서 신뢰할 만하게 잡히지
않으므로 **여기서 걸러지지 않는다.** 이 계층은 "덜 보낸다" 이지 "안전하다" 가
아니다.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

# 순서가 중요하다. 넓은 패턴이 먼저 걸리면 좁은 패턴이 영영 안 걸린다.
# 010-1234-5678 은 전화번호이면서 계좌번호 패턴에도 맞는다.
_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    # 주민등록번호. 뒷자리 첫 숫자는 1~4(내국인) 또는 5~8(외국인).
    ("[주민등록번호]", re.compile(r"\b\d{6}\s?[-~]\s?[1-8]\d{6}\b")),
    # 카드번호. 4-4-4-4 구분 표기만 잡는다.
    ("[카드번호]", re.compile(r"\b\d{4}[-\s]\d{4}[-\s]\d{4}[-\s]\d{4}\b")),
    ("[이메일]", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    # 휴대폰과 지역번호.
    ("[전화번호]", re.compile(r"\b01\d[-.\s]?\d{3,4}[-.\s]?\d{4}\b")),
    ("[전화번호]", re.compile(r"\b0\d{1,2}[-.\s]\d{3,4}[-.\s]\d{4}\b")),
    # 계좌번호. 구분자가 있는 형태와, 금액이 아닌 긴 숫자열.
    ("[계좌번호]", re.compile(r"\b\d{2,6}-\d{2,6}-\d{2,8}\b")),
    ("[계좌번호]", re.compile(r"\b\d{10,16}\b(?!\s*(?:원|만|억|천))")),
)


@dataclass(frozen=True)
class MinimizedText:
    text: str
    #: 자리표시자별 치환 건수. 값이 아니라 건수만 담는다 - `adr/0004` 가 로그에
    #: 허용하는 것도 "건수와 성공 여부" 뿐이다.
    removed: Mapping[str, int]

    @property
    def removed_total(self) -> int:
        return sum(self.removed.values())


def minimize_for_provider(text: str) -> MinimizedText:
    counts: dict[str, int] = {}
    minimized = text
    for placeholder, pattern in _RULES:
        minimized, replaced = pattern.subn(placeholder, minimized)
        if replaced:
            counts[placeholder] = counts.get(placeholder, 0) + replaced
    return MinimizedText(text=minimized, removed=counts)
