"""공개 도메인을 밖에서 두드려 본다. `docs/28` P0-4 의 완료 기준 검사기다.

    python -m scripts.verify_public_deployment --domain finshield.example.com
    python -m scripts.verify_public_deployment --certificate-only   # cron 용

**서버 안이 아니라 다른 네트워크에서 돌려야 의미가 있다.** 서버 안에서는
loopback 에만 bind 된 내부 포트가 열려 보이고, 방화벽도 통과한 뒤라 "밖에서
무엇이 보이는가" 를 측정하지 못한다.

판정은 `app/core/public_deployment.py` 가 한다. 여기서는 값만 받아 온다.

인증서 갱신은 조용히 실패한다. Caddy 는 만료 30일 전부터 갱신을 시도하고,
실패해도 사용자는 만료 당일까지 아무것도 느끼지 못한다. `--certificate-only`
로 주기 실행해 두면 그 침묵을 깬다 (`docs/28` P1-1 이 붙기 전까지의 최소한).

화면이 200 이라는 것과 그 화면이 부르는 API 가 산다는 것은 다른 문제다.
2026-09-05 에 `page:/products` 는 초록이었고 금융상품은 전부 503 이었다 -
껍데기는 서버가 그리고 상품은 브라우저가 따로 부르기 때문이다. 그래서 화면
목록과 별도로 **그 화면이 부르는 경로**를 목록·상세·비교까지 이어서 찍는다.

출력은 JSON 한 줄씩이다. 공유 문구 왕복 검사에는 실제 문자 대신 고정된
검사 문자열만 쓴다 - 검사기가 남의 문자 원문을 만들 이유가 없다.
"""

import argparse
import json
import os
import socket
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from cryptography import x509

from app.core.public_deployment import (
    INTERNAL_PORTS,
    PUBLIC_HEALTH_STATUS,
    CheckResult,
    evaluate_certificate,
    evaluate_https_redirect,
    evaluate_hsts,
    evaluate_internal_port,
    evaluate_product_endpoint,
    evaluate_public_health,
    evaluate_security_headers,
    evaluate_share_target,
    summarize,
)

TIMEOUT = 10

# 공공데이터 왕복이 들어 있어 화면보다 느리다. 10초로는 느린 날에 검사기가
# 스스로 타임아웃을 내고, 그러면 배포 실패와 구분되지 않는다.
PRODUCT_TIMEOUT = 25

# 로그인 없이 열려야 하는 주요 화면. 하나라도 500 이면 공개 상태가 아니다.
PUBLIC_PATHS = (
    "/",
    "/check",
    "/onboarding",
    "/profile",
    "/products",
    "/learn/wealth",
    "/offline",
    "/manifest.webmanifest",
    "/sw.js",
)

SHARE_PROBE_TEXT = "배포 확인용 문구입니다. 실제 사용자 메시지가 아닙니다."

# 상품 목록을 받아 올 때 쓰는 목표값. `FinancialGoal` 의 한 값이고, 프로필을
# 만들지 않는다 - 이 경로는 목표 하나만 받는다.
PRODUCT_PROBE_GOAL = "emergency_cash"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """리다이렉트를 따라가면 리다이렉트 자체를 검사할 수 없다."""

    def redirect_request(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return None


def check_https_redirect(domain: str) -> CheckResult:
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(f"http://{domain}/", timeout=TIMEOUT) as response:
            return evaluate_https_redirect(response.status, response.headers.get("location"), domain)
    except urllib.error.HTTPError as error:
        return evaluate_https_redirect(error.code, error.headers.get("location"), domain)
    except OSError as error:
        return CheckResult("https_redirect", False, f"평문 접속 실패: {type(error).__name__}")


def fetch(url: str, context: ssl.SSLContext) -> tuple[int, dict[str, str], bytes]:
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT, context=context) as response:
            return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers.items()), error.read()


