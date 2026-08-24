import socket

import pytest
from fastapi.testclient import TestClient

from app.domain.fraud.signals import baseline_score, detect_legacy_signals
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

    assert body["risk_score"] == 70
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
    assert body["risk_score"] == 70
    assert body["risk_level"] == "high"
    assert "DO_NOT_SHARE_ACCESS" in action_codes(body)


def test_otp_request_alone_is_not_low_risk() -> None:
    body = analyze("확인을 위해 OTP를 알려 주세요.")

    assert body["risk_score"] == 35
    assert body["risk_level"] == "medium"
    assert [signal["code"] for signal in body["signals"]] == ["credential"]


def test_app_install_and_remote_control() -> None:
    body = analyze("이 APK 앱 설치 후 원격제어를 허용해 주세요.")

    assert body["risk_score"] == 70
    assert body["risk_level"] == "high"
    assert "smishing_malware" in body["fraud_types"]
    assert {"DO_NOT_INSTALL", "CONTACT_KISA_118"} <= action_codes(body)


def test_receive_and_forward_money() -> None:
    body = analyze("계좌로 입금받고 다른 곳으로 다시 보내 주세요.")

    assert body["risk_score"] == 70
    assert body["risk_level"] == "high"
    assert "money_mule_transfer" in body["fraud_types"]
    assert [signal["code"] for signal in body["signals"]] == ["money_mule"]
    assert "DO_NOT_FORWARD_MONEY" in action_codes(body)


def test_card_delivery_claim() -> None:
    body = analyze("신청한 카드가 발급되어 오늘 카드 배송 예정입니다.")

    assert body["risk_score"] == 35
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
    # v1.1 에서 다시 뒤집혔다. **뒤집힌 것은 고립에 대한 판단이 아니라 이
    # 문장이 고립만 말하고 있다는 읽기다.**
    #
    # v0.9 는 "이 문장에는 자칭한 기관도 상품도 없다 - 말하는 사람만 있고
    # 찾아갈 창구가 없다" 고 적었다(held-out v0.8 `fh-627`). 앞부분은 맞고
    # 뒷부분이 틀렸다. 이 문장은 `수사 중인 사안` 이라고 말하고 있고, 수사가
    # 실재한다면 확인할 창구도 실재한다 - 112 와 관할서다. 기관을 자칭하지
    # 않았을 뿐 사건을 말하는 순간 창구가 생긴다(held-out v1.1 `fh-901`).
    #
    # 고립 자체에 대한 v0.9 의 판단은 그대로다. 사건 어휘가 없는 순수 고립
    # 요구는 여전히 아는 연락처로 보내고, 바로 아래 테스트가 그 자리를
    # 지킨다("주변에는 알리지 마시고 저와만 연락하세요").
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


@pytest.mark.parametrize(
    "text",
    [
        # held-out v0.3 `fh-138`. 어휘에 "넘겨" 가 없어 두 회차를 미탐으로 지났다.
        "들어온 돈은 그대로 다른 계좌로 넘겨 주시면 됩니다.",
        # held-out v0.6 `fh-446`. 어휘에는 "빼서 넣어" 가 **붙어** 있었는데 실제
        # 문장은 그 사이에 목적지가 낀다. 붙여 적은 어휘는 아무것도 잡지 못한다.
        "그 돈 빼서 다른 계좌로 넣어 주세요.",
        # 개발셋 `fg-004`. 요구가 문장 다른 곳이 아니라 **동사에 붙어 있다.**
        "조사 협조를 위해 자금을 지정 장소로 옮기세요.",
    ],
)
def test_forwarding_money_is_caught_in_the_forms_that_actually_arrive(
    text: str,
) -> None:
    body = analyze(text)

    assert "money_mule" in [signal["code"] for signal in body["signals"]]
    assert "money_mule_transfer" in body["fraud_types"]


@pytest.mark.parametrize(
    "text",
    [
        # 화자가 제 계좌 사이에서 옮기는 이야기다. held-out v0.7 `fh-545` 가
        # 동결 시점에 오탐이었고, 천장까지 함께 넘었다.
        "월급 들어오면 적금 계좌로 옮겨 놓을게. 이번 달도 자동이체로 걸어 뒀어.",
        "보증금 돌려받으면 대출 상환 계좌로 바로 넣을 예정이야.",
        # 목적어는 돈이지만 시키는 말이 아니다.
        "지난달 관리비 정산 내역입니다. 차액은 다음 달 고지서에 반영됩니다.",
    ],
)
def test_moving_your_own_money_is_not_a_forwarding_demand(text: str) -> None:
    """**재전달을 만드는 것은 동사도 목적어도 아니고 요구다.**

    목적어만 보면 "자동이체" 의 "이체" 하나로 금액 조건이 차고, 제 적금 계좌로
    옮기겠다는 말이 자금 재전달 요구가 된다. 이 어휘를 넓히는 회차에서 조건을
    함께 걸지 않으면 넓힌 만큼 정상 문장을 데려온다.
    """
    body = analyze(text)

    assert "money_mule" not in [signal["code"] for signal in body["signals"]]
    assert body["fraud_types"] == []


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


def test_a_threat_followed_by_a_demand_is_high_without_any_self_claim() -> None:
    """불이익을 예고해 놓고 접근수단을 달라고 하면 자칭이 없어도 high 다.

    재촉은 점수만 올리고 등급 하한을 세우지 않는다. 그래서 요구가 세운
    medium 하나만 남아 등급이 거기서 멈췄다 - 정작 거절하기 가장 어려운
    조합이 그 모양이다.
    """
    body = analyze("즉시 확인하지 않으면 계좌가 압류됩니다. 인증번호를 알려 주셔야 취소됩니다.")

    assert body["risk_level"] == "high"


