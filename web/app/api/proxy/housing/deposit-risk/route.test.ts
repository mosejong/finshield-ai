import { afterEach, describe, expect, it, vi } from "vitest";
import { POST } from "@/app/api/proxy/housing/deposit-risk/route";

const VALID_BODY = {
  stage: "balance_paid",
  deposit_krw: 200_000_000,
  property_price_krw: 300_000_000,
  senior_lien_krw: null,
  completed_checks: ["registry_checked"],
  move_in_reported_on: null,
};

function proxyPost(body: unknown, headers: Record<string, string> = {}): Request {
  return new Request("http://localhost/api/proxy/housing/deposit-risk", {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
}

function stubBackend(body: unknown, status: number) {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe("POST /api/proxy/housing/deposit-risk", () => {
  it("백엔드가 입력을 거부하면(422) 서버 장애(502)가 아니라 400 으로 옮긴다", async () => {
    /*
      전입신고일이 미래인 경우가 여기로 온다. "오늘" 의 기준은 KST 를 아는
      백엔드에 있어서 이 프록시의 스키마는 통과시킨다. 그 거부를 502 로 덮으면
      사용자는 고칠 수 있는 값을 앞에 두고 재시도만 반복하게 된다.
    */
    stubBackend({ detail: "move_in_reported_on must not be in the future" }, 422);

    const response = await POST(
      proxyPost({ ...VALID_BODY, move_in_reported_on: "2099-01-01" }),
    );

    expect(response.status).toBe(400);
    const body = await response.json();
    expect(body.hint).toContain("전입신고일");
  });

  it("백엔드 장애는 그대로 502 로 알린다", async () => {
    stubBackend({ detail: "boom" }, 500);

    const response = await POST(proxyPost(VALID_BODY));

    expect(response.status).toBe(502);
    expect((await response.json()).message).toContain("마치지 못했습니다");
  });

  it("스키마에 맞지 않는 입력은 백엔드까지 가지 않는다", async () => {
    const fetchMock = stubBackend({}, 200);

    const response = await POST(proxyPost({ ...VALID_BODY, deposit_krw: -1 }));

    expect(response.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("세션 쿠키를 백엔드로 넘기지 않는다", async () => {
    // 계약을 앞둔 사람에게 로그인을 먼저 요구하지 않는 기능이다. 세션을 함께
    // 보내면 이 점검이 계정에 딸린 기록처럼 취급될 여지가 생긴다.
    const fetchMock = stubBackend({ risk_level: "low" }, 200);

    await POST(proxyPost(VALID_BODY, { cookie: "finshield_session=abc" }));

    const sent = new Headers(fetchMock.mock.calls[0][1].headers);
    expect(sent.get("cookie")).toBeNull();
  });
});
