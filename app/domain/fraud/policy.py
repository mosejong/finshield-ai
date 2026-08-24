from dataclasses import dataclass

from app.schemas.analysis import Action, RiskSignal, UserState


@dataclass(frozen=True)
class ActionPolicy:
    priority: int
    title: str
    reason: str
    source_ids: tuple[str, ...]


ACTION_POLICIES: dict[str, ActionPolicy] = {
    "STOP_CONTACT": ActionPolicy(
        1,
        "상대방과의 연락을 중단하세요",
        "추가 지시를 따르기 전에 대화를 멈추면 피해 확대 가능성을 낮출 수 있습니다.",
        ("police_1394",),
    ),
    "DO_NOT_CLICK": ActionPolicy(
        1,
        "링크를 누르지 마세요",
        "출처가 확인되지 않은 링크는 개인정보 입력이나 악성 앱 설치로 이어질 수 있습니다.",
        ("kisa_smishing",),
    ),
    "DO_NOT_INSTALL": ActionPolicy(
        1,
        "앱이나 프로그램을 설치하지 마세요",
        "상대방이 보낸 앱은 단말 제어 또는 정보 탈취에 악용될 수 있습니다.",
        ("kisa_smishing",),
    ),
    "DO_NOT_SHARE_ACCESS": ActionPolicy(
        1,
        "인증정보와 금융 접근수단을 공유하지 마세요",
        "비밀번호, OTP, 통장, 카드를 넘기면 계좌와 자금에 접근할 수 있습니다.",
        ("electronic_financial_transactions_act",),
    ),
    "DO_NOT_FORWARD_MONEY": ActionPolicy(
        1,
        "받은 돈을 다른 곳으로 보내지 마세요",
        "출처를 모르는 자금을 재전달하면 피해가 커질 수 있으므로 먼저 금융기관에 확인해야 합니다.",
        ("police_1394", "fraud_refund_act"),
    ),
    "VERIFY_OFFICIAL_CHANNEL": ActionPolicy(
        2,
        "공식 대표번호로 사실을 확인하세요",
        "메시지에 적힌 연락처가 아니라 해당 기관의 공식 채널을 직접 찾아 확인하세요.",
        ("police_1394",),
    ),
    # 지인 사칭에는 확인할 "공식 대표번호"가 없다. 확인 수단은 기관 창구가 아니라
    # **이전부터 쓰던 연락처**이고, 그래서 위 액션과 다른 항목이어야 한다.
    # 같은 항목으로 묶으면 사용자에게 존재하지 않는 창구를 찾으라고 말하게 된다.
    #
    # v0.9. 이 항목은 지인 사칭 전용이 아니다. **이름을 대지 않은 상대** 전부가
    # 여기로 온다 - 자칭이 없으면 공식 대표번호도 없기 때문이다. 그래서 설명을
    # 지인 밖으로 넓혔다. 제목은 그대로 둔다: 이 문자열은 유료 판정 프롬프트에
    # `{actions}` 로 끼워지는데, 기록된 프롬프트 sha 는 템플릿만 덮고 끼워지는
    # 제목은 덮지 않는다. 지금 고치면 sha 를 움직이지 않은 채 모델이 본 것만
    # 바뀐다. 제목 교체는 판정 프롬프트 v0.2 와 같이 간다.
    "VERIFY_BY_KNOWN_CONTACT": ActionPolicy(
        1,
        "원래 알던 연락처로 본인에게 직접 확인하세요",
        "상대가 어느 기관인지 밝히지 않았다면 찾아갈 공식 대표번호가 없습니다. 가족·지인을 자칭하면 이전부터 쓰던 번호로 본인에게, 그 밖에는 카드 뒷면이나 기존 거래 창구처럼 이미 알고 있는 연락처로 확인하세요. 지금 대화 중인 창과 메시지에 적힌 번호는 확인 수단이 아닙니다.",
        ("police_1394",),
    ),
    "CONTACT_FINANCIAL_INSTITUTION": ActionPolicy(
        1,
        "거래 금융기관에 즉시 연락하세요",
        "계좌 접근이나 송금이 발생했다면 금융기관에 지급정지 등 가능한 조치를 문의해야 합니다.",
        ("fraud_refund_act", "police_ecrm_victim_help"),
    ),
    "CONTACT_1394": ActionPolicy(
        1,
        "보이스피싱 통합신고대응센터 1394에 상담하세요",
        "링크 클릭, 정보 제공, 악성 앱 설치 또는 송금 상황의 대응 절차를 안내받을 수 있습니다.",
        ("police_1394",),
    ),
    "CONTACT_112": ActionPolicy(
        1,
        "긴급한 피해 상황은 112에 신고하세요",
        "이미 계좌 접근, 자금 수취·재전달 또는 송금이 발생한 경우 신속한 신고가 필요합니다.",
        ("police_ecrm_victim_help",),
    ),
    "CONTACT_KISA_118": ActionPolicy(
        1,
        "KISA 118에 상담하세요",
        "스미싱, 악성 앱, 개인정보 침해 대응 안내를 받을 수 있습니다.",
        ("kisa_118", "kisa_smishing"),
    ),
    "PRESERVE_EVIDENCE": ActionPolicy(
        2,
        "대화와 거래 기록을 보존하세요",
        "문자, 메신저, 전화번호, 계좌와 이체 내역은 신고와 상담에 도움이 됩니다.",
        ("police_ecrm_victim_help",),
    ),
}

