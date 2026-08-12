"use client";

import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ProfileForm } from "@/components/finance/ProfileForm";
import { useStoredProfile } from "@/lib/store/profile-store";
import { useHydrated } from "@/lib/store/session-store";

export default function OnboardingPage() {
  const hydrated = useHydrated();
  const initial = useStoredProfile();

  return (
    <AppShell>
      <PageHeader
        title="금융상태 알려주기"
        description="5단계면 끝납니다. 대략적인 금액이어도 괜찮고, 모르면 비워 두어도 됩니다."
        backHref="/"
      />

      {/* 저장된 값을 읽기 전에 폼을 그리면 빈 값으로 초기화된다 */}
      {hydrated ? (
        <ProfileForm initial={initial} />
      ) : (
        <p className="text-body text-muted-foreground">불러오는 중…</p>
      )}
    </AppShell>
  );
}
