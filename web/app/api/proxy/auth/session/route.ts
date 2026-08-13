import { NextResponse } from "next/server";
import { backendBaseUrl } from "@/lib/api/client";
import { forwardedSessionCookie, rejectCrossSiteRequest } from "@/lib/api/server-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function proxySession(request: Request, method: "GET" | "POST" | "DELETE") {
  let upstream: Response;
  try {
    upstream = await fetch(`${backendBaseUrl()}/api/v1/auth/session`, {
      method,
      headers: forwardedSessionCookie(request),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json(
      { message: "세션 서버에 연결하지 못했습니다." },
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

export function GET(request: Request) {
  return proxySession(request, "GET");
}

export function POST(request: Request) {
  const rejected = rejectCrossSiteRequest(request);
  if (rejected) return rejected;
  return proxySession(request, "POST");
}

export function DELETE(request: Request) {
  const rejected = rejectCrossSiteRequest(request);
  if (rejected) return rejected;
  return proxySession(request, "DELETE");
}
