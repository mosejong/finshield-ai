import { z } from "zod";

/**
 * 프론트엔드가 기대하는 데이터 계약.
 *
 * 금융 파생지표처럼 백엔드가 아직 제공하지 않는 영역은 mock 어댑터가 채우고
 * `source: "mock"` 으로 표시한다. 프로필 CRUD, 상품 후보, 사기 분석은 실제
 * backend 응답을 검증해 사용한다.
 *
 * backend enum과 snake_case 계약을 화면용 camelCase 계약과 분리한다.
 */

/** 값의 출처. 화면은 이 값을 보고 mock 배지를 붙일지 결정한다. */
export const SourceKindSchema = z.enum(["live", "mock"]);
export type SourceKind = z.infer<typeof SourceKindSchema>;

export const AuthSessionResponseSchema = z.object({
  authenticated: z.literal(true),
  user_id: z.string().uuid(),
  kind: z.literal("anonymous"),
  expires_at: z.string().datetime({ offset: true }),
}).strict();
export type AuthSessionResponse = z.infer<typeof AuthSessionResponseSchema>;

/* ------------------------------------------------------------------ */
/* 공통                                                                */
/* ------------------------------------------------------------------ */

export const PersonaSchema = z.enum([
  "early_career",
  "small_business",
  "unknown",
]);
export type Persona = z.infer<typeof PersonaSchema>;

/** docs/03-product-scope.md 의 scenario states 와 1:1 대응 */
export const UserStateSchema = z.enum([
  "received_only",
  "clicked_link",
  "shared_personal_info",
  "shared_account_access",
  "installed_app",
  "received_unknown_money",
  "transferred_money",
]);
export type UserState = z.infer<typeof UserStateSchema>;

export const RiskLevelSchema = z.enum(["low", "medium", "high"]);
export type RiskLevel = z.infer<typeof RiskLevelSchema>;

/**
 * 근거/출처.
 *
 * `verified: false` 는 아직 공식 확인을 거치지 않은 항목이라는 뜻이며
 * 화면에 "검증 전"으로 표시된다. 가짜 출처를 만들어내지 않기 위한 장치다.
 */
export const EvidenceSchema = z.object({
  id: z.string(),
  title: z.string(),
  publisher: z.string(),
  url: z.string().url().optional(),
  phone: z.string().optional(),
  note: z.string().optional(),
  verified: z.boolean(),
  fetchedAt: z.string().optional(),
});
export type Evidence = z.infer<typeof EvidenceSchema>;

/* ------------------------------------------------------------------ */
/* 백엔드 실제 응답 — app/schemas/analysis.py 와 일치                   */
/* ------------------------------------------------------------------ */

export const BackendRiskSignalSchema = z.object({
  code: z.string(),
  label: z.string(),
  weight: z.number().int(),
});

export const FraudTypeSchema = z.enum([
  "authority_impersonation",
  "loan_policy_impersonation",
  "account_access_request",
  "money_mule_transfer",
  "smishing_malware",
  "card_delivery_impersonation",
]);
export type FraudType = z.infer<typeof FraudTypeSchema>;

export const BackendActionSchema = z.object({
  code: z.enum([
    "STOP_CONTACT",
    "DO_NOT_CLICK",
    "DO_NOT_INSTALL",
    "DO_NOT_SHARE_ACCESS",
    "DO_NOT_FORWARD_MONEY",
    "VERIFY_OFFICIAL_CHANNEL",
    "CONTACT_FINANCIAL_INSTITUTION",
    "CONTACT_1394",
    "CONTACT_112",
    "CONTACT_KISA_118",
    "PRESERVE_EVIDENCE",
  ]),
  priority: z.number().int().min(1).max(3),
  title: z.string(),
  reason: z.string(),
  source_ids: z.array(z.string()),
});
export type BackendAction = z.infer<typeof BackendActionSchema>;

export const BackendOfficialSourceSchema = z.object({
  source_id: z.string(),
  organization: z.string(),
  title: z.string(),
  source_url: z.string().url(),
  retrieved_at: z.string(),
  supports: z.array(z.string()),
});

