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
        ),
        25,
        "공식 기관 사칭 가능성",
    ),
    SignalRule(
        "secrecy_isolation",
        ("아무에게도 말하지", "비밀로", "혼자 처리", "보안 유지", "통화를 끊지"),
        18,
        "주변 확인을 막는 비밀 유지 요구",
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
        ),
        30,
        "대출·정책금융 제안",
    ),
    SignalRule(
        "credential_request",
        ("인증번호", "비밀번호", "otp", "보안카드 번호"),
        40,
        "인증정보 요구",
    ),
    SignalRule(
        "account_access_request",
        (
            "체크카드",
            "통장",
            "계좌를 빌려",
            "계좌 대여",
            "카드를 보내",
            "카드 전달",
        ),
        40,
        "계좌·접근수단 요구",
    ),
    SignalRule(
        "app_install_request",
        ("앱 설치", "어플 설치", "apk", "프로그램 설치"),
        35,
        "앱 설치 요구",
    ),
    SignalRule(
        "remote_control_request",
        ("원격제어", "원격 접속", "화면 공유", "팀뷰어", "애니데스크"),
        40,
        "원격제어·화면공유 요구",
    ),
    SignalRule(
        "money_transfer_request",
        ("송금해", "입금해", "돈을 보내", "안전계좌", "보호계좌"),
        35,
        "송금 요구",
    ),
    SignalRule(
        "receive_and_forward_money",
        ("입금받고", "재송금", "다시 보내", "전달해", "돈을 받아서 보내"),
        70,
        "자금 수취·재전달 요구",
    ),
    SignalRule(
        "card_delivery_claim",
        ("카드 배송", "카드가 발급", "신청한 카드", "카드 배달", "배송 기사"),
        35,
        "신청하지 않은 카드 배송·발급 주장",
    ),
)

LEGACY_RULES: tuple[SignalRule, ...] = (
    SignalRule("urgency", ("오늘까지", "즉시", "긴급", "지금 바로"), 12, "긴급한 행동 요구"),
    SignalRule("credential", ("인증번호", "비밀번호", "otp"), 25, "인증정보 요구"),
    SignalRule(
        "account_access",
        ("체크카드", "통장", "계좌를 빌려", "계좌 대여"),
        35,
        "계좌·접근수단 요구",
    ),
    SignalRule(
        "remote_app",
        ("원격제어", "앱 설치", "apk"),
        30,
        "앱 설치·원격접속 요구",
    ),
    SignalRule(
        "money_mule",
        ("입금받고", "재송금", "다시 보내", "전달해"),
        35,
        "자금 수취·재전달 요구",
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


def _detect_by_rules(text: str, rules: tuple[SignalRule, ...]) -> list[RiskSignal]:
    normalized = text.casefold()
    detected = []
    for rule in rules:
        if any(keyword.casefold() in normalized for keyword in rule.keywords):
            detected.append(
                RiskSignal(code=rule.code, label=rule.label, weight=rule.weight)
            )
    return detected


def _is_lexically_suspicious_url(raw_url: str) -> bool:
    candidate = raw_url.strip().rstrip(".,;:!?)]}")
    normalized_candidate = candidate.casefold()
    lacks_scheme = not normalized_candidate.startswith(("http://", "https://"))
    known_host_prefix = normalized_candidate.startswith("www.") or any(
        normalized_candidate == shortener
        or normalized_candidate.startswith(f"{shortener}/")
        for shortener in KNOWN_SHORTENERS
    )
    parse_target = (
        f"https://{candidate}" if lacks_scheme and known_host_prefix else candidate
    )
    try:
        parsed = urlsplit(parse_target)
        hostname = (parsed.hostname or "").casefold().rstrip(".")
    except ValueError:
        return True

    if parsed.scheme.casefold() == "http":
        return True
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


def contains_url(text: str, supplied_url: str | None = None) -> bool:
    return bool(supplied_url or URL_CANDIDATE_PATTERN.search(text))


def detect_legacy_signals(text: str) -> list[RiskSignal]:
    return _detect_by_rules(text, LEGACY_RULES)


def detect_canonical_signals(
    text: str, supplied_url: str | None = None
) -> list[RiskSignal]:
    detected = _detect_by_rules(text, SIGNAL_RULES)
    url_candidates = [match.group(0) for match in URL_CANDIDATE_PATTERN.finditer(text)]
    if supplied_url:
        url_candidates.append(supplied_url)

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
