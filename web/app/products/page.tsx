import Link from "next/link";
import { BookOpenCheck, Calculator } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ProductRecommendations } from "@/components/finance/ProductRecommendations";

export const metadata = {
  title: "금융상품",
};

export default function ProductsPage() {
  return (
    <AppShell>
      <PageHeader
        title="금융상품"
        description="내 금융 목표와 공식 상품 용도를 비교합니다. 적격 여부는 취급기관에서 확인해야 합니다."
        backHref="/"
      />
      <div className="mb-6 grid gap-3 sm:grid-cols-2">
        <Link
          href="/products/simulate"
          className="flex min-h-11 items-center gap-3 rounded-xl border border-border bg-card p-4 transition-colors hover:bg-accent"
        >
          <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-secondary text-primary">
            <Calculator aria-hidden className="size-5" />
          </span>
          <span>
            <span className="block text-title text-foreground">대출 조건 직접 비교</span>
            <span className="mt-0.5 block text-caption text-muted-foreground">
              금리를 바꿨을 때 월별 납입액과 총이자를 비교해 보세요.
            </span>
          </span>
        </Link>
        <Link
          href="/learn/wealth"
          className="flex min-h-11 items-center gap-3 rounded-xl border border-border bg-card p-4 transition-colors hover:bg-accent"
        >
          <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-secondary text-primary">
            <BookOpenCheck aria-hidden className="size-5" />
          </span>
          <span>
            <span className="block text-title text-foreground">재테크 기초부터 보기</span>
            <span className="mt-0.5 block text-caption text-muted-foreground">
              돈의 흐름·저축·부채·투자 위험을 공식 자료로 확인하세요.
            </span>
          </span>
        </Link>
      </div>
      <ProductRecommendations />
    </AppShell>
  );
}
