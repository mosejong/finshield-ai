import { NextResponse } from "next/server";
import { AnalyzeRequestSchema } from "@/lib/api/contracts";
import { analyzeOnServer, describeApiError } from "@/lib/api/analysis";

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
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { message: "요청 형식이 올바르지 않습니다." },
      { status: 400 },
    );
  }

  const parsed = AnalyzeRequestSchema.safeParse(body);
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
    const result = await analyzeOnServer(parsed.data);
    return NextResponse.json(result);
  } catch (error) {
    const failure = describeApiError(error);
    // 실패를 "위험 없음"으로 바꾸지 않는다. 502 로 명시한다.
    return NextResponse.json(failure, { status: 502 });
  }
}
