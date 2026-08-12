import { NextResponse } from "next/server";
import { WealthGuidanceResponseSchema } from "@/lib/api/contracts";
import { requestJson } from "@/lib/api/client";


export const runtime = "nodejs";
export const dynamic = "force-dynamic";


export async function GET() {
  try {
    const result = await requestJson(
      "GET",
      "/api/v1/guidance/wealth",
      undefined,
      WealthGuidanceResponseSchema,
    );
    return NextResponse.json(result);
  } catch {
    return NextResponse.json(
      { message: "공식 금융교육 정보를 확인하지 못했습니다." },
      { status: 502 },
    );
  }
}
