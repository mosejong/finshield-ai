"use client";

import { useSyncExternalStore } from "react";
import type { AnalyzeRequest } from "@/lib/api/contracts";

/**
 * 결과 화면에서 상황을 바꿔 다시 확인하기 위한 원문 보관소.
 *
 * "같은 문자를 받기만 한 사람"과 "같은 문자를 받고 이미 송금한 사람"은 같은
 * 판정에서 서로 다른 행동 목록을 받아야 한다. 그 전환은 결과를 본 **뒤에**
 * 일어난다 - 사용자는 결과를 읽으면서 자기가 무엇을 했는지 다시 떠올린다.
 * 그때 원문을 다시 붙여넣게 하면 그 사람은 대부분 그냥 나간다.
 *
 * `explanation-store.ts` 와 나눠 둔 이유가 있다. 그쪽은 설명 요청을 만드는
 * 즉시 원문을 버린다 - 한 번 쓰고 끝이라 들고 있을 이유가 없기 때문이다.
 * 다시 확인하기는 성격이 다르다. 사용자가 상황을 고칠 때까지 원문이 있어야
 * 하고, 그래서 **더 오래 들고 있는다.** 그 대가를 다음 세 가지로 좁혔다.
 *
 *   1. **sessionStorage 도 서버도 아니다.** 모듈 메모리 한 칸이다. 새로고침·
 *      탭 종료·다른 기기 어디에도 남지 않는다. 그래서 새로고침한 결과 화면
 *      에서는 이 기능이 사라지고 `/check` 로 가는 링크로 돌아간다.
 *   2. **한 건만 들고 있는다.** 새 분석이 들어오면 앞의 것을 덮는다.
 *   3. **"이 결과 지우기" 가 같이 지운다.** 원문이 결과보다 오래 남으면 안
 *      된다는 규칙은 그대로다.
 */

let pending: { id: string; request: AnalyzeRequest } | null = null;

/** 분석 직후 부른다. 가장 최근 것 하나만 남는다. */
export function rememberRecheckInput(id: string, request: AnalyzeRequest): void {
  pending = { id, request };
}

/** 이 결과를 다시 확인할 수 있는가. 없으면 `null` 이고 화면은 링크로 물러난다. */
export function recheckInputFor(id: string): AnalyzeRequest | null {
  return pending && pending.id === id ? pending.request : null;
}

/** "이 결과 지우기" 와 재확인 성공이 부른다. */
export function forgetRecheckInput(id: string): void {
  if (pending?.id === id) pending = null;
}

/*
  구독하지 않는 외부 스토어로 읽는다. `session-store.ts` 의 `useHydrated` 와
  같은 모양이다.

  모듈 변수를 렌더 본문에서 그냥 읽으면 서버 렌더(항상 없음)와 클라이언트 첫
  렌더가 갈라질 수 있고, React Compiler 는 렌더가 순수하다고 보고 메모해도
  된다고 판단한다. `useSyncExternalStore` 는 서버 스냅샷을 따로 받으므로 그
  둘을 명시적으로 갈라 준다.

  구독이 비어 있는 것도 의도다. 이 값은 화면 밖에서 바뀌지 않는다 - 바뀌는
  경우는 새 분석뿐이고 그때는 새 id 로 페이지가 다시 열린다. 반환값은 매번
  같은 객체 참조라 스냅샷이 흔들리지 않는다.
*/
const noSubscribe = () => () => {};
const serverSnapshot = () => null;

export function useRecheckInput(id: string, enabled: boolean): AnalyzeRequest | null {
  return useSyncExternalStore(
    noSubscribe,
    () => (enabled ? recheckInputFor(id) : null),
    serverSnapshot,
  );
}