# v0.9. 확인 행동은 신호에 고정된 것이 아니라 **그 메시지에 확인할 창구가
# 있는지**를 따른다.
#
# "공식 대표번호로 확인하세요" 는 확인할 기관이 있을 때만 실행할 수 있는
# 조언이다. 창구가 없는 메시지에 같은 말을 하면 사용자는 존재하지 않는 창구를
# 찾다가 결국 **메시지에 적힌 번호로 건다.** 틀린 행동은 없는 행동보다 나쁘다.
#
# 창구가 생기는 자리는 기관 자칭만이 아니다. 자칭하지 않아도 대출·정책자금,
# 카드 발급·배송, 투자 권유는 취급 기관과 공식 조회 창구를 가리킨다 - 카드
# 뒷면의 번호, 정책자금 취급 창구, 제도권 금융회사 조회. 반면 재촉, 고립 요구,
# 인증정보·계좌권한 요구는 그 자체로는 아무 기관도 가리키지 않는다. **말하는
# 사람만 있고 창구가 없다.**
#
# 고립 요구를 공식 창구 쪽에 넣지 않은 것은 판단이 아니라 이미 기록된
# 결론이다. v0.7 `fh-523` "부모님께는 말씀드리지 않는 편이 좋습니다. 저와만
# 연락하세요" 는 공식 창구를 요구했는데, 거의 같은 문장인 v0.8 `fh-627`
# "부모님께는 말씀드리지 않는 게 좋겠습니다. 저와만 연락하세요" 는 아는 창구를
# 요구하고 v0.8 이 그것을 엔진 결함으로 적어 두었다. 뒤에 적힌 판단을 따른다.
VERIFY_CLAIMED_IDENTITY = "VERIFY_CLAIMED_IDENTITY"

# 이 신호들이 켜지면 찾아갈 공식 창구가 실제로 존재한다.
OFFICIAL_CHANNEL_SIGNALS: frozenset[str] = frozenset(
    {
        "authority_impersonation",
        "loan_policy_offer",
        "card_delivery_claim",
        "guaranteed_return_offer",
        "private_channel_invite",
    }
)

# 자칭 지인에게는 대표번호가 없다. 확인 수단은 이전부터 쓰던 연락처다.
KNOWN_CONTACT_SIGNALS: frozenset[str] = frozenset({"familiar_person_claim"})

