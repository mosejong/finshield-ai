import { NextResponse } from "next/server";
import { z } from "zod";
import { ApiError, requestJson } from "@/lib/api/client";
import { ProfileMetricsResponseSchema } from "@/lib/api/contracts";
import { forwardedSessionCookie } from "@/lib/api/server-auth";


export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Context = { params: Promise<{ profileId: string }> };


function upstreamStatus(error: unknown): number {
  if (error instanceof ApiError && error.status === 401) return 401;
  if (error instanceof ApiError && error.status === 404) return 404;
  if (error instanceof ApiError && error.status === 503) return 503;
  return 502;
}


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
      forwardedSessionCookie(request),
    );
    return NextResponse.json(result);
  } catch (error) {
    return NextResponse.json(
      { message: "금융지표를 불러오지 못했습니다." },
      { status: upstreamStatus(error) },
    );
  }
}
