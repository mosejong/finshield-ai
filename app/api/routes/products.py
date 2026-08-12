from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.clients.public_data_products import (
    ProductProviderConfigurationError,
    ProductProviderError,
)
from app.schemas.product import ProductCatalogResponse
from app.services.product_catalog import (
    ProductCatalogService,
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
