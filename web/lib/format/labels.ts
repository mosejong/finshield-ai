import type { FinancialProfile, FraudType } from "@/lib/api/contracts";

/** enum 값 → 화면 문구. 매핑만 하고 판단하지 않는다. */

export const AGE_BAND_LABEL: Record<FinancialProfile["ageBand"], string> = {
  under_20: "20세 미만",
  "20_29": "20~29세",
  "30_39": "30~39세",
  "40_49": "40~49세",
  "50_59": "50~59세",
  "60_plus": "60세 이상",
};

export const EMPLOYMENT_LABEL: Record<
  FinancialProfile["employmentStatus"],
  string
> = {
  employed: "직장인",
  self_employed: "자영업·소상공인",
  unemployed: "구직 중·미취업",
  student: "학생",
  retired: "은퇴",
  other: "그 외",
};

export const CREDIT_BAND_LABEL: Record<
  FinancialProfile["creditScoreBand"],
  string
> = {
  unknown: "모름",
  excellent: "매우 양호",
  good: "양호",
  fair: "보통",
  poor: "낮음",
};

export const GOAL_LABEL: Record<FinancialProfile["goal"], string> = {
  housing: "집 구하기",
  emergency_cash: "비상금 마련",
  debt_refinance: "기존 대출 갈아타기",
  living_expense: "생활비 메우기",
  startup_business: "사업 자금",
  vehicle: "차량 구입",
  asset_building: "돈 모으기",
  other: "그 외",
};

export const PERSONA_LABEL: Record<FinancialProfile["persona"], string> = {
  early_career: "사회초년생",
  small_business: "소상공인",
  unknown: "선택 안 함",
};

export const FRAUD_TYPE_LABEL: Record<FraudType, string> = {
  authority_impersonation: "기관 사칭",
  acquaintance_impersonation: "지인·가족 사칭",
  loan_policy_impersonation: "대출·정책자금 사칭",
  investment_scheme: "투자·리딩방 유인",
  advance_fee_demand: "선입금·수수료 요구",
  account_access_request: "계좌·인증수단 접근 요구",
  money_mule_transfer: "자금 수취·재전달 요구",
  smishing_malware: "스미싱·악성 앱 유도",
  card_delivery_impersonation: "카드 배송 사칭",
  isolation_coercion: "고립·확인 차단 유도",
};

/**
 * 공식 상품 데이터를 제공한 기관. `app/clients/public_data_products.py` 의
 * `PROVIDER_NAME` 과 같은 문자열을 받는다.
 *
 * 화면에 이미 나오는 `offering_institution` 은 **취급기관**(은행)이고 이것은
 * **데이터 주체**다. 둘은 다른 기관이므로 함께 보여야 출처가 읽힌다.
 */
export const PRODUCT_PROVIDER_LABEL: Record<string, string> = {
  financial_services_commission: "금융위원회",
};

/**
 * 모르는 provider 는 원문 식별자를 그대로 돌려준다. 없는 기관명을 지어내는
 * 것이 표시하지 않는 것보다 나쁘다.
 */
export function productProviderLabel(provider: string): string {
  return PRODUCT_PROVIDER_LABEL[provider] ?? provider;
}

export function optionsOf<T extends string>(
  map: Record<T, string>,
): ReadonlyArray<{ value: T; label: string }> {
  return (Object.keys(map) as T[]).map((value) => ({
    value,
    label: map[value],
  }));
}
