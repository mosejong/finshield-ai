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

**근거 밖에서 말한 경우.** 2026-08-27 에 늘어난 쪽이다. 그전까지 근거와 대조하는
대상은 연락처 하나뿐이었고, 근거에 없는 기관·법령·기한·비율·약속을 지어낸 문장
18개를 넣어 보니 **18개가 모두 통과했다.** 연락처를 근거에서 파생한 허용 목록으로
거른다는 발상은 그대로 두고 대상만 넓혔다 — 기관 이름, 법령 인용, 숫자 주장, 결과
약속. `CLAUDE.md` 비협상 조항이 이름을 그대로 적어 둔 것들이다.

숫자의 허용 목록은 **근거 + 사용자가 붙여넣은 문자**다. 연락처와 다른 점이 여기
있고, 다른 이유도 분명하다. 사기 문자가 "24시간 이내" 라고 압박했으면 설명은 그
기한을 되읽어야 하고, 되읽는 것은 지어내는 것이 아니라 설명해야 할 대상이다.
문자를 허용 목록에서 빼고 재 보면 되읽기 문장 4개 중 3개가 거부됐다.

**연락처는 반대다.** 문자에 적혀 있어도 절대 되읽으면 안 된다 — 사기범의 번호를
우리 화면이 다시 찍어 주는 꼴이 된다. 그래서 연락처 검사만 문자를 허용 목록에
넣지 않는다. 이 비대칭은 빠뜨린 것이 아니라 규칙이다.

