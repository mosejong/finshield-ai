"use client";

import { useEffect, useState } from "react";
import { FinancialStatusBlock } from "@/components/home/FinancialStatusBlock";
import { fetchProfileMetrics } from "@/lib/api/profiles";
import type {
  FinancialSnapshot,
  ProfileMetricsResponse,
} from "@/lib/api/contracts";
import { useProfileStore } from "@/lib/store/profile-store";


export function HomeFinancialStatus() {
  const profileState = useProfileStore();
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
            error: "금융상태는 저장되어 있지만 요약 지표를 불러오지 못했습니다.",
          });
        }
      });
    return () => {
      active = false;
    };
  }, [profileState.profileId, profileState.status]);

  const currentMetrics =
    profileState.profileId && metricsState?.profileId === profileState.profileId
      ? metricsState
      : null;

  let snapshot: FinancialSnapshot;
  if (profileState.status === "idle" || profileState.status === "loading") {
    snapshot = {
      hasProfile: profileState.profileId !== null,
      profile: null,
      summary: "저장한 금융상태를 불러오고 있습니다…",
      metrics: [],
      source: "live",
    };
  } else if (!profileState.profile) {
    snapshot = {
      hasProfile: false,
      profile: null,
      summary:
        profileState.error ??
        "아직 금융상태를 알려주지 않으셨습니다. 5단계만 답하면 요약을 볼 수 있습니다.",
      metrics: [],
      source: "live",
    };
  } else {
    snapshot = {
      hasProfile: true,
      profile: profileState.profile,
      summary:
        currentMetrics?.data?.summary ??
        currentMetrics?.error ??
        "입력값으로 금융지표를 계산하고 있습니다…",
      metrics: currentMetrics?.data?.metrics ?? [],
      source: "live",
    };
  }

  return <FinancialStatusBlock snapshot={snapshot} />;
}
