import { NextResponse } from "next/server";
import { readLimitedBody } from "@/lib/api/request-body";
import {
  buildHandoffDocument,
  buildShareNoticeDocument,
  composeSharedText,
} from "@/lib/share/handoff";

/**
 * manifest 의 share_target 이 가리키는 곳. 안드로이드 공유 시트가 여기로 POST 한다.
 *
 * 페이지가 아니라 Route Handler 인 이유는 App Router 의 `page.tsx` 가 POST 를
 * 받지 못하기 때문이다. 그래서 응답 HTML 을 직접 만든다.
 *
 * CSRF 를 검사하지 않는 것은 빠뜨린 게 아니라 이 엔드포인트의 성격이다. 공유
 * 대상은 정의상 다른 앱이 보내는 교차 출처 POST 이고, `Sec-Fetch-Site` 는
 * `cross-site` 로 온다. 대신 이 핸들러는 CSRF 로 악용될 여지 자체를 없애 둔다.
 *   - 상태를 바꾸지 않는다. 쓰기도, 세션 변경도 없다.
 *   - 백엔드를 부르지 않는다. 분석 요청은 사용자가 `/check` 에서 눌러야 나간다.
 *   - 받은 값을 저장하지 않는다. 그대로 응답 문서에 담아 브라우저로 돌려준다.
 * 즉 공격자가 이 주소로 요청을 유도해도 얻는 것은 자기가 보낸 문자열이 담긴
 * HTML 한 장뿐이고, 그마저 `no-store` 로 어디에도 남지 않는다.
 *
 * 받은 내용은 로그로 남기지 않는다 (docs/12 log leakage, adr/0004).
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** 공유 본문 상한. 원문 10,000자에 multipart 경계와 UTF-8 3바이트를 얹은 여유값. */
const MAX_SHARE_BODY_BYTES = 64 * 1024;

export async function POST(request: Request): Promise<Response> {
  const body = await readLimitedBody(request, MAX_SHARE_BODY_BYTES);
  if (!body.ok) {
    return html(
      buildShareNoticeDocument(
        body.reason === "too_large"
          ? "공유된 내용이 너무 길어 받지 못했습니다. 확인이 필요한 부분만 붙여넣어 주세요."
          : "공유된 내용을 읽지 못했습니다. 확인이 필요한 부분을 붙여넣어 주세요.",
      ),
      body.reason === "too_large" ? 413 : 400,
    );
  }

  let form: FormData;
  try {
    // 이미 다 읽은 바이트를 파싱만 다시 시킨다. `request.formData()` 를 바로
    // 부르면 위의 크기 상한을 건너뛰게 된다.
    form = await new Response(body.bytes, {
      headers: {
        "content-type":
          request.headers.get("content-type") ?? "application/octet-stream",
      },
    }).formData();
  } catch {
    return html(
      buildShareNoticeDocument(
        "공유된 내용을 읽지 못했습니다. 확인이 필요한 부분을 붙여넣어 주세요.",
      ),
      400,
    );
  }

  const text = composeSharedText({
    title: field(form, "title"),
    text: field(form, "text"),
    url: field(form, "url"),
  });

  if (!text) {
    return html(
      buildShareNoticeDocument("공유된 내용에서 확인할 문구를 찾지 못했습니다."),
    );
  }

  return html(buildHandoffDocument(text));
}

/**
 * 주소창에 직접 치거나 뒤로 가기로 돌아온 경우. 빈 확인 화면으로 보낸다.
 * 여기에 머물러 봐야 보여줄 것이 없다.
 */
export function GET(request: Request): Response {
  return NextResponse.redirect(new URL("/check", request.url), 303);
}

/** 파일이 왔거나 칸이 비었으면 없는 것으로 본다. manifest 는 파일을 요청하지 않는다. */
function field(form: FormData, name: string): string | null {
  const value = form.get(name);
  return typeof value === "string" ? value : null;
}

function html(document: string, status = 200): Response {
  return new Response(document, {
    status,
    headers: {
      "content-type": "text/html; charset=utf-8",
      // 사용자가 받은 문자 원문이 담긴 문서다. 뒤로 가기 캐시에도 남기지 않는다.
      "cache-control": "no-store, must-revalidate",
      "x-robots-tag": "noindex, nofollow",
    },
  });
}
