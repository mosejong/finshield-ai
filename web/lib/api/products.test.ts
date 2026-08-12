import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchProductRecommendations } from "@/lib/api/products";

const RESPONSE = {
  provider: "financial_services_commission",
  source_base_month: "202607",
  total_count: 0,
  page_no: 1,
  page_size: 100,
  summary: { potential_match: 0, mismatch: 0, needs_review: 0 },
  disclaimer: "후보 분류입니다.",
  results: [],
};

afterEach(() => vi.unstubAllGlobals());

describe("fetchProductRecommendations", () => {
  it("소득·부채 없이 goal 하나만 전송한다", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(RESPONSE), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await fetchProductRecommendations("startup_business");

    const options = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(options.body as string)).toEqual({
      goal: "startup_business",
    });
  });

  it("실패를 빈 상품목록으로 바꾸지 않는다", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 502 })));
    await expect(fetchProductRecommendations("housing")).rejects.toThrow(
      "상품 정보를 불러오지 못했습니다",
    );
  });
});
