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
    # 낱말 하나에 담기지 않는 **요구**다. 조건은 `demand_gated_keywords` 와
    # 같고, 어휘의 모양만 다르다 - "계좌 조회 권한을 담당자에게 위임해" 는
    # 세 조각이 사이에 다른 말을 끼고 순서대로 온다. 붙여 적으면 어떤 실제
    # 문장도 잡지 못한다. v0.8.
    demand_gated_sequences: tuple[tuple[str, ...], ...] = ()
    # 동사만으로는 신호가 되지 않는 어휘다. "전달해"·"다시 보내"는 계약서에도
    # 쓴다. 목적어가 돈일 때만 자금 재전달이다.
    money_gated_keywords: tuple[str, ...] = ()
    # 낱말 하나에 담기지 않는 어형이다. "돈을 빼서 다른 계좌로 넣어" 는
    # "빼서" 와 "넣어" 사이에 목적지가 낀다. 붙여 적으면 그 어휘는 **어떤
    # 실제 문장도 잡지 못한다** - v0.5 가 "빼서 넣어" 를 그렇게 적어 뒀고
    # v0.6 `fh-446` 이 그대로 미탐이었다. 순서만 지키면 사이에 무엇이 오든
    # 받는다. 켜지는 조건은 `money_gated_keywords` 와 같다. v0.7.
    money_gated_sequences: tuple[tuple[str, ...], ...] = ()
    # 방 이름만으로는 신호가 되지 않는 어휘다. 단톡방·오픈채팅방·텔레그램은
    # 학부모 공지에도 워크샵 안내에도 쓴다. 같은 메시지 안에 **매매 맥락**이
    # 있어야 켠다. v0.6.
    investment_gated_keywords: tuple[str, ...] = ()
    # **요구의 대상이 아니라 보내는 쪽의 정체를 가리키는 어휘다.**
    #
    # 위 세 게이트와 조건의 모양이 다르다. 저쪽은 '이 명사가 요구의 대상인가'를
    # 묻고, 이쪽은 '이 메시지가 기관이 하지 않는 요구를 하고 있는가'를 묻는다.
    # 그래서 어휘는 **메시지 전체에서** 찾고(자칭은 끝난 일을 말하는 절에도
    # 들어간다), 조건은 다른 민감 요구 신호가 함께 켜졌는지로 본다. v0.6.
    request_gated_keywords: tuple[str, ...] = ()


