from datetime import timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.routes.products import get_product_catalog_service
from app.clients.public_data_products import (
    API_URL,
    DATASET_URL,
    ProductProviderResponseError,
    PublicDataProductClient,
)
from app.main import app
from app.services.product_catalog import (
    ProductCatalogService,
    build_product_catalog_service,
)


SAMPLE_ITEM = {
    "basYm": "202202",
    "snq": "1",
    "finPrdNm": "미소금융 창업자금_임차보증금대출",
    "lnLmt": "7000만원",
    "irtCtg": "변동금리",
    "irt": "4.5%",
    "maxTotLnTrm": "6년",
    "maxDfrmTrm": "1년",
    "maxRdptTrm": "5년",
    "rdptMthd": "원(리)금균등분할상환",
    "usge": "창업",
    "trgt": "사업자, 금융취약계층",
    "ofrInstNm": "서민금융진흥원",
    "suprTgtDtlCond": "공식 상세조건 원문",
    "age": "미성년자 제외",
    "incm": "소득증빙 필요",
    "crdtSc": "개인신용평점 하위 20%",
    "jnMthd": "미소금융 전국 지점 방문",
    "hdlInst": "미소금융 전국 지점",
    "prdExisYn": "Y",
    "prdNm": "대출상품",
    "prdCtg2": "정책자금",
    "fileWrtDt": "202202080917",
}


def provider_payload(*, item: dict | list[dict] = SAMPLE_ITEM) -> dict:
    return {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
            "body": {
                "numOfRows": 20,
                "pageNo": 1,
                "totalCount": 1,
                "items": {"item": item},
            },
        }
    }


def test_client_sends_fixed_official_endpoint_and_required_parameters() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith(API_URL)
        assert request.url.params["serviceKey"] == "test-key"
        assert request.url.params["resultType"] == "json"
        assert request.url.params["prdExisYn"] == "Y"
        return httpx.Response(200, json=provider_payload())

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        page = PublicDataProductClient(
            "test-key",
            client=http_client,
        ).fetch_products(page_no=1, page_size=20)

    assert page.total_count == 1
    assert page.rows[0]["finPrdNm"] == SAMPLE_ITEM["finPrdNm"]
    assert page.fetched_at.tzinfo is timezone.utc


def test_client_passes_optional_base_month_to_provider() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["basYm"] == "202607"
        return httpx.Response(200, json=provider_payload())

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        PublicDataProductClient(
            "test-key",
            client=http_client,
        ).fetch_products(page_no=1, page_size=20, base_month="202607")


def test_client_accepts_url_encoded_general_service_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["serviceKey"] == "abc+def/ghi="
        return httpx.Response(200, json=provider_payload())

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        page = PublicDataProductClient(
            "abc%2Bdef%2Fghi%3D",
            client=http_client,
        ).fetch_products(page_no=1, page_size=20)

    assert page.total_count == 1


def test_service_normalizes_text_without_inventing_numeric_eligibility() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json=provider_payload())
    )
    with httpx.Client(transport=transport) as http_client:
        service = ProductCatalogService(
            PublicDataProductClient("test-key", client=http_client),
            start_month_provider=lambda: "202202",
        )
        result = service.list_products(page_no=1, page_size=20)

    product = result.items[0]
    assert product.source_product_id == "202202:1"
    assert product.interest_rate_text == "4.5%"
    assert product.loan_limit_text == "7000만원"
    assert product.eligibility.credit_score_text == "개인신용평점 하위 20%"
    assert product.eligibility.annual_income_text is None
    assert str(product.source_reference) == DATASET_URL


def test_service_decodes_provider_html_character_references_once() -> None:
    escaped_item = {
        **SAMPLE_ITEM,
        "rdptMthd": "원&#40;리&#41;금균등분할상환",
        "jnMthd": "안내 &amp; 신청",
    }
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json=provider_payload(item=escaped_item))
    )
    with httpx.Client(transport=transport) as http_client:
        service = ProductCatalogService(
            PublicDataProductClient("test-key", client=http_client),
            start_month_provider=lambda: "202202",
        )
        product = service.list_products(page_no=1, page_size=20).items[0]

    assert product.repayment_method_text == "원(리)금균등분할상환"
    assert product.application_method_text == "안내 & 신청"


@pytest.mark.parametrize(
    "payload",
    [
        {"response": {"header": {"resultCode": "30"}, "body": {}}},
        provider_payload(item={"basYm": "202202", "snq": "1"}),
        provider_payload(item={**SAMPLE_ITEM, "basYm": "invalid"}),
    ],
)
def test_provider_errors_are_explicit(payload: dict) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    with httpx.Client(transport=transport) as http_client:
        service = ProductCatalogService(
            PublicDataProductClient("test-key", client=http_client),
            start_month_provider=lambda: "202202",
        )
        with pytest.raises(ProductProviderResponseError):
            service.list_products(page_no=1, page_size=20)


