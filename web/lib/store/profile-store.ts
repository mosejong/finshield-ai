"use client";

import { useSyncExternalStore } from "react";
import {
  FinancialProfileSchema,
  type FinancialProfile,
} from "@/lib/api/contracts";
import {
  readSession,
  removeSession,
  subscribeSession,
  writeSession,
} from "@/lib/store/session-store";

/**
 * 온보딩에서 입력한 금융 프로필의 임시 보관소.
 *
 * 백엔드 `/api/v1/profiles` 가 없어서 브라우저 세션에만 둔다.
 * localStorage 가 아니라 sessionStorage 를 쓰는 이유는 소득·부채 정보를
 * 기기에 남기지 않기 위해서다. (docs/09 — 최소 수집 원칙)
 */

const KEY = "finshield:profile";

export function saveProfile(profile: FinancialProfile): void {
  writeSession(KEY, JSON.stringify(profile));
}

export function clearProfile(): void {
  removeSession(KEY);
}

/**
 * useSyncExternalStore 는 값이 바뀌지 않았으면 같은 참조를 돌려받아야 한다.
 * 매번 JSON.parse 하면 새 객체가 나와 렌더가 끝없이 돈다. 원문 문자열로 캐시한다.
 */
let cachedRaw: string | null = null;
let cachedProfile: FinancialProfile | null = null;

function snapshot(): FinancialProfile | null {
  const raw = readSession(KEY);
  if (raw === cachedRaw) return cachedProfile;

  cachedRaw = raw;
  cachedProfile = null;

  if (raw) {
    try {
      const parsed = FinancialProfileSchema.safeParse(JSON.parse(raw));
      if (parsed.success) cachedProfile = parsed.data;
    } catch {
      // 손상된 값은 없는 것으로 본다.
    }
  }

  return cachedProfile;
}

const serverSnapshot = () => null;

export function useStoredProfile(): FinancialProfile | null {
  return useSyncExternalStore(subscribeSession, snapshot, serverSnapshot);
}
