import { NextResponse } from "next/server";

/**
 * Route Handler 가 백엔드를 부르기 전에 들어온 요청에서 꺼내는 것들.
 *
 * 서버 전용 모듈이다. 클라이언트 컴포넌트에서 import 하지 않는다.
 */

const SESSION_COOKIE_NAME = "finshield_session";

const FORWARDED_FOR_HEADER = "x-forwarded-for";

/** 백엔드 `MAX_TRUSTED_PROXY_HOPS` 와 같은 값. 그보다 왼쪽은 쓰이지 않는다. */
const MAX_FORWARDED_ENTRIES = 8;

/** IPv4/IPv6(존 ID·대괄호·포트 포함)와 `unknown` 토큰이 들어갈 수 있는 문자만. */
const SAFE_FORWARDED_ENTRY = /^[\w.:%[\]-]{1,64}$/;

export function forwardedSessionCookie(request: Request): Record<string, string> {
  const cookieHeader = request.headers.get("cookie");
  if (!cookieHeader) return {};

  const sessionCookie = cookieHeader
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${SESSION_COOKIE_NAME}=`));

  return sessionCookie ? { Cookie: sessionCookie } : {};
}

/**
 * 들어온 `X-Forwarded-For` 체인을 백엔드로 넘길 값으로 다듬는다.
 *
 * 항목을 새로 덧붙이지 않는다. Next.js Route Handler 는 TCP peer 를 볼 수
 * 없어서 덧붙일 정확한 주소가 없고, 실제 클라이언트 주소는 이미 Caddy 가
 * 맨 오른쪽에 붙여서 보냈기 때문이다. 그래서 백엔드는
 * `FINSHIELD_TRUSTED_PROXY_HOPS=1` 로 맨 오른쪽 항목을 고른다.
 *
 * 다듬는 규칙은 두 가지뿐이고, 둘 다 **오른쪽 기준 홉 인덱스를 흔들지 않는
 * 것**이 조건이다.
 *  - 오른쪽 8개만 남긴다. 왼쪽은 클라이언트가 임의로 채워 보낼 수 있고,
 *    백엔드가 그만큼 왼쪽을 볼 일도 없다. 잘라도 오른쪽 순서는 그대로다.
 *  - 주소일 수 없는 항목은 버리지 않고 `unknown` 으로 바꾼다. 버리면 뒤
 *    항목들이 한 칸씩 밀려서 위조된 항목이 client 로 뽑힌다.
 */
export function trimForwardedChain(raw: string | null | undefined): string | null {
  if (!raw) return null;

  const entries = raw
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean)
    .map((entry) => (SAFE_FORWARDED_ENTRY.test(entry) ? entry : "unknown"));

  if (entries.length === 0) return null;
  return entries.slice(-MAX_FORWARDED_ENTRIES).join(", ");
}

/**
 * 백엔드 호출에 붙일 헤더.
 *
 * 클라이언트 주소는 **모든** 프록시 경로에서 넘긴다. 한 곳이라도 빠뜨리면
 * 그 엔드포인트만 모든 사용자가 web 컨테이너 하나로 묶여서, rate limit 이
 * 있는데도 한 명이 전체를 막을 수 있다.
 *
 * 세션 쿠키는 반대로 필요한 경로에서만 명시적으로 켠다.
 */
export function backendHeaders(
  request: Request,
  options: { session?: boolean } = {},
): Record<string, string> {
  const headers: Record<string, string> = {};

  const forwarded = trimForwardedChain(request.headers.get(FORWARDED_FOR_HEADER));
  if (forwarded) headers["X-Forwarded-For"] = forwarded;

  if (options.session) Object.assign(headers, forwardedSessionCookie(request));
  return headers;
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