# v1.1. **창구를 가리키는 것은 자칭만이 아니다.**
#
# 위 목록은 창구를 신호에서만 찾는다. 그런데 사기 문자의 절반은 자기가
# 누구인지 말하지 않고 **무슨 일이 일어났는지**만 말한다 - "결제 47만원
# 승인되었습니다", "종합소득세 환급금 조회 결과", "진행 중인 수사와 관련된
# 사안입니다". 이 문장들에는 기관명이 없지만 읽는 사람이 찾아갈 창구는
# 명확하다. 카드 뒷면 번호, 홈택스, 112 다. 사건 어휘가 창구를 가리킨다.
#
# 재 보니 동결 시점 미탐의 가장 큰 덩이가 여기였다 - `VERIFY_OFFICIAL_CHANNEL`
# 누락 15 건, 다음이 `VERIFY_BY_KNOWN_CONTACT` 7 건이다. 그리고 창구가 없다고
# 판단하면 폴백이 아는 연락처를 내므로, 미탐 하나가 **금지 행동 하나**를
# 함께 낸다(v1.1 `fh-901`·`fh-903`·`fh-904`·`fh-907` 이 그 모양이다).
#
# 넓히는 값은 정상 문장이 치른다. 그래서 두 겹으로 좁힌다.
#
# 첫째, **어휘를 사건으로 한정한다.** `확인`·`절차`·`신청` 같은 일반 명사는
# 넣지 않는다 - 그 말들은 창구를 가리키지 않고 그냥 흔하다. 남기는 것은
# 공식 창구가 실재하는 사건들뿐이다.
#
# 둘째, **이미 위험 신호가 켜진 메시지에서만 본다.** 이 어휘는 등급을 올리지
# 않고 행동만 고른다. 신호가 하나도 없는 메시지는 애초에 확인을 권하는
# 자리가 아니다 - "출금 승인 알림: 03/14 자동이체 통신요금"(`fh-977`)에
# 창구 안내가 붙으면 사용자는 곧 모든 안내를 무시하게 된다. 정상 문장이
# 값을 치르되 **아무 정상 문장이 아니라 바로 이 어형을 정상적으로 쓰는
# 문장**이어야 한다는 규칙을 여기서도 지킨다(`fh-976`~`fh-978`).
OFFICIAL_CHANNEL_CONTEXT_TERMS: tuple[str, ...] = (
    # 수사기관. 사건이 실재하면 112 와 관할서가 창구다.
    "수사",
    "조사",
    "압수",
    "영장",
    "고소",
    "입건",
    # 카드사·은행. 창구는 카드 뒷면과 대표번호다.
    "승인되었",
    "승인 되었",
    "결제 취소",
    "출금되었",
    "이상 거래",
    "부정 사용",
    # 세무·복지. 창구는 홈택스·정부24·복지로다.
    "환급",
    "지급 대상",
    "지원금",
    "보조금",
    "과태료",
    "체납",
    # 창구 이름이 문장에 직접 있는 경우. 사기는 그 이름을 **막으려고**
    # 부른다("정부24 는 점검 중이라", `fh-921`). 이름이 불린 이상 읽는
    # 사람은 그 창구로 갈 수 있다.
    "정부24",
    "홈택스",
    "복지로",
    "손택스",
)


def mentions_official_channel_event(text: str) -> bool:
    """이 문장이 공식 창구가 실재하는 사건을 말하고 있는가.

    등급에는 관여하지 않는다. 이 함수가 참이어도 위험 점수는 그대로이고,
    바뀌는 것은 **무엇으로 확인하라고 말하는가**뿐이다.
    """
    lowered = text.casefold()
    return any(term in lowered for term in OFFICIAL_CHANNEL_CONTEXT_TERMS)


def resolve_verification_actions(
    signal_codes: set[str], *, official_channel_context: bool = False
) -> tuple[str, ...]:
    """이 메시지에서 실제로 확인할 수 있는 창구만 낸다.

    둘 다 해당하면 둘 다 낸다. 한쪽을 이기게 하면 문장에 실제로 적힌 확인
    대상 하나를 빠뜨리게 된다. 이 갈래를 밟는 사례는 아직 어느 셋에도 없으므로
    **재서 고른 규칙이 아니라 설계 판단이다.**

    어느 쪽도 아니면 공식 창구가 아니라 아는 연락처로 보낸다. 틀렸을 때의 값이
    한쪽으로 크게 기울기 때문이다 - 창구가 없는데 공식 창구로 보내면 사용자는
    메시지 안의 번호로 돌아오지만, 창구가 있는데 아는 연락처로 보내면 카드
    뒷면이나 기존 거래 창구가 그 자리를 메운다.
    """
    resolved: list[str] = []
    if signal_codes & OFFICIAL_CHANNEL_SIGNALS or official_channel_context:
        resolved.append("VERIFY_OFFICIAL_CHANNEL")
    if signal_codes & KNOWN_CONTACT_SIGNALS:
        resolved.append("VERIFY_BY_KNOWN_CONTACT")
    return tuple(resolved) or ("VERIFY_BY_KNOWN_CONTACT",)


