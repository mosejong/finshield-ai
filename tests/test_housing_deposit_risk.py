"""전세보증금 위험 점검의 계산·규칙 고정.

이 파일이 지키려는 것은 하나다. **돈이 걸린 계산과 법문에서 나온 날짜가
조용히 바뀌지 않게 하는 것.** 부채비율 한 자리와 대항력 발생일 하루가
사용자에게는 보증금 전액의 차이가 된다.
"""

import re
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.domain.housing.deposit_risk import compute_protection, compute_ratio
from app.domain.housing.policy import (
    ACTION_ORDER,
    ACTION_POLICIES,
    SIGNAL_ACTIONS,
    SIGNAL_LABELS,
    SIGNAL_MINIMUM_RISK,
    STAGE_ACTIONS,
    STAGE_MINIMUM_RISK,
    TAX_ARREARS_RELEVANT_STAGES,
)
from app.main import app
from app.schemas.housing import DepositCheck, DepositRiskRequest, LeaseStage
from app.services.housing_deposit import check_deposit_risk


client = TestClient(app)

ENDPOINT = "/api/v1/housing/deposit-risk"


def _request(**overrides) -> DepositRiskRequest:
    payload = {"stage": LeaseStage.BEFORE_CONTRACT, "deposit_krw": 100_000_000}
    payload.update(overrides)
    return DepositRiskRequest(**payload)


# --- 부채비율 -----------------------------------------------------------


def test_ratio_is_plain_arithmetic() -> None:
    result = compute_ratio(
        deposit_krw=200_000_000,
        property_price_krw=300_000_000,
        senior_lien_krw=60_000_000,
    )
    # (60,000,000 + 200,000,000) / 300,000,000 * 100 = 86.666... -> 86.7
    assert str(result.ratio_percent) == "86.7"
    assert result.band == "high"


def test_ratio_band_boundaries_are_exclusive() -> None:
    """정확히 경계값이면 낮은 쪽 구간에 남는다.

    60.0% 를 'elevated' 로 올리면 경계에 선 사용자가 이유 없이 한 단계 높은
    경고를 받는다. 경계는 '넘었을 때' 움직인다.
    """
    at_sixty = compute_ratio(600, 1000, 0)
    just_over_sixty = compute_ratio(601, 1000, 0)
    at_eighty = compute_ratio(800, 1000, 0)
    just_over_eighty = compute_ratio(801, 1000, 0)

    assert (at_sixty.band, just_over_sixty.band) == ("low", "elevated")
    assert (at_eighty.band, just_over_eighty.band) == ("elevated", "high")


def test_unknown_senior_lien_is_not_treated_as_zero() -> None:
    """선순위를 0 으로 가정하면 등기부를 안 본 사람에게 가장 안전한 숫자가 나온다."""
    guessed = compute_ratio(200_000_000, 300_000_000, 0)
    unknown = compute_ratio(200_000_000, 300_000_000, None)

    assert guessed.band == "elevated"
    assert unknown.ratio_percent is None
    assert unknown.band == "unknown"


def test_unknown_price_yields_unknown_band() -> None:
    assert compute_ratio(100, None, 0).band == "unknown"
    # 0 원짜리 주택은 없다. 0 을 나눗셈에 넣지 않고 unknown 으로 돌린다.
    assert compute_ratio(100, 0, 0).band == "unknown"


# --- 대항력·우선변제권 --------------------------------------------------


def test_opposing_power_starts_the_next_day() -> None:
    """주택임대차보호법 제3조 제1항: 인도와 주민등록을 마친 때 '그 다음 날부터'."""
    reported = date(2026, 3, 2)
    result = compute_protection(
        LeaseStage.MOVED_IN, {DepositCheck.MOVE_IN_REPORTED}, reported
    )

    assert result.opposing_power_effective_on == reported + timedelta(days=1)
    assert result.has_opposing_power_requirements is True


