import type {
  DerivedMetric,
  FinancialProfile,
  FinancialSnapshot,
} from "@/lib/api/contracts";

/**
 * 금융 프로필 mock.
 *
 * 파생지표는 여기서 계산하지 않는다. 백엔드 `/api/v1/profiles/{id}/metrics` 가
 * 내려줄 "계산이 끝난 값"을 흉내 낸 고정 fixture 다.
 * 프론트엔드에 금융 계산식을 두지 않기 위한 의도적인 제약이다.
 * (CLAUDE.md — "Deterministic code handles financial math")
 */

export const MOCK_PROFILE: FinancialProfile = {
  ageBand: "20_29",
  employmentStatus: "employed",
  householdSize: 1,
  dependentsCount: 0,

  monthlyNetIncome: 2_800_000,
  monthlyFixedExpenses: 1_150_000,
  monthlyVariableExpenses: 620_000,
  liquidAssets: 4_200_000,
  emergencyFundTargetMonths: 3,

  totalDebt: 18_000_000,
  monthlyDebtPayment: 310_000,

  creditScoreBand: "fair",
  businessOwner: false,
  goal: "debt_refinance",
  persona: "early_career",
};

/** MOCK_PROFILE 기준으로 백엔드가 내려줄 값을 미리 적어둔 것 */
const MOCK_METRICS: DerivedMetric[] = [
  {
    key: "disposable_cashflow",
    label: "매달 쓸 수 있는 돈",
    display: "72만 원",
    hint: "월 소득에서 고정지출·생활비·대출 상환을 빼고 남는 금액입니다.",
    tone: "positive",
  },
  {
    key: "debt_payment_ratio",
    label: "소득 대비 빚 부담",
    display: "11%",
    hint: "월 소득 중 대출 상환에 나가는 비율입니다.",
    tone: "neutral",
    caveat: "은행이 대출 심사에 쓰는 공식 DSR 과는 계산 방식이 다릅니다.",
  },
  {
    key: "emergency_fund_coverage",
    label: "비상금으로 버틸 수 있는 기간",
    display: "2.4개월",
    hint: "소득이 끊겨도 지금 모아둔 돈으로 생활할 수 있는 기간입니다.",
    tone: "caution",
  },
];

export const MOCK_SNAPSHOT: FinancialSnapshot = {
  hasProfile: true,
  profile: MOCK_PROFILE,
  summary:
    "매달 72만 원이 남고, 비상금은 2.4개월치입니다. 빚 부담은 아직 낮은 편입니다.",
  metrics: MOCK_METRICS,
  source: "mock",
};

export const EMPTY_SNAPSHOT: FinancialSnapshot = {
  hasProfile: false,
  profile: null,
  summary:
    "아직 금융상태를 알려주지 않으셨습니다. 5단계만 답하면 요약을 볼 수 있습니다.",
  metrics: [],
  source: "mock",
};
