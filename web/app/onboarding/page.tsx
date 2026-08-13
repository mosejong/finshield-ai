"use client";

import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ProfileForm } from "@/components/finance/ProfileForm";
import { useProfileStore } from "@/lib/store/profile-store";

export default function OnboardingPage() {
  const profileState = useProfileStore();
  const loading = profileState.status === "idle" || profileState.status === "loading";

  return (
    <AppShell>
      <PageHeader
        title="금융상태 알려주기"
        description="5단계면 끝납니다. 대략적인 금액이어도 괜찮고, 모르면 비워 두어도 됩니다."
        backHref="/"
      />

      {loading ? (
        <p role="status" className="text-body text-muted-foreground">불러오는 중…</p>
      ) : (
        <>
          {profileState.error ? (
            <p role="alert" className="mb-4 rounded-lg border border-risk-medium-border bg-risk-medium-bg p-4 text-body text-risk-medium">
              {profileState.error}
            </p>
          ) : null}
          <ProfileForm initial={profileState.profile} />
        </>
      )}
    </AppShell>
  );
}
