from collections.abc import Mapping
from datetime import datetime
from html import unescape
from typing import Any

from app.clients.public_data_products import (
    DATASET_URL,
    PROVIDER_NAME,
    ProductProviderResponseError,
)
from app.schemas.product import FinancialProduct, ProductEligibility


def _text(row: Mapping[str, Any], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    normalized = unescape(str(value)).strip()
    return normalized or None


def _active(value: str | None) -> bool | None:
    if value == "Y":
        return True
    if value == "N":
        return False
    return None


def normalize_public_data_product(
    row: Mapping[str, Any],
    *,
    fetched_at: datetime,
) -> FinancialProduct:
    base_month = _text(row, "basYm")
    sequence = _text(row, "snq")
    name = _text(row, "finPrdNm")

    if not base_month or not sequence or not name:
        raise ProductProviderResponseError(
            "provider product identity fields are missing"
        )

    return FinancialProduct(
        provider=PROVIDER_NAME,
        source_product_id=f"{base_month}:{sequence}",
        name=name,
        category=_text(row, "prdNm"),
        category_detail=_text(row, "prdCtg2"),
        loan_limit_text=_text(row, "lnLmt"),
        interest_rate_type=_text(row, "irtCtg"),
        interest_rate_text=_text(row, "irt"),
        max_total_term_text=_text(row, "maxTotLnTrm"),
        max_grace_term_text=_text(row, "maxDfrmTrm"),
        max_repayment_term_text=_text(row, "maxRdptTrm"),
        repayment_method_text=_text(row, "rdptMthd"),
        purpose_text=_text(row, "usge"),
        offering_institution=_text(row, "ofrInstNm"),
        handling_institution_text=_text(row, "hdlInst"),
        application_method_text=_text(row, "jnMthd"),
        active=_active(_text(row, "prdExisYn")),
        eligibility=ProductEligibility(
            target_text=_text(row, "trgt"),
            detailed_conditions_text=_text(row, "suprTgtDtlCond"),
            age_text=_text(row, "age"),
            income_text=_text(row, "incm"),
            annual_income_text=_text(row, "anin"),
            credit_score_text=_text(row, "crdtSc"),
            region_text=_text(row, "rsdArea"),
        ),
        source_base_month=base_month,
        source_file_written_at=_text(row, "fileWrtDt"),
        fetched_at=fetched_at,
        source_reference=DATASET_URL,
    )
