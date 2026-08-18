import { describe, expect, it } from "vitest";
import { GET, POST } from "@/app/check/shared/route";

function sharePost(fields: Record<string, string>): Request {
  const form = new FormData();
  for (const [name, value] of Object.entries(fields)) form.append(name, value);
  return new Request("http://localhost/check/shared", {
    method: "POST",
    body: form,
  });
}

const BOUNDARY = "----finshieldsharetest";

/**
 * multipart 본문을 직접 만든다.
 *
 * `FormData` 를 넘기면 undici 가 본문을 비동기 제너레이터로 흘려보내는데, 크기
 * 상한에 걸려 중간에 스트림을 끊으면 그 제너레이터가 닫힌 스트림에 계속 쓰려다
 * unhandled rejection 을 낸다. 테스트 러너 안에서만 나는 문제지만, 상한 동작을
 * 확인하려다 엉뚱한 에러를 보게 되므로 여기서는 바이트를 직접 만든다.
 */
function rawSharePost(fields: Record<string, string>): Request {
  const body =
    Object.entries(fields)
      .map(
        ([name, value]) =>
          `--${BOUNDARY}\r\nContent-Disposition: form-data; name="${name}"\r\n\r\n${value}\r\n`,
      )
      .join("") + `--${BOUNDARY}--\r\n`;

  return new Request("http://localhost/check/shared", {
    method: "POST",
    headers: { "content-type": `multipart/form-data; boundary=${BOUNDARY}` },
    body,
  });
}

describe("POST /check/shared", () => {
  it("공유된 내용을 인계 문서로 돌려준다", async () => {
    const response = await POST(
      sharePost({ text: "급여계좌 등록이 필요합니다", url: "https://example.test/a" }),
    );
    const body = await response.text();

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toContain("text/html");
    expect(body).toContain("급여계좌 등록이 필요합니다");
    expect(body).toContain("https://example.test/a");
    expect(body).toContain('<script src="/share-handoff.js" defer></script>');
  });

  it("받은 문자 원문이 담긴 문서를 캐시하지 않게 한다", async () => {
    const response = await POST(sharePost({ text: "확인 바랍니다" }));
    expect(response.headers.get("cache-control")).toContain("no-store");
    expect(response.headers.get("x-robots-tag")).toContain("noindex");
  });

  it("확인할 문구가 없으면 안내 문서를 준다", async () => {
    const response = await POST(sharePost({ text: "   " }));
    const body = await response.text();

    expect(response.status).toBe(200);
    expect(body).toContain("찾지 못했습니다");
    expect(body).toContain('href="/check"');
  });

  it("너무 긴 공유는 413 으로 끊고 붙여넣기를 안내한다", async () => {
    const response = await POST(rawSharePost({ text: "가".repeat(60_000) }));
    const body = await response.text();

    expect(response.status).toBe(413);
    expect(body).toContain("너무 길어");
    expect(body).toContain('href="/check"');
  });

  it("multipart 가 아닌 본문은 400 이다", async () => {
    const response = await POST(
      new Request("http://localhost/check/shared", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: '{"text":"확인"}',
      }),
    );

    expect(response.status).toBe(400);
    expect(await response.text()).toContain('href="/check"');
  });

  it("백엔드를 부르거나 상태를 바꾸지 않는다", async () => {
    // 교차 출처 POST 를 그대로 받는 엔드포인트다. 그게 안전한 이유는 이 요청이
    // 아무것도 바꾸지 않기 때문이므로, 쿠키를 세우지 않는다는 것을 고정해 둔다.
    const response = await POST(sharePost({ text: "확인" }));
    expect(response.headers.get("set-cookie")).toBeNull();
  });
});

describe("GET /check/shared", () => {
  it("빈 확인 화면으로 돌려보낸다", () => {
    const response = GET(new Request("http://localhost/check/shared"));
    expect(response.status).toBe(303);
    expect(response.headers.get("location")).toBe("http://localhost/check");
  });
});
