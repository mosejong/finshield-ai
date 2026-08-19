"""Google AI Studio (Gemini API) 프로바이더.

`app/services/llm/` 의 `LlmProvider` 를 만족하는 유일한 실제 구현이다. 계약 경계는
이미 그쪽에서 강제되므로, 여기서 할 일은 좁다 — 고정된 엔드포인트 하나에 요청을
보내고, 텍스트 하나를 꺼내고, **나머지 모든 경우를 `LlmUnavailable` 로 접는 것.**

이 파일이 지키는 것 세 가지.

1. **키를 흘리지 않는다.** 키는 쿼리스트링이 아니라 헤더로 보낸다. URL 은 로그·
   프록시·오류 보고서에 남지만 헤더는 덜 남는다. 예외 메시지에도 키가 들어가지
   않는다.
2. **원문을 로그로 남기지 않는다.** 이 모듈은 로거를 import 하지 않는다. 예외
   메시지에 응답 본문을 넣지 않는 것도 같은 이유다 — 400 응답이 요청 일부를
   되돌려 주는 경우가 있다.
3. **재시도하지 않는다.** 설명은 있으면 좋고 없어도 되는 것이다. 실패한 호출을
   다시 보내면 지연만 늘고, 유료 호출이 두 번 나간다.

`follow_redirects=False` 는 `PublicDataProductClient` 와 같은 이유다. 리다이렉트를
따라가면 키가 실린 요청이 우리가 고르지 않은 호스트로 간다.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from typing import Any

import httpx

from app.core.runtime_secrets import (
    RuntimeSecretConfigurationError,
    read_secret_setting,
)
from app.services.llm.contract import LlmContract
from app.services.llm.provider import LlmUnavailable

API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

PROVIDER_NAME = "google_ai_studio"

# 설명은 600자 상한이다(`explanation.py`). 토큰은 넉넉히 주고, 넘치면 잘린 문장을
# 보여 주는 대신 통째로 버린다 - 아래 finishReason 검사가 그 역할을 한다.
#
# 1024 였다가 4096 으로 올렸다(2026-08-19). 답변 길이 때문이 아니다 - Gemini 3.x
# flash 계열은 **사고 토큰(thinking)이 같은 예산에서 나간다.** 1024 로 두면 사고에
# 982 토큰이 나가고 답변 몫으로 38 토큰만 남아, `finishReason` 이 항상 `MAX_TOKENS`
# 가 된다. 즉 모델은 정상 동작하는데 우리 쪽 예산 때문에 매번 버려졌다.
# `gemini-3.6-flash` 와 `gemini-3.5-flash` 둘 다 재현됐고, 사고를 하지 않는
# `gemini-3.1-flash-lite` 만 통과하고 있었다. 이 상수는 답변 길이가 아니라
# 사고 + 답변의 합으로 잡아야 한다.
MAX_OUTPUT_TOKENS = 4096

# 사고 깊이. 이 작업은 이미 확정된 판정을 3~5문장으로 옮기는 일이고, 출력은 어차피
# `validation.py` 를 통과해야 한다. 깊게 생각해서 좋아지는 종류의 과제가 아니다.
#
# 실측(2026-08-19): `gemini-3.5-flash` 는 기본값에서 위 `MAX_TOKENS` 에 걸렸고
# `low` 에서 4.34초에 정상 응답했다. `gemini-3.6-flash` 는 8.30초 -> 6.3~7.4초.
# 사고를 아예 끄는 `thinkingBudget: 0` 은 `gemini-3.6-flash` 에서 HTTP 400 이다.
#
# 이 키를 모르는 모델은 400 을 돌려주고, 그러면 `LlmUnavailable` 로 접혀 다음
# 모델로 넘어간다. 조용히 품질이 나빠지는 대신 그 모델이 통째로 빠지는 쪽이다.
THINKING_LEVEL = "low"

# 모델명은 URL 경로에 들어간다. 계약에서 오는 값이라 사용자 입력은 아니지만,
# 경로에 넣는 문자열은 넣기 전에 본다.
_MODEL_PATTERN = re.compile(r"^[A-Za-z0-9.\-]+$")


class GoogleAiStudioConfigurationError(RuntimeError):
    """키가 없거나 비어 있다. 요청 도중이 아니라 조립 시점에 터져야 한다."""


class GoogleAiStudioProvider:
    """`LlmProvider` 구현.

    `client` 를 주입할 수 있어 테스트가 네트워크 없이 전 경로를 돈다.
    """

    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        normalized_key = api_key.strip()
        if not normalized_key:
            raise GoogleAiStudioConfigurationError("GEMINI_API_KEY is not configured")
        self._api_key = normalized_key
        self._client = client

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    def generate(self, *, contract: LlmContract, prompt: str) -> str:
        if contract.provider != PROVIDER_NAME:
            # 계약이 다른 프로바이더용인데 여기로 흘러왔다. 조용히 처리하면 어디로
            # 나가는지 아무도 모르게 된다.
            raise LlmUnavailable(
                f"{PROVIDER_NAME} cannot serve a contract for {contract.provider}"
            )
        if not _MODEL_PATTERN.match(contract.model):
            raise LlmUnavailable(f"unsupported model name: {contract.model!r}")

        url = f"{API_BASE_URL}/{contract.model}:generateContent"
        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": contract.temperature,
                "maxOutputTokens": MAX_OUTPUT_TOKENS,
                "thinkingConfig": {"thinkingLevel": THINKING_LEVEL},
            },
        }
        headers = {
            "x-goog-api-key": self._api_key,
            "content-type": "application/json",
        }

        try:
            if self._client is not None:
                response = self._client.post(url, json=payload, headers=headers)
            else:
                with httpx.Client(
                    timeout=httpx.Timeout(contract.timeout_seconds),
                    follow_redirects=False,
                ) as client:
                    response = client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            # 예외 본문에 원인 문자열만 넣는다. 요청 본문은 넣지 않는다.
            raise LlmUnavailable(
                f"{PROVIDER_NAME} request failed: {type(exc).__name__}"
            ) from exc

        if response.status_code != 200:
            # 상태 코드만 남긴다. 본문은 요청 일부를 되돌려 줄 수 있다.
            raise LlmUnavailable(
                f"{PROVIDER_NAME} returned HTTP {response.status_code}"
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise LlmUnavailable(f"{PROVIDER_NAME} returned a non-JSON body") from exc

        return _extract_text(body)


def _extract_text(body: Any) -> str:
    """응답에서 문장 하나를 꺼낸다. 못 꺼내면 전부 `LlmUnavailable`.

    빈 문자열을 돌려주지 않는 것이 중요하다. 빈 문자열은 "모델이 답했지만 할 말이
    없었다" 처럼 보이는데, 실제로는 안전 필터에 막혔거나 응답 모양이 바뀐 것이다.
    """
    if not isinstance(body, dict):
        raise LlmUnavailable(f"{PROVIDER_NAME} returned an unexpected payload shape")

    candidates = body.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        # 안전 필터 차단이 여기로 온다. `promptFeedback.blockReason` 이 붙지만
        # 사유 문자열을 그대로 올리지는 않는다.
        raise LlmUnavailable(f"{PROVIDER_NAME} returned no candidate")

    candidate = candidates[0]
    if not isinstance(candidate, dict):
        raise LlmUnavailable(f"{PROVIDER_NAME} returned an unexpected candidate shape")

    finish_reason = candidate.get("finishReason")
    if finish_reason not in (None, "STOP"):
        # MAX_TOKENS 로 잘린 문장을 사용자에게 보여 주지 않는다. SAFETY,
        # RECITATION 도 마찬가지로 설명 없이 간다.
        raise LlmUnavailable(f"{PROVIDER_NAME} stopped early: {finish_reason}")

    parts = candidate.get("content", {}).get("parts")
    if not isinstance(parts, list):
        raise LlmUnavailable(f"{PROVIDER_NAME} returned no content parts")

    text = "".join(
        part["text"]
        for part in parts
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    )
    if not text.strip():
        raise LlmUnavailable(f"{PROVIDER_NAME} returned empty text")
    return text


def build_google_ai_studio_provider(
    values: Mapping[str, str] | None = None,
) -> GoogleAiStudioProvider:
    """환경에서 키를 읽어 조립한다.

    `GEMINI_API_KEY` 또는 `GEMINI_API_KEY_FILE` 을 받는다. 후자가 Docker secret
    경로다 - 키를 환경변수로 두면 `docker inspect` 와 프로세스 목록에 남는다.

    `values` 를 받는 이유는 부르는 쪽(`llm/runtime.py`)이 이미 매핑 하나로 설정을
    읽고 있기 때문이다. 여기서만 `os.environ` 을 직접 보면, 매핑을 넘겼는데 키만
    프로세스 환경에서 오는 상태가 된다 - 테스트가 통과하는 이유와 운영이 도는
    이유가 달라지는 종류의 함정이다.
    """
    environ = values if values is not None else os.environ
    try:
        api_key = read_secret_setting(environ, "GEMINI_API_KEY")
    except RuntimeSecretConfigurationError as exc:
        raise GoogleAiStudioConfigurationError(
            "GEMINI_API_KEY secret configuration is invalid"
        ) from exc
    return GoogleAiStudioProvider(api_key)
