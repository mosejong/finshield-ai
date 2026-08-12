from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.routes.products import get_product_catalog_service
from app.clients.public_data_products import PROVIDER_NAME
from app.domain.finance.product_catalog import normalize_public_data_product
from app.domain.finance.product_identity import ProductCatalogIdentityAudit
from app.main import app
from app.services.product_catalog_snapshot import (
    ACTIVE_PRODUCT_QUERY,
    ProductCatalogSnapshot,
    ProductCatalogSnapshotKey,
)


class CatalogStub:
    def get_snapshot(self) -> ProductCatalogSnapshot:
        fetched_at = datetime(2026, 8, 12, tzinfo=timezone.utc)
        items = tuple(
            normalize_public_data_product(
                {
                    "basYm": "202607",
                    "snq": str(index),
                    "finPrdNm": name,
                    "usge": purpose,
                    "prdExisYn": "Y",
                },
                fetched_at=fetched_at,
            )
            for index, name, purpose in [
                (1, "주거 상품", "주거"),
                (2, "창업 상품", "창업"),
                (3, "확인 상품", None),
            ]
        )
        return ProductCatalogSnapshot(
            key=ProductCatalogSnapshotKey(
                provider=PROVIDER_NAME,
                base_month="202607",
                query=ACTIVE_PRODUCT_QUERY,
                page_scope="all",
            ),
            fetched_at=fetched_at,
            items=items,
            identity_audit=ProductCatalogIdentityAudit(3, 0),
        )


def test_recommendations_endpoint_returns_conservative_statuses() -> None:
    app.dependency_overrides[get_product_catalog_service] = CatalogStub
    try:
        response = TestClient(app).post(
            "/api/v1/recommendations?page_size=10",
            json={"goal": "housing"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {
        "potential_match": 1,
        "mismatch": 1,
        "needs_review": 1,
    }
    assert [result["status"] for result in body["results"]] == [
        "potential_match",
        "needs_review",
        "mismatch",
    ]
    assert "보장하지 않습니다" in body["disclaimer"]


def test_recommendations_rejects_sensitive_profile_fields() -> None:
    payload = {"goal": "housing", "otp": "123456"}
    app.dependency_overrides[get_product_catalog_service] = CatalogStub
    try:
        response = TestClient(app).post(
            "/api/v1/recommendations",
            json=payload,
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422


def test_recommendations_openapi_contract_is_published() -> None:
    schema = TestClient(app).get("/openapi.json").json()
    operation = schema["paths"]["/api/v1/recommendations"]["post"]

    assert operation["requestBody"]["required"] is True
    response_schema = schema["components"]["schemas"][
        "ProductRecommendationResponse"
    ]
    assert {"summary", "disclaimer", "results"}.issubset(
        response_schema["required"]
    )