# 계좌 권한을 **사람에게 넘기라**는 요구다. held-out v0.7 `fh-508`
# ("세무서 … 계좌 접근 권한을 담당자에게 위임해 주셔야 합니다")은 신호가
# **하나도** 켜지지 않았다. `세무서` 는 다른 민감 요구가 있어야 켜지는
# 조건부 자칭 어휘이고, `계좌 접근 권한` 은 어느 어휘에도 없었다. 두 게이트가
# 서로를 기다린 것이다.
#
# 권한 위임 자체는 정상 제도다. 법인 계좌를 세무 대리인에게 맡기고, 부모
# 계좌를 자녀가 대리 조회한다. 신호는 위임이 아니라 그 권한을 **누구에게**
# 넘기라는 요구이고, 그래서 수령자 표현을 어휘에 함께 넣는다. "영업점에서
# 위임장을 제출하셔야 합니다" 에는 수령자가 없다.
#
# 손으로 열다섯 줄을 적지 않고 곱한다. 손으로 적으면 조합 하나가 조용히
# 빠지고, 빠진 것을 알아차릴 방법이 없다.
_ACCOUNT_AUTHORITY_TERMS = ("계좌", "뱅킹", "통장")
_AUTHORITY_HANDOVER_TERMS = (
    "에게 위임",
    "쪽으로 위임",
    "에게 양도",
    "넘겨",
    "넘기",
)
ACCOUNT_AUTHORITY_SEQUENCES: tuple[tuple[str, ...], ...] = tuple(
    (account, "권한", handover)
    for account in _ACCOUNT_AUTHORITY_TERMS
    for handover in _AUTHORITY_HANDOVER_TERMS
)


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
        # 보내지 않는다. 아래 목록(은행·카드사·공단·세무 관청)은 조건부다.
        #
        # v0.6. 그 조건을 **요구 있음**에서 **민감 요구 있음**으로 바꾼다.
        # 전에는 기관명이 열린 절에 있고 메시지 어딘가에 요구가 있으면 켰다.
        # held-out v0.6 의 오탐 4건이 전부 그래서 났다 - `fh-422`
        # ("하나은행 앱 정기 점검 안내입니다 ... 문의는 고객센터로 부탁드립니다"),
        # `fh-423`·`fh-463`·`fh-464` 는 전부 기관 + **무해한 요구**다. 정상
        # 안내문도 회신을 부탁하고 문의를 권한다. 요구가 있다는 사실만으로는
        # 아무것도 갈리지 않는다.
        #
        # 두 가지를 함께 고친다.
        #
        # 첫째, **자칭은 요구의 대상이 아니다.** 전에는 기관명을 열린 절에서만
        # 찾았는데, 보내는 쪽의 정체는 끝난 일을 말하는 절에도 들어간다("○○
        # 은행입니다. 이상 거래가 감지되었습니다"). 정체는 요구의 목적어가
        # 아니므로 절 시제로 가릴 대상이 아니다. 그래서 메시지 전체에서 찾는다.
        #
        # 둘째, 게이트를 **민감 요구**로 좁힌다. 기관을 자칭하는 문자를 위험하게
        # 만드는 것은 요구의 존재가 아니라 요구의 내용이다 - 인증정보·계좌·앱
        # 설치·원격·송금·본인 인증처럼 진짜 기관이 문자로 시키지 않는 것.
        # 좁히는 수정이므로 값을 사기 쪽에서 치른다. 그 값은 v0.6 이 재고 있다.
        request_gated_keywords=(
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
            # v0.6. 게이트가 민감 요구를 요구하게 되면서 기관 어휘를 넓혀도
            # 정상 안내문이 걸리지 않는다. v0.2 에서 국세청을 넣었다가 물러섰던
            # 이유("국세청 홈택스에서 조회할 수 있습니다")가 여기서 해소된다 -
            # 조회 안내에는 민감 요구가 없다. held-out v0.6 의 정상 사례
            # `fh-425`~`fh-428` 이 이 어휘들을 그대로 쓰고 있고, 전부 조용해야
            # 한다.
            "농협",
            "토스",
            "증권사",
            "새마을금고",
            "세무서",
            "신용정보원",
            "금융결제원",
        ),
    ),
    SignalRule(
        "secrecy_isolation",
        # **비밀 유지는 정상이고, 확인 차단이 신호다.**
        #
        # 전 어휘는 `비밀로`·`보안 유지`·`혼자 처리` 같은 맨 낱말이었다.
        # 회사 대외비 공지, 계약 NDA, 생일 파티 문자가 매일 쓰는 말이고,
        # v0.7 동결 시점에 실제로 네 건(`fh-527`·`fh-528`·`fh-530`·
        # `fh-531`)이 이 어휘로 켜져 있었다. 그동안은 등급만 올렸으니
        # 눈에 안 띄었는데, 이 신호에 사기 유형을 붙이는 순간 네 건이
        # 전부 **사기 판정**이 된다.
        #
        # 기밀 유지는 화제를 어떤 집단 안에 두는 일이다. 사기가 요구하는
        # 것은 그것이 아니라 **제3자 확인의 봉쇄**이고, 그 어형은 둘 중
        # 하나로 나타난다 - 금지의 대상이 전칭이거나(아무에게도·누구에게도·
        # 주변에·가족에게도), 연락 창구를 보내는 쪽 하나로 좁히거나
        # (통화를 끊지 마·저와만 연락). 어느 쪽도 정상 문장이 쓸 일이 없다.
        #
        # `혼자 처리` 는 **읽는 사람에게 시키는 형태**만 남긴다. 화자가
        # 자기를 두고 하는 말(`혼자 처리할 수 있을 것 같아요`)은 요구가
        # 아니다. 같은 낱말이 주어에 따라 갈린다.
        (
            "아무에게도 말하지",
            "아무에게도 알리지",
            "누구에게도 말",
            "누구에게도 알리",
            "누구에게도 보여",
            "주변에 말하지",
            "주변에는 알리지",
            "주변에 알리지",
            "가족에게도 알리",
            "가족에게도 말",
            "가족에게도 비밀",
            "통화를 끊지",
            "통화 끊지",
            "전화 끊지",
            "전화를 끊지",
            "혼자 처리하셔",
            "혼자 처리하세",
            "혼자 조용히",
            "저와만 연락",
            "저에게만 연락",
            "제게만 연락",
        ),
        18,
        "주변 확인을 막는 고립 요구",
    ),
    SignalRule(
        "familiar_person_claim",
        (
            # v0.4. 지인·가족 사칭에서 **검증 가능한 표지는 사칭 주장 자체가
            # 아니다.** "엄마야"는 진짜 엄마도 쓴다. 이 사기를 성립시키는 것은
            # 원래 알던 연락처로 확인할 수 없게 만드는 핑계다. 그래서 어휘를
            # 호칭이 아니라 **연락 수단이 바뀐 이유**로 잡는다.
            "폰이 고장",
            "폰 고장",
            "핸드폰이 고장",
            "휴대폰이 고장",
            # v0.5. 바로 위 "폰 고장"과 아래 세 줄은 전부 **같은 핑계의
            # 다른 활용형**이다. 어휘를 조사·어미가 붙은 한 형태로만 적어
            # 두면 실제 문장과 어긋난다. "폰이 고장"은 있는데 조사를 뺀
            # "폰 고장"이 없어서 held-out v0.5 의 `fh-301` 이 통째로 빠졌다.
            "폰이 망가",
            "핸드폰이 망가",
            "휴대폰이 망가",
            "액정이 깨",
            "액정 깨",
            "폰 액정",
            "새 번호로",
            "번호가 바뀌었",
            "번호 바뀌었",
            # 능동형. "번호 바꿨어"는 사칭 문자가 실제로 쓰는 형태다.
            # "번호가 바뀌어서"(정상 안내)와는 어형이 다르므로 여기서
            # 갈린다 - 남이 바꾼 것이 아니라 자기가 바꿨다고 말한다.
            "번호 바꿨",
            "번호를 바꿨",
            "이 번호로 저장",
            "전화가 안 돼",
            "전화가 안돼",
            "카톡이 안 돼",
            "카톡이 안돼",
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
            # 구어형. 약속의 내용이 "손실 보전"과 같다. 보조용언 어간까지만
            # 적는다 - "드리"로 적어 두면 "메워 드립니다"가 안 걸린다.
            # 한글은 어미가 앞 음절에 합쳐지므로("드리"+"ㅂ니다"→"드립니다")
            # 활용형의 접두사가 기본형이 아니다. 여기서 한 번 틀렸다.
            "메워 드",
            "메워 주",
            "메워 줄",
            "메워 줘",
            "확정 수익",
            "확정수익",
            # v0.5. "3배 확정입니다" 처럼 배수와 붙는 형태. 맨 "확정"은
            # 넣지 않는다 - "만기일이 확정되었습니다"가 보장 약속이 된다.
            "배 확정",
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
            # v0.6. 단톡방·오픈채팅방·텔레그램·비공개 방은 **여기서 뺐다.**
            # 아래 `investment_gated_keywords` 로 내려간다. 조사가 붙은 형태
            # ("단톡방으로"·"오픈채팅방 입장")만 적어 두는 것으로는 아무것도
            # 갈리지 않는다는 것이 v0.6 에서 드러났다 - "워크샵 안내는
            # 오픈채팅방으로 옮겼습니다"(`fh-410`)가 오탐이 되고, "주식 스터디
            # 단톡방 초대할게"(`fh-405`)는 어형이 없어 빠졌다. 방 이름의
            # 활용형을 쫓는 일은 끝이 없고, 끝까지 쫓아도 정상 단톡방과
            # 사기 단톡방은 여전히 같은 말을 쓴다.
            #
            # v0.4 `fh-244` 와 v0.5 `fh-308` 이 남긴 질문의 답이 이것이다 -
            # 갈림길은 초대의 어형이 아니라 **무엇을 위한 초대인가**이고,
            # 그것은 방 이름 옆의 매매 어휘로만 보인다.
            "1:1 상담방",
            "1대1 상담방",
            "전담 애널리스트",
            "vip방",
            "vip 방",
        ),
        25,
        "폐쇄 채널·리딩방 유도",
        # 맨 방 이름이다. 그 자체로는 학부모 공지·동아리·워크샵 안내에 그대로
        # 쓰인다(held-out v0.6 `fh-407`~`fh-411`). 같은 메시지에 매매 맥락이
        # 있을 때만 켠다. **리딩방·종목추천방 계열은 위 목록에 그대로 둔다** -
        # 그쪽은 이름 자체가 이미 매매를 말하고 있어 조건이 필요 없다.
        investment_gated_keywords=(
            "단톡방",
            "오픈채팅방",
            "오픈 채팅방",
            "오픈채팅",
            "비공개 방",
            "체험방",
            "텔레그램",
        ),
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
            # v0.5. 구어형. 요구 조건이 걸려 있어 "비번 잊어버렸어"는
            # 켜지지 않는다.
            "비번",
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
        demand_gated_sequences=ACCOUNT_AUTHORITY_SEQUENCES,
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
        # v0.5. "깔다"는 "설치"의 구어형이고 사칭 문자가 반말일 때 거의
        # 항상 이쪽을 쓴다. 요구 조건은 그대로 걸려 있어서 "가계부 앱
        # 깔았는데 편하더라"(자기 행동)는 켜지지 않는다.
        demand_gated_keywords=("설치", "내려받", "다운로드", "깔아"),
    ),
    SignalRule(
        "remote_control_request",
        (
            "원격제어",
            "원격 접속",
            "화면 공유",
            "팀뷰어",
            "애니데스크",
            # v0.5. 띄어쓰기 없는 표준 표기만 있어서 "원격 프로그램"을
            # 놓쳤다. 맨 "원격"은 넣지 않는다 - 원격근무·원격수업이 있다.
            "원격 프로그램",
        ),
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
        # v0.5. "빼서 넣어"·"빼서 보내"는 재전달의 구어형이다. 금액 조건은
        # 그대로라 목적어가 돈일 때만 켜진다.
        #
        # v0.7. 세 가지를 바꿨다.
        #
        # 첫째, "넘겨"·"넘기" 가 통째로 없었다. held-out v0.3 `fh-138`
        # ("들어온 돈은 그대로 다른 계좌로 넘겨 주시면 됩니다")이 그 구멍으로
        # 미탐이었고 두 회차를 그대로 지나왔다.
        #
        # 둘째, "빼서 넣어"·"빼서 보내" 를 `money_gated_sequences` 로 옮겼다.
        # 실제 문장은 그 사이에 목적지가 낀다(v0.6 `fh-446`). 붙여 적은 두
        # 어휘는 두 회차 동안 **한 번도 켜진 적이 없다.**
        #
        # 셋째, **조건에 요구를 더했다.** 목적어만 보면 "자동이체로 걸어
        # 뒀어" 의 "이체" 가 금액 조건을 채우고, "월급 들어오면 적금 계좌로
        # 옮겨 놓을게" 가 자금 재전달 요구가 된다. 목적어는 이 문장이 돈
        # 이야기라는 것만 말해 줄 뿐 **읽는 사람에게 시키는 말인지**는 말해
        # 주지 않는다. 화자가 제 계좌 사이에서 옮기겠다는 것은 요구가 아니다.
        # 맨 명사를 요구에 걸었던 것과 같은 이유이고, 위 두 확장이 어휘를
        # 넓히는 만큼 이 조건 없이는 정상 문장을 함께 데려온다.
        money_gated_keywords=(
            "다시 보내",
            "전달해",
            "옮기",
            "옮겨",
            "넘겨",
            "넘기",
        ),
        money_gated_sequences=(
            ("빼서", "넣어"),
            ("빼서", "보내"),
            ("빼서", "이체"),
        ),
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
    # v0.5. held-out v0.4 의 오탐 2건과 v0.5 의 3건이 전부 여기서 났다. 목록의
    # 모양은 그대로 유지한다 - **어간이 붙은 서술형만 넣고 맨 "하지 않"은 넣지
    # 않는다.** 맨 형태를 넣으면 "소명하지 않으면 계좌가 동결됩니다"·"인증을
    # 완료하지 않으면 카드가 정지됩니다" 같은 협박문이 통째로 예방 안내문이
    # 된다. 협박은 부정형을 조건절로 쓰고, 안내문은 종결형으로 쓴다.
    # v0.8. 맨 "드리지 않" 은 여기서 빠지고 아래
    # `PREVENTION_STATEMENT_PATTERNS` 로 내려간다. 이유는 그 목록에 적었다.
    "안내하지 않",
    "추천하지 않",
    "권유하지 않",
    "운영하지 않",
    "보장하지 않",
    "발송하지 않",
)

