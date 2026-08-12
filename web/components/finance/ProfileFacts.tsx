import type { FinancialProfile } from "@/lib/api/contracts";
import { formatWon } from "@/lib/format/money";
import {
  AGE_BAND_LABEL,
  CREDIT_BAND_LABEL,
  EMPLOYMENT_LABEL,
  GOAL_LABEL,
} from "@/lib/format/labels";

/** 사용자가 입력한 값을 그대로 되돌려 보여준다. 어떤 값이 판단에 쓰였는지 확인할 수 있게. */
export function ProfileFacts({ profile }: { profile: FinancialProfile }) {
  const rows: Array<{ label: string; value: string }> = [
    { label: "연령대", value: AGE_BAND_LABEL[profile.ageBand] },
    { label: "하는 일", value: EMPLOYMENT_LABEL[profile.employmentStatus] },
    { label: "매달 손에 들어오는 돈", value: formatWon(profile.monthlyNetIncome) },
    { label: "매달 나가는 고정지출", value: formatWon(profile.monthlyFixedExpenses) },
    { label: "매달 쓰는 생활비", value: formatWon(profile.monthlyVariableExpenses) },
    { label: "바로 쓸 수 있는 돈", value: formatWon(profile.liquidAssets) },
    { label: "남은 대출 총액", value: formatWon(profile.totalDebt) },
    { label: "매달 갚는 돈", value: formatWon(profile.monthlyDebtPayment) },
    { label: "신용점수 구간", value: CREDIT_BAND_LABEL[profile.creditScoreBand] },
    { label: "지금 목표", value: GOAL_LABEL[profile.goal] },
  ];

  return (
    <dl className="divide-y divide-border rounded-lg border border-border bg-card">
      {rows.map((row) => (
        <div
          key={row.label}
          className="flex items-baseline justify-between gap-3 px-4 py-3"
        >
          <dt className="text-body text-muted-foreground">{row.label}</dt>
          <dd className="text-body tabular-nums text-foreground">{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}
