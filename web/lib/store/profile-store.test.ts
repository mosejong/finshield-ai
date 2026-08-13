import { afterEach, describe, expect, it, vi } from "vitest";
import type { FinancialProfile } from "@/lib/api/contracts";

vi.mock("@/lib/api/auth", () => ({
  ensureAuthSession: vi.fn().mockResolvedValue({ authenticated: true }),
  deleteAnonymousAccount: vi.fn().mockResolvedValue(undefined),
}));

const PROFILE: FinancialProfile = {
  ageBand: "20_29",
  employmentStatus: "employed",
  householdSize: 1,
  dependentsCount: 0,
  monthlyNetIncome: 2_800_000,
  monthlyFixedExpenses: 1_100_000,
  monthlyVariableExpenses: 600_000,
  liquidAssets: 4_000_000,
  emergencyFundTargetMonths: 3,
  totalDebt: 0,
  monthlyDebtPayment: 0,
  creditScoreBand: "unknown",
  businessOwner: false,
  goal: "emergency_cash",
  persona: "early_career",
};

const RESOURCE = {
  profile_id: "742e91d5-2c31-45da-a13c-d76344a9815e",
  profile: {
    age_band: "20_29",
    employment_status: "employed",
    household_size: 1,
    dependents_count: 0,
    marital_status: null,
    region: null,
    monthly_net_income: "2800000.00",
    monthly_fixed_expenses: "1100000.00",
    monthly_variable_expenses: "600000.00",
    liquid_assets: "4000000.00",
    emergency_fund_target_months: 3,
    total_debt: "0.00",
    monthly_debt_payment: "0.00",
    loan_items: [],
    credit_score_band: "unknown",
    business_owner: false,
    business_age_months: null,
    annual_business_revenue_band: null,
    goal: "emergency_cash",
  },
  created_at: "2026-08-12T09:00:00Z",
  updated_at: "2026-08-12T09:00:00Z",
};

class MemoryStorage {
  private values = new Map<string, string>();
  getItem(key: string) { return this.values.get(key) ?? null; }
  setItem(key: string, value: string) { this.values.set(key, value); }
  removeItem(key: string) { this.values.delete(key); }
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe("profile session identity", () => {
  it("생성 후 브라우저에는 UUID와 persona만 보관한다", async () => {
    const storage = new MemoryStorage();
    storage.setItem("finshield:profile", JSON.stringify(PROFILE));
    vi.stubGlobal("sessionStorage", storage);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(RESOURCE), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    const { saveProfile } = await import("@/lib/store/profile-store");

    await saveProfile(PROFILE);

    const raw = storage.getItem("finshield:profile-identity:v1");
    expect(JSON.parse(raw!)).toEqual({
      profileId: RESOURCE.profile_id,
      persona: "early_career",
    });
    expect(raw).not.toContain("monthlyNetIncome");
    expect(storage.getItem("finshield:profile")).toBeNull();
  });

  it("삭제 성공 후 profile identity를 제거한다", async () => {
    const storage = new MemoryStorage();
    storage.setItem(
      "finshield:profile-identity:v1",
      JSON.stringify({ profileId: RESOURCE.profile_id, persona: "early_career" }),
    );
    vi.stubGlobal("sessionStorage", storage);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    const { clearProfile } = await import("@/lib/store/profile-store");

    await clearProfile();

    expect(storage.getItem("finshield:profile-identity:v1")).toBeNull();
  });

  it("removes local identity after anonymous account deletion succeeds", async () => {
    const storage = new MemoryStorage();
    storage.setItem(
      "finshield:profile-identity:v1",
      JSON.stringify({ profileId: RESOURCE.profile_id, persona: "early_career" }),
    );
    storage.setItem("finshield:profile", JSON.stringify(PROFILE));
    vi.stubGlobal("sessionStorage", storage);
    const { clearAnonymousAccount } = await import("@/lib/store/profile-store");

    await clearAnonymousAccount();

    expect(storage.getItem("finshield:profile-identity:v1")).toBeNull();
    expect(storage.getItem("finshield:profile")).toBeNull();
  });
});
