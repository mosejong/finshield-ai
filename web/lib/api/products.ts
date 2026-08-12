import {
  BackendRecommendationGoalSchema,
  ProductRecommendationResponseSchema,
  type FinancialProfile,
  type ProductRecommendationResponse,
} from "@/lib/api/contracts";

const GOAL_MAP: Record<FinancialProfile["goal"], string> = {
  housing: "housing",
  emergency_cash: "emergency_cash",
  debt_refinance: "debt_refinance",
  living_expense: "living_expense",
  business: "startup_business",
  vehicle: "vehicle",
  asset_building: "asset_building",
  other: "other",
};

export async function fetchProductRecommendations(
  goal: FinancialProfile["goal"],
): Promise<ProductRecommendationResponse> {
  const backendGoal = BackendRecommendationGoalSchema.parse(GOAL_MAP[goal]);
  const response = await fetch("/api/proxy/recommendations?page_size=100", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ goal: backendGoal }),
    cache: "no-store",
  });
  if (!response.ok) throw new Error("상품 정보를 불러오지 못했습니다.");
  return ProductRecommendationResponseSchema.parse(await response.json());
}
