import { NextResponse } from "next/server";
import {
  BackendFinancialProfileResourceSchema,
  FinancialProfileSchema,
} from "@/lib/api/contracts";
import { requestJson } from "@/lib/api/client";
import { toBackendProfile } from "@/lib/api/profiles";
import { backendHeaders, rejectCrossSiteRequest } from "@/lib/api/server-auth";
import { upstreamFailure } from "@/lib/api/proxy-response";
import { readJsonBody } from "@/lib/api/request-body";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const rejected = rejectCrossSiteRequest(request);
  if (rejected) return rejected;

  const body = await readJsonBody(request);
  if (!body.ok) return body.response;

  const parsed = FinancialProfileSchema.safeParse(body.value);
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
      backendHeaders(request, { session: true }),
    );
    return NextResponse.json(result, { status: 201 });
  } catch (error) {
    return upstreamFailure(error, "금융상태를 저장하지 못했습니다.");
  }
}