export const BackendAnalyzeResponseSchema = z.object({
  risk_score: z.number().int().min(0).max(100),
  risk_level: z.string(),
  signals: z.array(BackendRiskSignalSchema),
  scenario: UserStateSchema,
  disclaimer: z.string(),
  fraud_types: z.array(FraudTypeSchema),
  summary: z.string(),
  actions: z.array(BackendActionSchema),
  official_sources: z.array(BackendOfficialSourceSchema),
});
export type BackendAnalyzeResponse = z.infer<
  typeof BackendAnalyzeResponseSchema
>;

/* ------------------------------------------------------------------ */
/* 사기 분석 — 프론트 계약                                              */
/* ------------------------------------------------------------------ */

/**
 * 분석에 보낼 수 있는 원문 길이 상한.
 *
 * 입력 화면의 글자 수 표시, 공유 시트로 들어온 내용의 절단, 요청 스키마가
 * 모두 이 값을 봐야 한다. 세 곳에 따로 적으면 공유로 들어온 긴 메시지가
 * 입력창에는 들어가고 전송에서만 거부되는 식으로 어긋난다.
 */
export const ANALYZE_TEXT_MAX_LENGTH = 10_000;

export const AnalyzeRequestSchema = z.object({
  text: z.string().min(1).max(ANALYZE_TEXT_MAX_LENGTH),
  persona: PersonaSchema.default("unknown"),
  state: UserStateSchema.default("received_only"),
  url: z.string().optional(),
});
export type AnalyzeRequest = z.infer<typeof AnalyzeRequestSchema>;

export const RiskSignalSchema = z.object({
  code: z.string(),
  /** 감지된 것 — "계좌·접근수단 요구" */
  label: z.string(),
  /** 왜 위험한지 한 줄 — 없으면 화면에서 생략 */
  why: z.string().optional(),
  weight: z.number().int(),
  source: SourceKindSchema,
});
export type RiskSignal = z.infer<typeof RiskSignalSchema>;

export const ActionSchema = z.object({
  id: z.string(),
  /** 명령형 한 문장 — "상대에게 계좌·카드를 절대 보내지 마세요" */
  title: z.string(),
  detail: z.string().optional(),
  /** immediate = 지금 당장, soon = 오늘 안에, avoid = 하지 말 것 */
  kind: z.enum(["immediate", "soon", "avoid"]),
  /** 공식 창구 전화번호. tel: 링크로 연결된다. */
  contactPhone: z.string().optional(),
  contactLabel: z.string().optional(),
  evidenceIds: z.array(z.string()).default([]),
});
export type Action = z.infer<typeof ActionSchema>;

export const AnalysisResultSchema = z.object({
  id: z.string(),
  createdAt: z.string(),

  /** 위험 수준 — 백엔드 판정을 그대로 쓴다 */
  level: RiskLevelSchema,
  /** 헤드라인 한 문장. 점수보다 먼저 읽힌다. */
  headline: z.string(),
  headlineSource: SourceKindSchema,

  signals: z.array(RiskSignalSchema),
  fraudTypes: z.array(FraudTypeSchema),

  /** 왜 위험한지 — 문단 단위 */
  why: z.array(z.string()),
  whySource: SourceKindSchema,

  /** 사용자가 이미 한 것 */
  state: UserStateSchema,
  stateSummary: z.string(),
  stateSource: SourceKindSchema,

  actions: z.array(ActionSchema),
  actionsSource: SourceKindSchema,

  evidence: z.array(EvidenceSchema),
  evidenceSource: SourceKindSchema,

  /** 접어둔 분석 상세용. 화면 첫 진입에서 노출하지 않는다. */
  score: z.number().int().min(0).max(100),
  scoreSource: SourceKindSchema,
  engine: z.string(),

  disclaimer: z.string(),
});
export type AnalysisResult = z.infer<typeof AnalysisResultSchema>;

/** Home "위험한 금융 연락 확인" 블록에 쓰는 최근 분석 요약 */
export const AnalysisSummarySchema = z.object({
  id: z.string(),
  createdAt: z.string(),
  level: RiskLevelSchema,
  headline: z.string(),
  excerpt: z.string(),
  openActionCount: z.number().int().min(0),
});
export type AnalysisSummary = z.infer<typeof AnalysisSummarySchema>;

/* ------------------------------------------------------------------ */
/* 금융 프로필                                                          */
/* ------------------------------------------------------------------ */

