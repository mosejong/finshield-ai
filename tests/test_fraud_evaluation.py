import asyncio
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.analysis import (
    Action,
    AnalyzeRequest,
    AnalyzeResponse,
    Persona,
    UserState,
)
from app.services.fraud_analysis import analyze_fraud
from app.services.llm.contract import LlmContractError
from app.services.llm.provider import LlmProvider, LlmUnavailable
from evaluation.fraud_benchmark import (
    FRAUD_TYPES,
    _forbidden_action_avoidance,
    _required_action_coverage,
    check_minimum_quality,
    evaluate_golden_set,
    normalized_dataset_sha256,
)
from app.domain.fraud.policy import STATE_MINIMUM_RISK
from app.domain.fraud.signals import CANONICAL_TO_LEGACY_PUBLIC, SIGNAL_RULES
from evaluation.fraud_golden import (
    ACTION_CODES,
    HOLDOUT_V0_2_PATH,
    HOLDOUT_V0_3_PATH,
    HOLDOUT_V0_4_PATH,
    HOLDOUT_V0_5_PATH,
    HOLDOUT_V0_6_PATH,
    HOLDOUT_V0_7_PATH,
    HOLDOUT_V0_8_PATH,
    HOLDOUT_V0_9_PATH,
    HOLDOUT_V1_0_PATH,
    HOLDOUT_V1_1_PATH,
    HOLDOUT_V1_2_PATH,
    HOLDOUT_V1_3_PATH,
    RISK_RANK,
    SIGNAL_CODES,
    FraudGoldenCase,
    _validate_collection,
    is_held_out,
    load_golden_cases,
    load_holdout_cases,
)
from evaluation.llm_judge import (
    FRAUD_JUDGE_PROMPT,
    JUDGE_RUN_PATH,
    LlmJudgement,
    LlmJudgeRun,
    build_judge_prompt,
    fraud_judge_contract,
    judge_case,
    parse_judgement,
)
from scripts.evaluate_fraud_engine import load_llm_run, measure_asgi_latency, percentile


def test_golden_set_is_synthetic_versioned_and_covers_every_state() -> None:
    cases = load_golden_cases()

    assert len(cases) == 61
    assert all(case.synthetic for case in cases)
    assert len({case.case_id for case in cases}) == len(cases)
    assert {case.state.value for case in cases} == {
        "received_only",
        "clicked_link",
        "shared_personal_info",
        "shared_account_access",
        "installed_app",
        "received_unknown_money",
        "transferred_money",
    }
    state_counts = {
        state: sum(case.state.value == state for case in cases)
        for state in {case.state.value for case in cases}
    }
    assert min(state_counts.values()) >= 3


# --- held-out 셋 ----------------------------------------------------------
#
# 여기에는 **성능 단언이 없다.** 있으면 CI 가 빨개질 때마다 held-out 셋을 보고
# 규칙을 고치게 되고, 그 순간 held-out 이 아니게 된다. 이 셋에 대해 CI 가 지키는
# 것은 라벨 무결성과 개발셋과의 분리뿐이다. 숫자는 사람이 날짜를 붙여 잰다
# (`evaluation/results/fraud-holdout-v0.2.json`).

# v0.2 를 얼릴 때의 분류 표. `advance_fee_demand` 는 그 뒤에 생겼다.
FRAUD_TYPES_AT_HOLDOUT_V0_2_FREEZE = (
    "authority_impersonation",
    "loan_policy_impersonation",
    "account_access_request",
    "money_mule_transfer",
    "smishing_malware",
    "card_delivery_impersonation",
)

# v0.3 을 얼릴 때의 분류 표. `investment_scheme`·`acquaintance_impersonation` 은
# 그 뒤에 생겼다. v0.2 와 같은 이유로 동결 시점 표에 고정한다 - 표가 자랄 때마다
# 얼어붙은 파일이 빨개지면, 고칠 수 있는 것이 동결된 셋뿐이 된다.
FRAUD_TYPES_AT_HOLDOUT_V0_3_FREEZE = (
    "authority_impersonation",
    "loan_policy_impersonation",
    "advance_fee_demand",
    "account_access_request",
    "money_mule_transfer",
    "smishing_malware",
    "card_delivery_impersonation",
)

# v0.4~v0.6 을 얼릴 때의 분류 표. `isolation_coercion` 은 v0.7 에서 선언했다.
# 세 셋이 같은 표를 공유하는 이유는 그 사이 회차들이 유형을 늘리지 않았기
# 때문이고, 여기 적어 두는 이유는 v0.2·v0.3 과 같다 - 표가 자랄 때마다 이미
# 얼어붙은 파일이 빨개지면 고칠 수 있는 것이 동결된 셋뿐이 된다.
FRAUD_TYPES_AT_HOLDOUT_V0_4_TO_V0_6_FREEZE = (
    "authority_impersonation",
    "acquaintance_impersonation",
    "loan_policy_impersonation",
    "investment_scheme",
    "advance_fee_demand",
    "account_access_request",
    "money_mule_transfer",
    "smishing_malware",
    "card_delivery_impersonation",
)

OFFICIAL_CHANNEL = "VERIFY_OFFICIAL_CHANNEL"
KNOWN_CONTACT = "VERIFY_BY_KNOWN_CONTACT"

HOLDOUT_SIZES = {
    HOLDOUT_V0_2_PATH: 72,
    HOLDOUT_V0_3_PATH: 60,
    HOLDOUT_V0_4_PATH: 60,
    HOLDOUT_V0_5_PATH: 72,
    HOLDOUT_V0_6_PATH: 72,
    HOLDOUT_V0_7_PATH: 72,
    HOLDOUT_V0_8_PATH: 72,
    HOLDOUT_V0_9_PATH: 72,
    HOLDOUT_V1_0_PATH: 70,
    HOLDOUT_V1_1_PATH: 79,
    HOLDOUT_V1_2_PATH: 80,
    HOLDOUT_V1_3_PATH: 84,
}


@pytest.mark.parametrize("path", list(HOLDOUT_SIZES))
def test_holdout_set_is_labelled_and_separated_from_the_development_set(
    path: Path,
) -> None:
    holdout = load_holdout_cases(path)
    development = load_golden_cases()

    assert len(holdout) == HOLDOUT_SIZES[path]
    assert is_held_out(holdout)
    assert not is_held_out(development)
    assert all(case.synthetic for case in holdout)
    assert {case.case_id for case in holdout}.isdisjoint(
        case.case_id for case in development
    )
    # 문장이 겹치면 개발셋에서 고친 것이 held-out 점수로 되돌아온다.
    assert {case.text for case in holdout}.isdisjoint(
        case.text for case in development
    )