def test_an_urgent_normal_notice_naming_a_bankbook_stays_low() -> None:
    # 올리기의 값은 천장에서 치러진다. 기한이 급한 정상 안내가 통장·카드를
    # 입에 올리기만 해도 올라가면 이 수정은 손해다.
    body = analyze("오늘까지 서류를 제출하지 않으시면 심사가 자동 취소됩니다. 제출은 홈페이지에서만 받습니다.")

    assert body["fraud_types"] == []
    assert body["risk_level"] == "low"


def test_an_accusation_about_a_bankbook_is_not_a_demand_for_one() -> None:
    """대포통장이 개설되었다는 통보는 통장을 달라는 말이 아니다.

    요구 게이트는 메시지 안 아무 데나 요구가 있으면 열린다. 그래서 뒤에 붙은
    "이체하셔야" 하나로 앞 절의 고발 문구가 요구 대상이 되어 계좌·접근수단
    요구가 하나 더 붙었다. 겁을 주는 문장과 실제로 내놓으라는 문장은 사용자가
    해야 할 일이 다르다 - 앞은 확인, 뒤는 거절이다.
    """
    body = analyze(
        "서울중앙지검 수사관입니다. 귀하 명의로 대포통장이 개설되어 즉시 안전계좌로 이체하셔야 합니다."
    )

    assert "account_access_request" not in body["fraud_types"]
    assert "authority_impersonation" in body["fraud_types"]
    # 좁히기가 등급까지 깎으면 손해다. 고발은 여전히 사기의 표지다.
    assert body["risk_level"] == "high"


def test_a_real_bankbook_demand_from_the_same_sender_keeps_the_type() -> None:
    # 같은 자칭, 같은 낱말. 달라진 것은 통장이 고발 대상인지 요구 대상인지뿐이다.
    # 이 짝이 없으면 위 테스트는 계좌·접근수단 요구를 통째로 없애는 수정도
    # 통과시킨다.
    body = analyze(
        "서울중앙지검 수사관입니다. 수사 협조를 위해 사용 중인 통장과 체크카드를 보내 주십시오."
    )

    assert "account_access_request" in body["fraud_types"]
    assert body["risk_level"] == "high"


def test_a_demand_from_nobody_in_particular_does_not_send_the_user_to_a_desk() -> None:
    """확인 행동은 그 메시지에 창구가 있을 때만 공식 창구를 가리킨다.

    "공식 대표번호로 확인하세요" 를 이름 없는 상대에게 말하면 사용자는 찾을
    수 없는 창구를 뒤지다가 결국 **메시지에 적힌 번호로 건다.** 틀린 행동은
    없는 행동보다 나쁘다.
    """
    body = analyze("확인 절차입니다. 문자로 받으신 인증번호를 저에게 알려 주세요.")

    assert "VERIFY_BY_KNOWN_CONTACT" in action_codes(body)
    assert "VERIFY_OFFICIAL_CHANNEL" not in action_codes(body)


def test_the_same_demand_with_a_named_institution_keeps_the_official_channel() -> None:
    # 같은 요구, 같은 신호. 달라진 것은 자칭 하나뿐이고 확인 창구는 그것을
    # 따라간다. 이 짝이 없으면 위 테스트는 확인 행동을 없애는 수정도 통과시킨다.
    body = analyze("금융감독원 민원조사팀입니다. 계좌 안전 조치를 위해 인증번호를 불러 주십시오.")

    assert "VERIFY_OFFICIAL_CHANNEL" in action_codes(body)
    assert "VERIFY_BY_KNOWN_CONTACT" not in action_codes(body)


def test_a_loan_offer_has_an_official_desk_even_without_a_named_lender() -> None:
    # 기관을 자칭하지 않아도 대출·정책자금은 취급 창구를 가리킨다. 여기까지
    # 아는 창구로 돌리면 확인할 수 있는 것을 확인하지 말라고 하는 셈이 된다.
    body = analyze("정부지원 정책자금 대상자로 선정되셨습니다. 보증료 입금 후 실행됩니다.")

    assert "VERIFY_OFFICIAL_CHANNEL" in action_codes(body)


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

    # legacy 가중치는 양쪽 다 0 이다. 그래도 발표되는 점수는 다르다 - 등급을
    # 올린 것이 사용자 상태이지 문장이 아니어도, 등급이 high 면 점수도 high 다.
    assert received["risk_score"] == 0
    assert transferred["risk_score"] == 70
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

    assert body["risk_score"] == 70
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

    assert body["risk_score"] == 35
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
    """v0.8 부터 **채점기를 직접** 부른다.

    이 표가 못 박으려는 것은 `LEGACY_RULES` 의 가중치이지 응답에 실리는
    숫자가 아니었다. 응답 쪽 점수는 이제 등급이 함의하는 띠까지 올라가므로
    (`score_floor_for_level`) API 를 거치면 가중치를 잴 수 없다. 재려던
    것을 그대로 재려면 거치지 않으면 된다.
    """
    signals = detect_legacy_signals(text)

    assert baseline_score(signals) == expected_score
    if expected_code is not None:
        matching = [signal for signal in signals if signal.code == expected_code]
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


# --- 예방 안내문 표지의 자리 (2026-08-23) -----------------------------------


def test_the_auxiliary_verb_marker_does_not_cover_a_whole_word_that_contains_it() -> (
    None
):
    """맨 `드리지 않` 은 보조용언 자리를 넘어가 문장 전체를 눌렀다.

    이 표지가 있으면 그 절은 요구를 공급하지 못하고, 다른 표지가 없으면 메시지
    전체가 예방 안내문으로 억제된다. 그런데 `말씀드리다`·`건드리다` 는 보조용언
    구성이 아니라 한 낱말이다. **읽는 사람에게** 말하지 말라는 요구가 보내는
    쪽의 서술로 읽혔다 - held-out v0.7 `fh-523` 이 그렇게 미탐이었고, held-out
    v0.6 `fh-455`(사기)도 `건드리지 않` 하나로 같은 억제를 받고 있었다.
    """
    hidden_demand = analyze("부모님께는 말씀드리지 않는 게 좋겠습니다. 저와만 연락하세요.")
    assert "secrecy_isolation" in {s["code"] for s in hidden_demand["signals"]}
    assert hidden_demand["fraud_types"] == ["isolation_coercion"]

    untouched = analyze("계약 조건은 건드리지 않고 그대로 갱신됩니다.")
    assert untouched["fraud_types"] == []


