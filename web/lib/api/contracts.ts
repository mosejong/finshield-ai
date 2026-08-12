import { z } from "zod";

/**
 * 프론트엔드가 기대하는 데이터 계약.
 *
 * 백엔드가 아직 제공하지 않는 필드가 포함되어 있다. 그런 필드는 mock 어댑터가
 * 채우고 `source: "mock"` 으로 표시되며, 화면에서 MockBadge 로 노출된다.
 * 백엔드 구현이 끝나면 어댑터만 교체하고 이 파일은 그대로 둔다.
 *
 * 백엔드 실제 응답 스키마는 BackendAnalyzeResponseSchema 하나뿐이다.
 */

/** 값의 출처. 화면은 이 값을 보고 mock 배지를 붙일지 결정한다. */
export const SourceKindSchema = z.enum(["live", "mock"]);
export type SourceKind = z.infer<typeof SourceKindSchema>;

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

export const BackendAnalyzeResponseSchema = z.object({
  risk_score: z.number().int().min(0).max(100),
  risk_level: z.string(),
  signals: z.array(BackendRiskSignalSchema),
  scenario: UserStateSchema,
  disclaimer: z.string(),
});
export type BackendAnalyzeResponse = z.infer<
  typeof BackendAnalyzeResponseSchema
>;

/* ------------------------------------------------------------------ */
/* 사기 분석 — 프론트 계약                                              */
/* ------------------------------------------------------------------ */

export const AnalyzeRequestSchema = z.object({
  text: z.string().min(1).max(10000),
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

export const AgeBandSchema = z.enum(["19-24", "25-29", "30-34", "35-39", "40+"]);
export const EmploymentStatusSchema = z.enum([
  "employed",
  "probation",
  "freelance",
  "self_employed",
  "job_seeking",
  "student",
]);
export const CreditScoreBandSchema = z.enum([
  "unknown",
  "very_high",
  "high",
  "medium",
  "low",
]);
export const FinancialGoalSchema = z.enum([
  "housing",
  "emergency_cash",
  "debt_refinance",
  "living_expense",
  "business",
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

  monthlyNetIncome: z.number().int().min(0),
  monthlyFixedExpenses: z.number().int().min(0),
  monthlyVariableExpenses: z.number().int().min(0),
  liquidAssets: z.number().int().min(0),

  totalDebt: z.number().int().min(0),
  monthlyDebtPayment: z.number().int().min(0),

  creditScoreBand: CreditScoreBandSchema,
  goal: FinancialGoalSchema,
  persona: PersonaSchema,
});
export type FinancialProfile = z.infer<typeof FinancialProfileSchema>;

/**
 * 파생지표.
 *
 * 계산은 프론트에서 하지 않는다. 서비스 레이어가 계산 완료값을 내려주고
 * 화면은 표시만 한다. 백엔드 `/profiles/{id}/metrics` 가 생기면 그대로 교체된다.
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
