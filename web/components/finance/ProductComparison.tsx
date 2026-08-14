"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import { DisclaimerNote } from "@/components/common/DisclaimerNote";
import { PRODUCT_FIELD_GROUPS, officialText } from "@/components/finance/ProductFacts";
import { compareProducts } from "@/lib/api/products";
import type { ProductComparisonResponse } from "@/lib/api/contracts";


export function ProductComparison({ productIds }: { productIds: string[] }) {
  const [data, setData] = useState<ProductComparisonResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (productIds.length !== 2 || new Set(productIds).size !== 2) return;
    let active = true;
    compareProducts([productIds[0], productIds[1]])
      .then((result) => {
        if (active) setData(result);
      })
      .catch((cause: unknown) => {
        if (active) {
          setError(cause instanceof Error ? cause.message : "상품 비교 정보를 불러오지 못했습니다.");
        }
      });
    return () => {
      active = false;
    };
  }, [productIds]);

  if (productIds.length !== 2 || new Set(productIds).size !== 2) {
    return (
      <div className="rounded-lg border border-border bg-card p-5 text-center">
        <p className="text-title text-foreground">비교할 상품 2개를 선택해 주세요</p>
        <p className="mt-2 text-body text-muted-foreground">공식 상품 후보에서 서로 다른 상품을 두 개 고를 수 있습니다.</p>
        <Link href="/products" className="mt-4 inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-body font-semibold text-primary-foreground">
          상품 후보로 돌아가기
        </Link>
      </div>
    );
  }
  if (error) {
    return (
      <p role="alert" className="rounded-lg border border-risk-medium-border bg-risk-medium-bg p-4 text-body text-risk-medium">
        {error} 비교 결과가 없다고 두 상품이 같거나 이용할 수 없다는 뜻은 아닙니다.
      </p>
    );
  }
  if (!data) {
    return <p role="status" className="text-body text-muted-foreground">같은 기준월의 공식 상품을 확인하고 있습니다…</p>;
  }

  const [first, second] = data.items;
  return (
    <>
      <p className="mb-4 text-caption text-muted-foreground">
        공식 기준월 {data.source_base_month} · 같은 snapshot에서 불러온 원문입니다.
      </p>

      <div className="grid grid-cols-2 gap-3">
        {[first, second].map((product, index) => (
          <article key={product.source_product_id} className="min-w-0 rounded-xl border border-border bg-card p-3">
            <p className="text-caption font-medium text-primary">상품 {index === 0 ? "A" : "B"}</p>
            <h2 className="mt-1 break-words text-title text-foreground">{product.name}</h2>
            <p className="mt-1 break-words text-caption text-muted-foreground">
              {product.offering_institution ?? "제공기관 확인 필요"}
            </p>
            <Link
              href={`/products/${encodeURIComponent(product.source_product_id)}`}
              className="mt-2 inline-flex min-h-11 items-center text-caption font-medium text-primary underline underline-offset-2"
            >
              상세 보기
            </Link>
          </article>
        ))}
      </div>

      <div className="mt-6 flex flex-col gap-6">
        {PRODUCT_FIELD_GROUPS.map((group) => (
          <section key={group.id} aria-labelledby={`compare-${group.id}`}>
            <h2 id={`compare-${group.id}`} className="text-title text-foreground">{group.title}</h2>
            <dl className="mt-3 divide-y divide-border rounded-xl border border-border bg-card px-3">
              {group.fields.map((field) => (
                <div key={field.label} className="py-3">
                  <dt className="text-caption font-medium text-muted-foreground">{field.label}</dt>
                  <div className="mt-2 grid grid-cols-2 gap-3">
                    <dd className="min-w-0 whitespace-pre-wrap break-words text-body text-foreground">
                      {officialText(field.value(first))}
                    </dd>
                    <dd className="min-w-0 whitespace-pre-wrap break-words border-l border-border pl-3 text-body text-foreground">
                      {officialText(field.value(second))}
                    </dd>
                  </div>
                </div>
              ))}
            </dl>
          </section>
        ))}
      </div>

      <a
        href={data.source_reference}
        target="_blank"
        rel="noreferrer"
        className="mt-6 inline-flex min-h-11 items-center gap-1 text-body font-medium text-primary underline underline-offset-2"
      >
        공식 데이터셋 출처 보기
        <ExternalLink aria-hidden className="size-4" />
      </a>
      <DisclaimerNote>{data.disclaimer}</DisclaimerNote>
    </>
  );
}
