import { NextResponse } from "next/server";
import { BackendRecommendationGoalSchema, ProductRecommendationResponseSchema } from "@/lib/api/contracts";
import { CATALOG_TIMEOUT_MS, postJson } from "@/lib/api/client";
import { backendHeaders } from "@/lib/api/server-auth";
import { upstreamFailure } from "@/lib/api/proxy-response";
import { readJsonBody } from "@/lib/api/request-body";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const body = await readJsonBody(request);
  if (!body.ok) return body.response;
  const payload = body.value;
  const parsed = BackendRecommendationGoalSchema.safeParse(
    typeof payload === "object" && payload !== null && "goal" in payload
      ? payload.goal
      : undefined,
  );
  if (!parsed.success) return NextResponse.json({ message: "금융 목표를 확인해 주세요." }, { status: 400 });
  try {
    const result = await postJson(
      "/api/v1/recommendations?page_size=100",
      { goal: parsed.data },
      ProductRecommendationResponseSchema,
      CATALOG_TIMEOUT_MS,
      backendHeaders(request),
    );
    return NextResponse.json(result);
  } catch (error) {
    return upstreamFailure(error, "공식 상품 정보를 확인하지 못했습니다.");
  }
}