def test_a_real_prevention_notice_using_the_auxiliary_verb_stays_suppressed() -> None:
    """좁히기의 값은 이쪽에서 치러진다.

    억제를 풀면 진짜 예방 안내문이 사기로 올라간다. `입력해 드리지 않습니다` 는
    보조용언 구성이고, 그 절에 `입력` 이라는 요구 표지가 들어 있어서 억제가
    풀리는 순간 기관 사칭 + 인증정보 요구로 판정된다.
    """
    for text in (
        "국민은행입니다. 저희 직원은 어떤 경우에도 OTP를 대신 입력해 드리지 않습니다.",
        "저희는 고객님 계좌에서 먼저 출금해 드리지 않습니다.",
    ):
        body = analyze(text)
        assert body["fraud_types"] == [], text
        assert body["risk_level"] == "low", text


# --- 계좌 권한을 넘기라는 요구 (2026-08-23) ---------------------------------


def test_handing_account_authority_to_a_person_is_an_access_demand() -> None:
    """두 게이트가 서로를 기다리면 신호는 하나도 켜지지 않는다.

    held-out v0.7 `fh-508` 은 `세무서` 자칭과 계좌 권한 요구가 함께 있는데도
    빈 응답이었다. 자칭 어휘는 **다른 민감 요구가 있어야** 켜지는 조건부이고,
    계좌 권한 요구는 어느 어휘에도 없었다. 조건부 어휘를 무조건 켜는 쪽으로
    옮기는 것이 아니라, 빠져 있던 요구를 어휘에 넣는 것이 답이다.
    """
    delegated = analyze(
        "세무서 조사과입니다. 소명 자료 확인을 위해 계좌 접근 권한을 담당자에게 위임해 주셔야 합니다."
    )
    codes = {signal["code"] for signal in delegated["signals"]}
    assert {"authority_impersonation", "account_access"} <= codes
    assert delegated["risk_level"] == "high"

    # 수령자 표현은 하나가 아니다.
    for text in (
        "인터넷뱅킹 이용 권한을 저희 쪽으로 위임해 주세요.",
        "법인 계좌 조회 권한을 잠시 저에게 양도해 주시면 제가 정리하겠습니다.",
        "계좌 접근 권한을 조사관에게 넘겨 주셔야 합니다.",
    ):
        assert "account_access" in {
            signal["code"] for signal in analyze(text)["signals"]
        }, text


def test_delegating_account_authority_is_a_real_product_and_stays_quiet() -> None:
    """넓히기의 값은 여기서 치러진다. 위임은 실재하는 제도다.

    갈리는 자리는 위임이라는 낱말이 아니라 **수령자를 지목한 요구**다. 아래
    문장에는 계좌도 권한도 위임도 다 있고, 넘겨받을 사람만 없다.
    """
    for text in (
        "국민은행 안내입니다. 계좌 접근 권한 위임은 문자로 처리되지 않으며 반드시 영업점에서 위임장을 제출하셔야 합니다.",
        "법인 계좌 조회 권한을 세무 대리인에게 위임하는 절차는 홈택스에서 직접 진행하실 수 있습니다.",
        "이체 한도 변경 권한은 본인만 설정하실 수 있으며 타인에게 위임되지 않습니다.",
        "그룹웨어 관리자 권한은 김 대리에게 위임해 두었습니다. 휴가 동안 결재 부탁드려요.",
    ):
        body = analyze(text)
        assert body["fraud_types"] == [], text
        assert body["risk_level"] == "low", text


# --- 받은 돈을 다시 보내라는 요구 (2026-08-23) ------------------------------


def test_forwarding_is_caught_when_the_money_word_sits_in_a_closed_clause() -> None:
    """사기 문자는 받은 사실을 과거형으로 적고 요구만 현재형으로 남긴다.

    held-out v0.7 `fh-542`("거래처 대금이 착오 입금되었습니다. … 회수 계좌로
    돌려보내 주셔야 합니다")에서 돈을 가리키는 말은 전부 완료 보고 절에
    있었다. 완료 보고 절은 요구도 요구의 대상도 공급하지 않으므로, 열린 절에
    남은 단서는 **목적지로 지목된 계좌** 하나뿐이다.
    """
    for text in (
        "거래처 대금이 착오 입금되었습니다. 회수 전용 계좌로 돌려보내 주셔야 처리가 완료됩니다.",
        "저희 회사 정산금이 고객님 계좌로 잘못 입금되었습니다. 확인하시고 아래 지정 계좌로 옮겨 주세요.",
        "받으신 금액 중 절반은 아래 계좌로 나눠 보내 주세요.",
    ):
        body = analyze(text, state="received_unknown_money")
        assert "money_mule" in {s["code"] for s in body["signals"]}, text
        assert body["fraud_types"] == ["money_mule_transfer"], text


def test_the_destination_account_replaces_the_money_word_it_does_not_add_to_it() -> (
    None
):
    # 목적지 계좌를 대안으로 둔 값이다. `계좌` 만 보면 "제 계좌가 바뀌었어요"
    # 가 걸리므로 조사까지 함께 본다. 아래 두 문장에는 목적지 계좌도 있고
    # 요구도 있지만 재전달 동사가 없다.
    for text in (
        "제 주거래 계좌가 바뀌었어요. 앞으로는 새 계좌로 보내 주세요.",
        "정산금 지급일 안내입니다. 계좌 정보가 변경되신 분은 담당자에게 알려 주세요.",
    ):
        assert analyze(text)["fraud_types"] == [], text


