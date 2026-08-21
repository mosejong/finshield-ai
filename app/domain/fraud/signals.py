import re
from ipaddress import ip_address
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.schemas.analysis import RiskSignal


@dataclass(frozen=True)
class SignalRule:
    code: str
    keywords: tuple[str, ...]
    weight: int
    label: str
    # 맨 명사만으로는 신호가 되지 않는 어휘다. "체크카드"·"비밀번호"·"은행"은
    # 정상 문자에 매일 등장한다. 같은 메시지 안에 **읽는 사람을 향한 요구**가
    # 있어야 켠다. held-out v0.2 의 오탐 6건이 전부 이 구분을 안 해서 났다.
    demand_gated_keywords: tuple[str, ...] = ()
    # 동사만으로는 신호가 되지 않는 어휘다. "전달해"·"다시 보내"는 계약서에도
    # 쓴다. 목적어가 돈일 때만 자금 재전달이다.
    money_gated_keywords: tuple[str, ...] = ()


SIGNAL_RULES: tuple[SignalRule, ...] = (
    SignalRule(
        "urgency_pressure",
        ("오늘까지", "즉시", "긴급", "지금 바로", "곧 정지", "시간이 없습니다"),
        12,
        "긴급한 행동 압박",
    ),
    SignalRule(
        "authority_impersonation",
        (
            "검찰",
            "경찰",
            "금융감독원",
            "금감원",
            "수사관",
            "정부기관",
            "공공기관",
            "수사기관",
            # v0.2 추가. 2026-08-19 LLM 단독 판정이 잡고 규칙이 놓친 fg-046 에서
            # 드러난 구멍이다(`docs/32`). 실제 사칭에 쓰이는 기관인데 어휘에
            # 없어서 못 잡은 것이지, 판정 로직의 문제가 아니었다.
            # 부분 문자열로 매칭하므로 "검찰"이 "검찰청"을, "경찰"이 "경찰청"을
            # 이미 덮는다. 그래서 접미사 변형은 넣지 않는다.
            #
            # 여기서 멈춘 이유는 `docs/32` 에 적어 뒀다. 국세청·건강보험공단처럼
            # 사칭이 잦은 기관을 함께 넣어 봤더니, 골든셋 점수는 그대로인데
            # 골든셋 밖 정상 문장("국세청 홈택스에서 조회할 수 있습니다")에서
            # 오탐이 났다. 측정이 요구하지 않은 어휘는 넣지 않는다 - 넣으려면
            # held-out 셋으로 오탐을 재고 넣는다.
            "법원",
            "집행관",
        ),
        25,
        "공식 기관 사칭 가능성",
        # v0.3. held-out v0.2 에서 이 신호의 재현율이 0.333 이었다. 못 잡은
        # 사례가 전부 은행·카드사·공단을 자칭한 것이었는데, 그 어휘를 위 목록에
        # 그냥 넣었다가 정상 안내문에서 오탐이 났던 것이 v0.2 의 기록이다
        # (`docs/32`). 그래서 **두 층으로 나눈다.**
        #
        # 위 목록(수사기관·법원)은 언급만으로 켠다. 실제로 그 기관들은 문자를
        # 보내지 않는다. 아래 목록(은행·카드사·공단·세무 관청)은 **요구가 함께
        # 있을 때만** 켠다. 이들은 정상 문자를 매일 보내기 때문이다.
        # "하나은행 이용 안내입니다" 와 "하나은행입니다. 본인인증을 완료해
        # 주세요" 를 가르는 것은 기관명이 아니라 뒤에 붙은 요구다.
        demand_gated_keywords=(
            "은행",
            "뱅크",
            "카드사",
            "공단",
            "국세청",
            "관세청",
            "병무청",
            "우체국",
            "건강보험",
            "국민연금",
            "근로복지",
        ),
    ),
    SignalRule(
        "secrecy_isolation",
        ("아무에게도 말하지", "비밀로", "혼자 처리", "보안 유지", "통화를 끊지"),
        18,
        "주변 확인을 막는 비밀 유지 요구",
    ),
    SignalRule(
        "familiar_person_claim",
        (
            # v0.4. 지인·가족 사칭에서 **검증 가능한 표지는 사칭 주장 자체가
            # 아니다.** "엄마야"는 진짜 엄마도 쓴다. 이 사기를 성립시키는 것은
            # 원래 알던 연락처로 확인할 수 없게 만드는 핑계다. 그래서 어휘를
            # 호칭이 아니라 **연락 수단이 바뀐 이유**로 잡는다.
            "폰이 고장",
            "핸드폰이 고장",
            "휴대폰이 고장",
            "액정이 깨",
            "액정 깨",
            "폰 액정",
            "새 번호로",
            "번호가 바뀌었",
            "번호 바뀌었",
            "이 번호로 저장",
            "전화가 안 돼",
            "전화가 안돼",
            "통화가 안 돼",
            "통화가 안돼",
            "전화를 못 받",
            "친구 폰으로",
            "다른 폰으로",
            "컴퓨터로 카톡",
            "지금 컴퓨터로",
        ),
        25,
        "가족·지인 자칭과 연락 수단 변경",
        # 요구 조건을 걸지 않았다. 이 어휘가 정상 문자에서 켜져도 사용자가 받는
        # 조언은 "원래 알던 번호로 직접 전화해 보세요"뿐이고, 상대가 진짜
        # 지인이면 그 전화는 그냥 연결된다. **틀렸을 때의 비용이 통화 한 통**인
        # 신호에 요구 조건을 걸면 진짜 사칭 문자를 놓치는 쪽 비용이 훨씬 크다.
    ),
    SignalRule(
        "guaranteed_return_offer",
        (
            # v0.4. "원금이 보장됩니다"는 예금 안내문의 **사실**이고, "원금
            # 보장"을 약속하는 투자 권유는 자본시장법이 금지한 **거짓**이다.
            # 조사가 붙은 "원금이/원금은 보장"을 어휘에서 뺀 이유가 이것이다.
            "원금 보장",
            "원금보장",
            "원금을 보장",
            "손실 보전",
            "손실보전",
            "전액 보전",
            "확정 수익",
            "확정수익",
            "수익 보장",
            "수익보장",
            "무조건 수익",
            "절대 손해",
            "손해 볼 일 없",
        ),
        30,
        "원금·수익 보장 제안",
    ),
    SignalRule(
        "private_channel_invite",
        (
            # v0.4. **맨 명사를 쓰지 않는다.** "리딩방"·"단톡방"은 피해자
            # 자기보고("리딩방에서 알려준 계좌로 보냈는데요")와 예방 안내문에도
            # 똑같이 등장한다. 신호가 되는 것은 방의 이름이 아니라 **읽는 사람을
            # 그 방으로 들이려는 동작**이다. 그래서 초대·입장 어형까지 묶는다.
            "리딩방에 초대",
            "리딩방 초대",
            "리딩방으로",
            "리딩방 입장",
            "무료 리딩",
            "종목 추천방",
            "종목추천방",
            "추천방으로",
            "단톡방으로",
            "오픈채팅방으로",
            "오픈채팅으로",
            "비공개 방으로",
            "텔레그램 채널",
            "텔레그램으로 연락",
            "텔레그램으로 오",
            "1:1 상담방",
            "1대1 상담방",
            "전담 애널리스트",
            "vip방",
            "vip 방",
        ),
        25,
        "폐쇄 채널·리딩방 유도",
    ),
    SignalRule(
        "loan_policy_offer",
        (
            "저금리 대출",
            "정책자금",
            "정부지원 대출",
            "대환대출",
            "특례 대출",
            "보증료 입금",
            "정부 융자",
        ),
        30,
        "대출·정책금융 제안",
    ),
    SignalRule(
        "credential_request",
        (),
        40,
        "인증정보 요구",
        # 전부 맨 명사다. "OTP 카드를 재발급받았습니다"·"비밀번호는 은행 직원도
        # 묻지 않습니다" 는 인증정보 요구가 아니다.
        demand_gated_keywords=(
            "인증번호",
            "비밀번호",
            "otp",
            "보안카드 번호",
            "일회용 승인코드",
        ),
    ),
    SignalRule(
        "account_access_request",
        (
            "계좌를 빌려",
            "계좌 대여",
            "카드를 보내",
            "카드 전달",
        ),
        40,
        "계좌·접근수단 요구",
        # 위 네 개는 그 자체가 요구문이다. 아래는 명사뿐이라 요구가 필요하다.
        # "계좌번호" 는 v0.3 에서 새로 넣었다 - held-out v0.2 의 `fh-005` 가
        # 계좌번호를 요구하는데 어휘에 없어 통째로 빠졌다.
        demand_gated_keywords=("체크카드", "통장", "계좌번호"),
    ),
    SignalRule(
        "app_install_request",
        (
            "apk",
            "실행파일",
            # v0.2 추가. fg-047("보안 모듈을 내려받아 실행")이 여기서 빠졌다.
            # 기존 어휘가 전부 "설치"라는 단어에 걸려 있어서, 같은 요구를
            # "내려받다"로 쓰면 통과했다. 잡는 것은 **받아서 실행하라는 지시**이지
            # 대상 파일의 이름이 아니다 - "보안 모듈" 같은 명사를 넣으면 은행
            # 정상 안내까지 걸린다.
            "설치 파일",
            "설치 링크",
        ),
        35,
        "앱 설치 요구",
        # v0.3. 어휘가 "앱 설치"·"프로그램 설치" 처럼 조사 없는 형태로만 있어서
        # 실제 문장인 "앱**을** 설치해 주세요" 를 못 잡았다. 조사 조합을 늘리는
        # 대신 동사만 남기고 요구를 조건으로 걸었다. 그러면 "앱 설치했는데
        # 오류가 납니다"(사용자 자신의 행동)는 켜지지 않는다.
        demand_gated_keywords=("설치", "내려받", "다운로드"),
    ),
    SignalRule(
        "remote_control_request",
        ("원격제어", "원격 접속", "화면 공유", "팀뷰어", "애니데스크"),
        40,
        "원격제어·화면공유 요구",
    ),
    SignalRule(
        "money_transfer_request",
        (
            "송금해",
            "입금해",
            "돈을 보내",
            # v0.2 추가. "송금"의 동의어인 "이체"가 통째로 빠져 있었다.
            # 지시형만 넣는다. 맨 "이체"를 넣으면 "이체 내역을 확인하세요" 같은
            # 정상 안내가 걸리고, "이체하지 마세요"는 지시형에 걸리지 않는다.
            "이체하세요",
            "이체해",
            "이체 바랍니다",
            "이체를 진행",
        ),
        35,
        "송금 요구",
        # v0.3. "안전계좌라는 것은 존재하지 않습니다" 가 v0.2 오탐이었다.
        # 계좌 이름은 명사일 뿐이고, 요구가 붙어야 요구다.
        demand_gated_keywords=("안전계좌", "보호계좌"),
    ),
    SignalRule(
        "receive_and_forward_money",
        (
            "입금받고",
            "재송금",
            "돈을 받아서 보내",
            "수령한 금액",
        ),
        70,
        "자금 수취·재전달 요구",
        # v0.3. "전달해"·"다시 보내" 는 v0.2 오탐 2건의 원인이었다. 계약서도
        # 명함도 "다시 보내" 달라고 한다. 자금 재전달로 만드는 것은 동사가 아니라
        # **목적어**다.
        #
        # "옮겨" 는 어미 문제다. 어휘에는 "제3자 계좌로 옮기" 가 있었는데 실제
        # 문장은 "옮겨 주시면" 이라 부분 문자열이 어긋났다. 활용형을 일반 규칙으로
        # 펴는 대신 필요한 형태만 적고, 대신 목적어 조건을 걸어 "인증서는 어떻게
        # 옮기나요" 같은 문장이 걸리지 않게 했다.
        money_gated_keywords=("다시 보내", "전달해", "옮기", "옮겨"),
    ),
    SignalRule(
        "card_delivery_claim",
        (
            "카드 배송",
            "카드가 발급",
            "신청한 카드",
            "카드 배달",
            "배송 기사",
            "신용카드 수령",
        ),
        35,
        "신청하지 않은 카드 배송·발급 주장",
    ),
)

