import {
  AnalysisResultSchema,
  BackendAnalyzeResponseSchema,
  type AnalysisResult,
  type AnalyzeRequest,
  type RiskLevel,
  type RiskSignal,
} from "@/lib/api/contracts";
import { ApiError, postJson } from "@/lib/api/client";
import { apiMode } from "@/lib/api/mode";
import {
  buildActions,
  buildWhy,
  collectEvidence,
  demoAnalysis,
  headline,
  signalWhy,
  stateSummary,
} from "@/lib/mock/analysis";

/**
 * 사기 분석 서비스.
 *
 * 백엔드가 주는 것: risk_score, risk_level, signals, scenario, disclaimer
 * 백엔드에 없는 것: 설명(why), 대응 행동(actions), 근거(evidence), 헤드라인
 *
 * 없는 것은 mock 으로 채우되 `source: "mock"` 으로 표시해서 화면이 구분할 수 있게 한다.
 * 실제 판정에 해당하는 값(level, score, signals)은 절대 프론트에서 만들어내지 않는다.
 */

function toRiskLevel(value: string): RiskLevel {
  if (value === "high" || value === "medium" || value === "low") return value;
  // 알 수 없는 값이면 낮게 보이도록 낙관하지 않는다.
  return "high";
}

function newAnalysisId(): string {
  return `a-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

/** 백엔드 응답 + mock 보강 → 화면이 쓰는 AnalysisResult */
export function adaptBackendAnalysis(
  backend: unknown,
  request: AnalyzeRequest,
): AnalysisResult {
  const parsed = BackendAnalyzeResponseSchema.parse(backend);
  const level = toRiskLevel(parsed.risk_level);

  const signals: RiskSignal[] = parsed.signals.map((signal) => ({
    code: signal.code,
    label: signal.label,
    // 신호 자체는 live, 설명 문구만 mock 이다.
    why: signalWhy(signal.code),
    weight: signal.weight,
    source: "live",
  }));

  const state = parsed.scenario ?? request.state;
  const actions = buildActions(state, level);

  return AnalysisResultSchema.parse({
    id: newAnalysisId(),
    createdAt: new Date().toISOString(),

    level,
    headline: headline(level, state),
    headlineSource: "mock",

    signals,

    why: buildWhy(
      level,
      signals.map((signal) => signal.code),
    ),
    whySource: "mock",

    state,
    stateSummary: stateSummary(state),
    stateSource: "mock",

    actions,
    actionsSource: "mock",

    evidence: collectEvidence(actions),
    evidenceSource: "mock",

    score: parsed.risk_score,
    scoreSource: "live",
    engine: "규칙 기반 baseline (app/core/risk_engine.py)",

    disclaimer: parsed.disclaimer,
  });
}

/** 서버 사이드 전용. Route Handler 에서만 호출한다. */
export async function analyzeOnServer(
  request: AnalyzeRequest,
): Promise<AnalysisResult> {
  if (apiMode() === "mock") {
    return demoAnalysis(newAnalysisId(), request.state);
  }

  const backend = await postJson(
    "/api/v1/analyze",
    {
      text: request.text,
      persona: request.persona,
      state: request.state,
      url: request.url ?? null,
    },
    BackendAnalyzeResponseSchema,
  );

  return adaptBackendAnalysis(backend, request);
}

/* ------------------------------------------------------------------ */
/* 클라이언트 → Next Route Handler                                      */
/* ------------------------------------------------------------------ */

export type AnalyzeFailure = {
  message: string;
  hint?: string;
};

export async function analyzeFromClient(
  request: AnalyzeRequest,
): Promise<{ ok: true; result: AnalysisResult } | { ok: false } & AnalyzeFailure> {
  let response: Response;
  try {
    response = await fetch("/api/proxy/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
  } catch {
    return {
      ok: false,
      message: "분석을 요청하지 못했습니다.",
      hint: "네트워크 연결을 확인한 뒤 다시 시도해 주세요.",
    };
  }

  const payload: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    const failure =
      payload && typeof payload === "object" && "message" in payload
        ? (payload as AnalyzeFailure)
        : null;
    return {
      ok: false,
      message: failure?.message ?? "분석에 실패했습니다.",
      hint: failure?.hint,
    };
  }

  const parsed = AnalysisResultSchema.safeParse(payload);
  if (!parsed.success) {
    return {
      ok: false,
      message: "분석 결과를 이해하지 못했습니다.",
      hint: "잠시 후 다시 시도해 주세요.",
    };
  }

  return { ok: true, result: parsed.data };
}

/** ApiError 를 사용자에게 보여줄 문구로 바꾼다. 실패를 '위험 없음'으로 바꾸지 않는다. */
export function describeApiError(error: unknown): AnalyzeFailure {
  if (error instanceof ApiError) {
    switch (error.kind) {
      case "network":
        return {
          message: "분석 서버에 연결하지 못했습니다.",
          hint: "백엔드를 실행하거나(uvicorn app.main:app), NEXT_PUBLIC_API_MODE=mock 으로 예시 화면을 볼 수 있습니다.",
        };
      case "timeout":
        return {
          message: "분석 서버 응답이 너무 늦습니다.",
          hint: "잠시 후 다시 시도해 주세요.",
        };
      case "schema":
        return {
          message: "분석 서버 응답 형식이 예상과 다릅니다.",
          hint: "백엔드 스키마가 바뀌었을 수 있습니다.",
        };
      default:
        return {
          message: error.message,
          hint: "잠시 후 다시 시도해 주세요.",
        };
    }
  }
  return {
    message: "분석 중 알 수 없는 문제가 발생했습니다.",
    hint: "잠시 후 다시 시도해 주세요.",
  };
}
