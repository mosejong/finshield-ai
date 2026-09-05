"""공개 도메인이 실제로 안전하게 서비스되고 있는지 판정한다.

값을 받아 오는 일은 `scripts/verify_public_deployment.py` 가 하고, 합격/불합격
판정은 여기 있는 순수 함수가 한다. 나눈 이유는 네트워크 없이 **기준 자체를**
테스트하기 위해서다. P0-3 에서 겪은 것이 정확히 이 문제였다 - 검사가 돌고
있었지만 실패할 수 없는 검사였고, 초록불이 아무것도 증명하지 않았다.

여기서 판정하는 것은 `docs/28` P0-4 의 완료 기준이다. "인증서가 발급됐다" 가
아니라 **외부에서 접속했을 때 평문으로 새지 않고, 만료가 임박하지 않았으며,
내부 포트가 열려 있지 않다** 까지다.
"""

from dataclasses import dataclass
from datetime import datetime

# `docs/26` 이 명시한 값. 1년 미만이면 브라우저 preload 목록 기준에도 못 미친다.
MINIMUM_HSTS_MAX_AGE = 31_536_000

# Let's Encrypt 인증서는 90일이고 Caddy 는 만료 30일 전부터 갱신을 시도한다.
# 21일이 남았다는 것은 갱신이 9일 동안 실패해 왔다는 뜻이다. 7일이면 주말을
# 한 번 넘기면 끝난다.
CERTIFICATE_WARN_DAYS = 21
CERTIFICATE_FAIL_DAYS = 7

# 값까지 고정해야 하는 헤더. 존재만 보면 `X-Frame-Options: ALLOWALL` 같은
# 무력화를 못 잡는다.
EXACT_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
}

# 존재와 필수 지시어만 보는 헤더.
REQUIRED_CSP_DIRECTIVES = ("default-src 'self'", "frame-ancestors 'none'", "object-src 'none'")

# 서버 소프트웨어와 버전을 알려 줄 이유가 없다. Caddy 는 `-Server` 로 지우고
# Next 는 `poweredByHeader: false` 로 지운다.
FORBIDDEN_HEADERS = ("server", "x-powered-by")

# 운영에서는 아예 publish 하지 않는 포트들이다. 열려 있으면 Caddy 를 우회해
# 평문으로 붙을 수 있다는 뜻이라 HTTPS 를 붙인 의미가 없어진다.
INTERNAL_PORTS = (18000, 13000, 5432)


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def evaluate_https_redirect(status: int, location: str | None, domain: str) -> CheckResult:
    """평문 접속이 HTTPS 로 넘어가는가.

    200 이 돌아오면 HTTPS 가 붙어 있어도 실패다. 사용자가 주소를 칠 때는
    거의 항상 `http://` 이고, 그 요청이 그대로 처리되면 세션 쿠키가 평문으로
    오간다.
    """
    if status not in (301, 302, 307, 308):
        return CheckResult("https_redirect", False, f"평문 요청이 {status} 로 응답했다")
    if not location:
        return CheckResult("https_redirect", False, f"{status} 인데 Location 이 없다")
    if not location.startswith(f"https://{domain}"):
        return CheckResult("https_redirect", False, f"다른 곳으로 보낸다: {location}")
    return CheckResult("https_redirect", True, f"{status} → {location}")


def evaluate_hsts(value: str | None) -> CheckResult:
    """HSTS 가 실제로 1년 이상인가.

    `max-age=0` 은 헤더가 있는데 HSTS 를 끄는 값이다. 존재 여부만 보는 검사가
    놓치는 대표적인 경우다.
    """
    if not value:
        return CheckResult("hsts", False, "Strict-Transport-Security 가 없다")

    directives = [part.strip().lower() for part in value.split(";")]
    max_age: int | None = None
    for directive in directives:
        if directive.startswith("max-age="):
            try:
                max_age = int(directive.removeprefix("max-age="))
            except ValueError:
                return CheckResult("hsts", False, f"max-age 를 읽을 수 없다: {value}")

    if max_age is None:
        return CheckResult("hsts", False, f"max-age 가 없다: {value}")
    if max_age < MINIMUM_HSTS_MAX_AGE:
        return CheckResult("hsts", False, f"max-age={max_age} 는 1년 미만이다")
    if "includesubdomains" not in directives:
        return CheckResult("hsts", False, f"includeSubDomains 가 없다: {value}")
    return CheckResult("hsts", True, value)


