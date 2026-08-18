import { NextResponse } from "next/server";
import { AnalyzeRequestSchema } from "@/lib/api/contracts";
import { analyzeOnServer, describeApiError } from "@/lib/api/analysis";
import { ApiError } from "@/lib/api/client";
import { backendHeaders } from "@/lib/api/server-auth";
import { upstreamStatus } from "@/lib/api/proxy-response";
import { readJsonBody } from "@/lib/api/request-body";

/**
 * FastAPI 백엔드로 가는 서버 사이드 프록시.
 *
 * 브라우저가 FastAPI 를 직접 부르지 않는 이유:
 *  1. 백엔드에 CORSMiddleware 가 없다 (백엔드는 이번 작업에서 수정하지 않는다).
 *  2. 백엔드 주소를 클라이언트 번들에 노출하지 않는다.
 *
 * 사용자가 입력한 원문은 여기서 로그로 남기지 않는다.
 * (docs/12-security-threat-model.md — log leakage)
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const body = await readJsonBody(request);
  if (!body.ok) return body.response;

  const parsed = AnalyzeRequestSchema.safeParse(body.value);
  if (!parsed.success) {
    return NextResponse.json(
      {
        message: "분석할 내용을 확인해 주세요.",
        hint: "메시지는 1자 이상 10,000자 이하여야 합니다.",
      },
      { status: 400 },
    );
  }

  try {
    const result = await analyzeOnServer(parsed.data, backendHeaders(request));
    return NextResponse.json(result);
  } catch (error) {
    const failure = describeApiError(error);
    // 실패를 "위험 없음"으로 바꾸지 않는다. 상태 코드로 명시한다.
    // 한도 초과(429)·본문 초과(413)는 백엔드 장애가 아니므로 502 로 덮지 않는다.
    const response = NextResponse.json(failure, { status: upstreamStatus(error) });
    const retryAfter =
      error instanceof ApiError ? error.retryAfterSeconds : undefined;
    if (retryAfter) response.headers.set("Retry-After", String(retryAfter));
    return response;
  }
}
