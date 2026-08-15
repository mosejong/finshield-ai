import { NextResponse } from "next/server";
import {
  BackendLoanSimulationRequestSchema,
  LoanSimulationResponseSchema,
} from "@/lib/api/contracts";
import { postJson } from "@/lib/api/client";
import { backendHeaders } from "@/lib/api/server-auth";
import { upstreamFailure } from "@/lib/api/proxy-response";
import { readJsonBody } from "@/lib/api/request-body";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const body = await readJsonBody(request);
  if (!body.ok) return body.response;

  const parsed = BackendLoanSimulationRequestSchema.safeParse(body.value);
  if (!parsed.success) {
    return NextResponse.json(
      { message: "대출 조건을 다시 확인해 주세요." },
      { status: 400 },
    );
  }

  try {
    const result = await postJson(
      "/api/v1/loans/simulate",
      parsed.data,
      LoanSimulationResponseSchema,
      undefined,
      backendHeaders(request),
    );
    return NextResponse.json(result);
  } catch (error) {
    return upstreamFailure(error, "대출 상환 결과를 확인하지 못했습니다.");
  }
}