# 호환 기준선이지만 **점수를 만드는 것은 이쪽이다**(`baseline_score`). 정상
# 문자에서 켜지면 등급이 그대로 올라간다. 그래서 어휘는 늘리지 않되 v0.3 의
# 요구·목적어 조건은 그대로 적용한다.
LEGACY_RULES: tuple[SignalRule, ...] = (
    SignalRule("urgency", ("오늘까지", "즉시", "긴급", "지금 바로"), 12, "긴급한 행동 요구"),
    SignalRule(
        "credential",
        (),
        25,
        "인증정보 요구",
        demand_gated_keywords=("인증번호", "비밀번호", "otp"),
    ),
    SignalRule(
        "account_access",
        ("계좌를 빌려", "계좌 대여"),
        35,
        "계좌·접근수단 요구",
        demand_gated_keywords=("체크카드", "통장"),
    ),
    SignalRule(
        "remote_app",
        ("원격제어", "apk"),
        30,
        "앱 설치·원격접속 요구",
        demand_gated_keywords=("설치",),
    ),
    SignalRule(
        "money_mule",
        ("입금받고", "재송금"),
        35,
        "자금 수취·재전달 요구",
        money_gated_keywords=("다시 보내", "전달해"),
    ),
)

CANONICAL_TO_LEGACY_PUBLIC: dict[str, str] = {
    "urgency_pressure": "urgency",
    "credential_request": "credential",
    "account_access_request": "account_access",
    "app_install_request": "remote_app",
    "remote_control_request": "remote_app",
    "receive_and_forward_money": "money_mule",
}
LEGACY_RULE_BY_CODE = {rule.code: rule for rule in LEGACY_RULES}

