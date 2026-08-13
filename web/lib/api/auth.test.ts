import { afterEach, describe, expect, it, vi } from "vitest";
import {
  deleteAnonymousAccount,
  ensureAuthSession,
  resetAuthSessionCacheForTests,
} from "@/lib/api/auth";
import { forwardedSessionCookie } from "@/lib/api/server-auth";

const SESSION = {
  authenticated: true,
  user_id: "742e91d5-2c31-45da-a13c-d76344a9815e",
  kind: "anonymous",
  expires_at: "2026-09-12T06:00:00Z",
};

afterEach(() => {
  resetAuthSessionCacheForTests();
  vi.unstubAllGlobals();
});

describe("browser session bootstrap", () => {
  it("기존 세션이 없으면 한 번 생성하고 응답 계약을 검증한다", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response("", { status: 401 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify(SESSION), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await expect(ensureAuthSession()).resolves.toEqual(SESSION);
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/proxy/auth/session",
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/proxy/auth/session",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("유효한 기존 세션은 새로 만들지 않는다", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(SESSION), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await ensureAuthSession();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("동시에 시작된 요청은 하나의 세션 확인만 공유한다", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(SESSION), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await Promise.all([ensureAuthSession(), ensureAuthSession()]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("server cookie forwarding", () => {
  it("FinShield 세션 쿠키만 백엔드로 전달한다", () => {
    const request = new Request("http://localhost/api/proxy/profiles", {
      headers: {
        cookie: "theme=dark; finshield_session=opaque-token; analytics=abc",
      },
    });

    expect(forwardedSessionCookie(request)).toEqual({
      Cookie: "finshield_session=opaque-token",
    });
  });

  it("세션 쿠키가 없으면 다른 쿠키를 전달하지 않는다", () => {
    const request = new Request("http://localhost", {
      headers: { cookie: "theme=dark" },
    });
    expect(forwardedSessionCookie(request)).toEqual({});
  });
});

describe("anonymous account deletion", () => {
  it("deletes the server account through the same-origin proxy", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(null, { status: 204 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(deleteAnonymousAccount()).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/proxy/auth/account",
      expect.objectContaining({ method: "DELETE", cache: "no-store" }),
    );
  });

  it("reports a server-side deletion failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 503 })),
    );

    await expect(deleteAnonymousAccount()).rejects.toThrow("503");
  });
});