# v0.8. 맨 "드리지 않" 은 **보조용언 자리를 넘어간다.**
#
# `말씀드리지 않는 게 좋겠습니다`(held-out v0.7 `fh-523`, 고립 요구)와
# `건드리지 않`(held-out v0.6 `fh-455`, 사기 사례)이 그 낱말 하나로 예방
# 안내문이 됐다. 앞의 것은 **읽는 사람에게** 말하지 말라는 요구이지 보내는
# 쪽이 무엇을 안 한다는 서술이 아니다.
#
# 보조용언 `드리다` 는 앞말과 띄어 쓰거나 연결어미(-아/-어/-해/-려/-워)
# 뒤에 붙는다. `말씀드리다`·`건드리다` 는 보조용언 구성이 아니라 한 낱말이다.
# 그 자리를 정규식으로 못 박는다 - 목록의 원칙("어간이 붙은 서술형만")과
# 같은 이야기이고, 다만 어간이 아니라 **앞자리**를 본다.
#
# 완벽한 구분은 아니다. `안내드리지 않으며`·`전화드리지 않으며` 는 이 패턴에
# 걸리지 않는다. 둘 다 정상 안내문에 나오지만 그런 문장은 `묻지 않`·`요구하지
# 않` 같은 표지를 함께 달고 있고, 표지는 하나만 맞으면 된다. 놓치는 쪽이
# 억제를 **덜** 하는 방향이라 안전한 실패다.
PREVENTION_STATEMENT_PATTERNS = (
    re.compile(r"(?:^|[\s,·\"'()\[\]])드리지\s*않"),
    re.compile(r"(?:해|려|어|아|워)\s*드리지\s*않"),
)

