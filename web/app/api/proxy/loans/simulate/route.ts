import { NextResponse } from "next/server";
import {
  BackendLoanSimulationRequestSchema,
  LoanSimulationResponseSchema,
} from "@/lib/api/contracts";
import { postJson } from "@/lib/api/client";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { message: "요청 형식이 올바르지 않습니다." },
      { status: 400 },
    );
  }

  const parsed = BackendLoanSimulationRequestSchema.safeParse(body);
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
    );
    return NextResponse.json(result);
  } catch {
    return NextResponse.json(
      { message: "대출 상환 결과를 확인하지 못했습니다." },
      { status: 502 },
    );
  }
}