export const AgeBandSchema = z.enum([
  "under_20",
  "20_29",
  "30_39",
  "40_49",
  "50_59",
  "60_plus",
]);
export const EmploymentStatusSchema = z.enum([
  "employed",
  "self_employed",
  "unemployed",
  "student",
  "retired",
  "other",
]);
export const CreditScoreBandSchema = z.enum([
  "excellent",
  "good",
  "fair",
  "poor",
  "unknown",
]);
export const MaritalStatusSchema = z.enum([
  "single",
  "married",
  "other",
  "prefer_not_to_say",
]);
export const BusinessRevenueBandSchema = z.enum([
  "under_30m",
  "30m_100m",
  "100m_500m",
  "over_500m",
  "unknown",
]);
export const DebtCategorySchema = z.enum([
  "mortgage",
  "rent_deposit",
  "credit_loan",
  "secured_loan",
  "student_loan",
  "auto_loan",
  "business_loan",
  "card_loan",
  "other",
]);
export const ProfileRepaymentTypeSchema = z.enum([
  "equal_principal_and_interest",
  "equal_principal",
  "interest_only",
  "bullet",
  "other",
]);
export const FinancialGoalSchema = z.enum([
  "housing",
  "emergency_cash",
  "debt_refinance",
  "living_expense",
  "startup_business",
  "vehicle",
  "asset_building",
  "other",
]);

/**
 * docs/09-financial-profile-schema.md 의 MVP profile.
 * 주민번호·계좌번호·실명은 받지 않는다. 정확한 나이·신용점수 대신 band 를 쓴다.
 */
export const FinancialProfileSchema = z.object({
  ageBand: AgeBandSchema,
  employmentStatus: EmploymentStatusSchema,
  householdSize: z.number().int().min(1).max(10),
  dependentsCount: z.number().int().min(0).max(10),

  /**
   * 화면은 아직 입력받지 않지만 서버가 보관하는 값이다.
   * 왕복에서 빠뜨리면 프로필 수정 시 서버 값이 null 로 덮여 사라진다.
   */
  maritalStatus: MaritalStatusSchema.nullable().default(null),
  region: z.string().min(1).max(50).nullable().default(null),

  monthlyNetIncome: z.number().int().min(0),
  monthlyFixedExpenses: z.number().int().min(0),
  monthlyVariableExpenses: z.number().int().min(0),
  liquidAssets: z.number().int().min(0),
  emergencyFundTargetMonths: z.number().int().min(0).max(60),

  totalDebt: z.number().int().min(0),
  monthlyDebtPayment: z.number().int().min(0),

  creditScoreBand: CreditScoreBandSchema,
  businessOwner: z.boolean(),
  goal: FinancialGoalSchema,
  persona: PersonaSchema,
}).strict().superRefine((profile, context) => {
  if (profile.dependentsCount >= profile.householdSize) {
    context.addIssue({
      code: "custom",
      path: ["dependentsCount"],
      message: "부양가족 수는 가구원 수보다 작아야 합니다.",
    });
  }
  if (profile.totalDebt === 0 && profile.monthlyDebtPayment !== 0) {
    context.addIssue({
      code: "custom",
      path: ["monthlyDebtPayment"],
      message: "남은 대출이 없으면 매달 갚는 돈은 0원이어야 합니다.",
    });
  }
});
export type FinancialProfile = z.infer<typeof FinancialProfileSchema>;

const BackendMoneySchema = z
  .union([z.number().nonnegative(), z.string().regex(/^\d+(?:\.\d+)?$/)])
  .transform(Number);

/** app/schemas/financial_profile.py 의 LoanItem 과 1:1. */
export const BackendLoanItemSchema = z.object({
  category: DebtCategorySchema,
  balance: BackendMoneySchema,
  annual_rate: BackendMoneySchema,
  remaining_months: z.number().int().min(1).max(600),
  repayment_type: ProfileRepaymentTypeSchema,
}).strict();
export type BackendLoanItem = z.infer<typeof BackendLoanItemSchema>;

