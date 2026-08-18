"use client";

import { useEffect } from "react";

/**
 * 서비스 워커 등록. 화면에는 아무것도 그리지 않는다.
 *
 * 개발 모드에서는 등록하지 않는다. `next dev` 는 매 요청마다 산출물 경로가
 * 바뀌는데, 워커가 그중 일부를 붙들고 있으면 고친 코드가 반영되지 않는 것처럼
 * 보인다. 실제 동작은 `npm run build && npm start` 로 확인한다.
 *
 * `updateViaCache: "none"` 은 워커 파일 자체를 HTTP 캐시에서 꺼내 쓰지 않게
 * 한다. `next.config.ts` 의 `/sw.js` no-store 헤더와 같은 목적이다 - 워커를
 * 고쳤는데 기기에 옛 사본이 남아 있으면 되돌릴 방법이 사실상 없다.
 */
export function ServiceWorkerRegistration() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") return;
    if (!("serviceWorker" in navigator)) return;

    function register() {
      navigator.serviceWorker
        .register("/sw.js", { scope: "/", updateViaCache: "none" })
        .catch(() => {
          // 등록 실패는 오프라인 안내를 못 쓴다는 뜻일 뿐이다. 화면은 그대로
          // 동작하므로 사용자에게 알리지 않는다.
        });
    }

    // 첫 화면이 그려지는 동안 워커 설치가 대역폭을 가져가지 않게 미룬다.
    if (document.readyState === "complete") {
      register();
      return;
    }
    window.addEventListener("load", register);
    return () => window.removeEventListener("load", register);
  }, []);

  return null;
}
