import type { FinancialSnapshot, HomeView } from "@/lib/api/contracts";
import { EMPTY_SNAPSHOT, MOCK_SNAPSHOT } from "@/lib/mock/profile";
import {
  MOCK_CHECK_ITEMS,
  MOCK_NEXT_ACTION,
  ONBOARDING_NEXT_ACTION,
} from "@/lib/mock/home";
import { MOCK_RECENT_ANALYSES } from "@/lib/mock/analysis";

/**
 * 파생지표와 최근 분석 이력은 아직 mock이다. 저장된 profile 자체는 별도
 * `/api/v1/profiles` adapter가 관리한다.
 * (`/api/v1/profiles`, `/api/v1/recommendations` 미구현 — SKILL.md 참고)
 * 전부 mock 이며 화면에 mock 배지가 붙는다.
 */

export function getSnapshot(hasProfile = true): FinancialSnapshot {
  return hasProfile ? MOCK_SNAPSHOT : EMPTY_SNAPSHOT;
}

export function getHomeView(hasProfile = true): HomeView {
  const snapshot = getSnapshot(hasProfile);

  return {
    greetingName: null,
    snapshot,
    checkItems: hasProfile ? MOCK_CHECK_ITEMS : [],
    checkItemsSource: "mock",
    recentAnalyses: MOCK_RECENT_ANALYSES,
    recentAnalysesSource: "mock",
    nextAction: hasProfile ? MOCK_NEXT_ACTION : ONBOARDING_NEXT_ACTION,
    nextActionSource: "mock",
  };
}