@pytest.mark.parametrize(
    ("earlier", "later"),
    [
        (HOLDOUT_V0_2_PATH, HOLDOUT_V0_3_PATH),
        (HOLDOUT_V0_2_PATH, HOLDOUT_V0_4_PATH),
        (HOLDOUT_V0_3_PATH, HOLDOUT_V0_4_PATH),
        (HOLDOUT_V0_2_PATH, HOLDOUT_V0_5_PATH),
        (HOLDOUT_V0_3_PATH, HOLDOUT_V0_5_PATH),
        (HOLDOUT_V0_4_PATH, HOLDOUT_V0_5_PATH),
        (HOLDOUT_V0_2_PATH, HOLDOUT_V0_6_PATH),
        (HOLDOUT_V0_3_PATH, HOLDOUT_V0_6_PATH),
        (HOLDOUT_V0_4_PATH, HOLDOUT_V0_6_PATH),
        (HOLDOUT_V0_5_PATH, HOLDOUT_V0_6_PATH),
        (HOLDOUT_V0_2_PATH, HOLDOUT_V0_7_PATH),
        (HOLDOUT_V0_3_PATH, HOLDOUT_V0_7_PATH),
        (HOLDOUT_V0_4_PATH, HOLDOUT_V0_7_PATH),
        (HOLDOUT_V0_5_PATH, HOLDOUT_V0_7_PATH),
        (HOLDOUT_V0_6_PATH, HOLDOUT_V0_7_PATH),
        (HOLDOUT_V0_2_PATH, HOLDOUT_V0_8_PATH),
        (HOLDOUT_V0_3_PATH, HOLDOUT_V0_8_PATH),
        (HOLDOUT_V0_4_PATH, HOLDOUT_V0_8_PATH),
        (HOLDOUT_V0_5_PATH, HOLDOUT_V0_8_PATH),
        (HOLDOUT_V0_6_PATH, HOLDOUT_V0_8_PATH),
        (HOLDOUT_V0_7_PATH, HOLDOUT_V0_8_PATH),
        (HOLDOUT_V0_2_PATH, HOLDOUT_V0_9_PATH),
        (HOLDOUT_V0_3_PATH, HOLDOUT_V0_9_PATH),
        (HOLDOUT_V0_4_PATH, HOLDOUT_V0_9_PATH),
        (HOLDOUT_V0_5_PATH, HOLDOUT_V0_9_PATH),
        (HOLDOUT_V0_6_PATH, HOLDOUT_V0_9_PATH),
        (HOLDOUT_V0_7_PATH, HOLDOUT_V0_9_PATH),
        (HOLDOUT_V0_8_PATH, HOLDOUT_V0_9_PATH),
        (HOLDOUT_V0_2_PATH, HOLDOUT_V1_0_PATH),
        (HOLDOUT_V0_3_PATH, HOLDOUT_V1_0_PATH),
        (HOLDOUT_V0_4_PATH, HOLDOUT_V1_0_PATH),
        (HOLDOUT_V0_5_PATH, HOLDOUT_V1_0_PATH),
        (HOLDOUT_V0_6_PATH, HOLDOUT_V1_0_PATH),
        (HOLDOUT_V0_7_PATH, HOLDOUT_V1_0_PATH),
        (HOLDOUT_V0_8_PATH, HOLDOUT_V1_0_PATH),
        (HOLDOUT_V0_9_PATH, HOLDOUT_V1_0_PATH),
        (HOLDOUT_V0_2_PATH, HOLDOUT_V1_1_PATH),
        (HOLDOUT_V0_3_PATH, HOLDOUT_V1_1_PATH),
        (HOLDOUT_V0_4_PATH, HOLDOUT_V1_1_PATH),
        (HOLDOUT_V0_5_PATH, HOLDOUT_V1_1_PATH),
        (HOLDOUT_V0_6_PATH, HOLDOUT_V1_1_PATH),
        (HOLDOUT_V0_7_PATH, HOLDOUT_V1_1_PATH),
        (HOLDOUT_V0_8_PATH, HOLDOUT_V1_1_PATH),
        (HOLDOUT_V0_9_PATH, HOLDOUT_V1_1_PATH),
        (HOLDOUT_V1_0_PATH, HOLDOUT_V1_1_PATH),
        (HOLDOUT_V0_2_PATH, HOLDOUT_V1_2_PATH),
        (HOLDOUT_V0_3_PATH, HOLDOUT_V1_2_PATH),
        (HOLDOUT_V0_4_PATH, HOLDOUT_V1_2_PATH),
        (HOLDOUT_V0_5_PATH, HOLDOUT_V1_2_PATH),
        (HOLDOUT_V0_6_PATH, HOLDOUT_V1_2_PATH),
        (HOLDOUT_V0_7_PATH, HOLDOUT_V1_2_PATH),
        (HOLDOUT_V0_8_PATH, HOLDOUT_V1_2_PATH),
        (HOLDOUT_V0_9_PATH, HOLDOUT_V1_2_PATH),
        (HOLDOUT_V1_0_PATH, HOLDOUT_V1_2_PATH),
        (HOLDOUT_V1_1_PATH, HOLDOUT_V1_2_PATH),
        (HOLDOUT_V0_2_PATH, HOLDOUT_V1_3_PATH),
        (HOLDOUT_V0_3_PATH, HOLDOUT_V1_3_PATH),
        (HOLDOUT_V0_4_PATH, HOLDOUT_V1_3_PATH),
        (HOLDOUT_V0_5_PATH, HOLDOUT_V1_3_PATH),
        (HOLDOUT_V0_6_PATH, HOLDOUT_V1_3_PATH),
        (HOLDOUT_V0_7_PATH, HOLDOUT_V1_3_PATH),
        (HOLDOUT_V0_8_PATH, HOLDOUT_V1_3_PATH),
        (HOLDOUT_V0_9_PATH, HOLDOUT_V1_3_PATH),
        (HOLDOUT_V1_0_PATH, HOLDOUT_V1_3_PATH),
        (HOLDOUT_V1_1_PATH, HOLDOUT_V1_3_PATH),
        (HOLDOUT_V1_2_PATH, HOLDOUT_V1_3_PATH),
    ],
)
def test_holdout_versions_do_not_overlap_each_other(
    earlier: Path, later: Path
) -> None:
    # 앞 버전은 규칙 수정에 쓰여 소진되었다. 뒤 버전이 그 문장을 하나라도
    # 물려받으면 재측정이 소진된 셋의 점수를 그대로 되받는다.
    old = load_holdout_cases(earlier)
    new = load_holdout_cases(later)

    assert {c.case_id for c in new}.isdisjoint(c.case_id for c in old)
    assert {c.text for c in new}.isdisjoint(c.text for c in old)


@pytest.mark.parametrize("path", list(HOLDOUT_SIZES))
def test_holdout_covers_every_state_and_persona(path: Path) -> None:
    holdout = load_holdout_cases(path)

    assert {case.state.value for case in holdout} == {state.value for state in UserState}
    assert {case.persona.value for case in holdout} == {p.value for p in Persona}
    # 부정 사례가 없으면 오탐률을 잴 수 없다.
    assert sum(not case.is_fraud for case in holdout) >= 20


def test_holdout_v0_2_covers_the_taxonomy_it_was_frozen_against() -> None:
    # **동결 시점의 분류 표**를 기준으로 본다. 현재 표를 기준으로 하면, 나중에
    # 유형이 하나 늘 때마다 이미 얼어붙은 파일의 테스트가 빨개진다. 그때 할 수
    # 있는 일은 둘뿐인데 - 동결된 셋을 고치거나, 유형 추가를 포기하거나 - 둘 다
    # 틀렸다. 셋은 자기가 태어난 시점의 표를 덮으면 된다.
    covered = {
        t for case in load_holdout_cases(HOLDOUT_V0_2_PATH)
        for t in case.expected_fraud_types
    }

    assert covered == set(FRAUD_TYPES_AT_HOLDOUT_V0_2_FREEZE)
    assert covered <= set(FRAUD_TYPES)


def test_holdout_v0_3_covers_the_taxonomy_it_was_frozen_against() -> None:
    covered = {
        t for case in load_holdout_cases(HOLDOUT_V0_3_PATH)
        for t in case.expected_fraud_types
    }

    assert covered == set(FRAUD_TYPES_AT_HOLDOUT_V0_3_FREEZE)
    assert covered <= set(FRAUD_TYPES)


def test_holdout_v0_4_covers_the_taxonomy_it_was_frozen_against() -> None:
    # v0.4 는 투자·지인 사칭 유형이 선언된 뒤에 얼렸다. `isolation_coercion`
    # 은 v0.7 에서 선언했으므로 이 셋이 덮을 의무가 없다.
    covered = {
        t for case in load_holdout_cases(HOLDOUT_V0_4_PATH)
        for t in case.expected_fraud_types
    }

    assert covered == set(FRAUD_TYPES_AT_HOLDOUT_V0_4_TO_V0_6_FREEZE)
    assert covered < set(FRAUD_TYPES)


def test_holdout_v0_4_prices_the_new_vocabulary_against_normal_sentences() -> None:
    # 투자 어휘는 정상 금융 문장과 거의 겹친다 - 원금·수익률·투자·단톡방은
    # 매일 오는 정상 안내에 들어 있다. 부정 사례가 충분히 없으면 새 어휘의
    # 오탐 비용을 잴 수 없고, 그러면 이 셋은 새 유형을 재는 자가 되지 못한다.
    negatives = [c for c in load_holdout_cases(HOLDOUT_V0_4_PATH) if not c.is_fraud]
    collision_terms = ("원금", "수익률", "투자", "단톡방", "리딩방", "폰", "번호")

    assert len(negatives) >= 20
    assert sum(
        any(term in case.text for term in collision_terms) for case in negatives
    ) >= 10


def test_holdout_v0_5_covers_the_taxonomy_it_was_frozen_against() -> None:
    # v0.5 도 유형을 늘리지 않은 회차에서 얼렸다. v0.4 와 같은 표다.
    covered = {
        t for case in load_holdout_cases(HOLDOUT_V0_5_PATH)
        for t in case.expected_fraud_types
    }

    assert covered == set(FRAUD_TYPES_AT_HOLDOUT_V0_4_TO_V0_6_FREEZE)


def test_holdout_v0_5_prices_each_planned_fix_against_normal_sentences() -> None:
    """네 부류를 고칠 셋이라면, 그 네 부류를 **깨뜨릴** 정상 문장이 있어야 한다.

    이번 회차가 넓히려는 것은 활용형 어휘, 반말 요구 표지, 예방 안내문 표지,
    그리고 요구와 대상의 결합 범위다. 넷 다 넓히는 방향이고, 넓히는 수정은
    반드시 오탐을 사 온다. 부정 사례가 각 부류마다 없으면 이 셋은 회복률만
    올려 주고 그 대가를 감춘다.
    """
    negatives = [c for c in load_holdout_cases(HOLDOUT_V0_5_PATH) if not c.is_fraud]

    def matching(*terms: str) -> int:
        return sum(any(term in case.text for term in terms) for case in negatives)

    assert len(negatives) >= 20
    # 활용형을 넓히면 걸릴 낱말들
    assert matching("확정", "입장", "깔", "단톡방", "번호가 바뀌") >= 5
    # 반말 요구를 표지에 넣으면 걸릴 문장들
    assert matching("보내 줘", "알려 줘", "해 주세요", "부탁드립니다") >= 5
    # 예방 안내문 표지를 넓히면 억제될 문장들
    assert matching("하지 않", "드리지 않") >= 4
    # 요구와 대상이 다른 절에 흩어져 있는 정상 문장들
    assert sum(len(case.text.split(".")) >= 3 for case in negatives) >= 8


def test_holdout_v0_5_keeps_the_prevention_marker_widening_honest() -> None:
    # 예방 표지를 넓히는 수정은 **사기 쪽에서** 값을 치른다. "소명하지 않으면
    # 동결됩니다" 는 협박이지 예방 서술이 아니다. 같은 어형을 가진 진짜 사기가
    # 셋 안에 여러 유형으로 흩어져 있어야, 억제가 번졌을 때 한 유형의 잡음이
    # 아니라 전면적인 하락으로 드러난다.
    positives = [c for c in load_holdout_cases(HOLDOUT_V0_5_PATH) if c.is_fraud]
    with_negated_clause = [c for c in positives if "하지 않" in c.text]

    assert len(with_negated_clause) >= 5
    assert len({t for c in with_negated_clause for t in c.expected_fraud_types}) >= 4


