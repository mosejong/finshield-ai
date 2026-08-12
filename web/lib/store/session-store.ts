"use client";

import { useSyncExternalStore } from "react";

/**
 * sessionStorage 를 React 외부 스토어로 다루기 위한 최소 도구.
 *
 * useEffect 안에서 setState 로 읽어오면 하이드레이션 이후 한 번 더 렌더가 돌고,
 * React Compiler 린트도 이를 잡아낸다. sessionStorage 는 애초에 React 밖의
 * 스토어이므로 useSyncExternalStore 로 구독하는 편이 맞다.
 */

const listeners = new Set<() => void>();

/** 같은 탭에서 값을 바꿨을 때 구독자에게 알린다. storage 이벤트는 다른 탭에서만 온다. */
export function notifySessionChange(): void {
  for (const listener of listeners) listener();
}

export function subscribeSession(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

export function readSession(key: string): string | null {
  try {
    return sessionStorage.getItem(key);
  } catch {
    // 프라이빗 모드 등에서 접근이 막힐 수 있다. 값이 없는 것으로 본다.
    return null;
  }
}

export function writeSession(key: string, value: string): void {
  try {
    sessionStorage.setItem(key, value);
  } catch {
    // 저장 실패는 치명적이지 않다. 화면은 이미 값을 들고 있다.
  }
  notifySessionChange();
}

export function removeSession(key: string): void {
  try {
    sessionStorage.removeItem(key);
  } catch {
    // 무시
  }
  notifySessionChange();
}

const alwaysSubscribed = () => () => {};

/**
 * 서버 렌더 결과와 클라이언트 첫 렌더를 일치시키기 위한 플래그.
 *
 * false 인 동안은 sessionStorage 값을 신뢰할 수 없다. 이 값이 true 로 바뀐
 * 뒤에 읽어야 "저장된 값이 없음"과 "아직 못 읽음"을 구분할 수 있다.
 */
export function useHydrated(): boolean {
  return useSyncExternalStore(
    alwaysSubscribed,
    () => true,
    () => false,
  );
}
