import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ProductDetail } from "@/components/finance/ProductDetail";


export const metadata = {
  title: "공식 상품 상세",
};


export default async function ProductDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let productId = id;
  try {
    productId = decodeURIComponent(id);
  } catch {
    // The client-side contract renders the same safe invalid-identifier state.
  }
  return (
    <AppShell>
      <PageHeader
        title="공식 상품 상세"
        description="금리·한도·대상 조건을 공식 API 원문 그대로 확인합니다."
        backHref="/products"
      />
      <ProductDetail productId={productId} />
    </AppShell>
  );
}