/** app/schemas/financial_profile.py 와 1:1로 검증하는 서버 계약. */
export const BackendFinancialProfileSchema = z.object({
  age_band: AgeBandSchema,
  employment_status: EmploymentStatusSchema,
  household_size: z.number().int().min(1).max(20),
  dependents_count: z.number().int().min(0).max(19),
  marital_status: MaritalStatusSchema.nullable(),
  region: z.string().nullable(),
  monthly_net_income: BackendMoneySchema,
  monthly_fixed_expenses: BackendMoneySchema,
  monthly_variable_expenses: BackendMoneySchema,
  liquid_assets: BackendMoneySchema,
  emergency_fund_target_months: z.number().int().min(0).max(60),
  total_debt: BackendMoneySchema,
  monthly_debt_payment: BackendMoneySchema,
  loan_items: z.array(BackendLoanItemSchema),
  credit_score_band: CreditScoreBandSchema,
  business_owner: z.boolean(),
  business_age_months: z.number().int().nullable(),
  annual_business_revenue_band: BusinessRevenueBandSchema.nullable(),
  goal: FinancialGoalSchema,
}).strict();
export type BackendFinancialProfile = z.infer<
  typeof BackendFinancialProfileSchema
>;

export const BackendFinancialProfileResourceSchema = z.object({
  profile_id: z.string().uuid(),
  profile: BackendFinancialProfileSchema,
  created_at: z.string().datetime({ offset: true }),
  updated_at: z.string().datetime({ offset: true }),
}).strict();
export type BackendFinancialProfileResource = z.infer<
  typeof BackendFinancialProfileResourceSchema
>;

export type FinancialProfileResource = {
  profileId: string;
  profile: FinancialProfile;
  createdAt: string;
  updatedAt: string;
};

/* ------------------------------------------------------------------ */
/* 공식 금융상품 후보                                                  */
/* ------------------------------------------------------------------ */

export const BackendRecommendationGoalSchema = z.enum([
  "housing", "emergency_cash", "debt_refinance", "living_expense",
  "startup_business", "vehicle", "asset_building", "other",
]);
export type BackendRecommendationGoal = z.infer<typeof BackendRecommendationGoalSchema>;

export const ProductMatchStatusSchema = z.enum([
  "potential_match", "mismatch", "needs_review",
]);
export type ProductMatchStatus = z.infer<typeof ProductMatchStatusSchema>;

export const ProductSourceIdSchema = z.string().regex(/^\d{6}:\d+$/).max(100);

export const BackendProductSchema = z.object({
  provider: z.string(),
  source_product_id: ProductSourceIdSchema,
  name: z.string(),
  category: z.string().nullable(),
  category_detail: z.string().nullable(),
  loan_limit_text: z.string().nullable(),
  interest_rate_type: z.string().nullable(),
  interest_rate_text: z.string().nullable(),
  max_total_term_text: z.string().nullable(),
  max_grace_term_text: z.string().nullable(),
  max_repayment_term_text: z.string().nullable(),
  repayment_method_text: z.string().nullable(),
  purpose_text: z.string().nullable(),
  offering_institution: z.string().nullable(),
  handling_institution_text: z.string().nullable(),
  application_method_text: z.string().nullable(),
  active: z.boolean().nullable(),
  source_reference: z.string().url(),
  eligibility: z.object({
    target_text: z.string().nullable(),
    detailed_conditions_text: z.string().nullable(),
    age_text: z.string().nullable(),
    income_text: z.string().nullable(),
    annual_income_text: z.string().nullable(),
    credit_score_text: z.string().nullable(),
    region_text: z.string().nullable(),
  }).strict(),
  source_base_month: z.string().regex(/^\d{6}$/).nullable(),
  source_file_written_at: z.string().regex(/^\d{12}$/).nullable(),
  fetched_at: z.string().datetime({ offset: true }),
}).strict();
export type BackendProduct = z.infer<typeof BackendProductSchema>;

const ProductMatchReasonSchema = z.object({
  rule: z.enum(["goal_purpose", "eligibility_manual_review"]),
  status: ProductMatchStatusSchema,
  message: z.string(),
  source_field: z.enum(["purpose_text", "eligibility"]),
});

export const ProductRecommendationResponseSchema = z.object({
  provider: z.string(),
  source_base_month: z.string().regex(/^\d{6}$/),
  total_count: z.number().int().nonnegative(),
  page_no: z.number().int().positive(),
  page_size: z.number().int().positive(),
  summary: z.object({
    potential_match: z.number().int().nonnegative(),
    mismatch: z.number().int().nonnegative(),
    needs_review: z.number().int().nonnegative(),
  }),
  disclaimer: z.string(),
  results: z.array(z.object({
    status: ProductMatchStatusSchema,
    product: BackendProductSchema,
    reasons: z.array(ProductMatchReasonSchema).min(1),
  })),
});
export type ProductRecommendationResponse = z.infer<typeof ProductRecommendationResponseSchema>;