def test_a_verb_inside_a_prohibition_is_not_a_demand() -> None:
    """같은 문장이 그 행동을 하지 말라고 하고 있다.

    "나눠 보내" 를 어휘에 넣자 held-out v0.8 `fh-625` 가 자금 재전달 요구로
    뒤집혔다. 어휘를 어미까지 붙여 좁히면 다음 어미로 다시 뚫린다. 금지형은
    어휘의 문제가 아니라 자리의 문제다.
    """
    for text in (
        "회비는 나눠 보내지 마시고 총무 계좌로 한 번에 보내 주세요.",
        "돈은 절대 다른 계좌로 옮겨 주지 말고 은행에 먼저 문의하세요.",
    ):
        assert analyze(text)["fraud_types"] == [], text

    # 금지형만 뺀다. 조건절 부정은 협박이고 요구의 다른 얼굴이라 살아 있어야 한다.
    threat = analyze(
        "입금된 금액을 오늘까지 아래 계좌로 옮겨 주지 않으면 형사 고발됩니다.",
        state="received_unknown_money",
    )
    assert threat["risk_level"] == "high"


# --- 지검 자칭 (2026-08-23) --------------------------------------------------


def test_a_district_prosecutors_office_can_be_impersonated_too() -> None:
    # held-out v0.7 `fh-561`("서울중앙지검입니다 …")이 낱말 하나로 미탐이었다.
    # 무조건 켜는 목록에 `검찰` 이 있지만 `지검` 은 그 부분 문자열이 아니다.
    body = analyze(
        "서울남부지검 수사팀입니다. 귀하 명의 계좌가 대포통장으로 등록되어 안전계좌로 자금을 이체하셔야 합니다."
    )
    assert "authority_impersonation" in {s["code"] for s in body["signals"]}
    assert body["risk_level"] == "high"


def test_a_place_name_in_the_news_is_not_a_self_claim() -> None:
    """`지검` 을 무조건 켜는 층에 넣지 않은 이유다.

    `검찰` 은 자칭에 거의 전용으로 쓰이지만 `지검` 은 지명이 붙은 고유명사라
    일상 대화에 그대로 나온다. 민감한 요구가 함께 있을 때만 자칭이다.
    """
    for text in (
        "뉴스 봤어? 서울중앙지검에서 그 사건 수사 결과 발표했대.",
        "지검 앞에서 만나기로 했어. 2시까지 갈게.",
    ):
        body = analyze(text)
        assert body["signals"] == [], text
        assert body["risk_level"] == "low", text


# --- 높임 명령형 송금 요구 (2026-08-23) --------------------------------------


def test_an_honorific_imperative_is_still_a_transfer_demand() -> None:
    """어미 하나로 유형이 통째로 비었다.

    held-out v0.7 `fh-562`("지급 전 수수료로 먼저 입금하셔야 합니다")는
    선입금 표지를 다 갖췄는데도 유형이 서지 못했다. `advance_fee_demand` 는
    `money_transfer_request` 를 전제로 하고, 그 어휘에는 `입금해` 만 있었다.
    """
    body = analyze("당첨을 축하드립니다. 지급 전 제세공과금 10%를 먼저 입금하셔야 절차가 진행됩니다.")
    assert "money_transfer_request" in {s["code"] for s in body["signals"]}
    assert body["fraud_types"] == ["advance_fee_demand"]

    for text in (
        "나머지 수익금을 출금하시려면 수수료를 먼저 송금하셔야 합니다.",
        "열람 예치금을 먼저 이체하셔야 처리됩니다.",
    ):
        assert "advance_fee_demand" in analyze(text)["fraud_types"], text


def test_a_legitimate_invoice_uses_the_same_ending_and_stays_below_high() -> None:
    """넓히기의 값은 여기서 치러진다. 정상 청구도 계좌와 기한을 말한다.

    등급이 medium 까지 오르는 것은 이 회차가 감수한 값이다 - 송금 요구는
    실제로 있고, 그것이 사기라는 말은 아니다. 넘으면 안 되는 선은 high 와
    사기 유형이다.
    """
    body = analyze(
        "관리사무소입니다. 8월 관리비는 25일까지 아래 계좌로 입금하셔야 연체료가 발생하지 않습니다."
    )
    assert body["fraud_types"] == []
    assert body["risk_level"] != "high"

    # 과거형은 요구가 아니라 확인이다.
    confirmation = analyze("어제 입금하셨는지 확인 부탁드립니다.")
    assert "money_transfer_request" not in {s["code"] for s in confirmation["signals"]}


# --- 점수와 등급이 같은 것을 가리킨다 (2026-08-23) ---------------------------


def test_a_high_verdict_never_ships_with_a_zero_score() -> None:
    """원래 결함이다.

    점수는 `LEGACY_RULES` 의 가중치만 더하고, 등급은 canonical 신호와 사용자
    상태까지 본다. 그래서 **화면에 "높음" 과 "0점" 이 나란히** 실렸다. 읽는
    사람은 둘 중 어느 쪽을 믿어야 하는지 알 수 없고, 둘 다 못 믿게 된다.

    등급을 점수에서 다시 계산하는 방향은 택하지 않았다. 그러면 여섯 회차에
    걸쳐 쌓은 canonical 판단과 상태 하한이 전부 legacy 가중치 표로 되돌아간다.
    """
    body = analyze("짧은 안내입니다.", "transferred_money")

    assert body["risk_level"] == "high"
    assert body["risk_score"] >= 70


