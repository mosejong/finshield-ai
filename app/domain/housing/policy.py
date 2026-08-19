"""전세보증금 위험 점검의 규칙부.

구조는 `app/domain/fraud/policy.py` 와 같다. 신호 하나에 최소 위험 수준 하나,
단계 하나에 최소 위험 수준 하나를 붙이고 **가장 높은 것을 채택한다.** 어느
근거도 다른 근거를 낮추지 못한다.

사기 분석에서 이미 검증된 모양을 그대로 쓰는 이유는 단순하다. 두 화면이 같은
방식으로 결론을 내면 사용자가 한 번만 이해하면 되고, 나중에 임계값을 손볼 때
바꿔야 할 곳이 한 종류다.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.domain.housing.deposit_risk import (
    ELEVATED_RATIO_PERCENT,
    HIGH_RATIO_PERCENT,
    OCCUPIED_STAGES,
    ProtectionResult,
    RatioResult,
)
from app.schemas.housing import (
    DepositCheck,
    DepositRiskAction,
    DepositRiskSignal,
    LeaseStage,
)


RISK_RANK = {"low": 0, "medium": 1, "high": 2}


@dataclass(frozen=True)
class ActionPolicy:
    priority: int
    title: str
    reason: str
    source_ids: tuple[str, ...]


ACTION_POLICIES: dict[str, ActionPolicy] = {
    "CHECK_REGISTRY": ActionPolicy(
        1,
        "등기부등본을 직접 떼어 확인하세요",
        "소유자, 근저당권 등 선순위 권리는 등기부에서만 확인할 수 있습니다. "
        "상대방이 보여 주는 사본이 아니라 직접 발급받은 것을 보세요.",
        ("easylaw_property_registry",),
    ),
    "VERIFY_OWNER_IDENTITY": ActionPolicy(
        1,
        "계약 상대가 등기부상 소유자인지 확인하세요",
        "등기부의 소유자와 계약서에 서명하는 사람이 다르면 대리권이 있는지 "
        "함께 확인해야 합니다.",
        ("easylaw_property_registry",),
    ),
    "REPORT_MOVE_IN": ActionPolicy(
        1,
        "입주 후 곧바로 전입신고를 하세요",
        "주택임대차보호법 제3조 제1항은 주택의 인도와 주민등록을 마친 때 "
        "그 다음 날부터 대항력이 생긴다고 정하고 있습니다.",
        ("housing_lease_act_article3", "easylaw_opposing_power"),
    ),
    "GET_CONFIRMED_DATE": ActionPolicy(
        1,
        "임대차계약서에 확정일자를 받으세요",
        "대항요건과 확정일자를 함께 갖추어야 우선변제권 요건이 충족됩니다.",
        ("easylaw_opposing_power",),
    ),
    "JOIN_DEPOSIT_GUARANTEE": ActionPolicy(
        2,
        "전세보증금반환보증 가입 조건을 확인하세요",
        "주택도시보증공사(HUG)가 전세보증금반환보증을 운영합니다. "
        "가입 대상과 조건은 기관 안내에서 직접 확인하세요.",
        ("khug_deposit_return_guarantee",),
    ),
    "KEEP_OPPOSING_POWER": ActionPolicy(
        1,
        "보증금을 돌려받기 전에는 전출하지 마세요",
        "대항요건은 주민등록을 유지하는 동안 유지됩니다. 먼저 이사해야 한다면 "
        "임차권등기명령 절차를 확인한 뒤에 움직이세요.",
        ("housing_lease_act_article3", "easylaw_lease_registration_order"),
    ),
    "APPLY_LEASE_REGISTRATION_ORDER": ActionPolicy(
        1,
        "임차권등기명령 신청을 검토하세요",
        "임대차가 끝난 뒤 보증금을 돌려받지 못한 경우 신청할 수 있으며, "
        "등기 후에는 이사하더라도 이미 취득한 대항력과 우선변제권이 유지됩니다.",
        ("easylaw_lease_registration_order",),
    ),
    "CHECK_VICTIM_SUPPORT": ActionPolicy(
        2,
        "전세사기피해자 지원 요건에 해당하는지 확인하세요",
        "전세사기피해자 지원 및 주거안정에 관한 특별법 제3조가 요건을 정하고 "
        "있습니다. 해당 여부는 이 서비스가 판단하지 않습니다.",
        ("jeonse_fraud_victim_act_article3",),
    ),
}


# 단계별로 항상 안내할 행동. 신호가 하나도 없어도 남는다.
STAGE_ACTIONS: dict[LeaseStage, tuple[str, ...]] = {
    LeaseStage.BEFORE_CONTRACT: ("CHECK_REGISTRY", "VERIFY_OWNER_IDENTITY"),
    LeaseStage.CONTRACT_SIGNED: (
        "CHECK_REGISTRY",
        "VERIFY_OWNER_IDENTITY",
        "JOIN_DEPOSIT_GUARANTEE",
    ),
    LeaseStage.BALANCE_PAID: (
        "REPORT_MOVE_IN",
        "GET_CONFIRMED_DATE",
        "JOIN_DEPOSIT_GUARANTEE",
    ),
    LeaseStage.MOVED_IN: ("KEEP_OPPOSING_POWER", "JOIN_DEPOSIT_GUARANTEE"),
    LeaseStage.LEASE_ENDING: ("KEEP_OPPOSING_POWER",),
    LeaseStage.DEPOSIT_UNRETURNED: (
        "KEEP_OPPOSING_POWER",
        "APPLY_LEASE_REGISTRATION_ORDER",
        "CHECK_VICTIM_SUPPORT",
    ),
}

SIGNAL_ACTIONS: dict[str, tuple[str, ...]] = {
    "high_debt_ratio": ("JOIN_DEPOSIT_GUARANTEE",),
    "elevated_debt_ratio": ("JOIN_DEPOSIT_GUARANTEE",),
    "property_price_unknown": (),
    "senior_lien_unknown": ("CHECK_REGISTRY",),
    "registry_not_checked": ("CHECK_REGISTRY",),
    "owner_identity_unverified": ("VERIFY_OWNER_IDENTITY",),
    "opposing_power_missing": ("REPORT_MOVE_IN", "GET_CONFIRMED_DATE"),
    "priority_repayment_missing": ("GET_CONFIRMED_DATE",),
    "deposit_guarantee_absent": ("JOIN_DEPOSIT_GUARANTEE",),
    "deposit_unreturned": (
        "KEEP_OPPOSING_POWER",
        "APPLY_LEASE_REGISTRATION_ORDER",
        "CHECK_VICTIM_SUPPORT",
    ),
}

SIGNAL_MINIMUM_RISK: dict[str, str] = {
    "high_debt_ratio": "high",
    "elevated_debt_ratio": "medium",
    "property_price_unknown": "medium",
    "senior_lien_unknown": "medium",
    "registry_not_checked": "medium",
    "owner_identity_unverified": "medium",
    # 잔금을 치르고 입주까지 했는데 전입신고가 없다는 것은 보증금 전액이
    # 아무 대항력 없이 놓여 있다는 뜻이다. 되돌릴 수 없는 금액에 붙는 신호다.
    "opposing_power_missing": "high",
    "priority_repayment_missing": "medium",
    "deposit_guarantee_absent": "medium",
    "deposit_unreturned": "high",
}

# 단계 자체가 만드는 최소 위험 수준.
# BALANCE_PAID 만 medium 인 이유: 잔금이 이미 나갔는데 대항력·우선변제권이
# 아직 확정되지 않은 유일한 구간이다. MOVED_IN 은 그 절차를 마친 상태이므로
# 단계만으로 위험을 올리지 않는다 — 올리면 잘 처리한 사용자를 겁준다.
# 보증 가입이 아직 선택지로 남아 있는 단계.
# 계약 전에는 가입할 계약이 없고, 미반환이 발생한 뒤에는 이미 일어난 손실을
# 보증으로 되돌릴 수 없다. 두 끝에서 "가입하지 않았다" 는 신호는 사실이지만
# 할 수 있는 일이 아니므로 띄우지 않는다.
GUARANTEE_RELEVANT_STAGES: frozenset[LeaseStage] = frozenset(
    {
        LeaseStage.CONTRACT_SIGNED,
        LeaseStage.BALANCE_PAID,
        LeaseStage.MOVED_IN,
        LeaseStage.LEASE_ENDING,
    }
)

STAGE_MINIMUM_RISK: dict[LeaseStage, str] = {
    LeaseStage.BEFORE_CONTRACT: "low",
    LeaseStage.CONTRACT_SIGNED: "low",
    LeaseStage.BALANCE_PAID: "medium",
    LeaseStage.MOVED_IN: "low",
    LeaseStage.LEASE_ENDING: "low",
    LeaseStage.DEPOSIT_UNRETURNED: "high",
}

# 같은 우선순위 안에서의 나열 순서. 알파벳순으로 두면 "확정일자" 가
# "전입신고" 보다 앞에 온다. 대항요건이 먼저 서야 그 위에 확정일자가 얹히므로
# 절차 순서를 코드로 고정한다.
ACTION_ORDER: tuple[str, ...] = (
    "CHECK_REGISTRY",
    "VERIFY_OWNER_IDENTITY",
    "REPORT_MOVE_IN",
    "GET_CONFIRMED_DATE",
    "KEEP_OPPOSING_POWER",
    "APPLY_LEASE_REGISTRATION_ORDER",
    "JOIN_DEPOSIT_GUARANTEE",
    "CHECK_VICTIM_SUPPORT",
)

COMPLETED_CHECK_ACTIONS: dict[DepositCheck, str] = {
    DepositCheck.REGISTRY_CHECKED: "CHECK_REGISTRY",
    DepositCheck.OWNER_IDENTITY_VERIFIED: "VERIFY_OWNER_IDENTITY",
    DepositCheck.MOVE_IN_REPORTED: "REPORT_MOVE_IN",
    DepositCheck.CONFIRMED_DATE_OBTAINED: "GET_CONFIRMED_DATE",
    DepositCheck.DEPOSIT_GUARANTEE_JOINED: "JOIN_DEPOSIT_GUARANTEE",
}

SIGNAL_LABELS: dict[str, str] = {
    "high_debt_ratio": "주택가격 대비 보증금·선순위 채권 비중이 큽니다",
    "elevated_debt_ratio": "주택가격 대비 보증금·선순위 채권 비중이 낮지 않습니다",
    "property_price_unknown": "주택가격을 입력하지 않아 비율을 계산하지 못했습니다",
    "senior_lien_unknown": "선순위 채권최고액을 확인하지 않았습니다",
    "registry_not_checked": "등기부등본을 확인하지 않았습니다",
    "owner_identity_unverified": "계약 상대가 등기부상 소유자인지 확인하지 않았습니다",
    "opposing_power_missing": "입주했는데 전입신고가 확인되지 않습니다",
    "priority_repayment_missing": "확정일자가 확인되지 않습니다",
    "deposit_guarantee_absent": "전세보증금반환보증에 가입하지 않았습니다",
    "deposit_unreturned": "계약이 끝났는데 보증금을 돌려받지 못했습니다",
}


def _ratio_signals(ratio: RatioResult, has_price: bool, has_lien: bool) -> list[str]:
    if ratio.band == "high":
        return ["high_debt_ratio"]
    if ratio.band == "elevated":
        return ["elevated_debt_ratio"]
    if ratio.band == "low":
        return []

    codes: list[str] = []
    if not has_price:
        codes.append("property_price_unknown")
    if not has_lien:
        codes.append("senior_lien_unknown")
    return codes


def detect_signals(
    stage: LeaseStage,
    completed_checks: set[DepositCheck],
    ratio: RatioResult,
    protection: ProtectionResult,
    *,
    has_price: bool,
    has_lien: bool,
) -> list[DepositRiskSignal]:
    """입력과 계산 결과에서 신호 코드를 뽑는다.

    순서는 코드 정의 순서가 아니라 아래 나열 순서를 따른다. 화면이 이 순서를
    그대로 쓰므로, 돈에 직접 걸린 것(비율·대항력)을 먼저 둔다.
    """
    codes: list[str] = []

    if stage is LeaseStage.DEPOSIT_UNRETURNED:
        codes.append("deposit_unreturned")

    codes.extend(_ratio_signals(ratio, has_price, has_lien))

    if stage in OCCUPIED_STAGES and not protection.has_opposing_power_requirements:
        codes.append("opposing_power_missing")
    elif (
        protection.has_opposing_power_requirements
        and not protection.has_priority_repayment_requirements
    ):
        codes.append("priority_repayment_missing")

    if DepositCheck.REGISTRY_CHECKED not in completed_checks:
        codes.append("registry_not_checked")
    if DepositCheck.OWNER_IDENTITY_VERIFIED not in completed_checks:
        codes.append("owner_identity_unverified")

    # 보증 미가입은 그 자체로 위험이 아니다. 비율이 낮지 않거나 계산조차 안 될
    # 때만 신호로 올린다. 아니면 잘 계약한 사람에게도 늘 경고가 붙는다.
    if (
        DepositCheck.DEPOSIT_GUARANTEE_JOINED not in completed_checks
        and ratio.band in {"unknown", "elevated", "high"}
        and stage in GUARANTEE_RELEVANT_STAGES
    ):
        codes.append("deposit_guarantee_absent")

    return [
        DepositRiskSignal(
            code=code,
            label=SIGNAL_LABELS[code],
            detail=_signal_detail(code, ratio, protection),
        )
        for code in codes
    ]


def _signal_detail(
    code: str, ratio: RatioResult, protection: ProtectionResult
) -> str:
    if code == "high_debt_ratio":
        return (
            f"계산된 비율은 {_format_ratio(ratio.ratio_percent)}%입니다. "
            f"이 서비스는 {HIGH_RATIO_PERCENT}%를 넘으면 높은 구간으로 봅니다. "
            "공식 기준이 아니라 이 서비스의 보수적 기준입니다."
        )
    if code == "elevated_debt_ratio":
        return (
            f"계산된 비율은 {_format_ratio(ratio.ratio_percent)}%입니다. "
            f"이 서비스는 {ELEVATED_RATIO_PERCENT}%를 넘으면 낮지 않은 구간으로 "
            "봅니다. 공식 기준이 아니라 이 서비스의 보수적 기준입니다."
        )
    if code == "property_price_unknown":
        return "주택가격이 없으면 보증금이 차지하는 비중을 계산할 수 없습니다."
    if code == "senior_lien_unknown":
        return (
            "선순위 채권최고액을 0으로 두고 계산하면 실제보다 안전해 보입니다. "
            "그래서 계산하지 않고 확인을 먼저 안내합니다."
        )
    if code == "opposing_power_missing":
        return (
            "주택임대차보호법 제3조 제1항의 대항요건은 주택의 인도와 주민등록 "
            "둘 다입니다. 전입신고 전에는 보증금이 대항력 없이 놓여 있습니다."
        )
    if code == "priority_repayment_missing":
        return (
            "대항요건은 갖추었지만 확정일자가 없습니다. 우선변제권 요건은 "
            "대항요건과 확정일자를 함께 갖춘 경우에 충족됩니다."
        )
    if code == "deposit_guarantee_absent":
        return "보증금 반환을 보장하는 별도 장치가 확인되지 않았습니다."
    if code == "deposit_unreturned":
        return "이미 발생한 미반환 상태이므로 예방이 아니라 회수 절차 단계입니다."
    if code == "registry_not_checked":
        return "선순위 권리와 소유자는 등기부에서만 확인됩니다."
    return "계약 상대의 권한을 확인하지 않은 상태입니다."


def _format_ratio(value: Decimal | None) -> str:
    return "-" if value is None else f"{value.normalize():f}"


def determine_risk_level(
    signals: list[DepositRiskSignal], stage: LeaseStage
) -> str:
    """신호와 단계 중 가장 높은 위험 수준을 채택한다.

    점수는 만들지 않는다. 사기 분석과 달리 여기에는 가중치를 조정할 근거가
    될 실측 데이터가 아직 없다. 없는 정밀도를 숫자로 흉내 내지 않는다.
    """
    level = STAGE_MINIMUM_RISK[stage]
    for signal in signals:
        minimum = SIGNAL_MINIMUM_RISK[signal.code]
        if RISK_RANK[minimum] > RISK_RANK[level]:
            level = minimum
    return level


def select_actions(
    signals: list[DepositRiskSignal],
    stage: LeaseStage,
    completed_checks: set[DepositCheck],
) -> list[DepositRiskAction]:
    action_codes: set[str] = set(STAGE_ACTIONS[stage])
    for signal in signals:
        action_codes.update(SIGNAL_ACTIONS[signal.code])

    # 비율 신호도 보증 가입을 부른다. 단계가 그것을 허용하지 않으면 여기서 뺀다.
    if stage not in GUARANTEE_RELEVANT_STAGES:
        action_codes.discard("JOIN_DEPOSIT_GUARANTEE")

    # 이미 마친 것은 다시 시키지 않는다. 끝난 일이 할 일 목록에 남아 있으면
    # 목록 전체의 신뢰도가 떨어지고, 진짜 남은 일이 묻힌다.
    for check, satisfied_action in COMPLETED_CHECK_ACTIONS.items():
        if check in completed_checks:
            action_codes.discard(satisfied_action)

    ordered = sorted(
        action_codes,
        key=lambda code: (ACTION_POLICIES[code].priority, ACTION_ORDER.index(code)),
    )
    return [
        DepositRiskAction(
            code=code,
            priority=ACTION_POLICIES[code].priority,
            title=ACTION_POLICIES[code].title,
            reason=ACTION_POLICIES[code].reason,
            source_ids=list(ACTION_POLICIES[code].source_ids),
        )
        for code in ordered
    ]
