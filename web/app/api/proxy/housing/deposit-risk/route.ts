import { NextResponse } from "next/server";
import {
  DepositRiskRequestSchema,
  DepositRiskResponseSchema,
} from "@/lib/api/contracts";
import { ApiError, postJson } from "@/lib/api/client";
import { backendHeaders } from "@/lib/api/server-auth";
import { upstreamFailure } from "@/lib/api/proxy-response";
import { readJsonBody } from "@/lib/api/request-body";

/**
 * `POST /api/v1/housing/deposit-risk` 로 가는 서버 사이드 프록시.
 *
 * 세션을 넘기지 않는다. 계약을 앞둔 사람에게 회원가입을 먼저 요구하지 않는
 * 것이 이 기능의 전제이고, 백엔드 라우트도 세션을 요구하지 않는다.
 * CSRF 검사도 붙이지 않는다 — 이 요청은 아무 상태도 바꾸지 않고, 사용자 계정에
 * 딸린 자원을 읽지도 않는다. `analyze` 와 같은 성격이다.
 *
 * 보증금·주택가격은 여기서 로그로 남기지 않는다. (ADR 0006)
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const body = await readJsonBody(request);
  if (!body.ok) return body.response;

  const parsed = DepositRiskRequestSchema.safeParse(body.value);
  if (!parsed.success) return invalidInput();

  try {
    const result = await postJson(
      "/api/v1/housing/deposit-risk",
      parsed.data,
      DepositRiskResponseSchema,
      undefined,
      backendHeaders(request),
    );
    return NextResponse.json(result);
  } catch (error) {
    /*
      백엔드의 422 는 입력이 거부됐다는 뜻이지 서버가 고장났다는 뜻이 아니다.
      이것을 502 로 덮으면 사용자는 고칠 수 있는 값을 앞에 두고 "잠시 후 다시"
      만 반복하게 된다.

      전입신고일이 대표적이다. 날짜 형식은 맞아서 여기 스키마는 통과하지만,
      "오늘" 의 기준은 서버(KST)에 있어서 최종 판단은 백엔드가 한다. 규칙을
      여기에 한 벌 더 두지 않고, 거부됐다는 사실만 정확히 옮긴다.
    */
    if (error instanceof ApiError && error.status === 422) return invalidInput();

    // 점검하지 못한 것을 "문제 없음" 으로 바꾸지 않는다.
    return upstreamFailure(error, "전세보증금 점검을 마치지 못했습니다.");
  }
}

function invalidInput(): NextResponse {
  return NextResponse.json(
    {
      message: "입력한 값을 확인해 주세요.",
      hint: "금액은 0 이상의 숫자여야 하고, 전입신고일은 오늘보다 뒤일 수 없습니다.",
    },
    { status: 400 },
  );
}
