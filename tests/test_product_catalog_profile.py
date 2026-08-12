import argparse

import pytest

from app.clients.public_data_products import ProviderProductPage
from scripts.profile_product_catalog import (
    build_profile,
    discover_latest_month,
    fetch_month_rows,
    parse_base_month,
    previous_month,
)


def page(*, rows: list[dict], total: int, page_no: int = 1) -> ProviderProductPage:
    from datetime import datetime, timezone

    return ProviderProductPage(
        rows=rows,
        page_no=page_no,
        page_size=100,
        total_count=total,
        fetched_at=datetime.now(timezone.utc),
    )


class FakeClient:
    def __init__(self, pages: dict[tuple[str, int], ProviderProductPage]) -> None:
        self.pages = pages
        self.calls: list[tuple[str | None, int, int]] = []

    def fetch_products(
        self,
        *,
        page_no: int,
        page_size: int,
        base_month: str | None = None,
    ) -> ProviderProductPage:
        self.calls.append((base_month, page_no, page_size))
        assert base_month is not None
        return self.pages[(base_month, page_no)]


def test_previous_month_crosses_year_boundary() -> None:
    assert previous_month("202601") == "202512"
    assert previous_month("202608") == "202607"


@pytest.mark.parametrize("value", ["202613", "202600", "20261", "abcdef"])
def test_parse_base_month_rejects_invalid_values(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        parse_base_month(value)


def test_parse_base_month_accepts_valid_value() -> None:
    assert parse_base_month("202607") == "202607"


def test_discover_latest_month_stops_at_first_non_empty_month() -> None:
    client = FakeClient(
        {
            ("202608", 1): page(rows=[], total=0),
            ("202607", 1): page(rows=[{"basYm": "202607"}], total=1),
        }
    )

    result = discover_latest_month(
        client,
        start_month="202608",
        lookback_months=12,
    )

    assert result == "202607"
    assert [call[0] for call in client.calls] == ["202608", "202607"]


def test_fetch_month_rows_checks_all_pages() -> None:
    client = FakeClient(
        {
            ("202607", 1): page(rows=[{"snq": 1}, {"snq": 2}], total=3),
            ("202607", 2): page(rows=[{"snq": 3}], total=3, page_no=2),
        }
    )

    rows = fetch_month_rows(client, base_month="202607", page_size=2)

    assert [row["snq"] for row in rows] == [1, 2, 3]


def test_build_profile_reports_missing_and_duplicates() -> None:
    rows = [
        {
            "basYm": "202607",
            "snq": "1",
            "finPrdNm": "상품 A",
            "ofrInstNm": "기관",
            "prdCtg2": "정책자금",
            "hdlInst": "지점",
            "irt": "4%",
            "lnLmt": "1000만원",
            "maxTotLnTrm": "5년",
            "rdptMthd": "분할",
            "usge": "생활",
            "trgt": "근로자",
            "suprTgtDtlCond": "NULL",
            "prdNm": "대출상품",
        },
        {
            "basYm": "202607",
            "snq": "2",
            "finPrdNm": " 상품  A ",
            "ofrInstNm": "기관",
            "prdCtg2": "정책자금",
            "hdlInst": "지점",
            "irt": None,
            "lnLmt": "1000만원",
            "maxTotLnTrm": "5년",
            "rdptMthd": "분할",
            "usge": "생활",
            "trgt": "근로자",
            "suprTgtDtlCond": "상세",
            "prdNm": "대출상품",
        },
    ]

    profile = build_profile(rows, base_month="202607")

    assert profile["active_row_count"] == 2
    assert profile["missing_fields"]["irt"] == {"count": 1, "ratio": 0.5}
    assert profile["missing_fields"]["suprTgtDtlCond"] == {
        "count": 1,
        "ratio": 0.5,
    }
    assert profile["duplicates"]["source_id"]["groups"] == 0
    assert profile["duplicates"]["normalized_name"]["groups"] == 1
    assert profile["duplicates"]["normalized_signature"]["excess_rows"] == 1
    assert profile["duplicates"]["normalized_name_samples"] == [
        {
            "name": "상품 A",
            "count": 2,
            "source_product_ids": ["202607:1", "202607:2"],
            "offering_institutions": ["기관"],
            "handling_institutions": ["지점"],
        }
    ]


def test_missing_source_identity_is_not_counted_as_a_duplicate() -> None:
    rows = [
        {"finPrdNm": "상품 A"},
        {"finPrdNm": "상품 B"},
    ]

    profile = build_profile(rows, base_month="202607")

    assert profile["missing_fields"]["basYm"]["count"] == 2
    assert profile["missing_fields"]["snq"]["count"] == 2
    assert profile["duplicates"]["source_id"]["groups"] == 0
