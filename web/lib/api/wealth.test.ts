import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchWealthGuidance } from "@/lib/api/wealth";


const RESPONSE = {
  version: "0.1",
  scope_disclaimer: "일반 금융교육입니다.",
  modules: [
    ["money_flow", 1],
    ["saving_plan", 2],
    ["debt_credit", 3],
    ["investment_risk", 4],
  ].map(([code, order]) => ({
    code,
    order,
    title: `${order}단계`,
    summary: "공식 교육 요약",
    check_questions: ["확인했나요?"],
    next_action: "공식 교육을 확인하세요.",
    source_ids: [`source-${order}`],
  })),
  official_sources: [1, 2, 3, 4].map((order) => ({
    source_id: `source-${order}`,
    organization: "공식기관",
    title: "공식 교육",
    source_url: `https://example.go.kr/${order}`,
    retrieved_at: "2026-08-12",
    supports: [["money_flow", "saving_plan", "debt_credit", "investment_risk"][order - 1]],
  })),
};


afterEach(() => vi.unstubAllGlobals());


describe("fetchWealthGuidance", () => {
  it("개인 프로필 없이 고정 교육 계약만 GET으로 요청한다", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(RESPONSE), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await fetchWealthGuidance();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/proxy/guidance/wealth",
      expect.objectContaining({ method: "GET", cache: "no-store" }),
    );
    expect(fetchMock.mock.calls[0][1]).not.toHaveProperty("body");
    expect(result.modules).toHaveLength(4);
  });

  it("실패를 빈 교육목록으로 바꾸지 않는다", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("", { status: 502 })),
    );

    await expect(fetchWealthGuidance()).rejects.toThrow(
      "재테크 기초 가이드를 불러오지 못했습니다",
    );
  });
});
