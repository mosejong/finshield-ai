"use client";

import { CheckTodayBlock } from "@/components/home/CheckTodayBlock";
import { NextActionBlock } from "@/components/home/NextActionBlock";
import type { CheckItem, NextAction } from "@/lib/api/contracts";
import { GOAL_LABEL } from "@/lib/format/labels";
import { useProfileStore } from "@/lib/store/profile-store";


export function HomeCheckToday() {
  const profileState = useProfileStore();
  if (profileState.status === "idle" || profileState.status === "loading") {
    return null;
  }
  const items: CheckItem[] = profileState.profile
    ? [
        {
          id: "official-product-purpose",
          title: "내 목표와 공식 상품의 용도를 비교해 보세요",
          reason: `저장한 목표는 ‘${GOAL_LABEL[profileState.profile.goal]}’입니다. 상세 자격은 취급기관에서 확인해야 합니다.`,
          href: "/products",
        },
      ]
    : [];

  return <CheckTodayBlock items={items} source="live" />;
}


export function HomeNextAction() {
  const profileState = useProfileStore();
  if (profileState.status === "idle" || profileState.status === "loading") {
    return null;
  }
  const action: NextAction = profileState.profile
    ? {
        id: "select-products-to-compare",
        title: "후보 상품 2개의 공식 원문을 나란히 확인하기",
        detail:
          "금리·한도·지원조건 원문을 비교하되 더 유리한 상품을 자동으로 판정하지 않습니다.",
        href: "/products",
        ctaLabel: "상품 고르기",
      }
    : {
        id: "complete-profile",
        title: "금융상태 5단계 입력하기",
        detail:
          "소득·지출·대출을 대략만 알려주면 현재 흐름과 공식 상품 용도를 확인할 수 있습니다.",
        href: "/onboarding",
        ctaLabel: "시작하기",
      };

  return <NextActionBlock action={action} source="live" />;
}