URL_CANDIDATE_PATTERN = re.compile(
    r"(?:https?://|www\.|(?:bit\.ly|cutt\.ly|goo\.gl|han\.gl|is\.gd|me2\.do|"
    r"t\.co|tinyurl\.com|url\.kr)/)[^\s<>\"']+",
    re.IGNORECASE,
)

# 실제 스미싱 문자는 스킴 없이 `1.2.3.4/login` 형태로 온다.
# 경로가 붙은 것만 링크 후보로 본다. 그래야 "report.pdf" 같은 문자열을 링크로 오인하지 않는다.
BARE_URL_CANDIDATE_PATTERN = re.compile(
    r"(?<![\w@.\-/])"
    r"(?:"
    r"\d{1,3}(?:\.\d{1,3}){3}"
    r"|[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?)*"
    r"\.[a-z]{2,24}"
    r")"
    r"(?::\d{2,5})?"
    r"/[^\s<>\"']*",
    re.IGNORECASE,
)

# `scheme://host` 형태
SCHEME_SEPARATED_PATTERN = re.compile(r"^[a-z][a-z0-9+.\-]*://", re.IGNORECASE)
# `javascript:`, `data:`, `mailto:` 처럼 호스트가 없는 스킴.
# 콜론 뒤가 숫자면 `example.com:8080` 같은 포트 표기이므로 스킴으로 보지 않는다.
OPAQUE_SCHEME_PATTERN = re.compile(r"^[a-z][a-z0-9+.\-]*:(?![0-9])", re.IGNORECASE)
SAFE_URL_SCHEMES = {"http", "https"}

