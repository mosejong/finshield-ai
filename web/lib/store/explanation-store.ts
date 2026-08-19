"use client";

import { useEffect, useState } from "react";
import type { AnalyzeRequest, Explanation } from "@/lib/api/contracts";
import { explainFromClient } from "@/lib/api/explanation";

/**
 * 설명 요청을 확인 화면에서 결과 화면으로 넘기는 보관소.
 *
 * **sessionStorage 를 쓰지 않는다.** 여기에 담기는 것은 사용자가 붙여넣은 원문
 * 이고, 그 안에는 이름·계좌번호·연락처가 들어 있을 수 있다. 분석 결과는 이미
 * 판정으로 가공된 값이라 sessionStorage 에 두지만(`analysis-store.ts`), 원문은
 * 가공되지 않은 그대로다. `share/pending.ts` 가 공유로 받은 원문을 화면이
 * 집어가는 즉시 저장소에서 지우는 것과 같은 이유다.
 *
 * 대가는 분명하다. **새로고침하면 설명은 다시 붙지 않는다.** 원문이 사라졌으니
 * 물어볼 수가 없다. 판정·신호·행동·공식 근거는 그대로 남고 "왜 위험한지" 블록만
 * 결정론 요약으로 돌아간다. 원문을 저장소에 남기는 것보다 이쪽이 낫다고 봤다.
 *
 * 결과를 `Promise` 째로 캐시하는 것도 의도다. 설명은 유료 외부 호출이고 한 번에
 * 8초쯤 걸린다. 개발 모드의 StrictMode 이중 실행이나 결과 화면을 다시 여는 것
 * 만으로 같은 호출이 두 번 나가면 안 된다.
 */

let pendingInput: { id: string; request: AnalyzeRequest } | null = null;

const inFlight = new Map<string, Promise<Explanation>>();

/** 확인 화면이 분석 직후 부른다. 가장 최근 것 하나만 들고 있는다. */
export function rememberAnalysisInput(
  id: string,
  request: AnalyzeRequest,
): void {
  pendingInput = { id, request };
}

/**
 * 설명을 요청한다. 물어볼 원문이 없으면 `null`.
 *
 * `null` 은 실패가 아니다. 새로고침으로 들어왔거나 예시 결과를 보고 있는
 * 상태이고, 화면은 설명 블록 없이 그대로 성립한다.
 */
export function requestExplanation(id: string): Promise<Explanation> | null {
  const cached = inFlight.get(id);
  if (cached) return cached;

  if (!pendingInput || pendingInput.id !== id) return null;

  const { request } = pendingInput;
  // 요청을 만든 즉시 원문을 버린다. 두 번 쓸 일이 없고, 들고 있을수록 나쁘다.
  pendingInput = null;

  const promise = explainFromClient(request);
  inFlight.set(id, promise);
  return promise;
}

/** "이 결과 지우기" 가 부른다. 원문과 설명이 결과보다 오래 남으면 안 된다. */
export function forgetExplanation(id: string): void {
  if (pendingInput?.id === id) pendingInput = null;
  inFlight.delete(id);
}

/**
 * 결과 화면이 쓰는 훅.
 *
 * `null` 은 "아직 모른다" 다 - 로딩 중이거나, 물어볼 원문이 없어 곧 `off` 로
 * 정해질 참이다. 상태가 정해지기 전까지 블록을 그리지 않으면 화면이 덜컥거리
 * 므로, 로딩은 블록 안에서 보여준다.
 */
export function useExplanation(id: string, enabled: boolean): Explanation | null {
  const [explanation, setExplanation] = useState<Explanation | null>(null);

  useEffect(() => {
    if (!enabled) return;

    let active = true;

    /*
      물어볼 원문이 없으면 화면 결과는 계층이 꺼진 것과 같다 - 어느 쪽이든
      설명 블록을 그리지 않는다. 여기서 곧바로 setState 하지 않고 이미 resolve
      된 Promise 로 맞춰 두는 이유는, 효과 본문에서 동기적으로 상태를 바꾸면
      렌더가 한 번 더 도는 것을 React Compiler 린트가 막기 때문이다.
    */
    const promise =
      requestExplanation(id) ??
      Promise.resolve<Explanation>({ status: "off", text: null, model: null });

    // `explainFromClient` 는 스스로 실패를 삼켜 `failed` 로 돌려주므로 여기서
    // 거부될 일이 없다. 그래도 catch 를 다는 것은, 캐시에 넣어 둔 Promise 가
    // 거부되면 화면이 아니라 처리되지 않은 거부로 터지기 때문이다.
    promise
      .then((result) => {
        if (active) setExplanation(result);
      })
      .catch(() => {
        if (active) setExplanation({ status: "failed", text: null, model: null });
      });

    return () => {
      active = false;
    };
  }, [id, enabled]);

  return explanation;
}
