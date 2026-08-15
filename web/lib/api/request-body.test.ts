import { afterEach, describe, expect, it } from "vitest";
import { maxProxyBodyBytes, readJsonBody } from "@/lib/api/request-body";

function jsonRequest(body: string, headers: Record<string, string> = {}): Request {
  return new Request("http://localhost/api/proxy/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body,
  });
}

afterEach(() => {
  delete process.env.FINSHIELD_MAX_REQUEST_BYTES;
});

describe("maxProxyBodyBytes", () => {
  it("백엔드 기본값과 같은 131072 를 쓴다", () => {
    expect(maxProxyBodyBytes()).toBe(131_072);
  });

  it("환경변수로 백엔드와 함께 올릴 수 있다", () => {
    process.env.FINSHIELD_MAX_REQUEST_BYTES = "262144";
    expect(maxProxyBodyBytes()).toBe(262_144);
  });

  it("범위를 벗어나거나 숫자가 아니면 기본값으로 돌아간다", () => {
    for (const value of ["0", "1024", "99999999", "많이", ""]) {
      process.env.FINSHIELD_MAX_REQUEST_BYTES = value;
      expect(maxProxyBodyBytes()).toBe(131_072);
    }
  });
});

describe("readJsonBody", () => {
  it("정상 본문은 파싱해서 넘긴다", async () => {
    const result = await readJsonBody(jsonRequest(JSON.stringify({ text: "안녕" })));
    expect(result.ok).toBe(true);
    if (result.ok) expect(result.value).toEqual({ text: "안녕" });
  });

  it("깨진 JSON 은 400 으로 돌려보낸다", async () => {
    const result = await readJsonBody(jsonRequest("{not json"));
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.response.status).toBe(400);
      await expect(result.response.json()).resolves.toEqual({
        message: "요청 형식이 올바르지 않습니다.",
      });
    }
  });

  it("빈 본문도 400 이다", async () => {
    const result = await readJsonBody(jsonRequest(""));
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.response.status).toBe(400);
  });

  it("상한을 넘는 본문은 413 이고, 실패를 400 으로 감추지 않는다", async () => {
    const result = await readJsonBody(
      jsonRequest(JSON.stringify({ text: "가".repeat(50_000) })),
      1_024,
    );
    expect(result.ok).toBe(false);
    if (!result.ok) {
      // 400 이면 사용자는 자기가 잘못 입력했다고 읽는다. 크기 문제는 크기로 말한다.
      expect(result.response.status).toBe(413);
      const body = await result.response.json();
      expect(body.message).toContain("너무 커서");
      // 바이트 수 같은 내부 값을 문구로 흘리지 않는다.
      expect(JSON.stringify(body)).not.toMatch(/\d{3,}/);
    }
  });

  it("Content-Length 만 보고도 먼저 끊는다", async () => {
    let pulled = 0;
    const stream = new ReadableStream<Uint8Array>({
      pull(controller) {
        pulled += 1;
        controller.enqueue(new TextEncoder().encode("x".repeat(64)));
      },
    });
    const request = new Request("http://localhost/api/proxy/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Content-Length": "999999" },
      body: stream,
      duplex: "half",
    } as RequestInit);

    const result = await readJsonBody(request, 1_024);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.response.status).toBe(413);
    // 런타임이 Request 를 만든 뒤 스스로 한 조각을 미리 당겨간다(우리가 읽지
    // 않아도 그렇다). 중요한 건 999999 바이트를 끝까지 받아내지 않았다는 것이다.
    // 64 바이트씩 다 읽었다면 pull 이 만 번 넘게 일어났을 것이다.
    expect(pulled).toBeLessThanOrEqual(1);
  });

  it("헤더가 없어도 흘러오는 바이트를 세서 도중에 끊는다", async () => {
    let pulled = 0;
    const stream = new ReadableStream<Uint8Array>({
      pull(controller) {
        pulled += 1;
        controller.enqueue(new TextEncoder().encode("x".repeat(256)));
      },
    });
    const request = new Request("http://localhost/api/proxy/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: stream,
      duplex: "half",
    } as RequestInit);

    const result = await readJsonBody(request, 1_024);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.response.status).toBe(413);
    // 상한을 넘긴 뒤로는 계속 받아주지 않는다. 무한 스트림인데도 끝났다.
    expect(pulled).toBeLessThanOrEqual(8);
  });

  it("여러 조각에 걸쳐 쪼개진 한글도 깨지지 않는다", async () => {
    const payload = new TextEncoder().encode(JSON.stringify({ text: "안녕하세요" }));
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        // UTF-8 한 글자 중간에서 자른다.
        for (let i = 0; i < payload.length; i += 1) {
          controller.enqueue(payload.slice(i, i + 1));
        }
        controller.close();
      },
    });
    const request = new Request("http://localhost/api/proxy/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: stream,
      duplex: "half",
    } as RequestInit);

    const result = await readJsonBody(request);
    expect(result.ok).toBe(true);
    if (result.ok) expect(result.value).toEqual({ text: "안녕하세요" });
  });
});
