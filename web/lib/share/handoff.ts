import { ANALYZE_TEXT_MAX_LENGTH } from "@/lib/api/contracts";

/**
 * Android 공유 시트로 들어온 내용을 `/check` 입력창까지 나르는 방법.
 *
 * 왜 쿼리스트링이 아닌가. 공유되는 것은 사용자가 방금 받은 문자 원문이고, 이
 * 제품에서 가장 민감한 데이터다. URL 에 실으면 브라우저 방문 기록, Caddy·Next
 * 액세스 로그, 그리고 이후 요청의 Referer 에 그대로 남는다. 로그에 금융 원문을
 * 남기지 않는다는 규칙(`adr/0004`, `docs/27`)과 정면으로 충돌한다. 그래서
 * manifest 의 share_target 은 POST 이고, 원문은 본문으로만 온다.
 *
 * 그런데 POST 로 받은 페이지는 새로고침하면 재전송 경고가 뜨고 주소창에는
 * `/check/shared` 가 남는다. 그래서 받은 즉시 sessionStorage 로 옮기고 `/check`
 * 로 replace 한다. 이 파일은 그 인계 과정의 순수 함수만 담는다 - 라우트
 * 핸들러와 브라우저 스크립트가 같은 형식을 봐야 하기 때문이다.
 */

export const SHARE_HANDOFF_KEY = "finshield:share:pending";

/** 인계 문서 안에서 payload 를 담는 스크립트 태그의 id. */
export const SHARE_PAYLOAD_ELEMENT_ID = "finshield-share-payload";

export type SharedFields = {
  title?: string | null;
  text?: string | null;
  url?: string | null;
};

/**
 * 공유 시트가 준 세 칸을 분석에 넣을 한 덩어리로 합친다.
 *
 * 앱마다 어디에 무엇을 넣는지가 다르다. 문자 앱은 보통 본문을 `text` 에 넣고,
 * 브라우저는 `url` 과 페이지 제목을 나눠 보낸다. 본문 끝에 링크를 이미 붙여
 * 보내는 앱도 있어서, 같은 링크가 두 번 들어가지 않게 한다.
 *
 * 링크는 버리지 않고 그대로 넘긴다. 분석에 필요한 신호이고, 서버가 그 주소를
 * 열어보지는 않는다 (`CLAUDE.md` — 사용자 URL 은 적대적으로 취급).
 */
export function composeSharedText(fields: SharedFields): string {
  const text = (fields.text ?? "").trim();
  const url = (fields.url ?? "").trim();
  const title = (fields.title ?? "").trim();

  const parts: string[] = [];
  if (text) parts.push(text);
  if (url && !text.includes(url)) parts.push(url);

  // 제목만 온 경우에만 제목을 쓴다. 본문이 있는데 제목까지 붙이면 브라우저
  // 공유에서 페이지 제목이 메시지 원문인 것처럼 섞인다.
  if (parts.length === 0 && title) parts.push(title);

  return parts.join("\n").slice(0, ANALYZE_TEXT_MAX_LENGTH);
}

/**
 * `<script type="application/json">` 태그 안에서 문서를 깨뜨릴 수 있는 문자들.
 *
 * `</script>` 가 그대로 들어가면 파서가 거기서 태그를 닫아버린다. 공유 내용은
 * 외부에서 들어온 값이므로 `<`, `>`, `&` 를 막는다. U+2028·U+2029 는 JSON 에서는
 * 합법이지만 오래된 파서가 줄바꿈으로 읽는다.
 */
const UNSAFE_IN_SCRIPT_TAG = /[<>&\u2028\u2029]/g;

function escapeForScriptTag(value: unknown): string {
  return JSON.stringify(value).replace(
    UNSAFE_IN_SCRIPT_TAG,
    (character) =>
      "\\u" + character.charCodeAt(0).toString(16).padStart(4, "0"),
  );
}

/**
 * 공유 POST 에 대한 응답 문서.
 *
 * 인라인 스크립트를 쓰지 않는다. CSP 에 `'unsafe-inline'` 이 아직 남아 있긴
 * 하지만(`next.config.ts`), 외부에서 들어온 문자열이 실행 문맥 근처에 놓이는
 * 구조 자체를 만들지 않는다. payload 는 실행되지 않는 JSON 태그에 담고, 옮기는
 * 일은 정적 파일 `/share-handoff.js` 가 한다.
 */
export function buildHandoffDocument(text: string): string {
  const payload = escapeForScriptTag({ key: SHARE_HANDOFF_KEY, text });

  return shell({
    title: "확인 화면으로 옮기는 중",
    head: `<script type="application/json" id="${SHARE_PAYLOAD_ELEMENT_ID}">${payload}</script>
<script src="/share-handoff.js" defer></script>`,
    body: `<p>받은 내용을 확인 화면으로 옮기고 있습니다.</p>
<noscript><p><a href="/check">확인 화면 열기</a></p></noscript>`,
  });
}

/**
 * 공유를 받아들이지 못했을 때 보여줄 문서.
 *
 * 조용히 빈 입력창으로 보내지 않는다. 사용자는 공유 버튼을 눌렀고, 아무 설명
 * 없이 빈 화면이 뜨면 앱이 고장 난 것으로 읽는다. 받지 못한 내용이 무엇이었는지는
 * 되풀이하지 않는다 - 서버가 그것을 다시 화면에 그릴 이유가 없다.
 */
export function buildShareNoticeDocument(message: string): string {
  return shell({
    title: "확인 화면 열기",
    body: `<p>${escapeHtmlText(message)}</p>
<p><a href="/check">직접 붙여넣어 확인하기</a></p>`,
  });
}

function escapeHtmlText(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/**
 * 두 문서가 공유하는 껍데기.
 *
 * Tailwind 도 globals.css 도 쓰지 않는다. 이 문서들은 App Router 바깥에서
 * 만들어지는 데다, 화면에 머무는 시간이 한 프레임 남짓이다. 스타일시트를
 * 기다리게 하면 그 사이에 흰 화면만 보인다.
 */
function shell({
  title,
  head = "",
  body,
}: {
  title: string;
  head?: string;
  body: string;
}): string {
  return `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<meta name="theme-color" content="#1f3a5f">
<title>${title} · FinShield</title>
${head}
</head>
<body style="margin:0;padding:24px;font:16px/1.6 system-ui,-apple-system,sans-serif;color:#16191f;background:#ffffff">
${body}
</body>
</html>
`;
}