def check_paths(domain: str, context: ssl.SSLContext) -> list[CheckResult]:
    results: list[CheckResult] = []
    for path in PUBLIC_PATHS:
        try:
            status, headers, _ = fetch(f"https://{domain}{path}", context)
        except OSError as error:
            results.append(CheckResult(f"page:{path}", False, type(error).__name__))
            continue

        results.append(CheckResult(f"page:{path}", status == 200, str(status)))

        if path == "/":
            results.append(evaluate_hsts(headers.get("Strict-Transport-Security")))
            results.extend(evaluate_security_headers(headers))
        # 200 일 때만 본다. 404 응답에도 no-store 가 붙어 있어서, 그냥 보면
        # "서비스 워커가 캐시되지 않는다" 가 파일이 없을 때 통과해 버린다.
        if path == "/sw.js" and status == 200:
            cache_control = headers.get("Cache-Control", "")
            results.append(
                CheckResult(
                    "service_worker_not_cached",
                    "no-store" in cache_control.lower(),
                    cache_control or "Cache-Control 이 없다",
                )
            )
    return results


def check_public_health(domain: str, context: ssl.SSLContext) -> list[CheckResult]:
    """상태 확인 세 경로를 공개 도메인에서 찍는다.

    컨테이너 안에서 찍으면 언제나 초록이다. 리버스 프록시가 그 요청을 backend
    로 보내는지는 **밖에서만** 보인다.
    """
    results: list[CheckResult] = []
    for path in PUBLIC_HEALTH_STATUS:
        try:
            status, _, body = fetch(f"https://{domain}{path}", context)
        except OSError as error:
            results.append(CheckResult(f"health:{path}", False, type(error).__name__))
            continue
        results.append(evaluate_public_health(path, status, body.decode("utf-8", "replace")))
    return results


def post_json(url: str, payload: dict, context: ssl.SSLContext) -> tuple[int, object]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=PRODUCT_TIMEOUT, context=context) as response:
            return response.status, _decode(response.read())
    except urllib.error.HTTPError as error:
        return error.code, _decode(error.read())


def _decode(raw: bytes) -> object:
    try:
        return json.loads(raw or b"null")
    except ValueError:
        return None


def check_product_catalog(domain: str, context: ssl.SSLContext) -> list[CheckResult]:
    """목록 → 상세 → 비교를 실제 식별자로 이어서 찍는다.

    상세와 비교는 목록이 돌려준 `source_product_id` 를 그대로 쓴다. 검사기가
    식별자를 지어내면 404 가 나고, 그 404 는 배포가 아니라 검사기 탓이다.
    목록이 실패하면 뒤의 둘은 찍지 않는다 - 같은 원인 하나를 세 번 세면
    실패 개수가 원인 개수를 속인다.
    """
    try:
        status, payload = post_json(
            f"https://{domain}/api/proxy/recommendations",
            {"goal": PRODUCT_PROBE_GOAL},
            context,
        )
    except OSError as error:
        return [CheckResult("product:list", False, type(error).__name__)]

    matches = payload.get("results") if isinstance(payload, dict) else None
    matches = matches if isinstance(matches, list) else []
    results = [evaluate_product_endpoint("list", status, len(matches))]

    identifiers = [
        match["product"]["source_product_id"]
        for match in matches
        if isinstance(match, dict)
        and isinstance(match.get("product"), dict)
        and isinstance(match["product"].get("source_product_id"), str)
    ]
    if len(identifiers) < 2:
        return results

    detail_url = f"https://{domain}/api/proxy/products/{urllib.parse.quote(identifiers[0], safe='')}"
    try:
        status, _, body = fetch(detail_url, context)
    except OSError as error:
        results.append(CheckResult("product:detail", False, type(error).__name__))
    else:
        detail = _decode(body)
        found = isinstance(detail, dict) and detail.get("source_product_id") == identifiers[0]
        results.append(evaluate_product_endpoint("detail", status, 1 if found else 0))

    try:
        status, payload = post_json(
            f"https://{domain}/api/proxy/products/compare",
            {"product_ids": identifiers[:2]},
            context,
        )
    except OSError as error:
        results.append(CheckResult("product:compare", False, type(error).__name__))
    else:
        items = payload.get("items") if isinstance(payload, dict) else None
        results.append(
            evaluate_product_endpoint("compare", status, len(items) if isinstance(items, list) else 0)
        )
    return results


