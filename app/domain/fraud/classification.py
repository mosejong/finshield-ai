from app.schemas.analysis import RiskSignal


FRAUD_TYPE_ORDER: tuple[str, ...] = (
    "authority_impersonation",
    "loan_policy_impersonation",
    "advance_fee_demand",
    "account_access_request",
    "money_mule_transfer",
    "smishing_malware",
    "card_delivery_impersonation",
)


def classify_fraud_types(signals: list[RiskSignal]) -> list[str]:
    codes = {signal.code for signal in signals}
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

    return [fraud_type for fraud_type in FRAUD_TYPE_ORDER if fraud_type in matched]
