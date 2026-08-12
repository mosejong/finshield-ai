import { NextResponse } from "next/server";
import { ApiError, requestJson } from "@/lib/api/client";
import {
  BackendProductSchema,
  ProductSourceIdSchema,
} from "@/lib/api/contracts";


export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Context = { params: Promise<{ productId: string }> };


function upstreamStatus(error: unknown): number {
  if (error instanceof ApiError && [404, 503].includes(error.status)) {
    return error.status;
  }
  return 502;
}


export async function GET(_request: Request, context: Context) {
  const { productId: rawProductId } = await context.params;
  let decodedProductId: string;
  try {
    decodedProductId = decodeURIComponent(rawProductId);
  } catch {
    return NextResponse.json(
      { message: "상품 식별자가 올바르지 않습니다." },
      { status: 400 },
    );
  }
  const parsed = ProductSourceIdSchema.safeParse(decodedProductId);
  if (!parsed.success) {
    return NextResponse.json(
      { message: "상품 식별자가 올바르지 않습니다." },
      { status: 400 },
    );
  }

  try {
    const result = await requestJson(
      "GET",
      `/api/v1/products/${encodeURIComponent(parsed.data)}`,
      undefined,
      BackendProductSchema,
    );
    return NextResponse.json(result);
  } catch (error) {
    return NextResponse.json(
      { message: "공식 상품 상세 정보를 확인하지 못했습니다." },
      { status: upstreamStatus(error) },
    );
  }
}