def test_holdout_v0_6_covers_the_taxonomy_it_was_frozen_against() -> None:
    # v0.6 이 `fh-454` 로 찾아낸 것이 바로 `isolation_coercion` 의 부재인데,
    # 그 유형은 v0.7 에서야 선언됐다. 셋은 자기가 태어난 시점의 표를 덮는다.
    covered = {
        t for case in load_holdout_cases(HOLDOUT_V0_6_PATH)
        for t in case.expected_fraud_types
    }

    assert covered == set(FRAUD_TYPES_AT_HOLDOUT_V0_4_TO_V0_6_FREEZE)


def test_holdout_v0_6_prices_two_narrowings_with_fraud_not_with_normal_text() -> None:
    """**좁히는 수정은 사기 쪽에서 값을 치른다.**

    v0.2~v0.5 가 잰 수정은 전부 넓히는 것이었고, 그 값은 정상 문장에서
    치러지므로 부정 사례를 모으면 됐다. 이번 회차는 방향이 반대다 - 기관
    게이트에 민감 요구 조건을 걸고, 공식 창구를 가리키는 절을 요구에서 뺀다.
    두 수정 다 오탐을 줄이는 대신 **진짜 사기를 끊을 수 있다.**

    그래서 이 셋의 안전장치는 부정 사례 수가 아니라, 좁히기가 끊을 수 있는
    자리에 놓인 **양성** 사례 수다. 이것이 없으면 오탐률만 떨어지고 그 대가가
    측정에 나타나지 않는다.
    """
    cases = load_holdout_cases(HOLDOUT_V0_6_PATH)
    positives = [case for case in cases if case.is_fraud]
    negatives = [case for case in cases if not case.is_fraud]

    def counting(pool, *terms: str) -> int:
        return sum(any(term in case.text for term in terms) for case in pool)

    referral = ("영업점", "창구", "홈페이지", "고객센터", "대표번호", "공식 앱")
    institutions = ("은행", "뱅크", "공단", "국세청", "세무서", "카드사", "증권사", "농협", "토스")

    # 좁히기가 끊을 수 있는 양성. 여기가 이 셋의 존재 이유다.
    assert counting(positives, *referral) >= 4
    assert counting(positives, *institutions) >= 6
    # 좁히기가 실제로 지워야 할 정상 문장.
    assert counting(negatives, *referral) >= 8
    assert counting(negatives, *institutions) >= 8
    # 유일하게 넓히는 수정(폐쇄 채널 초대의 맥락 조건)은 여전히 정상 문장으로 잰다.
    assert counting(negatives, "단톡방", "오픈채팅방", "초대") >= 5


def test_holdout_v0_7_covers_the_taxonomy_it_was_frozen_against() -> None:
    # v0.7 은 `isolation_coercion` 을 **선언한 뒤** 얼렸다. 엔진은 아직 이 유형을
    # 내지 못하고, 그래서 동결 시점 baseline 에서 이 유형의 f1 은 0.0 이다.
    covered = {
        t for case in load_holdout_cases(HOLDOUT_V0_7_PATH)
        for t in case.expected_fraud_types
    }

    assert covered == set(FRAUD_TYPES)
    assert "isolation_coercion" in covered


def test_holdout_v0_7_puts_a_ceiling_on_every_normal_sentence() -> None:
    """**재는 자에 천장이 없었다.**

    `expected_min_risk` 는 바닥만 정한다(`>=`). 그래서 등급을 올리는 수정은 이
    프로젝트의 어떤 지표에서도 점수를 잃을 수 없었고, 모든 문자를 high 로 찍는
    엔진이 상태 정책 정확도 1.0 을 받는다. 이번 회차의 세 수정 중 하나가 바로
    등급을 올리는 것(`HIGH_RISK_SIGNAL_COMBINATIONS` 확장)이므로 여기서 닫는다.

    천장은 **정상 문장에만** 건다. 사기를 필요 이상으로 높게 매기는 것은 결함이
    아니라 신중함이고, 거기에 상한을 걸면 신중함을 감점하게 된다. 넘치면 안 되는
    자리는 정상 문장이고, 정상 문장의 정답 등급은 상태 하한 **그대로**다.
    """
    cases = load_holdout_cases(HOLDOUT_V0_7_PATH)
    negatives = [case for case in cases if not case.is_fraud]
    positives = [case for case in cases if case.is_fraud]

    assert len(negatives) >= 30
    assert all(case.expected_max_risk is not None for case in negatives)
    assert all(
        case.expected_max_risk == case.expected_min_risk for case in negatives
    )
    assert all(case.expected_max_risk is None for case in positives)


def test_holdout_v0_7_prices_the_grade_raising_fix_where_it_can_overshoot() -> None:
    """등급을 올리는 수정의 값은 **기관 이름을 쓰는 정상 안내문**이 치른다.

    `authority_impersonation` + 넘겨주기 신호를 고위험으로 올리면, 같은 낱말을
    쓰는 정상 안내문이 함께 올라갈 수 있다. 값을 치를 문장이 셋에 없으면 이
    수정은 상태 정책 정확도만 올리고 대가를 감춘다.

    양성 쪽 조건도 함께 못을 박는다 - 올릴 자리가 `received_only` 여야 한다.
    상태 하한이 이미 high 면 등급이 올라간 이유가 정책인지 상태인지 갈리지 않는다.
    """
    cases = load_holdout_cases(HOLDOUT_V0_7_PATH)
    positives = [case for case in cases if case.is_fraud]
    negatives = [case for case in cases if not case.is_fraud]

    institutions = (
        "은행", "뱅크", "공단", "국세청", "세무서", "카드사", "우체국",
        "농협", "토스", "금융감독원", "지검", "장학재단",
    )

    def counting(pool, *terms: str) -> int:
        return sum(any(term in case.text for term in terms) for case in pool)

    # 올릴 자리: 기관 자칭 + 넘겨주기 요구, 상태 하한이 등급을 대신 올리지 않는 것.
    liftable = [
        case
        for case in positives
        if case.expected_min_risk == "high"
        and case.state.value == "received_only"
        and "authority_impersonation" in case.required_signal_codes
    ]
    assert len(liftable) >= 10

    # 값을 치를 자리: 같은 낱말을 쓰는 정상 안내문.
    assert counting(negatives, *institutions) >= 10


def test_holdout_v0_7_prices_the_new_type_against_ordinary_confidentiality() -> None:
    """`secrecy_isolation` 에 유형을 붙이는 순간, 그 신호의 오탐이 곧 사기 판정이 된다.

    지금까지 이 신호는 등급만 올렸다. 유형이 붙으면 `bool(fraud_types)` 가
    참이 되므로 **판정 자체가 뒤집힌다.** 그런데 현재 어휘는 "비밀로"·"보안
    유지" 같은 맨 낱말이라, 회사 대외비 공지와 생일 파티 문자가 전부 사기가 된다.

    그래서 새 유형의 값은 **평범한 비밀 유지 문장**으로 잰다. 이것이 없으면
    유형 추가는 회복률만 올리고 그 대가를 측정 밖에 둔다.
    """
    cases = load_holdout_cases(HOLDOUT_V0_7_PATH)
    positives = [case for case in cases if case.is_fraud]
    negatives = [case for case in cases if not case.is_fraud]

    secrecy_words = ("비밀", "보안 유지", "혼자 처리", "말하지", "말씀하지", "끊지", "알리지")

    isolation_cases = [
        case for case in positives if "isolation_coercion" in case.expected_fraud_types
    ]
    collisions = [
        case
        for case in negatives
        if any(word in case.text for word in secrecy_words)
    ]

    assert len(isolation_cases) >= 8
    # 고립 요구는 사칭이나 송금 없이 단독으로도 와야 한다. 다른 신호에 업혀
    # 가면 이 유형이 스스로 판정을 만드는지 알 수 없다.
    assert sum(case.required_signal_codes == ["secrecy_isolation"] for case in isolation_cases) >= 6
    assert len(collisions) >= 8


def test_holdout_v0_7_prices_the_forwarding_vocabulary_with_own_account_moves() -> None:
    # `receive_and_forward_money` 어휘를 넓히면 "월급 들어오면 적금으로 옮길게"
    # 가 걸린다. 목적지가 남의 계좌인지 내 계좌인지가 유일한 차이다.
    cases = load_holdout_cases(HOLDOUT_V0_7_PATH)
    positives = [case for case in cases if case.is_fraud]
    negatives = [case for case in cases if not case.is_fraud]

    moves = ("넘겨", "옮겨", "빼서", "빼 줘", "돌려보내", "나눠 보내", "이체", "보낼", "보냈")

    assert sum(
        "money_mule_transfer" in case.expected_fraud_types for case in positives
    ) >= 8
    assert sum(any(m in case.text for m in moves) for case in negatives) >= 6


def test_holdout_v0_9_covers_the_taxonomy_and_keeps_the_ceiling_discipline() -> None:
    cases = load_holdout_cases(HOLDOUT_V0_9_PATH)
    negatives = [case for case in cases if not case.is_fraud]
    positives = [case for case in cases if case.is_fraud]
    covered = {t for case in cases for t in case.expected_fraud_types}

    assert covered == set(FRAUD_TYPES)
    assert len(negatives) == 31
    assert all(case.expected_max_risk is not None for case in negatives)
    assert all(case.expected_max_risk is None for case in positives)


