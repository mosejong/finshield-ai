"""Profile the latest official product-catalog month without exposing the key."""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.clients.public_data_products import PublicDataProductClient


SEOUL = timezone(timedelta(hours=9), name="KST")
PROFILE_FIELDS = (
    "basYm",
    "snq",
    "finPrdNm",
    "prdNm",
    "prdCtg2",
    "lnLmt",
    "irt",
    "maxTotLnTrm",
    "rdptMthd",
    "usge",
    "trgt",
    "suprTgtDtlCond",
    "ofrInstNm",
    "hdlInst",
)
MISSING_MARKERS = {"", "null", "none", "-"}


def read_service_key(env_file: Path | None) -> str:
    environment_key = os.getenv("PUBLIC_DATA_SERVICE_KEY", "").strip()
    if environment_key:
        return environment_key

    if env_file is None:
        raise RuntimeError(
            "PUBLIC_DATA_SERVICE_KEY is not configured; set it or use --env-file"
        )

    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("PUBLIC_DATA_SERVICE_KEY="):
            value = line.split("=", 1)[1].strip()
            if value:
                return value
            break
    raise RuntimeError("PUBLIC_DATA_SERVICE_KEY is missing from the env file")


def previous_month(value: str) -> str:
    year = int(value[:4])
    month = int(value[4:])
    if month == 1:
        return f"{year - 1:04d}12"
    return f"{year:04d}{month - 1:02d}"


def parse_base_month(value: str) -> str:
    if not re.fullmatch(r"\d{6}", value) or not 1 <= int(value[4:]) <= 12:
        raise argparse.ArgumentTypeError("base month must use a valid YYYYMM")
    return value


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
    raise RuntimeError("no active official products found in the lookback window")


def fetch_month_rows(
    client: PublicDataProductClient,
    *,
    base_month: str,
    page_size: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page_no = 1
    total_count: int | None = None

    while total_count is None or len(rows) < total_count:
        page = client.fetch_products(
            page_no=page_no,
            page_size=page_size,
            base_month=base_month,
        )
        if total_count is None:
            total_count = page.total_count
        elif page.total_count != total_count:
            raise RuntimeError("provider totalCount changed during profiling")

        page_rows = [dict(row) for row in page.rows]
        if not page_rows and len(rows) < total_count:
            raise RuntimeError("provider returned an empty page before totalCount")
        rows.extend(page_rows)
        page_no += 1

    if len(rows) != total_count:
        raise RuntimeError("collected row count does not match provider totalCount")
    return rows


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    return str(value).strip().lower() in MISSING_MARKERS


def normalized_text(value: Any) -> str:
    if is_missing(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


def duplicate_summary(keys: list[str]) -> dict[str, int]:
    counts = Counter(key for key in keys if key)
    duplicate_groups = [count for count in counts.values() if count > 1]
    return {
        "groups": len(duplicate_groups),
        "rows_in_groups": sum(duplicate_groups),
        "excess_rows": sum(count - 1 for count in duplicate_groups),
    }


def top_values(rows: list[dict[str, Any]], field: str, limit: int = 10) -> list[dict]:
    counts = Counter(
        str(row[field]).strip()
        for row in rows
        if not is_missing(row.get(field))
    )
    return [
        {"value": value, "count": count}
        for value, count in counts.most_common(limit)
    ]


def duplicate_name_samples(
    rows: list[dict[str, Any]],
    limit: int = 5,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = normalized_text(row.get("finPrdNm"))
        if key:
            grouped.setdefault(key, []).append(row)

    samples = []
    for group in grouped.values():
        if len(group) < 2:
            continue
        samples.append(
            {
                "name": str(group[0]["finPrdNm"]).strip(),
                "count": len(group),
                "source_product_ids": sorted(
                    f"{row.get('basYm')}:{row.get('snq')}" for row in group
                ),
                "offering_institutions": sorted(
                    {
                        str(row["ofrInstNm"]).strip()
                        for row in group
                        if not is_missing(row.get("ofrInstNm"))
                    }
                ),
                "handling_institutions": sorted(
                    {
                        str(row["hdlInst"]).strip()
                        for row in group
                        if not is_missing(row.get("hdlInst"))
                    }
                ),
            }
        )
    return sorted(samples, key=lambda item: (-item["count"], item["name"]))[:limit]


def build_profile(rows: list[dict[str, Any]], *, base_month: str) -> dict[str, Any]:
    row_count = len(rows)
    missing = {}
    for field in PROFILE_FIELDS:
        count = sum(is_missing(row.get(field)) for row in rows)
        missing[field] = {
            "count": count,
            "ratio": round(count / row_count, 4) if row_count else 0,
        }

    source_ids = []
    for row in rows:
        base_month_value = normalized_text(row.get("basYm"))
        sequence_value = normalized_text(row.get("snq"))
        source_ids.append(
            f"{base_month_value}:{sequence_value}"
            if base_month_value and sequence_value
            else ""
        )
    names = [normalized_text(row.get("finPrdNm")) for row in rows]
    signatures = [
        "|".join(
            normalized_text(row.get(field))
            for field in ("finPrdNm", "ofrInstNm", "prdCtg2", "hdlInst")
        )
        for row in rows
    ]

    return {
        "profile_version": "0.1",
        "source": "financial_services_commission",
        "source_reference": "https://www.data.go.kr/data/15094787/openapi.do",
        "profiled_at": datetime.now(SEOUL).isoformat(),
        "base_month": base_month,
        "active_row_count": row_count,
        "missing_rule": "None, blank, NULL, none, or '-' after trim",
        "missing_fields": missing,
        "duplicates": {
            "source_id": duplicate_summary(source_ids),
            "normalized_name": duplicate_summary(names),
            "normalized_signature": duplicate_summary(signatures),
            "normalized_name_samples": duplicate_name_samples(rows),
        },
        "distributions": {
            "product_category": top_values(rows, "prdNm"),
            "product_category_detail": top_values(rows, "prdCtg2"),
            "offering_institution": top_values(rows, "ofrInstNm"),
            "purpose": top_values(rows, "usge"),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--base-month", type=parse_base_month)
    parser.add_argument("--page-size", type=int, default=100, choices=range(1, 101))
    parser.add_argument("--lookback-months", type=int, default=36)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.lookback_months < 0 or args.lookback_months > 120:
        raise SystemExit("--lookback-months must be between 0 and 120")

    service_key = read_service_key(args.env_file)
    client = PublicDataProductClient(service_key)
    start_month = datetime.now(SEOUL).strftime("%Y%m")
    base_month = args.base_month or discover_latest_month(
        client,
        start_month=start_month,
        lookback_months=args.lookback_months,
    )
    rows = fetch_month_rows(
        client,
        base_month=base_month,
        page_size=args.page_size,
    )
    print(json.dumps(build_profile(rows, base_month=base_month), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