export const ProductComparisonRequestSchema = z.object({
  product_ids: z.array(ProductSourceIdSchema).length(2),
}).strict().refine(
  ({ product_ids }) => new Set(product_ids).size === 2,
  { message: "서로 다른 상품 2개를 선택해야 합니다.", path: ["product_ids"] },
);

export const ProductComparisonResponseSchema = z.object({
  provider: z.string(),
  source_base_month: z.string().regex(/^\d{6}$/),
  fetched_at: z.string().datetime({ offset: true }),
  source_reference: z.string().url(),
  items: z.array(BackendProductSchema).length(2),
  disclaimer: z.string(),
}).strict();
export type ProductComparisonResponse = z.infer<
  typeof ProductComparisonResponseSchema
>;

/* ------------------------------------------------------------------ */
/* 대출 What-if 시뮬레이션                                             */
/* ------------------------------------------------------------------ */

const DecimalStringSchema = z.string().regex(/^\d+(?:\.\d+)?$/);

export const RepaymentTypeSchema = z.enum([
  "equal_principal_and_interest",
  "equal_principal",
]);
export type RepaymentType = z.infer<typeof RepaymentTypeSchema>;

/** 백엔드 LoanSimulationRequest 는 annual_interest_rate 를 소수점 4자리까지만 받는다. */
export const MAX_INTEREST_RATE_DECIMALS = 4;

export const LoanScenarioInputSchema = z.object({
  principal: z.number().positive().max(999_999_999_999_999.99),
  annualInterestRate: z
    .number()
    .min(0)
    .max(100)
    // 자릿수를 세면 0.1+0.2 같은 부동소수점 잡음까지 거부한다.
    // 4자리로 반올림해도 값이 같은지만 본다.
    .refine(
      (rate) =>
        Math.abs(rate - Number(rate.toFixed(MAX_INTEREST_RATE_DECIMALS))) < 1e-9,
      { message: "금리는 소수점 넷째 자리까지만 입력할 수 있습니다." },
    ),
  months: z.number().int().min(1).max(600),
  repaymentType: RepaymentTypeSchema,
}).strict();
export type LoanScenarioInput = z.infer<typeof LoanScenarioInputSchema>;

export const BackendLoanSimulationRequestSchema = z.object({
  principal: DecimalStringSchema,
  annual_interest_rate: DecimalStringSchema,
  months: z.number().int().min(1).max(600),
  repayment_type: RepaymentTypeSchema,
}).strict();
export type BackendLoanSimulationRequest = z.infer<
  typeof BackendLoanSimulationRequestSchema
>;

export const LoanPaymentScheduleItemSchema = z.object({
  month: z.number().int().min(1),
  principal_payment: DecimalStringSchema,
  interest_payment: DecimalStringSchema,
  payment: DecimalStringSchema,
  remaining_principal: DecimalStringSchema,
}).strict();

export const LoanSimulationResponseSchema = z.object({
  principal: DecimalStringSchema,
  annual_interest_rate: DecimalStringSchema,
  months: z.number().int().min(1).max(600),
  repayment_type: RepaymentTypeSchema,
  monthly_payment: DecimalStringSchema.nullable(),
  schedule: z.array(LoanPaymentScheduleItemSchema).min(1).max(600),
  total_repayment: DecimalStringSchema,
  total_interest: DecimalStringSchema,
  assumptions: z.array(z.string()),
}).strict();
export type LoanSimulationResponse = z.infer<
  typeof LoanSimulationResponseSchema
>;

/* ------------------------------------------------------------------ */
/* 재테크 기초 가이드                                                  */
/* ------------------------------------------------------------------ */

export const WealthModuleCodeSchema = z.enum([
  "money_flow",
  "saving_plan",
  "debt_credit",
  "investment_risk",
]);

export const WealthGuidanceSourceSchema = z.object({
  source_id: z.string().min(1),
  organization: z.string().min(1),
  title: z.string().min(1),
  source_url: z.string().url().startsWith("https://"),
  retrieved_at: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  supports: z.array(WealthModuleCodeSchema).min(1),
}).strict();

