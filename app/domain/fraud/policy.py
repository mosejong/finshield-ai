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

SIGNAL_ACTIONS: dict[str, tuple[str, ...]] = {
    "urgency_pressure": ("STOP_CONTACT", "VERIFY_OFFICIAL_CHANNEL"),
    "authority_impersonation": ("STOP_CONTACT", "VERIFY_OFFICIAL_CHANNEL"),
    "secrecy_isolation": ("STOP_CONTACT", "VERIFY_OFFICIAL_CHANNEL"),
    "loan_policy_offer": ("STOP_CONTACT", "VERIFY_OFFICIAL_CHANNEL"),
    "credential_request": ("DO_NOT_SHARE_ACCESS", "STOP_CONTACT"),
    "account_access_request": ("DO_NOT_SHARE_ACCESS", "STOP_CONTACT"),
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
        "VERIFY_OFFICIAL_CHANNEL",
    ),
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
}

HIGH_RISK_SIGNAL_COMBINATIONS: tuple[frozenset[str], ...] = (
    frozenset({"authority_impersonation", "money_transfer_request"}),
    frozenset({"loan_policy_offer", "account_access_request"}),
    frozenset({"app_install_request", "remote_control_request"}),
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


def select_actions(signals: list[RiskSignal], state: UserState) -> list[Action]:
    action_codes: set[str] = set(STATE_ACTIONS[state])
    for signal in signals:
        action_codes.update(SIGNAL_ACTIONS.get(signal.code, ()))

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
