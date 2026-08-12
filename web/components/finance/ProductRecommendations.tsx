"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchProductRecommendations } from "@/lib/api/products";
import { useStoredProfile } from "@/lib/store/profile-store";
import type { ProductRecommendationResponse, ProductMatchStatus } from "@/lib/api/contracts";
import { DisclaimerNote } from "@/components/common/DisclaimerNote";

const STATUS_LABEL: Record<ProductMatchStatus, string> = {
  potential_match: "목적이 비슷해요",
  needs_review: "추가 확인 필요",
  mismatch: "현재 목적과 달라요",
};

export function ProductRecommendations() {
  const profile = useStoredProfile();
  const [data, setData] = useState<ProductRecommendationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!profile) return;
    let active = true;
    fetchProductRecommendations(profile.goal)
      .then((result) => { if (active) setData(result); })
      .catch(() => { if (active) setError("공식 상품 정보를 불러오지 못했습니다. 잠시 후 다시 확인해 주세요."); });
    return () => { active = false; };
  }, [profile]);

  if (!profile) return <div className="rounded-lg border border-border bg-card p-5 text-center"><p className="text-title text-foreground">금융 목표를 먼저 알려주세요</p><p className="mt-2 text-body text-muted-foreground">목표 하나만 서버에 보내 공식 상품 용도와 비교합니다.</p><Link href="/onboarding" className="mt-4 inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-body font-semibold text-primary-foreground">프로필 입력하기</Link></div>;
  if (error) return <p role="alert" className="rounded-lg border border-risk-medium-border bg-risk-medium-bg p-4 text-body text-risk-medium">{error}<br />결과를 불러오지 못했다고 이용 가능한 상품이 없다는 뜻은 아닙니다.</p>;
  if (!data) return <p className="text-body text-muted-foreground">공식 상품을 확인하고 있습니다…</p>;

  return <>
    <div className="grid grid-cols-3 gap-2" aria-label="상품 후보 분류 요약">
      {(["potential_match", "needs_review", "mismatch"] as const).map((status) => <div key={status} className="rounded-lg border border-border bg-card p-3 text-center"><p className="text-title tabular-nums text-foreground">{data.summary[status]}</p><p className="text-caption text-muted-foreground">{STATUS_LABEL[status]}</p></div>)}
    </div>
    <p className="mt-3 text-caption text-muted-foreground">공식 기준월 {data.source_base_month} · 전체 {data.total_count}건 중 목적 후보 우선 최대 100건을 표시합니다.</p>
    <ul className="mt-4 flex flex-col gap-3">
      {data.results.map(({ status, product, reasons }) => <li key={product.source_product_id} className="rounded-xl border border-border bg-card p-4">
        <span className="inline-flex rounded-full border border-border px-2 py-1 text-caption text-foreground">{STATUS_LABEL[status]}</span>
        <h2 className="mt-2 text-title text-foreground">{product.name}</h2><p className="mt-1 text-caption text-muted-foreground">{product.offering_institution ?? "제공기관 확인 필요"}</p>
        <dl className="mt-3 grid grid-cols-2 gap-2 text-body"><div><dt className="text-caption text-muted-foreground">공식 용도</dt><dd>{product.purpose_text ?? "확인 필요"}</dd></div><div><dt className="text-caption text-muted-foreground">금리 원문</dt><dd>{product.interest_rate_text ?? "확인 필요"}</dd></div><div><dt className="text-caption text-muted-foreground">한도 원문</dt><dd>{product.loan_limit_text ?? "확인 필요"}</dd></div><div><dt className="text-caption text-muted-foreground">대상 원문</dt><dd>{product.eligibility.target_text ?? "확인 필요"}</dd></div></dl>
        <ul className="mt-3 border-t border-border pt-3 text-caption text-muted-foreground">{reasons.map((reason) => <li key={reason.rule}>• {reason.message}</li>)}</ul>
        <a href={product.source_reference} target="_blank" rel="noreferrer" className="mt-3 inline-flex min-h-11 items-center text-body font-medium text-primary underline underline-offset-2">공식 데이터 출처 보기</a>
      </li>)}
    </ul><DisclaimerNote>{data.disclaimer}</DisclaimerNote>
  </>;
}
