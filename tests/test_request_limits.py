import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.request_limits import (
    DEFAULT_MAX_REQUEST_BYTES,
    RequestLimitConfigurationError,
    RequestSizeLimitMiddleware,
    install_request_limits,
    read_max_request_bytes,
    verify_request_limit_configuration,
)

JSON_HEADERS = {"Content-Type": "application/json"}


@pytest.fixture()
def limited_app() -> FastAPI:
    app = FastAPI()

    @app.post("/echo")
    async def echo(payload: dict) -> dict:
        return {"size": len(json.dumps(payload))}

    @app.get("/ping")
    async def ping() -> dict:
        return {"ok": True}

    install_request_limits(app)
    return app


def _oversized_body(limit: int) -> bytes:
    return json.dumps({"text": "a" * (limit + 1024)}).encode()


def test_declared_content_length_over_limit_is_rejected(
    limited_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FINSHIELD_MAX_REQUEST_BYTES", "8192")
    with TestClient(limited_app) as client:
        response = client.post(
            "/echo", content=_oversized_body(8192), headers=JSON_HEADERS
        )
    assert response.status_code == 413
    assert response.json()["max_bytes"] == 8192


@pytest.mark.parametrize("chunked", [False, True])
def test_oversized_body_never_reaches_the_handler(
    monkeypatch: pytest.MonkeyPatch, chunked: bool
) -> None:
    """413이 나더라도 핸들러 본문은 실행되면 안 된다.

    본문 크기 제한이 스키마 검증 뒤에 걸리면, 거부하기 전에 이미 본문을
    다 읽고 파싱한 뒤다. 제한의 의미가 없어진다.
    """
    monkeypatch.setenv("FINSHIELD_MAX_REQUEST_BYTES", "8192")
    reached = False

    app = FastAPI()

    @app.post("/echo")
    async def echo(payload: dict) -> dict:
        nonlocal reached
        reached = True
        return {"ok": True}

    install_request_limits(app)

    body = _oversized_body(8192)
    content: object = body
    if chunked:

        def chunks():
            for start in range(0, len(body), 1024):
                yield body[start : start + 1024]

        content = chunks()

    with TestClient(app) as client:
        response = client.post("/echo", content=content, headers=JSON_HEADERS)

    assert response.status_code == 413
    assert reached is False


def test_chunked_body_without_content_length_is_rejected(
    limited_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`Content-Length`가 없어도 막혀야 한다.

    헤더만 보고 판단하면 chunked 전송으로 그대로 우회된다.
    """
    monkeypatch.setenv("FINSHIELD_MAX_REQUEST_BYTES", "8192")
    body = _oversized_body(8192)

    def chunks():
        for start in range(0, len(body), 1024):
            yield body[start : start + 1024]

    with TestClient(limited_app) as client:
        response = client.post("/echo", content=chunks(), headers=JSON_HEADERS)

    assert response.status_code == 413
    # 파싱 실패로 나온 400 이 아니라 크기 초과라는 사실이 응답에 남아야 한다.
    assert response.json()["detail"] == "request body too large"


def test_understated_content_length_does_not_bypass_the_limit(
    limited_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """선언된 길이를 믿지 않는다.

    `Content-Length: 10`을 붙이고 실제로는 대용량을 흘려보내는 요청이
    통과하면 헤더 검사는 장식일 뿐이다.
    """
    monkeypatch.setenv("FINSHIELD_MAX_REQUEST_BYTES", "8192")
    body = _oversized_body(8192)

    def chunks():
        yield body

    with TestClient(limited_app) as client:
        response = client.post(
            "/echo",
            content=chunks(),
            headers={**JSON_HEADERS, "Content-Length": "10"},
        )

    assert response.status_code == 413


def test_normal_request_passes_through(
    limited_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FINSHIELD_MAX_REQUEST_BYTES", "8192")
    with TestClient(limited_app) as client:
        response = client.post("/echo", json={"text": "정상 요청"})
    assert response.status_code == 200


def test_request_without_body_passes_through(
    limited_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FINSHIELD_MAX_REQUEST_BYTES", "4096")
    with TestClient(limited_app) as client:
        response = client.get("/ping")
    assert response.status_code == 200


def test_body_exactly_at_the_limit_is_allowed(
    limited_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """경계는 거부가 아니라 허용이다. 상한'까지'는 받는다."""
    monkeypatch.setenv("FINSHIELD_MAX_REQUEST_BYTES", "4096")
    filler = "a" * (4096 - len(json.dumps({"text": ""}).encode()))
    body = json.dumps({"text": filler}).encode()
    assert len(body) == 4096

    with TestClient(limited_app) as client:
        response = client.post("/echo", content=body, headers=JSON_HEADERS)

    assert response.status_code == 200


def test_default_limit_leaves_room_for_the_largest_valid_analysis_body(
    limited_app: FastAPI,
) -> None:
    """기본값이 정상 요청을 자르면 안 된다.

    `AnalyzeRequest.text`는 10000자까지 허용한다. 한글이 전부 `\\uXXXX`로
    이스케이프되는 최악의 경우가 기본 상한 안에 들어와야, 스키마는 통과하는데
    미들웨어가 막는 모순이 생기지 않는다.
    """
    worst_case = json.dumps(
        {"text": "가" * 10_000, "url": "https://example.com/" + "a" * 2_000},
        ensure_ascii=True,
    ).encode()
    assert len(worst_case) < DEFAULT_MAX_REQUEST_BYTES

    with TestClient(limited_app) as client:
        response = client.post("/echo", content=worst_case, headers=JSON_HEADERS)

    assert response.status_code == 200


async def _drive(
    middleware: RequestSizeLimitMiddleware,
    *,
    chunk_count: int,
    chunk_size: int,
) -> tuple[int, list[dict]]:
    """미들웨어를 ASGI 레벨에서 직접 돌린다.

    `TestClient` 의 transport 는 본문을 통째로 읽어 한 메시지로 전달하므로
    "상한을 넘은 시점에 읽기를 멈추는가" 를 확인할 수 없다.
    """
    pulled = 0
    sent: list[dict] = []

    async def receive() -> dict:
        nonlocal pulled
        if pulled >= chunk_count:
            return {"type": "http.request", "body": b"", "more_body": False}
        pulled += 1
        return {
            "type": "http.request",
            "body": b"a" * chunk_size,
            "more_body": pulled < chunk_count,
        }

    async def send(message: dict) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/echo",
        "headers": [],
    }
    await middleware(scope, receive, send)
    return pulled, sent


@pytest.mark.anyio
async def test_reading_stops_once_the_limit_is_passed() -> None:
    """상한을 넘으면 나머지 본문을 받지 않는다.

    끝까지 읽은 뒤 거부하면 메모리와 대역폭은 이미 다 쓴 뒤다.
    제한이 실제로 지켜주는 것이 없다.
    """
    drained = False

    async def app(scope, receive, send) -> None:
        nonlocal drained
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                break
            if not message.get("more_body", False):
                drained = True
                break
        await send(
            {"type": "http.response.start", "status": 200, "headers": []}
        )
        await send({"type": "http.response.body", "body": b"{}"})

    middleware = RequestSizeLimitMiddleware(app, max_bytes=4_096)
    pulled, sent = await _drive(middleware, chunk_count=1_000, chunk_size=1_024)

    assert sent[0]["status"] == 413
    # 4096 상한이면 1KB 청크 5개째에서 넘어선다. 1000개를 다 받으면 안 된다.
    assert pulled == 5
    assert drained is False


@pytest.mark.anyio
async def test_response_is_not_replaced_once_it_has_started() -> None:
    """이미 나가기 시작한 응답의 상태 코드는 바꿀 수 없다.

    본문을 다 읽기 전에 응답을 시작하는 핸들러가 있으면, 미들웨어가 뒤늦게
    413을 끼워 넣으려다 ASGI 프로토콜을 깨뜨린다.
    """

    async def app(scope, receive, send) -> None:
        await send(
            {"type": "http.response.start", "status": 200, "headers": []}
        )
        while True:
            message = await receive()
            if message["type"] == "http.disconnect" or not message.get(
                "more_body", False
            ):
                break
        await send({"type": "http.response.body", "body": b"{}"})

    middleware = RequestSizeLimitMiddleware(app, max_bytes=4_096)
    _, sent = await _drive(middleware, chunk_count=1_000, chunk_size=1_024)

    assert [message["type"] for message in sent] == [
        "http.response.start",
        "http.response.body",
    ]
    assert sent[0]["status"] == 200


def test_analyze_endpoint_rejects_an_oversized_body() -> None:
    """실제 앱에 붙어 있는지 확인한다.

    미들웨어가 동작해도 `app/main.py` 에 설치되지 않으면 아무것도 막지 못한다.
    """
    from app.main import app as main_app

    body = json.dumps({"text": "가" * 200_000}).encode()
    with TestClient(main_app) as client:
        response = client.post("/api/v1/analyze", content=body, headers=JSON_HEADERS)

    assert response.status_code == 413
    # 크기 제한이 보안 미들웨어 안쪽에 있어야 413 에도 보안 헤더가 붙는다.
    assert response.headers["x-content-type-options"] == "nosniff"


def test_analyze_endpoint_still_accepts_a_maximum_length_message() -> None:
    """상한이 정상 요청을 자르지 않는지 실제 엔드포인트로 확인한다."""
    from app.main import app as main_app

    with TestClient(main_app) as client:
        response = client.post("/api/v1/analyze", json={"text": "가" * 10_000})

    assert response.status_code == 200


def test_limit_reads_from_the_environment() -> None:
    assert read_max_request_bytes({}) == DEFAULT_MAX_REQUEST_BYTES
    assert read_max_request_bytes({"FINSHIELD_MAX_REQUEST_BYTES": " 65536 "}) == 65_536


@pytest.mark.parametrize(
    "value",
    ["not-a-number", "", "1024", "20971520", "-1"],
)
def test_invalid_limit_configuration_is_rejected(value: str) -> None:
    with pytest.raises(RequestLimitConfigurationError):
        verify_request_limit_configuration({"FINSHIELD_MAX_REQUEST_BYTES": value})
