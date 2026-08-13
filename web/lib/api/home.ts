import type { FinancialSnapshot } from "@/lib/api/contracts";
import { EMPTY_SNAPSHOT, MOCK_SNAPSHOT } from "@/lib/mock/profile";

/**
 * profile 화면에서 입력 전 구조를 보여주는 명시적 예시 fixture다. 실제 Home 금융상태는
 * HomeFinancialStatus가 저장 profile과 `/profiles/{id}/metrics`를 live로 읽는다.
 */

export function getSnapshot(hasProfile = true): FinancialSnapshot {
  return hasProfile ? MOCK_SNAPSHOT : EMPTY_SNAPSHOT;
}