def evaluate_security_headers(headers: dict[str, str]) -> list[CheckResult]:
    """브라우저 응답 헤더가 `docs/26` 의 계약을 지키는가."""
    normalized = {name.lower(): value for name, value in headers.items()}
    results: list[CheckResult] = []

    for name, expected in EXACT_HEADERS.items():
        actual = normalized.get(name)
        results.append(
            CheckResult(
                f"header:{name}",
                actual == expected,
                f"{actual!r} (기대값 {expected!r})" if actual != expected else expected,
            )
        )

    csp = normalized.get("content-security-policy", "")
    missing = [directive for directive in REQUIRED_CSP_DIRECTIVES if directive not in csp]
    results.append(
        CheckResult(
            "header:content-security-policy",
            not missing and bool(csp),
            "없다" if not csp else (f"빠진 지시어: {', '.join(missing)}" if missing else "필수 지시어 확인"),
        )
    )

    for name in FORBIDDEN_HEADERS:
        present = name in normalized
        results.append(
            CheckResult(
                f"header:{name}",
                not present,
                f"노출됨: {normalized.get(name)!r}" if present else "없음",
            )
        )

    return results


def evaluate_certificate(
    not_after: datetime,
    now: datetime,
    *,
    hostname_verified: bool,
    protocol: str | None,
) -> list[CheckResult]:
    """인증서가 신뢰 가능하고, 갱신이 조용히 멈춰 있지 않은가.

    만료일만 보는 것으로는 부족하다. 갱신이 멈춘 상태는 만료 직전이 아니라
    **만료 30일 전부터** 이미 진행 중이고, 그때 알아야 손쓸 수 있다.
    """
    results = [
        CheckResult(
            "certificate_trusted",
            hostname_verified,
            "체인·호스트명 검증 통과" if hostname_verified else "공개 CA 로 검증되지 않는다",
        )
    ]

    remaining = certificate_days_remaining(not_after, now)
    if remaining < 0:
        detail = f"{-remaining}일 전에 만료됐다"
        passed = False
    elif remaining < CERTIFICATE_FAIL_DAYS:
        detail = f"{remaining}일 남았다. 갱신이 멈춰 있다"
        passed = False
    elif remaining < CERTIFICATE_WARN_DAYS:
        detail = f"{remaining}일 남았다. 갱신이 {30 - remaining}일째 실패하고 있다"
        passed = False
    else:
        detail = f"{remaining}일 남음 (만료 {not_after.date().isoformat()})"
        passed = True
    results.append(CheckResult("certificate_expiry", passed, detail))

    # TLS 1.0/1.1 은 주요 브라우저가 이미 거부한다. 여기서 걸린다는 것은
    # 앞단에 우리가 모르는 종단점이 하나 더 있다는 뜻이다.
    acceptable = protocol in ("TLSv1.2", "TLSv1.3")
    results.append(
        CheckResult("tls_version", acceptable, protocol or "알 수 없음")
    )
    return results


def certificate_days_remaining(not_after: datetime, now: datetime) -> int:
    return (not_after - now).days


def evaluate_share_target(status: int, headers: dict[str, str]) -> list[CheckResult]:
    """공유 시트 진입점이 실도메인에서도 값을 남기지 않는가 (`docs/30`)."""
    normalized = {name.lower(): value for name, value in headers.items()}
    cache_control = normalized.get("cache-control", "")
    return [
        CheckResult("share_target_status", status == 200, str(status)),
        CheckResult(
            "share_target_no_store",
            "no-store" in cache_control.lower(),
            cache_control or "Cache-Control 이 없다",
        ),
        CheckResult(
            "share_target_no_cookie",
            "set-cookie" not in normalized,
            "쿠키 없음" if "set-cookie" not in normalized else "Set-Cookie 가 붙었다",
        ),
    ]


