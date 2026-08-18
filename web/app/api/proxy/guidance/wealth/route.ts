import { NextResponse } from "next/server";
import { WealthGuidanceResponseSchema } from "@/lib/api/contracts";
import { requestJson } from "@/lib/api/client";
import { backendHeaders } from "@/lib/api/server-auth";
import { upstreamFailure } from "@/lib/api/proxy-response";


export const runtime = "nodejs";
export const dynamic = "force-dynamic";


export async function GET(request: Request) {
  try {
    const result = await requestJson(
      "GET",
      "/api/v1/guidance/wealth",
      undefined,
      WealthGuidanceResponseSchema,
      undefined,
      backendHeaders(request),
    );
    return NextResponse.json(result);
  } catch (error) {
    return upstreamFailure(error, "공식 금융교육 정보를 확인하지 못했습니다.");
  }
}
