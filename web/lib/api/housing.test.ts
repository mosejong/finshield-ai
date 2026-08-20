import { afterEach, describe, expect, it, vi } from "vitest";
import { checkDepositRisk } from "@/lib/api/housing";
import { DepositRiskResponseSchema } from "@/lib/api/contracts";
import type { DepositRiskRequest } from "@/lib/api/contracts";


const REQUEST: DepositRiskRequest = {
  stage: "balance_paid",
  deposit_krw: 200_000_000,
  property_price_krw: 300_000_000,
  senior_lien_krw: 60_000_000,
  completed_checks: ["registry_checked"],
  move_in_reported_on: null,
};

const RESPONSE = {
  risk_level: "high",
  stage: "balance_paid",
  summary: "잔금 지급·입주 단계입니다. 먼저 처리해야 할 부분이 있습니다.",
  ratio: {
    ratio_percent: 86.7,
    band: "high",
    band_is_service_rule: true,
    formula: "(선순위 채권최고액 + 보증금) ÷ 주택가격 × 100",
  },
  protection: {
    opposing_power_effective_on: null,
    has_opposing_power_requirements: false,
    has_priority_repayment_requirements: false,
  },
  signals: [
    {
      code: "opposing_power_missing",
      label: "대항력 요건이 아직 갖춰지지 않았습니다",
      detail: "잔금을 치렀는데 전입신고가 확인되지 않습니다.",
    },
  ],
  actions: [
    {
      code: "REPORT_MOVE_IN",
      priority: 1,
      title: "전입신고를 하세요",
      reason: "대항요건은 인도와 주민등록으로 갖춰집니다.",
      source_ids: ["housing_lease_act_article3"],
    },
  ],
  official_sources: [
    {
      source_id: "housing_lease_act_article3",
      organization: "국가법령정보센터",
      title: "주택임대차보호법 제3조",
      source_url: "https://www.law.go.kr/example",
      retrieved_at: "2026-08-19",
      supports: ["REPORT_MOVE_IN"],
    },
  ],
  disclaimer:
    "위험 구간은 이 서비스가 정한 보수적 기준이며 공식 기준이 아닙니다.",
};


afterEach(() => vi.unstubAllGlobals());


function stubFetch(body: unknown, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}


describe("checkDepositRisk", () => {
  it("프록시 경로로 POST 하고 결과를 그대로 돌려준다", async () => {
    const fetchMock = stubFetch(RESPONSE);

    const outcome = await checkDepositRisk(REQUEST);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/proxy/housing/deposit-risk",
      expect.objectContaining({ method: "POST" }),
    );
    expect(outcome.ok).toBe(true);
    if (!outcome.ok) return;
    expect(outcome.result.risk_level).toBe("high");
    expect(outcome.result.ratio.ratio_percent).toBe(86.7);
  });

  it("모르는 값을 0 으로 바꾸지 않고 null 그대로 보낸다", async () => {
    const fetchMock = stubFetch(RESPONSE);

    await checkDepositRisk({ ...REQUEST, senior_lien_krw: null });

    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.senior_lien_krw).toBeNull();
  });

  it("백엔드 오류를 '위험 없음' 으로 바꾸지 않는다", async () => {
    stubFetch({ message: "전세보증금 점검을 마치지 못했습니다." }, 502);

    const outcome = await checkDepositRisk(REQUEST);

    expect(outcome.ok).toBe(false);
    if (outcome.ok) return;
    expect(outcome.message).toBe("전세보증금 점검을 마치지 못했습니다.");
  });

  it("네트워크가 끊기면 결과를 지어내지 않는다", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

    const outcome = await checkDepositRisk(REQUEST);

    expect(outcome.ok).toBe(false);
  });
});


describe("DepositRiskResponseSchema", () => {
  it("band_is_service_rule 이 빠진 응답은 받지 않는다", () => {
    /*
      60%·80% 구간은 이 서비스가 정한 기준이다. 그 사실을 알리는 표시가 빠진
      응답을 그냥 그리면, 화면은 우리 기준을 공식 기준처럼 보여주게 된다.
      조용히 넘어가느니 스키마에서 멈추는 편이 낫다.
    */
    const ratio: Record<string, unknown> = { ...RESPONSE.ratio };
    delete ratio.band_is_service_rule;

    const parsed = DepositRiskResponseSchema.safeParse({
      ...RESPONSE,
      ratio,
    });

    expect(parsed.success).toBe(false);
  });

  it("계산하지 못한 비율은 null 로 받는다", () => {
    const parsed = DepositRiskResponseSchema.safeParse({
      ...RESPONSE,
      ratio: { ...RESPONSE.ratio, ratio_percent: null, band: "unknown" },
    });

    expect(parsed.success).toBe(true);
  });
});