def test_move_in_report_without_occupancy_does_not_meet_requirements() -> None:
    """대항요건은 인도와 주민등록 둘 다다. 잔금 전에는 인도가 없다."""
    result = compute_protection(
        LeaseStage.CONTRACT_SIGNED, {DepositCheck.MOVE_IN_REPORTED}, date(2026, 3, 2)
    )

    assert result.has_opposing_power_requirements is False
    assert result.opposing_power_effective_on is None


def test_priority_repayment_needs_both_requirements() -> None:
    only_confirmed_date = compute_protection(
        LeaseStage.MOVED_IN, {DepositCheck.CONFIRMED_DATE_OBTAINED}, None
    )
    both = compute_protection(
        LeaseStage.MOVED_IN,
        {DepositCheck.MOVE_IN_REPORTED, DepositCheck.CONFIRMED_DATE_OBTAINED},
        None,
    )

    assert only_confirmed_date.has_priority_repayment_requirements is False
    assert both.has_priority_repayment_requirements is True


def test_priority_repayment_is_reported_without_a_date() -> None:
    """요건 충족만 말하고 취득 시점을 날짜로 단정하지 않는다."""
    response = check_deposit_risk(
        _request(
            stage=LeaseStage.MOVED_IN,
            completed_checks=[
                DepositCheck.MOVE_IN_REPORTED,
                DepositCheck.CONFIRMED_DATE_OBTAINED,
            ],
        )
    )

    assert response.protection.has_priority_repayment_requirements is True
    assert not hasattr(response.protection, "priority_repayment_effective_on")


# --- 위험 수준 ----------------------------------------------------------


def test_stage_alone_can_raise_the_level() -> None:
    """신호가 하나도 없어도 미반환 단계는 high 다."""
    response = check_deposit_risk(
        _request(
            stage=LeaseStage.DEPOSIT_UNRETURNED,
            property_price_krw=500_000_000,
            senior_lien_krw=0,
            completed_checks=list(DepositCheck),
        )
    )

    assert response.risk_level == "high"


def test_no_signal_can_lower_the_stage_minimum() -> None:
    for stage, minimum in STAGE_MINIMUM_RISK.items():
        response = check_deposit_risk(
            _request(
                stage=stage,
                deposit_krw=1,
                property_price_krw=1_000_000_000,
                senior_lien_krw=0,
                completed_checks=list(DepositCheck),
            )
        )
        rank = {"low": 0, "medium": 1, "high": 2}
        assert rank[response.risk_level] >= rank[minimum], stage


def test_paid_balance_without_move_in_report_is_high() -> None:
    """잔금은 나갔는데 대항력이 없다. 되돌릴 수 없는 금액에 붙는 신호다."""
    response = check_deposit_risk(
        _request(
            stage=LeaseStage.BALANCE_PAID,
            property_price_krw=500_000_000,
            senior_lien_krw=0,
            completed_checks=[
                DepositCheck.REGISTRY_CHECKED,
                DepositCheck.OWNER_IDENTITY_VERIFIED,
                DepositCheck.DEPOSIT_GUARANTEE_JOINED,
            ],
        )
    )

    assert "opposing_power_missing" in {s.code for s in response.signals}
    assert response.risk_level == "high"


def test_fully_prepared_lease_stays_low() -> None:
    """잘 처리한 사용자를 겁주지 않는다."""
    response = check_deposit_risk(
        _request(
            stage=LeaseStage.MOVED_IN,
            property_price_krw=500_000_000,
            senior_lien_krw=0,
            completed_checks=list(DepositCheck),
        )
    )

    assert response.signals == []
    assert response.risk_level == "low"


# --- 행동 --------------------------------------------------------------


def test_completed_checks_are_not_asked_again() -> None:
    response = check_deposit_risk(
        _request(
            stage=LeaseStage.BEFORE_CONTRACT,
            completed_checks=[DepositCheck.REGISTRY_CHECKED],
        )
    )

    assert "CHECK_REGISTRY" not in {a.code for a in response.actions}


