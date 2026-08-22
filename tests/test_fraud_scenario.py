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


def test_isolation_demand_now_has_a_name_instead_of_only_a_grade() -> None:
    # `secrecy_isolation` 은 v0.1 부터 켜졌지만 유형 표에 자리가 없었다. 이진
    # 판정이 `bool(fraud_types)` 라서 등급만 medium 으로 오르고 사용자에게는
    # "정상" 이 나갔다 - held-out v0.6 `fh-454` 가 그렇게 미탐이었다.
    body = analyze("수사 중인 사안이라 가족에게도 알리시면 안 됩니다. 통화를 끊지 마시고 지시대로 진행하세요.")

    assert "isolation_coercion" in body["fraud_types"]
    assert body["risk_level"] == "medium"
    assert "STOP_CONTACT" in action_codes(body)
    assert "VERIFY_OFFICIAL_CHANNEL" in action_codes(body)


def test_isolation_stands_on_its_own_without_an_impersonated_institution() -> None:
    # 기관 자칭도 송금 요구도 없는 고립 요구다. `authority_impersonation` 에
    # 합치지 않은 이유가 이것이다 - 사칭이라고 적혀 있지 않은 문장에 사칭이라는
    # 이름을 붙이면 그것이 지어낸 근거가 된다.
    body = analyze("주변에는 알리지 마시고 저와만 연락하세요.")

    assert body["fraud_types"] == ["isolation_coercion"]


@pytest.mark.parametrize(
    "text",
    [
        # 회사 대외비. 화제를 집단 안에 두는 일이지 확인을 막는 일이 아니다.
        "다음 주 인사 발령은 공지 전까지 대외 보안 유지 부탁드립니다.",
        # 계약 NDA.
        "계약 조건은 양사 간 비밀 유지 대상입니다.",
        # 생일 파티. 금지의 대상이 한 사람이다.
        "이번 생일 파티는 비밀로 하자. 당일까지 본인한테는 말하지 마.",
        # 주어가 화자다. 같은 낱말이 주어에 따라 갈린다.
        "이번 건은 제가 혼자 처리할 수 있을 것 같아요.",
        # 통화가 끊기는 것이지 끊지 말라는 요구가 아니다.
        "통화 중에 끊기면 다시 걸게. 지하철이라 신호가 약해.",
    ],
)
def test_ordinary_confidentiality_is_not_an_isolation_demand(text: str) -> None:
    """**비밀 유지는 정상이고, 확인 차단이 신호다.**

    이 유형을 붙이기 전에는 위 문장들이 등급만 medium 으로 올랐다. 유형이
    붙는 순간 같은 오탐이 **사기 판정**이 되므로, 어휘를 함께 바꾸지 않으면
    회사 공지와 생일 파티 문자가 전부 사기가 된다. held-out v0.7 동결 시점
    baseline 이 네 건(`fh-527`·`fh-528`·`fh-530`·`fh-531`)으로 그 값을 미리
    보여 줬다.
    """
    body = analyze(text)

    assert body["fraud_types"] == []
    assert body["risk_level"] == "low"


def test_investment_scheme_from_guarantee_and_private_channel() -> None:
    body = analyze("원금 보장 확정 수익 종목 드립니다. 무료 리딩방에 초대할게요.")

    assert "investment_scheme" in body["fraud_types"]
    assert body["risk_level"] == "medium"
    assert {"guaranteed_return_offer", "private_channel_invite"} <= {
        signal["code"] for signal in body["signals"]
    }
    assert "VERIFY_OFFICIAL_CHANNEL" in action_codes(body)


def test_deposit_protection_notice_is_not_a_guaranteed_return_offer() -> None:
    """예금자보호법상 원금 보장은 사실이다. 같은 문구라도 사기가 아니다."""
    body = analyze("이 상품은 예금자보호법에 따라 5천만원까지 원금 보장이 됩니다.")

    assert body["fraud_types"] == []
    assert body["risk_level"] == "low"


def test_investment_disclosure_negation_does_not_fire() -> None:
    body = analyze("본 펀드는 원금이 보장되지 않으며 손실이 발생할 수 있습니다.")

    assert body["fraud_types"] == []
    assert body["risk_level"] == "low"


def test_victim_self_report_mentioning_a_leading_room_does_not_fire_the_invite() -> None:
    """피해자가 겪은 일을 말하는 것과, 읽는 사람을 방으로 들이는 것은 다르다."""
    body = analyze("리딩방에서 알려준 계좌로 500만원을 보냈는데 연락이 끊겼어요.")

    assert "private_channel_invite" not in {
        signal["code"] for signal in body["signals"]
    }


