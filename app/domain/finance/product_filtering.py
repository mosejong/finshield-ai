from app.schemas.financial_profile import FinancialGoal
from app.schemas.product import FinancialProduct
from app.schemas.recommendation import ProductMatchReason, ProductMatchResult


GOAL_PURPOSE_TOKENS: dict[FinancialGoal, tuple[str, ...]] = {
    FinancialGoal.HOUSING: ("주거", "전세", "임대"),
    FinancialGoal.EMERGENCY_CASH: ("생계", "생활", "긴급"),
    FinancialGoal.DEBT_REFINANCE: ("대환", "채무", "상환"),
    FinancialGoal.LIVING_EXPENSE: ("생계", "생활"),
    FinancialGoal.STARTUP_BUSINESS: ("창업", "운영", "운전", "시설", "사업"),
    FinancialGoal.VEHICLE: ("자동차", "차량"),
    FinancialGoal.ASSET_BUILDING: ("자산", "저축", "형성"),
    FinancialGoal.OTHER: (),
}


def filter_product_for_profile(
    product: FinancialProduct,
    goal: FinancialGoal,
) -> ProductMatchResult:
    tokens = GOAL_PURPOSE_TOKENS[goal]
    purpose = product.purpose_text

    if not tokens or not purpose:
        purpose_reason = ProductMatchReason(
            rule="goal_purpose",
            status="needs_review",
            message="공식 용도 정보만으로 사용 목적 일치 여부를 확인할 수 없습니다.",
            source_field="purpose_text",
        )
        status = "needs_review"
    elif any(token in purpose for token in tokens):
        purpose_reason = ProductMatchReason(
            rule="goal_purpose",
            status="potential_match",
            message="사용자 목표와 공식 상품 용도에 공통 범주가 있습니다.",
            source_field="purpose_text",
        )
        status = "potential_match"
    else:
        purpose_reason = ProductMatchReason(
            rule="goal_purpose",
            status="mismatch",
            message="사용자 목표와 공식 상품 용도의 범주가 다릅니다.",
            source_field="purpose_text",
        )
        status = "mismatch"

    eligibility_reason = ProductMatchReason(
        rule="eligibility_manual_review",
        status="needs_review",
        message="나이·소득·신용·지역 등 상세 자격은 공식 원문과 취급기관 확인이 필요합니다.",
        source_field="eligibility",
    )
    return ProductMatchResult(
        status=status,
        product=product,
        reasons=[purpose_reason, eligibility_reason],
    )