def test_holdout_v0_9_pairs_every_demand_with_and_without_a_named_institution() -> None:
    """**확인 행동이 어디로 가리키는가**를 재려면 짝이 있어야 한다.

    "공식 대표번호로 확인하세요" 는 확인할 기관이 지정됐을 때만 실행 가능한
    조언이다. 이름을 대지 않은 상대에게 같은 말을 하면 사용자는 존재하지 않는
    창구를 찾다가 결국 **메시지에 적힌 번호로 건다.** 그래서 같은 신호 위에
    자칭이 있는 문장과 없는 문장을 짝지어 놓고, 각 사례가 내면 **안 되는**
    행동을 함께 적는다.

    값은 양쪽에서 치러진다. 이름 없는 쪽으로 너무 돌면 기관 사칭 열네 건이
    공식 창구를 잃고, 자칭 쪽으로 너무 돌면 지인 사칭 네 건이 v0.4 회귀가
    된다.
    """
    cases = load_holdout_cases(HOLDOUT_V0_9_PATH)

    def has(case, required: str, forbidden: str) -> bool:
        return (
            required in case.required_action_codes
            and forbidden in case.forbidden_action_codes
        )

    nameless = [c for c in cases if has(c, KNOWN_CONTACT, OFFICIAL_CHANNEL)]
    named = [c for c in cases if has(c, OFFICIAL_CHANNEL, KNOWN_CONTACT)]

    assert len(nameless) >= 20
    assert len(named) >= 14

    # 지인 사칭은 v0.4 가 이미 맞게 내보내고 있다. 이 회차가 깨뜨릴 수 있는
    # 자리이므로 넷 전부 아는 창구를 요구하고 공식 창구를 금지한다.
    acquaintance = [
        c for c in cases if "acquaintance_impersonation" in c.expected_fraud_types
    ]
    assert len(acquaintance) == 4
    assert all(has(c, KNOWN_CONTACT, OFFICIAL_CHANNEL) for c in acquaintance)

    # 정상 문장도 없는 창구를 가리키면 안 된다. 사기 쪽에서만 재면 수정이
    # 정상 문장에 남긴 자국이 측정 밖으로 빠진다.
    assert sum(
        OFFICIAL_CHANNEL in c.forbidden_action_codes for c in cases if not c.is_fraud
    ) >= 3


def test_holdout_v0_9_prices_the_grade_raise_and_the_accusation_narrowing() -> None:
    """등급 올리기와 유형 좁히기는 값을 치르는 자리가 서로 반대다.

    올리기의 값은 천장에서 치러지므로 정상 31건이 전부 천장을 선언한다.
    좁히기(`대포통장` 은 고발이지 요구가 아니다)의 값은 **사기 쪽에서**
    치러진다 - 좁히기가 지나치면 통장·카드를 진짜로 요구하는 문장이
    접근수단 요구라는 이름을 잃는다.
    """
    cases = load_holdout_cases(HOLDOUT_V0_9_PATH)
    positives = [case for case in cases if case.is_fraud]

    # 위협 + 접근수단 요구인데 자칭이 없어 medium 에서 멈추는 자리.
    threatened = [
        c
        for c in positives
        if "urgency" in c.required_signal_codes
        and {"credential", "account_access"} & set(c.required_signal_codes)
        and c.expected_min_risk == "high"
        and "authority_impersonation" not in c.required_signal_codes
    ]
    assert len(threatened) >= 5

    # 고발 문구. 통장이 나오지만 요구 대상이 아니다.
    accusation = [c for c in positives if "대포통장" in c.text or "통장이 범죄" in c.text]
    assert len(accusation) >= 3
    assert all(
        "account_access_request" not in c.expected_fraud_types for c in accusation
    )

    # 같은 낱말을 쓰는 진짜 요구. 좁히기가 이쪽을 끊으면 값을 치른 것이다.
    demanded = [
        c
        for c in positives
        if ("통장" in c.text or "체크카드" in c.text)
        and "account_access_request" in c.expected_fraud_types
    ]
    assert len(demanded) >= 6


def test_holdout_v1_0_covers_the_taxonomy_and_keeps_the_ceiling_discipline() -> None:
    cases = load_holdout_cases(HOLDOUT_V1_0_PATH)
    negatives = [case for case in cases if not case.is_fraud]
    positives = [case for case in cases if case.is_fraud]
    covered = {t for case in cases for t in case.expected_fraud_types}

    assert covered == set(FRAUD_TYPES)
    assert len(negatives) == 32
    assert all(case.expected_max_risk is not None for case in negatives)
    assert all(case.expected_max_risk is None for case in positives)


def test_holdout_v1_0_prices_five_widenings_against_the_normal_form_they_touch() -> None:
    """**다섯 수정이 전부 넓히기다. 값은 한 방향으로만 치러진다.**

    v0.9 §9 가 다음 회차 몫으로 이름을 적어 둔 결함이 그대로 이 셋의 다섯
    그룹이다. 넓히기의 값은 정상 문장에서 나오는데, 아무 정상 문장이 아니라
    **넓히려는 바로 그 어형을 정상적으로 쓰는 문장**이어야 한다.

    - 우언적 금지(`-면 안 됩니다`): 예방 안내문은 위험한 행동을 **금지형으로
      입에 올린다.** 요구를 세는 자리에서 그 문장이 요구로 세어졌다.
    - 자기 경로 제한(`…에서만`): 정상 공지도 창구를 하나로 제한한다. 다른
      점은 그 창구를 읽는 사람이 이미 아는가뿐이다.
    - 숫자로 적은 기한: 청구서도 오늘 자정을 말한다.
    - 띄어 쓴 `대환 대출`: 은행도 그 제도를 안내한다.
    - 고립 요구만 든 조건부 자칭: 대외비 공지도 비밀을 요구한다.
    """
    cases = load_holdout_cases(HOLDOUT_V1_0_PATH)
    positives = [case for case in cases if case.is_fraud]
    negatives = [case for case in cases if not case.is_fraud]

    def count(pool, *needles: str) -> int:
        return sum(any(n in c.text for n in needles) for c in pool)

    # 1. 우언적 금지 어형. 사기는 아는 창구를 금지해 놓고 그 뒤에서 요구하고,
    #    정상은 요구하지 말라고 말한다. 같은 어형이 정반대 자리에 있다.
    assert count(positives, "면 안 됩니다", "면 안 되") >= 6
    assert count(negatives, "면 안 됩니다", "면 안 되") >= 5

    # 2. 자기 경로 제한. 정상 쪽이 더 많아야 한다 - 넓히면 이쪽이 먼저 깨진다.
    assert count(positives, "에서만", "으로만", "만 가능", "만 처리", "만 진행") >= 6
    assert count(negatives, "에서만", "으로만", "만 가능", "만 처리", "만 진행") >= 7

    # 3. 숫자로 적은 기한. 사기 쪽 넷은 접근수단 요구와 짝을 이뤄 high 를,
    #    정상 쪽 일곱은 같은 표현을 쓰고도 low 를 요구한다.
    deadlines = ("1시간 안에", "30분 내", "오늘 자정까지", "내일까지", "금일 중", "마감 임박")
    assert count(positives, *deadlines) >= 6
    assert count(negatives, *deadlines) >= 5
    assert (
        sum(
            any(d in c.text for d in deadlines) and c.expected_min_risk == "high"
            for c in positives
        )
        >= 4
    )

    # 4. 띄어 쓴 `대환 대출`. 무조건 층에 넣으면 이 넷이 바로 오탐이 된다.
    assert count(positives, "대환 대출") >= 3
    assert count(negatives, "대환 대출", "대출 갈아타기", "햇살론") >= 4

    # 5. 고립 요구만 든 조건부 자칭. 넘겨줄 물건이 없을 뿐 요구가 없는 것이
    #    아니다. 값은 기밀 유지를 말하는 정상 공지가 치른다.
    isolation = [c for c in positives if "isolation_coercion" in c.expected_fraud_types]
    assert len(isolation) >= 3
    assert all(c.expected_min_risk == "high" for c in isolation)
    assert count(negatives, "대외비", "비밀유지", "공유하지 말아") >= 2


def test_holdout_v1_0_declares_a_ceiling_on_every_normal_and_names_what_it_forbids() -> None:
    """정상 34건 전부가 천장을 선언한다. 다섯 수정이 전부 넓히기이기 때문이다.

    넓히기는 등급을 올리는 방향으로만 미끄러진다. 사기 쪽에 바닥을 적는 것은
    이 회차에서 거의 아무것도 재지 못하고, 정상 쪽 천장 하나가 깨지는 것이
    이 수정들이 지불할 수 있는 유일한 값이다.

    금지 행동은 v0.9 가 들여온 자다. 여기서는 **고발과 예방을 요구로 읽지
    않는지**를 겹쳐 센다 - 통장을 빌려주지 말라는 안내문이 접근수단 요구로
    읽히면 사용자에게 계좌 보호 행동이 나간다.
    """
    cases = load_holdout_cases(HOLDOUT_V1_0_PATH)
    negatives = [case for case in cases if not case.is_fraud]

    assert len(negatives) == 32
    assert all(case.expected_max_risk == "low" for case in negatives)

    forbidding = [c for c in cases if c.forbidden_action_codes]
    assert len(forbidding) >= 12


