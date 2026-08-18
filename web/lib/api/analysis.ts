import {
  AnalysisResultSchema,
  BackendAnalyzeResponseSchema,
  type BackendAction,
  type AnalysisResult,
  type AnalyzeRequest,
  type RiskLevel,
  type RiskSignal,
} from "@/lib/api/contracts";
import { ApiError, postJson, retryHint } from "@/lib/api/client";
import { apiMode } from "@/lib/api/mode";
import { demoAnalysis, headline, stateSummary } from "@/lib/mock/analysis";

/**
 * 사기 분석 서비스.
 *
 * Scenario Engine v0.1의 판정, 요약, 행동, 공식 근거를 화면 계약으로 변환한다.
 * 프론트는 위험도를 재계산하지 않고 행동 코드의 표시 그룹과 연락처 링크만 매핑한다.
 */

function toRiskLevel(value: string): RiskLevel {
  if (value === "high" || value === "medium" || value === "low") return value;
  // 알 수 없는 값이면 낮게 보이도록 낙관하지 않는다.
  return "high";
}

function newAnalysisId(): string {
  return `a-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

const CONTACTS: Partial<
  Record<BackendAction["code"], { phone: string; label: string }>
> = {
  CONTACT_112: { phone: "112", label: "경찰 112" },
  CONTACT_1394: {
    phone: "1394",
    label: "보이스피싱 통합신고대응센터 1394",
  },
  CONTACT_KISA_118: { phone: "118", label: "KISA 118" },
};

function actionKind(action: BackendAction): "immediate" | "soon" | "avoid" {
  if (action.code.startsWith("DO_NOT_")) return "avoid";
  return action.priority === 1 ? "immediate" : "soon";
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
    weight: signal.weight,
    source: "live",
  }));

  const state = parsed.scenario ?? request.state;
  const actions = parsed.actions.map((action) => {
    const contact = CONTACTS[action.code];
    return {
      id: action.code,
      title: action.title,
      detail: action.reason,
      kind: actionKind(action),
      contactPhone: contact?.phone,
      contactLabel: contact?.label,
      evidenceIds: action.source_ids,
    };
  });

  const evidence = parsed.official_sources.map((source) => ({
    id: source.source_id,
    title: source.title,
    publisher: source.organization,
    url: source.source_url,
    verified: true,
    fetchedAt: source.retrieved_at,
  }));

  return AnalysisResultSchema.parse({
    id: newAnalysisId(),
    createdAt: new Date().toISOString(),

    level,
    headline: headline(level, state),
    headlineSource: "live",

    signals,
    fraudTypes: parsed.fraud_types,

    why: [parsed.summary],
    whySource: "live",

    state,
    stateSummary: stateSummary(state),
    stateSource: "live",

    actions,
    actionsSource: "live",

    evidence,
    evidenceSource: "live",

    score: parsed.risk_score,
    scoreSource: "live",
    engine: "Scenario Engine v0.1 (결정론적 규칙·상태 정책)",

    disclaimer: parsed.disclaimer,
  });
}

/** 서버 사이드 전용. Route Handler 에서만 호출한다. */
export async function analyzeOnServer(
  request: AnalyzeRequest,
  headers: HeadersInit = {},
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
    undefined,
    headers,
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
      case "http":
        // 분석이 "안전하다" 가 아니라 "돌지 않았다" 로 읽히게 쓴다.
        if (error.status === 429) {
          return {
            message: "요청이 많아 분석을 잠시 멈췄습니다. 아직 위험 여부는 확인되지 않았습니다.",
            hint: `${retryHint(error.retryAfterSeconds)} 지금 급하다면 경찰 112 또는 보이스피싱 통합신고대응센터 1394로 바로 연락하세요.`,
          };
        }
        if (error.status === 413) {
          return {
            message: "보낸 내용이 너무 길어 분석하지 못했습니다.",
            hint: "확인이 필요한 부분만 남기고 다시 붙여넣어 주세요.",
          };
        }
        return {
          message: error.message,
          hint: "잠시 후 다시 시도해 주세요.",
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
