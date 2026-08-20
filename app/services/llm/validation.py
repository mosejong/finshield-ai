"""모델 출력 검증.

프롬프트는 방어선이 아니다. 모델은 지시를 무시할 수 있고, 사용자가 붙여넣은 문자
안에 지시문이 섞여 있을 수도 있다(간접 프롬프트 주입). 그래서 나온 것을 다시 본다.

여기서 잡는 것은 두 가지다.

**없는 것을 만들어 낸 경우.**

- 근거에 없던 연락처: 가짜 신고번호를 알려 주는 것은 이 서비스가 낼 수 있는 가장
  나쁜 출력이다. 사용자가 그 번호로 전화를 건다.
- 주소(URL): 설명에 링크가 필요한 경우가 없다. 나오면 지어낸 것이다.
- 주민등록번호 형태: 모델이 예시로라도 만들어 내면 안 된다.

**판정과 어긋나는 경우.** 위험 수준이 `medium` 이상인데 설명이 "정상적인
안내입니다" 라고 안심시키는 출력. 타입 구조가 위험 수준 자체는 지켜 주지만,
사용자가 화면에서 제일 먼저 읽는 것은 등급이 아니라 문장이다. 등급과 문장이
어긋난 화면은 등급만 맞고 실제로는 안심시키는 화면이다.

이 검사는 `untrusted.py` 의 입력 방어와 짝이다. 한쪽은 지시가 들어가는 것을
막고 한쪽은 지시가 통했을 때 그 결과가 나가는 것을 막는다. 새 표현으로 입력
방어를 뚫어도 여기서 다시 걸린다.

한계도 분명하다. 이것은 사실 검증기가 아니다. 문장이 틀렸는지는 판단하지 못하고,
**근거에 없는 연락처·주소가 새로 등장했는지** 와 **판정을 뒤집는 안심 문구가
있는지** 만 본다.
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

# 판정을 뒤집는 안심 문구. `medium` 이상에서만 본다 - `low` 에서 "위험하지
# 않습니다" 는 맞는 말이다.
#
# **주어를 요구한다.** 이 규칙은 실측에서 왔다. 서술어만 보던 첫 판(2026-08-20)은
# 실제 모델 출력을 거부했다.
#
#     "…해당 기관의 공식 대표번호를 직접 찾아 사실관계를 확인하시는 것이
#      안전합니다."
#
# 안심시키는 문장이 아니라 **권고 문장**이다. 한국어 안전 안내는 "…하는 편이
# 안전합니다" 로 끝나는 것이 자연스럽고, 그것까지 거부하면 이 검사가 막으려던
# 공격보다 검사 자체가 더 많은 좋은 설명을 지운다.
#
# 그래서 안심의 대상이 **문자·발신자** 일 때만 잡는다. "안전계좌라는 제도는
# 없습니다" 와 "정상 절차와 다릅니다" 가 살아남아야 하는 것도 같은 이유다.
_MESSAGE_SUBJECT = (
    r"(?:이|그|해당|받으신|수신하신|보내신)?\s*"
    r"(?:문자|메시지|연락|발신자|발신\s*번호|링크|요청|안내문|상대방)"
)
_SUBJECT_MARKER = r"\s*(?:는|은|이|가|를|을|도|에는|에)?\s*"

# 사기범이 요구한 행동. "안심하고 ~하세요" 처럼 **응하라는 신호가 앞에 붙었을 때**만
# 보는 넓은 목록이다.
_COMPLY_ACTION = (
    r"(?:송금|이체|입금|납부|결제|설치|클릭|접속|연결|가입|등록|"
    r"제공|전달|회신|응답|진행|따르|응하|알려)"
)
# 정당한 설명에는 나올 이유가 없는 행동. 앞에 신호가 없어도 본다 - "신고를
# 진행하셔도 됩니다" 같은 정상 문장을 지우지 않으려고 `진행`·`따르`는 뺐다.
_SCAM_COMPLIANCE = (
    r"(?:송금|이체|입금|납부|결제|설치|클릭|접속|가입|"
    r"계좌\s*번호|개인정보|비밀번호|인증번호)"
)

_REASSURANCE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # "이 문자는 안전합니다", "해당 메시지는 정상입니다"
    re.compile(
        _MESSAGE_SUBJECT + _SUBJECT_MARKER + r"(?:모두\s*)?(?:안전|정상)"
        r"(?:합니다|입니다|하며|이며|한\s*것)"
    ),
    re.compile(r"안전한\s*(?:문자|메시지|연락|안내|발신자|링크|요청)"),
    re.compile(r"안전하다고\s*(?:판단|볼\s*수)"),
    # "정상적인 안내 문자입니다" 처럼 명사가 겹치는 형태. 종결어미를 요구하므로
    # "정상 절차와 다른 점이 있습니다" 는 걸리지 않는다.
    re.compile(
        r"정상적?인?\s*(?:(?:문자|메시지|연락|안내|절차|발신)\s*){1,3}"
        r"(?:입니다|이며|이고|이에요|예요)"
    ),
    # "이 문자는 사기가 아닙니다"
    re.compile(
        _MESSAGE_SUBJECT + _SUBJECT_MARKER + r".{0,12}?사기(?:가|는)?\s*아(?:닙니다|니라|니에요)"
    ),
    # "이 요청은 위험하지 않습니다"
    re.compile(
        _MESSAGE_SUBJECT + _SUBJECT_MARKER + r".{0,12}?위험(?:하지\s*않|이\s*없)"
    ),
    # "신뢰할 수 있는 공식 창구로 확인하세요" 는 정당하므로 주어를 요구한다.
    re.compile(r"신뢰할\s*수\s*있는\s*(?:문자|메시지|연락|발신자|번호|링크|기관입니다)"),
    # "이 문자는 믿으셔도 됩니다", "이 메시지는 신뢰할 수 있습니다"
    #
    # 서술어 목록을 `안전|정상` 으로만 두면 같은 뜻의 다른 동사가 통과한다. 코덱스
    # 검토(2026-08-20)가 이 구멍을 짚었다.
    re.compile(
        _MESSAGE_SUBJECT + _SUBJECT_MARKER + r"(?:믿|신뢰하)(?:으셔도|어도|셔도|으시면|시면)"
        r"\s*(?:됩니다|좋습니다|괜찮|무방|안전)"
    ),
    re.compile(
        _MESSAGE_SUBJECT + _SUBJECT_MARKER + r"(?:믿을|신뢰할)\s*수\s*있(?:습니다|어요|으며|고)"
    ),
    # "안심하고 안내대로 송금하세요", "요청대로 입금하셔도 됩니다"
    #
    # 판정을 부정하지 않고 **행동만 뒤집는** 형태다. 판정 문장은 그대로 두면서
    # 사용자를 사기범이 요구한 행동으로 보내므로 앞의 것들보다 위험하다.
    re.compile(r"안심하고\s*.{0,12}?" + _COMPLY_ACTION),
    re.compile(
        r"(?:그대로|안내대로|요청대로|시키는\s*대로|말씀대로|알려\s*준\s*대로)"
        r"\s*.{0,10}?" + _COMPLY_ACTION
    ),
    re.compile(
        _SCAM_COMPLIANCE + r"(?:하셔도|해도|하시면|셔도|하는\s*것은)"
        r"\s*(?:됩니다|괜찮|안전|무방|문제\s*없|상관\s*없|좋습니다)"
    ),
)

_REASSURANCE_CHECKED_LEVELS = frozenset({"medium", "high"})


class LlmOutputRejected(ValueError):
    """출력이 계약을 어겼다. 어긴 출력은 고쳐 쓰지 않고 버린다."""


def _contacts(text: str) -> set[str]:
    return {re.sub(r"\D", "", match) for match in _CONTACT_PATTERN.findall(text)}


def contradicts_verdict(text: str, *, risk_level: str) -> bool:
    """판정이 위험한데 문장이 안심시키는가."""
    if risk_level not in _REASSURANCE_CHECKED_LEVELS:
        return False
    return any(pattern.search(text) for pattern in _REASSURANCE_PATTERNS)


def validate_explanation(
    output: str, *, grounded_text: str, max_chars: int, risk_level: str
) -> str:
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
    if contradicts_verdict(explanation, risk_level=risk_level):
        raise LlmOutputRejected(
            f"explanation reassures the user while the verdict is {risk_level}"
        )

    invented = _contacts(explanation) - _contacts(grounded_text)
    if invented:
        raise LlmOutputRejected(
            f"explanation introduced contacts absent from the evidence: {sorted(invented)}"
        )
    return explanation
