import {
  BackendExplanationResponseSchema,
  ExplanationSchema,
  type AnalyzeRequest,
  type Explanation,
} from "@/lib/api/contracts";
import { postJson } from "@/lib/api/client";
import { apiMode } from "@/lib/api/mode";

/**
 * 판정을 문장으로 옮긴 설명.
 *
 * 판정과 따로 부르는 이유는 백엔드가 나눠 놓은 이유와 같다. 설명 한 문단에 약
 * 8초가 걸리고(`docs/34` 2-1 실측), 그것을 판정에 붙이면 위험 수준을 보여주기
 * 까지 8초를 기다리게 된다. 지금 의심 문자를 받은 사람에게 가장 나쁜 순서다.
 * 그래서 결과 화면은 판정으로 먼저 그려지고, 이 호출은 "왜 위험한지" 블록
 * 안에서만 기다린다.
 *
 * 이 모듈은 위험도를 만들지 않는다. 설명이 없어도 화면은 그대로 성립하고,
 * 설명이 늦거나 실패해도 판정은 이미 화면에 있다.
 */

/**
 * 설명은 모델 호출이라 판정보다 훨씬 오래 걸린다. 백엔드가 두 모델을 순서대로
 * 시도하고 최악의 경우 20초에서 자르므로(`app/services/llm/runtime.py`), 여기는
 * 그보다 조금 길게 잡는다. 8초 기본값을 그대로 쓰면 백엔드가 정상적으로 답하는
 * 중에 프론트가 먼저 끊는다.
 */
const EXPLANATION_TIMEOUT_MS = 25_000;

const OFF: Explanation = { status: "off", text: null, model: null };
const FAILED: Explanation = { status: "failed", text: null, model: null };

/** 백엔드 응답 → 화면 상태. `available` 과 `explanation` 을 합치지 않는다. */
export function toExplanation(backend: unknown): Explanation {
  const parsed = BackendExplanationResponseSchema.parse(backend);
  if (!parsed.available) return OFF;
  if (!parsed.explanation) return FAILED;
  return ExplanationSchema.parse({
    status: "ready",
    text: parsed.explanation,
    model: parsed.model,
  });
}

/**
 * 서버 사이드 전용. Route Handler 에서만 부른다.
 *
 * mock 모드에서 그럴듯한 문장을 지어내지 않는다. 다른 mock 데이터와 성격이
 * 다르기 때문이다 - 화면 구조를 보여주는 예시 값과, 모델이 실제로 뭐라고
 * 말하는지는 서로 대신할 수 없다. 백엔드 없이 볼 때 이 블록은 결정론 요약만
 * 보여주고 끝난다.
 */
export async function explainOnServer(
  request: AnalyzeRequest,
  headers: HeadersInit = {},
): Promise<Explanation> {
  if (apiMode() === "mock") return OFF;

  const backend = await postJson(
    "/api/v1/analyze/explanation",
    {
      text: request.text,
      persona: request.persona,
      state: request.state,
      url: request.url ?? null,
    },
    BackendExplanationResponseSchema,
    EXPLANATION_TIMEOUT_MS,
    headers,
  );

  return toExplanation(backend);
}

/**
 * 클라이언트 → Next Route Handler.
 *
 * 실패를 예외로 올리지 않고 `failed` 로 돌려준다. 설명은 있으면 좋고 없어도
 * 되는 것이라, 이것 때문에 결과 화면이 오류 화면으로 바뀌면 안 된다. 다만
 * 조용히 `off` 로 접지도 않는다 - 켜져 있는데 못 만든 것은 사용자가 알 수
 * 있어야 하고, 그래야 다시 시도할지 판단한다.
 */
export async function explainFromClient(
  request: AnalyzeRequest,
): Promise<Explanation> {
  let response: Response;
  try {
    response = await fetch("/api/proxy/analyze/explanation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      cache: "no-store",
    });
  } catch {
    return FAILED;
  }

  if (!response.ok) return FAILED;

  const payload: unknown = await response.json().catch(() => null);
  const parsed = ExplanationSchema.safeParse(payload);
  return parsed.success ? parsed.data : FAILED;
}