def test_holdout_v1_1_covers_the_taxonomy_and_keeps_the_ceiling_discipline() -> None:
    cases = load_holdout_cases(HOLDOUT_V1_1_PATH)
    negatives = [case for case in cases if not case.is_fraud]
    positives = [case for case in cases if case.is_fraud]
    covered = {t for case in cases for t in case.expected_fraud_types}

    assert covered == set(FRAUD_TYPES)
    assert len(negatives) == 38
    assert all(case.expected_max_risk is not None for case in negatives)
    assert all(case.expected_max_risk is None for case in positives)


def test_holdout_v1_1_puts_the_user_state_back_into_the_denominator() -> None:
    """**이 셋이 존재하는 이유. 상태를 재는 자리가 열 회차에 걸쳐 말라붙었다.**

    `received_only` 가 아닌 사례 수는 v0.2 부터 이렇게 움직였다 -
    18, 27, 21, 15, 14, 17, 16, 14, 8, 6. 아무도 그렇게 정하지 않았다.
    회차마다 고칠 결함이 문장 안에 있었고, 문장 안의 결함을 재는 데에는
    `received_only` 가 가장 편했기 때문이다.

    그래서 v1.0 의 `scenario_policy_accuracy` 0.9571 은 사실상
    **`received_only` 에 대한 진술**이다. 상태 정책이 여섯 갈래인데 그중
    하나가 표본의 91% 를 차지하면, 나머지 다섯 갈래가 무너져도 그 숫자는
    거의 움직이지 않는다. 재지 않은 것을 잰 것처럼 적으면 그것이 지어낸
    근거다.

    이 셋은 그 비율을 뒤집는다. 상태별 최소치를 못박아 두는 이유는,
    다음 회차가 또 편한 쪽으로 흘러가더라도 **이 셋만은 상태를 계속
    재도록** 하기 위해서다.
    """
    cases = load_holdout_cases(HOLDOUT_V1_1_PATH)
    stateful = [c for c in cases if c.state is not UserState.RECEIVED_ONLY]

    assert len(stateful) >= 30
    # 여섯 갈래 전부가 혼자서도 의미 있는 표본이어야 한다.
    for state in UserState:
        if state is UserState.RECEIVED_ONLY:
            continue
        assert sum(c.state is state for c in cases) >= 4, state

    # 뒤집혔는지는 앞 회차와 견줘야 말이 된다.
    previous = load_holdout_cases(HOLDOUT_V1_0_PATH)
    assert sum(
        c.state is not UserState.RECEIVED_ONLY for c in previous
    ) < len(stateful)

    # 상태는 정상 문장에도 붙는다. 상태가 곧 사기라면 잰 것은 상태가
    # 아니라 사기다.
    assert sum(not c.is_fraud for c in stateful) >= 6


def test_holdout_v1_1_ceilings_a_stateful_normal_at_the_floor_its_state_forces() -> None:
    """**상태가 있는 정상 문장의 천장은 그 상태의 바닥이다.**

    링크를 눌렀다는 사실은 등급을 medium 으로 올린다. 그것은 상태 정책의
    몫이고 맞는 일이다. 하지만 거기서 한 칸이라도 더 올라가면 그것은
    **문장이 올린 것**이고, 문장이 정상이면 틀린 것이다.

    v1.0 은 정상 34건 전부에 `low` 천장을 걸었다. 상태가 전부
    `received_only` 였으니 그럴 수 있었다. 여기서는 그렇게 적을 수 없다 -
    적으면 상태 정책 자체를 결함으로 선언하는 라벨이 된다. 천장을
    상태의 바닥에 맞추면, 재는 것이 **상태 위에 문장이 얹은 몫**으로
    좁혀진다.
    """
    cases = load_holdout_cases(HOLDOUT_V1_1_PATH)
    negatives = [c for c in cases if not c.is_fraud]

    for case in negatives:
        floor = STATE_MINIMUM_RISK[case.state]
        assert case.expected_max_risk is not None, case.case_id
        assert RISK_RANK[case.expected_max_risk] >= RISK_RANK[floor], case.case_id
        if case.state is UserState.RECEIVED_ONLY:
            continue
        # 상태가 있으면 천장은 바닥과 같다. 여유를 두면 아무것도 재지 않는다.
        assert case.expected_max_risk == floor, case.case_id


def test_holdout_v1_1_prices_the_state_and_channel_widenings_where_each_can_break() -> None:
    """**이번 회차 다섯 수정 중 넷이 넓히기다. 값은 이 셋의 정상 쪽에서 나온다.**

    - D1 상태가 예방 행동을 반복하지 않는다. `CLICKED_LINK` 는
      `DO_NOT_CLICK` 을 돌려받고 `RECEIVED_UNKNOWN_MONEY` 는
      `DO_NOT_FORWARD_MONEY` 를 돌려받는데, 계좌 권한과 앱 설치와
      송금에는 그런 자리가 없다. **이미 한 번 넘긴 사람이 가장 다시
      넘기기 쉬운 사람이다.** 값은 상태를 가진 정상 문장이 치른다.
    - D2 창구를 기관 자칭으로만 찾는다. `수사`, `세무조사`, `결제 승인`,
      `지원금·환급` 은 이름을 대지 않고도 확인할 창구를 가리킨다. 값은
      진짜 승인 문자와 진짜 정부·국세청 안내문이 치른다 - **창구를
      가리키는 것과 위험을 가리키는 것은 다르다.**
    - D3 요구 어미의 종결형 계열(`-하셔야 합니다`). 값은 종결형으로 쓴
      정상 안내문이 치른다.
    - D4 고립 어휘 × 우언적 금지. v1.0 은 요구 쪽 자리만 닫았다. 값은
      `가족`·`부모님` 이 정상적으로 등장하는 문장이 치른다.
    - D5 채널 어휘 미등록 이름(구글플레이·원스토어·정부24). 값은 그
      스토어로 **보내는** 정상 문장이 치른다.
    """
    cases = load_holdout_cases(HOLDOUT_V1_1_PATH)
    positives = [case for case in cases if case.is_fraud]
    negatives = [case for case in cases if not case.is_fraud]

    def count(pool, *needles: str) -> int:
        return sum(any(n in c.text for n in needles) for c in pool)

    # D1. 상태만이 낼 수 있는 예방 행동. 문장이 그 행동을 요구하지 않는데
    #     라벨이 요구한다 - 이 조건은 상태에서 나오지 않으면 만족될 수 없다.
    state_only = {
        UserState.SHARED_ACCOUNT_ACCESS: "DO_NOT_SHARE_ACCESS",
        UserState.INSTALLED_APP: "DO_NOT_INSTALL",
        UserState.SHARED_PERSONAL_INFO: "DO_NOT_SHARE_ACCESS",
        UserState.TRANSFERRED_MONEY: "DO_NOT_FORWARD_MONEY",
    }
    for state, action in state_only.items():
        demanding = [
            c
            for c in positives
            if c.state is state and action in c.required_action_codes
        ]
        assert len(demanding) >= 2, state
    # 값을 치르는 쪽. 상태만 보고 붙이면 이 문장들에도 붙는다.
    assert sum(
        c.state in state_only for c in negatives
    ) >= 4
    assert all(
        not c.required_action_codes for c in negatives
    )

    # D2. 이름을 대지 않고 사건으로 창구를 가리키는 문장.
    events = ("수사", "조사", "승인", "환급", "지원")
    channel_positives = [
        c
        for c in positives
        if any(e in c.text for e in events)
        and "VERIFY_OFFICIAL_CHANNEL" in c.required_action_codes
    ]
    assert len(channel_positives) >= 8
    # 같은 낱말을 쓰는 진짜 안내문. 넓히기가 이쪽에 행동을 붙이면 값을
    # 치른 것이다.
    channel_negatives = [c for c in negatives if any(e in c.text for e in events)]
    assert len(channel_negatives) >= 7
    assert all(
        "VERIFY_OFFICIAL_CHANNEL" not in c.required_action_codes
        for c in channel_negatives
    )

    # D3. 종결형. 정상 쪽이 적으면 어미 표를 넓혀도 값을 치를 자리가 없다.
    endings = ("셔야 합니다", "하셔야", "주셔야")
    assert count(positives, *endings) >= 6
    assert count(negatives, *endings) >= 4

    # D4. 고립 어휘 × 우언적 금지. 같은 어형이 정반대 자리에 있다.
    assert count(positives, "가족", "부모님", "직원분들께", "주변에") >= 5
    assert count(negatives, "가족", "부모님", "직원분들께", "외부에") >= 4

    # D5. 채널 이름. 사기는 공식 스토어를 **막고**, 정상은 그리로 **보낸다.**
    stores = ("구글플레이", "플레이스토어", "원스토어", "정부24")
    assert count(positives, *stores) >= 4
    assert count(negatives, *stores) >= 3


def test_holdout_v0_8_covers_the_taxonomy_and_keeps_the_ceiling_discipline() -> None:
    cases = load_holdout_cases(HOLDOUT_V0_8_PATH)
    negatives = [case for case in cases if not case.is_fraud]
    positives = [case for case in cases if case.is_fraud]
    covered = {t for case in cases for t in case.expected_fraud_types}

    assert covered == set(FRAUD_TYPES)
    assert len(negatives) == 36
    # 천장은 정상 문장에만. 사기를 필요 이상으로 높게 매기는 것은 결함이 아니다.
    assert all(case.expected_max_risk is not None for case in negatives)
    assert all(case.expected_max_risk is None for case in positives)


