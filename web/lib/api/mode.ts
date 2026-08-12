export type ApiMode = "live" | "mock";

/**
 * live  — 위험 신호/점수는 FastAPI 백엔드에서 받고, 아직 없는 필드만 mock 으로 채운다.
 * mock  — 백엔드를 부르지 않고 예시 결과를 보여준다. 서버 없이 화면을 볼 때 쓴다.
 *
 * 기본값은 live 다. 백엔드가 꺼져 있으면 가짜 결과로 조용히 대체하지 않고
 * 오류를 그대로 보여준다. (docs/11-engineering-standards.md — Errors)
 */
export function apiMode(): ApiMode {
  return process.env.NEXT_PUBLIC_API_MODE === "mock" ? "mock" : "live";
}