def test_no_active_snapshot_is_an_explicit_provider_error() -> None:
    payload = provider_payload(item=[])
    payload["response"]["body"]["items"] = ""
    payload["response"]["body"]["totalCount"] = 0
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=payload))

    with httpx.Client(transport=transport) as http_client:
        service = ProductCatalogService(
            PublicDataProductClient("test-key", client=http_client),
            lookback_months=0,
            start_month_provider=lambda: "202202",
        )
        with pytest.raises(ProductProviderResponseError):
            service.list_products(page_no=1, page_size=20)


def test_products_endpoint_returns_normalized_official_contract() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json=provider_payload())
    )
    http_client = httpx.Client(transport=transport)
    service = ProductCatalogService(
        PublicDataProductClient("test-key", client=http_client),
        start_month_provider=lambda: "202202",
    )
    app.dependency_overrides[get_product_catalog_service] = lambda: service

    try:
        response = TestClient(app).get("/api/v1/products?page_no=1&page_size=20")
    finally:
        app.dependency_overrides.clear()
        http_client.close()

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "financial_services_commission"
    assert body["source_base_month"] == "202202"
    assert body["identity"] == {
        "policy": "provider_base_month_sequence",
        "source_id_unique": True,
        "unique_source_id_count": 1,
        "normalized_name_duplicate_groups": 0,
        "name_only_dedup_applied": False,
    }
    assert body["items"][0]["source_product_id"] == "202202:1"
    assert body["items"][0]["interest_rate_text"] == "4.5%"
    assert body["items"][0]["source_reference"] == DATASET_URL


def test_products_endpoint_returns_503_when_service_key_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_product_catalog_service.cache_clear()
    monkeypatch.delenv("PUBLIC_DATA_SERVICE_KEY", raising=False)
    try:
        response = TestClient(app).get("/api/v1/products")
    finally:
        get_product_catalog_service.cache_clear()

    assert response.status_code == 503
    assert response.json() == {
        "detail": "official product provider is not configured"
    }


def test_product_service_accepts_key_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    key_path = tmp_path / "public-data-key"
    key_path.write_text("test-key\n", encoding="utf-8")
    monkeypatch.delenv("PUBLIC_DATA_SERVICE_KEY", raising=False)
    monkeypatch.setenv("PUBLIC_DATA_SERVICE_KEY_FILE", str(key_path))

    service = build_product_catalog_service()

    assert isinstance(service, ProductCatalogService)


def test_products_endpoint_returns_503_for_unreadable_key_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    get_product_catalog_service.cache_clear()
    monkeypatch.delenv("PUBLIC_DATA_SERVICE_KEY", raising=False)
    monkeypatch.setenv(
        "PUBLIC_DATA_SERVICE_KEY_FILE",
        str(tmp_path / "missing-key"),
    )
    try:
        response = TestClient(app).get("/api/v1/products")
    finally:
        get_product_catalog_service.cache_clear()

    assert response.status_code == 503
    assert response.json() == {
        "detail": "official product provider is not configured"
    }


def test_products_endpoint_returns_503_for_invalid_cache_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_product_catalog_service.cache_clear()
    monkeypatch.setenv("PUBLIC_DATA_SERVICE_KEY", "test-key")
    monkeypatch.setenv("PRODUCT_CATALOG_CACHE_TTL_SECONDS", "0")
    try:
        response = TestClient(app).get("/api/v1/products")
    finally:
        get_product_catalog_service.cache_clear()

    assert response.status_code == 503
    assert response.json() == {
        "detail": "official product provider is not configured"
    }


def test_products_endpoint_hides_provider_failure_details() -> None:
    class FailingService:
        def list_products(self, *, page_no: int, page_size: int) -> None:
            raise ProductProviderResponseError("upstream payload included a secret")

    app.dependency_overrides[get_product_catalog_service] = FailingService
    try:
        response = TestClient(app).get("/api/v1/products")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    assert response.json() == {
        "detail": "official product provider is unavailable"
    }


def test_products_openapi_contract_is_published() -> None:
    schema = TestClient(app).get("/openapi.json").json()
    operation = schema["paths"]["/api/v1/products"]["get"]

    assert operation["responses"]["200"]["content"]["application/json"]["schema"]
    response_schema = schema["components"]["schemas"]["ProductCatalogResponse"]
    assert "source_base_month" in response_schema["required"]
    assert "identity" in response_schema["required"]
    assert {parameter["name"] for parameter in operation["parameters"]} == {
        "page_no",
        "page_size",
    }
