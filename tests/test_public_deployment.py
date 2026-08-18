"""공개 배포 판정 기준 자체를 고정한다.

P0-3 에서 배운 것을 그대로 적용했다. 검사가 돌고 있다는 사실은 검사가 실패할
수 있다는 뜻이 아니다. 여기서는 **통과해서는 안 되는 입력이 실제로 떨어지는지**
를 항목마다 하나씩 확인한다.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.public_deployment import (
    CERTIFICATE_FAIL_DAYS,
    CERTIFICATE_WARN_DAYS,
    MINIMUM_HSTS_MAX_AGE,
    evaluate_certificate,
    evaluate_https_redirect,
    evaluate_hsts,
    evaluate_internal_port,
    evaluate_security_headers,
    evaluate_share_target,
    summarize,
)

DOMAIN = "finshield.example.com"
NOW = datetime(2026, 8, 17, tzinfo=timezone.utc)

VALID_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; base-uri 'self'; object-src 'none'; "
        "frame-ancestors 'none'; form-action 'self'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


def failed(results) -> list[str]:
    return [result.name for result in results if not result.passed]


class TestHttpsRedirect:
    def test_permanent_redirect_to_the_same_domain_passes(self):
        result = evaluate_https_redirect(308, f"https://{DOMAIN}/", DOMAIN)
        assert result.passed

    def test_serving_plaintext_directly_fails(self):
        # HTTPS 가 붙어 있어도 평문 요청이 그대로 처리되면 쿠키가 평문으로 오간다.
        assert not evaluate_https_redirect(200, None, DOMAIN).passed

    def test_redirect_without_location_fails(self):
        assert not evaluate_https_redirect(301, None, DOMAIN).passed

    def test_redirect_to_plaintext_fails(self):
        assert not evaluate_https_redirect(301, f"http://{DOMAIN}/", DOMAIN).passed

    def test_redirect_to_another_host_fails(self):
        assert not evaluate_https_redirect(301, "https://evil.example.com/", DOMAIN).passed


class TestHsts:
    def test_one_year_with_subdomains_passes(self):
        assert evaluate_hsts(f"max-age={MINIMUM_HSTS_MAX_AGE}; includeSubDomains").passed

    def test_missing_header_fails(self):
        assert not evaluate_hsts(None).passed

    def test_max_age_zero_fails(self):
        # 헤더는 있지만 HSTS 를 끄는 값이다. 존재만 보는 검사가 놓치는 경우.
        assert not evaluate_hsts("max-age=0; includeSubDomains").passed

    def test_short_max_age_fails(self):
        assert not evaluate_hsts("max-age=600; includeSubDomains").passed

    def test_missing_include_subdomains_fails(self):
        assert not evaluate_hsts(f"max-age={MINIMUM_HSTS_MAX_AGE}").passed

    def test_unparsable_max_age_fails(self):
        assert not evaluate_hsts("max-age=forever; includeSubDomains").passed


class TestSecurityHeaders:
    def test_documented_contract_passes(self):
        assert failed(evaluate_security_headers(VALID_HEADERS)) == []

    def test_case_insensitive_header_names(self):
        lowered = {name.lower(): value for name, value in VALID_HEADERS.items()}
        assert failed(evaluate_security_headers(lowered)) == []

    def test_weakened_frame_options_fails(self):
        headers = {**VALID_HEADERS, "X-Frame-Options": "SAMEORIGIN"}
        assert "header:x-frame-options" in failed(evaluate_security_headers(headers))

    def test_csp_without_frame_ancestors_fails(self):
        headers = {**VALID_HEADERS, "Content-Security-Policy": "default-src 'self'; object-src 'none'"}
        assert "header:content-security-policy" in failed(evaluate_security_headers(headers))

    def test_missing_csp_fails(self):
        headers = {name: value for name, value in VALID_HEADERS.items() if name != "Content-Security-Policy"}
        assert "header:content-security-policy" in failed(evaluate_security_headers(headers))

    @pytest.mark.parametrize("leaky", ["Server", "X-Powered-By"])
    def test_version_disclosure_fails(self, leaky: str):
        headers = {**VALID_HEADERS, leaky: "Caddy/2.10.2"}
        assert f"header:{leaky.lower()}" in failed(evaluate_security_headers(headers))


class TestCertificate:
    def fresh(self, days: int, **overrides):
        return evaluate_certificate(
            NOW + timedelta(days=days),
            NOW,
            **{"hostname_verified": True, "protocol": "TLSv1.3", **overrides},
        )

    def test_freshly_renewed_certificate_passes(self):
        assert failed(self.fresh(89)) == []

    def test_expired_certificate_fails(self):
        assert "certificate_expiry" in failed(self.fresh(-1))

    def test_renewal_silently_stopped_fails_before_expiry(self):
        # 이 검사의 존재 이유. 만료 21일 전이면 갱신이 이미 9일째 실패 중이다.
        assert "certificate_expiry" in failed(self.fresh(CERTIFICATE_WARN_DAYS - 1))

    def test_boundary_between_warning_and_healthy(self):
        assert failed(self.fresh(CERTIFICATE_WARN_DAYS)) == []
        assert "certificate_expiry" in failed(self.fresh(CERTIFICATE_WARN_DAYS - 1))

    def test_fail_threshold_is_below_warn_threshold(self):
        assert CERTIFICATE_FAIL_DAYS < CERTIFICATE_WARN_DAYS

    def test_untrusted_chain_fails(self):
        assert "certificate_trusted" in failed(self.fresh(60, hostname_verified=False))

    def test_obsolete_tls_version_fails(self):
        assert "tls_version" in failed(self.fresh(60, protocol="TLSv1"))

    def test_unknown_tls_version_fails(self):
        assert "tls_version" in failed(self.fresh(60, protocol=None))


class TestShareTarget:
    def test_documented_response_passes(self):
        results = evaluate_share_target(200, {"Cache-Control": "no-store, must-revalidate"})
        assert failed(results) == []

    def test_cached_share_response_fails(self):
        # 공유된 문자 원문이 담긴 문서다. 캐시되면 기기에 남는다 (docs/30).
        results = evaluate_share_target(200, {"Cache-Control": "public, max-age=60"})
        assert "share_target_no_store" in failed(results)

    def test_missing_cache_control_fails(self):
        assert "share_target_no_store" in failed(evaluate_share_target(200, {}))

    def test_cookie_on_share_response_fails(self):
        results = evaluate_share_target(
            200, {"Cache-Control": "no-store", "Set-Cookie": "session=abc"}
        )
        assert "share_target_no_cookie" in failed(results)

    def test_error_status_fails(self):
        assert "share_target_status" in failed(evaluate_share_target(502, {"Cache-Control": "no-store"}))


class TestInternalPorts:
    def test_closed_port_passes(self):
        assert evaluate_internal_port(5432, reachable=False).passed

    def test_reachable_database_port_fails(self):
        assert not evaluate_internal_port(5432, reachable=True).passed


class TestSummary:
    def test_all_passing_summary(self):
        results = evaluate_share_target(200, {"Cache-Control": "no-store"})
        assert summarize(results) == {
            "checks": 3,
            "failed": 0,
            "failed_checks": [],
            "passed": True,
        }

    def test_failures_are_named(self):
        summary = summarize(evaluate_share_target(500, {}))
        assert summary["passed"] is False
        assert "share_target_status" in summary["failed_checks"]
        assert "share_target_no_store" in summary["failed_checks"]
