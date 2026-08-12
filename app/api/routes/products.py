from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.clients.public_data_products import (
    ProductProviderConfigurationError,
    ProductProviderError,
)
from app.schemas.product import (
    FinancialProduct,
    ProductCatalogResponse,
    ProductComparisonRequest,
    ProductComparisonResponse,
)
from app.services.product_catalog import (
    ProductCatalogService,
    ProductNotFoundError,
    build_product_catalog_service,
)


router = APIRouter(prefix="/products", tags=["products"])


@lru_cache(maxsize=1)
def get_product_catalog_service() -> ProductCatalogService:
    try:
        return build_product_catalog_service()
    except ProductProviderConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="official product provider is not configured",
        ) from exc


@router.get("", response_model=ProductCatalogResponse)
def list_products(
    service: Annotated[ProductCatalogService, Depends(get_product_catalog_service)],
    page_no: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ProductCatalogResponse:
    try:
        return service.list_products(page_no=page_no, page_size=page_size)
    except ProductProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="official product provider is unavailable",
        ) from exc


@router.post("/compare", response_model=ProductComparisonResponse)
def compare_products(
    request: ProductComparisonRequest,
    service: Annotated[ProductCatalogService, Depends(get_product_catalog_service)],
) -> ProductComparisonResponse:
    try:
        return service.compare_products(request.product_ids)
    except ProductNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="official product was not found in the latest snapshot",
        ) from exc
    except ProductProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="official product provider is unavailable",
        ) from exc


@router.get("/{source_product_id}", response_model=FinancialProduct)
def get_product(
    service: Annotated[ProductCatalogService, Depends(get_product_catalog_service)],
    source_product_id: Annotated[
        str,
        Path(pattern=r"^\d{6}:\d+$", min_length=8, max_length=100),
    ],
) -> FinancialProduct:
    try:
        return service.get_product(source_product_id)
    except ProductNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="official product was not found in the latest snapshot",
        ) from exc
    except ProductProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="official product provider is unavailable",
        ) from exc
