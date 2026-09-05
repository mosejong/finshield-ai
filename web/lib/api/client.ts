import { z } from "zod";

/**
 * FastAPI 백엔드 호출용 fetch 래퍼.
 *
 * 브라우저에서 직접 부르지 않는다. FastAPI 에 CORSMiddleware 가 없기 때문에
 * 항상 Next.js Route Handler(서버) 를 거친다. app/api/proxy/* 참고.
 */

const DEFAULT_TIMEOUT_MS = 8000;

/**
 * 공식 상품 목록을 거치는 경로의 예산.
 *
 * 기본 8초는 백엔드 한 번 왕복을 재는 값이다. 상품 경로는 그 안에서
 * 공공데이터포털을 여러 번 부르고, 캐시가 비어 있으면 그 값을 전부 치른다.
 * 2026-09-05 공개 URL 에서 캐시 없는 첫 요청이 9.6초에 끊겨 502 가 됐고,
 * 같은 요청이 캐시가 찬 뒤에는 1.1초였다. 8초는 백엔드가 살아 있는데도
 * 고장으로 보이게 만드는 값이었다.
 *
 * 늘린 예산은 실패를 감추지 않는다. 공급자가 정말 죽어 있으면 그때도 502 가
 * 나가고, 다만 살아 있는 느린 응답을 죽음으로 바꾸지 않을 뿐이다.
 */
export const CATALOG_TIMEOUT_MS = 20000;

export class ApiError extends Error {
  readonly status: number;
  readonly kind: "network" | "timeout" | "http" | "schema";
  /** 429 응답의 `Retry-After` (초). 없거나 해석할 수 없으면 undefined. */
  readonly retryAfterSeconds?: number;

  constructor(
    kind: ApiError["kind"],
    message: string,
    status = 0,
    options?: { cause?: unknown; retryAfterSeconds?: number },
  ) {
    super(message, options);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.retryAfterSeconds = options?.retryAfterSeconds;
  }
}

/**
 * `Retry-After` 를 초로 읽는다.
 *
 * 백엔드는 초만 보낸다. HTTP-date 형식은 항상 요일 이름으로 시작하므로
 * 여기서 NaN 이 되어 자연히 걸러진다.
 */
export function parseRetryAfter(headers: Headers): number | undefined {
  const raw = headers.get("retry-after");
  if (!raw) return undefined;
  const seconds = Number.parseInt(raw.trim(), 10);
  return Number.isFinite(seconds) && seconds > 0 ? seconds : undefined;
}

/** 한도 초과 안내 문구. 기다릴 시간을 알면 함께 알려준다. */
export function retryHint(seconds?: number): string {
  const wait = seconds && seconds > 0 ? `${seconds}초 뒤에` : "잠시 후";
  return `${wait} 다시 시도해 주세요.`;
}

/** 백엔드 주소. 서버 사이드에서만 읽는다. */
export function backendBaseUrl(): string {
  return process.env.FINSHIELD_API_URL ?? "http://127.0.0.1:8000";
}

export async function postJson<T>(
  path: string,
  body: unknown,
  schema: z.ZodType<T>,
  timeoutMs = DEFAULT_TIMEOUT_MS,
  headers: HeadersInit = {},
): Promise<T> {
  return requestJson("POST", path, body, schema, timeoutMs, headers);
}

export async function requestJson<T>(
  method: "GET" | "POST" | "PUT",
  path: string,
  body: unknown,
  schema: z.ZodType<T>,
  timeoutMs = DEFAULT_TIMEOUT_MS,
  headers: HeadersInit = {},
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    const requestHeaders = new Headers(headers);
    requestHeaders.set("Content-Type", "application/json");
    response = await fetch(`${backendBaseUrl()}${path}`, {
      method,
      headers: requestHeaders,
      body: method === "GET" ? undefined : JSON.stringify(body),
      signal: controller.signal,
      cache: "no-store",
    });
  } catch (cause) {
    const timedOut = controller.signal.aborted;
    throw new ApiError(
      timedOut ? "timeout" : "network",
      timedOut
        ? "분석 서버 응답이 너무 늦습니다."
        : "분석 서버에 연결하지 못했습니다.",
      0,
      { cause },
    );
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) {
    // 제공자 오류를 "위험 없음"으로 바꾸지 않는다. (docs/11-engineering-standards.md)
    throw new ApiError(
      "http",
      `분석 서버가 오류를 반환했습니다. (${response.status})`,
      response.status,
      { retryAfterSeconds: parseRetryAfter(response.headers) },
    );
  }

  const parsed = schema.safeParse(await response.json());
  if (!parsed.success) {
    throw new ApiError(
      "schema",
      "분석 서버 응답 형식이 예상과 다릅니다.",
      response.status,
      { cause: parsed.error },
    );
  }

  return parsed.data;
}

export async function requestNoContent(
  method: "DELETE",
  path: string,
  timeoutMs = DEFAULT_TIMEOUT_MS,
  headers: HeadersInit = {},
): Promise<void> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await fetch(`${backendBaseUrl()}${path}`, {
      method,
      headers,
      signal: controller.signal,
      cache: "no-store",
    });
  } catch (cause) {
    throw new ApiError(
      controller.signal.aborted ? "timeout" : "network",
      "서버에 연결하지 못했습니다.",
      0,
      { cause },
    );
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) {
    throw new ApiError(
      "http",
      `서버가 오류를 반환했습니다. (${response.status})`,
      response.status,
      { retryAfterSeconds: parseRetryAfter(response.headers) },
    );
  }
}
