from app.schemas.analysis import RiskSignal


FRAUD_TYPE_ORDER: tuple[str, ...] = (
    "authority_impersonation",
    "acquaintance_impersonation",
    "loan_policy_impersonation",
    "investment_scheme",
    "advance_fee_demand",
    "account_access_request",
    "money_mule_transfer",
    "smishing_malware",
    "card_delivery_impersonation",
)


# "먼저 보내면 돌려준다·처리해 준다" 구조의 표지다. 송금 요구만으로는 유형을
# 정할 수 없다 - 검찰 사칭이 안전계좌로 보내라는 것도 송금 요구이고, 그쪽은
# 대가를 약속하지 않는다. 선입금 유형을 가르는 것은 **대가의 약속**이다.
ADVANCE_FEE_MARKERS: tuple[str, ...] = (
    "먼저",
    "선입금",
    "선결제",
    "선납",
    "선금",
    "수수료",
    "보증료",
    "보증보험료",
    "예치금",
    "제세공과금",
    "통관비",
    "복구비",
    "작업비",
    "대납",
)


def classify_fraud_types(signals: list[RiskSignal], text: str = "") -> list[str]:
    """신호를 사용자에게 보일 사기 유형으로 옮긴다.

    `text` 를 받는 유일한 이유는 선입금 유형이다. 그 구분은 신호가 아니라
    **낱말**에 있고("먼저", "수수료"), 이것을 공개 신호로 승격시키면 어휘 하나가
    API 계약에 박힌다. 판단은 여전히 신호가 하고, 낱말은 유형을 좁히기만 한다.
    """
    codes = {signal.code for signal in signals}
    normalized = text.casefold()
    matched: set[str] = set()

    if "authority_impersonation" in codes:
        matched.add("authority_impersonation")
    if "loan_policy_offer" in codes:
        matched.add("loan_policy_impersonation")
    if codes & {"credential_request", "account_access_request"}:
        matched.add("account_access_request")
    if "receive_and_forward_money" in codes:
        matched.add("money_mule_transfer")
    if codes & {
        "suspicious_link",
        "app_install_request",
        "remote_control_request",
    }:
        matched.add("smishing_malware")
    if "card_delivery_claim" in codes:
        matched.add("card_delivery_impersonation")
    # v0.3. `money_transfer_request` 는 등급을 올리면서도 유형 표에 자리가 없었다.
    # 그래서 held-out v0.2 에 등급이 high 인데 유형이 빈 사례가 남았다.
    if "money_transfer_request" in codes and any(
        marker in normalized for marker in ADVANCE_FEE_MARKERS
    ):
        matched.add("advance_fee_demand")

    return [fraud_type for fraud_type in FRAUD_TYPE_ORDER if fraud_type in matched]