export const WealthGuidanceModuleSchema = z.object({
  code: WealthModuleCodeSchema,
  order: z.number().int().min(1).max(4),
  title: z.string().min(1),
  summary: z.string().min(1),
  check_questions: z.array(z.string().min(1)).min(1),
  next_action: z.string().min(1),
  source_ids: z.array(z.string().min(1)).min(1),
}).strict();

export const WealthGuidanceResponseSchema = z.object({
  version: z.literal("0.1"),
  scope_disclaimer: z.string().min(1),
  modules: z.array(WealthGuidanceModuleSchema).length(4),
  official_sources: z.array(WealthGuidanceSourceSchema).min(1),
}).strict();
export type WealthGuidanceResponse = z.infer<
  typeof WealthGuidanceResponseSchema
>;

/**
 * 파생지표.
 *
 * 계산은 프론트에서 하지 않는다. 백엔드 `/profiles/{id}/metrics`가 계산 완료값을
 * 내려주고 화면은 표시만 한다.
 */
export const DerivedMetricSchema = z.object({
  key: z.enum([
    "disposable_cashflow",
    "debt_payment_ratio",
    "emergency_fund_coverage",
  ]),
  /** 전문용어 금지. "매달 쓸 수 있는 돈" 같은 표현. */
  label: z.string(),
  /** 이미 포맷된 표시 문자열 */
  display: z.string(),
  /** 한 줄 쉬운 설명 */
  hint: z.string(),
  tone: z.enum(["positive", "neutral", "caution"]),
  /** 공식 DSR 과 다르다는 식의 주의 문구 */
  caveat: z.string().optional(),
});
export type DerivedMetric = z.infer<typeof DerivedMetricSchema>;

const SignedDecimalStringSchema = z.string().regex(/^-?\d+(?:\.\d+)?$/);

export const ProfileMetricsResponseSchema = z.object({
  version: z.literal("0.1"),
  profile_id: z.string().uuid(),
  profile_updated_at: z.string().datetime({ offset: true }),
  summary: z.string().min(1),
  metrics: z.array(DerivedMetricSchema).length(3),
  calculation: z.object({
    monthly_disposable_cashflow: SignedDecimalStringSchema,
    monthly_debt_payment_ratio_percent: DecimalStringSchema.nullable(),
    emergency_fund_coverage_months: DecimalStringSchema.nullable(),
    essential_monthly_expenses: DecimalStringSchema,
    emergency_fund_target_amount: DecimalStringSchema,
    emergency_fund_gap: DecimalStringSchema,
  }).strict(),
  assumptions: z.array(z.string().min(1)).min(3),
  disclaimer: z.string().min(1),
}).strict();
export type ProfileMetricsResponse = z.infer<typeof ProfileMetricsResponseSchema>;

export const FinancialSnapshotSchema = z.object({
  hasProfile: z.boolean(),
  profile: FinancialProfileSchema.nullable(),
  /** 금융상태를 요약한 한 문장 */
  summary: z.string(),
  metrics: z.array(DerivedMetricSchema),
  source: SourceKindSchema,
});
export type FinancialSnapshot = z.infer<typeof FinancialSnapshotSchema>;

/* ------------------------------------------------------------------ */
/* Home                                                                */
/* ------------------------------------------------------------------ */

/** "지금 확인할 금융정보" 한 건 */
export const CheckItemSchema = z.object({
  id: z.string(),
  title: z.string(),
  reason: z.string(),
  href: z.string(),
  evidence: EvidenceSchema.optional(),
});
export type CheckItem = z.infer<typeof CheckItemSchema>;

/** "다음 행동" */
export const NextActionSchema = z.object({
  id: z.string(),
  title: z.string(),
  detail: z.string(),
  href: z.string(),
  ctaLabel: z.string(),
});
export type NextAction = z.infer<typeof NextActionSchema>;

export const HomeViewSchema = z.object({
  greetingName: z.string().nullable(),
  snapshot: FinancialSnapshotSchema,
  checkItems: z.array(CheckItemSchema),
  checkItemsSource: SourceKindSchema,
  recentAnalyses: z.array(AnalysisSummarySchema),
  recentAnalysesSource: SourceKindSchema,
  nextAction: NextActionSchema.nullable(),
  nextActionSource: SourceKindSchema,
});
export type HomeView = z.infer<typeof HomeViewSchema>;
