import os

from pydantic import ValidationError

from app.clients.public_data_products import (
    DATASET_URL,
    PROVIDER_NAME,
    ProductProviderResponseError,
    PublicDataProductClient,
)
from app.domain.finance.product_catalog import normalize_public_data_product
from app.schemas.product import ProductCatalogResponse


class ProductCatalogService:
    def __init__(self, client: PublicDataProductClient) -> None:
        self._client = client

    def list_products(
        self,
        *,
        page_no: int,
        page_size: int,
    ) -> ProductCatalogResponse:
        provider_page = self._client.fetch_products(
            page_no=page_no,
            page_size=page_size,
        )
        try:
            items = [
                normalize_public_data_product(
                    row,
                    fetched_at=provider_page.fetched_at,
                )
                for row in provider_page.rows
            ]
        except ValidationError as exc:
            raise ProductProviderResponseError(
                "provider product fields are invalid"
            ) from exc
        return ProductCatalogResponse(
            provider=PROVIDER_NAME,
            page_no=provider_page.page_no,
            page_size=provider_page.page_size,
            total_count=provider_page.total_count,
            fetched_at=provider_page.fetched_at,
            source_reference=DATASET_URL,
            items=items,
        )


def build_product_catalog_service() -> ProductCatalogService:
    service_key = os.getenv("PUBLIC_DATA_SERVICE_KEY", "")
    return ProductCatalogService(PublicDataProductClient(service_key))
