from datetime import datetime, timezone

from app.domain.finance.product_catalog import normalize_public_data_product
from app.domain.finance.product_filtering import filter_product_for_profile
from app.schemas.financial_profile import FinancialGoal


def product(purpose: str | None):
    row = {
        "basYm": "202607",
        "snq": "1",
        "finPrdNm": "공식 상품",
        "prdExisYn": "Y",
    }
    if purpose is not None:
        row["usge"] = purpose
    return normalize_public_data_product(
        row,
        fetched_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
    )


def test_matching_official_purpose_is_only_a_potential_match() -> None:
    result = filter_product_for_profile(product("주거"), FinancialGoal.HOUSING)

    assert result.status == "potential_match"
    assert result.reasons[0].source_field == "purpose_text"
    assert result.reasons[1].status == "needs_review"


def test_different_official_purpose_is_mismatch() -> None:
    result = filter_product_for_profile(product("창업"), FinancialGoal.HOUSING)
    assert result.status == "mismatch"


def test_missing_purpose_or_other_goal_needs_review() -> None:
    assert filter_product_for_profile(product(None), FinancialGoal.HOUSING).status == "needs_review"
    assert filter_product_for_profile(product("주거"), FinancialGoal.OTHER).status == "needs_review"