한계는 그대로다. **이것은 여전히 사실 검증기가 아니다.** 같은 셋에서 15/18 이
걸리고 셋이 남는다: 실재하는 기관에 지어낸 발표를 붙인 문장("경찰청은 이 수법을
올해 최다 피해 유형으로 지정했습니다"), 지어낸 상품명, 지어낸 절차. 셋 다 형태가
정상 문장과 같아서 형태 규칙으로는 닿지 않는다(`docs/34` 17절).
"""

from __future__ import annotations

import re

from app.services.llm.outcomes import ExplanationOutcome

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


# --------------------------------------------------------------- 근거 밖 주장

# 대조용 정규화. 공백뿐 아니라 구두점도 지운다.
#
# 근거 줄은 `- 경찰청: 사이버범죄 신고시스템` 처럼 목록 기호와 콜론을 달고 오고,
# 설명 문장은 `경찰청 사이버범죄 신고시스템` 이라고 쓴다. 공백만 지우면 콜론이
# 남아 같은 것이 다른 것이 되고, **실재하는 공식 창구를 안내한 정상 문장이
# 거부된다.** 2026-08-27 설계 측정의 유일한 오거부가 이것이었고, 고칠 곳은
# 규칙이 아니라 정규화였다.
_NON_WORD = re.compile(r"[^0-9A-Za-z가-힣]+")

# 법령 인용. **연락처·기관과 같은 방식으로 근거에 대조한다.**
#
# 오래 허용 목록 없이 거부했고, 그 근거는 "설명에 조문 번호가 필요한 경우가
# 없다" 였다. 틀린 전제였다 — 엔진은 계좌·인증 접근권을 넘긴 사건에
# `국가법령정보센터: 전자금융거래법 제6조 …` 를 **공식 근거로 붙이고, 그 줄을
# 그대로 프롬프트에 넣는다.** 모델에게 법령을 읽히고 그 법령을 되읽었다고
# 거부한 것이다. 2026-09-04 홀드아웃 v1.3 에서 `fh-1135` 가 이것으로 죽었고,
# **주 모델과 대체 모델이 같은 이유로 걸려 그 사건만 설명이 아예 없었다.**
# 기관 규칙과 같은 자리에서 같은 모양으로 틀렸다(`docs/devlog/2026-09-04`).
#
# 좁히는 쪽은 그대로다. 근거에 없는 법률과 근거에 없는 조문 번호는 여전히
# 거부되고, 대조는 부분 문자열이라 이름을 줄여 쓴 것도 통과하지 못한다
# (`전기통신금융사기 피해 방지 및 피해금 환급에 관한 특별법` 을
# `전기통신금융사기특별법` 으로 줄이면 붙지 않는다). 이 변경으로 거부가
# **늘어나는 입력은 없다** — 통과하던 것은 전부 그대로 통과한다.
#
# **맨 `~법` 은 쓸 수 없다.** 방법·수법·불법·비법·요법이 같은 꼬리를 갖는다.
# `저` 지시관형사를 제외했던 것과 같은 모양의 문제이고, 같은 방식으로 푼다 —
# 법률 이름에만 붙는 꼬리를 열거한다.
_LAW_PATTERN = re.compile(
    r"제\s?\d+\s?조"
    r"|[가-힣]{2,}(?:특별법|보호법|기본법|진흥법|거래법|관리법|처벌법|이용법)"
)

# 숫자 주장. 근거에도 문자에도 없는 비율·기한·건수는 지어낸 것이다.
#
# 건수의 단위를 `건|명` 으로 좁힌 것은 **금액을 일부러 뺀 것**이다. 금액은
# 문자에 "200만원" 으로 적히고 설명에 "200만 원" 으로 쓰이는 식으로 표기가
# 갈리는데, 정규화로 붙일 수 있는 것은 공백까지이고 "이백만원" 까지는 못 붙인다.
# 지어낸 통계는 거의 언제나 건수·인원으로 오므로 금액을 빼도 잡을 것은 잡는다.
_NUMERIC_CLAIM_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\d+(?:\.\d+)?\s*(?:%|퍼센트|프로)"),
    re.compile(r"\d+\s*(?:시간|영업일|일|개월|주|년)\s*(?:이내|안에|내에|만에)"),
    re.compile(r"\d+(?:\s*[만천억])?\s*(?:건|명)"),
)

# 기관 이름. 공식 출처 카탈로그가 다섯 기관으로 닫혀 있으므로 연락처와 **같은
# 방식**으로 근거에서 파생한 허용 목록에 대조할 수 있다.
#
# 꼬리 목록에 `청`·`원` 이 없는 이유: 요청·신청·지원·직원·병원이 같은 꼬리를
# 갖는다. 그래서 기관에만 붙는 꼬리만 남겼고, 그 대신 "금융감독원" 처럼 `원` 으로
# 끝나는 기관은 `감독원`·`진흥원`·`보안원` 같은 더 긴 꼬리로 잡는다.
_ORG_SUFFIXES = (
    "센터", "위원회", "공단", "공사", "진흥원", "감독원", "보안원", "수사대",
    "협회", "거래소", "포털", "신고시스템", "지킴이",
)
_ORG_PATTERN = re.compile(
    r"(?:[가-힣]+\s?){0,3}(?:" + "|".join(_ORG_SUFFIXES) + r")"
)
# 고유명사가 아니라 일반명사인 꼬리. "은행 고객센터에 문의하세요" 는 특정 기관을
# 지목한 것이 아니라 사용자가 이미 아는 창구를 가리키는 말이다.
_ORG_GENERIC_TAILS = (
    "고객센터", "상담센터", "콜센터", "지원센터", "안내센터", "서비스센터",
)

# 결과 약속과 적격성 단정. 엔진이 하지 않은 말이다.
#
# 전부 **종결형을 요구한다.** "보장한다는 표현은 정상 안내에서 쓰지 않습니다" 나
# "구제 대상 여부는 관계기관이 판단합니다" 처럼 같은 낱말을 인용하거나 유보하는
# 문장은 이 서비스가 내야 하는 문장이고, 그것까지 지우면 검사가 막으려던 것보다
# 검사가 더 많이 부순다. `_REASSURANCE_PATTERNS` 가 주어를 요구하는 것과 같은
# 이유다.
_PROMISE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"전액\s*(?:환급|보전|보상|배상|지급)"),
    re.compile(r"손실을\s*부담(?:하게)?\s*(?:됩니다|합니다)"),
    re.compile(r"보장(?:됩니다|합니다|해\s*드립니다)"),
    re.compile(r"책임(?:집니다|지게\s*됩니다)"),
    re.compile(r"자격이\s*(?:있습니다|됩니다|주어집니다)"),
    re.compile(r"대상(?:입니다|이\s*됩니다|에\s*해당합니다|에\s*해당됩니다)"),
    re.compile(r"(?:피해자|수급자|가입자)로\s*인정(?:되므로|됩니다)"),
)


class LlmOutputRejected(ValueError):
    """출력이 계약을 어겼다. 어긴 출력은 고쳐 쓰지 않고 버린다.

    `outcome` 은 **필수**다. 이 예외는 전부 이 파일 안에서 우리가 던지므로 사유를
    요구할 수 있고, 요구하지 않으면 새 검사 규칙이 사유 없이 늘어난다. `outcomes.py`
    가 여섯 가지를 따로 세는 이유도 같이 적혀 있다 - 없는 연락처를 지어낸 것과
    길이가 넘친 것을 한 칸으로 세면, 전화를 걸게 만드는 출력이 사소한 것에 묻힌다.

    같은 이유로 `LlmUnavailable` 쪽은 사유가 선택이다. 남이 던질 수 있는 예외는
    사유를 요구할 수 없다.
    """

    def __init__(self, message: str, *, outcome: ExplanationOutcome) -> None:
        super().__init__(message)
        self.outcome = outcome


def _contacts(text: str) -> set[str]:
    return {re.sub(r"\D", "", match) for match in _CONTACT_PATTERN.findall(text)}


def _normalize(text: str) -> str:
    return _NON_WORD.sub("", text)


def _boundary_suffixes(text: str) -> list[str]:
    """공백에서 끊어지는 뒷조각들. 자기 자신이 첫 번째다.

    `_ORG_PATTERN` 은 기관 꼬리 **앞의 어절 세 개까지** 함께 삼킨다. 이름 앞에
    보통 낱말이 오면("필요하다면 보이스피싱 통합신고대응센터") 잡힌 덩어리가
    근거에 없는 문자열이 되고, 근거에 **있는** 기관을 부른 문장이 지어낸 것으로
    거부된다. 앞 어절을 하나씩 떼어 보는 것이 그것을 되돌린다.
    """
    parts = text.split()
    return [" ".join(parts[i:]) for i in range(len(parts))] or [text]


def _grounded_organizations(grounded_text: str) -> set[str]:
    """근거가 이름을 댄 기관. 앞 어절이 붙지 않은 **온전한 이름**만 담는다."""
    return {
        name
        for match in _ORG_PATTERN.findall(grounded_text)
        if (name := _normalize(match))
    }


def _ungrounded_organizations(explanation: str, grounded_text: str) -> set[str]:
    """설명이 이름을 댄 기관 중 근거에 없는 것.

    문자 원문은 여기 들어가지 않는다. 사칭 문자가 "국세청" 이라고 적었다는 사실이
    그 기관을 안내해도 된다는 뜻은 아니기 때문이다.

    통과하는 길은 둘이고, **둘 다 좁다.**

    1. 잡힌 덩어리 전체가 근거 안에 있다. 표기가 달라도(`경찰청: 사이버범죄
       신고시스템` 대 `경찰청 사이버범죄 신고시스템`) 정규화가 흡수한다.
    2. 덩어리의 **어절 경계 뒷조각 중 하나가 근거의 온전한 기관 이름과 같다.**

    2번이 없으면 이름 앞에 낱말 하나만 와도 정당한 설명이 죽는다. 2번을 부분
    문자열이 아니라 **일치**로 둔 것은 그 반대쪽 값이다 — 부분 문자열로 열면
    "국세청 신고시스템" 이 근거의 "사이버범죄 신고시스템" 을 빌려 통과한다.
    앞에 무엇이 붙어 있든 뒷조각이 근거의 이름과 **같아야** 한다.
    """
    grounded = _normalize(grounded_text)
    named = _grounded_organizations(grounded_text)
    return {
        name
        for match in _ORG_PATTERN.findall(explanation)
        if (name := _normalize(match))
        and not name.endswith(_ORG_GENERIC_TAILS)
        and name not in grounded
        and not any(_normalize(part) in named for part in _boundary_suffixes(match))
    }


def _ungrounded_laws(explanation: str, grounded_text: str) -> set[str]:
    """설명이 든 법령 중 근거에 없는 것. 법률 이름과 조문 번호를 **따로** 본다.

    따로 보는 것이 중요하다. 근거가 `전자금융거래법 제6조` 를 달고 왔을 때
    `예금자보호법 제6조` 는 조문 번호만 빌린 문장이고, `전자금융거래법 제9조` 는
    법률 이름만 빌린 문장이다. 둘 다 걸려야 한다.

    문자 원문은 여기 들어가지 않는다. `_ungrounded_organizations` 와 같은
    이유다 — 사기 문자가 법 조항을 들먹였다는 사실이 그 조항을 설명에 실어도
    된다는 뜻은 아니다.
    """
    grounded = _normalize(grounded_text)
    return {
        name
        for match in _LAW_PATTERN.findall(explanation)
        if (name := _normalize(match)) and name not in grounded
    }


def _ungrounded_numbers(
    explanation: str, grounded_text: str, message_text: str
) -> set[str]:
    """설명이 단정한 숫자 중 근거에도 문자에도 없는 것.

    돌려주는 값은 정의상 문자에 없는 것들이라, 이 집합을 예외 메시지에 실어도
    사용자가 붙여넣은 내용이 따라 나가지 않는다.
    """
    # 사이에 개행을 끼운다. 정규화된 문자열끼리 붙여 놓으면 근거의 끝과 문자의
    # 처음이 이어져 없던 숫자가 있는 것처럼 보일 수 있다.
    allowed = _normalize(grounded_text) + "\n" + _normalize(message_text)
    return {
        claim
        for pattern in _NUMERIC_CLAIM_PATTERNS
        for match in pattern.findall(explanation)
        if (claim := _normalize(match)) and claim not in allowed
    }


def contradicts_verdict(text: str, *, risk_level: str) -> bool:
    """판정이 위험한데 문장이 안심시키는가."""
    if risk_level not in _REASSURANCE_CHECKED_LEVELS:
        return False
    return any(pattern.search(text) for pattern in _REASSURANCE_PATTERNS)


def validate_explanation(
    output: str,
    *,
    grounded_text: str,
    message_text: str,
    max_chars: int,
    risk_level: str,
) -> str:
    """모델 출력을 검사하고, 통과하면 다듬은 문장을 돌려준다.

    `message_text` 는 **모델이 실제로 본 문자**여야 한다. 숫자 주장의 허용 목록이
    여기서 오기 때문에, 모델에게 잘라서 보낸 뒤 여기에는 원문을 넘기면 모델이
    읽을 수 없었던 숫자까지 통과시키게 된다. 기본값을 두지 않은 것도 그래서다 —
    빼먹으면 문자를 되읽는 정상 문장이 조용히 거부된다.
    """
    explanation = output.strip()
    if not explanation:
        raise LlmOutputRejected(
            "empty explanation", outcome=ExplanationOutcome.REJECTED_EMPTY
        )
    if len(explanation) > max_chars:
        raise LlmOutputRejected(
            f"explanation is {len(explanation)} characters, limit is {max_chars}",
            outcome=ExplanationOutcome.REJECTED_TOO_LONG,
        )
    if _URL_PATTERN.search(explanation):
        raise LlmOutputRejected(
            "explanation introduced a URL", outcome=ExplanationOutcome.REJECTED_URL
        )
    if _RRN_PATTERN.search(explanation):
        raise LlmOutputRejected(
            "explanation contains a resident registration number",
            outcome=ExplanationOutcome.REJECTED_RRN,
        )
    if contradicts_verdict(explanation, risk_level=risk_level):
        raise LlmOutputRejected(
            f"explanation reassures the user while the verdict is {risk_level}",
            outcome=ExplanationOutcome.REJECTED_CONTRADICTS_VERDICT,
        )

    invented = _contacts(explanation) - _contacts(grounded_text)
    if invented:
        raise LlmOutputRejected(
            f"explanation introduced contacts absent from the evidence: {sorted(invented)}",
            outcome=ExplanationOutcome.REJECTED_INVENTED_CONTACT,
        )

    # 여기부터는 순서대로 보고 **처음 걸린 사유 하나만** 남긴다. 그래서 지표의
    # 칸은 "이 문장이 어긴 것 전부" 가 아니라 "처음 걸린 것" 이고, 합계는 거부된
    # 문장 수와 같다. 기관을 맨 앞에 둔 것은 위 연락처 검사와 같은 이유다 —
    # 사용자가 실제로 그리로 찾아간다.
    named = _ungrounded_organizations(explanation, grounded_text)
    if named:
        raise LlmOutputRejected(
            f"explanation named organizations absent from the evidence: {sorted(named)}",
            outcome=ExplanationOutcome.REJECTED_UNGROUNDED_ORG,
        )
    statutes = _ungrounded_laws(explanation, grounded_text)
    if statutes:
        raise LlmOutputRejected(
            f"explanation cited statutes absent from the evidence: {sorted(statutes)}",
            outcome=ExplanationOutcome.REJECTED_LAW_CITATION,
        )
    figures = _ungrounded_numbers(explanation, grounded_text, message_text)
    if figures:
        raise LlmOutputRejected(
            f"explanation asserted figures absent from the evidence and the message: {sorted(figures)}",
            outcome=ExplanationOutcome.REJECTED_UNGROUNDED_NUMBER,
        )
    if any(pattern.search(explanation) for pattern in _PROMISE_PATTERNS):
        raise LlmOutputRejected(
            "explanation promised an outcome or an eligibility the engine never asserted",
            outcome=ExplanationOutcome.REJECTED_UNGROUNDED_PROMISE,
        )
    return explanation