KNOWN_SHORTENERS = {
    "bit.ly",
    "cutt.ly",
    "goo.gl",
    "han.gl",
    "is.gd",
    "me2.do",
    "t.co",
    "tinyurl.com",
    "url.kr",
}


# 사기 문자는 "공식 창구에서 직접 확인하라"고 말하지 않는다. 공식 창구로 가면
# 거짓이 드러나기 때문이다. 그래서 이 문구는 예방 안내문의 표지로 쓸 수 있다.
OFFICIAL_VERIFICATION_PHRASES = (
    "공식 누리집",
    "공식 홈페이지",
    "공식 웹사이트",
    "공식 창구",
    "공식 대표번호",
    "대표번호로 확인",
    "대표번호로 직접",
)

# 위 문구가 있어도 읽는 사람에게 무언가를 요구하면 억제하지 않는다. 안전 문구를
# 앞에 붙여 놓고 뒤에서 요구하는 혼합 문장이 실제로 존재하고, 그것이 이 억제
# 규칙을 노리는 가장 쉬운 우회다.
READER_DEMAND_PHRASES = (
    "송금",
    "입금",
    "이체",
    "설치",
    "내려받",
    "다운로드",
    "알려 주세요",
    "알려주세요",
    "보내 주세요",
    "보내주세요",
    "입력",
    "전달",
    "회신",
    "연락 주세요",
    "연락주세요",
)