def test_holdout_v0_8_prices_five_widenings_where_each_one_can_break() -> None:
    """**넓히는 수정의 값은 정상 문장이 치른다. 아무 정상 문장이 아니라 그 자리의 것이다.**

    이번 회차 여섯 수정 중 다섯이 넓히기다. 부정 사례를 72건 아무거나 모아
    두면 오탐률은 0 으로 나오고 대가는 측정 밖에 남는다. 값을 치를 문장은
    **넓힌 어휘를 정상적으로 쓰는 문장**이어야 한다.

    - 권한 위임: 계좌 권한 위임은 실재하는 제도다(위임장·대리인·영업점).
    - 재전달: '정산금' 은 관리비 고지서의 낱말이고 '돌려보내' 는 환불의 낱말이다.
    - 지검 자칭: '지검' 은 지명이 붙은 고유명사라 일상 대화에 그대로 나온다.
    - 높임 어미 송금: 정상적인 청구도 "계좌로 입금하셔야" 라고 쓴다.
    """
    cases = load_holdout_cases(HOLDOUT_V0_8_PATH)
    positives = [case for case in cases if case.is_fraud]
    negatives = [case for case in cases if not case.is_fraud]

    def counting(pool, *terms: str) -> int:
        return sum(any(term in case.text for term in terms) for case in pool)

    # 1) 권한 위임 요구. 수령자 표현이 있는 쪽과 없는 쪽.
    assert counting(positives, "위임", "양도", "넘겨") >= 5
    assert counting(negatives, "위임", "양도", "넘겨") >= 5

    # 2) 재전달 어형과 돈 목적어 확장.
    assert counting(positives, "정산금", "돌려보내", "나눠 보내", "옮겨") >= 5
    assert counting(negatives, "정산금", "돌려보내", "나눠 보내", "옮겨") >= 5

    # 3) 지검 자칭. 무조건 켜는 층에 넣으면 정상 대화가 걸린다.
    assert counting(positives, "지검") >= 3
    assert counting(negatives, "지검") >= 1

    # 4) 높임 어미 송금 요구. 정상 청구도 같은 어미를 쓴다.
    assert counting(positives, "입금하셔", "송금하셔", "이체하셔") >= 3
    assert counting(negatives, "입금하셔", "입금해") >= 2


def test_holdout_v0_8_prices_the_prevention_marker_narrowing_on_both_sides() -> None:
    """예방 표지를 좁히는 수정은 **양쪽에서** 값을 치른다.

    `드리지 않` 이라는 맨 표지가 '말씀드리지 않'·'건드리지 않' 까지 덮는다.
    좁히면 고립 요구가 살아나지만(양성), 좁히기가 지나치면 진짜 예방
    안내문이 사기로 올라간다(음성). 두 자리를 같은 셋에 넣어야 수정이
    어느 쪽으로 미끄러졌는지 보인다.
    """
    cases = load_holdout_cases(HOLDOUT_V0_8_PATH)
    positives = [case for case in cases if case.is_fraud]
    negatives = [case for case in cases if not case.is_fraud]

    # 억제에 눌려 있는 고립 요구.
    isolation = [
        case for case in positives if "isolation_coercion" in case.expected_fraud_types
    ]
    assert len(isolation) >= 5
    assert sum("드리지" in case.text for case in isolation) >= 2

    # 억제가 계속 살아 있어야 하는 진짜 예방 안내문.
    prevention = [
        case
        for case in negatives
        if any(m in case.text for m in ("않습니다", "않으며", "없습니다", "일은 없"))
    ]
    assert len(prevention) >= 8
    assert sum("드리지" in case.text for case in negatives) >= 2


def test_the_ceiling_metric_reports_null_for_sets_that_never_declared_one() -> None:
    """재지 않은 것을 만점으로 적으면 그것이 곧 지어낸 근거다.

    v0.1~v0.6 은 천장을 선언하지 않았다. 그 셋들의 `risk_ceiling_accuracy` 가
    1.0 으로 나가면, 이번 수정이 여섯 개 셋을 통과한 것처럼 보인다. 통과한 것이
    아니라 **재지 않은** 것이다.
    """
    without = evaluate_golden_set(load_holdout_cases(HOLDOUT_V0_6_PATH))
    with_ceiling = evaluate_golden_set(load_holdout_cases(HOLDOUT_V0_7_PATH))

    assert without["scenario_engine_v0_1"]["risk_ceiling_accuracy"] is None  # type: ignore[index]
    measured = with_ceiling["scenario_engine_v0_1"]["risk_ceiling_accuracy"]  # type: ignore[index]
    assert isinstance(measured, float)
    assert 0.0 <= measured <= 1.0


def test_a_ceiling_below_the_floor_is_a_typo_not_a_label() -> None:
    payload = load_holdout_cases(HOLDOUT_V0_7_PATH)[0].model_dump()
    payload["expected_min_risk"] = "high"
    payload["expected_max_risk"] = "low"

    with pytest.raises(ValueError, match="expected_max_risk"):
        FraudGoldenCase.model_validate(payload)


def test_an_undeclared_label_does_not_restate_what_an_old_measurement_measured() -> None:
    """v0.7 이 라벨에 등급 천장을 더했다. 그 앞의 셋들은 하나도 안 움직여야 한다.

    `normalized_dataset_sha256` 은 **어떤 사례와 라벨로 쟀는지**를 식별한다.
    선택 필드를 하나 더했다고 옛 셋의 신원이 바뀌면, 이미 돈을 주고 받아 둔
    판정 결과와 v0.1~v0.6 결과 파일의 출처 연결이 전부 끊어진다 - 문장도
    라벨도 그대로인데. 그래서 **선언하지 않은 천장은 신원에 들어가지 않는다.**

    아래 두 값은 v0.6 회차(`7688dad`)에 커밋된 결과 파일이 적고 있는 해시다.
    손으로 옮겨 적은 상수가 아니라 그 파일에서 읽는다.
    """
    committed = json.loads(
        Path("evaluation/results/fraud-holdout-v0.6.json").read_text(encoding="utf-8")
    )

    assert normalized_dataset_sha256(
        load_holdout_cases(HOLDOUT_V0_6_PATH)
    ) == committed["dataset"]["normalized_sha256"]


def test_declaring_a_ceiling_does_change_the_identity_of_the_set_that_declares_it() -> None:
    # 앞 테스트의 반대편이다. 천장을 선언한 셋에서까지 해시가 안 바뀌면, 그것은
    # 라벨을 신원에서 통째로 빼 버린 것이고 v0.7 의 출처 연결이 거짓이 된다.
    cases = load_holdout_cases(HOLDOUT_V0_7_PATH)
    stripped = [
        FraudGoldenCase.model_validate(
            {**case.model_dump(), "expected_max_risk": None}
        )
        for case in cases
    ]

    assert normalized_dataset_sha256(cases) != normalized_dataset_sha256(stripped)


def test_a_required_signal_must_be_one_the_response_can_actually_carry() -> None:
    """엔진이 절대 만족시킬 수 없는 요구 조건은 결함이 아니라 오탈자다.

    내부 규칙 이름(`account_access_request`)과 응답에 실리는 이름
    (`account_access`)이 다르다. 내부 이름을 적으면 그 조건은 영원히 미달로
    집계되고, `required_signal_coverage` 는 탐지가 아니라 이름 불일치를 잰다.
    v0.4·v0.5 를 얼릴 때 실제로 그렇게 적었다.
    """
    payload = load_holdout_cases(HOLDOUT_V0_5_PATH)[0].model_dump()
    payload["required_signal_codes"] = ["account_access_request"]

    with pytest.raises(ValueError, match="unemittable"):
        FraudGoldenCase.model_validate(payload)


def test_every_public_signal_code_is_reachable_from_the_rule_table() -> None:
    """허용 목록을 손으로 적지 않았다는 것을 고정한다."""
    reachable = {
        CANONICAL_TO_LEGACY_PUBLIC.get(rule.code, rule.code) for rule in SIGNAL_RULES
    }

    assert reachable < SIGNAL_CODES
    assert SIGNAL_CODES - reachable == {"suspicious_link"}


def test_a_dataset_cannot_be_half_held_out() -> None:
    mixed = load_holdout_cases(HOLDOUT_V0_2_PATH)[:40] + load_golden_cases()[:40]

    with pytest.raises(ValueError, match="entirely held-out or entirely not"):
        _validate_collection(mixed)


def test_a_holdout_case_cannot_be_smuggled_in_under_a_development_id() -> None:
    payload = load_holdout_cases(HOLDOUT_V0_2_PATH)[0].model_dump()
    payload["case_id"] = "fg-900"

    with pytest.raises(ValueError, match="case ID prefix must match held_out"):
        _validate_collection([FraudGoldenCase.model_validate(payload)])


def test_report_records_which_dataset_it_describes() -> None:
    report = evaluate_golden_set(
        load_holdout_cases(HOLDOUT_V0_3_PATH), dataset_id="fraud_holdout_v0.3"
    )

    assert report["dataset"]["id"] == "fraud_holdout_v0.3"  # type: ignore[index]
    assert report["dataset"]["held_out"] is True  # type: ignore[index]


def test_scenario_engine_meets_bootstrap_quality_gate_without_claiming_llm() -> None:
    # 판정 파일을 주지 않은 경로다. 모델 숫자가 없어도 엔진 게이트는 그대로
    # 성립해야 한다 - LLM 은 이 게이트의 전제가 아니다.
    report = evaluate_golden_set(load_golden_cases())

    assert check_minimum_quality(report) == []
    assert report["llm_only"]["status"] == "not_run"  # type: ignore[index]
    assert report["dataset"]["held_out"] is False  # type: ignore[index]
    assert len(report["dataset"]["normalized_sha256"]) == 64  # type: ignore[index]


