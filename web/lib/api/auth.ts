import {
  AuthSessionResponseSchema,
  type AuthSessionResponse,
} from "@/lib/api/contracts";

let bootstrapPromise: Promise<AuthSessionResponse> | null = null;

async function parseSession(response: Response): Promise<AuthSessionResponse> {
  if (!response.ok) {
    throw new Error(`세션을 준비하지 못했습니다. (${response.status})`);
  }
  return AuthSessionResponseSchema.parse(await response.json());
}

async function bootstrapSession(): Promise<AuthSessionResponse> {
  const current = await fetch("/api/proxy/auth/session", {
    method: "GET",
    cache: "no-store",
  });
  if (current.ok) return parseSession(current);
  if (current.status !== 401) return parseSession(current);

  const created = await fetch("/api/proxy/auth/session", {
    method: "POST",
    cache: "no-store",
  });
  return parseSession(created);
}

export async function ensureAuthSession(): Promise<AuthSessionResponse> {
  if (bootstrapPromise) return bootstrapPromise;

  const pending = bootstrapSession();
  bootstrapPromise = pending;
  try {
    return await pending;
  } finally {
    if (bootstrapPromise === pending) bootstrapPromise = null;
  }
}

export function resetAuthSessionCacheForTests(): void {
  bootstrapPromise = null;
}

export async function deleteAnonymousAccount(): Promise<void> {
  const response = await fetch("/api/proxy/auth/account", {
    method: "DELETE",
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`개인정보를 삭제하지 못했습니다. (${response.status})`);
  }
  bootstrapPromise = null;
}