SIGNAL_ACTIONS: dict[str, tuple[str, ...]] = {
    "urgency_pressure": ("STOP_CONTACT", VERIFY_CLAIMED_IDENTITY),
    "authority_impersonation": ("STOP_CONTACT", VERIFY_CLAIMED_IDENTITY),
    "secrecy_isolation": ("STOP_CONTACT", VERIFY_CLAIMED_IDENTITY),
    "loan_policy_offer": ("STOP_CONTACT", VERIFY_CLAIMED_IDENTITY),
    # v0.9. 요구 신호에도 확인 수단을 붙인다. 넘기지 말라고만 하고 무엇으로
    # 확인하라는 말이 없으면, 사용자는 확인할 방법을 그 대화창 안에서 찾는다.
    "credential_request": (
        "DO_NOT_SHARE_ACCESS",
        "STOP_CONTACT",
        VERIFY_CLAIMED_IDENTITY,
    ),
    "account_access_request": (
        "DO_NOT_SHARE_ACCESS",
        "STOP_CONTACT",
        VERIFY_CLAIMED_IDENTITY,
    ),
    "app_install_request": ("DO_NOT_INSTALL", "CONTACT_KISA_118"),
    "remote_control_request": ("DO_NOT_INSTALL", "CONTACT_KISA_118"),
    "money_transfer_request": ("STOP_CONTACT", "CONTACT_1394"),
    "receive_and_forward_money": (
        "DO_NOT_FORWARD_MONEY",
        "CONTACT_FINANCIAL_INSTITUTION",
        "CONTACT_1394",
    ),
    "suspicious_link": ("DO_NOT_CLICK", "CONTACT_KISA_118"),
    "card_delivery_claim": (
        "DO_NOT_SHARE_ACCESS",
        VERIFY_CLAIMED_IDENTITY,
    ),
    # v0.4 는 여기만 다른 확인 수단을 박아 두었다. v0.9 에서 그 판단이 표
    # 전체로 올라갔으므로 이 줄도 자리표시자를 쓴다 - 지인 자칭은
    # `KNOWN_CONTACT_SIGNALS` 에 있으므로 결과는 그대로다.
    "familiar_person_claim": ("STOP_CONTACT", VERIFY_CLAIMED_IDENTITY),
    "guaranteed_return_offer": ("STOP_CONTACT", VERIFY_CLAIMED_IDENTITY),
    "private_channel_invite": ("STOP_CONTACT", VERIFY_CLAIMED_IDENTITY),
}

# 상태는 진행 순서가 아니라 서로 독립적인 사실이다. 각 상태에 직접 정책을 연결한다.
STATE_ACTIONS: dict[UserState, tuple[str, ...]] = {
    UserState.RECEIVED_ONLY: (),
    UserState.CLICKED_LINK: (
        "STOP_CONTACT",
        "DO_NOT_CLICK",
        "CONTACT_KISA_118",
        "PRESERVE_EVIDENCE",
    ),
    UserState.SHARED_PERSONAL_INFO: (
        "STOP_CONTACT",
        "CONTACT_KISA_118",
        "CONTACT_1394",
        "PRESERVE_EVIDENCE",
    ),
    UserState.SHARED_ACCOUNT_ACCESS: (
        "STOP_CONTACT",
        "CONTACT_FINANCIAL_INSTITUTION",
        "CONTACT_1394",
        "CONTACT_112",
        "PRESERVE_EVIDENCE",
    ),
    UserState.INSTALLED_APP: (
        "STOP_CONTACT",
        "CONTACT_KISA_118",
        "CONTACT_FINANCIAL_INSTITUTION",
        "CONTACT_1394",
        "PRESERVE_EVIDENCE",
    ),
    UserState.RECEIVED_UNKNOWN_MONEY: (
        "STOP_CONTACT",
        "DO_NOT_FORWARD_MONEY",
        "CONTACT_FINANCIAL_INSTITUTION",
        "CONTACT_1394",
        "CONTACT_112",
        "PRESERVE_EVIDENCE",
    ),
    UserState.TRANSFERRED_MONEY: (
        "STOP_CONTACT",
        "CONTACT_FINANCIAL_INSTITUTION",
        "CONTACT_1394",
        "CONTACT_112",
        "PRESERVE_EVIDENCE",
    ),
}

