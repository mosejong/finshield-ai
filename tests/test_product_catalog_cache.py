from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event, Lock

import httpx
import pytest

from app.clients.public_data_products import (
    DATASET_URL,
    PROVIDER_NAME,
    ProviderProductPage,
    ProductProviderConfigurationError,
    ProductProviderResponseError,
    PublicDataProductClient,
)
from app.services.product_catalog import (
    ProductCatalogService,
    build_product_catalog_service,
)
from app.services.product_catalog_snapshot import (
    ACTIVE_PRODUCT_QUERY,
    ProductCatalogSnapshot,
    ProductCatalogSnapshotCache,
    ProductCatalogSnapshotKey,
    load_latest_product_snapshot,
)


def provider_payload(
    *,
    rows: list[dict],
    total_count: int,
    page_no: int = 1,
    page_size: int = 100,
) -> dict:
    return {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
            "body": {
                "numOfRows": page_size,
                "pageNo": page_no,
                "totalCount": total_count,
                "items": {"item": rows},
            },
        }
    }


def row(sequence: int) -> dict:
    return {
        "basYm": "202607",
        "snq": str(sequence),
        "finPrdNm": f"공식 상품 {sequence}",
        "prdExisYn": "Y",
    }


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def empty_snapshot() -> ProductCatalogSnapshot:
    return ProductCatalogSnapshot(
        key=ProductCatalogSnapshotKey(
            provider=PROVIDER_NAME,
            base_month="202607",
            query=ACTIVE_PRODUCT_QUERY,
            page_scope="all",
        ),
        fetched_at=datetime.now(timezone.utc),
        items=(),
    )


def catalog_service(
    handler,
    *,
    cache: ProductCatalogSnapshotCache | None = None,
) -> tuple[ProductCatalogService, httpx.Client]:
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    return (
        ProductCatalogService(
            PublicDataProductClient("test-key", client=http_client),
            cache=cache,
            start_month_provider=lambda: "202608",
        ),
        http_client,
    )


def test_service_caches_latest_full_snapshot_and_paginates_locally() -> None:
    calls: list[tuple[str, int, int]] = []
    rows = [row(1), row(2), row(3)]

    def handler(request: httpx.Request) -> httpx.Response:
        month = request.url.params["basYm"]
        page_no = int(request.url.params["pageNo"])
        page_size = int(request.url.params["numOfRows"])
        calls.append((month, page_no, page_size))
        if month == "202608":
            return httpx.Response(
                200,
                json=provider_payload(
                    rows=[], total_count=0, page_no=page_no, page_size=page_size
                ),
            )
        response_rows = rows[:1] if page_size == 1 else rows
        return httpx.Response(
            200,
            json=provider_payload(
                rows=response_rows,
                total_count=3,
                page_no=page_no,
                page_size=page_size,
            ),
        )

    service, http_client = catalog_service(handler)
    try:
        first = service.list_products(page_no=1, page_size=2)
        second = service.list_products(page_no=2, page_size=2)
    finally:
        http_client.close()

    assert calls == [
        ("202608", 1, 1),
        ("202607", 1, 1),
        ("202607", 1, 100),
    ]
    assert first.total_count == second.total_count == 3
    assert first.source_base_month == second.source_base_month == "202607"
    assert [item.source_product_id for item in first.items] == [
        "202607:1",
        "202607:2",
    ]
    assert [item.source_product_id for item in second.items] == ["202607:3"]
    assert first.fetched_at == second.fetched_at
    assert str(first.source_reference) == DATASET_URL


def test_cache_refreshes_only_after_ttl() -> None:
    clock = FakeClock()
    cache = ProductCatalogSnapshotCache(ttl_seconds=10, clock=clock)
    load_count = 0

    def loader() -> ProductCatalogSnapshot:
        nonlocal load_count
        load_count += 1
        return empty_snapshot()

    first = cache.get_or_load(loader)
    clock.value = 9.99
    assert cache.get_or_load(loader) is first
    assert load_count == 1

    clock.value = 10.0
    second = cache.get_or_load(loader)
    assert second is not first
    assert load_count == 2


def test_cache_prevents_concurrent_refresh_stampede() -> None:
    cache = ProductCatalogSnapshotCache(ttl_seconds=60)
    release_loader = Event()
    count_lock = Lock()
    load_count = 0

    def loader() -> ProductCatalogSnapshot:
        nonlocal load_count
        with count_lock:
            load_count += 1
        assert release_loader.wait(timeout=5)
        return empty_snapshot()

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(cache.get_or_load, loader) for _ in range(8)]
        release_loader.set()
        snapshots = [future.result(timeout=5) for future in futures]

    assert load_count == 1
    assert all(snapshot is snapshots[0] for snapshot in snapshots)