# "저희는 …를 요구하지 않습니다" 는 요구가 아니라 요구에 대한 서술이다.
# 예방 안내문과 사기 문자는 어휘가 거의 같고, 갈리는 자리가 여기다.
# 서술형만 넣는다. "설치하지 마세요" 같은 부정 명령형을 넣으면 "아무에게도
# 말하지 마시고 통화를 끊지 마세요"(실제 사기 문장)까지 예방 안내문이 된다.
PREVENTION_STATEMENT_MARKERS = (
    "요구하지 않",
    "요청하지 않",
    "요구하는 일은 없",
    "묻지 않",
    "물어보지 않",
    "보내지 않",
    "알려 드리지 않",
    "존재하지 않",
)

# 읽는 사람을 향한 요구의 표지. `READER_DEMAND_PHRASES` 보다 넓다 - 저쪽은
# "안내문인가"를 가리는 좁고 위험한 요구만 모은 목록이고, 이쪽은 맨 명사를
# 신호로 승격시킬지 판단하는 데 쓴다.
#
# **맨 명령형 어미는 넣지 않는다.** "하세요"·"바랍니다"를 넣었더니 "이체 내역을
# 확인하세요. 모르는 출금이 있으면 은행에 문의하세요" 가 은행 사칭이 됐다.
# 정상 안내도 명령형을 쓴다. 그래서 이 목록에는 "-아/어 주세요" 계열(무언가를
# 해 달라는 부탁)과 대상이 분명한 동사만 남긴다.
DEMAND_MARKERS = (
    "주세요",
    "주십시오",
    "주시기",
    "주시면",
    "주실",
    "주시길",
    "주셔야",
    "부탁",
    "빌려",
    "알려",
    "불러",
    "입력",
    "회신",
    "제출해",
    "등록해",
    "전송",
    "요청합니다",
    "요청드립니다",
)

# 요구의 두 번째 계열: **위험한 행동이 동사가 된 자리**.
#
# 위 목록만으로는 부탁의 형식을 빌리지 않은 지시를 놓친다. "앱 설치가
# 필요합니다"·"내려받아 실행하면 본인 확인이 끝납니다"·"지금 설치하세요" 에는
# "주세요"가 없다. 반대로 맨 어미를 세면 정상 안내가 걸린다.
#
# 가르는 자리는 어미가 아니라 **어근에 무엇이 붙었는가**다. "이체 내역"의
# '이체'는 뒤에 명사가 오므로 서술이고, "이체하세요"·"이체가 필요합니다"의
# '이체'는 읽는 사람이 할 행동이다. 과거형("송금했습니다")은 넣지 않는다 -
# 이미 한 일을 말하는 것은 요구가 아니라 자기 보고다.
RISKY_ACTION_STEMS = (
    "설치",
    "다운로드",
    "송금",
    "입금",
    "이체",
    "인증",
    "입력",
    "전송",
    "제출",
    "회신",
    "실행",
    "허용",
    "클릭",
)

# "…가 필요합니다" 는 부탁의 형식을 빌리지 않은 요구다. 다만 무엇이 필요하다고
# 말하는지가 갈림길이다 - "본인 확인이 필요합니다" 는 정상 안내에도 흔하다.
# 그래서 위험한 행동과 **넘겨줄 수 있는 물건**만 대상으로 센다.
DEMANDABLE_OBJECTS = RISKY_ACTION_STEMS + (
    "체크카드",
    "통장",
    "계좌번호",
    "인증번호",
    "비밀번호",
    "otp",
    "보안카드",
)

