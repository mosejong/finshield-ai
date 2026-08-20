from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from threading import Lock
from time import monotonic

from pydantic import ValidationError

from app.clients.public_data_products import (
    DATASET_URL,
    PROVIDER_NAME,
    ProductProviderResponseError,
    PublicDataProductClient,
)
from app.core.clock import SEOUL
from app.domain.finance.product_identity import (
    ProductCatalogIdentityAudit,
    audit_product_catalog_identity,
)
from app.domain.finance.product_catalog import normalize_public_data_product
from app.schemas.product import FinancialProduct


ACTIVE_PRODUCT_QUERY = "active:Y"


@dataclass(frozen=True)
class ProductCatalogSnapshotKey:
    provider: str
    base_month: str
    query: str
    page_scope: str


@dataclass(frozen=True)
class ProductCatalogSnapshot:
    key: ProductCatalogSnapshotKey
    fetched_at: datetime
    items: tuple[FinancialProduct, ...]
    identity_audit: ProductCatalogIdentityAudit


@dataclass(frozen=True)
class _CacheEntry:
    snapshot: ProductCatalogSnapshot
    expires_at: float


class ProductCatalogSnapshotCache:
    """Process-local, thread-safe cache for one latest official snapshot."""

    def __init__(
        self,
        *,
        ttl_seconds: float,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if not isfinite(ttl_seconds) or ttl_seconds <= 0:
            raise ValueError("cache TTL must be greater than zero")
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._lock = Lock()
        self._entry: _CacheEntry | None = None

    def get_or_load(
        self,
        loader: Callable[[], ProductCatalogSnapshot],
    ) -> ProductCatalogSnapshot:
        # The loader runs under the lock. This intentionally trades one blocked
        # request group for exactly one official-provider refresh on cache expiry.
        with self._lock:
            now = self._clock()
            if self._entry is not None and now < self._entry.expires_at:
                return self._entry.snapshot

            snapshot = loader()
            self._entry = _CacheEntry(
                snapshot=snapshot,
                expires_at=self._clock() + self._ttl_seconds,
            )
            return snapshot


def previous_month(value: str) -> str:
    year = int(value[:4])
    month = int(value[4:])
    if month == 1:
        return f"{year - 1:04d}12"
    return f"{year:04d}{month - 1:02d}"


def current_seoul_month() -> str:
    return datetime.now(SEOUL).strftime("%Y%m")


def discover_latest_month(
    client: PublicDataProductClient,
    *,
    start_month: str,
    lookback_months: int,
) -> str:
    candidate = start_month
    for _ in range(lookback_months + 1):
        page = client.fetch_products(
            page_no=1,
            page_size=1,
            base_month=candidate,
        )
        if page.total_count > 0:
            return candidate
        candidate = previous_month(candidate)
    raise ProductProviderResponseError(
        "no active official products found in the lookback window"
    )


def load_latest_product_snapshot(
    client: PublicDataProductClient,
    *,
    start_month: str,
    lookback_months: int,
    provider_page_size: int = 100,
) -> ProductCatalogSnapshot:
    base_month = discover_latest_month(
        client,
        start_month=start_month,
        lookback_months=lookback_months,
    )
    rows = []
    page_no = 1
    total_count: int | None = None
    fetched_at: datetime | None = None

    while total_count is None or len(rows) < total_count:
        page = client.fetch_products(
            page_no=page_no,
            page_size=provider_page_size,
            base_month=base_month,
        )
        if page.page_no != page_no:
            raise ProductProviderResponseError(
                "provider page number changed during snapshot collection"
            )
        if total_count is None:
            total_count = page.total_count
            fetched_at = page.fetched_at
        elif page.total_count != total_count:
            raise ProductProviderResponseError(
                "provider totalCount changed during snapshot collection"
            )
        if not page.rows and len(rows) < total_count:
            raise ProductProviderResponseError(
                "provider returned an empty page before snapshot completion"
            )
        rows.extend(page.rows)
        page_no += 1

    if fetched_at is None or total_count is None or len(rows) != total_count:
        raise ProductProviderResponseError(
            "provider snapshot row count is inconsistent"
        )

    try:
        items = tuple(
            normalize_public_data_product(row, fetched_at=fetched_at) for row in rows
        )
    except ValidationError as exc:
        raise ProductProviderResponseError(
            "provider product fields are invalid"
        ) from exc

    identity_audit = audit_product_catalog_identity(
        items,
        provider=PROVIDER_NAME,
        base_month=base_month,
        fetched_at=fetched_at,
        source_reference=DATASET_URL,
    )

    return ProductCatalogSnapshot(
        key=ProductCatalogSnapshotKey(
            provider=PROVIDER_NAME,
            base_month=base_month,
            query=ACTIVE_PRODUCT_QUERY,
            page_scope="all",
        ),
        fetched_at=fetched_at,
        items=items,
        identity_audit=identity_audit,
    )
