import { NextResponse } from "next/server";
import {
  BackendFinancialProfileResourceSchema,
  FinancialProfileSchema,
} from "@/lib/api/contracts";
import { ApiError, requestJson } from "@/lib/api/client";
import { toBackendProfile } from "@/lib/api/profiles";
import { forwardedSessionCookie } from "@/lib/api/server-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ message: "요청 형식이 올바르지 않습니다." }, { status: 400 });
  }

  const parsed = FinancialProfileSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ message: "금융상태 입력값을 확인해 주세요." }, { status: 400 });
  }

  try {
    const result = await requestJson(
      "POST",
      "/api/v1/profiles",
      toBackendProfile(parsed.data),
      BackendFinancialProfileResourceSchema,
      8000,
      forwardedSessionCookie(request),
    );
    return NextResponse.json(result, { status: 201 });
  } catch (error) {
    const status = error instanceof ApiError && [401, 503].includes(error.status)
      ? error.status
      : 502;
    return NextResponse.json({ message: "금융상태를 저장하지 못했습니다." }, { status });
  }
}
