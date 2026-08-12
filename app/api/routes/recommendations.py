from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.routes.products import get_product_catalog_service
from app.clients.public_data_products import ProductProviderError
from app.schemas.recommendation import (
    ProductRecommendationRequest,
    ProductRecommendationResponse,
)
from app.services.product_catalog import ProductCatalogService
from app.services.product_recommendation import ProductRecommendationService


router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.post("", response_model=ProductRecommendationResponse)
def recommend_products(
    request: ProductRecommendationRequest,
    catalog_service: Annotated[
        ProductCatalogService, Depends(get_product_catalog_service)
    ],
    page_no: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ProductRecommendationResponse:
    try:
        return ProductRecommendationService(catalog_service).recommend(
            request.goal,
            page_no=page_no,
            page_size=page_size,
        )
    except ProductProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="official product provider is unavailable",
        ) from exc