# 밖에서 상태를 볼 수 있어야 하는 경로와 각 경로가 내는 값.
# `app/api/routes/health.py` 와 `deploy/Caddyfile` 의 `@public_health` 가 같은
# 목록을 갖는지는 `tests/test_public_routing.py` 가 지킨다. 여기서 보는 것은
# 그 세 경로가 **공개 도메인에서** 실제로 답하느냐다. 2026-09-05 외부 검수가
# 셋 다 404 라고 보고했고, 그때 이 검사는 없었다.
PUBLIC_HEALTH_STATUS = {
    "/health": "ok",
    "/health/live": "alive",
    "/health/ready": "ready",
}

# 금융상품 경로가 실패할 때 상태 코드가 원인을 가른다. 이 대응은
# `app/api/routes/products.py` 가 정한 것이고, Next 프록시가 503 을 그대로
# 통과시키기 때문에(`web/lib/api/proxy-response.ts` 의 `PASSTHROUGH_STATUSES`)
# 밖에서 두드려도 구분이 남는다. 이 구분이 2026-09-05 에 실제로 값을 했다 -
# 돌아온 것이 503 이었으므로 제공자 장애가 아니라 배포 설정 누락으로 바로
# 좁혔고, VM 에 들어가기 전에 원인이 정해졌다.
PRODUCT_FAILURE_CAUSES = {
    503: "설정 누락 - backend 에 PUBLIC_DATA_SERVICE_KEY 가 없다 (compose.public-data.yaml)",
    502: "제공자 실패 - 키는 있고 공공데이터 호출이 실패했다",
    404: "그 상품이 이번 기준월 목록에 없다",
    400: "요청이 스키마에 맞지 않는다. 검사기 쪽 문제다",
    429: "요청 한도에 걸렸다. 잠시 뒤 다시 찍는다",
}


def evaluate_public_health(path: str, status: int, body: str) -> CheckResult:
    """상태 확인 경로가 backend 까지 닿았는가.

    404 는 "백엔드가 죽었다" 가 아니라 **리버스 프록시가 backend 로 보내지
    않는다** 는 뜻이다. 그래서 본문의 값까지 본다 - 200 이어도 그것이 Next 가
    낸 200 이면 여기 적힌 문자열이 없다.
    """
    name = f"health:{path}"
    expected = PUBLIC_HEALTH_STATUS.get(path)
    if expected is None:
        return CheckResult(name, False, "공개 대상이 아닌 경로다")
    if status == 404:
        return CheckResult(name, False, "404 - 리버스 프록시가 backend 로 보내지 않는다")
    if status == 400:
        return CheckResult(name, False, "400 - backend 가 Host 를 거부했다 (TRUSTED_HOSTS)")
    if status != 200:
        return CheckResult(name, False, str(status))
    if f'"{expected}"' not in body:
        return CheckResult(name, False, f'200 인데 "{expected}" 가 없다. backend 응답이 아니다')
    return CheckResult(name, True, f"200 {expected}")


def evaluate_product_endpoint(name: str, status: int, item_count: int) -> CheckResult:
    """공식 상품 경로 하나가 실제로 상품을 돌려주는가.

    화면이 200 이라는 사실만으로는 아무것도 알 수 없다. `/products` 는 껍데기가
    먼저 그려지고 상품은 그 뒤에 브라우저가 따로 부르므로, 상품이 전부 죽어
    있어도 `page:/products` 는 초록이다. 2026-09-05 에 정확히 그랬다 - 화면은
    200, 상품은 전부 503.
    """
    check = f"product:{name}"
    if status != 200:
        cause = PRODUCT_FAILURE_CAUSES.get(status, "알 수 없는 실패")
        return CheckResult(check, False, f"{status} - {cause}")
    if item_count <= 0:
        return CheckResult(check, False, "200 인데 상품이 0건이다")
    return CheckResult(check, True, f"200, {item_count}건")


def evaluate_internal_port(port: int, reachable: bool) -> CheckResult:
    return CheckResult(
        f"internal_port:{port}",
        not reachable,
        "닫힘" if not reachable else "외부에서 붙는다. Caddy 를 우회할 수 있다",
    )


def summarize(results: list[CheckResult]) -> dict[str, object]:
    failed = [result.name for result in results if not result.passed]
    return {
        "checks": len(results),
        "failed": len(failed),
        "failed_checks": failed,
        "passed": not failed,
    }
