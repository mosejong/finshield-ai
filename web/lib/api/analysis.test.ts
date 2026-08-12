import { describe, expect, it } from "vitest";

import { adaptBackendAnalysis } from "@/lib/api/analysis";
import type { AnalyzeRequest } from "@/lib/api/contracts";

const request: AnalyzeRequest = {
  text: "계좌 접근수단을 넘겼습니다.",
  persona: "unknown",
  state: "shared_account_access",
};

const backendResponse = {
  risk_score: 0,
  risk_level: "high",
  signals: [
    {
      code: "account_access",
      label: "계좌·접근수단 요구",
      weight: 35,
    },
  ],
  scenario: "shared_account_access",
  disclaimer: "결정론적 위험 신호 분석이며 공식 판단을 대신하지 않습니다.",
  fraud_types: ["account_access_request"],
  summary: "이미 취한 행동에 맞춰 긴급 대응을 우선 확인하세요.",
  actions: [
    {
      code: "DO_NOT_SHARE_ACCESS",
      priority: 1,
      title: "인증정보와 금융 접근수단을 공유하지 마세요",
      reason: "추가 접근을 막아야 합니다.",
      source_ids: ["electronic_financial_transactions_act"],
    },
    {
      code: "CONTACT_112",
      priority: 1,
      title: "긴급한 피해 상황은 112에 신고하세요",
      reason: "신속한 신고가 필요합니다.",
      source_ids: ["police_ecrm_victim_help"],
    },
    {
      code: "VERIFY_OFFICIAL_CHANNEL",
      priority: 2,
      title: "공식 대표번호로 사실을 확인하세요",
      reason: "메시지 속 연락처를 사용하지 마세요.",
      source_ids: ["police_ecrm_victim_help"],
    },
  ],
  official_sources: [
    {
      source_id: "electronic_financial_transactions_act",
      organization: "국가법령정보센터",
      title: "전자금융거래법 제6조",
      source_url: "https://law.go.kr/example",
      retrieved_at: "2026-08-12",
      supports: ["DO_NOT_SHARE_ACCESS"],
    },
    {
      source_id: "police_ecrm_victim_help",
      organization: "경찰청 사이버범죄 신고시스템",
      title: "피해자 구제·신고 안내",
      source_url: "https://ecrm.police.go.kr/example",
      retrieved_at: "2026-08-12",
      supports: ["CONTACT_112", "VERIFY_OFFICIAL_CHANNEL"],
    },
  ],
};

describe("adaptBackendAnalysis", () => {
  it("Scenario Engine의 요약·행동·공식 근거를 mock 없이 보존한다", () => {
    const result = adaptBackendAnalysis(backendResponse, request);

    expect(result.level).toBe("high");
    expect(result.score).toBe(0);
    expect(result.fraudTypes).toEqual(["account_access_request"]);
    expect(result.why).toEqual([backendResponse.summary]);
    expect(result.whySource).toBe("live");
    expect(result.actionsSource).toBe("live");
    expect(result.evidenceSource).toBe("live");
    expect(result.signals[0]).not.toHaveProperty("why");

    expect(result.actions).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: "DO_NOT_SHARE_ACCESS",
          kind: "avoid",
          evidenceIds: ["electronic_financial_transactions_act"],
        }),
        expect.objectContaining({
          id: "CONTACT_112",
          kind: "immediate",
          contactPhone: "112",
        }),
        expect.objectContaining({
          id: "VERIFY_OFFICIAL_CHANNEL",
          kind: "soon",
        }),
      ]),
    );

    expect(result.evidence).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: "police_ecrm_victim_help",
          publisher: "경찰청 사이버범죄 신고시스템",
          verified: true,
          fetchedAt: "2026-08-12",
        }),
      ]),
    );
  });

  it("알 수 없는 위험도는 낙관하지 않고 high로 표시한다", () => {
    const result = adaptBackendAnalysis(
      { ...backendResponse, risk_level: "unexpected" },
      request,
    );

    expect(result.level).toBe("high");
  });

  it("신규 필드가 없는 이전 백엔드 응답은 안전하게 거절한다", () => {
    expect(() =>
      adaptBackendAnalysis(
        {
          risk_score: 0,
          risk_level: "low",
          signals: [],
          scenario: "received_only",
          disclaimer: "old contract",
        },
        request,
      ),
    ).toThrow();
  });
});