_RISKY_ACTION_ALTERNATION = "|".join(RISKY_ACTION_STEMS)
_DEMANDABLE_OBJECT_ALTERNATION = "|".join(DEMANDABLE_OBJECTS)
#
# 부정형("설치하지 마세요")은 제외한다. 하지 말라는 말은 요구가 아니다.
ACTION_DEMAND_PATTERN = re.compile(
    # 어근 + 하다-동사화. "했"·"됐" 같은 완료형은 의도적으로 빠져 있다.
    rf"(?:{_RISKY_ACTION_ALTERNATION})(?:하|해|한|할)(?!지\s*마)"
    # 대상 + 필요 서술. "설치가 필요합니다"·"체크카드가 필요합니다" 는 부탁이
    # 아니지만 요구다.
    rf"|(?:{_DEMANDABLE_OBJECT_ALTERNATION})(?:을|를|가|이)?\s*필요"
    # 대상 + 완료·진행 요구. "설치를 완료하세요" 는 위 두 가지에 다 걸리지
    # 않는다 - 어근에 붙은 것이 조사라 동사화가 아니고, 필요 서술도 아니다.
    # 능동형만 센다. "인증이 완료되었습니다" 는 요구가 아니라 결과 통보다.
    rf"|(?:{_DEMANDABLE_OBJECT_ALTERNATION})(?:을|를|가|이)?\s*(?:완료|진행)(?:하|해)(?!지\s*마)"
    # "내려받"은 명사로 쓰이지 않아 어근만으로 이미 행동을 가리킨다.
    r"|내려받(?!지\s*마)"
)

# 돈을 가리키는 목적어. "원"은 넣지 않는다 - 원격·지원·직원·병원에 다 들어간다.
MONEY_OBJECT_TERMS = (
    "돈",
    "금액",
    "자금",
    "대금",
    "현금",
    "입금",
    "송금",
    "잔액",
    "수익금",
    "수수료",
    "이체",
)

CLAUSE_BOUNDARY_PATTERN = re.compile(r"[.!?\n]+")

def _clauses(normalized: str) -> list[str]:
    return [part for part in CLAUSE_BOUNDARY_PATTERN.split(normalized) if part.strip()]


def _demanding_clauses(normalized: str) -> list[str]:
    """예방 서술이 든 절은 요구를 공급하지 못한다.

    "안전계좌로 송금하라고 요구하는 일은 없습니다" 에는 '송금'이 들어 있지만
    이 문장은 송금을 요구하지 않는다. 절 단위로 걸러야 이 구분이 선다.
    """
    return [
        clause
        for clause in _clauses(normalized)
        if not any(marker in clause for marker in PREVENTION_STATEMENT_MARKERS)
    ]


def _has_reader_demand(normalized: str) -> bool:
    for clause in _demanding_clauses(normalized):
        if any(marker in clause for marker in DEMAND_MARKERS):
            return True
        if ACTION_DEMAND_PATTERN.search(clause):
            return True
    return False


def _mentions_money(normalized: str) -> bool:
    return any(term in normalized for term in MONEY_OBJECT_TERMS)


def _is_prevention_notice(normalized: str) -> bool:
    """요구가 하나도 없는 예방·정상 이용 안내문인가.

    표지는 두 가지다. 공식 창구를 직접 가리키거나("공식 대표번호로 확인하세요"),
    무엇을 요구하지 않는지 서술하거나("OTP 는 은행 직원도 묻지 않습니다").
    사기 문자는 둘 다 하지 않는다 - 공식 창구로 가면 거짓이 드러나기 때문이다.

    표지가 있어도 예방 서술 밖의 절에 위험한 요구가 있으면 억제하지 않는다.
    안전 문구를 앞에 붙이고 뒤에서 요구하는 혼합 문장이 이 규칙을 노리는 가장
    쉬운 우회다.
    """
    has_marker = any(
        phrase in normalized for phrase in OFFICIAL_VERIFICATION_PHRASES
    ) or any(marker in normalized for marker in PREVENTION_STATEMENT_MARKERS)
    if not has_marker:
        return False
    return not any(
        phrase in clause
        for clause in _demanding_clauses(normalized)
        for phrase in READER_DEMAND_PHRASES
    )


