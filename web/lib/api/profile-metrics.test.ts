import { afterEach, describe, expect, it, vi } from "vitest";
import { ProfileMetricsResponseSchema } from "@/lib/api/contracts";
import { fetchProfileMetrics } from "@/lib/api/profiles";


const PROFILE_ID = "742e91d5-2c31-45da-a13c-d76344a9815e";
const RESPONSE = {
  version: "0.1",
  profile_id: PROFILE_ID,
  profile_updated_at: "2026-08-12T09:00:00Z",
  summary: "월 지출과 상환 후 1,450,000원이 남습니다.",
  metrics: [
    {
      key: "disposable_cashflow",
      label: "매달 남는 돈",
      display: "1,450,000원",
      hint: "월 순소득에서 지출과 상환액을 뺀 금액입니다.",
      tone: "positive",
    },
    {
      key: "debt_payment_ratio",
      label: "월소득 대비 빚 상환액",
      display: "7.1%",
      hint: "월 순소득 중 상환액 비율입니다.",
      tone: "neutral",
      caveat: "공식 DSR이 아닙니다.",
    },
    {
      key: "emergency_fund_coverage",
      label: "비상금으로 버틸 수 있는 기간",
      display: "5.6개월",
      hint: "유동자산을 생활비로 나눈 기간입니다.",
      tone: "caution",
    },
  ],
  calculation: {
    monthly_disposable_cashflow: "1450000.00",
    monthly_debt_payment_ratio_percent: "7.1",
    emergency_fund_coverage_months: "5.6",
    essential_monthly_expenses: "1800000.00",
    emergency_fund_target_amount: "10800000.00",
    emergency_fund_gap: "800000.00",
  },
  assumptions: ["가정 1", "가정 2", "가정 3"],
  disclaimer: "공식 DSR이나 대출 심사 결과가 아닙니다.",
};


afterEach(() => vi.unstubAllGlobals());


describe("profile metrics API", () => {
  it("표시값과 계산 감사값을 엄격히 검증한다", () => {
    const parsed = ProfileMetricsResponseSchema.parse(RESPONSE);

    expect(parsed.metrics).toHaveLength(3);
    expect(parsed.calculation.monthly_disposable_cashflow).toBe("1450000.00");
  });

  it("profile ID만 같은 오리진 proxy 경로로 보낸다", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(RESPONSE), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await fetchProfileMetrics(PROFILE_ID);

    expect(fetchMock).toHaveBeenCalledWith(
      `/api/proxy/profiles/${PROFILE_ID}/metrics`,
      { cache: "no-store" },
    );
    expect(result.metrics[0].display).toBe("1,450,000원");
  });

  it("404와 잘못된 응답을 정상 지표로 바꾸지 않는다", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 404 })));
    await expect(fetchProfileMetrics(PROFILE_ID)).rejects.toThrow("금융지표");

    expect(
      ProfileMetricsResponseSchema.safeParse({ ...RESPONSE, otp: "123456" }).success,
    ).toBe(false);
  });
});
