import { describe, expect, it } from "vitest";
import { ApiError } from "./client";
import {
  rateLimitedFromUpstream,
  upstreamFailure,
  upstreamStatus,
} from "./proxy-response";

describe("upstreamStatus", () => {
  it("사용자가 알아야 의미가 있는 코드만 그대로 넘긴다", () => {
    for (const status of [401, 404, 413, 429, 503]) {
      expect(upstreamStatus(new ApiError("http", "", status))).toBe(status);
    }
  });

  it("나머지는 502 로 덮는다", () => {
    expect(upstreamStatus(new ApiError("http", "", 500))).toBe(502);
    expect(upstreamStatus(new ApiError("network", ""))).toBe(502);
    expect(upstreamStatus(new Error("boom"))).toBe(502);
  });
});

describe("upstreamFailure", () => {
  it("한도 초과를 502 로 덮지 않는다", async () => {
    const error = new ApiError("http", "", 429, { retryAfterSeconds: 42 });
    const response = upstreamFailure(error, "공식 상품 정보를 확인하지 못했습니다.");

    expect(response.status).toBe(429);
    expect(response.headers.get("Retry-After")).toBe("42");
    await expect(response.json()).resolves.toEqual({
      message: "요청이 많아 잠시 멈췄습니다.",
      hint: "42초 뒤에 다시 시도해 주세요.",
    });
  });

  it("기다릴 시간을 모르면 초를 지어내지 않는다", async () => {
    const response = upstreamFailure(new ApiError("http", "", 429), "무시됨");

    expect(response.headers.get("Retry-After")).toBeNull();
    await expect(response.json()).resolves.toMatchObject({
      hint: "잠시 후 다시 시도해 주세요.",
    });
  });

  it("그 밖의 실패는 경로별 문구를 그대로 쓴다", async () => {
    const response = upstreamFailure(
      new ApiError("http", "", 503),
      "공식 상품 정보를 확인하지 못했습니다.",
    );

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toEqual({
      message: "공식 상품 정보를 확인하지 못했습니다.",
    });
  });
});

describe("rateLimitedFromUpstream", () => {
  it("백엔드 영문 detail 을 사용자 문구로 바꾼다", async () => {
    const upstream = new Response(JSON.stringify({ detail: "too many requests" }), {
      status: 429,
      headers: { "Retry-After": "17" },
    });

    const response = rateLimitedFromUpstream(upstream);

    expect(response.status).toBe(429);
    expect(response.headers.get("Retry-After")).toBe("17");
    await expect(response.json()).resolves.toEqual({
      message: "요청이 많아 잠시 멈췄습니다.",
      hint: "17초 뒤에 다시 시도해 주세요.",
    });
  });
});
