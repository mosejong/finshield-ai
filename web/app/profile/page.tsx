"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { SectionHeading } from "@/components/common/SectionHeading";
import { MockBadge } from "@/components/common/MockBadge";
import { DisclaimerNote } from "@/components/common/DisclaimerNote";
import { MetricList } from "@/components/finance/MetricList";
import { ProfileFacts } from "@/components/finance/ProfileFacts";
import { getSnapshot } from "@/lib/api/home";
import { fetchProfileMetrics } from "@/lib/api/profiles";
import type { ProfileMetricsResponse } from "@/lib/api/contracts";
import { clearProfile, useProfileStore } from "@/lib/store/profile-store";

/**
 * 내 금융상태.
 *
 * 직접 입력한 프로필이 있으면 입력값을 그대로 보여주되, 파생지표는 비워 둔다.
 * 지표 계산은 백엔드 몫이고 프론트엔드에서 대신 계산하지 않기 때문이다.
 * 입력값이 없으면 예시 스냅샷을 "예시"로 표시해 화면 구조를 보여준다.
 */
export default function ProfilePage() {
  const profileState = useProfileStore();
  const profile = profileState.profile;
  const loading = profileState.status === "idle" || profileState.status === "loading";
  const [deletePending, setDeletePending] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [metricsState, setMetricsState] = useState<{
    profileId: string;
    data?: ProfileMetricsResponse;
    error?: string;
  } | null>(null);

  useEffect(() => {
    if (profileState.status !== "ready" || !profileState.profileId) return;
    const profileId = profileState.profileId;
    let active = true;
    fetchProfileMetrics(profileId)
      .then((data) => {
        if (active) setMetricsState({ profileId, data });
      })
      .catch(() => {
        if (active) {
          setMetricsState({
            profileId,
            error: "입력값은 저장됐지만 계산 지표를 불러오지 못했습니다. 잠시 후 다시 확인해 주세요.",
          });
        }
      });
    return () => {
      active = false;
    };
  }, [profileState.profileId, profileState.status]);

  const demoSnapshot = getSnapshot();
  const hasOwnProfile = profile !== null;
  const currentMetrics =
    profileState.profileId && metricsState?.profileId === profileState.profileId
      ? metricsState
      : null;

  return (
    <AppShell>
      <PageHeader
        title="내 금융상태"
        description="어떤 정보가 판단에 쓰이는지 그대로 보여드립니다."
        backHref="/"
      />

      {loading ? (
        <p className="text-body text-muted-foreground">불러오는 중…</p>
      ) : (
        <div className="flex flex-col gap-7">
          {profileState.error ? (
            <p role="alert" className="rounded-lg border border-risk-medium-border bg-risk-medium-bg p-4 text-body text-risk-medium">
              {profileState.error}
            </p>
          ) : null}
          <section aria-labelledby="profile-summary">
            <SectionHeading
              badge={hasOwnProfile ? undefined : <MockBadge source="mock" label="예시" />}
            >
              <span id="profile-summary">요약</span>
            </SectionHeading>

            <p className="rounded-lg border border-border bg-card p-4 text-body text-foreground">
              {hasOwnProfile
                ? currentMetrics?.data?.summary ?? "입력값으로 금융지표를 계산하고 있습니다…"
                : demoSnapshot.summary}
            </p>
          </section>

          <section aria-labelledby="profile-metrics">
            <SectionHeading
              badge={hasOwnProfile ? undefined : <MockBadge source="mock" label="예시" />}
            >
              <span id="profile-metrics">한눈에 보는 지표</span>
            </SectionHeading>

            {hasOwnProfile ? (
              currentMetrics?.error ? (
                <p role="alert" className="rounded-lg border border-risk-medium-border bg-risk-medium-bg p-4 text-body text-risk-medium">
                  {currentMetrics.error}
                </p>
              ) : currentMetrics?.data ? (
                <>
                  <MetricList metrics={currentMetrics.data.metrics} />
                  <details className="mt-3 rounded-lg border border-border bg-card p-4">
                    <summary className="cursor-pointer text-body font-medium text-foreground">
                      계산 기준 보기
                    </summary>
                    <ul className="mt-3 list-disc space-y-2 pl-5 text-caption text-muted-foreground">
                      {currentMetrics.data.assumptions.map((assumption) => (
                        <li key={assumption}>{assumption}</li>
                      ))}
                    </ul>
                  </details>
                </>
              ) : (
                <p className="rounded-lg border border-dashed border-border bg-secondary/60 p-4 text-body text-muted-foreground">
                  입력값으로 금융지표를 계산하고 있습니다…
                </p>
              )
            ) : (
              <MetricList metrics={demoSnapshot.metrics} />
            )}
          </section>

          <section aria-labelledby="profile-facts">
            <SectionHeading
              badge={hasOwnProfile ? undefined : <MockBadge source="mock" label="예시" />}
              action={
                <Link
                  href="/onboarding"
                  className="text-caption font-medium text-primary underline underline-offset-2"
                >
                  {hasOwnProfile ? "고치기" : "직접 입력하기"}
                </Link>
              }
            >
              <span id="profile-facts">입력한 내용</span>
            </SectionHeading>

            <ProfileFacts profile={profile ?? demoSnapshot.profile!} />

            <p className="mt-3 text-caption text-muted-foreground">
              주민등록번호, 계좌번호, 실명은 받지 않습니다. 브라우저에는 프로필
              식별자만 남고, 입력값은 로컬 프로토타입 서버에서 관리합니다.
            </p>

            {/* 탭을 닫을 때까지 기다리지 않고 지울 수 있어야 한다 */}
            {hasOwnProfile ? (
              <button
                type="button"
                disabled={deletePending}
                onClick={async () => {
                  setDeletePending(true);
                  setDeleteError(null);
                  try {
                    await clearProfile();
                  } catch {
                    setDeleteError("금융상태를 삭제하지 못했습니다. 잠시 후 다시 시도해 주세요.");
                    setDeletePending(false);
                  }
                }}
                className="mt-2 min-h-9 text-caption font-medium text-muted-foreground underline underline-offset-2 hover:text-foreground"
              >
                {deletePending ? "지우는 중…" : "입력한 내용 지우기"}
              </button>
            ) : null}
            {deleteError ? <p role="alert" className="mt-2 text-caption text-risk-medium">{deleteError}</p> : null}
          </section>
        </div>
      )}

      <DisclaimerNote>
        {hasOwnProfile && currentMetrics?.data
          ? currentMetrics.data.disclaimer
          : "여기 표시되는 지표는 상황을 이해하기 위한 참고값이며, 은행이 대출 심사에 사용하는 공식 기준과 다릅니다."}
      </DisclaimerNote>
    </AppShell>
  );
}
