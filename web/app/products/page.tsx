import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { DisclaimerNote } from "@/components/common/DisclaimerNote";

/**
 * 금융상품 영역 자리표시.
 *
 * 비어 있는 화면을 그냥 두지 않고 "왜 아직 없는지"를 적는다.
 * 상품명·금리는 공식 API 연동 전까지 어떤 예시도 만들지 않는다.
 * (CLAUDE.md — Never fabricate products, rates, eligibility)
 */
export const metadata = {
  title: "금융상품 | FinShield",
};

const PLANNED = [
  {
    title: "대출·정책상품 탐색",
    detail: "서민금융진흥원·금융위원회 공식 상품정보를 그대로 보여줍니다.",
  },
  {
    title: "대출 부담 비교",
    detail: "지금 갚는 금액과 갈아탔을 때의 금액을 나란히 놓고 비교합니다.",
  },
  {
    title: "What-if 시뮬레이션",
    detail: "금액·기간을 바꿔가며 매달 부담이 어떻게 달라지는지 확인합니다.",
  },
];

export default function ProductsPage() {
  return (
    <AppShell>
      <PageHeader
        title="금융상품"
        description="아직 준비 중입니다. 공식 상품정보 연동이 끝나기 전에는 상품명이나 금리를 보여주지 않습니다."
        backHref="/"
      />

      <ul className="flex flex-col gap-2">
        {PLANNED.map((item) => (
          <li
            key={item.title}
            className="rounded-lg border border-dashed border-border bg-card p-4"
          >
            <p className="text-body font-medium text-foreground">{item.title}</p>
            <p className="mt-1 text-caption text-muted-foreground">
              {item.detail}
            </p>
          </li>
        ))}
      </ul>

      <p className="mt-6 text-body text-muted-foreground">
        그 사이에 할 수 있는 일:{" "}
        <Link
          href="/check"
          className="font-medium text-primary underline underline-offset-2"
        >
          받은 연락이 안전한지 확인하기
        </Link>
      </p>

      <DisclaimerNote>
        상품 정보는 공식 출처에서 받아온 값만 표시할 예정이며, 추정치나 예시
        금리를 만들어 보여주지 않습니다.
      </DisclaimerNote>
    </AppShell>
  );
}
