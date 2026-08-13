import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api/auth", () => ({
  ensureAuthSession: vi.fn().mockResolvedValue({ authenticated: true }),
}));
import {
  BackendFinancialProfileResourceSchema,
  FinancialProfileSchema,
  type FinancialProfile,
} from "@/lib/api/contracts";
import {
  adaptProfileResource,
  createProfile,
  deleteProfile,
  replaceProfile,
  toBackendProfile,
} from "@/lib/api/profiles";

const PROFILE: FinancialProfile = {
  ageBand: "20_29",
  employmentStatus: "employed",
  householdSize: 2,
  dependentsCount: 1,
  monthlyNetIncome: 3_500_000,
  monthlyFixedExpenses: 1_200_000,
  monthlyVariableExpenses: 600_000,
  liquidAssets: 10_000_000,
  emergencyFundTargetMonths: 6,
  totalDebt: 5_000_000,
  monthlyDebtPayment: 250_000,
  creditScoreBand: "good",
  businessOwner: false,
  goal: "debt_refinance",
  persona: "early_career",
};

const BACKEND_RESOURCE = {
  profile_id: "742e91d5-2c31-45da-a13c-d76344a9815e",
  profile: {
    age_band: "20_29",
    employment_status: "employed",
    household_size: 2,
    dependents_count: 1,
    marital_status: null,
    region: null,
    monthly_net_income: "3500000.00",
    monthly_fixed_expenses: "1200000.00",
    monthly_variable_expenses: "600000.00",
    liquid_assets: "10000000.00",
    emergency_fund_target_months: 6,
    total_debt: "5000000.00",
    monthly_debt_payment: "250000.00",
    loan_items: [],
    credit_score_band: "good",
    business_owner: false,
    business_age_months: null,
    annual_business_revenue_band: null,
    goal: "debt_refinance",
  },
  created_at: "2026-08-12T09:00:00Z",
  updated_at: "2026-08-12T09:00:00Z",
};

afterEach(() => vi.unstubAllGlobals());

describe("financial profile adapter", () => {
  it("UI 전용 persona를 backend 요청에서 제외한다", () => {
    const backend = toBackendProfile(PROFILE);

    expect(backend).not.toHaveProperty("persona");
    expect(backend).toMatchObject({
      age_band: "20_29",
      emergency_fund_target_months: 6,
      loan_items: [],
      goal: "debt_refinance",
    });
  });

  it("민감하거나 승인되지 않은 frontend 필드를 거부한다", () => {
    expect(
      FinancialProfileSchema.safeParse({ ...PROFILE, otp: "123456" }).success,
    ).toBe(false);
  });

  it("Decimal 문자열을 숫자로 바꾸고 session persona만 다시 합친다", () => {
    const parsed = BackendFinancialProfileResourceSchema.parse(BACKEND_RESOURCE);
    const resource = adaptProfileResource(parsed, "small_business");

    expect(resource.profile.monthlyNetIncome).toBe(3_500_000);
    expect(resource.profile.persona).toBe("small_business");
    expect(resource.profileId).toBe(BACKEND_RESOURCE.profile_id);
  });
});

describe("financial profile browser API", () => {
  it("생성은 frontend profile을 같은 오리진 proxy로 전송한다", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(BACKEND_RESOURCE), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await createProfile(PROFILE);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/proxy/profiles",
      expect.objectContaining({ method: "POST" }),
    );
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.persona).toBe("early_career");
  });

  it("교체와 삭제는 동일 profile ID를 사용한다", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(BACKEND_RESOURCE), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await replaceProfile(BACKEND_RESOURCE.profile_id, PROFILE);
    await deleteProfile(BACKEND_RESOURCE.profile_id);

    expect(fetchMock.mock.calls[0][0]).toBe(
      `/api/proxy/profiles/${BACKEND_RESOURCE.profile_id}`,
    );
    expect(fetchMock.mock.calls[0][1].method).toBe("PUT");
    expect(fetchMock.mock.calls[1][1].method).toBe("DELETE");
  });

  it("삭제 실패를 성공으로 바꾸지 않는다", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 503 })));

    await expect(deleteProfile(BACKEND_RESOURCE.profile_id)).rejects.toThrow(
      "금융상태 삭제에 실패했습니다",
    );
  });
});