def _detect_by_rules(text: str, rules: tuple[SignalRule, ...]) -> list[RiskSignal]:
    normalized = text.casefold()
    has_demand = _has_reader_demand(normalized)
    has_money = _mentions_money(normalized)
    detected = []
    for rule in rules:
        matched = (
            any(keyword.casefold() in normalized for keyword in rule.keywords)
            or (
                has_demand
                and any(
                    keyword.casefold() in normalized
                    for keyword in rule.demand_gated_keywords
                )
            )
            or (
                has_money
                and any(
                    keyword.casefold() in normalized
                    for keyword in rule.money_gated_keywords
                )
            )
        )
        if matched and not _safe_context_suppresses(rule.code, normalized):
            detected.append(
                RiskSignal(code=rule.code, label=rule.label, weight=rule.weight)
            )
    return detected


def _safe_context_suppresses(code: str, normalized: str) -> bool:
    """명시적인 예방·정상 이용 문맥만 억제한다.

    일반 negation 해석기가 아니다. 공격 지시가 함께 있는 혼합 문장은 억제하지
    않도록 좁은 문구 조합만 사용한다.
    """
    # v0.3. 예방 안내문 억제를 **모든 신호**로 넓혔다. 전에는 기관명·상품명
    # 신호에만 걸려 있어서 "금융감독원은 앱 설치를 요구하지 않습니다" 가
    # 사칭 신호는 면했지만 설치 요구 신호에 그대로 걸렸다.
    if _is_prevention_notice(normalized):
        return True
    if code in {"credential_request", "account_access_request"}:
        return any(
            phrase in normalized
            for phrase in ("알려주지 마세요", "공유하지 마세요", "전달하지 마세요")
        ) and not any(
            phrase in normalized
            for phrase in (
                "답장해",
                "보내 주세요",
                "불러 주세요",
                "입력해 주세요",
                "입력하세요",
                "전송해 주세요",
                "말해 주세요",
                "제출해 주세요",
            )
        )
    if code in {"authority_impersonation", "money_transfer_request"}:
        return "요구하지 않습니다" in normalized and not any(
            phrase in normalized
            for phrase in (
                "송금해",
                "입금해",
                "돈을 보내",
                "보호계좌로 보내",
                "안전계좌로 보내",
            )
        )
    if code == "guaranteed_return_offer":
        # 예금자보호법상 한도 안의 예금은 **실제로** 원금이 보장된다. 같은
        # 문구가 예금 안내문에서는 사실이고 투자 권유에서는 자본시장법이 금지한
        # 거짓이다. 둘을 가르는 것은 문구가 아니라 제도 근거를 함께 대는지다.
        return any(
            phrase in normalized
            for phrase in ("예금자보호", "예금자 보호", "예금보험공사")
        )
    if code == "loan_policy_offer":
        return (
            "상품을 비교" in normalized
            and "공식 금리" in normalized
            and "보증료 입금" not in normalized
        )
    if code in {"app_install_request", "remote_control_request"}:
        return any(
            phrase in normalized
            for phrase in (
                "설치하지 마세요",
                "허용하지 마세요",
                # v0.2. "내려받"·"다운로드"를 어휘에 넣은 순간 그 부정형도
                # 걸리기 시작했다. "모르는 사람이 보낸 파일은 절대 내려받지
                # 마세요" 는 예방 안내문이지 설치 요구가 아니다.
                "내려받지 마세요",
                "다운로드하지 마세요",
                "다운로드 하지 마세요",
            )
        ) and not any(
            phrase in normalized
            for phrase in (
                "설치해 주세요",
                "설치하세요",
                "원격 접속을 허용하세요",
                "화면 공유를 켜 주세요",
            )
        )
    if code == "card_delivery_claim":
        return "제가 신청한" in normalized and "공식 앱" in normalized
    return False


