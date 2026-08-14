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
