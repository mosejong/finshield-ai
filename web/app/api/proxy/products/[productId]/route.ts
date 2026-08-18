import { NextResponse } from "next/server";
import { requestJson } from "@/lib/api/client";
import {
  BackendProductSchema,
  ProductSourceIdSchema,
} from "@/lib/api/contracts";
import { backendHeaders } from "@/lib/api/server-auth";
import { upstreamFailure } from "@/lib/api/proxy-response";


export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Context = { params: Promise<{ productId: string }> };


export async function GET(request: Request, context: Context) {
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
      undefined,
      backendHeaders(request),
    );
    return NextResponse.json(result);
  } catch (error) {
    return upstreamFailure(error, "공식 상품 상세 정보를 확인하지 못했습니다.");
  }
}
