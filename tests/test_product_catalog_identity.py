from datetime import datetime, timedelta, timezone

import pytest

from app.clients.public_data_products import (
    DATASET_URL,
    PROVIDER_NAME,
    ProductProviderResponseError,
)
from app.domain.finance.product_catalog import normalize_public_data_product
from app.domain.finance.product_identity import audit_product_catalog_identity
from app.schemas.product import FinancialProduct


FETCHED_AT = datetime(2026, 8, 12, tzinfo=timezone.utc)


def product(
    sequence: str,
    *,
    name: str = "공식 상품",
) -> FinancialProduct:
    return normalize_public_data_product(
        {
            "basYm": "202607",
            "snq": sequence,
            "finPrdNm": name,
            "prdExisYn": "Y",
        },
        fetched_at=FETCHED_AT,
    )


def audit(items: list[FinancialProduct]):
    return audit_product_catalog_identity(
        items,
        provider=PROVIDER_NAME,
        base_month="202607",
        fetched_at=FETCHED_AT,
        source_reference=DATASET_URL,
    )


def test_same_normalized_name_with_distinct_source_ids_is_preserved() -> None:
    first = product("295", name="소상공인 비즈플러스 카드보증")
    second = product("321", name="  소상공인  비즈플러스 카드보증 ")

    result = audit([first, second])

    assert result.unique_source_id_count == 2
    assert result.normalized_name_duplicate_groups == 1


def test_duplicate_official_source_id_rejects_entire_snapshot() -> None:
    with pytest.raises(
        ProductProviderResponseError,
        match="duplicate official source product ID",
    ):
        audit([product("1"), product("1")])


@pytest.mark.parametrize(
    "invalid_product",
    [
        product("1").model_copy(update={"provider": "other_provider"}),
        product("1").model_copy(update={"source_base_month": "202606"}),
        product("1").model_copy(update={"source_product_id": "202607:1:2"}),
        product("1").model_copy(
            update={"fetched_at": FETCHED_AT + timedelta(seconds=1)}
        ),
        product("1").model_copy(
            update={"source_reference": "https://example.com/data"}
        ),
        product("1").model_copy(update={"active": None}),
        product("1").model_copy(update={"active": False}),
    ],
)
def test_provenance_mismatch_rejects_snapshot(
    invalid_product: FinancialProduct,
) -> None:
    with pytest.raises(ProductProviderResponseError):
        audit([invalid_product])
