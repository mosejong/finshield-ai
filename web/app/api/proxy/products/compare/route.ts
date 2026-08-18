import { NextResponse } from "next/server";
import { postJson } from "@/lib/api/client";
import {
  ProductComparisonRequestSchema,
  ProductComparisonResponseSchema,
} from "@/lib/api/contracts";
import { backendHeaders } from "@/lib/api/server-auth";
import { upstreamFailure } from "@/lib/api/proxy-response";
import { readJsonBody } from "@/lib/api/request-body";


export const runtime = "nodejs";
export const dynamic = "force-dynamic";


export async function POST(request: Request) {
  const body = await readJsonBody(request);
  if (!body.ok) return body.response;

  const parsed = ProductComparisonRequestSchema.safeParse(body.value);
  if (!parsed.success) {
    return NextResponse.json(
      { message: "서로 다른 공식 상품 2개를 선택해 주세요." },
      { status: 400 },
    );
  }

  try {
    const result = await postJson(
      "/api/v1/products/compare",
      parsed.data,
      ProductComparisonResponseSchema,
      undefined,
      backendHeaders(request),
    );
    return NextResponse.json(result);
  } catch (error) {
    return upstreamFailure(error, "공식 상품 비교 정보를 확인하지 못했습니다.");
  }
}