def test_bootstrap_errors_were_fixed_without_deleting_the_hard_cases() -> None:
    # 이 테스트의 원래 목적은 "점수를 좋게 만들려고 어려운 케이스를 지우는 것"을
    # 막는 것이었다. 2026-08-19 어휘 확장(v0.2)으로 세 오류가 실제로 닫혔으므로
    # 목적은 그대로 두고 주장을 바꾼다: 세 케이스가 여전히 셋에 남아 있고,
    # 분모가 61 그대로이며, 그 상태에서 오류 목록이 비어 있어야 한다.
    cases = load_golden_cases()
    case_ids = {case.case_id for case in cases}
    assert {"fg-046", "fg-047", "fg-049"} <= case_ids

    report = evaluate_golden_set(cases)
    engine = report["scenario_engine_v0_1"]  # type: ignore[assignment]
    binary = engine["binary"]  # type: ignore[index]

    counted = (
        binary["true_positive"]
        + binary["true_negative"]
        + binary["false_positive"]
        + binary["false_negative"]
    )
    assert counted == 61

    assert engine["errors"] == {  # type: ignore[index]
        "false_positive_case_ids": [],
        "false_negative_case_ids": [],
    }


def test_previously_failing_cases_are_judged_correctly_one_by_one() -> None:
    # 집계가 아니라 케이스 단위로 못을 박는다. 집계만 보면 어떤 케이스가
    # 왜 통과했는지 알 수 없고, 나중에 어휘를 줄일 때 이 셋이 조용히
    # 되돌아가도 f1 만으로는 눈에 잘 띄지 않는다.
    by_id = {case.case_id: case for case in load_golden_cases()}

    def run(case_id: str):
        case = by_id[case_id]
        return analyze_fraud(AnalyzeRequest(text=case.text, state=case.state))

    fg046 = run("fg-046")
    assert "authority_impersonation" in {signal.code for signal in fg046.signals}
    assert fg046.fraud_types != []

    fg047 = run("fg-047")
    assert "remote_app" in {signal.code for signal in fg047.signals}
    assert fg047.fraud_types != []

    fg049 = run("fg-049")
    assert fg049.signals == []
    assert fg049.fraud_types == []


def test_explicit_prevention_context_is_not_classified_as_fraud() -> None:
    prevention_messages = (
        "OTP와 비밀번호는 누구에게도 절대 알려주지 마세요.",
        "경찰과 금융기관은 안전계좌 송금을 요구하지 않습니다.",
        "출처가 불분명한 앱 설치나 원격제어를 허용하지 마세요.",
        "제가 신청한 카드 배송 조회를 공식 앱에서 확인했습니다.",
    )

    for text in prevention_messages:
        response = analyze_fraud(AnalyzeRequest(text=text))
        assert response.fraud_types == []


def test_prevention_phrase_does_not_hide_a_later_direct_request() -> None:
    response = analyze_fraud(
        AnalyzeRequest(
            text=(
                "OTP는 알려주지 마세요. 하지만 지금 본인 확인을 위해 "
                "인증번호를 답장해 주세요."
            )
        )
    )

    assert "account_access_request" in response.fraud_types
    assert "DO_NOT_SHARE_ACCESS" in {action.code for action in response.actions}


@pytest.mark.parametrize(
    ("text", "fraud_type"),
    (
        (
            "경찰은 안전계좌 송금을 요구하지 않습니다. 하지만 지금 안전계좌로 보내 주세요.",
            "authority_impersonation",
        ),
        (
            "앱 설치는 위험하니 설치하지 마세요. 하지만 이 보안 앱 설치는 지금 설치하세요.",
            "smishing_malware",
        ),
    ),
)
def test_safety_sentence_cannot_mask_a_following_direct_instruction(
    text: str, fraud_type: str
) -> None:
    response = analyze_fraud(AnalyzeRequest(text=text))

    assert fraud_type in response.fraud_types


def test_nearest_rank_percentile_is_deterministic() -> None:
    assert percentile([4.0, 1.0, 3.0, 2.0], 0.50) == 2.0
    assert percentile([4.0, 1.0, 3.0, 2.0], 0.95) == 4.0


def test_golden_case_rejects_labels_outside_public_contract() -> None:
    payload = load_golden_cases()[0].model_dump()
    payload["expected_fraud_types"] = ["invented_type"]

    with pytest.raises(ValidationError, match="unknown fraud type labels"):
        FraudGoldenCase.model_validate(payload)


def test_latency_measurement_uses_the_supplied_case_collection() -> None:
    report = asyncio.run(measure_asgi_latency(load_golden_cases()[:1], repeats=2))

    assert report["sample_count"] == 2
    assert report["scope"] == "in_process_asgi_without_network_or_tls"


# --- LLM 단독 판정 --------------------------------------------------------
#
# 여기서 지키려는 것은 모델의 점수가 아니라 **집계의 정직성**이다. 모델을
# 유리하게 재는 방법은 셋뿐이고, 셋 다 아래에서 막는다 - 실패한 호출을 빼는 것,
# 빠진 사례를 건너뛰는 것, 다른 데이터로 잰 숫자를 그대로 두는 것.


def _run_with(judgements: list[LlmJudgement], *, dataset_sha256: str) -> LlmJudgeRun:
    return LlmJudgeRun(
        judged_at="2026-08-19T00:00:00+00:00",
        dataset_id="fraud_golden_v0.1",
        dataset_sha256=dataset_sha256,
        provider="google_ai_studio",
        model="gemini-3.6-flash",
        prompt_id="fraud_judge_v1",
        prompt_sha256="0" * 64,
        temperature=0.0,
        judgements=judgements,
    )


def test_llm_numbers_measured_on_another_dataset_are_rejected_not_reused() -> None:
    cases = load_golden_cases()
    stale = _run_with(
        [LlmJudgement(case_id=case.case_id, ok=True, is_fraud=True) for case in cases],
        dataset_sha256="f" * 64,
    )

    report = evaluate_golden_set(cases, llm_run=stale)

    assert report["llm_only"]["status"] == "stale"  # type: ignore[index]
    assert "binary" not in report["llm_only"]  # type: ignore[operator]
    # 게이트가 잡아야 한다. 잡지 않으면 골든셋을 고친 PR 이 옛 숫자를 그대로
    # 끌고 병합된다.
    assert "llm_only_stale" in check_minimum_quality(report)


def test_a_call_that_never_answered_counts_as_no_warning() -> None:
    cases = load_golden_cases()
    run = _run_with(
        [
            LlmJudgement(case_id=case.case_id, ok=False, failure="timeout")
            for case in cases
        ],
        dataset_sha256=normalized_dataset_sha256(cases),
    )

    section = evaluate_golden_set(cases, llm_run=run)["llm_only"]

    assert section["run"]["failure_count"] == len(cases)  # type: ignore[index]
    # 실패를 빼고 채점하면 분모가 0 이 되어 점수가 사라진다. 사용자 입장에서
    # 답이 없는 것은 경고가 없는 것이므로 재현율 0 으로 남는다.
    assert section["binary"]["recall"] == 0.0  # type: ignore[index]


def test_cases_the_model_was_never_asked_about_are_not_dropped() -> None:
    cases = load_golden_cases()
    run = _run_with(
        [LlmJudgement(case_id=cases[0].case_id, ok=True, is_fraud=True)],
        dataset_sha256=normalized_dataset_sha256(cases),
    )

    section = evaluate_golden_set(cases, llm_run=run)["llm_only"]

    assert section["run"]["case_count"] == len(cases)  # type: ignore[index]
    assert section["run"]["failure_kinds"] == {"missing_judgement": len(cases) - 1}  # type: ignore[index]


def test_the_shipped_hybrid_detects_exactly_what_the_engine_detects() -> None:
    # 설명 계층은 판정을 바꿀 수 없다. 이 등식이 깨지는 날은 CLAUDE.md 의 첫
    # non-negotiable 이 깨진 날이다.
    report = evaluate_golden_set(load_golden_cases())

    assert report["hybrid_v0_1"]["binary"] == report["scenario_engine_v0_1"]["binary"]  # type: ignore[index]
    assert report["hybrid_v0_1"]["detection_identical_to"] == "scenario_engine_v0_1"  # type: ignore[index]


def test_committed_judgement_run_still_describes_the_committed_dataset() -> None:
    # 커밋된 두 파일이 서로 어긋난 채 병합되는 것을 막는다. 골든셋을 고치고
    # 재측정을 잊으면 여기서 걸린다.
    run = load_llm_run(JUDGE_RUN_PATH)
    if run is None:
        pytest.skip("판정 결과 파일이 없다")

    cases = load_golden_cases()
    assert run.dataset_sha256 == normalized_dataset_sha256(cases)
    assert {judgement.case_id for judgement in run.judgements} == {
        case.case_id for case in cases
    }


# --- 판정 계약 ------------------------------------------------------------


def test_judge_prompt_is_pinned_to_its_hash() -> None:
    contract = fraud_judge_contract(provider="stub")
    contract.verify_prompt(FRAUD_JUDGE_PROMPT)

    with pytest.raises(LlmContractError, match="does not match the pinned hash"):
        contract.verify_prompt(FRAUD_JUDGE_PROMPT + " ")


