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
