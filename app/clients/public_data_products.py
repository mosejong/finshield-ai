from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote

import httpx


PROVIDER_NAME = "financial_services_commission"
DATASET_URL = "https://www.data.go.kr/data/15094787/openapi.do"
API_URL = (
    "https://apis.data.go.kr/1160100/service/"
    "GetSmallLoanFinanceInstituteInfoService/getOrdinaryFinanceInfo"
)


class ProductProviderError(RuntimeError):
    """Base error for official product-provider failures."""


class ProductProviderConfigurationError(ProductProviderError):
    """Raised when the provider cannot be called safely."""


class ProductProviderResponseError(ProductProviderError):
    """Raised when the provider returns an error or unsupported payload."""


# One provider round trip, measured 2026-09-05. From the dev PC a 325-row page
# takes 0.64s; from the us-west1 VM the first call of a process takes 2.33s,
# because the TLS handshake to the Korean host is paid there. A 5s budget left
# too little margin for that, and exceeding it turns a slow provider into a
# hard failure the user sees as "official product data unavailable".
PROVIDER_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class ProviderProductPage:
    rows: list[Mapping[str, Any]]
    page_no: int
    page_size: int
    total_count: int
    fetched_at: datetime


class PublicDataProductClient:
    def __init__(
        self,
        service_key: str,
        *,
        client: httpx.Client | None = None,
        timeout_seconds: float = PROVIDER_TIMEOUT_SECONDS,
    ) -> None:
        normalized_key = service_key.strip()
        if not normalized_key:
            raise ProductProviderConfigurationError(
                "PUBLIC_DATA_SERVICE_KEY is not configured"
            )

        # The public-data portal may expose the general key in either encoded or
        # decoded form. Decode exactly once; httpx then performs the one required
        # query-string encoding when it builds the request.
        self._service_key = unquote(normalized_key)
        self._client = client
        self._timeout = httpx.Timeout(timeout_seconds)

    def fetch_products(
        self,
        *,
        page_no: int,
        page_size: int,
        base_month: str | None = None,
    ) -> ProviderProductPage:
        params = {
            "serviceKey": self._service_key,
            "pageNo": page_no,
            "numOfRows": page_size,
            "resultType": "json",
            "prdExisYn": "Y",
        }
        if base_month is not None:
            params["basYm"] = base_month

        try:
            if self._client is not None:
                response = self._client.get(API_URL, params=params)
            else:
                with httpx.Client(
                    timeout=self._timeout,
                    follow_redirects=False,
                ) as client:
                    response = client.get(API_URL, params=params)
        except httpx.HTTPError as exc:
            raise ProductProviderResponseError(
                "official product provider request failed"
            ) from exc

        if response.status_code != 200:
            raise ProductProviderResponseError(
                f"official product provider returned HTTP {response.status_code}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProductProviderResponseError(
                "official product provider returned invalid JSON"
            ) from exc

        return self._parse_payload(payload)

    @staticmethod
    def _parse_payload(payload: Any) -> ProviderProductPage:
        if not isinstance(payload, Mapping):
            raise ProductProviderResponseError("provider payload must be an object")

        response = payload.get("response")
        if not isinstance(response, Mapping):
            raise ProductProviderResponseError("provider response object is missing")

        header = response.get("header")
        if not isinstance(header, Mapping):
            raise ProductProviderResponseError("provider response header is missing")

        result_code = str(header.get("resultCode", ""))
        if result_code != "00":
            safe_code = result_code or "unknown"
            raise ProductProviderResponseError(
                f"official product provider returned result code {safe_code}"
            )

        body = response.get("body")
        if not isinstance(body, Mapping):
            raise ProductProviderResponseError("provider response body is missing")

        raw_items = body.get("items", {})
        if raw_items is None or raw_items == "":
            rows: Any = []
        elif isinstance(raw_items, Mapping):
            rows = raw_items.get("item", [])
        else:
            rows = raw_items

        if isinstance(rows, Mapping):
            rows = [rows]
        if not isinstance(rows, list) or not all(
            isinstance(row, Mapping) for row in rows
        ):
            raise ProductProviderResponseError("provider items have an invalid shape")

        try:
            page_no = int(body["pageNo"])
            page_size = int(body["numOfRows"])
            total_count = int(body["totalCount"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ProductProviderResponseError(
                "provider pagination metadata is invalid"
            ) from exc

        if page_no < 1 or page_size < 1 or total_count < 0:
            raise ProductProviderResponseError(
                "provider pagination metadata is out of range"
            )

        return ProviderProductPage(
            rows=rows,
            page_no=page_no,
            page_size=page_size,
            total_count=total_count,
            fetched_at=datetime.now(timezone.utc),
        )
