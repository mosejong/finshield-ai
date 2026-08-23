"""위험 등급 판정의 경계값을 고정한다.

determine_risk_level 은 사용자에게 보이는 등급을 직접 결정하는데,
이전에는 점수 임계값을 70에서 90으로 바꿔도 전체 스위트가 통과했다.
여기서는 임계값·신호 최소등급·조합 규칙·상태 최소등급을 각각 독립적으로 고정한다.
"""

import pytest

from app.domain.fraud.policy import (
    HIGH_RISK_SIGNAL_COMBINATIONS,
    SIGNAL_MINIMUM_RISK,
    STATE_MINIMUM_RISK,
    determine_risk_level,
)
from app.domain.fraud.signals import SENSITIVE_REQUEST_SIGNALS
from app.schemas.analysis import RiskSignal, UserState


def signal(code: str, weight: int = 0) -> RiskSignal:
    return RiskSignal(code=code, label=code, weight=weight)


# 최소등급이 걸려 있지 않은 신호. 점수만으로 등급이 정해지는지 볼 때 쓴다.
NEUTRAL_SIGNAL = signal("card_delivery_claim_unmapped")


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0, "low"),
        (34, "low"),
        (35, "medium"),
        (36, "medium"),
        (69, "medium"),
        (70, "high"),
        (100, "high"),
    ],
)
def test_score_thresholds_are_fixed(score: int, expected: str) -> None:
    """점수 경계 34/35 와 69/70 을 고정한다. 임계값을 옮기면 여기서 실패한다."""
    assert (
        determine_risk_level(score, [NEUTRAL_SIGNAL], UserState.RECEIVED_ONLY)
        == expected
    )


def test_neutral_signal_has_no_minimum_risk() -> None:
    """위 경계 테스트가 성립하려면 대조군 신호에 최소등급이 없어야 한다."""
    assert NEUTRAL_SIGNAL.code not in SIGNAL_MINIMUM_RISK


@pytest.mark.parametrize(("code", "minimum"), sorted(SIGNAL_MINIMUM_RISK.items()))
def test_signal_minimum_risk_raises_low_score(code: str, minimum: str) -> None:
    """점수가 0이어도 신호별 최소등급 아래로는 내려가지 않는다."""
    assert determine_risk_level(0, [signal(code)], UserState.RECEIVED_ONLY) == minimum


def test_signal_minimum_never_lowers_a_higher_score() -> None:
    """medium 최소등급 신호가 high 점수를 끌어내리지 않는다."""
    assert (
        determine_risk_level(70, [signal("suspicious_link")], UserState.RECEIVED_ONLY)
        == "high"
    )


@pytest.mark.parametrize("combination", HIGH_RISK_SIGNAL_COMBINATIONS)
def test_high_risk_combinations_force_high(combination: frozenset[str]) -> None:
    """조합 규칙은 점수가 0이어도 high 로 올린다."""
    signals = [signal(code) for code in sorted(combination)]
    assert determine_risk_level(0, signals, UserState.RECEIVED_ONLY) == "high"


@pytest.mark.parametrize("request_code", sorted(SENSITIVE_REQUEST_SIGNALS))
def test_a_self_claimed_institution_plus_any_handover_demand_is_high(
    request_code: str,
) -> None:
    """**기관은 자칭과 같은 메시지에서 넘겨 달라고 하지 않는다.**

    조합 표를 사례에서 뽑지 않고 `SENSITIVE_REQUEST_SIGNALS` 에서 뽑았다는
    사실을 이 테스트가 지킨다. 저 목록에 민감 요구를 새로 추가하면서 조합
    표를 함께 손대지 않으면 여기서 깨진다 - 목록과 정책이 갈라지는 순간
    "기관이 하지 않는 요구"라는 정의가 두 벌이 된다.
    """
    signals = [signal("authority_impersonation"), signal(request_code)]

    assert determine_risk_level(0, signals, UserState.RECEIVED_ONLY) == "high"


def test_a_self_claimed_institution_alone_is_still_only_medium() -> None:
    """넓힌 것은 조합이지 자칭이 아니다.

    자칭 하나만으로 high 로 올리면 기관 이름이 들어간 정상 안내가 전부
    올라간다. held-out v0.7 의 정상 10건(`fh-511`~`fh-518` 계열)이 그것을
    재고 있고, 천장은 그 자리에 있다.
    """
    assert (
        determine_risk_level(
            0, [signal("authority_impersonation")], UserState.RECEIVED_ONLY
        )
        == "medium"
    )


def test_partial_combination_does_not_force_high() -> None:
    """조합의 일부만 있으면 high 로 올리지 않는다. 조합 규칙이 무의미해지지 않는지 확인한다."""
    assert (
        determine_risk_level(
            0, [signal("authority_impersonation")], UserState.RECEIVED_ONLY
        )
        == "medium"
    )


@pytest.mark.parametrize(("state", "minimum"), sorted(STATE_MINIMUM_RISK.items()))
def test_state_minimum_risk_applies_without_signals(
    state: UserState, minimum: str
) -> None:
    """신호가 하나도 없어도 이미 취한 행동만으로 등급이 올라간다."""
    assert determine_risk_level(0, [], state) == minimum


def test_state_does_not_lower_signal_level() -> None:
    """received_only 상태가 high 점수를 low 로 끌어내리지 않는다."""
    assert (
        determine_risk_level(70, [NEUTRAL_SIGNAL], UserState.RECEIVED_ONLY) == "high"
    )


def test_no_signals_and_no_state_is_low() -> None:
    assert determine_risk_level(0, [], UserState.RECEIVED_ONLY) == "low"


def test_every_state_has_a_minimum_risk() -> None:
    """상태가 추가되면 KeyError 로 죽는 대신 여기서 먼저 드러난다."""
    assert set(STATE_MINIMUM_RISK) == set(UserState)
