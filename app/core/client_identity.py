"""요청을 보낸 client 를 식별한다.

rate limit 은 "누구를" 제한하는지가 정해져야 성립한다. 그런데 이 서비스의
공개 경로는 `Caddy -> web:3000 (Next.js) -> backend:8000` 이라서, backend 가
보는 TCP peer 는 언제나 web 컨테이너 하나다. 그대로 쓰면 모든 사용자가 한
덩어리로 묶여, 공격자 한 명이 전체 사용자를 막아버린다. 제한이 없는 것보다
나쁘다.

그래서 forwarded 헤더를 봐야 하는데, 이 헤더는 클라이언트가 마음대로 적어
보낼 수 있다. 무조건 믿으면 매 요청 다른 IP 를 적는 것만으로 제한이 무력화되고,
무조건 무시하면 위의 한 덩어리 문제로 돌아간다.

절충은 **몇 홉을 신뢰하는지 명시적으로 설정하게** 하는 것이다. 신뢰 홉 수가
n 이면 오른쪽에서 n 번째 항목을 client 로 본다. 각 프록시가 자기가 본 peer 를
오른쪽에 덧붙이므로, 클라이언트가 미리 적어 보낸 값은 항상 왼쪽으로 밀려
선택되지 않는다.

기본값은 0 - 아무 헤더도 믿지 않는다. 설정을 빠뜨렸을 때 조용히 위조를
허용하는 대신, IP 기반 식별이 동작하지 않는 쪽으로 기울인다.
"""

import ipaddress
import os
from collections.abc import Mapping, Sequence

from starlette.types import Scope

FORWARDED_FOR_HEADER = b"x-forwarded-for"

MAX_TRUSTED_PROXY_HOPS = 8


class ClientIdentityConfigurationError(RuntimeError):
    pass


def read_trusted_proxy_hops(values: Mapping[str, str] | None = None) -> int:
    settings = values if values is not None else os.environ
    raw_value = settings.get("FINSHIELD_TRUSTED_PROXY_HOPS", "0").strip()
    try:
        hops = int(raw_value)
    except ValueError as exc:
        raise ClientIdentityConfigurationError(
            "FINSHIELD_TRUSTED_PROXY_HOPS must be an integer"
        ) from exc
    if hops < 0 or hops > MAX_TRUSTED_PROXY_HOPS:
        raise ClientIdentityConfigurationError(
            f"FINSHIELD_TRUSTED_PROXY_HOPS must be between 0 and {MAX_TRUSTED_PROXY_HOPS}"
        )
    return hops


def verify_client_identity_configuration(
    values: Mapping[str, str] | None = None,
) -> None:
    settings = values if values is not None else os.environ
    read_trusted_proxy_hops(settings)
    app_env = settings.get("APP_ENV", "development").strip().lower()
    if app_env in {"development", "test"}:
        return
    if "FINSHIELD_TRUSTED_PROXY_HOPS" not in settings:
        # 기본값 0 을 물려받으면 배포 환경에서는 모든 사용자가 web 컨테이너
        # 하나로 식별된다. 조용히 그렇게 되지 않도록 명시를 강제한다.
        raise ClientIdentityConfigurationError(
            "deployed environments must set FINSHIELD_TRUSTED_PROXY_HOPS explicitly"
        )


def resolve_client_ip(
    scope: Scope, values: Mapping[str, str] | None = None
) -> str | None:
    """client IP 를 돌려준다. 확정할 수 없으면 `None`.

    `None` 은 "제한하지 않는다" 가 아니라 "식별되지 않았다" 이다. 호출자는
    이것을 공용 bucket 으로 묶어야 한다. 식별 실패를 통과로 처리하면 위조
    한 번으로 제한을 벗어날 수 있다.
    """
    hops = read_trusted_proxy_hops(values)
    if hops == 0:
        return _peer_ip(scope)

    chain = _forwarded_chain(scope)
    if len(chain) < hops:
        # 체인이 설정보다 짧다. 프록시를 거치지 않고 직접 들어왔거나 설정이
        # 틀렸다. 어느 쪽이든 헤더를 믿을 근거가 없으므로 peer 로 되돌린다.
        return _peer_ip(scope)
    return _clean_ip(chain[-hops])


def _forwarded_chain(scope: Scope) -> Sequence[str]:
    """`X-Forwarded-For` 를 왼쪽부터 순서대로 돌려준다.

    잘못된 항목도 자리를 유지한 채 남긴다. 걸러내면 인덱스가 밀려서
    홉 계산이 어긋나고, 위조된 항목을 client 로 고르게 된다.
    """
    entries: list[str] = []
    for key, value in scope.get("headers", ()):
        if key != FORWARDED_FOR_HEADER:
            continue
        entries.extend(value.decode("latin-1").split(","))
    return [entry.strip() for entry in entries if entry.strip()]


def _peer_ip(scope: Scope) -> str | None:
    client = scope.get("client")
    if not client:
        return None
    return _clean_ip(str(client[0]))


def _clean_ip(raw: str) -> str | None:
    value = raw.strip()
    if not value:
        return None
    if value.startswith("["):
        # `[2001:db8::1]:443`
        value = value[1:].partition("]")[0]
    elif value.count(":") == 1:
        # `203.0.113.7:443` — IPv6 는 콜론이 둘 이상이라 걸리지 않는다.
        value = value.partition(":")[0]
    try:
        # 표기를 정규화해 같은 주소가 다른 key 로 새지 않게 한다.
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None
