import { NextResponse } from "next/server";
import { ApiError, parseRetryAfter, retryHint } from "@/lib/api/client";

/**
 * 백엔드 실패를 프록시 응답으로 옮긴다.
 *
 * 서버 전용 모듈이다. 클라이언트 컴포넌트에서 import 하지 않는다.
 */

/**
 * 사용자가 알아야 의미가 있는 상태 코드. 나머지는 502 로 덮는다.
 *
 * 429 를 502 로 덮으면 "서버가 고장났다" 로 읽혀서 사용자는 계속 재시도한다.
 * 실제로는 잠시 기다리면 되는 상황이므로 그대로 넘긴다.
 */
const PASSTHROUGH_STATUSES = new Set([401, 404, 413, 429, 503]);

export function upstreamStatus(error: unknown): number {
  return error instanceof ApiError && PASSTHROUGH_STATUSES.has(error.status)
    ? error.status
    : 502;
}

/**
 * 실패 응답을 만든다. 실패를 "확인됨" 이나 "이상 없음" 으로 바꾸지 않는다.
 *
 * `message` 는 경로마다 다른 문구다. 한도 초과(429)만은 원인이 백엔드 장애가
 * 아니라서 공통 문구로 대체한다.
 */
export function upstreamFailure(error: unknown, message: string): NextResponse {
  const status = upstreamStatus(error);
  if (status !== 429) {
    return NextResponse.json({ message }, { status });
  }

  const seconds = error instanceof ApiError ? error.retryAfterSeconds : undefined;
  return rateLimited(seconds);
}

/**
 * 백엔드 응답을 그대로 흘려보내는 경로(auth)에서 쓰는 429 처리.
 *
 * 백엔드의 영문 `detail` 을 그대로 보여주지 않고 사용자 문구로 바꾼다.
 */
export function rateLimitedFromUpstream(upstream: Response): NextResponse {
  return rateLimited(parseRetryAfter(upstream.headers));
}

function rateLimited(seconds: number | undefined): NextResponse {
  const response = NextResponse.json(
    {
      message: "요청이 많아 잠시 멈췄습니다.",
      hint: retryHint(seconds),
    },
    { status: 429 },
  );
  if (seconds) response.headers.set("Retry-After", String(seconds));
  return response;
}