def test_move_in_report_is_listed_before_confirmed_date() -> None:
    """대항요건이 먼저 서야 확정일자가 그 위에 얹힌다. 알파벳순이면 뒤집힌다."""
    response = check_deposit_risk(
        _request(stage=LeaseStage.BALANCE_PAID, property_price_krw=0)
    )
    codes = [a.code for a in response.actions]

    assert codes.index("REPORT_MOVE_IN") < codes.index("GET_CONFIRMED_DATE")


@pytest.mark.parametrize(
    "stage", [LeaseStage.BEFORE_CONTRACT, LeaseStage.DEPOSIT_UNRETURNED]
)
def test_guarantee_is_not_offered_where_it_cannot_be_used(stage: LeaseStage) -> None:
    """계약 전에는 가입할 계약이 없고, 미반환 뒤에는 손실을 되돌리지 못한다."""
    response = check_deposit_risk(
        _request(
            stage=stage,
            property_price_krw=100_000_000,
            senior_lien_krw=99_000_000,
        )
    )

    assert "JOIN_DEPOSIT_GUARANTEE" not in {a.code for a in response.actions}
    assert "deposit_guarantee_absent" not in {s.code for s in response.signals}


# --- 미납 국세·지방세 열람 ----------------------------------------------


@pytest.mark.parametrize("stage", sorted(TAX_ARREARS_RELEVANT_STAGES, key=str))
def test_tax_arrears_lookup_is_offered_while_the_window_is_open(
    stage: LeaseStage,
) -> None:
    response = check_deposit_risk(_request(stage=stage))

    assert "tax_arrears_unchecked" in {s.code for s in response.signals}
    assert "CHECK_TAX_ARREARS" in {a.code for a in response.actions}


@pytest.mark.parametrize(
    "stage",
    [
        LeaseStage.BALANCE_PAID,
        LeaseStage.MOVED_IN,
        LeaseStage.LEASE_ENDING,
        LeaseStage.DEPOSIT_UNRETURNED,
    ],
)
def test_tax_arrears_lookup_is_not_offered_after_the_window_closes(
    stage: LeaseStage,
) -> None:
    """국세징수법 제109조 제1항의 신청 기간은 임대차 기간이 시작하는 날까지다.

    잔금을 치르고 들어간 사람에게 "열람하세요" 라고 하면 할 수 없는 일을
    시키는 것이고, 하지 않았다는 신호는 남은 기간 내내 지워지지 않는다.
    """
    response = check_deposit_risk(_request(stage=stage))

    assert "tax_arrears_unchecked" not in {s.code for s in response.signals}
    assert "CHECK_TAX_ARREARS" not in {a.code for a in response.actions}


def test_completed_tax_arrears_check_clears_both_signal_and_action() -> None:
    response = check_deposit_risk(
        _request(
            stage=LeaseStage.CONTRACT_SIGNED,
            completed_checks=[DepositCheck.TAX_ARREARS_CHECKED],
        )
    )

    assert "tax_arrears_unchecked" not in {s.code for s in response.signals}
    assert "CHECK_TAX_ARREARS" not in {a.code for a in response.actions}


def test_tax_arrears_action_quotes_the_statute_instead_of_a_won_amount() -> None:
    """법문의 '대통령령으로 정하는 금액' 을 우리가 아는 숫자로 바꿔 적지 않는다.

    임대인 동의 없이 열람할 수 있는 보증금 기준액은 시행령이 정하는데, 그
    시행령 조문은 열어 확인하지 못했다. 확인하지 않은 숫자를 적느니 법문의
    표현을 그대로 둔다. 이 서비스가 금액을 지어내면 사용자는 자기 보증금이
    기준 아래라고 믿고 신청을 포기할 수 있다.
    """
    reason = ACTION_POLICIES["CHECK_TAX_ARREARS"].reason

    assert "대통령령으로 정하는 금액" in reason
    assert not re.search(r"\d[\d,]*\s*(억|천만|백만|만\s*원|원)", reason)


