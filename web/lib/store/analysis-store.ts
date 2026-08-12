"use client";

import { useCallback, useSyncExternalStore } from "react";
import { AnalysisResultSchema, type AnalysisResult } from "@/lib/api/contracts";
import {
  readSession,
  removeSession,
  subscribeSession,
  writeSession,
} from "@/lib/store/session-store";

/**
 * 분석 결과를 결과 화면으로 넘기기 위한 임시 보관소.
 *
 * sessionStorage 를 쓰는 이유: 사용자가 붙여넣은 원문과 분석 결과를 서버나
 * localStorage 에 남기지 않기 위해서다. 탭을 닫으면 사라진다.
 * (docs/03-product-scope.md — 개인정보 저장 최소화)
 */

const KEY_PREFIX = "finshield:analysis:";

export function saveAnalysis(result: AnalysisResult): void {
  writeSession(`${KEY_PREFIX}${result.id}`, JSON.stringify(result));
}

export function clearAnalysis(id: string): void {
  cache.delete(id);
  removeSession(`${KEY_PREFIX}${id}`);
}

/**
 * useSyncExternalStore 는 값이 안 바뀌었으면 같은 참조를 받아야 한다.
 * 매번 JSON.parse 하면 새 객체가 나와 렌더가 끝없이 돈다.
 *
 * id 별로 캐시한다. 한 항목만 캐시하면 서로 다른 id 를 읽는 컴포넌트가
 * 둘 있을 때 캐시가 번갈아 무효화되면서 같은 무한 렌더가 난다.
 */
const cache = new Map<string, { raw: string | null; value: AnalysisResult | null }>();

export function loadAnalysis(id: string): AnalysisResult | null {
  const raw = readSession(`${KEY_PREFIX}${id}`);

  const cached = cache.get(id);
  if (cached && cached.raw === raw) return cached.value;

  let value: AnalysisResult | null = null;
  if (raw) {
    try {
      const parsed = AnalysisResultSchema.safeParse(JSON.parse(raw));
      if (parsed.success) value = parsed.data;
    } catch {
      // 손상된 값은 없는 것으로 본다.
    }
  }

  cache.set(id, { raw, value });
  return value;
}

const serverSnapshot = () => null;

export function useStoredAnalysis(id: string): AnalysisResult | null {
  const snapshot = useCallback(() => loadAnalysis(id), [id]);
  return useSyncExternalStore(subscribeSession, snapshot, serverSnapshot);
}