def test_the_published_score_always_sits_in_the_band_its_level_names() -> None:
    """불변식. 어느 쪽으로도 어긋나지 않는다.

    `determine_risk_level` 은 점수 띠에서 출발해 **올리기만** 한다. 그래서
    원래도 `점수 띠 <= 등급` 은 성립했다 - 어긋나는 방향은 한쪽뿐이었다.
    바닥을 깔면 `등급 <= 점수 띠` 도 성립해서 둘이 정확히 같아진다.
    """
    corpus = [
        ("내일 오전 10시에 회의실에서 만나요.", "received_only"),
        ("오늘까지 처리해 주세요.", "received_only"),
        ("확인을 위해 OTP를 알려 주세요.", "received_only"),
        ("검찰 수사관입니다. 지금 바로 안전계좌로 송금해 주세요.", "received_only"),
        ("신청한 카드가 발급되어 오늘 카드 배송 예정입니다.", "received_only"),
        ("짧은 안내입니다.", "installed_app"),
        (
            "오늘까지 인증번호와 체크카드를 주고 앱 설치 후 입금받고 다시 보내 주세요.",
            "shared_account_access",
        ),
    ]

    def band(score: int) -> str:
        if score >= 70:
            return "high"
        return "medium" if score >= 35 else "low"

    for text, state in corpus:
        body = analyze(text, state)
        assert band(body["risk_score"]) == body["risk_level"], (text, state)


def test_flooring_the_score_never_moves_the_level() -> None:
    """바닥은 등급을 정한 **뒤에** 깔린다. 자기 자신을 근거로 삼지 않는다.

    순서가 뒤집히면 점수 12 짜리 문장이 상태 때문에 high 가 되고, 올라간 70 이
    다음 계산에서 다시 high 를 만드는 순환이 생긴다. 지금은 등급이 상태와
    신호만으로 정해지므로 legacy 가중치가 0 이든 100 이든 같은 등급이 나온다.
    """
    quiet = analyze("짧은 안내입니다.", "transferred_money")
    loud = analyze("검찰 수사관입니다. 지금 바로 안전계좌로 송금해 주세요.", "transferred_money")

    assert quiet["risk_level"] == loud["risk_level"] == "high"
    # legacy 가중치는 0 과 12 로 다르지만 둘 다 바닥 아래라 같은 70 이 된다.
    assert quiet["risk_score"] == loud["risk_score"] == 70


def test_a_score_above_the_floor_is_left_alone() -> None:
    body = analyze("오늘까지 인증번호와 체크카드를 주고 앱 설치 후 입금받고 다시 보내 주세요.")

    assert body["risk_level"] == "high"
    assert body["risk_score"] == 100


# --- 목적지 계좌는 혼자서 돈 이야기를 만들지 않는다 (2026-08-23) --------------


def test_a_destination_account_alone_does_not_make_it_a_forwarding_demand() -> None:
    """안전계좌 이체 요구는 자금 재전달 요구가 아니다.

    받은 돈이 없다. 피해자 제 돈을 옮기라는 요구이고, 이름이 `money_mule` 로
    바뀌면 사용자에게 나가는 행동도 "받은 돈을 보내지 마세요" 로 어긋난다.
    held-out v0.5 `fh-317` 이 목적지 어휘를 들인 뒤 그렇게 뒤집혔다.
    """
    body = analyze("검찰 수사 때문에 계좌가 묶였어. 일단 안전계좌로 옮겨 놔. 끝나면 돌려받는 거니까 걱정 안 해도 돼.")

    codes = {signal["code"] for signal in body["signals"]}
    assert "money_transfer_request" in codes
    assert "money_mule" not in codes
    assert "money_mule_transfer" not in body["fraud_types"]
    assert body["risk_level"] == "high"


def test_a_destination_still_counts_when_the_money_word_was_filtered_out() -> None:
    """넓힌 자리는 그대로다. 좁힌 것은 **만들어 내는 것**뿐이다.

    돈을 가리키는 말이 완료 보고 절에 들어가 걸러지면 열린 절에는 목적지만
    남는다. 그 절이 걸러졌을 뿐 메시지에는 남아 있으므로 조건은 찬다.
    """
    body = analyze("거래처 대금이 착오 입금되었습니다. 회수 계좌로 돌려보내 주셔야 합니다.")

    assert "money_mule" in {signal["code"] for signal in body["signals"]}
    assert "money_mule_transfer" in body["fraud_types"]


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("shared_personal_info", "DO_NOT_SHARE_ACCESS"),
        ("shared_account_access", "DO_NOT_SHARE_ACCESS"),
        ("installed_app", "DO_NOT_INSTALL"),
        ("transferred_money", "DO_NOT_FORWARD_MONEY"),
    ],
)
def test_the_state_repeats_the_prevention_it_had_only_for_two_states(
    state: str, expected: str
) -> None:
    """**이미 한 번 넘긴 사람이 가장 다시 넘기기 쉬운 사람이다.**

    `clicked_link` 는 `DO_NOT_CLICK` 을, `received_unknown_money` 는
    `DO_NOT_FORWARD_MONEY` 를 냈는데 나머지 네 상태에는 예방 행동이 하나도
    없었다. 사기는 한 번으로 끝나지 않고 같은 요구를 다시 하는데, 두 번째
    요구를 막는 말이 이미 당한 사람에게만 빠져 있었다. held-out v0.2
    `fh-021` 이 여섯 회차 전에 이 자리를 지나갔다.
    """
    body = analyze("검찰청 첨단범죄수사부입니다. 접수 확인되었고 나머지는 내부 절차로 진행됩니다.", state)

    assert expected in action_codes(body)


