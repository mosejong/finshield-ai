import { describe, expect, it } from "vitest";
import { ANALYZE_TEXT_MAX_LENGTH } from "@/lib/api/contracts";
import {
  SHARE_HANDOFF_KEY,
  SHARE_PAYLOAD_ELEMENT_ID,
  buildHandoffDocument,
  buildShareNoticeDocument,
  composeSharedText,
} from "@/lib/share/handoff";

/** 인계 문서에서 JSON payload 만 꺼낸다. */
function payloadOf(document: string): { key: string; text: string } {
  const opening = `<script type="application/json" id="${SHARE_PAYLOAD_ELEMENT_ID}">`;
  const start = document.indexOf(opening);
  expect(start).toBeGreaterThanOrEqual(0);
  const from = start + opening.length;
  const to = document.indexOf("</script>", from);
  return JSON.parse(document.slice(from, to));
}

describe("composeSharedText", () => {
  it("본문만 온 경우 그대로 쓴다", () => {
    expect(composeSharedText({ text: "  급여계좌 등록이 필요합니다  " })).toBe(
      "급여계좌 등록이 필요합니다",
    );
  });

  it("본문과 링크가 따로 오면 줄을 나눠 합친다", () => {
    expect(
      composeSharedText({ text: "확인 바랍니다", url: "https://example.test/a" }),
    ).toBe("확인 바랍니다\nhttps://example.test/a");
  });

  it("본문에 이미 들어 있는 링크를 두 번 붙이지 않는다", () => {
    const text = "확인: https://example.test/a 로 접속하세요";
    expect(composeSharedText({ text, url: "https://example.test/a" })).toBe(text);
  });

  it("본문이 있으면 제목은 쓰지 않는다", () => {
    expect(
      composeSharedText({ title: "네이버 뉴스", text: "본문 내용" }),
    ).toBe("본문 내용");
  });

  it("제목만 온 경우에는 제목이라도 넘긴다", () => {
    expect(composeSharedText({ title: "긴급 안내" })).toBe("긴급 안내");
  });

  it("아무 칸도 채워지지 않으면 빈 문자열이다", () => {
    expect(composeSharedText({})).toBe("");
    expect(composeSharedText({ text: "   ", url: null, title: undefined })).toBe("");
  });

  it("분석 상한을 넘는 내용은 잘라서 넘긴다", () => {
    const shared = composeSharedText({ text: "가".repeat(ANALYZE_TEXT_MAX_LENGTH + 500) });
    // 입력창·전송 스키마와 같은 값을 봐야 한다. 여기서만 길면 붙여넣기는 되고
    // 전송에서만 거부된다.
    expect(shared).toHaveLength(ANALYZE_TEXT_MAX_LENGTH);
  });
});

describe("buildHandoffDocument", () => {
  it("원문을 그대로 복원할 수 있는 payload 를 담는다", () => {
    const text = "계좌 등록이 필요합니다\nhttps://example.test/a";
    expect(payloadOf(buildHandoffDocument(text))).toEqual({
      key: SHARE_HANDOFF_KEY,
      text,
    });
  });

  it("공유 내용의 </script> 로 문서가 끊기지 않는다", () => {
    const hostile = '</script><script>alert("x")</script>';
    const document = buildHandoffDocument(hostile);

    // 스크립트 태그는 payload 용과 인계 스크립트용 둘뿐이어야 한다.
    expect(document.match(/<\/script>/g)).toHaveLength(2);
    expect(document).not.toContain('<script>alert("x")');
    // 그러면서 원문은 손실 없이 전달된다.
    expect(payloadOf(document).text).toBe(hostile);
  });

  it("줄바꿈으로 오해될 수 있는 유니코드 구분자도 이스케이프한다", () => {
    // 소스에 직접 넣으면 눈에 보이지 않아 나중에 지워진다. 코드포인트로 만든다.
    const text = `a${String.fromCharCode(0x2028)}b${String.fromCharCode(0x2029)}c`;
    const document = buildHandoffDocument(text);

    expect(document).toContain("\\u2028");
    expect(document).toContain("\\u2029");
    expect(payloadOf(document).text).toBe(text);
  });

  it("스크립트가 꺼져 있어도 확인 화면으로 갈 길을 남긴다", () => {
    const document = buildHandoffDocument("내용");
    expect(document).toContain("<noscript>");
    expect(document).toContain('href="/check"');
    expect(document).toContain('<script src="/share-handoff.js" defer></script>');
  });

  it("색인되지 않게 표시한다", () => {
    expect(buildHandoffDocument("내용")).toContain('name="robots" content="noindex"');
  });
});

describe("buildShareNoticeDocument", () => {
  it("안내 문구를 HTML 로 해석되지 않게 담는다", () => {
    const document = buildShareNoticeDocument("<b>길어요</b>");
    expect(document).toContain("&lt;b&gt;길어요&lt;/b&gt;");
    expect(document).not.toContain("<b>길어요</b>");
  });

  it("직접 붙여넣을 수 있는 길을 준다", () => {
    expect(buildShareNoticeDocument("안내")).toContain('href="/check"');
  });
});