def _is_lexically_suspicious_url(raw_url: str) -> bool:
    """링크를 열지 않고 문자열 형태만으로 위험 여부를 판단한다.

    서버는 이 URL 을 요청하지 않는다. 순수 문자열 검사다.

    스킴 유무로 검사 범위가 갈리면 `http://1.2.3.4/login` 은 잡히고
    `1.2.3.4/login` 은 통과하는 구멍이 생긴다. 스킴이 없으면 https 를 가정해
    호스트를 뽑고, 스킴이 있든 없든 같은 검사를 적용한다.
    """
    candidate = raw_url.strip().rstrip(".,;:!?)]}")
    if not candidate:
        return False

    has_scheme = SCHEME_SEPARATED_PATTERN.match(candidate) is not None
    if not has_scheme and OPAQUE_SCHEME_PATTERN.match(candidate):
        # javascript:, data:, mailto: 는 링크로 위장한 실행·수집 지시일 수 있다.
        return True

    parse_target = candidate if has_scheme else f"https://{candidate}"
    try:
        parsed = urlsplit(parse_target)
        hostname = (parsed.hostname or "").casefold().rstrip(".")
    except ValueError:
        # 대괄호 불일치 등 파싱되지 않는 문자열은 정상 링크로 취급하지 않는다.
        return True

    scheme = parsed.scheme.casefold()
    if has_scheme and scheme not in SAFE_URL_SCHEMES:
        return True
    if scheme == "http":
        return True
    if not hostname:
        return False
    if parsed.username is not None or parsed.password is not None:
        return True
    if hostname == "localhost" or hostname.endswith(".localhost"):
        return True
    if hostname.startswith("xn--") or ".xn--" in hostname:
        return True
    if any(
        hostname == shortener or hostname.endswith(f".{shortener}")
        for shortener in KNOWN_SHORTENERS
    ):
        return True

    try:
        ip_address(hostname)
    except ValueError:
        return False
    return True


def _url_candidates(text: str, supplied_url: str | None = None) -> list[str]:
    candidates = [match.group(0) for match in URL_CANDIDATE_PATTERN.finditer(text)]
    candidates.extend(
        match.group(0) for match in BARE_URL_CANDIDATE_PATTERN.finditer(text)
    )
    if supplied_url and supplied_url.strip():
        candidates.append(supplied_url)
    return candidates


def contains_url(text: str, supplied_url: str | None = None) -> bool:
    return bool(_url_candidates(text, supplied_url))


def detect_legacy_signals(text: str) -> list[RiskSignal]:
    return _detect_by_rules(text, LEGACY_RULES)


def detect_canonical_signals(
    text: str, supplied_url: str | None = None
) -> list[RiskSignal]:
    detected = _detect_by_rules(text, SIGNAL_RULES)
    url_candidates = _url_candidates(text, supplied_url)

    if any(_is_lexically_suspicious_url(url) for url in url_candidates):
        detected.append(
            RiskSignal(
                code="suspicious_link",
                label="주의가 필요한 링크 형식",
                weight=35,
            )
        )

    return detected


def project_public_signals(canonical_signals: list[RiskSignal]) -> list[RiskSignal]:
    """내부 canonical 신호를 의미상 중복 없는 public API 신호로 변환한다."""
    projected: list[RiskSignal] = []
    seen_codes: set[str] = set()
    canonical_codes = {signal.code for signal in canonical_signals}

    for signal in canonical_signals:
        if (
            signal.code == "money_transfer_request"
            and "receive_and_forward_money" in canonical_codes
        ):
            continue
        legacy_code = CANONICAL_TO_LEGACY_PUBLIC.get(signal.code)
        if legacy_code is None:
            public_signal = signal
        else:
            legacy_rule = LEGACY_RULE_BY_CODE[legacy_code]
            public_signal = RiskSignal(
                code=legacy_rule.code,
                label=legacy_rule.label,
                weight=legacy_rule.weight,
            )

        if public_signal.code not in seen_codes:
            projected.append(public_signal)
            seen_codes.add(public_signal.code)

    return projected


def baseline_score(signals: list[RiskSignal]) -> int:
    legacy_codes = {rule.code for rule in LEGACY_RULES}
    return min(sum(s.weight for s in signals if s.code in legacy_codes), 100)
