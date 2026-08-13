import json
import logging
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
LATENCY_BUCKETS_MS = (25, 50, 100, 250, 500, 1000, 2500, 5000)
request_logger = logging.getLogger("finshield.request")


@dataclass(frozen=True)
class RequestMetric:
    method: str
    route: str
    status_code: int
    duration_ms: float


class RequestMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._requests: Counter[tuple[str, str, int]] = Counter()
        self._latency_buckets: Counter[tuple[str, str, float]] = Counter()
        self._duration_sum_ms: Counter[tuple[str, str]] = Counter()

    def observe(self, metric: RequestMetric) -> None:
        key = (metric.method, metric.route, metric.status_code)
        route_key = (metric.method, metric.route)
        with self._lock:
            self._requests[key] += 1
            self._duration_sum_ms[route_key] += metric.duration_ms
            for bucket in LATENCY_BUCKETS_MS:
                if metric.duration_ms <= bucket:
                    self._latency_buckets[(metric.method, metric.route, bucket)] += 1

    def prometheus_text(self) -> str:
        with self._lock:
            requests = self._requests.copy()
            buckets = self._latency_buckets.copy()
            duration_sums = self._duration_sum_ms.copy()

        lines = [
            "# FinShield process-local metrics; aggregate structured logs across workers.",
            "# HELP finshield_http_requests_total Completed HTTP requests.",
            "# TYPE finshield_http_requests_total counter",
        ]
        for (method, route, status_code), count in sorted(requests.items()):
            lines.append(
                "finshield_http_requests_total"
                f'{{method="{method}",route="{route}",status="{status_code}"}} {count}'
            )
        lines.extend(
            [
                "# HELP finshield_http_request_duration_milliseconds HTTP request latency.",
                "# TYPE finshield_http_request_duration_milliseconds histogram",
            ]
        )
        route_counts: Counter[tuple[str, str]] = Counter()
        for (method, route, _), count in requests.items():
            route_counts[(method, route)] += count
        for method, route in sorted(route_counts):
            for bucket in LATENCY_BUCKETS_MS:
                count = buckets[(method, route, bucket)]
                lines.append(
                    "finshield_http_request_duration_milliseconds_bucket"
                    f'{{method="{method}",route="{route}",le="{bucket}"}} {count}'
                )
            count = route_counts[(method, route)]
            lines.append(
                "finshield_http_request_duration_milliseconds_bucket"
                f'{{method="{method}",route="{route}",le="+Inf"}} {count}'
            )
            lines.append(
                "finshield_http_request_duration_milliseconds_sum"
                f'{{method="{method}",route="{route}"}} {duration_sums[(method, route)]:.3f}'
            )
            lines.append(
                "finshield_http_request_duration_milliseconds_count"
                f'{{method="{method}",route="{route}"}} {count}'
            )
        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()
            self._latency_buckets.clear()
            self._duration_sum_ms.clear()


request_metrics = RequestMetrics()


def install_observability(app: FastAPI) -> None:
    _configure_request_logger()
    app.add_middleware(ObservabilityMiddleware)


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = _request_id(request.headers)
        started_at = perf_counter()
        response: Response | None = None
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = round((perf_counter() - started_at) * 1000, 3)
            route = _route_template(request)
            metric = RequestMetric(
                method=request.method,
                route=route,
                status_code=status_code,
                duration_ms=duration_ms,
            )
            request_metrics.observe(metric)
            request_logger.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "service": "finshield-api",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "request_id": request_id,
                        "method": metric.method,
                        "route": metric.route,
                        "status_code": metric.status_code,
                        "duration_ms": metric.duration_ms,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
            if response is not None:
                response.headers["X-Request-ID"] = request_id
                response.headers["Server-Timing"] = f"app;dur={duration_ms:.3f}"


def _request_id(headers: Mapping[str, str]) -> str:
    candidate = headers.get("x-request-id", "")
    return candidate if REQUEST_ID_PATTERN.fullmatch(candidate) else uuid4().hex


def _configure_request_logger() -> None:
    request_logger.setLevel(logging.INFO)
    has_json_handler = any(
        getattr(handler, "_finshield_json", False)
        for handler in request_logger.handlers
    )
    if not has_json_handler:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler._finshield_json = True  # type: ignore[attr-defined]
        request_logger.addHandler(handler)
    request_logger.propagate = False


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "<unmatched>"