# v1.1. **이미 한 번 넘긴 사람이 가장 다시 넘기기 쉬운 사람이다.**
#
# 위 표에서 `CLICKED_LINK` 는 `DO_NOT_CLICK` 을, `RECEIVED_UNKNOWN_MONEY` 는
# `DO_NOT_FORWARD_MONEY` 를 낸다. 그런데 계좌 권한을 넘겼거나 앱을 깔았거나
# 이미 송금한 상태에는 예방 행동이 하나도 없다. 사기는 한 번으로 끝나지
# 않고 같은 요구를 다시 하는데, 두 번째 요구를 막는 말이 그 사람에게만
# 빠져 있었다. held-out v0.2 `fh-021` 이 여섯 회차 전에 이 자리를 지나갔고
# 그때는 상태를 재는 사례가 적어 묻혔다.
#
# **상태가 신호를 대신하지는 않는다.** 이 행동들은 위험 신호가 하나라도
# 켜진 메시지에서만 낸다. 계좌를 알려 주는 일도 앱을 까는 일도 송금하는
# 일도 대부분은 정상이고, 그 정상 문장이 값을 치르는 자리를 v1.1 이
# 따로 만들어 두었다 - "알려 주신 급여이체 계좌로 4월분부터 지급됩니다"
# (`fh-974`), "이체가 정상 처리되었습니다"(`fh-975`), 회사 보안 앱 설치
# 안내(`fh-969`). 상태만으로 켜면 이 문장들이 전부 예방 경고를 받는다.
#
# 값은 반대쪽에서도 치른다. 신호가 하나도 켜지지 않는 사기 - `fh-908`·
# `fh-909`·`fh-913`·`fh-923`·`fh-925`·`fh-926` - 는 이 수정으로도 예방
# 행동을 받지 못한다. 그 여섯 건이 못 받는 이유는 상태 표가 아니라
# **어휘가 비어서**이고, 그 구멍은 각자의 신호에서 메워야 한다.
STATE_PREVENTION_ACTIONS: dict[UserState, tuple[str, ...]] = {
    UserState.SHARED_PERSONAL_INFO: ("DO_NOT_SHARE_ACCESS",),
    UserState.SHARED_ACCOUNT_ACCESS: ("DO_NOT_SHARE_ACCESS",),
    UserState.INSTALLED_APP: ("DO_NOT_INSTALL",),
    UserState.TRANSFERRED_MONEY: ("DO_NOT_FORWARD_MONEY",),
}

STATE_MINIMUM_RISK: dict[UserState, str] = {
    UserState.RECEIVED_ONLY: "low",
    UserState.CLICKED_LINK: "medium",
    UserState.SHARED_PERSONAL_INFO: "medium",
    UserState.SHARED_ACCOUNT_ACCESS: "high",
    UserState.INSTALLED_APP: "high",
    UserState.RECEIVED_UNKNOWN_MONEY: "high",
    UserState.TRANSFERRED_MONEY: "high",
}

RISK_RANK = {"low": 0, "medium": 1, "high": 2}

SIGNAL_MINIMUM_RISK: dict[str, str] = {
    "authority_impersonation": "medium",
    "secrecy_isolation": "medium",
    "loan_policy_offer": "medium",
    "credential_request": "medium",
    "account_access_request": "medium",
    "app_install_request": "medium",
    "remote_control_request": "high",
    "money_transfer_request": "medium",
    "receive_and_forward_money": "high",
    "suspicious_link": "medium",
    "card_delivery_claim": "medium",
    "familiar_person_claim": "medium",
    "guaranteed_return_offer": "medium",
    "private_channel_invite": "medium",
}

