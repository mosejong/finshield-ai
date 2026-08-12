import {
  BackendRecommendationGoalSchema,
  BackendProductSchema,
  ProductComparisonRequestSchema,
  ProductComparisonResponseSchema,
  ProductRecommendationResponseSchema,
  ProductSourceIdSchema,
  type BackendProduct,
  type FinancialProfile,
  type ProductComparisonResponse,
  type ProductRecommendationResponse,
} from "@/lib/api/contracts";

const GOAL_MAP: Record<FinancialProfile["goal"], string> = {
  housing: "housing",
  emergency_cash: "emergency_cash",
  debt_refinance: "debt_refinance",
  living_expense: "living_expense",
  startup_business: "startup_business",
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

export async function fetchProductDetail(
  sourceProductId: string,
): Promise<BackendProduct> {
  const productId = ProductSourceIdSchema.parse(sourceProductId);
  const response = await fetch(
    `/api/proxy/products/${encodeURIComponent(productId)}`,
    { method: "GET", cache: "no-store" },
  );
  if (response.status === 404) {
    throw new Error("최신 공식 상품에서 해당 상품을 찾지 못했습니다.");
  }
  if (!response.ok) throw new Error("상품 상세 정보를 불러오지 못했습니다.");
  return BackendProductSchema.parse(await response.json());
}

export async function compareProducts(
  productIds: [string, string],
): Promise<ProductComparisonResponse> {
  const request = ProductComparisonRequestSchema.parse({ product_ids: productIds });
  const response = await fetch("/api/proxy/products/compare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    cache: "no-store",
  });
  if (response.status === 404) {
    throw new Error("비교할 상품 중 최신 공식 목록에서 찾을 수 없는 상품이 있습니다.");
  }
  if (!response.ok) throw new Error("상품 비교 정보를 불러오지 못했습니다.");
  return ProductComparisonResponseSchema.parse(await response.json());
}
