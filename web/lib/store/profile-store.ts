"use client";

import { useEffect, useSyncExternalStore } from "react";
import { z } from "zod";
import { PersonaSchema, type FinancialProfile, type Persona } from "@/lib/api/contracts";
import {
  createProfile,
  deleteProfile,
  fetchProfile,
  replaceProfile,
  type ProfileRequestError,
} from "@/lib/api/profiles";
import {
  readSession,
  removeSession,
  subscribeSession,
  writeSession,
} from "@/lib/store/session-store";

/**
 * 서버 profile의 브라우저 측 식별자 저장소.
 *
 * 소득·부채를 포함한 profile 원문은 sessionStorage에 저장하지 않는다. 브라우저에는
 * 불투명 UUID와 fraud 분석에만 쓰는 persona를 두고, profile은 서버에서 다시 읽는다.
 */

const IDENTITY_KEY = "finshield:profile-identity:v1";
const LEGACY_PROFILE_KEY = "finshield:profile";

type ProfileIdentity = { profileId: string; persona: Persona };
export type ProfileStoreState = {
  profileId: string | null;
  profile: FinancialProfile | null;
  status: "empty" | "idle" | "loading" | "ready" | "error";
  error: string | null;
};

const listeners = new Set<() => void>();
let identityRaw: string | null = null;
let state: ProfileStoreState = {
  profileId: null,
  profile: null,
  status: "empty",
  error: null,
};

function parseIdentity(raw: string | null): ProfileIdentity | null {
  if (!raw) return null;
  try {
    const value: unknown = JSON.parse(raw);
    if (typeof value !== "object" || value === null) return null;
    const profileId = "profileId" in value ? value.profileId : null;
    const persona = "persona" in value ? value.persona : null;
    const parsedId = z.string().uuid().safeParse(profileId);
    if (!parsedId.success) return null;
    const parsedPersona = PersonaSchema.safeParse(persona);
    if (!parsedPersona.success) return null;
    return { profileId: parsedId.data, persona: parsedPersona.data };
  } catch {
    return null;
  }
}

function reconcileIdentity(): ProfileIdentity | null {
  const raw = readSession(IDENTITY_KEY);
  const identity = parseIdentity(raw);
  if (raw !== identityRaw) {
    identityRaw = raw;
    state = identity
      ? {
          profileId: identity.profileId,
          profile: null,
          status: "idle",
          error: null,
        }
      : {
          profileId: null,
          profile: null,
          status: "empty",
          error: null,
        };
  }
  return identity;
}

function emit(next: ProfileStoreState): void {
  state = next;
  for (const listener of listeners) listener();
}

function snapshot(): ProfileStoreState {
  reconcileIdentity();
  return state;
}

const serverSnapshot: ProfileStoreState = {
  profileId: null,
  profile: null,
  status: "empty",
  error: null,
};

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  const unsubscribeSession = subscribeSession(() => {
    reconcileIdentity();
    listener();
  });
  return () => {
    listeners.delete(listener);
    unsubscribeSession();
  };
}

async function loadStoredProfile(): Promise<void> {
  const identity = reconcileIdentity();
  if (!identity || state.status !== "idle") return;

  emit({ ...state, status: "loading", error: null });
  try {
    const resource = await fetchProfile(identity.profileId, identity.persona);
    if (parseIdentity(readSession(IDENTITY_KEY))?.profileId !== identity.profileId) return;
    emit({
      profileId: resource.profileId,
      profile: resource.profile,
      status: "ready",
      error: null,
    });
  } catch (error) {
    const status = (error as ProfileRequestError).status;
    if (status === 400 || status === 404) {
      identityRaw = null;
      removeSession(IDENTITY_KEY);
      emit({
        profileId: null,
        profile: null,
        status: "error",
        error: "서버가 다시 시작되어 저장한 금융상태를 찾지 못했습니다. 다시 입력해 주세요.",
      });
      return;
    }
    emit({
      ...state,
      status: "error",
      error: "금융상태를 불러오지 못했습니다. 서버 연결을 확인해 주세요.",
    });
  }
}

export async function saveProfile(profile: FinancialProfile): Promise<void> {
  const identity = reconcileIdentity();
  const resource = identity
    ? await replaceProfile(identity.profileId, profile)
    : await createProfile(profile);

  const raw = JSON.stringify({
    profileId: resource.profileId,
    persona: profile.persona,
  } satisfies ProfileIdentity);
  identityRaw = raw;
  writeSession(IDENTITY_KEY, raw);
  removeSession(LEGACY_PROFILE_KEY);
  emit({
    profileId: resource.profileId,
    profile: resource.profile,
    status: "ready",
    error: null,
  });
}

export async function clearProfile(): Promise<void> {
  const identity = reconcileIdentity();
  if (identity) await deleteProfile(identity.profileId);
  identityRaw = null;
  removeSession(IDENTITY_KEY);
  removeSession(LEGACY_PROFILE_KEY);
  emit({
    profileId: null,
    profile: null,
    status: "empty",
    error: null,
  });
}

export function useProfileStore(): ProfileStoreState {
  const current = useSyncExternalStore(subscribe, snapshot, () => serverSnapshot);
  useEffect(() => {
    if (current.status === "idle") void loadStoredProfile();
  }, [current.profileId, current.status]);
  return current;
}

export function useStoredProfile(): FinancialProfile | null {
  return useProfileStore().profile;
}