HIGH_RISK_SIGNAL_COMBINATIONS: tuple[frozenset[str], ...] = (
    frozenset({"authority_impersonation", "money_transfer_request"}),
    frozenset({"loan_policy_offer", "account_access_request"}),
    frozenset({"app_install_request", "remote_control_request"}),
    # v0.4. **새 신호가 들어간 조합만 추가한다.** 기존 신호끼리의 조합을 같이
    # 손대면 v0.3 held-out 의 정책 수치가 무엇 때문에 움직였는지 갈라낼 수
    # 없어진다. 기존 조합의 공백(`docs/10`)은 별도 작업으로 남긴다.
    frozenset({"familiar_person_claim", "money_transfer_request"}),
    frozenset({"familiar_person_claim", "credential_request"}),
    frozenset({"familiar_person_claim", "account_access_request"}),
    frozenset({"guaranteed_return_offer", "money_transfer_request"}),
    frozenset({"private_channel_invite", "money_transfer_request"}),
    # v0.7. **기관은 자칭과 같은 메시지에서 넘겨 달라고 하지 않는다.**
    #
    # 자칭도 medium 을 세우고 민감 요구도 medium 을 세우는데, 둘이 함께
    # 켜져도 medium 에서 멈춘다 - `max` 는 두 medium 을 high 로 만들지
    # 않는다. 그래서 소진된 held-out 다섯 회차에 이 모양의 하한 미달이
    # 15건 남아 있었다(v0.2 `fh-003`·`fh-005`·`fh-006`·`fh-008`·`fh-012`·
    # `fh-014`, v0.3 `fh-102`~`fh-105`·`fh-110`, v0.4 `fh-237`,
    # v0.6 `fh-415`·`fh-416`·`fh-418`~`fh-421`).
    #
    # 사례에서 짝을 세지 않았다. 짝은 `SENSITIVE_REQUEST_SIGNALS` 를 그대로
    # 따른다 - 그 목록이 이미 '기관이 문자로 시키지 않는 요구'의 정의다.
    # 어휘로 뽑은 링크도 같은 자리에 둔다. 진짜 기관은 단축 URL 로 보내지
    # 않으므로 그것 자체가 요구다(`_detect_by_rules` 가 이미 그렇게 쓴다).
    frozenset({"authority_impersonation", "credential_request"}),
    frozenset({"authority_impersonation", "account_access_request"}),
    frozenset({"authority_impersonation", "app_install_request"}),
    frozenset({"authority_impersonation", "remote_control_request"}),
    frozenset({"authority_impersonation", "receive_and_forward_money"}),
    frozenset({"authority_impersonation", "card_delivery_claim"}),
    frozenset({"authority_impersonation", "suspicious_link"}),
    # 고립 요구도 기관이 하지 않는 요구다. v0.7 의 어휘 정리로 이 신호는
    # 전칭 금지와 창구 봉쇄만 남았고, 둘 다 정상 안내가 쓸 일이 없다.
    # v0.2 `fh-008`(수사 보안상 통화를 끊지 말고 가족에게도 비밀로 하라).
    frozenset({"authority_impersonation", "secrecy_isolation"}),
    # 자칭 조합과 같은 모양이 대출에도 하나 비어 있었다. `account_access_request`
    # 짝만 있고 선입금 짝이 없다 - 대출 빙자 보증료 선입금은 이 목록이
    # 처음부터 노린 것인데 v0.2 `fh-016`·`fh-019`, v0.3 `fh-139` 가 그대로
    # 지나갔다.
    frozenset({"loan_policy_offer", "money_transfer_request"}),
    # v0.9. **불이익을 예고해 놓고 접근수단을 달라고 하면 자칭이 없어도
    # high 다.** 재촉은 점수만 12 올리고 등급 하한을 세우지 않으므로, 요구가
    # 세운 medium 하나만 남아 등급이 거기서 멈춘다 - 정지·압류·회수를
    # 앞세워 인증번호나 통장을 받아 내는 문장이 이 모양이고, 그것이 요구를
    # 거절하기 가장 어렵게 만드는 조합이다.
    #
    # 위 조합들과 달리 이 짝에는 자칭이 없다. 그래서 값은 천장에서 치러진다:
    # 기한이 급한 정상 안내가 통장·카드를 입에 올리기만 해도 high 로 올라가면
    # 이 수정은 손해다. v0.9 정상 31건이 전부 천장을 선언하고 있다.
    frozenset({"urgency_pressure", "credential_request"}),
    frozenset({"urgency_pressure", "account_access_request"}),
    # v1.0. 대출 짝의 나머지 한 칸이다. `account_access_request` 와
    # `money_transfer_request` 는 앞선 회차가 채웠는데 인증정보 짝만
    # 비어 있었다 - "서민 대환 대출 한도 조회를 도와드립니다. 공동인증서와
    # 비밀번호를 알려 주세요"(`fh-821`). 한도 조회에 비밀번호가 필요한
    # 대출 창구는 없다.
    frozenset({"loan_policy_offer", "credential_request"}),
)

# 사용자에게 보이는 등급을 직접 결정하는 임계값이다.
# tests/test_fraud_risk_level.py 가 경계값(34/35/69/70)을 고정한다.
HIGH_RISK_SCORE_THRESHOLD = 70
MEDIUM_RISK_SCORE_THRESHOLD = 35


