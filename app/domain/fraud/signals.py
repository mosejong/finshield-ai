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
            "정부 융자",
        ),
        30,
        "대출·정책금융 제안",
    ),
    SignalRule(
        "credential_request",
        ("인증번호", "비밀번호", "otp", "보안카드 번호", "일회용 승인코드"),
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
        (
            "앱 설치",
            "어플 설치",
            "apk",
            "프로그램 설치",
            "실행파일",
            # v0.2 추가. fg-047("보안 모듈을 내려받아 실행")이 여기서 빠졌다.
            # 기존 어휘가 전부 "설치"라는 단어에 걸려 있어서, 같은 요구를
            # "내려받다"로 쓰면 통과했다. 잡는 것은 **받아서 실행하라는 지시**이지
            # 대상 파일의 이름이 아니다 - "보안 모듈" 같은 명사를 넣으면 은행
            # 정상 안내까지 걸린다.
            "내려받",
            "다운로드",
            "설치 파일",
            "설치 링크",
        ),
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
        (
            "송금해",
            "입금해",
            "돈을 보내",
            "안전계좌",
            "보호계좌",
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
    ),
    SignalRule(
        "receive_and_forward_money",
        (
            "입금받고",
            "재송금",
            "다시 보내",
            "전달해",
            "돈을 받아서 보내",
            "수령한 금액",
            "제3자 계좌로 옮기",
        ),
        70,
        "자금 수취·재전달 요구",
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

# 기관명·상품명만으로 켜지는 신호는 예방 안내문에서도 그대로 켜진다.
# 요구가 하나도 없는 안내문까지 경고로 올리면 사용자는 경고를 무시하게 된다.
ADVISORY_SUPPRESSIBLE_CODES = frozenset(
    {"authority_impersonation", "loan_policy_offer"}
)


def _is_official_verification_notice(normalized: str) -> bool:
    return any(
        phrase in normalized for phrase in OFFICIAL_VERIFICATION_PHRASES
    ) and not any(phrase in normalized for phrase in READER_DEMAND_PHRASES)


def _detect_by_rules(text: str, rules: tuple[SignalRule, ...]) -> list[RiskSignal]:
    normalized = text.casefold()
    detected = []
    for rule in rules:
        if (
            any(keyword.casefold() in normalized for keyword in rule.keywords)
            and not _safe_context_suppresses(rule.code, normalized)
        ):
            detected.append(
                RiskSignal(code=rule.code, label=rule.label, weight=rule.weight)
            )
    return detected


def _safe_context_suppresses(code: str, normalized: str) -> bool:
    """명시적인 예방·정상 이용 문맥만 억제한다.

    일반 negation 해석기가 아니다. 공격 지시가 함께 있는 혼합 문장은 억제하지
    않도록 좁은 문구 조합만 사용한다.
    """
    if code in ADVISORY_SUPPRESSIBLE_CODES and _is_official_verification_notice(
        normalized
    ):
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
