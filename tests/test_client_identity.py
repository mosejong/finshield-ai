import pytest

from app.core.client_identity import (
    ClientIdentityConfigurationError,
    read_trusted_proxy_hops,
    resolve_client_ip,
    verify_client_identity_configuration,
)


def _scope(
    *, client: tuple[str, int] | None = ("10.0.0.9", 51234), forwarded: list[str] | None = None
) -> dict:
    headers: list[tuple[bytes, bytes]] = [(b"host", b"backend")]
    for value in forwarded or []:
        headers.append((b"x-forwarded-for", value.encode()))
    return {"type": "http", "method": "POST", "headers": headers, "client": client}


def test_without_trusted_hops_the_peer_address_is_used() -> None:
    ip = resolve_client_ip(
        _scope(forwarded=["203.0.113.7"]), {"FINSHIELD_TRUSTED_PROXY_HOPS": "0"}
    )
    assert ip == "10.0.0.9"


def test_forwarded_header_is_ignored_by_default() -> None:
    """설정을 빠뜨렸을 때 헤더를 믿어버리면 안 된다."""
    ip = resolve_client_ip(_scope(forwarded=["203.0.113.7"]), {})
    assert ip == "10.0.0.9"


def test_one_trusted_hop_takes_the_rightmost_entry() -> None:
    ip = resolve_client_ip(
        _scope(forwarded=["203.0.113.7"]), {"FINSHIELD_TRUSTED_PROXY_HOPS": "1"}
    )
    assert ip == "203.0.113.7"


def test_client_supplied_prefix_cannot_impersonate_another_address() -> None:
    """위조 시도는 항상 왼쪽으로 밀려 선택되지 않는다.

    클라이언트가 `X-Forwarded-For: 1.2.3.4` 를 붙여 보내면 Caddy 가 자기가
    본 peer 를 오른쪽에 덧붙인다. 오른쪽에서 세면 진짜 주소가 잡힌다.
    """
    ip = resolve_client_ip(
        _scope(forwarded=["1.2.3.4, 203.0.113.7"]),
        {"FINSHIELD_TRUSTED_PROXY_HOPS": "1"},
    )
    assert ip == "203.0.113.7"


def test_repeated_headers_are_joined_in_order() -> None:
    """같은 헤더가 여러 줄로 오는 경우도 하나의 체인이다."""
    ip = resolve_client_ip(
        _scope(forwarded=["1.2.3.4", "198.51.100.2, 203.0.113.7"]),
        {"FINSHIELD_TRUSTED_PROXY_HOPS": "2"},
    )
    assert ip == "198.51.100.2"


def test_chain_shorter_than_configured_hops_falls_back_to_the_peer() -> None:
    """체인이 설정보다 짧으면 헤더를 믿을 근거가 없다.

    프록시를 건너뛰고 직접 들어온 요청이 프록시를 거친 것처럼 취급되면
    안 된다.
    """
    ip = resolve_client_ip(
        _scope(forwarded=["203.0.113.7"]), {"FINSHIELD_TRUSTED_PROXY_HOPS": "2"}
    )
    assert ip == "10.0.0.9"


def test_ports_are_stripped() -> None:
    assert (
        resolve_client_ip(
            _scope(forwarded=["203.0.113.7:44321"]),
            {"FINSHIELD_TRUSTED_PROXY_HOPS": "1"},
        )
        == "203.0.113.7"
    )
    assert (
        resolve_client_ip(
            _scope(forwarded=["[2001:db8::1]:44321"]),
            {"FINSHIELD_TRUSTED_PROXY_HOPS": "1"},
        )
        == "2001:db8::1"
    )


def test_ipv6_notation_is_normalised() -> None:
    """같은 주소가 표기만 달라 다른 key 로 새면 제한을 그만큼 우회한다."""
    ip = resolve_client_ip(
        _scope(forwarded=["2001:0DB8:0000:0000:0000:0000:0000:0001"]),
        {"FINSHIELD_TRUSTED_PROXY_HOPS": "1"},
    )
    assert ip == "2001:db8::1"


def test_unparsable_entry_yields_no_identity() -> None:
    """RFC 7239 의 `unknown` 같은 값은 주소가 아니다."""
    ip = resolve_client_ip(
        _scope(forwarded=["1.2.3.4, unknown"]),
        {"FINSHIELD_TRUSTED_PROXY_HOPS": "1"},
    )
    assert ip is None


def test_invalid_entries_do_not_shift_the_hop_count() -> None:
    """잘못된 항목을 걸러내면 자리가 밀려 위조된 값이 선택된다."""
    ip = resolve_client_ip(
        _scope(forwarded=["9.9.9.9, unknown, 203.0.113.7"]),
        {"FINSHIELD_TRUSTED_PROXY_HOPS": "2"},
    )
    assert ip is None


def test_missing_peer_yields_no_identity() -> None:
    assert resolve_client_ip(_scope(client=None), {}) is None


def test_hops_are_read_and_bounded() -> None:
    assert read_trusted_proxy_hops({}) == 0
    assert read_trusted_proxy_hops({"FINSHIELD_TRUSTED_PROXY_HOPS": " 2 "}) == 2


@pytest.mark.parametrize("value", ["-1", "9", "many", ""])
def test_invalid_hop_configuration_is_rejected(value: str) -> None:
    with pytest.raises(ClientIdentityConfigurationError):
        read_trusted_proxy_hops({"FINSHIELD_TRUSTED_PROXY_HOPS": value})


def test_deployment_must_declare_the_hop_count() -> None:
    """배포 환경에서 기본값 0 을 물려받으면 모두가 한 덩어리가 된다."""
    with pytest.raises(ClientIdentityConfigurationError):
        verify_client_identity_configuration({"APP_ENV": "production"})

    verify_client_identity_configuration(
        {"APP_ENV": "production", "FINSHIELD_TRUSTED_PROXY_HOPS": "1"}
    )
    # 직접 노출을 의도한 0 도 명시라면 통과한다.
    verify_client_identity_configuration(
        {"APP_ENV": "production", "FINSHIELD_TRUSTED_PROXY_HOPS": "0"}
    )


def test_local_environments_do_not_require_the_setting() -> None:
    verify_client_identity_configuration({"APP_ENV": "development"})
    verify_client_identity_configuration({})