def determine_risk_level(
    score: int, signals: list[RiskSignal], state: UserState
) -> str:
    """점수·신호·사용자 상태 중 가장 높은 위험 수준을 채택한다.

    세 근거는 서로 독립적이며 어느 하나도 다른 하나를 낮추지 못한다.
    """
    if score >= HIGH_RISK_SCORE_THRESHOLD:
        signal_level = "high"
    elif score >= MEDIUM_RISK_SCORE_THRESHOLD:
        signal_level = "medium"
    else:
        signal_level = "low"
    signal_codes = {signal.code for signal in signals}
    for code in signal_codes:
        minimum = SIGNAL_MINIMUM_RISK.get(code, "low")
        if RISK_RANK[minimum] > RISK_RANK[signal_level]:
            signal_level = minimum
    if any(required <= signal_codes for required in HIGH_RISK_SIGNAL_COMBINATIONS):
        signal_level = "high"
    state_level = STATE_MINIMUM_RISK[state]
    return max((signal_level, state_level), key=RISK_RANK.__getitem__)


def score_floor_for_level(level: str) -> int:
    """그 등급이 되려면 점수가 최소 얼마여야 하는가.

    v0.8. `risk_score` 와 `risk_level` 이 서로 다른 것을 재고 있었다.
    점수는 `LEGACY_RULES` 의 가중치만 더하고, 등급은 canonical 신호와
    사용자 상태까지 본다. 그래서 **`risk_level: "high"` 인데
    `risk_score: 0` 인 응답이 나간다** - 화면에 둘 다 보이면 서로를
    부정하고, 읽는 사람은 어느 쪽을 믿어야 할지 알 수 없다.

    등급을 점수에서 다시 계산하지 않는다. 그 방향은 canonical 신호와
    상태 하한을 버리는 것이고, 이 프로젝트가 여섯 회차에 걸쳐 쌓은
    판단이 전부 legacy 가중치 표로 되돌아간다. 대신 **점수를 등급이
    함의하는 띠까지 올린다.** 점수는 등급의 근거가 아니라 등급을
    거스르지 않는 표시값이 된다.
    """
    if level == "high":
        return HIGH_RISK_SCORE_THRESHOLD
    if level == "medium":
        return MEDIUM_RISK_SCORE_THRESHOLD
    return 0


def select_actions(
    signals: list[RiskSignal], state: UserState, text: str = ""
) -> list[Action]:
    signal_codes = {signal.code for signal in signals}
    action_codes: set[str] = set(STATE_ACTIONS[state])
    for signal in signals:
        action_codes.update(SIGNAL_ACTIONS.get(signal.code, ()))

    # 상태가 내는 예방 행동과 사건 어휘가 가리키는 창구는 **위험 신호가
    # 켜진 메시지에서만** 본다. 둘 다 등급을 올리지 않고 행동만 고른다.
    if signals:
        action_codes.update(STATE_PREVENTION_ACTIONS.get(state, ()))
    official_channel_context = bool(signals) and mentions_official_channel_event(text)

    # 자리표시자는 정책표에 없다. 여기서 풀지 않으면 아래 조회가 터진다 -
    # 조용히 빠지는 것보다 낫다. 정책표에 없다는 것은 판정 프롬프트에도
    # 실리지 않는다는 뜻이기도 하다.
    if VERIFY_CLAIMED_IDENTITY in action_codes:
        action_codes.discard(VERIFY_CLAIMED_IDENTITY)
        action_codes.update(
            resolve_verification_actions(
                signal_codes, official_channel_context=official_channel_context
            )
        )
    elif official_channel_context:
        # 자리표시자를 다는 신호가 하나도 없는데 창구는 있는 경우다. 링크
        # 하나만 켜진 스미싱이 이 모양이고(`fh-905`·`fh-921`), 그때 사용자가
        # 받는 말은 "누르지 마세요"뿐이다. **무엇으로 확인하라는 말이 없으면
        # 사용자는 확인할 방법을 그 대화창 안에서 찾는다.**
        action_codes.add("VERIFY_OFFICIAL_CHANNEL")

    ordered_codes = sorted(
        action_codes,
        key=lambda code: (ACTION_POLICIES[code].priority, code),
    )
    return [
        Action(
            code=code,
            priority=ACTION_POLICIES[code].priority,
            title=ACTION_POLICIES[code].title,
            reason=ACTION_POLICIES[code].reason,
            source_ids=list(ACTION_POLICIES[code].source_ids),
        )
        for code in ordered_codes
    ]
