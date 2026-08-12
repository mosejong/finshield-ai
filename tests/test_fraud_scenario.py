import socket

import pytest
from fastapi.testclient import TestClient

from app.domain.fraud.sources import load_official_sources
from app.main import app


client = TestClient(app)

ALLOWED_SOURCE_URLS = {
    "https://www.fsec.or.kr/bbs/detail?bbsNo=11997&menuNo=66",
    "https://www.fsec.or.kr/bbs/detail?bbsNo=11872&menuNo=69",
    "https://www.police.go.kr/user/bbs/BD_selectBbs.do?q_bbsCode=1007&q_bbscttSn=20260209152732394",
    "https://ecrm.police.go.kr/minwon/crs/quick/vichelp",
    "https://www.kisa.or.kr/118/",
    "https://www.kisa.or.kr/1020601",
    "https://law.go.kr/LSW/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1025295481",
    "https://www.law.go.kr/LSW/lsInfoP.do?ancNo=21320&ancYd=20260203&efYd=20260804&lsiSeq=283199",
}


def analyze(text: str, state: str = "received_only", url: str | None = None) -> dict:
    payload = {"text": text, "state": state}
    if url is not None:
        payload["url"] = url
    response = client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 200
    return response.json()


def action_codes(body: dict) -> set[str]:
    return {action["code"] for action in body["actions"]}


def test_authority_impersonation_and_transfer_is_high_risk() -> None:
    body = analyze("검찰 수사관입니다. 지금 바로 안전계좌로 송금해 주세요.")

    assert body["risk_score"] == 12
    assert body["risk_level"] == "high"
    assert "authority_impersonation" in body["fraud_types"]
    assert {"STOP_CONTACT", "VERIFY_OFFICIAL_CHANNEL", "CONTACT_1394"} <= action_codes(
        body
    )


def test_low_interest_loan_and_check_card_request() -> None:
    body = analyze("정부지원 저금리 대출을 위해 체크카드를 보내 주세요.")

    assert {
        "loan_policy_impersonation",
        "account_access_request",
    } <= set(body["fraud_types"])
    assert body["risk_score"] == 35
    assert body["risk_level"] == "high"
    assert "DO_NOT_SHARE_ACCESS" in action_codes(body)


def test_otp_request_alone_is_not_low_risk() -> None:
    body = analyze("확인을 위해 OTP를 알려 주세요.")

    assert body["risk_score"] == 25
    assert body["risk_level"] == "medium"
    assert [signal["code"] for signal in body["signals"]] == ["credential"]


def test_app_install_and_remote_control() -> None:
    body = analyze("이 APK 앱 설치 후 원격제어를 허용해 주세요.")

    assert body["risk_score"] == 30
    assert body["risk_level"] == "high"
    assert "smishing_malware" in body["fraud_types"]
    assert {"DO_NOT_INSTALL", "CONTACT_KISA_118"} <= action_codes(body)


def test_receive_and_forward_money() -> None:
    body = analyze("계좌로 입금받고 다른 곳으로 다시 보내 주세요.")

    assert body["risk_score"] == 35
    assert body["risk_level"] == "high"
    assert "money_mule_transfer" in body["fraud_types"]
    assert [signal["code"] for signal in body["signals"]] == ["money_mule"]
    assert "DO_NOT_FORWARD_MONEY" in action_codes(body)


def test_card_delivery_claim() -> None:
    body = analyze("신청한 카드가 발급되어 오늘 카드 배송 예정입니다.")

    assert body["risk_score"] == 0
    assert "card_delivery_impersonation" in body["fraud_types"]
    assert body["risk_level"] == "medium"
    assert "VERIFY_OFFICIAL_CHANNEL" in action_codes(body)


def test_benign_message_has_no_fraud_type_or_sources() -> None:
    body = analyze("내일 오전 10시에 회의실에서 만나요.")

    assert body["risk_level"] == "low"
    assert body["signals"] == []
    assert body["fraud_types"] == []
    assert body["actions"] == []
    assert body["official_sources"] == []


def test_same_text_changes_policy_by_explicit_user_state() -> None:
    received = analyze("안녕하세요.", "received_only")
    transferred = analyze("안녕하세요.", "transferred_money")

    assert received["risk_score"] == transferred["risk_score"] == 0
    assert received["risk_level"] == "low"
    assert transferred["risk_level"] == "high"
    assert "CONTACT_FINANCIAL_INSTITUTION" in action_codes(transferred)


@pytest.mark.parametrize(
    ("state", "required_action"),
    [
        ("transferred_money", "CONTACT_112"),
        ("shared_account_access", "CONTACT_FINANCIAL_INSTITUTION"),
        ("installed_app", "CONTACT_KISA_118"),
        ("received_unknown_money", "DO_NOT_FORWARD_MONEY"),
    ],
)
def test_urgent_state_guarantees_high_risk_action(
    state: str, required_action: str
) -> None:
    body = analyze("짧은 안내입니다.", state)

    assert body["risk_score"] == 0
    assert body["risk_level"] == "high"
    assert required_action in action_codes(body)


def test_multiple_fraud_types_are_returned_in_stable_order() -> None:
    body = analyze(
        "경찰입니다. 저금리 대출을 위해 체크카드를 보내고 앱 설치 후 "
        "입금받은 돈을 다시 보내 주세요."
    )

    assert body["fraud_types"] == [
        "authority_impersonation",
        "loan_policy_impersonation",
        "account_access_request",
        "money_mule_transfer",
        "smishing_malware",
    ]


