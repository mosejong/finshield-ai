import { NextResponse } from "next/server";

/**
 * 프록시 라우트가 읽는 JSON 본문의 크기 상한.
 *
 * 백엔드에는 `FINSHIELD_MAX_REQUEST_BYTES` 상한이 이미 있지만, 배포 경로는
 * Caddy -> web -> backend 라서 인터넷에 직접 노출된 쪽은 web 이다. Route
 * Handler 에는 본문 크기 기본 상한이 없어서 `request.json()` 을 그냥 부르면
 * 100MB 짜리 본문도 전부 메모리에 담은 뒤에야 스키마 검증에서 거부한다.
 * 백엔드는 그 요청을 구경도 못 하므로 백엔드 상한은 여기서 도움이 안 된다.
 *
 * `Content-Length` 만 믿지 않는 이유는 백엔드
 * (`app/core/request_limits.py`) 와 같다. chunked 전송에는 헤더가 없고,
 * 헤더 값이 실제 본문과 다를 수도 있다. 헤더는 빠른 거부에만 쓰고 실제
 * 판단은 흘러오는 바이트를 세서 한다.
 */

const DEFAULT_MAX_BODY_BYTES = 131_072;
const MIN_MAX_BODY_BYTES = 4_096;
const MAX_MAX_BODY_BYTES = 10_485_760;

/**
 * 백엔드 `FINSHIELD_MAX_REQUEST_BYTES` 와 같은 값을 읽는다. 두 상한이 벌어지면
 * web 이 더 작을 때는 백엔드가 받아줄 요청을 여기서 413 으로 막고, web 이 더
 * 클 때는 백엔드가 어차피 거부할 본문을 통째로 메모리에 담는다.
 *
 * 값이 이상하면 조용히 기본값으로 돌아간다. 잘못된 값에 대한 경고는 백엔드가
 * 기동 시점에 이미 크게 낸다. 여기서 같이 죽어봐야 화면만 함께 사라진다.
 */
export function maxProxyBodyBytes(): number {
  const raw = Number.parseInt(process.env.FINSHIELD_MAX_REQUEST_BYTES ?? "", 10);
  if (!Number.isFinite(raw)) return DEFAULT_MAX_BODY_BYTES;
  if (raw < MIN_MAX_BODY_BYTES || raw > MAX_MAX_BODY_BYTES) {
    return DEFAULT_MAX_BODY_BYTES;
  }
  return raw;
}

export type JsonBodyResult =
  | { ok: true; value: unknown }
  | { ok: false; response: NextResponse };

export type LimitedBodyResult =
  // `Uint8Array<ArrayBuffer>` 로 좁혀 둔다. 기본 `ArrayBufferLike` 는
  // SharedArrayBuffer 도 포함해서 `new Response(bytes)` 에 그대로 넘길 수 없다.
  | { ok: true; bytes: Uint8Array<ArrayBuffer> }
  | { ok: false; reason: "too_large" | "unreadable" };

/**
 * 상한을 지키며 본문을 바이트로 읽는다.
 *
 * JSON 이 아닌 본문을 다루는 곳(공유 시트가 보내는 multipart)이 쓴다. 응답을
 * 만들지 않고 이유만 돌려주는 이유는, 그런 곳은 JSON 오류 형식이 아니라 사람이
 * 읽는 HTML 로 답해야 하기 때문이다.
 */
export async function readLimitedBody(
  request: Request,
  maxBytes: number = maxProxyBodyBytes(),
): Promise<LimitedBodyResult> {
  const declared = Number.parseInt(
    request.headers.get("content-length") ?? "",
    10,
  );
  if (Number.isFinite(declared) && declared > maxBytes) {
    // 한 바이트도 읽지 않고 끊는다.
    return { ok: false, reason: "too_large" };
  }

  try {
    return { ok: true, bytes: await readLimited(request, maxBytes) };
  } catch (error) {
    if (error instanceof BodyTooLargeError) {
      return { ok: false, reason: "too_large" };
    }
    return { ok: false, reason: "unreadable" };
  }
}

/**
 * 프록시 라우트의 본문 읽기 진입점. 실패하면 그대로 돌려보낼 응답을 준다.
 * `rejectCrossSiteRequest` 와 같은 사용 방식이다.
 *
 * ```ts
 * const body = await readJsonBody(request);
 * if (!body.ok) return body.response;
 * const parsed = Schema.safeParse(body.value);
 * ```
 */
export async function readJsonBody(
  request: Request,
  maxBytes: number = maxProxyBodyBytes(),
): Promise<JsonBodyResult> {
  const body = await readLimitedBody(request, maxBytes);
  if (!body.ok) {
    return {
      ok: false,
      response: body.reason === "too_large" ? tooLarge() : malformed(),
    };
  }

  try {
    return { ok: true, value: JSON.parse(new TextDecoder().decode(body.bytes)) };
  } catch {
    return { ok: false, response: malformed() };
  }
}

class BodyTooLargeError extends Error {}

async function readLimited(
  request: Request,
  maxBytes: number,
): Promise<Uint8Array<ArrayBuffer>> {
  const stream = request.body;
  if (!stream) {
    // 본문 없는 요청. 호출자가 빈 본문으로 처리한다.
    return new Uint8Array(0);
  }

  const reader = stream.getReader();
  const chunks: Uint8Array[] = [];
  let received = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      if (!value) continue;
      received += value.byteLength;
      if (received > maxBytes) throw new BodyTooLargeError();
      chunks.push(value);
    }
  } finally {
    // 상한을 넘긴 뒤에도 남은 업로드를 계속 받아주지 않는다.
    await reader.cancel().catch(() => {});
  }

  return merge(chunks, received);
}

function merge(chunks: Uint8Array[], total: number): Uint8Array<ArrayBuffer> {
  const merged = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return merged;
}

function tooLarge(): NextResponse {
  // 바이트 수를 문구에 넣지 않는다. 사용자가 할 수 있는 일은 내용을 줄이는
  // 것뿐이고, 숫자는 그 판단에 도움이 되지 않는다.
  return NextResponse.json(
    {
      message: "보낸 내용이 너무 커서 처리하지 못했습니다.",
      hint: "확인이 필요한 부분만 남기고 다시 시도해 주세요.",
    },
    { status: 413 },
  );
}

function malformed(): NextResponse {
  return NextResponse.json(
    { message: "요청 형식이 올바르지 않습니다." },
    { status: 400 },
  );
}
