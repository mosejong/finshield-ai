import { afterEach, describe, expect, it, vi } from "vitest";
import { compareProducts, fetchProductDetail } from "@/lib/api/products";


const PRODUCT = {
  provider: "financial_services_commission",
  source_product_id: "202607:1",
  name: "공식 상품",
  category: "대출상품",
  category_detail: "정책자금",
  loan_limit_text: "1000만원",
  interest_rate_type: "고정금리",
  interest_rate_text: "4.5%",
  max_total_term_text: "5년",
  max_grace_term_text: "1년",
  max_repayment_term_text: "4년",
  repayment_method_text: "원리금균등",
  purpose_text: "창업",
  offering_institution: "공식기관",
  handling_institution_text: "취급기관",
  application_method_text: "방문",
  active: true,
  eligibility: {
    target_text: "공식 대상",
    detailed_conditions_text: "공식 상세 조건",
    age_text: null,
    income_text: null,
    annual_income_text: null,
    credit_score_text: null,
    region_text: null,
  },
  source_base_month: "202607",
  source_file_written_at: "202607010900",
  fetched_at: "2026-08-12T00:00:00Z",
  source_reference: "https://www.data.go.kr/data/15121098/openapi.do",
};


afterEach(() => vi.unstubAllGlobals());


describe("product detail and comparison API", () => {
  it("상세 요청은 source ID만 URL에 포함한다", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(PRODUCT), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await fetchProductDetail("202607:1");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/proxy/products/202607%3A1",
      { method: "GET", cache: "no-store" },
    );
    expect(result.interest_rate_text).toBe("4.5%");
  });

  it("비교 요청은 서로 다른 source ID 2개만 전송한다", async () => {
    const response = {
      provider: "financial_services_commission",
      source_base_month: "202607",
      fetched_at: "2026-08-12T00:00:00Z",
      source_reference: PRODUCT.source_reference,
      items: [PRODUCT, { ...PRODUCT, source_product_id: "202607:2", name: "둘째" }],
      disclaimer: "적격성을 보장하지 않습니다.",
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(response), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await compareProducts(["202607:1", "202607:2"]);

    const options = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(options.body as string)).toEqual({
      product_ids: ["202607:1", "202607:2"],
    });
  });

  it("중복 ID와 실패 응답을 비교 결과로 바꾸지 않는다", async () => {
    await expect(compareProducts(["202607:1", "202607:1"])).rejects.toThrow(
      "서로 다른 상품 2개",
    );

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("", { status: 404 })),
    );
    await expect(fetchProductDetail("202607:99")).rejects.toThrow(
      "최신 공식 상품",
    );
  });
});