# 이미 일어난 일을 말하는 절이다. **요구도 아니고 요구의 대상도 아니다.**
#
# held-out 세 판에 걸쳐 남은 오탐이 전부 이 한 가지였다 - "체크카드 재발급이
# 발송되었습니다. 공식 앱에서 등록해 주세요"(v0.2 `fh-050`), "입금 확인했습니다.
# 주소가 바뀌었으면 다시 보내 주세요"(v0.2 `fh-063`), "은행 창구에서 신분증을
# 제출하고 계좌를 개설했습니다"(v0.4 `fh-252`). 요구는 진짜 요구이고 위험한
# 명사도 진짜로 들어 있지만, 그 명사가 있는 절은 **끝난 일에 대한 보고**라서
# 요구의 대상이 될 수 없다.
#
# 어간만 세지 않는다. "확인하셨죠"·"보내신"처럼 상대의 행동을 가리키는 높임
# 과거형까지 걸려서, 자금 재전달 요구("입금된 금액 확인하셨죠 ... 전달해
# 주시면")가 조용히 꺼진다. 그래서 종결어미까지 함께 본다.
#
# **절 끝에 붙은 것만 센다.** 연결어미로 이어지는 과거형은 보고가 아니라
# 요구의 앞자락이다 - "아까 준 통장이랑 비밀번호로 인증했는데 하나만 더
# 알려 줘"(v0.4 `fh-224`)는 같은 절 안에서 과거형 뒤에 요구가 온다. 보고는
# 절을 끝내고, 절이 끝나지 않았다면 그 뒤에 오는 것이 요구다.
COMPLETED_REPORT_PATTERN = re.compile(
    r"(?:했|됐|였|웠|았|었)(?:습니다|습니까|어요|아요|다)[\s,·'\")\]]*$"
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

# 반말 요구. 위 목록이 "-아/어 주세요" 계열만 덮고 있어서 **반말로 오는 요구를
# 통째로 놓쳤다** (held-out v0.4 `fh-219`, v0.5 의 여덟 건).
#
# 이것을 뒤늦게 세는 것이 아니라 처음부터 세야 했다. 지인·가족 사칭 문자는 거의
# 전부 반말로 오고, 그것이 사칭의 일부다 - 존댓말로 "인증번호를 알려 주세요"
# 라고 쓰는 순간 가족인 척이 무너지기 때문이다. 존댓말 요구만 세는 게이트는
# 이 제품이 가장 잡아야 할 사기에서 가장 자주 열리지 않는다.
#
# 위 목록과 같은 원칙으로 만든다. **맨 명령형 어미는 넣지 않는다** - "확인해",
# "봐" 를 넣으면 정상 대화가 전부 요구가 된다. 남기는 것은 존댓말 목록의 거울,
# 즉 "-아/어 주다" 의 반말 활용과 "-아/어 놓다" 의 명령형뿐이다.
CASUAL_DEMAND_PATTERN = re.compile(
    # 보내 줘 / 알려 줘 / 넘겨 줘. "보내 줘서 고마워"(고마움)와 "해 줘도"(양보)는
    # 요구가 아니라서 뺀다.
    r"줘(?!서|도)"
    r"|줄래"
    r"|줄 수 있"
    # 깔아 놔 / 옮겨 놔. "놔두다"(내버려 두다)는 반대 뜻이라 뺀다.
    r"|[가-힣]\s*놔(?!두)"
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

# 매매 맥락. 방 이름을 신호로 승격시킬지 가르는 어휘다.
#
# **"투자"·"주식"은 넣지 않았다.** 주식회사·투자자 보호 안내처럼 정상 문장이
# 매일 쓰는 말이라, 방 이름과 만나면 학부모 단톡방 하나로도 오탐이 난다. 여기
# 있는 것은 값이 움직이는 것을 사고파는 자리에서만 쓰는 말이다.
INVESTMENT_CONTEXT_TERMS = (
    "종목",
    "매수",
    "매도",
    # v0.6. 아래 네 개는 held-out v0.4 `fh-214`("AI 자동매매 봇")와 v0.5
    # `fh-307`("장 마감 전까지만 열어 둡니다")·`fh-309`("실시간 매매 신호")가
    # 요구했다. 맨 방 이름을 이 게이트로 내리면서 그 세 건이 함께 꺼졌는데,
    # 그것은 좁히기의 값이 아니라 이 목록의 구멍이었다.
    "매매",
    "장 마감",
    "시황",
    "종가",
    "수익률",
    "수익 나",
    "수익 인증",
    "코인",
    "비트코인",
    "급등",
    "상한가",
    "단타",
    "시드",
    "리딩",
    "애널리스트",
    "차트",
    "공모주",
    "선물 거래",
    "원금 보장",
    "투자금",
    "재테크",
)

# 기관 자칭을 신호로 승격시키는 **민감 요구** 신호들.
#
# 진짜 기관도 문자를 보내고 회신을 부탁한다. 진짜 기관이 문자로 시키지 않는
# 것은 이쪽이다 - 인증정보·계좌·접근수단을 넘기라거나, 앱을 깔라거나, 원격을
# 열라거나, 돈을 보내라거나, 받은 돈을 다시 보내라는 것.
SENSITIVE_REQUEST_SIGNALS = frozenset(
    {
        "credential_request",
        "account_access_request",
        "app_install_request",
        "remote_control_request",
        "money_transfer_request",
        "receive_and_forward_money",
        "card_delivery_claim",
    }
)

# 위 신호 어디에도 걸리지 않는 민감 요구가 둘 있다. 넘겨주는 물건이 없어서
# 어느 규칙의 대상도 아니지만, 기관이 문자로 시키지 않는 행동이다.
#
# 하나는 본인 인증이다. 계정이 잠겼으니 지금 본인 인증을 완료하라는 문자는
# 기관이 보내지 않는다(held-out v0.6 `fh-414`). 다른 하나는 링크를 누르라는
# 요구다. 이것은 v0.6 이 아니라 주입 골든셋 `pi-002`("국민은행입니다. 계좌
# 확인을 위해 링크를 눌러 주세요")가 요구했다 - 게이트를 민감 요구로 좁히자
# 이 사례가 함께 꺼졌고, 그것은 좁히기의 값이 아니라 목록의 구멍이었다.
#
# 요구와 **같은 절**에 있을 때만 센다. "공식 앱에서 본인 인증을 완료하시면
# 조회 가능합니다"(`fh-433`)는 안내이지 요구가 아니고, 그 절은 아래 창구 안내
# 규칙에서 이미 빠진다.
SENSITIVE_DEMAND_TERMS = (
    "본인 인증",
    "본인인증",
    "본인확인",
    "본인 확인",
    "재인증",
    "계정 잠금 해제",
    "계정 해제",
    "링크",
    # **정상 기관은 이미 아는 창구로 보내고, 사기는 자기가 만든 창구로 부른다.**
    # 아래 창구 안내 규칙과 같은 자를 반대 방향으로 쓴 것이다. held-out v0.2
    # `fh-007`·`fh-011` 과 v0.3 `fh-109` 가 전부 이 모양이고, `fh-109` 는
    # 아예 "카드사 대표번호 말고 아래 담당자 번호로" 라고 쓴다 - 공식 창구를
    # 명시적으로 밀어내는 것이야말로 이 사기의 서명이다.
    "담당자 번호",
    "안내 번호",
    "아래 번호",
    "아래 연락처",
    "직통 번호",
    "전용 번호",
)

# **정상 기관은 이미 아는 창구로 보내고, 사기는 자기가 만든 창구로 부른다.**
#
# v0.6. held-out 다섯 판에 걸쳐 남은 오탐 중 마지막 무리가 이 모양이었다 -
# "통장 재발급은 창구에서만 처리 가능합니다"(`fh-430`), "비밀번호 변경은
# 인터넷뱅킹 홈페이지에서 직접 처리 가능합니다"(`fh-431`), "계좌번호 변경은
# 영업점에서만 신청 가능합니다"(`fh-432`). 위험한 명사가 진짜로 들어 있고 절에
# 요구도 붙어 있지만, 그 절이 가리키는 곳은 **읽는 사람이 이미 알고 있는
# 창구**다. 사기 문자는 이 말을 할 수 없다 - 그 창구로 가면 거짓이 드러난다.
#
# 두 조각을 함께 요구한다. 창구 이름에 **조사가 붙어 방향을 가리켜야** 하고
# (그래야 "○○은행 고객센터입니다" 같은 자칭이 걸리지 않는다), 같은 절에
# **안내 서술어**가 있어야 한다. 절 단위로만 본다. 메시지 단위로 보면 안전한
# 첫 문장 하나로 나머지 전부가 통과한다.
CHANNEL_REFERRAL_PATTERN = re.compile(
    r"(?:영업점|창구|고객센터|대표번호|홈페이지|누리집|인터넷뱅킹|공식 앱|모바일 앱|앱 내)"
    r"(?:에서만|에서도|에서|으로만|으로도|으로|로만|로도|로|에|\s*방문)"
)
CHANNEL_REFERRAL_VERBS = (
    "가능",
    "확인",
    "조회",
    "열람",
    "문의",
    "신청",
    "처리",
    "접수",
    "출력",
    "방문",
    "지참",
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
        # v0.8. 정규식 표지도 같은 자격이다. 목록에서만 빼고 여기서 빼지 않으면
        # 예방 서술 절이 요구를 공급하게 되고, 그 순간 진짜 예방 안내문이
        # 사기로 올라간다 - held-out v0.8 `fh-632` 가 정확히 그렇게 깨졌다.
        and not any(
            pattern.search(clause) for pattern in PREVENTION_STATEMENT_PATTERNS
        )
    ]


def _open_clauses(normalized: str) -> list[str]:
    """요구와 그 대상을 함께 공급할 수 있는 절만 남긴다.

    v0.5. 게이트를 **절 단위로 좁힌 것이 아니라 절 단위로 닫았다.** 요구와 대상이
    몇 번째 절 떨어져 있는지로는 가를 수 없다는 것이 held-out v0.5 를 얼리면서
    분명해졌다 - "체크카드 실물이 필요합니다. 기사님 보낼 테니 전달해 주세요"
    (사기)와 "통장 자동이체는 정상 처리되었습니다. 첨부 파일 확인만 부탁드립니다"
    (정상)는 거리가 똑같다. 거리는 신호가 아니다.

    가르는 것은 **절의 시제**다. 뒤쪽 문장의 '통장'은 끝난 일에 대한 보고 안에
    있어서 뒤따르는 요구의 대상이 될 수 없다. 그래서 예방 서술과 완료 보고를
    양쪽 게이트에서 함께 뺀다 - 그런 절은 요구도, 요구의 대상도 공급하지 않는다.

    v0.6 에서 세 번째 종류를 함께 뺀다. **이미 아는 창구를 가리키는 절**이다.
    시제가 아니라 방향으로 갈린다 - 그 절의 요구는 읽는 사람을 이 메시지 밖의
    공식 창구로 보내므로, 이 메시지가 무엇을 받아 가려는지에 대해 아무것도
    말하지 않는다.
    """
    return [
        clause
        for clause in _demanding_clauses(normalized)
        if not COMPLETED_REPORT_PATTERN.search(clause)
        and not _is_channel_referral(clause)
    ]


def _is_channel_referral(clause: str) -> bool:
    """읽는 사람을 이미 아는 공식 창구로 보내는 절인가."""
    if not CHANNEL_REFERRAL_PATTERN.search(clause):
        return False
    return any(verb in clause for verb in CHANNEL_REFERRAL_VERBS)


def _has_reader_demand(clauses: list[str]) -> bool:
    for clause in clauses:
        if any(marker in clause for marker in DEMAND_MARKERS):
            return True
        if ACTION_DEMAND_PATTERN.search(clause):
            return True
        if CASUAL_DEMAND_PATTERN.search(clause):
            return True
    return False


# 어휘에 바로 붙는 지시 어미. **전역 요구 목록에는 넣을 수 없는 것들이다** -
# "확인하세요"·"참고하세요"가 전부 요구가 되어 버린다. 게이트가 이미 어휘를
# 좁혀 둔 자리에서만 본다. v0.7.
DIRECT_IMPERATIVE_ENDINGS = ("세요", "십시오", "시오", "시길", "시기 바랍")


def _is_direct_imperative(text: str, keyword: str) -> bool:
    """동사가 그 자리에서 명령형이면, 요구가 문장 다른 곳에 또 있을 필요가 없다.

    개발셋 `fg-004`("자금을 지정 장소로 옮기세요")가 이것을 요구했다.
    "옮기세요" 는 존댓말 부탁 목록에도 반말 목록에도 없고, 위험 행동 어근
    목록에도 없다. 요구가 없는 것이 아니라 **요구가 동사에 붙어 있다.**
    """
    folded = keyword.casefold()
    return any(folded + ending in text for ending in DIRECT_IMPERATIVE_ENDINGS)


def _appears_in_order(text: str, sequence: tuple[str, ...]) -> bool:
    """어형이 낱말 하나에 담기지 않을 때, 순서만 지키면 받는다.

    사이에 무엇이 오는지는 묻지 않는다 - 거기 오는 것은 목적지이고,
    목적지의 이름을 어휘로 적기 시작하면 끝이 없다.
    """
    cursor = 0
    for part in sequence:
        found = text.find(part.casefold(), cursor)
        if found < 0:
            return False
        cursor = found + len(part)
    return True


def _mentions_money(clauses: list[str]) -> bool:
    return any(term in clause for clause in clauses for term in MONEY_OBJECT_TERMS)


def _mentions_investment(clauses: list[str]) -> bool:
    return any(
        term in clause for clause in clauses for term in INVESTMENT_CONTEXT_TERMS
    )


def _demands_something_sensitive(clauses: list[str]) -> bool:
    """넘겨줄 물건은 없지만 기관이 시키지 않는 요구가 한 절 안에 있는가."""
    return any(
        any(term in clause for term in SENSITIVE_DEMAND_TERMS)
        and _has_reader_demand([clause])
        for clause in clauses
    )


def _is_prevention_notice(normalized: str) -> bool:
    """요구가 하나도 없는 예방·정상 이용 안내문인가.

    표지는 두 가지다. 공식 창구를 직접 가리키거나("공식 대표번호로 확인하세요"),
    무엇을 요구하지 않는지 서술하거나("OTP 는 은행 직원도 묻지 않습니다").
    사기 문자는 둘 다 하지 않는다 - 공식 창구로 가면 거짓이 드러나기 때문이다.

    표지가 있어도 예방 서술 밖의 절에 위험한 요구가 있으면 억제하지 않는다.
    안전 문구를 앞에 붙이고 뒤에서 요구하는 혼합 문장이 이 규칙을 노리는 가장
    쉬운 우회다.

    v0.6. 그 탈출구를 `READER_DEMAND_PHRASES` 목록에서 **요구 판정 전체**로
    넓힌다. 좁은 목록으로는 어형 하나만 비켜 가면 통과했다 - held-out v0.6
    `fh-435` 는 "공식 홈페이지에서도 확인 가능합니다" 를 앞에 붙이고 뒤에서
    "인증번호를 알려 주시면" 이라고 한다. 목록에 있는 것은 "알려 주세요"
    뿐이라 이 문장은 예방 안내문으로 통과했다.

    넓혀도 정상 안내문이 걸리지 않는 이유는 창구 안내 절이 이제 열린 절에서
    빠지기 때문이다. "의심되면 대표번호로 확인해 주세요" 는 요구의 형식을
    갖췄지만 그 절은 창구 안내라 애초에 세지 않는다. 두 수정은 함께여야
    한다 - 하나만 넣으면 정상 예방 문자가 무너진다.
    """
    has_marker = (
        any(phrase in normalized for phrase in OFFICIAL_VERIFICATION_PHRASES)
        or any(marker in normalized for marker in PREVENTION_STATEMENT_MARKERS)
        or any(
            pattern.search(normalized) for pattern in PREVENTION_STATEMENT_PATTERNS
        )
    )
    if not has_marker:
        return False
    return not _has_reader_demand(_open_clauses(normalized))


def _detect_by_rules(
    text: str, rules: tuple[SignalRule, ...], *, has_suspicious_link: bool = False
) -> list[RiskSignal]:
    normalized = text.casefold()
    # 조건부 어휘는 **열린 절 안에서만** 찾는다. 요구가 어느 절에 있는지는 계속
    # 메시지 단위로 본다 - 사기 문자는 요구를 마지막 절에 몰아 쓰고 대상은 앞
    # 절에 흩어 놓기 때문에(`fh-324`는 두 절, `fh-325`는 세 절 떨어져 있다),
    # 거리를 재는 순간 진짜 사기부터 놓친다.
    open_clauses = _open_clauses(normalized)
    open_text = " ".join(open_clauses)
    has_demand = _has_reader_demand(open_clauses)
    has_money = _mentions_money(open_clauses)
    has_investment = _mentions_investment(open_clauses)

    def object_gated_match(rule: SignalRule) -> bool:
        return (
            any(keyword.casefold() in normalized for keyword in rule.keywords)
            or (
                has_demand
                and (
                    any(
                        keyword.casefold() in open_text
                        for keyword in rule.demand_gated_keywords
                    )
                    or any(
                        _appears_in_order(open_text, sequence)
                        for sequence in rule.demand_gated_sequences
                    )
                )
            )
            or (
                # v0.7. 목적어 **와** 요구를 함께 본다. 목적어만 보면
                # 화자가 제 계좌 사이에서 옮기겠다는 말이 재전달 요구가
                # 된다 - "자동이체" 의 "이체" 하나로 금액 조건이 찬다.
                has_money
                and (
                    any(
                        keyword.casefold() in open_text
                        and (
                            has_demand
                            or _is_direct_imperative(open_text, keyword)
                        )
                        for keyword in rule.money_gated_keywords
                    )
                    or (
                        has_demand
                        and any(
                            _appears_in_order(open_text, sequence)
                            for sequence in rule.money_gated_sequences
                        )
                    )
                )
            )
            or (
                has_investment
                and any(
                    keyword.casefold() in open_text
                    for keyword in rule.investment_gated_keywords
                )
            )
        )

    # v0.6. 두 번 돈다. 자칭 게이트의 조건이 **다른 신호가 켜졌는가**라서,
    # 한 번에 돌면 규칙 순서가 판정을 바꾼다. 첫 번째 바퀴는 요구의 대상으로
    # 켜지는 신호만 모으고, 두 번째 바퀴가 그 결과를 조건으로 쓴다.
    object_gated = {
        rule.code
        for rule in rules
        if object_gated_match(rule)
        and not _safe_context_suppresses(rule.code, normalized)
    }
    has_sensitive_request = (
        bool(object_gated & SENSITIVE_REQUEST_SIGNALS)
        # 어휘적으로 의심스러운 링크는 그 자체가 민감 요구다. 진짜 기관은 단축
        # URL 이나 IP 주소로 보내지 않는다. held-out v0.3 `fh-156`("국세청 환급금
        # 조회 서비스입니다. bit.ly/... 에서 환급 계좌를 등록해 주세요")이 이것을
        # 요구했다 - 요구의 대상은 '계좌 등록'이라 어느 규칙에도 걸리지 않지만,
        # 링크가 이미 이 문자가 무엇인지 말하고 있다.
        or has_suspicious_link
        or _demands_something_sensitive(open_clauses)
    )

    detected = []
    for rule in rules:
        matched = rule.code in object_gated or (
            has_sensitive_request
            # 자칭은 메시지 전체에서 찾는다. 요구의 대상이 아니라 보내는
            # 쪽의 정체라서, 절의 시제로 가릴 것이 아니다.
            and any(
                keyword.casefold() in normalized
                for keyword in rule.request_gated_keywords
            )
            and not _safe_context_suppresses(rule.code, normalized)
        )
        if matched:
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
    url_candidates = _url_candidates(text, supplied_url)
    # 링크 판정을 규칙 탐지보다 먼저 한다. 기관 자칭 게이트가 이 결과를 조건으로
    # 쓰기 때문이다. 신호를 붙이는 자리는 그대로 뒤에 둔다 - 순서가 바뀌면
    # 응답에 실리는 신호 목록의 순서가 바뀐다.
    has_suspicious_link = any(
        _is_lexically_suspicious_url(url) for url in url_candidates
    )
    detected = _detect_by_rules(
        text, SIGNAL_RULES, has_suspicious_link=has_suspicious_link
    )

    if has_suspicious_link:
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
