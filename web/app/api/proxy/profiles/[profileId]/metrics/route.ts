import { NextResponse } from "next/server";
import { z } from "zod";
import { requestJson } from "@/lib/api/client";
import { ProfileMetricsResponseSchema } from "@/lib/api/contracts";
import { backendHeaders } from "@/lib/api/server-auth";
import { upstreamFailure } from "@/lib/api/proxy-response";


export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Context = { params: Promise<{ profileId: string }> };


export async function GET(request: Request, context: Context) {
  const { profileId: rawProfileId } = await context.params;
  const parsed = z.string().uuid().safeParse(rawProfileId);
  if (!parsed.success) {
    return NextResponse.json(
      { message: "프로필 식별자가 올바르지 않습니다." },
      { status: 400 },
    );
  }

  try {
    const result = await requestJson(
      "GET",
      `/api/v1/profiles/${parsed.data}/metrics`,
      undefined,
      ProfileMetricsResponseSchema,
      8000,
      backendHeaders(request, { session: true }),
    );
    return NextResponse.json(result);
  } catch (error) {
    return upstreamFailure(error, "금융지표를 불러오지 못했습니다.");
  }
}
