import { NextResponse } from "next/server";
import { BackendRecommendationGoalSchema, ProductRecommendationResponseSchema } from "@/lib/api/contracts";
import { postJson } from "@/lib/api/client";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  let body: unknown;
  try { body = await request.json(); } catch {
    return NextResponse.json({ message: "요청 형식이 올바르지 않습니다." }, { status: 400 });
  }
  const parsed = BackendRecommendationGoalSchema.safeParse(
    typeof body === "object" && body !== null && "goal" in body ? body.goal : undefined,
  );
  if (!parsed.success) return NextResponse.json({ message: "금융 목표를 확인해 주세요." }, { status: 400 });
  try {
    const result = await postJson("/api/v1/recommendations?page_size=100", { goal: parsed.data }, ProductRecommendationResponseSchema);
    return NextResponse.json(result);
  } catch {
    return NextResponse.json({ message: "공식 상품 정보를 확인하지 못했습니다." }, { status: 502 });
  }
}
