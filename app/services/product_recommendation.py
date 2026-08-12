from collections import Counter

from app.domain.finance.product_filtering import filter_product_for_profile
from app.schemas.financial_profile import FinancialGoal
from app.schemas.recommendation import (
    ProductRecommendationResponse,
    ProductRecommendationSummary,
)
from app.services.product_catalog import ProductCatalogService


DISCLAIMER = (
    "이 결과는 공식 상품 용도와 입력 목표를 비교한 후보 분류이며 적격성·승인·금리를 "
    "보장하지 않습니다. 상세 조건은 공식 원문과 취급기관에서 확인하세요."
)


class ProductRecommendationService:
    def __init__(self, catalog_service: ProductCatalogService) -> None:
        self._catalog_service = catalog_service

    def recommend(
        self,
        goal: FinancialGoal,
        *,
        page_no: int,
        page_size: int,
    ) -> ProductRecommendationResponse:
        snapshot = self._catalog_service.get_snapshot()
        results = [
            filter_product_for_profile(product, goal) for product in snapshot.items
        ]
        order = {"potential_match": 0, "needs_review": 1, "mismatch": 2}
        results.sort(key=lambda result: (order[result.status], result.product.source_product_id))
        counts = Counter(result.status for result in results)
        start = (page_no - 1) * page_size
        return ProductRecommendationResponse(
            provider=snapshot.key.provider,
            source_base_month=snapshot.key.base_month,
            total_count=len(results),
            page_no=page_no,
            page_size=page_size,
            summary=ProductRecommendationSummary(
                potential_match=counts["potential_match"],
                mismatch=counts["mismatch"],
                needs_review=counts["needs_review"],
            ),
            disclaimer=DISCLAIMER,
            results=results[start : start + page_size],
        )
