import type { CheckItem, NextAction } from "@/lib/api/contracts";
import { MOCK_EVIDENCE } from "@/lib/mock/evidence";

/**
 * Home "지금 확인할 금융정보" / "다음 행동" mock.
 *
 * 백엔드 `/api/v1/recommendations` 가 생기면 대체된다.
 * 구체적인 상품명·금리는 넣지 않는다. 공식 API 연동 전에 상품 정보를
 * 지어내지 않기 위해서다.
 */

export const MOCK_CHECK_ITEMS: CheckItem[] = [
  {
    id: "check-refinance",
    title: "지금 쓰는 대출보다 이자가 낮은 정책상품이 있는지 확인해 보세요",
    reason: "목표를 '기존 대출 갈아타기'로 선택하셨습니다.",
    href: "/products",
    evidence: MOCK_EVIDENCE.kinfa_products,
  },
  {
    id: "check-emergency",
    title: "비상금이 3개월치에 못 미칩니다",
    reason: "소득이 끊기면 2.4개월 뒤부터 생활비가 부족해집니다.",
    href: "/profile",
  },
];

export const MOCK_NEXT_ACTION: NextAction = {
  id: "next-compare",
  title: "대출을 갈아타면 매달 얼마가 달라지는지 확인하기",
  detail:
    "지금 상환액과 비교해서 부담이 얼마나 줄어드는지 먼저 보고 결정하세요.",
  // 비교/시뮬레이션 화면은 아직 없다. 준비 중 화면으로 보낸다.
  href: "/products",
  ctaLabel: "비교해 보기",
};

export const ONBOARDING_NEXT_ACTION: NextAction = {
  id: "next-onboarding",
  title: "금융상태 5단계 입력하기",
  detail:
    "소득·지출·대출을 대략만 알려주면 내 상황에 맞는 정보를 골라 보여드립니다.",
  href: "/onboarding",
  ctaLabel: "시작하기",
};
