import { NextResponse } from "next/server";

const SESSION_COOKIE_NAME = "finshield_session";

export function forwardedSessionCookie(request: Request): HeadersInit {
  const cookieHeader = request.headers.get("cookie");
  if (!cookieHeader) return {};

  const sessionCookie = cookieHeader
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${SESSION_COOKIE_NAME}=`));

  return sessionCookie ? { Cookie: sessionCookie } : {};
}

export function rejectCrossSiteRequest(request: Request): NextResponse | null {
  const origin = request.headers.get("origin");
  const fetchSite = request.headers.get("sec-fetch-site");
  if (!origin || fetchSite === "cross-site") {
    return csrfFailure();
  }

  let normalizedOrigin: string;
  try {
    normalizedOrigin = new URL(origin).origin;
  } catch {
    return csrfFailure();
  }

  const configuredOrigins = (process.env.FINSHIELD_ALLOWED_ORIGINS ?? "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  const allowedOrigins = new Set<string>();
  for (const value of configuredOrigins.length > 0
    ? configuredOrigins
    : [new URL(request.url).origin]) {
    try {
      allowedOrigins.add(new URL(value).origin);
    } catch {
      // An invalid configured origin must fail closed, not widen access.
    }
  }

  return allowedOrigins.has(normalizedOrigin) ? null : csrfFailure();
}

function csrfFailure(): NextResponse {
  return NextResponse.json(
    {
      message:
        "\uc694\uccad \ucd9c\ucc98\ub97c \ud655\uc778\ud560 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4. \ud654\uba74\uc744 \uc0c8\ub85c\uace0\uce68\ud55c \ub4a4 \ub2e4\uc2dc \uc2dc\ub3c4\ud574 \uc8fc\uc138\uc694.",
    },
    { status: 403 },
  );
}
