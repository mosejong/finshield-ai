import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ProductRecommendations } from "@/components/finance/ProductRecommendations";

export const metadata = {
  title: "금융상품 | FinShield",
};

export default function ProductsPage() {
  return (
    <AppShell>
      <PageHeader
        title="금융상품"
        description="내 금융 목표와 공식 상품 용도를 비교합니다. 적격 여부는 취급기관에서 확인해야 합니다."
        backHref="/"
      />
      <ProductRecommendations />
    </AppShell>
  );
}
