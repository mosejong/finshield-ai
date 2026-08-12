from app.schemas.analysis import RiskSignal

# Temporary transparent baseline.
# Replace weights only after evidence/evaluation is documented.
RULES: tuple[tuple[str, tuple[str, ...], int, str], ...] = (
    ("urgency", ("오늘까지", "즉시", "긴급", "지금 바로"), 12, "긴급한 행동 요구"),
    ("credential", ("인증번호", "비밀번호", "otp"), 25, "인증정보 요구"),
    ("account_access", ("체크카드", "통장", "계좌를 빌려", "계좌 대여"), 35, "계좌·접근수단 요구"),
    ("remote_app", ("원격제어", "앱 설치", "apk"), 30, "앱 설치·원격접속 요구"),
    ("money_mule", ("입금받고", "재송금", "다시 보내", "전달해"), 35, "자금 수취·재전달 요구"),
)


def analyze_rules(text: str) -> tuple[int, list[RiskSignal]]:
    normalized = text.lower()
    signals: list[RiskSignal] = []

    for code, keywords, weight, label in RULES:
        if any(keyword in normalized for keyword in keywords):
            signals.append(RiskSignal(code=code, label=label, weight=weight))

    score = min(sum(signal.weight for signal in signals), 100)
    return score, signals


def risk_level(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 35:
        return "medium"
    return "low"