def test_tax_arrears_lookup_comes_after_the_registry_checks() -> None:
    """등기부와 소유자를 먼저 본 다음에 세금을 본다. 알파벳순이면 뒤집힌다."""
    response = check_deposit_risk(_request(stage=LeaseStage.BEFORE_CONTRACT))
    codes = [a.code for a in response.actions]

    assert codes.index("VERIFY_OWNER_IDENTITY") < codes.index("CHECK_TAX_ARREARS")


def test_every_action_carries_a_supporting_official_source() -> None:
    """근거 없는 행동은 내보내지 않는다."""
    for stage in LeaseStage:
        response = check_deposit_risk(_request(stage=stage))
        available = {source.source_id for source in response.official_sources}
        assert response.actions
        for action in response.actions:
            assert action.source_ids
            assert set(action.source_ids) <= available


# --- 정책 테이블 정합성 -------------------------------------------------


def test_policy_tables_cover_the_same_signal_codes() -> None:
    assert set(SIGNAL_ACTIONS) == set(SIGNAL_MINIMUM_RISK) == set(SIGNAL_LABELS)


def test_every_referenced_action_code_has_a_policy() -> None:
    referenced = {code for codes in STAGE_ACTIONS.values() for code in codes}
    referenced |= {code for codes in SIGNAL_ACTIONS.values() for code in codes}

    assert referenced <= set(ACTION_POLICIES)
    assert set(ACTION_ORDER) == set(ACTION_POLICIES)


def test_every_stage_has_a_minimum_and_actions() -> None:
    for stage in LeaseStage:
        assert stage in STAGE_MINIMUM_RISK
        assert STAGE_ACTIONS[stage]


# --- API ---------------------------------------------------------------


def test_endpoint_returns_the_full_contract() -> None:
    response = client.post(
        ENDPOINT,
        json={
            "stage": "balance_paid",
            "deposit_krw": 200_000_000,
            "property_price_krw": 300_000_000,
            "senior_lien_krw": 60_000_000,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["risk_level"] == "high"
    assert body["ratio"]["ratio_percent"] == 86.7
    assert body["ratio"]["band_is_service_rule"] is True
    assert body["disclaimer"]
    assert body["official_sources"]


def test_endpoint_does_not_require_a_session() -> None:
    """계약을 앞둔 사람에게 회원가입을 먼저 시키지 않는다."""
    response = client.post(
        ENDPOINT, json={"stage": "before_contract", "deposit_krw": 1}
    )

    assert response.status_code == 200


def test_future_move_in_date_is_rejected() -> None:
    response = client.post(
        ENDPOINT,
        json={
            "stage": "moved_in",
            "deposit_krw": 1,
            "move_in_reported_on": (date.today() + timedelta(days=1)).isoformat(),
        },
    )

    assert response.status_code == 422


def test_negative_amounts_are_rejected() -> None:
    response = client.post(
        ENDPOINT, json={"stage": "moved_in", "deposit_krw": -1}
    )

    assert response.status_code == 422


def test_band_is_never_presented_as_an_official_standard() -> None:
    """구간 이름이 공식 기준으로 읽히면 안 된다. 응답 안에서 부인한다."""
    response = check_deposit_risk(
        _request(
            stage=LeaseStage.MOVED_IN,
            deposit_krw=900,
            property_price_krw=1000,
            senior_lien_krw=0,
        )
    )
    ratio_signal = next(s for s in response.signals if s.code == "high_debt_ratio")

    assert response.ratio.band_is_service_rule is True
    assert "공식 기준이 아니라" in ratio_signal.detail
    assert "공식 기준이 아닙니다" in response.disclaimer