@pytest.mark.parametrize(
    ("text", "state"),
    [
        # 급여 계좌를 알려 준 일이 사기인 것은 아니다.
        ("알려 주신 급여이체 계좌로 4월분부터 지급됩니다.", "shared_account_access"),
        # 송금은 대부분 정상이다.
        ("이체가 정상 처리되었습니다. 수취인 확인 후 입금까지 최대 10분 소요됩니다.", "transferred_money"),
        # 회사가 시킨 보안 앱 설치.
        ("사내 보안 정책에 따라 업무용 단말에 보안 앱 설치가 완료되었습니다.", "installed_app"),
    ],
)
def test_a_state_alone_never_emits_a_prevention_action(text: str, state: str) -> None:
    """**상태는 신호를 대신하지 않는다.**

    상태만으로 예방 행동을 켜면 위 문장들이 전부 경고를 받는다. 이 값을
    치르는 자리를 held-out v1.1 이 따로 만들어 두었다(`fh-969`·`fh-974`·
    `fh-975`). 등급은 상태의 몫으로 그대로 올라가되, 행동은 메시지에
    위험 신호가 켜졌을 때만 붙는다.
    """
    body = analyze(text, state)

    assert body["signals"] == []
    assert body["fraud_types"] == []
    assert not {
        "DO_NOT_SHARE_ACCESS",
        "DO_NOT_INSTALL",
        "DO_NOT_FORWARD_MONEY",
    } & action_codes(body)


@pytest.mark.parametrize(
    "text",
    [
        # 결제 승인. 창구는 카드 뒷면 번호다.
        (
            "[Web발신] 해외가맹점 결제 47만원 승인되었습니다. "
            "본인이 아닐 경우 즉시 취소하세요 http://bit.ly/pay-cx9"
        ),
        # 환급. 창구는 홈택스다.
        "종합소득세 환급금 조회 결과를 안내드립니다. 환급 계좌 등록은 cutt.ly/tax-rf2 에서 하세요.",
        # 창구 이름을 **막으려고** 부른다. 이름이 불린 이상 그리로 갈 수 있다.
        "정부24 는 점검 중이라 신청이 되지 않습니다. 아래 주소에서 진행해 주세요. https://cutt.ly/gov-24",
    ],
)
def test_an_event_names_a_counter_even_when_no_institution_is_claimed(
    text: str,
) -> None:
    """**창구를 가리키는 것은 기관 자칭만이 아니다.**

    사기 문자의 절반은 자기가 누구인지 말하지 않고 무슨 일이 일어났는지만
    말한다. 그래도 읽는 사람이 찾아갈 창구는 명확하다 - 카드 뒷면 번호,
    홈택스, 112 다. 창구가 없다고 판단하면 폴백이 아는 연락처를 내므로
    미탐 하나가 **틀린 행동 하나**를 함께 낸다(held-out v1.1 `fh-903`·
    `fh-905`·`fh-921`).
    """
    body = analyze(text)

    assert "VERIFY_OFFICIAL_CHANNEL" in action_codes(body)
    assert "VERIFY_BY_KNOWN_CONTACT" not in action_codes(body)


@pytest.mark.parametrize(
    "text",
    [
        # 예방 안내문은 말리려고 그 어휘를 입에 올린다.
        "세무조사 사전통지서는 우편으로만 발송됩니다. 전화로 자료를 요구하는 경우 관할 세무서에 확인해 주세요.",
        # 승인 알림은 하루에도 여러 번 온다.
        "출금 승인 알림: 03/14 09:10 자동이체 통신요금 42,900원",
        # 지원금 안내가 스스로 창구를 말하고 있다.
        "청년내일저축계좌 지원금 신청은 복지로 또는 가까운 주민센터에서 가능합니다.",
    ],
)
def test_an_event_word_alone_never_adds_a_verification_action(text: str) -> None:
    """사건 어휘는 등급을 올리지 않고, 신호가 없으면 행동도 내지 않는다.

    **넓히기의 값은 넓히려는 바로 그 어형을 정상적으로 쓰는 문장이 치른다.**
    승인 알림에 창구 안내가 붙으면 사용자는 곧 모든 안내를 무시하게 된다
    (held-out v1.1 `fh-976`~`fh-978`).
    """
    body = analyze(text)

    assert body["risk_level"] == "low"
    assert not {"VERIFY_OFFICIAL_CHANNEL", "VERIFY_BY_KNOWN_CONTACT"} & action_codes(
        body
    )


@pytest.mark.parametrize(
    "text",
    [
        "가족에게 말씀하시면 안 됩니다. 지금은 저와만 진행하시는 편이 안전합니다.",
        "이 내용은 직원분들께 공유하시면 안 됩니다. 대표님만 알고 계셔야 합니다.",
        "지금 상황은 주변에 알리시면 안 되고, 저와만 확인하시면 됩니다.",
        "부모님께 상의하시면 안 됩니다. 절차만 복잡해지고 기한을 넘기게 됩니다.",
    ],
)
def test_isolation_is_caught_when_the_prohibition_is_periphrastic(text: str) -> None:
    """`-지 마세요` 만 보던 자리에 `-(으)시면 안 됩니다` 를 더한다.

    어휘를 더 적지 않는다. `가족에게 말`, `직원분들께 공유` 를 목록에 넣으면
    다음 회차에 `가족분들께 말씀`, `동료에게 공유` 가 그대로 남는다. 고립의
    **대상**과 **금지**를 따로 세우고 둘이 한 절 안에 있을 때만 켠다.
    """
    body = analyze(text)

    assert "secrecy_isolation" in {signal["code"] for signal in body["signals"]}
    assert "isolation_coercion" in body["fraud_types"]


@pytest.mark.parametrize(
    "text",
    [
        # held-out v0.9 `fh-741`. 어형이 위 네 문장과 글자까지 겹친다.
        "고객센터입니다. 인증번호는 저희를 포함해 누구에게도 알려 주시면 안 됩니다.",
        "비밀번호는 은행 직원에게도 알려 주시면 안 됩니다. 은행은 절대 묻지 않습니다.",
        # 대상이 고립의 대상이 아니다.
        "가족 명의로는 신청하시면 안 됩니다. 본인 명의로만 접수됩니다.",
        # 금지가 없다.
        "이 지침은 직원분들께도 공유하셔야 합니다.",
        "부모님과 상의하신 뒤 결정하시는 것을 권해 드립니다.",
    ],
)
def test_a_security_advisory_is_not_an_isolation_demand(text: str) -> None:
    """**금지의 대상이 읽는 사람이 쥔 비밀이면 고립이 아니라 보안 안내다.**

    고립은 **이 대화 자체**를 말하지 말라고 하고, 보안 안내는 읽는 사람이
    이미 쥔 비밀을 말하지 말라고 한다. 앞의 것은 제3자 확인을 막고, 뒤의
    것은 제3자 확인과 아무 상관이 없다.
    """
    body = analyze(text)

    assert "secrecy_isolation" not in {signal["code"] for signal in body["signals"]}
    assert body["fraud_types"] == []


