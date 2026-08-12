from app.domain.fraud.signals import baseline_score, detect_legacy_signals
from app.schemas.analysis import RiskSignal


def analyze_rules(text: str) -> tuple[int, list[RiskSignal]]:
    """이전 호출부를 위한 호환 함수. 신규 API는 fraud_analysis 서비스를 사용한다."""
    signals = detect_legacy_signals(text)
    return baseline_score(signals), signals


def risk_level(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 35:
        return "medium"
    return "low"
