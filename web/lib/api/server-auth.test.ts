import { describe, expect, it } from "vitest";
import {
  backendHeaders,
  rejectCrossSiteRequest,
  trimForwardedChain,
} from "./server-auth";

describe("rejectCrossSiteRequest", () => {
  it("accepts a same-origin state-changing request", () => {
    const request = new Request("http://localhost:3000/api/proxy/auth/session", {
      method: "POST",
      headers: { Origin: "http://localhost:3000", "Sec-Fetch-Site": "same-origin" },
    });

    expect(rejectCrossSiteRequest(request)).toBeNull();
  });

  it("rejects missing and cross-site origins", () => {
    const missing = new Request("http://localhost:3000/api/proxy/auth/session", {
      method: "POST",
    });
    const crossSite = new Request("http://localhost:3000/api/proxy/auth/session", {
      method: "POST",
      headers: { Origin: "https://attacker.example", "Sec-Fetch-Site": "cross-site" },
    });

    expect(rejectCrossSiteRequest(missing)?.status).toBe(403);
    expect(rejectCrossSiteRequest(crossSite)?.status).toBe(403);
  });

  it("fails closed when the configured origin is malformed", () => {
    const previous = process.env.FINSHIELD_ALLOWED_ORIGINS;
    process.env.FINSHIELD_ALLOWED_ORIGINS = "not a url";
    try {
      const request = new Request("http://localhost:3000/api/proxy/auth/session", {
        method: "POST",
        headers: { Origin: "http://localhost:3000" },
      });
      expect(rejectCrossSiteRequest(request)?.status).toBe(403);
    } finally {
      if (previous === undefined) delete process.env.FINSHIELD_ALLOWED_ORIGINS;
      else process.env.FINSHIELD_ALLOWED_ORIGINS = previous;
    }
  });
});

describe("trimForwardedChain", () => {
  it("헤더가 없으면 아무것도 만들지 않는다", () => {
    expect(trimForwardedChain(null)).toBeNull();
    expect(trimForwardedChain("")).toBeNull();
    expect(trimForwardedChain(" , ,")).toBeNull();
  });

  it("Caddy가 붙인 실제 주소를 맨 오른쪽에 그대로 남긴다", () => {
    // 클라이언트가 미리 적어 보낸 값(198.51.100.9)이 왼쪽으로 밀려 있다.
    expect(trimForwardedChain("198.51.100.9, 203.0.113.7")).toBe(
      "198.51.100.9, 203.0.113.7",
    );
  });

  it("우리 홉을 덧붙이지 않는다", () => {
    // 덧붙이면 백엔드가 hops=1 로 web 컨테이너를 client 로 고른다.
    const trimmed = trimForwardedChain("203.0.113.7");
    expect(trimmed).toBe("203.0.113.7");
    expect(trimmed?.split(",")).toHaveLength(1);
  });

  it("체인이 길면 오른쪽 8개만 남긴다", () => {
    const chain = Array.from({ length: 40 }, (_, index) => `10.0.0.${index}`);
    const trimmed = trimForwardedChain(chain.join(", "));

    expect(trimmed?.split(", ")).toHaveLength(8);
    expect(trimmed?.endsWith("10.0.0.39")).toBe(true);
  });

  it("주소일 수 없는 항목은 버리지 않고 자리를 지킨 채 unknown 으로 바꾼다", () => {
    // 버리면 뒤 항목이 한 칸씩 밀려 위조된 값이 client 로 뽑힌다.
    expect(trimForwardedChain("<script>, 203.0.113.7")).toBe(
      "unknown, 203.0.113.7",
    );
    expect(trimForwardedChain(`${"9".repeat(200)}, 203.0.113.7`)).toBe(
      "unknown, 203.0.113.7",
    );
  });

  it("IPv6 와 포트 표기를 그대로 넘긴다", () => {
    expect(trimForwardedChain("[2001:db8::1]:443")).toBe("[2001:db8::1]:443");
    expect(trimForwardedChain("2001:db8::1%eth0")).toBe("2001:db8::1%eth0");
  });
});

describe("backendHeaders", () => {
  function requestWith(headers: Record<string, string>): Request {
    return new Request("http://localhost:3000/api/proxy/analyze", {
      method: "POST",
      headers,
    });
  }

  it("클라이언트 주소를 백엔드로 넘긴다", () => {
    expect(
      backendHeaders(requestWith({ "X-Forwarded-For": "198.51.100.9, 203.0.113.7" })),
    ).toEqual({ "X-Forwarded-For": "198.51.100.9, 203.0.113.7" });
  });

  it("기본으로는 세션 쿠키를 넘기지 않는다", () => {
    const request = requestWith({
      "X-Forwarded-For": "203.0.113.7",
      cookie: "finshield_session=opaque-token",
    });

    expect(backendHeaders(request)).toEqual({ "X-Forwarded-For": "203.0.113.7" });
    expect(backendHeaders(request, { session: true })).toEqual({
      "X-Forwarded-For": "203.0.113.7",
      Cookie: "finshield_session=opaque-token",
    });
  });

  it("주소를 알 수 없으면 헤더를 만들지 않는다", () => {
    // 백엔드가 peer 로 되돌아가 공용 bucket 으로 묶는다. 위조된 값을 지어내지 않는다.
    expect(backendHeaders(requestWith({}))).toEqual({});
  });

  it("fetch 가 거절하지 않는 헤더 값을 만든다", () => {
    const headers = backendHeaders(
      requestWith({ "X-Forwarded-For": "203.0.113.7" }),
    );

    expect(() => new Headers(headers)).not.toThrow();
  });
});
