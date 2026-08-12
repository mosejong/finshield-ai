import type { BackendProduct } from "@/lib/api/contracts";


export type ProductFieldDefinition = {
  label: string;
  value: (product: BackendProduct) => string | null;
};

export type ProductFieldGroup = {
  id: string;
  title: string;
  fields: ProductFieldDefinition[];
};

export const PRODUCT_FIELD_GROUPS: ProductFieldGroup[] = [
  {
    id: "basic",
    title: "상품 기본 정보",
    fields: [
      { label: "상품 분류", value: (product) => product.category },
      { label: "세부 분류", value: (product) => product.category_detail },
      { label: "공식 용도", value: (product) => product.purpose_text },
      { label: "제공기관", value: (product) => product.offering_institution },
      { label: "취급기관", value: (product) => product.handling_institution_text },
      { label: "신청 방법", value: (product) => product.application_method_text },
    ],
  },
  {
    id: "terms",
    title: "금리·한도·상환 원문",
    fields: [
      { label: "금리 유형", value: (product) => product.interest_rate_type },
      { label: "금리", value: (product) => product.interest_rate_text },
      { label: "대출 한도", value: (product) => product.loan_limit_text },
      { label: "최대 총 기간", value: (product) => product.max_total_term_text },
      { label: "최대 거치기간", value: (product) => product.max_grace_term_text },
      { label: "최대 상환기간", value: (product) => product.max_repayment_term_text },
      { label: "상환 방법", value: (product) => product.repayment_method_text },
    ],
  },
  {
    id: "eligibility",
    title: "지원 대상·조건 원문",
    fields: [
      { label: "지원 대상", value: (product) => product.eligibility.target_text },
      { label: "상세 조건", value: (product) => product.eligibility.detailed_conditions_text },
      { label: "연령 조건", value: (product) => product.eligibility.age_text },
      { label: "소득 조건", value: (product) => product.eligibility.income_text },
      { label: "연소득 조건", value: (product) => product.eligibility.annual_income_text },
      { label: "신용 조건", value: (product) => product.eligibility.credit_score_text },
      { label: "지역 조건", value: (product) => product.eligibility.region_text },
    ],
  },
];


export function officialText(value: string | null): string {
  return value?.trim() || "확인 필요";
}


export function ProductFacts({ product }: { product: BackendProduct }) {
  return (
    <div className="flex flex-col gap-6">
      {PRODUCT_FIELD_GROUPS.map((group) => (
        <section key={group.id} aria-labelledby={`facts-${group.id}`}>
          <h3 id={`facts-${group.id}`} className="text-title text-foreground">
            {group.title}
          </h3>
          <dl className="mt-3 divide-y divide-border rounded-xl border border-border bg-card px-4">
            {group.fields.map((field) => (
              <div key={field.label} className="grid gap-1 py-3 sm:grid-cols-[9rem_1fr] sm:gap-4">
                <dt className="text-caption text-muted-foreground">{field.label}</dt>
                <dd className="whitespace-pre-wrap break-words text-body text-foreground">
                  {officialText(field.value(product))}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      ))}
    </div>
  );
}
