import {
  BackendFinancialProfileResourceSchema,
  ProfileMetricsResponseSchema,
  type BackendFinancialProfile,
  type BackendFinancialProfileResource,
  type FinancialProfile,
  type FinancialProfileResource,
  type Persona,
  type ProfileMetricsResponse,
} from "@/lib/api/contracts";
import { ensureAuthSession } from "@/lib/api/auth";

export type ProfileRequestError = Error & { status?: number };

export function toBackendProfile(
  profile: FinancialProfile,
): BackendFinancialProfile {
  return {
    age_band: profile.ageBand,
    employment_status: profile.employmentStatus,
    household_size: profile.householdSize,
    dependents_count: profile.dependentsCount,
    marital_status: null,
    region: null,
    monthly_net_income: profile.monthlyNetIncome,
    monthly_fixed_expenses: profile.monthlyFixedExpenses,
    monthly_variable_expenses: profile.monthlyVariableExpenses,
    liquid_assets: profile.liquidAssets,
    emergency_fund_target_months: profile.emergencyFundTargetMonths,
    total_debt: profile.totalDebt,
    monthly_debt_payment: profile.monthlyDebtPayment,
    loan_items: [],
    credit_score_band: profile.creditScoreBand,
    business_owner: profile.businessOwner,
    business_age_months: null,
    annual_business_revenue_band: null,
    goal: profile.goal,
  };
}

export function adaptProfileResource(
  raw: BackendFinancialProfileResource,
  persona: Persona,
): FinancialProfileResource {
  const { profile } = raw;
  return {
    profileId: raw.profile_id,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
    profile: {
      ageBand: profile.age_band,
      employmentStatus: profile.employment_status,
      householdSize: profile.household_size,
      dependentsCount: profile.dependents_count,
      monthlyNetIncome: profile.monthly_net_income,
      monthlyFixedExpenses: profile.monthly_fixed_expenses,
      monthlyVariableExpenses: profile.monthly_variable_expenses,
      liquidAssets: profile.liquid_assets,
      emergencyFundTargetMonths: profile.emergency_fund_target_months,
      totalDebt: profile.total_debt,
      monthlyDebtPayment: profile.monthly_debt_payment,
      creditScoreBand: profile.credit_score_band,
      businessOwner: profile.business_owner,
      goal: profile.goal,
      persona,
    },
  };
}

async function parseResponse(response: Response): Promise<BackendFinancialProfileResource> {
  if (!response.ok) {
    const error = new Error("금융상태 요청에 실패했습니다.") as ProfileRequestError;
    error.status = response.status;
    throw error;
  }
  return BackendFinancialProfileResourceSchema.parse(await response.json());
}

export async function createProfile(
  profile: FinancialProfile,
): Promise<FinancialProfileResource> {
  await ensureAuthSession();
  const response = await fetch("/api/proxy/profiles", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile),
    cache: "no-store",
  });
  return adaptProfileResource(await parseResponse(response), profile.persona);
}

export async function fetchProfile(
  profileId: string,
  persona: Persona,
): Promise<FinancialProfileResource> {
  await ensureAuthSession();
  const response = await fetch(`/api/proxy/profiles/${profileId}`, {
    cache: "no-store",
  });
  return adaptProfileResource(await parseResponse(response), persona);
}

export async function replaceProfile(
  profileId: string,
  profile: FinancialProfile,
): Promise<FinancialProfileResource> {
  await ensureAuthSession();
  const response = await fetch(`/api/proxy/profiles/${profileId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile),
    cache: "no-store",
  });
  return adaptProfileResource(await parseResponse(response), profile.persona);
}

export async function deleteProfile(profileId: string): Promise<void> {
  await ensureAuthSession();
  const response = await fetch(`/api/proxy/profiles/${profileId}`, {
    method: "DELETE",
    cache: "no-store",
  });
  if (!response.ok && response.status !== 404) {
    const error = new Error("금융상태 삭제에 실패했습니다.") as ProfileRequestError;
    error.status = response.status;
    throw error;
  }
}

export async function fetchProfileMetrics(
  profileId: string,
): Promise<ProfileMetricsResponse> {
  await ensureAuthSession();
  const response = await fetch(`/api/proxy/profiles/${profileId}/metrics`, {
    cache: "no-store",
  });
  if (!response.ok) {
    const error = new Error("금융지표를 불러오지 못했습니다.") as ProfileRequestError;
    error.status = response.status;
    throw error;
  }
  return ProfileMetricsResponseSchema.parse(await response.json());
}
