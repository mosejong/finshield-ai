import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ProductComparison } from "@/components/finance/ProductComparison";


export const metadata = {
  title: "공식 상품 비교",
};


export default async function ProductComparePage({
  searchParams,
}: {
  searchParams: Promise<{ ids?: string | string[] }>;
}) {
  const { ids } = await searchParams;
  const productIds = Array.isArray(ids) ? ids : ids ? [ids] : [];

  return (
    <AppShell>
      <PageHeader
        title="공식 상품 비교"
        description="같은 공식 기준월의 원문을 나란히 확인합니다. 더 유리한 상품을 자동 판정하지 않습니다."
        backHref="/products"
      />
      <ProductComparison productIds={productIds} />
    </AppShell>
  );
}
