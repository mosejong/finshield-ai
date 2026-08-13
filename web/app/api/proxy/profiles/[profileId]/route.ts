import { NextResponse } from "next/server";
import { z } from "zod";
import {
  BackendFinancialProfileResourceSchema,
  FinancialProfileSchema,
} from "@/lib/api/contracts";
import { ApiError, requestJson, requestNoContent } from "@/lib/api/client";
import { toBackendProfile } from "@/lib/api/profiles";
import { forwardedSessionCookie } from "@/lib/api/server-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Context = { params: Promise<{ profileId: string }> };

async function parseId(context: Context): Promise<string | null> {
  const { profileId } = await context.params;
  const parsed = z.string().uuid().safeParse(profileId);
  return parsed.success ? parsed.data : null;
}

function upstreamStatus(error: unknown): number {
  if (error instanceof ApiError && error.status === 401) return 401;
  if (error instanceof ApiError && error.status === 404) return 404;
  if (error instanceof ApiError && error.status === 503) return 503;
  return 502;
}

export async function GET(request: Request, context: Context) {
  const profileId = await parseId(context);
  if (!profileId) return NextResponse.json({ message: "프로필 식별자가 올바르지 않습니다." }, { status: 400 });

  try {
    const result = await requestJson(
      "GET",
      `/api/v1/profiles/${profileId}`,
      undefined,
      BackendFinancialProfileResourceSchema,
      8000,
      forwardedSessionCookie(request),
    );
    return NextResponse.json(result);
  } catch (error) {
    return NextResponse.json({ message: "금융상태를 불러오지 못했습니다." }, { status: upstreamStatus(error) });
  }
}

export async function PUT(request: Request, context: Context) {
  const profileId = await parseId(context);
  if (!profileId) return NextResponse.json({ message: "프로필 식별자가 올바르지 않습니다." }, { status: 400 });

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ message: "요청 형식이 올바르지 않습니다." }, { status: 400 });
  }
  const parsed = FinancialProfileSchema.safeParse(body);
  if (!parsed.success) return NextResponse.json({ message: "금융상태 입력값을 확인해 주세요." }, { status: 400 });

  try {
    const result = await requestJson(
      "PUT",
      `/api/v1/profiles/${profileId}`,
      toBackendProfile(parsed.data),
      BackendFinancialProfileResourceSchema,
      8000,
      forwardedSessionCookie(request),
    );
    return NextResponse.json(result);
  } catch (error) {
    return NextResponse.json({ message: "금융상태를 저장하지 못했습니다." }, { status: upstreamStatus(error) });
  }
}

export async function DELETE(request: Request, context: Context) {
  const profileId = await parseId(context);
  if (!profileId) return NextResponse.json({ message: "프로필 식별자가 올바르지 않습니다." }, { status: 400 });

  try {
    await requestNoContent(
      "DELETE",
      `/api/v1/profiles/${profileId}`,
      8000,
      forwardedSessionCookie(request),
    );
    return new NextResponse(null, { status: 204 });
  } catch (error) {
    return NextResponse.json({ message: "금융상태를 삭제하지 못했습니다." }, { status: upstreamStatus(error) });
  }
}
