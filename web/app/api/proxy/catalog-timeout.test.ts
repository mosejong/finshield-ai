import { afterEach, describe, expect, it, vi } from "vitest";
import { CATALOG_TIMEOUT_MS } from "@/lib/api/client";
import { POST as recommendations } from "@/app/api/proxy/recommendations/route";
import { POST as compare } from "@/app/api/proxy/products/compare/route";
import { GET as productDetail } from "@/app/api/proxy/products/[productId]/route";

/*
  2026-09-05, 공개 URL 에서 나온 장애의 회귀 시험.

  공식 상품 목록은 캐시가 비어 있으면 공공데이터포털을 여러 번 부른다. 그때
  걸린 시간이 9.6 초였고, 프록시의 기본 8 초 예산이 먼저 끊어 502 를 냈다.
  캐시가 찬 뒤 같은 요청은 1.1 초에 200 이었다. 백엔드는 멀쩡했는데 프록시가
  고장으로 바꿔 보고한 것이다.

  그래서 여기서 재는 것은 "느린 응답을 기다리는가" 하나다. 얼마나 느려지는지는
  백엔드 쪽 문제이고(공급자 호출 수를 줄인 것은 별도), 이 예산은 살아 있는
  응답을 죽음으로 바꾸지 않기 위한 것이다. 공급자가 정말 죽어 있으면 예산이
  끝난 뒤 그대로 502 가 나가는 것도 함께 확인한다.
*/

/** 취소되기 전에는 끝나지 않는 백엔드. 예산이 얼마인지만 드러낸다. */
function neverAnsweringBackend() {
  const fetchMock = vi.fn(
    (_url: string, init: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init.signal?.addEventListener("abort", () => {
          reject(new DOMException("The operation was aborted.", "AbortError"));
        });
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const CATALOG_ROUTES: ReadonlyArray<readonly [string, () => Promise<Response>]> = [
  [
    "POST /api/proxy/recommendations",
    () =>
      recommendations(
        new Request("http://localhost/api/proxy/recommendations", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ goal: "emergency_cash" }),
        }),
      ),
  ],
  [
    "POST /api/proxy/products/compare",
    () =>
      compare(
        new Request("http://localhost/api/proxy/products/compare", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ product_ids: ["202608:1", "202608:2"] }),
        }),
      ),
  ],
  [
    "GET /api/proxy/products/[productId]",
    () =>
      productDetail(
        new Request("http://localhost/api/proxy/products/202608:1"),
        { params: Promise.resolve({ productId: "202608%3A1" }) },
      ),
  ],
];

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("공식 상품 경로의 응답 예산", () => {
  it.each(CATALOG_ROUTES)("%s 는 8 초에 끊지 않는다", async (_name, call) => {
    vi.useFakeTimers();
    neverAnsweringBackend();

    let settled = false;
    const response = call().then((value) => {
      settled = true;
      return value;
    });

    await vi.advanceTimersByTimeAsync(8_000 + 1);
    expect(settled).toBe(false);

    await vi.advanceTimersByTimeAsync(CATALOG_TIMEOUT_MS);
    expect((await response).status).toBe(502);
  });

  it("늘어난 예산은 단일 왕복 기본값보다 커야 의미가 있다", () => {
    // 이 값이 기본값 이하로 되돌아오면 위 시험이 통과해도 장애는 돌아온다.
    expect(CATALOG_TIMEOUT_MS).toBeGreaterThan(8_000);
  });
});
