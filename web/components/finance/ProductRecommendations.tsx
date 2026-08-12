"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchProductRecommendations } from "@/lib/api/products";
import { useProfileStore } from "@/lib/store/profile-store";
import type { FinancialProfile, ProductRecommendationResponse, ProductMatchStatus } from "@/lib/api/contracts";
import { DisclaimerNote } from "@/components/common/DisclaimerNote";

const STATUS_LABEL: Record<ProductMatchStatus, string> = {
  potential_match: "목적이 비슷해요",
  needs_review: "추가 확인 필요",
  mismatch: "현재 목적과 달라요",
};

export function ProductRecommendations() {
  const profileState = useProfileStore();
  const profile = profileState.profile;
  const [requestState, setRequestState] = useState<{
    goal: FinancialProfile["goal"];
    data?: ProductRecommendationResponse;
    error?: string;
  } | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  useEffect(() => {
    if (!profile) return;
    let active = true;
    fetchProductRecommendations(profile.goal)
      .then((result) => { if (active) setRequestState({ goal: profile.goal, data: result }); })
      .catch(() => { if (active) setRequestState({ goal: profile.goal, error: "공식 상품 정보를 불러오지 못했습니다. 잠시 후 다시 확인해 주세요." }); });
    return () => { active = false; };
  }, [profile]);

  if (profileState.status === "idle" || profileState.status === "loading") return <p className="text-body text-muted-foreground">금융 목표를 불러오고 있습니다…</p>;
  if (!profile) return <div className="rounded-lg border border-border bg-card p-5 text-center">{profileState.error ? <p role="alert" className="mb-3 text-body text-risk-medium">{profileState.error}</p> : null}<p className="text-title text-foreground">금융 목표를 먼저 알려주세요</p><p className="mt-2 text-body text-muted-foreground">목표 하나만 서버에 보내 공식 상품 용도와 비교합니다.</p><Link href="/onboarding" className="mt-4 inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-body font-semibold text-primary-foreground">프로필 입력하기</Link></div>;
  const currentState = requestState?.goal === profile.goal ? requestState : null;
  if (currentState?.error) return <p role="alert" className="rounded-lg border border-risk-medium-border bg-risk-medium-bg p-4 text-body text-risk-medium">{currentState.error}<br />결과를 불러오지 못했다고 이용 가능한 상품이 없다는 뜻은 아닙니다.</p>;
  if (!currentState?.data) return <p className="text-body text-muted-foreground">공식 상품을 확인하고 있습니다…</p>;
  const data = currentState.data;
  const visibleIds = new Set(data.results.map(({ product }) => product.source_product_id));
  const activeSelectedIds = selectedIds.filter((id) => visibleIds.has(id));
  const comparisonHref = activeSelectedIds.length === 2
    ? `/products/compare?ids=${encodeURIComponent(activeSelectedIds[0])}&ids=${encodeURIComponent(activeSelectedIds[1])}`
    : null;

  function toggleComparison(productId: string) {
    setSelectedIds((previous) => {
      const active = previous.filter((id) => visibleIds.has(id));
      if (active.includes(productId)) return active.filter((id) => id !== productId);
      if (active.length >= 2) return active;
      return [...active, productId];
    });
  }

  return <>
    <div className="grid grid-cols-3 gap-2" aria-label="상품 후보 분류 요약">
      {(["potential_match", "needs_review", "mismatch"] as const).map((status) => <div key={status} className="rounded-lg border border-border bg-card p-3 text-center"><p className="text-title tabular-nums text-foreground">{data.summary[status]}</p><p className="text-caption text-muted-foreground">{STATUS_LABEL[status]}</p></div>)}
    </div>
    <p className="mt-3 text-caption text-muted-foreground">공식 기준월 {data.source_base_month} · 전체 {data.total_count}건 중 목적 후보 우선 최대 100건을 표시합니다.</p>
    <div className="mt-4 flex items-center justify-between gap-3 rounded-lg border border-border bg-card p-3">
      <p className="text-body text-foreground">비교 선택 {activeSelectedIds.length} / 2</p>
      {comparisonHref ? (
        <Link href={comparisonHref} className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-body font-semibold text-primary-foreground">
          선택한 상품 비교
        </Link>
      ) : (
        <span className="inline-flex min-h-11 items-center rounded-md bg-muted px-4 text-body text-muted-foreground">
          2개를 선택하세요
        </span>
      )}
    </div>
    <ul className="mt-4 flex flex-col gap-3">
      {data.results.map(({ status, product, reasons }) => <li key={product.source_product_id} className="rounded-xl border border-border bg-card p-4">
        <div className="flex items-start justify-between gap-3">
          <span className="inline-flex rounded-full border border-border px-2 py-1 text-caption text-foreground">{STATUS_LABEL[status]}</span>
          <label className="flex min-h-11 items-center gap-2 text-caption text-foreground">
            <input
              type="checkbox"
              checked={activeSelectedIds.includes(product.source_product_id)}
              disabled={activeSelectedIds.length >= 2 && !activeSelectedIds.includes(product.source_product_id)}
              aria-label={`${product.name} 비교 선택`}
              onChange={() => toggleComparison(product.source_product_id)}
              className="size-5 accent-primary"
            />
            비교 선택
          </label>
        </div>
        <h2 className="mt-2 text-title text-foreground">{product.name}</h2><p className="mt-1 text-caption text-muted-foreground">{product.offering_institution ?? "제공기관 확인 필요"}</p>
        <dl className="mt-3 grid grid-cols-2 gap-2 text-body"><div><dt className="text-caption text-muted-foreground">공식 용도</dt><dd>{product.purpose_text ?? "확인 필요"}</dd></div><div><dt className="text-caption text-muted-foreground">금리 원문</dt><dd>{product.interest_rate_text ?? "확인 필요"}</dd></div><div><dt className="text-caption text-muted-foreground">한도 원문</dt><dd>{product.loan_limit_text ?? "확인 필요"}</dd></div><div><dt className="text-caption text-muted-foreground">대상 원문</dt><dd>{product.eligibility.target_text ?? "확인 필요"}</dd></div></dl>
        <ul className="mt-3 border-t border-border pt-3 text-caption text-muted-foreground">{reasons.map((reason) => <li key={reason.rule}>• {reason.message}</li>)}</ul>
        <div className="mt-3 flex flex-wrap gap-x-4">
          <Link href={`/products/${encodeURIComponent(product.source_product_id)}`} className="inline-flex min-h-11 items-center text-body font-medium text-primary underline underline-offset-2">상세 보기</Link>
          <a href={product.source_reference} target="_blank" rel="noreferrer" className="inline-flex min-h-11 items-center text-body font-medium text-primary underline underline-offset-2">공식 데이터 출처 보기</a>
        </div>
      </li>)}
    </ul><DisclaimerNote>{data.disclaimer}</DisclaimerNote>
  </>;
}
