import { NextResponse } from "next/server";
import { backendBaseUrl } from "@/lib/api/client";
import { forwardedSessionCookie } from "@/lib/api/server-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function DELETE(request: Request) {
  let upstream: Response;
  try {
    upstream = await fetch(`${backendBaseUrl()}/api/v1/auth/account`, {
      method: "DELETE",
      headers: forwardedSessionCookie(request),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json(
      { message: "개인정보 삭제 서버에 연결하지 못했습니다." },
      { status: 502 },
    );
  }

  const response = upstream.status === 204
    ? new NextResponse(null, { status: 204 })
    : new NextResponse(await upstream.text(), {
        status: upstream.status,
        headers: {
          "Content-Type": upstream.headers.get("content-type") ?? "application/json",
        },
      });
  const setCookie = upstream.headers.get("set-cookie");
  if (setCookie) response.headers.set("Set-Cookie", setCookie);
  return response;
}
