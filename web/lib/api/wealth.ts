import {
  WealthGuidanceResponseSchema,
  type WealthGuidanceResponse,
} from "@/lib/api/contracts";


export async function fetchWealthGuidance(): Promise<WealthGuidanceResponse> {
  const response = await fetch("/api/proxy/guidance/wealth", {
    method: "GET",
    headers: { Accept: "application/json" },
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error("재테크 기초 가이드를 불러오지 못했습니다.");
  }

  return WealthGuidanceResponseSchema.parse(await response.json());
}
