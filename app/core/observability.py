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

# 설명 계층 전용 로거. 요청 로거와 나누는 이유는 성격이 다르기 때문이다 - 요청
# 로그는 모든 요청에 한 줄이고, 이쪽은 유료 외부 호출에만 붙는다. 수집 쪽에서
# 보존 기간과 경보를 따로 걸 수 있어야 한다.
llm_logger = logging.getLogger("finshield.llm")

# 지표 라벨로 쓸 수 있는 모델 이름. `outcome` 은 `ExplanationOutcome` 이라 이미
# 닫혀 있지만 모델명은 문자열이고, 여기 들어오는 값에 따옴표나 줄바꿈이 있으면
# Prometheus 노출 형식이 깨진다. **허용 목록을 벗어나면 값을 고쳐 쓰지 않고
# `other` 로 센다** - `ADR 0006` 이 마스킹 대신 허용 목록을 쓰는 것과 같은 규율이다.
_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_LABEL_FALLBACK = "other"


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


def _label(value: str) -> str:
    return value if _LABEL_PATTERN.fullmatch(value) else _LABEL_FALLBACK


class ExplanationMetrics:
    """설명 계층이 남기는 것 - 개수와 성패뿐이다.

    `ADR 0006` 이 요구하는 형태다. 여기 들어오는 값은 모델 이름(코드 상수)과
    결과 이름(`ExplanationOutcome`)과 정수뿐이고, 사용자 원문·프롬프트·모델 출력은
    한 글자도 지나가지 않는다. 그래서 이 지표는 마스킹이 필요하지 않다 -
    민감한 것이 애초에 들어오지 않는다.

    **시도와 결과를 따로 센다.** 대체 모델이 있으므로 요청 하나가 시도 둘을 만들 수
    있고, 그때 실패 하나와 성공 하나가 같이 일어난다. 시도만 세면 "설명이 결국
    비었다" 를 계산할 수 없고, 결과만 세면 "주 모델이 얼마나 막히는가" 를 계산할
    수 없다. `docs/34` 9절이 물은 안전 필터 차단율은 앞쪽 숫자다.

    프로세스 로컬이라는 한계는 `RequestMetrics` 와 같다. 워커가 여럿이면 지표는
    워커별로 갈리고, 합계는 구조화 로그 쪽에서 모은다.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._attempts: Counter[tuple[str, str]] = Counter()
        self._attempt_duration_ms: Counter[tuple[str, str]] = Counter()
        self._results: Counter[str] = Counter()

    def observe_attempt(
        self,
        *,
        model: str,
        outcome: str,
        attempt: int,
        duration_ms: float,
    ) -> None:
        """시도 하나. 지표와 로그를 같은 자리에서 남긴다.

        둘을 나누면 언젠가 한쪽만 부르는 코드가 생기고, 그때부터 지표와 로그의
        건수가 어긋난다. 어긋난 뒤에는 어느 쪽이 맞는지 알 방법이 없다.
        """
        model_label = _label(model)
        outcome_label = _label(outcome)
        key = (model_label, outcome_label)
        with self._lock:
            self._attempts[key] += 1
            self._attempt_duration_ms[key] += duration_ms
        llm_logger.info(
            json.dumps(
                {
                    "event": "llm_explanation_attempt",
                    "service": "finshield-api",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "model": model_label,
                    "outcome": outcome_label,
                    "attempt": attempt,
                    "duration_ms": round(duration_ms, 3),
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )

    def observe_result(self, *, outcome: str, attempts: int) -> None:
        """요청 하나의 최종 결과. 운영에서 경보를 거는 줄은 이쪽이다."""
        outcome_label = _label(outcome)
        with self._lock:
            self._results[outcome_label] += 1
        llm_logger.info(
            json.dumps(
                {
                    "event": "llm_explanation_result",
                    "service": "finshield-api",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "outcome": outcome_label,
                    "attempts": attempts,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )

    def prometheus_text(self) -> str:
        with self._lock:
            attempts = self._attempts.copy()
            durations = self._attempt_duration_ms.copy()
            results = self._results.copy()

        lines = [
            "# HELP finshield_llm_explanation_attempts_total"
            " Explanation attempts by model and outcome.",
            "# TYPE finshield_llm_explanation_attempts_total counter",
        ]
        for (model, outcome), count in sorted(attempts.items()):
            lines.append(
                "finshield_llm_explanation_attempts_total"
                f'{{model="{model}",outcome="{outcome}"}} {count}'
            )
        lines.extend(
            [
                "# HELP finshield_llm_explanation_attempt_duration_milliseconds_sum"
                " Total attempt latency by model and outcome.",
                "# TYPE finshield_llm_explanation_attempt_duration_milliseconds_sum"
                " counter",
            ]
        )
        for (model, outcome), total in sorted(durations.items()):
            lines.append(
                "finshield_llm_explanation_attempt_duration_milliseconds_sum"
                f'{{model="{model}",outcome="{outcome}"}} {total:.3f}'
            )
        lines.extend(
            [
                "# HELP finshield_llm_explanation_results_total"
                " Explanation requests by final outcome.",
                "# TYPE finshield_llm_explanation_results_total counter",
            ]
        )
        for outcome, count in sorted(results.items()):
            lines.append(
                "finshield_llm_explanation_results_total"
                f'{{outcome="{outcome}"}} {count}'
            )
        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        with self._lock:
            self._attempts.clear()
            self._attempt_duration_ms.clear()
            self._results.clear()


explanation_metrics = ExplanationMetrics()


def install_observability(app: FastAPI) -> None:
    _configure_request_logger()
    configure_json_logger(llm_logger)
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


def configure_json_logger(logger: logging.Logger) -> None:
    """메시지를 그대로 한 줄씩 내보낸다.

    메시지가 이미 JSON 이라 formatter 가 접두어를 붙이면 파싱이 깨진다.
    두 번 불러도 handler 가 늘어나지 않아야 한다 - 같은 줄이 여러 번 찍히면
    로그 수집 쪽에서 건수가 부풀려진다.
    """
    logger.setLevel(logging.INFO)
    has_json_handler = any(
        getattr(handler, "_finshield_json", False) for handler in logger.handlers
    )
    if not has_json_handler:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler._finshield_json = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
    logger.propagate = False


def _configure_request_logger() -> None:
    configure_json_logger(request_logger)


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "<unmatched>"
