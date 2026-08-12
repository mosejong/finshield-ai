from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.routes.products import get_product_catalog_service
from app.clients.public_data_products import PROVIDER_NAME
from app.domain.finance.product_catalog import normalize_public_data_product
from app.domain.finance.product_identity import ProductCatalogIdentityAudit
from app.main import app
from app.services.product_catalog import ProductCatalogService
from app.services.product_catalog_snapshot import (
    ACTIVE_PRODUCT_QUERY,
    ProductCatalogSnapshot,
    ProductCatalogSnapshotKey,
)


FETCHED_AT = datetime(2026, 8, 12, tzinfo=timezone.utc)


def make_product(sequence: int, name: str):
    return normalize_public_data_product(
        {
            "basYm": "202607",
            "snq": str(sequence),
            "finPrdNm": name,
            "irt": f"{sequence}.5%",
            "lnLmt": f"{sequence}000만원",
            "trgt": "공식 대상 원문",
            "prdExisYn": "Y",
        },
        fetched_at=FETCHED_AT,
    )


class DetailCatalogStub(ProductCatalogService):
    def __init__(self) -> None:
        self.calls = 0

    def get_snapshot(self) -> ProductCatalogSnapshot:
        self.calls += 1
        return ProductCatalogSnapshot(
            key=ProductCatalogSnapshotKey(
                provider=PROVIDER_NAME,
                base_month="202607",
                query=ACTIVE_PRODUCT_QUERY,
                page_scope="all",
            ),
            fetched_at=FETCHED_AT,
            items=(make_product(1, "첫 상품"), make_product(2, "둘째 상품")),
            identity_audit=ProductCatalogIdentityAudit(2, 0),
        )


def test_product_detail_returns_exact_source_id() -> None:
    service = DetailCatalogStub()
    app.dependency_overrides[get_product_catalog_service] = lambda: service
    try:
        response = TestClient(app).get("/api/v1/products/202607:2")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["name"] == "둘째 상품"
    assert response.json()["source_product_id"] == "202607:2"


def test_product_detail_missing_id_is_explicit_404() -> None:
    app.dependency_overrides[get_product_catalog_service] = DetailCatalogStub
    try:
        response = TestClient(app).get("/api/v1/products/202607:99")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert "latest snapshot" in response.json()["detail"]


def test_compare_uses_one_snapshot_and_preserves_request_order() -> None:
    service = DetailCatalogStub()
    app.dependency_overrides[get_product_catalog_service] = lambda: service
    try:
        response = TestClient(app).post(
            "/api/v1/products/compare",
            json={"product_ids": ["202607:2", "202607:1"]},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert service.calls == 1
    assert body["source_base_month"] == "202607"
    assert [item["source_product_id"] for item in body["items"]] == [
        "202607:2",
        "202607:1",
    ]
    assert "보장하지 않습니다" in body["disclaimer"]


def test_compare_rejects_duplicate_extra_and_sensitive_fields() -> None:
    client = TestClient(app)
    app.dependency_overrides[get_product_catalog_service] = DetailCatalogStub
    try:
        duplicate = client.post(
            "/api/v1/products/compare",
            json={"product_ids": ["202607:1", "202607:1"]},
        )
        extra = client.post(
            "/api/v1/products/compare",
            json={"product_ids": ["202607:1", "202607:2"], "income": 1000},
        )
        three = client.post(
            "/api/v1/products/compare",
            json={"product_ids": ["202607:1", "202607:2", "202607:3"]},
        )
    finally:
        app.dependency_overrides.clear()

    assert duplicate.status_code == 422
    assert extra.status_code == 422
    assert three.status_code == 422


def test_compare_missing_one_product_returns_no_partial_result() -> None:
    app.dependency_overrides[get_product_catalog_service] = DetailCatalogStub
    try:
        response = TestClient(app).post(
            "/api/v1/products/compare",
            json={"product_ids": ["202607:1", "202607:99"]},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert "items" not in response.json()


def test_detail_and_compare_openapi_contracts_are_published() -> None:
    schema = TestClient(app).get("/openapi.json").json()

    assert "/api/v1/products/{source_product_id}" in schema["paths"]
    assert schema["paths"]["/api/v1/products/compare"]["post"]["requestBody"][
        "required"
    ]
