"""HTTP 경계의 요청 본문 크기 제한.

스키마의 `max_length`는 이미 파싱된 값의 길이를 본다. 파싱 전에 본문을 다
읽은 뒤라서, 100MB 짜리 본문을 보내면 거부되기 전에 100MB를 이미 받는다.
여기서는 파싱 이전에 바이트 수로 자른다.

`Content-Length`만 믿지 않는다. chunked 전송에는 헤더가 없고, 헤더 값이
실제 본문과 다를 수도 있다. 헤더는 빠른 거부에만 쓰고, 실제 판단은 흘러오는
바이트를 세서 한다.
"""

import os
from collections.abc import Mapping

from fastapi import FastAPI
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestLimitConfigurationError(RuntimeError):
    pass


# 가장 큰 정상 요청은 분석 본문이다. text 10000자가 전부 `\uXXXX`로
# 이스케이프되면 60KB, 여기에 url 2048자와 프로필 payload 여유를 더했다.
DEFAULT_MAX_REQUEST_BYTES = 131_072
MIN_MAX_REQUEST_BYTES = 4_096
MAX_MAX_REQUEST_BYTES = 10_485_760


def read_max_request_bytes(values: Mapping[str, str] | None = None) -> int:
    settings = values if values is not None else os.environ
    raw_value = settings.get(
        "FINSHIELD_MAX_REQUEST_BYTES", str(DEFAULT_MAX_REQUEST_BYTES)
    ).strip()
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RequestLimitConfigurationError(
            "FINSHIELD_MAX_REQUEST_BYTES must be an integer"
        ) from exc
    if value < MIN_MAX_REQUEST_BYTES or value > MAX_MAX_REQUEST_BYTES:
        raise RequestLimitConfigurationError(
            "FINSHIELD_MAX_REQUEST_BYTES must be between "
            f"{MIN_MAX_REQUEST_BYTES} and {MAX_MAX_REQUEST_BYTES}"
        )
    return value


def verify_request_limit_configuration(
    values: Mapping[str, str] | None = None,
) -> None:
    read_max_request_bytes(values)


def install_request_limits(app: FastAPI) -> None:
    app.add_middleware(RequestSizeLimitMiddleware)


class RequestSizeLimitMiddleware:
    """순수 ASGI 미들웨어.

    `BaseHTTPMiddleware`가 아닌 이유는 `receive`를 직접 감싸야 하기 때문이다.
    바이트를 세려면 스트림 자체에 개입해야 한다.
    """

    def __init__(self, app: ASGIApp, max_bytes: int | None = None) -> None:
        self.app = app
        self._max_bytes = max_bytes

    @property
    def max_bytes(self) -> int:
        # 테스트가 환경변수로 상한을 바꿀 수 있도록 요청 시점에 읽는다.
        return self._max_bytes if self._max_bytes is not None else read_max_request_bytes()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        max_bytes = self.max_bytes
        declared = _declared_length(scope)
        if declared is not None and declared > max_bytes:
            # 본문을 한 바이트도 읽지 않고 끊는다.
            await _too_large(max_bytes)(scope, receive, send)
            return

        received = 0
        exceeded = False
        response_started = False
        rejected = False

        async def counting_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > max_bytes:
                    exceeded = True
                    # 예외를 던지지 않는다. FastAPI 는 `request.body()` 에서 나온
                    # 예외를 전부 400 "error parsing the body" 로 감싸버려서
                    # 여기까지 올라오지 않는다. 대신 연결이 끊긴 것처럼 알려
                    # 앱을 즉시 풀어주고, 응답은 아래 send 쪽에서 갈아끼운다.
                    return {"type": "http.disconnect"}
            return message

        async def limiting_send(message: Message) -> None:
            nonlocal response_started, rejected
            if exceeded and not response_started:
                # 본문이 상한을 넘은 이상 앱이 무엇을 말하든 의미가 없다.
                # 파싱 실패로 나온 400 을 그대로 내보내면 원인이 가려진다.
                if not rejected:
                    rejected = True
                    await _too_large(max_bytes)(scope, receive, send)
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        await self.app(scope, counting_receive, limiting_send)

        if exceeded and not response_started and not rejected:
            # 앱이 아무 응답도 내지 않고 끝난 경우.
            await _too_large(max_bytes)(scope, receive, send)


def _declared_length(scope: Scope) -> int | None:
    for key, value in scope.get("headers", ()):
        if key == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


def _too_large(max_bytes: int) -> JSONResponse:
    return JSONResponse(
        {"detail": "request body too large", "max_bytes": max_bytes},
        status_code=413,
    )