@pytest.mark.parametrize(
    "text",
    [
        # held-out v1.2 `fh-1001`. 경찰청이 실제로 대는 창구는 이파인이다.
        "경찰청 교통민원 안내입니다. 과태료 사전통지서가 우편으로 발송되었습니다. "
        "이의신청은 이파인에서 하실 수 있습니다.",
        # `fh-1002`. 검찰청은 형사사법포털을 댄다.
        "지방검찰청 사건과입니다. 접수하신 고소 건에 사건번호가 부여되었습니다. "
        "진행 상황은 형사사법포털에서 조회하십시오.",
        # `fh-1006`. 법원은 민원실을 댄다.
        "법원 집행관사무소 안내입니다. 부동산 현황조사 일정이 확정되었습니다. "
        "자세한 사항은 관할 법원 민원실로 문의하십시오.",
        # `fh-1005`. 이름이 아니라 종류를 대도 창구는 창구다.
        "관할 경찰서입니다. 접수하신 사건의 참고인 조사 일정을 안내드립니다. "
        "일정 조정이 필요하시면 경찰서 대표번호로 연락 주십시오.",
        # held-out v1.1 `fh-942`. 같은 결함이 한 회차 전에 이미 지나갔다.
        "경찰청입니다. 접수하신 사건의 담당 수사관이 배정되었습니다. "
        "진행 상황은 경찰민원포털에서 조회하실 수 있습니다.",
    ],
)
def test_an_institution_that_names_a_reachable_counter_is_not_impersonation(
    text: str,
) -> None:
    """**진짜 기관은 읽는 사람이 혼자 갈 수 있는 창구를 준다.**

    자칭 무조건 층은 기관명이 나오기만 하면 켜졌다. 그래서 경찰청·검찰청·
    법원이 실제로 보내는 통지문이 전부 사칭으로 읽혔다 - held-out v1.2 동결
    시점 오탐 열 건 중 여덟 건이 이 자리다.

    갈리는 것은 기관명이 아니라 창구다. 사칭은 창구를 댈 수 없다. 대는 순간
    읽는 사람이 거기로 가서 거짓이 드러나기 때문이다.
    """
    body = analyze(text)

    assert "authority_impersonation" not in {
        signal["code"] for signal in body["signals"]
    }
    assert body["fraud_types"] == []
    assert "STOP_CONTACT" not in action_codes(body)


@pytest.mark.parametrize(
    "text",
    [
        # held-out v1.2 `fh-1049`. 진짜 창구를 밀어내려고만 부른다.
        "홈택스 말고 저희 전용 시스템으로만 신고가 가능합니다.",
        # `fh-1051`. 창구 이름이 있어도 닫아 두면 창구가 아니다.
        "1332는 지금 연결이 안 되니 안내드린 직통 번호로만 연락 주십시오.",
        # `fh-1052`. `공식 홈페이지` 는 예방 안내문의 표지이기도 하다.
        "공식 홈페이지에는 아직 반영되지 않은 건입니다. 저희 쪽 확인이 유일한 방법입니다.",
        # `fh-1050`. 창구 어휘와 조사와 동사를 모두 갖췄지만 방향이 반대다.
        "은행 창구에서는 처리되지 않는 건이라 저희 담당자를 통해서만 진행됩니다.",
    ],
)
def test_naming_an_official_counter_only_to_close_it_is_not_a_counter(text: str) -> None:
    """**창구를 대는 것과 창구를 닫는 것은 반대 방향이다.**

    창구 이름은 억제의 표지다. 그 표지를 그대로 갖추고 부정만 덧붙이는
    어형이 실제로 있고, 억제 규칙을 노리는 가장 싼 우회가 이것이다.
    """
    body = analyze(text)

    assert "secrecy_isolation" in {signal["code"] for signal in body["signals"]}
    assert "isolation_coercion" in body["fraud_types"]


@pytest.mark.parametrize(
    "text",
    [
        # held-out v1.2 `fh-1018`.
        "서울중앙지검 형사부입니다. 귀하 명의 계좌가 범죄에 이용된 정황이 "
        "확인되었습니다. 확인 절차는 이 번호로만 진행됩니다.",
        # `fh-1020`. 창구 어휘가 있어서 창구 안내 절로 세어지던 자리다.
        "국민연금공단입니다. 미납 내역이 확인되어 처리 중입니다. "
        "확인은 저희 담당 창구에서만 가능합니다.",
        # `fh-1021`.
        "근로복지공단 급여팀입니다. 신청하신 건이 보류되었습니다. "
        "사유는 담당자가 유선으로만 안내드립니다.",
        # `fh-1022`·`fh-1053`. 다른 창구를 통째로 막는 쪽.
        "병무청입니다. 병역 관련 확인 사항이 있어 연락드렸습니다. "
        "다른 기관에는 문의하지 마시고 회신 부탁드립니다.",
        "설치하신 앱의 상담창으로만 문의가 가능합니다. 다른 경로는 이용하지 마십시오.",
    ],
)
def test_narrowing_the_counter_to_the_speaker_is_an_isolation_demand(text: str) -> None:
    """**창구의 독점.** 고립의 나머지 절반은 어디로 가지 말라는 쪽이다.

    전 어휘는 `저와만 연락`·`통화를 끊지` 같은 어형 몇 개뿐이었다. 실제
    어형은 훨씬 흔한 자리에 있다 - 화자를 가리키는 말에 배타 조사가 붙는다.
    진짜 기관은 자기를 유일한 통로로 만들지 않는다. 그럴 필요가 없다.
    """
    body = analyze(text)

    assert "secrecy_isolation" in {signal["code"] for signal in body["signals"]}
    assert "isolation_coercion" in body["fraud_types"]


