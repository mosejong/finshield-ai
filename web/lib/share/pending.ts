"use client";

import { useSyncExternalStore } from "react";
import { ANALYZE_TEXT_MAX_LENGTH } from "@/lib/api/contracts";
import { SHARE_HANDOFF_KEY } from "@/lib/share/handoff";

/**
 * 공유 시트로 들어와 sessionStorage 에 놓인 내용을 확인 화면으로 넘긴다.
 *
 * 모듈이 브라우저에서 평가될 때 딱 한 번 꺼내고 곧바로 지운다. 이 값은 사용자가
 * 받은 문자 원문이라 화면이 한 번 집어간 뒤에는 저장소에 남겨 둘 이유가 없다.
 * 남겨 두면 나중에 `/check` 를 다시 열었을 때 예전 문자가 되살아난다.
 *
 * 공유 인계는 `location.replace` 로 오는 전체 문서 로드라서, 모듈 평가 시점이면
 * 값은 이미 저장소에 들어와 있다.
 *
 * `useEffect` 로 읽지 않는 이유는, 그러면 마운트 직후 setState 가 한 번 더 돌고
 * React Compiler 린트가 이를 막기 때문이다. sessionStorage 는 애초에 React 밖의
 * 스토어이므로 `useSyncExternalStore` 로 읽는 편이 맞다 - `useHydrated` 와 같은
 * 이유다. 서버 스냅샷을 null 로 두어 하이드레이션 불일치도 생기지 않는다.
 *
 * `handoff.ts` 와 파일을 나눈 것은 이 모듈이 `"use client"` 이기 때문이다.
 * 라우트 핸들러가 서버에서 `handoff.ts` 를 부르므로 둘을 합칠 수 없다.
 */

const pending = takeOnce();

function takeOnce(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const value = window.sessionStorage.getItem(SHARE_HANDOFF_KEY);
    if (!value) return null;
    window.sessionStorage.removeItem(SHARE_HANDOFF_KEY);
    // 서버가 이미 잘라서 보내지만, 저장소 값은 무엇이든 들어올 수 있다.
    return value.slice(0, ANALYZE_TEXT_MAX_LENGTH);
  } catch {
    // 프라이빗 모드 등에서 접근이 막힐 수 있다. 빈 입력창으로 연다.
    return null;
  }
}

const neverChanges = () => () => {};

export function usePendingShare(): string | null {
  return useSyncExternalStore(
    neverChanges,
    () => pending,
    () => null,
  );
}
