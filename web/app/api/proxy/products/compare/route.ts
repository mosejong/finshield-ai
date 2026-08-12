import { NextResponse } from "next/server";
import { ApiError, postJson } from "@/lib/api/client";
import {
  ProductComparisonRequestSchema,
  ProductComparisonResponseSchema,
} from "@/lib/api/contracts";


export const runtime = "nodejs";
export const dynamic = "force-dynamic";


function upstreamStatus(error: unknown): number {
  if (error instanceof ApiError && [404, 503].includes(error.status)) {
    return error.status;
  }
  return 502;
}


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

  const parsed = ProductComparisonRequestSchema.safeParse(body);
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
    );
    return NextResponse.json(result);
  } catch (error) {
    return NextResponse.json(
      { message: "공식 상품 비교 정보를 확인하지 못했습니다." },
      { status: upstreamStatus(error) },
    );
  }
}