def test_acquaintance_impersonation_with_a_transfer_demand_is_high_risk() -> None:
    body = analyze("엄마 나야. 폰이 고장나서 새 번호로 연락해. 200만원만 송금해 줘.")

    assert "acquaintance_impersonation" in body["fraud_types"]
    assert body["risk_level"] == "high"
    assert "VERIFY_BY_KNOWN_CONTACT" in action_codes(body)


def test_verify_by_known_contact_carries_an_official_source() -> None:
    body = analyze("아빠야, 액정이 깨져서 이 번호로 저장해 둬.")

    known_contact = next(
        action for action in body["actions"] if action["code"] == "VERIFY_BY_KNOWN_CONTACT"
    )
    assert known_contact["source_ids"]
    assert body["official_sources"]


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


# --- 어휘 확장 v0.2 (2026-08-19) -------------------------------------------
#
# 아래 문장은 전부 골든셋 61건에 없다. 일부러 그렇게 골랐다. 어휘를 넓힌
# 변경은 골든셋 안에서는 좋아 보이면서 밖에서 오탐을 늘리기 쉬운데,
# 골든셋으로 재면 그 손해가 보이지 않는다. 확장 당시 실제로 이 방식으로
# 오탐 여섯 건을 찾아 되돌렸다(`docs/32`).


def test_widened_vocabulary_does_not_fire_on_prevention_and_informational_text() -> (
    None
):
    quiet_messages = (
        # "내려받"·"다운로드"를 어휘에 넣자 그 부정형이 걸리기 시작했다.
        "모르는 사람이 보낸 파일은 절대 내려받지 마세요.",
        "출처가 불분명한 앱은 다운로드하지 마세요.",
        # "이체"를 통째로 넣으면 걸렸을 문장이다. 그래서 지시형만 넣었다.
        "이체 내역을 확인하세요. 모르는 출금이 있으면 은행에 문의하세요.",
        # 기관명을 넓게 넣었다가 되돌린 이유가 이 문장이다.
        "국세청 홈택스에서 연말정산 자료를 조회할 수 있습니다.",
        "건강보험공단 고지서는 공식 누리집에서 확인할 수 있습니다.",
    )

    for text in quiet_messages:
        body = analyze(text)
        assert body["fraud_types"] == [], text


def test_widened_vocabulary_catches_paraphrases_of_the_two_missed_cases() -> None:
    # fg-046 계열: 사법기관 사칭 + 이체 지시. 골든셋 문장과 다른 표현을 쓴다.
    court = analyze("법원 집행관입니다. 오늘까지 안내 계좌로 이체 바랍니다.")
    signals = {signal["code"] for signal in court["signals"]}
    assert "authority_impersonation" in signals
    assert "money_transfer_request" in signals
    assert court["risk_level"] in {"medium", "high"}

    # fg-047 계열: 파일을 받아 실행하라는 지시. 신호는 파일 이름이 아니라
    # "받아서 실행하라"는 요구 자체다.
    install = analyze("본인 확인 설치 파일을 다운로드해 실행해 주세요.")
    assert install["fraud_types"] != []
    assert install["risk_level"] in {"medium", "high"}


def test_official_verification_notice_is_not_treated_as_impersonation() -> None:
    # fg-049 를 닫은 억제 규칙이다. 기관명이 나오지만 독자에게 요구하는 것이
    # "공식 창구에서 직접 확인하라" 뿐이면 사칭 문구가 아니다.
    body = analyze("정부기관 정책자금 안내는 공식 누리집에서 자격을 확인하세요.")
    assert body["signals"] == []
    assert body["fraud_types"] == []

    # 같은 "공식 누리집" 문구가 붙어 있어도 독자에게 돈이나 설치를 요구하면
    # 억제되지 않아야 한다. 억제 규칙이 사기 문구의 위장 수단이 되면 안 된다.
    #
    # fraud_types 가 아니라 신호와 위험 수준으로 확인한다. 이 문장은 송금 요구
    # 하나만 있어서 이름 붙은 사기 유형(조합이 필요하다)에는 해당하지 않는다.
    # 억제 여부를 보려는 것이므로 신호가 살아남았는지가 확인할 지점이다.
    disguised = analyze(
        "공식 누리집 안내입니다. 지원금 수령을 위해 아래 계좌로 이체해 주세요."
    )
    assert "money_transfer_request" in {
        signal["code"] for signal in disguised["signals"]
    }
    assert disguised["risk_level"] != "low"
