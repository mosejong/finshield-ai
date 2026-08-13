import os
from math import isfinite

from app.clients.public_data_products import (
    DATASET_URL,
    PROVIDER_NAME,
    ProductProviderConfigurationError,
    PublicDataProductClient,
)
from app.core.runtime_secrets import (
    RuntimeSecretConfigurationError,
    read_secret_setting,
)
from app.domain.finance.product_identity import SNAPSHOT_IDENTITY_POLICY
from app.schemas.product import (
    FinancialProduct,
    ProductCatalogIdentity,
    ProductCatalogResponse,
    ProductComparisonResponse,
)
from app.services.product_catalog_snapshot import (
    ProductCatalogSnapshot,
    ProductCatalogSnapshotCache,
    current_seoul_month,
    load_latest_product_snapshot,
)


DEFAULT_CACHE_TTL_SECONDS = 300.0
DEFAULT_LOOKBACK_MONTHS = 36
PRODUCT_COMPARISON_DISCLAIMER = (
    "공식 원문을 나란히 표시한 결과이며 적격성, 승인 가능성, 금리 우열을 "
    "판정하거나 보장하지 않습니다. 최신 조건은 취급기관에서 확인하세요."
)


class ProductNotFoundError(LookupError):
    pass


class ProductCatalogService:
    def __init__(
        self,
        client: PublicDataProductClient,
        *,
        cache: ProductCatalogSnapshotCache | None = None,
        lookback_months: int = DEFAULT_LOOKBACK_MONTHS,
        start_month_provider=current_seoul_month,
    ) -> None:
        if lookback_months < 0 or lookback_months > 120:
            raise ValueError("lookback months must be between 0 and 120")
        self._client = client
        self._cache = cache or ProductCatalogSnapshotCache(
            ttl_seconds=DEFAULT_CACHE_TTL_SECONDS
        )
        self._lookback_months = lookback_months
        self._start_month_provider = start_month_provider

    def list_products(
        self,
        *,
        page_no: int,
        page_size: int,
    ) -> ProductCatalogResponse:
        snapshot = self.get_snapshot()
        start = (page_no - 1) * page_size
        items = list(snapshot.items[start : start + page_size])
        return ProductCatalogResponse(
            provider=PROVIDER_NAME,
            page_no=page_no,
            page_size=page_size,
            total_count=len(snapshot.items),
            source_base_month=snapshot.key.base_month,
            fetched_at=snapshot.fetched_at,
            source_reference=DATASET_URL,
            identity=ProductCatalogIdentity(
                policy=SNAPSHOT_IDENTITY_POLICY,
                source_id_unique=True,
                unique_source_id_count=(snapshot.identity_audit.unique_source_id_count),
                normalized_name_duplicate_groups=(snapshot.identity_audit.normalized_name_duplicate_groups),
                name_only_dedup_applied=False,
            ),
            items=items,
        )

    def get_snapshot(self) -> ProductCatalogSnapshot:
        return self._cache.get_or_load(
            lambda: load_latest_product_snapshot(
                self._client,
                start_month=self._start_month_provider(),
                lookback_months=self._lookback_months,
            )
        )

    def get_product(self, source_product_id: str) -> FinancialProduct:
        snapshot = self.get_snapshot()
        return self._find_product(snapshot, source_product_id)

    def compare_products(
        self,
        product_ids: list[str],
    ) -> ProductComparisonResponse:
        snapshot = self.get_snapshot()
        items = [
            self._find_product(snapshot, source_product_id)
            for source_product_id in product_ids
        ]
        return ProductComparisonResponse(
            provider=snapshot.key.provider,
            source_base_month=snapshot.key.base_month,
            fetched_at=snapshot.fetched_at,
            source_reference=DATASET_URL,
            items=items,
            disclaimer=PRODUCT_COMPARISON_DISCLAIMER,
        )

    @staticmethod
    def _find_product(
        snapshot: ProductCatalogSnapshot,
        source_product_id: str,
    ) -> FinancialProduct:
        for item in snapshot.items:
            if item.source_product_id == source_product_id:
                return item
        raise ProductNotFoundError(source_product_id)


def build_product_catalog_service() -> ProductCatalogService:
    try:
        service_key = read_secret_setting(os.environ, "PUBLIC_DATA_SERVICE_KEY")
    except RuntimeSecretConfigurationError as exc:
        raise ProductProviderConfigurationError(
            "official product provider secret configuration is invalid"
        ) from exc
    ttl_seconds = _read_float_setting(
        "PRODUCT_CATALOG_CACHE_TTL_SECONDS",
        DEFAULT_CACHE_TTL_SECONDS,
    )
    lookback_months = _read_int_setting(
        "PRODUCT_CATALOG_LOOKBACK_MONTHS",
        DEFAULT_LOOKBACK_MONTHS,
        minimum=0,
        maximum=120,
    )
    return ProductCatalogService(
        PublicDataProductClient(service_key),
        cache=ProductCatalogSnapshotCache(ttl_seconds=ttl_seconds),
        lookback_months=lookback_months,
    )


def _read_float_setting(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ProductProviderConfigurationError(f"{name} must be a number") from exc
    if not isfinite(value) or value <= 0:
        raise ProductProviderConfigurationError(
            f"{name} must be greater than zero"
        )
    return value


def _read_int_setting(
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ProductProviderConfigurationError(f"{name} must be an integer") from exc
    if value < minimum or value > maximum:
        raise ProductProviderConfigurationError(
            f"{name} must be between {minimum} and {maximum}"
        )
    return value
