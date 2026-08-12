import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.clients.public_data_products import ProductProviderResponseError
from app.schemas.product import FinancialProduct


SNAPSHOT_IDENTITY_POLICY = "provider_base_month_sequence"
SOURCE_PRODUCT_ID_PATTERN = re.compile(r"^\d{6}:\d+$")


@dataclass(frozen=True)
class ProductCatalogIdentityAudit:
    unique_source_id_count: int
    normalized_name_duplicate_groups: int


def normalized_product_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def audit_product_catalog_identity(
    items: Sequence[FinancialProduct],
    *,
    provider: str,
    base_month: str,
    fetched_at: datetime,
    source_reference: str,
) -> ProductCatalogIdentityAudit:
    source_ids: set[str] = set()
    normalized_names: Counter[str] = Counter()

    for item in items:
        if item.provider != provider:
            raise ProductProviderResponseError(
                "product provider does not match snapshot provenance"
            )
        if item.source_base_month != base_month:
            raise ProductProviderResponseError(
                "product base month does not match snapshot provenance"
            )
        if (
            not SOURCE_PRODUCT_ID_PATTERN.fullmatch(item.source_product_id)
            or not item.source_product_id.startswith(f"{base_month}:")
        ):
            raise ProductProviderResponseError(
                "product source ID does not match the official identity format"
            )
        if item.source_product_id in source_ids:
            raise ProductProviderResponseError(
                "duplicate official source product ID in snapshot"
            )
        if item.fetched_at != fetched_at:
            raise ProductProviderResponseError(
                "product fetched_at does not match snapshot provenance"
            )
        if str(item.source_reference) != source_reference:
            raise ProductProviderResponseError(
                "product source reference does not match snapshot provenance"
            )
        if item.active is not True:
            raise ProductProviderResponseError(
                "inactive or unknown product returned by active snapshot query"
            )

        source_ids.add(item.source_product_id)
        normalized_names[normalized_product_name(item.name)] += 1

    return ProductCatalogIdentityAudit(
        unique_source_id_count=len(source_ids),
        normalized_name_duplicate_groups=sum(
            count > 1 for count in normalized_names.values()
        ),
    )