def test_failed_refresh_is_not_cached_as_an_empty_snapshot() -> None:
    cache = ProductCatalogSnapshotCache(ttl_seconds=60)
    load_count = 0

    def loader() -> ProductCatalogSnapshot:
        nonlocal load_count
        load_count += 1
        if load_count == 1:
            raise ProductProviderResponseError("temporary provider failure")
        return empty_snapshot()

    with pytest.raises(ProductProviderResponseError):
        cache.get_or_load(loader)

    snapshot = cache.get_or_load(loader)
    assert snapshot.key.base_month == "202607"
    assert cache.get_or_load(loader) is snapshot
    assert load_count == 2


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("PRODUCT_CATALOG_CACHE_TTL_SECONDS", "0"),
        ("PRODUCT_CATALOG_CACHE_TTL_SECONDS", "not-a-number"),
        ("PRODUCT_CATALOG_CACHE_TTL_SECONDS", "nan"),
        ("PRODUCT_CATALOG_CACHE_TTL_SECONDS", "inf"),
        ("PRODUCT_CATALOG_LOOKBACK_MONTHS", "121"),
        ("PRODUCT_CATALOG_LOOKBACK_MONTHS", "1.5"),
    ],
)
def test_invalid_cache_configuration_is_explicit(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
) -> None:
    monkeypatch.setenv("PUBLIC_DATA_SERVICE_KEY", "test-key")
    monkeypatch.setenv(name, value)

    with pytest.raises(ProductProviderConfigurationError):
        build_product_catalog_service()


class SnapshotClient:
    def __init__(self, pages: dict[tuple[str, int, int], ProviderProductPage]) -> None:
        self.pages = pages

    def fetch_products(
        self,
        *,
        page_no: int,
        page_size: int,
        base_month: str | None = None,
    ) -> ProviderProductPage:
        assert base_month is not None
        return self.pages[(base_month, page_no, page_size)]


def provider_page(
    *,
    rows: list[dict],
    total_count: int,
    page_no: int = 1,
    page_size: int = 100,
) -> ProviderProductPage:
    return ProviderProductPage(
        rows=rows,
        page_no=page_no,
        page_size=page_size,
        total_count=total_count,
        fetched_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
    )


def test_snapshot_loader_collects_every_page_with_explicit_identity() -> None:
    client = SnapshotClient(
        {
            ("202608", 1, 1): provider_page(rows=[], total_count=0, page_size=1),
            ("202607", 1, 1): provider_page(
                rows=[row(1)], total_count=3, page_size=1
            ),
            ("202607", 1, 2): provider_page(
                rows=[row(1), row(2)], total_count=3, page_size=2
            ),
            ("202607", 2, 2): provider_page(
                rows=[row(3)], total_count=3, page_no=2, page_size=2
            ),
        }
    )

    snapshot = load_latest_product_snapshot(
        client,
        start_month="202608",
        lookback_months=1,
        provider_page_size=2,
    )

    assert snapshot.key == ProductCatalogSnapshotKey(
        provider=PROVIDER_NAME,
        base_month="202607",
        query=ACTIVE_PRODUCT_QUERY,
        page_scope="all",
    )
    assert [item.source_product_id for item in snapshot.items] == [
        "202607:1",
        "202607:2",
        "202607:3",
    ]
    assert all(item.fetched_at == snapshot.fetched_at for item in snapshot.items)


def test_snapshot_loader_rejects_total_count_changes() -> None:
    client = SnapshotClient(
        {
            ("202607", 1, 1): provider_page(
                rows=[row(1)], total_count=3, page_size=1
            ),
            ("202607", 1, 2): provider_page(
                rows=[row(1), row(2)], total_count=3, page_size=2
            ),
            ("202607", 2, 2): provider_page(
                rows=[row(3)], total_count=4, page_no=2, page_size=2
            ),
        }
    )

    with pytest.raises(ProductProviderResponseError):
        load_latest_product_snapshot(
            client,
            start_month="202607",
            lookback_months=0,
            provider_page_size=2,
        )


def test_snapshot_loader_rejects_mixed_base_month_rows() -> None:
    mismatched = {**row(1), "basYm": "202606"}
    client = SnapshotClient(
        {
            ("202607", 1, 1): provider_page(
                rows=[mismatched], total_count=1, page_size=1
            ),
            ("202607", 1, 100): provider_page(
                rows=[mismatched], total_count=1
            ),
        }
    )

    with pytest.raises(ProductProviderResponseError):
        load_latest_product_snapshot(
            client,
            start_month="202607",
            lookback_months=0,
        )
