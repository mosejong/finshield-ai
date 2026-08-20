import {
  DepositRiskResponseSchema,
  type DepositRiskRequest,
  type DepositRiskResponse,
} from "@/lib/api/contracts";

/**
 * 전세보증금 위험 점검 호출.
 *
 * 실패를 결과로 바꾸지 않는다. 백엔드가 답하지 못했으면 화면은 "점검하지
 * 못했다" 라고 말해야 하고, 조용히 낮은 위험으로 대체하면 안 된다.
 */

export type DepositRiskFailure = { message: string; hint?: string };

export type DepositRiskOutcome =
  | { ok: true; result: DepositRiskResponse }
  | ({ ok: false } & DepositRiskFailure);

export async function checkDepositRisk(
  request: DepositRiskRequest,
): Promise<DepositRiskOutcome> {
  let response: Response;
  try {
    response = await fetch("/api/proxy/housing/deposit-risk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
  } catch {
    return {
      ok: false,
      message: "점검을 요청하지 못했습니다.",
      hint: "네트워크 연결을 확인한 뒤 다시 시도해 주세요.",
    };
  }

  const payload: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    const failure =
      payload && typeof payload === "object" && "message" in payload
        ? (payload as DepositRiskFailure)
        : null;
    return {
      ok: false,
      message: failure?.message ?? "전세보증금 점검에 실패했습니다.",
      hint: failure?.hint,
    };
  }

  const parsed = DepositRiskResponseSchema.safeParse(payload);
  if (!parsed.success) {
    return {
      ok: false,
      message: "점검 결과를 이해하지 못했습니다.",
      hint: "잠시 후 다시 시도해 주세요.",
    };
  }

  return { ok: true, result: parsed.data };
}
