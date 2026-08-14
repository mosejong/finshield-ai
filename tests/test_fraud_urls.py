"""링크 판정을 문자열 형태만으로 검증한다.

이전에는 스킴이 있는 URL 만 검사를 통과해서 `http://1.2.3.4/login` 은 잡히고
`1.2.3.4/login` 은 그대로 빠져나갔다. 스미싱 문자는 후자 형태로 온다.

여기서 다루는 URL 은 전부 문자열이다. 서버는 이 주소로 요청하지 않는다.
"""

import pytest
from fastapi.testclient import TestClient

from app.domain.fraud.signals import (
    _is_lexically_suspicious_url,
    contains_url,
    detect_canonical_signals,
)
from app.main import app


client = TestClient(app)


SUSPICIOUS = [
    "http://example.com/login",  # 평문 http
    "https://1.2.3.4/login",
    "1.2.3.4/login",  # 스킴 없는 IP
    "192.168.0.1/verify",
    "https://xn--80ak6aa92e.com/x",
    "xn--80ak6aa92e.com/x",  # 스킴 없는 퓨니코드
    "https://bit.ly/abc",
    "bit.ly/abc",
    "tinyurl.com/xyz",
    "https://localhost/admin",
    "localhost/admin",
    "https://user:pw@example.com/",
    # 호스트가 없는 스킴
    "javascript:alert(1)",
    "data:text/html;base64,PHNjcmlwdD4=",
    # `scheme://` 형태지만 http/https 가 아닌 것. 위 두 개와 다른 분기를 탄다.
    "ftp://example.com/file",
    "file://example.com/share",
    "intent://example.com/#Intent;scheme=http;end",
]

NOT_SUSPICIOUS = [
    "https://www.kisa.or.kr/118/",
    "www.police.go.kr/index.do",
    "https://ecrm.police.go.kr/minwon/main",
    "example.com/login",  # 평범한 도메인은 형태만으로 위험하지 않다
    "",
    "   ",
]


@pytest.mark.parametrize("raw_url", SUSPICIOUS)
def test_suspicious_urls_are_detected(raw_url: str) -> None:
    assert _is_lexically_suspicious_url(raw_url) is True


@pytest.mark.parametrize("raw_url", NOT_SUSPICIOUS)
def test_ordinary_urls_are_not_flagged(raw_url: str) -> None:
    assert _is_lexically_suspicious_url(raw_url) is False


@pytest.mark.parametrize(
    "raw_url",
    ["1.2.3.4/login", "https://1.2.3.4/login", "http://1.2.3.4/login"],
)
def test_scheme_does_not_change_the_verdict(raw_url: str) -> None:
    """같은 호스트라면 스킴 유무로 판정이 갈리지 않는다."""
    assert _is_lexically_suspicious_url(raw_url) is True


def test_bare_ip_in_text_produces_signal() -> None:
    signals = detect_canonical_signals("확인해주세요 1.2.3.4/login")
    assert "suspicious_link" in {signal.code for signal in signals}


def test_bare_shortener_in_text_produces_signal() -> None:
    signals = detect_canonical_signals("여기로 들어오세요 bit.ly/abc123")
    assert "suspicious_link" in {signal.code for signal in signals}


@pytest.mark.parametrize(
    "text",
    [
        "오늘 점심 뭐 먹을까",
        "3.5/5점 정도였어",
        "report.pdf 파일 보냈어",
        "2026.08.14/기록 확인",
    ],
)
def test_ordinary_text_produces_no_link_signal(text: str) -> None:
    signals = detect_canonical_signals(text)
    assert "suspicious_link" not in {signal.code for signal in signals}


def test_contains_url_sees_bare_links() -> None:
    assert contains_url("여기 1.2.3.4/login 접속") is True
    assert contains_url("오늘 점심 뭐 먹을까") is False


def test_blank_supplied_url_is_not_a_url() -> None:
    assert contains_url("안녕하세요", "") is False
    assert contains_url("안녕하세요", "   ") is False


@pytest.mark.parametrize(
    ("supplied_url", "expected_signal"),
    [("http://1.2.3.4/login", True), ("1.2.3.4/login", True), ("", False)],
)
def test_api_url_field_matches_domain_verdict(
    supplied_url: str, expected_signal: bool
) -> None:
    """API 경계에서도 같은 판정이 나오는지 확인한다."""
    response = client.post(
        "/api/v1/analyze",
        json={"text": "확인 부탁드립니다", "state": "received_only", "url": supplied_url},
    )
    assert response.status_code == 200
    codes = {signal["code"] for signal in response.json()["signals"]}
    assert ("suspicious_link" in codes) is expected_signal