@pytest.mark.parametrize(
    "text",
    [
        # held-out v1.2 `fh-1029`.
        "금융범죄 수사 협조 요청입니다. 조사가 끝날 때까지 이 건을 외부에 알리지 마십시오.",
        # `fh-1030`. 금지가 아니라 불이익 예고 어형이다.
        "계좌 동결 해제 절차가 진행 중입니다. 절차상 외부에 문의하시면 처리가 지연됩니다.",
        # `fh-1032`.
        "명의도용 피해 확인 절차입니다. 보안상 이 통화 내용은 외부에 말씀하지 마십시오.",
        # `fh-1034`.
        "저희가 안내드린 절차는 외부에 유출하지 마시고 지시대로 진행해 주십시오.",
    ],
)
def test_forbidding_disclosure_of_this_contact_itself_is_isolation(text: str) -> None:
    """**금지의 대상이 이 연락 자체이면 고립이다.**

    `외부에` 는 v1.0 부터 고립 어휘에서 일부러 빼 두었다. 사내 공지의 대외비
    문구가 그 어형이기 때문이다(`fh-865`). 그래서 반대쪽도 통째로 비어 있었다.
    어휘가 아니라 대상으로 가른다.
    """
    body = analyze(text)

    assert "secrecy_isolation" in {signal["code"] for signal in body["signals"]}
    assert "isolation_coercion" in body["fraud_types"]


@pytest.mark.parametrize(
    "text",
    [
        # held-out v1.2 `fh-1023`~`fh-1027`. 금지의 대상이 읽는 사람이 쥔 것이다.
        "내년도 조직개편 초안 공유드립니다. 확정 전이라 외부에 알리지 말아 주세요.",
        "채용 최종 결과는 발표일까지 대외비입니다. 합격 사실을 외부에 알리지 마시고 기다려 주십시오.",
        "고객사와의 계약 조건은 비밀유지계약 대상입니다. 협의 내용을 외부에 공유하지 마십시오.",
        "연구 참여자 정보는 연구윤리 규정상 외부에 공개할 수 없습니다. 문의는 연구책임자에게 해 주세요.",
        "사내 감사가 진행 중입니다. 감사 종료 시까지 관련 내용을 외부에 말하지 말아 주세요.",
        # `fh-1028`. 전칭 금지를 갖췄지만 남겨 두는 집단이 있다.
        "인사 발표 전까지 팀원들 외에는 아무에게도 말하지 말아 주세요.",
        # held-out v0.7 `fh-535`. 금지가 아니라 보장이다.
        "개인정보 보호를 위해 상담 내용은 외부에 공개되지 않습니다. 녹취는 본인 요청 시에만 제공됩니다.",
    ],
)
def test_ordinary_confidentiality_is_still_not_an_isolation_demand(text: str) -> None:
    """넓히기의 값은 정상 문장이 치른다. 이 일곱 자리가 그 값이다.

    `외부에` 를 고립 쪽으로 열면 사내 공지가 무너지고, 어미를 열면 "공개되지
    않습니다" 같은 보장 서술이 금지로 읽힌다. 고립은 남겨 두는 집단이 없고,
    금지의 대상이 이 연락 자체이며, 어미가 금지형이다.
    """
    body = analyze(text)

    assert "secrecy_isolation" not in {signal["code"] for signal in body["signals"]}
    assert body["fraud_types"] == []


@pytest.mark.parametrize(
    ("text", "state"),
    [
        # held-out v1.2 `fh-1059`. 상대가 회사다.
        ("급여 입금 안내: 03/25 2,480,000원 입금되었습니다.", "transferred_money"),
        # `fh-1063`. 상대가 정보보안팀이다.
        (
            "사내 보안 정책에 따라 업무용 단말에 보안 프로그램이 설치되었습니다. "
            "문의는 정보보안팀으로 해 주세요.",
            "installed_app",
        ),
        # `fh-1064`. 상대가 병원이다.
        (
            "진료 예약이 04/05 15:30으로 확정되었습니다. 변경은 예약 페이지에서 하실 수 있습니다.",
            "shared_personal_info",
        ),
        # `fh-1065`. 상대가 거래처다.
        (
            "말씀하신 대금 입금 확인했습니다. 세금계산서는 이번 주 안에 발행해 드리겠습니다.",
            "transferred_money",
        ),
        # `fh-1068`. 상대가 은행이고 계좌 권한 위임은 정상 제도다.
        (
            "가족 계좌 조회 서비스 동의가 등록되었습니다. 해지는 영업점이나 공식 앱에서 하실 수 있습니다.",
            "shared_account_access",
        ),
    ],
)
def test_a_state_alone_never_tells_the_reader_to_cut_contact(
    text: str, state: str
) -> None:
    """**상대를 적으로 부르는 말은 상대에 대한 신호가 있어야 한다.**

    상태 표의 나머지 행동은 읽는 사람 쪽에서 끝난다 - 증거를 남기고, 창구에
    전화하고, 더 넘기지 않는 것이다. `STOP_CONTACT` 만 방향이 반대라서
    상대가 적이라는 판단이 먼저 있어야 하는데, 상태는 읽는 사람이 무엇을
    했는지만 말한다.

    등급은 상태의 몫으로 그대로 올라간다. 재는 것은 등급이 아니라 행동이다.
    """
    body = analyze(text, state)

    assert body["signals"] == []
    assert "STOP_CONTACT" not in action_codes(body)
