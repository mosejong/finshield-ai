"use client";

import { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import { DisclaimerNote } from "@/components/common/DisclaimerNote";
import { ProductFacts } from "@/components/finance/ProductFacts";
import { fetchProductDetail } from "@/lib/api/products";
import { productProviderLabel } from "@/lib/format/labels";
import type { BackendProduct } from "@/lib/api/contracts";


export function ProductDetail({ productId }: { productId: string }) {
  const [product, setProduct] = useState<BackendProduct | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetchProductDetail(productId)
      .then((result) => {
        if (active) setProduct(result);
      })
      .catch((cause: unknown) => {
        if (active) {
          setError(cause instanceof Error ? cause.message : "상품 상세 정보를 불러오지 못했습니다.");
        }
      });
    return () => {
      active = false;
    };
  }, [productId]);

  if (error) {
    return (
      <p role="alert" className="rounded-lg border border-risk-medium-border bg-risk-medium-bg p-4 text-body text-risk-medium">
        {error} 상품이 보이지 않는다고 이용 가능한 상품이 없다는 뜻은 아닙니다.
      </p>
    );
  }
  if (!product) {
    return <p role="status" className="text-body text-muted-foreground">최신 공식 상품을 확인하고 있습니다…</p>;
  }

  return (
    <>
      <section className="mb-6 rounded-xl border border-border bg-card p-4">
        <p className="text-caption font-medium text-primary">공식 상품 상세</p>
        <h2 className="mt-1 text-title text-foreground">{product.name}</h2>
        <p className="mt-1 text-body text-muted-foreground">
          {product.offering_institution ?? "제공기관 확인 필요"}
        </p>
        <p className="mt-3 text-caption text-muted-foreground">
          {productProviderLabel(product.provider)} 공공데이터 · 기준월{" "}
          {product.source_base_month ?? "확인 필요"} · 상품 ID {product.source_product_id}
        </p>
      </section>

      <ProductFacts product={product} />

      <a
        href={product.source_reference}
        target="_blank"
        rel="noreferrer"
        className="mt-6 inline-flex min-h-11 items-center gap-1 text-body font-medium text-primary underline underline-offset-2"
      >
        공식 데이터셋 출처 보기
        <ExternalLink aria-hidden className="size-4" />
      </a>

      <DisclaimerNote>
        공식 API의 원문을 표시한 화면입니다. 비어 있는 필드는 추정하지 않았으며 적격성, 승인 가능성, 실제 적용 금리를 보장하지 않습니다. 최신 조건은 취급기관에서 확인하세요.
      </DisclaimerNote>
    </>
  );
}