def test_text_length_boundary() -> None:
    accepted = client.post("/api/v1/analyze", json={"text": "가" * 10_000})
    rejected = client.post("/api/v1/analyze", json={"text": "가" * 10_001})

    assert accepted.status_code == 200
    assert rejected.status_code == 422


def test_supplied_url_is_never_fetched(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("outbound network access is forbidden")

    monkeypatch.setattr(socket, "create_connection", fail_if_called)
    body = analyze("확인용 주소입니다.", url="http://127.0.0.1:9999/private")

    assert "suspicious_link" in {signal["code"] for signal in body["signals"]}
    assert "DO_NOT_CLICK" in action_codes(body)


def test_normal_https_url_does_not_create_fraud_signal() -> None:
    body = analyze("은행 홈페이지를 확인했습니다.", url="https://www.kb.com")

    assert body["risk_score"] == 0
    assert body["risk_level"] == "low"
    assert "suspicious_link" not in {
        signal["code"] for signal in body["signals"]
    }
    assert "smishing_malware" not in body["fraud_types"]
    assert body["actions"] == []
    assert "평판을 확인하지 않아 안전 여부를 보증하지 않습니다" in body["summary"]


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/login",
        "https://localhost/internal",
        "https://192.168.0.10/login",
        "https://bank.example@evil.example/login",
        "https://bit.ly/account-check",
        "bit.ly/account-check",
        "https://xn--example-dk9c.com/login",
        "https://[invalid-ipv6/login",
    ],
)
def test_risky_lexical_url_features_are_detected_without_fetch(url: str) -> None:
    body = analyze("링크를 확인해 주세요.", url=url)

    assert body["risk_score"] == 0
    assert body["risk_level"] == "medium"
    assert "suspicious_link" in {signal["code"] for signal in body["signals"]}
    assert "smishing_malware" in body["fraud_types"]


@pytest.mark.parametrize(
    ("text", "expected_score", "expected_code"),
    [
        ("오늘까지 처리해 주세요.", 12, "urgency"),
        ("인증번호를 알려 주세요.", 25, "credential"),
        ("체크카드가 필요합니다.", 35, "account_access"),
        ("앱 설치 후 원격제어를 허용해 주세요.", 30, "remote_app"),
        ("입금받고 다시 보내 주세요.", 35, "money_mule"),
        (
            "오늘까지 인증번호와 체크카드를 주고 앱 설치 후 입금받고 다시 보내 주세요.",
            100,
            None,
        ),
    ],
)
def test_legacy_baseline_exact_scores(
    text: str, expected_score: int, expected_code: str | None
) -> None:
    body = analyze(text)

    assert body["risk_score"] == expected_score
    if expected_code is not None:
        matching = [
            signal for signal in body["signals"] if signal["code"] == expected_code
        ]
        assert len(matching) == 1


def test_legacy_signal_weights_are_preserved() -> None:
    body = analyze("오늘까지 인증번호와 통장을 주고 APK 설치 후 재송금해 주세요.")
    legacy_weights = {
        signal["code"]: signal["weight"]
        for signal in body["signals"]
        if signal["code"]
        in {"urgency", "credential", "account_access", "remote_app", "money_mule"}
    }

    assert legacy_weights == {
        "urgency": 12,
        "credential": 25,
        "account_access": 35,
        "remote_app": 30,
        "money_mule": 35,
    }


def test_public_signals_keep_legacy_codes_without_semantic_duplicates() -> None:
    body = analyze(
        "오늘까지 OTP와 통장을 주고 APK 앱 설치 후 원격제어를 허용한 뒤 "
        "입금받고 다시 보내 주세요."
    )
    codes = [signal["code"] for signal in body["signals"]]

    assert len(codes) == len(set(codes))
    assert codes.count("remote_app") == 1
    assert {"urgency", "credential", "account_access", "remote_app", "money_mule"} <= set(
        codes
    )
    assert not {
        "urgency_pressure",
        "credential_request",
        "account_access_request",
        "app_install_request",
        "remote_control_request",
        "receive_and_forward_money",
    } & set(codes)


def test_new_signal_concepts_keep_canonical_public_codes() -> None:
    body = analyze(
        "경찰 수사관입니다. 저금리 대출 확인을 위해 안전계좌로 송금해 주세요."
    )
    codes = {signal["code"] for signal in body["signals"]}

    assert {"authority_impersonation", "loan_policy_offer", "money_transfer_request"} <= codes


def test_action_source_ids_are_related_and_valid() -> None:
    body = analyze("APK 앱 설치 후 입금받은 돈을 재송금해 주세요.")
    returned_sources = {
        source["source_id"]: source for source in body["official_sources"]
    }

    for action in body["actions"]:
        assert action["source_ids"]
        for source_id in action["source_ids"]:
            assert source_id in returned_sources
            assert action["code"] in returned_sources[source_id]["supports"]

    referenced_ids = {
        source_id for action in body["actions"] for source_id in action["source_ids"]
    }
    assert set(returned_sources) == referenced_ids


def test_official_source_metadata_is_reviewed_and_unique() -> None:
    sources = list(load_official_sources().values())

    assert len(sources) == 8
    assert len({source.source_id for source in sources}) == len(sources)
    assert len({source.source_url for source in sources}) == len(sources)
    assert {source.source_url for source in sources} == ALLOWED_SOURCE_URLS
    assert {source.retrieved_at for source in sources} == {"2026-08-12"}


def test_existing_response_fields_and_route_are_preserved() -> None:
    body = analyze("긴급 안내입니다.")

    assert {"risk_score", "risk_level", "signals", "scenario", "disclaimer"} <= set(
        body
    )
    assert body["scenario"] == "received_only"
    assert "확정" in body["disclaimer"]
