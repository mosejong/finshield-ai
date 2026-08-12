import { z } from "zod";

/**
 * FastAPI 백엔드 호출용 fetch 래퍼.
 *
 * 브라우저에서 직접 부르지 않는다. FastAPI 에 CORSMiddleware 가 없기 때문에
 * 항상 Next.js Route Handler(서버) 를 거친다. app/api/proxy/* 참고.
 */

const DEFAULT_TIMEOUT_MS = 8000;

export class ApiError extends Error {
  readonly status: number;
  readonly kind: "network" | "timeout" | "http" | "schema";

  constructor(
    kind: ApiError["kind"],
    message: string,
    status = 0,
    options?: { cause?: unknown },
  ) {
    super(message, options);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
  }
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
): Promise<T> {
  return requestJson("POST", path, body, schema, timeoutMs);
}

export async function requestJson<T>(
  method: "GET" | "POST" | "PUT",
  path: string,
  body: unknown,
  schema: z.ZodType<T>,
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await fetch(`${backendBaseUrl()}${path}`, {
      method,
      headers: { "Content-Type": "application/json" },
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
): Promise<void> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await fetch(`${backendBaseUrl()}${path}`, {
      method,
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
    );
  }
}