def check_share_target(domain: str, context: ssl.SSLContext) -> list[CheckResult]:
    boundary = "----finshielddeploycheck"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="text"\r\n\r\n'
        f"{SHARE_PROBE_TEXT}\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")
    request = urllib.request.Request(
        f"https://{domain}/check/shared",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT, context=context) as response:
            return evaluate_share_target(response.status, dict(response.headers.items()))
    except urllib.error.HTTPError as error:
        return evaluate_share_target(error.code, dict(error.headers.items()))
    except OSError as error:
        return [CheckResult("share_target_status", False, type(error).__name__)]


def probe_certificate(domain: str, insecure: bool) -> list[CheckResult]:
    """인증서를 읽고 검증 결과까지 함께 판정한다.

    검증에 실패해도 인증서 자체는 다시 읽는다. "왜 못 믿는가" 를 만료일과 함께
    봐야 판단할 수 있고, 사설 CA 로 하는 예행연습에서도 만료는 보고 싶다.
    """
    verified = True
    der: bytes | None = None
    protocol: str | None = None

    try:
        der, protocol = _handshake(domain, ssl.create_default_context())
    except ssl.SSLCertVerificationError:
        verified = False
    except OSError as error:
        return [CheckResult("certificate_trusted", False, f"접속 실패: {type(error).__name__}")]

    if der is None:
        relaxed = ssl.create_default_context()
        relaxed.check_hostname = False
        relaxed.verify_mode = ssl.CERT_NONE
        try:
            der, protocol = _handshake(domain, relaxed)
        except OSError as error:
            return [CheckResult("certificate_trusted", False, f"접속 실패: {type(error).__name__}")]

    certificate = x509.load_der_x509_certificate(der)
    results = evaluate_certificate(
        certificate.not_valid_after_utc,
        datetime.now(timezone.utc),
        hostname_verified=verified,
        protocol=protocol,
    )

    if insecure and not verified:
        # 예행연습에서는 사설 CA 가 정상이다. 다만 통과했다고 적지 않고, 무엇을
        # 건너뛰었는지 결과에 남긴다. 이 줄이 실도메인 출력에 보이면 잘못된 것이다.
        results = [
            CheckResult("certificate_trusted", True, "--insecure: 체인 검증을 건너뛴 예행연습")
            if result.name == "certificate_trusted"
            else result
            for result in results
        ]

    return results


def _handshake(domain: str, context: ssl.SSLContext) -> tuple[bytes, str | None]:
    with socket.create_connection((domain, 443), timeout=TIMEOUT) as raw:
        with context.wrap_socket(raw, server_hostname=domain) as tls:
            return tls.getpeercert(binary_form=True), tls.version()


def check_internal_ports(domain: str) -> list[CheckResult]:
    results = []
    for port in INTERNAL_PORTS:
        try:
            with socket.create_connection((domain, port), timeout=3):
                reachable = True
        except OSError:
            reachable = False
        results.append(evaluate_internal_port(port, reachable))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", default=None, help="공개 도메인. 없으면 FINSHIELD_DOMAIN")
    parser.add_argument(
        "--certificate-only",
        action="store_true",
        help="인증서 만료만 본다. 주기 실행용",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="사설 CA 예행연습. 체인 검증 실패를 실패로 세지 않는다",
    )
    arguments = parser.parse_args()

    domain = arguments.domain or os.getenv("FINSHIELD_DOMAIN")
    if not domain:
        print(
            json.dumps(
                {"error": "domain is required (--domain 또는 FINSHIELD_DOMAIN)"},
                ensure_ascii=False,
            )
        )
        return 2

    results = probe_certificate(domain, arguments.insecure)

    if not arguments.certificate_only:
        context = ssl.create_default_context()
        if arguments.insecure:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE

        results.append(check_https_redirect(domain))
        results.extend(check_paths(domain, context))
        results.extend(check_public_health(domain, context))
        results.extend(check_product_catalog(domain, context))
        results.extend(check_share_target(domain, context))
        results.extend(check_internal_ports(domain))

    for result in results:
        print(
            json.dumps(
                {"check": result.name, "passed": result.passed, "detail": result.detail},
                ensure_ascii=False,
            )
        )

    summary = summarize(results)
    print(json.dumps({"domain": domain, **summary}, ensure_ascii=False, sort_keys=True))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
