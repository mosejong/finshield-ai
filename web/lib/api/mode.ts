export type ApiMode = "live" | "mock";

/**
 * live  — 판정·설명·행동·공식 근거를 FastAPI Scenario Engine에서 받는다.
 * mock  — 백엔드를 부르지 않고 예시 결과를 보여준다. 서버 없이 화면을 볼 때 쓴다.
 *
 * 기본값은 live 다. 백엔드가 꺼져 있으면 가짜 결과로 조용히 대체하지 않고
 * 오류를 그대로 보여준다. (docs/11-engineering-standards.md — Errors)
 */
export function apiMode(): ApiMode {
  return process.env.NEXT_PUBLIC_API_MODE === "mock" ? "mock" : "live";
}