def test_personal_identifiers_do_not_leave_with_the_judge_prompt() -> None:
    prompt = build_judge_prompt(
        persona="unknown",
        state="received_only",
        message="900101-1234567 계좌 123-456-7890 으로 010-1234-5678 에 연락",
        max_input_chars=4_000,
    )

    assert "900101-1234567" not in prompt
    assert "010-1234-5678" not in prompt
    assert "123-456-7890" not in prompt
    # 무엇이 요구됐는지는 남아야 한다. 통째로 지우면 신호까지 사라진다.
    assert "[계좌번호]" in prompt


def test_a_code_fence_does_not_throw_away_a_valid_judgement() -> None:
    judgement = parse_judgement(
        "fg-001",
        '```json\n{"is_fraud": true, "fraud_types": ["authority_impersonation"], '
        '"risk_level": "high", "actions": ["STOP_CONTACT"]}\n```',
        latency_ms=1.0,
    )

    assert judgement.ok
    assert judgement.fraud_types == ["authority_impersonation"]


def test_codes_outside_the_contract_are_dropped_and_recorded() -> None:
    judgement = parse_judgement(
        "fg-001",
        '{"is_fraud": true, "fraud_types": ["romance_scam"], '
        '"risk_level": "high", "actions": ["CALL_MY_LAWYER", "STOP_CONTACT"]}',
        latency_ms=1.0,
    )

    assert judgement.fraud_types == []
    assert judgement.actions == ["STOP_CONTACT"]
    assert judgement.dropped_codes == ["romance_scam", "CALL_MY_LAWYER"]


@pytest.mark.parametrize(
    ("raw", "failure"),
    (
        ("판정: 사기입니다", "unparsable_json"),
        ("[]", "not_an_object"),
        ('{"is_fraud": true, "risk_level": "critical"}', "unknown_risk_level"),
        ('{"risk_level": "high"}', "missing_is_fraud"),
    ),
)
def test_output_we_cannot_score_is_recorded_as_a_failure(
    raw: str, failure: str
) -> None:
    judgement = parse_judgement("fg-001", raw, latency_ms=1.0)

    assert not judgement.ok
    assert judgement.failure == failure


def test_one_dead_call_does_not_abandon_the_rest_of_the_batch() -> None:
    class DeadProvider:
        name = "stub"

        def generate(self, *, contract: object, prompt: str) -> str:
            raise LlmUnavailable("stub returned HTTP 503")

    provider: LlmProvider = DeadProvider()  # type: ignore[assignment]
    judgement = judge_case(
        case_id="fg-001",
        persona="unknown",
        state="received_only",
        message="검찰입니다. 지금 송금하세요.",
        provider=provider,
        contract=fraud_judge_contract(provider="stub"),
        clock=lambda: 0.0,
    )

    assert not judgement.ok
    assert judgement.failure == "stub returned HTTP 503"


# ---------------------------------------------------------------------------
# v0.9. 행동 쪽에도 천장이 없었다.
# ---------------------------------------------------------------------------


def _case_with(forbidden: list[str], required: list[str]) -> FraudGoldenCase:
    return FraudGoldenCase(
        case_id="fh-701",
        text="이름을 대지 않은 사람이 계좌 조회 권한을 넘겨 달라고 한다.",
        persona=Persona.EARLY_CAREER,
        state=UserState.RECEIVED_ONLY,
        is_fraud=True,
        expected_fraud_types=["account_access_request"],
        expected_min_risk="medium",
        required_action_codes=required,
        forbidden_action_codes=forbidden,
        held_out=True,
        annotation_note="지표가 무엇을 재는지 보이려고 만든 사례다.",
    )


def _response_with(action_codes: list[str]) -> AnalyzeResponse:
    return AnalyzeResponse(
        risk_score=50,
        risk_level="medium",
        signals=[],
        scenario=UserState.RECEIVED_ONLY,
        disclaimer="테스트",
        fraud_types=["account_access_request"],
        summary="테스트",
        actions=[
            Action(code=code, priority=1, title="제목", reason="이유", source_ids=[])
            for code in action_codes
        ],
        official_sources=[],
    )


def test_coverage_alone_cannot_tell_the_right_advice_from_extra_advice() -> None:
    """행동을 **더 붙이는** 수정은 `required_action_coverage` 에서 못 잃는다.

    v0.7 이 등급에서 찾은 것과 같은 모양이다. 바닥만 보는 지표에서는 모든
    문자를 high 로 찍는 엔진이 만점을 받았고, 지금 행동 쪽에서는 열두 행동을
    전부 붙이는 엔진이 만점을 받는다.

    그리고 행동은 등급보다 조용히 나쁘다. 이름을 대지 않은 상대에게
    "공식 대표번호로 확인하세요" 라고 하면 사용자는 존재하지 않는 창구를
    찾다가 결국 **메시지에 적힌 번호**로 건다.
    """
    case = _case_with(
        forbidden=["VERIFY_OFFICIAL_CHANNEL"],
        required=["DO_NOT_SHARE_ACCESS", "VERIFY_BY_KNOWN_CONTACT"],
    )
    right = _response_with(["DO_NOT_SHARE_ACCESS", "VERIFY_BY_KNOWN_CONTACT"])
    everything = _response_with(sorted(ACTION_CODES))

    assert _required_action_coverage([case], [right]) == 1.0
    assert _required_action_coverage([case], [everything]) == 1.0

    assert _forbidden_action_avoidance([case], [right]) == 1.0
    assert _forbidden_action_avoidance([case], [everything]) == 0.0


def test_the_forbidden_action_metric_reports_null_for_sets_that_never_declared_one() -> (
    None
):
    """v0.1~v0.8 은 금지 행동을 선언한 적이 없다. 그 셋들은 통과가 아니라 미측정이다."""
    without = evaluate_golden_set(load_holdout_cases(HOLDOUT_V0_8_PATH))

    assert without["scenario_engine_v0_1"]["forbidden_action_avoidance"] is None  # type: ignore[index]


def test_an_action_cannot_be_both_required_and_forbidden() -> None:
    payload = load_holdout_cases(HOLDOUT_V0_8_PATH)[0].model_dump()
    payload["required_action_codes"] = ["STOP_CONTACT"]
    payload["forbidden_action_codes"] = ["STOP_CONTACT"]

    with pytest.raises(ValueError, match="both required and forbidden"):
        FraudGoldenCase.model_validate(payload)


def test_adding_the_forbidden_label_does_not_move_any_earlier_dataset() -> None:
    """선언하지 않은 라벨은 라벨이 아니다 - v0.7 에서 천장에 적용한 규칙 그대로.

    선택 필드를 하나 더했다고 v0.1~v0.8 의 해시가 바뀌면, 이미 돈을 주고
    받아 둔 판정 결과와 여덟 개 결과 파일의 출처 연결이 전부 끊어진다.
    """
    frozen = {
        HOLDOUT_V0_7_PATH: "15286971f13f",
        HOLDOUT_V0_8_PATH: "9f85da97ebd5",
    }
    for path, prefix in frozen.items():
        cases = load_holdout_cases(path)
        assert normalized_dataset_sha256(cases).startswith(prefix)


def test_v1_0_fh_803_is_a_recorded_label_disagreement_not_a_silent_regression() -> None:
    """두 얼린 셋이 서로 다른 판단을 적어 두었다. **뒤에 적힌 판단을 따른다.**

    v1.0 `fh-803` "이 건은 가족에게 말씀하시면 안 됩니다. 수사 종료까지
    안전계좌로 이체하셔야 합니다" 는 `VERIFY_OFFICIAL_CHANNEL` 을 금지한다.
    v1.1 `fh-901` "본 건은 진행 중인 수사와 관련된 사안입니다 …" 는 같은
    행동을 **요구한다.** 두 문장 다 기관을 자칭하지 않고, 둘 다 수사를
    말하고, 둘 다 고립을 요구한다. 라벨만 반대다.

    이 프로젝트는 이 상황을 이미 한 번 지났다 - v0.7 `fh-523` 과 v0.8
    `fh-627` 이 거의 같은 문장에 반대 라벨을 달았고, `policy.py` 가 "뒤에
    적힌 판단을 따른다" 고 적어 두었다. 같은 규칙을 적용해 v1.1 을 따른다.
    수사 사칭 문자를 받은 사람에게 "이전부터 쓰던 연락처로 확인하세요" 는
    실행할 수 없는 조언이다 - 수사기관과 이전부터 쓰던 연락처는 없다.

    **얼린 라벨은 고치지 않는다.** 대신 그 값이 어디서 나가는지 여기에
    못 박는다. v1.0 의 `forbidden_action_avoidance` 가 1.0 에서 0.9231 로
    내려가 있고, 내려간 자리는 이 한 건이다. 누군가 이 수치를 되돌리려면
    v1.1 의 판단을 먼저 뒤집어야 한다.
    """
    cases = {case.case_id: case for case in load_holdout_cases(HOLDOUT_V1_0_PATH)}
    case = cases["fh-803"]
    emitted = {action.code for action in analyze_fraud(case.request()).actions}

    assert "VERIFY_OFFICIAL_CHANNEL" in case.forbidden_action_codes
    assert "VERIFY_OFFICIAL_CHANNEL" in emitted
    # 나머지는 전부 지켜져 있어야 한다. 알고 있는 불일치는 이 한 건뿐이다.
    assert set(case.required_action_codes) <= emitted
    others = [
        other
        for other in cases.values()
        if other.case_id != "fh-803"
        and {action.code for action in analyze_fraud(other.request()).actions}
        & set(other.forbidden_action_codes)
    ]
    assert others == []
