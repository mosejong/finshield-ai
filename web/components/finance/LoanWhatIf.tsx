"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import {
  LoanScenarioInputSchema,
  type LoanSimulationResponse,
  type RepaymentType,
} from "@/lib/api/contracts";
import {
  compareLoanScenarios,
  type LoanWhatIfComparison,
} from "@/lib/api/loans";
import { formatWon, formatWonShort } from "@/lib/format/money";
import { DisclaimerNote } from "@/components/common/DisclaimerNote";

const REPAYMENT_LABEL: Record<RepaymentType, string> = {
  equal_principal_and_interest: "원리금균등",
  equal_principal: "원금균등",
};

const ASSUMPTION_LABEL: Record<string, string> = {
  "annual_interest_rate is a nominal annual percentage divided by 12":
    "연이율을 12개월로 나눈 월 이율을 사용합니다.",
  "schedule amounts are rounded to 0.01 using ROUND_HALF_UP":
    "각 회차 금액은 소수 둘째 자리에서 일반적인 반올림 방식으로 계산합니다.",
  "the final installment is adjusted to clear the remaining principal":
    "마지막 회차는 남은 원금이 0이 되도록 조정됩니다.",
  "fees, taxes, insurance, and early-repayment charges are excluded":
    "수수료·세금·보험료·중도상환수수료는 포함하지 않습니다.",
  "all monetary values use the same currency unit as principal":
    "모든 금액은 입력한 원금과 같은 통화 단위를 사용합니다.",
};

type Draft = {
  principal: number;
  currentRate: number;
  alternativeRate: number;
  months: number;
  repaymentType: RepaymentType;
};

const DEFAULTS: Draft = {
  principal: 10_000_000,
  currentRate: 5.5,
  alternativeRate: 4.0,
  months: 36,
  repaymentType: "equal_principal_and_interest",
};

function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  step,
  unit,
  hint,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
  step: number;
  unit: string;
  hint?: string;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-body text-foreground">{label}</span>
      <div className="flex items-center gap-2">
        <input
          type="number"
          inputMode="decimal"
          min={min}
          max={max}
          step={step}
          value={value || ""}
          onChange={(event) => onChange(Number(event.target.value))}
          required
          className="min-h-11 w-full rounded-md border border-input bg-background px-3 text-body tabular-nums text-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none"
        />
        <span className="shrink-0 text-body text-muted-foreground">{unit}</span>
      </div>
      {hint ? <span className="text-caption text-muted-foreground">{hint}</span> : null}
    </label>
  );
}

function ResultCard({
  title,
  result,
}: {
  title: string;
  result: LoanSimulationResponse;
}) {
  const firstPayment = result.schedule[0];
  const lastPayment = result.schedule[result.schedule.length - 1];
  const paymentLabel = result.monthly_payment ? "정기 월 납입액" : "첫 달 납입액";
  const paymentValue = result.monthly_payment ?? firstPayment.payment;

  return (
    <article className="rounded-xl border border-border bg-card p-4">
      <p className="text-caption font-medium text-primary">{title}</p>
      <h2 className="mt-1 text-title text-foreground">
        연 {result.annual_interest_rate}% · {REPAYMENT_LABEL[result.repayment_type]}
      </h2>
      <dl className="mt-4 flex flex-col gap-3">
        <div className="flex items-baseline justify-between gap-3">
          <dt className="text-caption text-muted-foreground">{paymentLabel}</dt>
          <dd className="text-title tabular-nums text-foreground">
            {formatWon(Number(paymentValue))}
          </dd>
        </div>
        <div className="flex items-baseline justify-between gap-3">
          <dt className="text-caption text-muted-foreground">마지막 달 납입액</dt>
          <dd className="text-body tabular-nums text-foreground">
            {formatWon(Number(lastPayment.payment))}
          </dd>
        </div>
        <div className="flex items-baseline justify-between gap-3 border-t border-border pt-3">
          <dt className="text-caption text-muted-foreground">총 이자</dt>
          <dd className="text-body tabular-nums text-foreground">
            {formatWon(Number(result.total_interest))}
          </dd>
        </div>
        <div className="flex items-baseline justify-between gap-3">
          <dt className="text-caption text-muted-foreground">총 상환액</dt>
          <dd className="text-body tabular-nums text-foreground">
            {formatWon(Number(result.total_repayment))}
          </dd>
        </div>
      </dl>
      <p className="mt-4 text-caption text-muted-foreground">
        {result.months}개월 일정 · 첫 달 원금 {formatWon(Number(firstPayment.principal_payment))}, 이자 {formatWon(Number(firstPayment.interest_payment))}
      </p>
    </article>
  );
}

export function LoanWhatIf() {
  const [draft, setDraft] = useState<Draft>(DEFAULTS);
  const [comparison, setComparison] = useState<LoanWhatIfComparison | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (pending) return;

    const shared = {
      principal: draft.principal,
      months: draft.months,
      repaymentType: draft.repaymentType,
    };
    const current = LoanScenarioInputSchema.safeParse({
      ...shared,
      annualInterestRate: draft.currentRate,
    });
    const alternative = LoanScenarioInputSchema.safeParse({
      ...shared,
      annualInterestRate: draft.alternativeRate,
    });

    if (!current.success || !alternative.success) {
      setComparison(null);
      setError("원금·금리·기간을 허용 범위에 맞게 입력해 주세요.");
      return;
    }

    setPending(true);
    setError(null);
    setComparison(null);
    try {
      setComparison(await compareLoanScenarios(current.data, alternative.data));
    } catch {
      setError(
        "두 조건의 결과를 모두 확인하지 못했습니다. 결과가 없다고 유리하거나 안전한 조건이라는 뜻은 아닙니다.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      <form onSubmit={handleSubmit} className="rounded-xl border border-border bg-card p-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <NumberField
              label="비교할 대출 원금"
              value={draft.principal}
              onChange={(principal) => setDraft((previous) => ({ ...previous, principal }))}
              min={1}
              max={999_999_999_999_999.99}
              step={1}
              unit="원"
              hint={draft.principal > 0 ? formatWonShort(draft.principal) : "0원보다 큰 금액을 입력하세요"}
            />
          </div>
          <NumberField
            label="현재 연 금리"
            value={draft.currentRate}
            onChange={(currentRate) => setDraft((previous) => ({ ...previous, currentRate }))}
            min={0}
            max={100}
            step={0.01}
            unit="%"
          />
          <NumberField
            label="바꿔볼 연 금리"
            value={draft.alternativeRate}
            onChange={(alternativeRate) => setDraft((previous) => ({ ...previous, alternativeRate }))}
            min={0}
            max={100}
            step={0.01}
            unit="%"
          />
          <NumberField
            label="남은 상환 기간"
            value={draft.months}
            onChange={(months) => setDraft((previous) => ({ ...previous, months }))}
            min={1}
            max={600}
            step={1}
            unit="개월"
          />
          <label className="flex flex-col gap-1.5">
            <span className="text-body text-foreground">상환 방식</span>
            <select
              value={draft.repaymentType}
              onChange={(event) => setDraft((previous) => ({
                ...previous,
                repaymentType: event.target.value as RepaymentType,
              }))}
              className="min-h-11 rounded-md border border-input bg-background px-3 text-body text-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none"
            >
              <option value="equal_principal_and_interest">원리금균등</option>
              <option value="equal_principal">원금균등</option>
            </select>
          </label>
        </div>

        {error ? (
          <p role="alert" className="mt-4 rounded-lg border border-risk-medium-border bg-risk-medium-bg p-3 text-body text-risk-medium">
            {error}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={pending}
          aria-busy={pending}
          className="mt-5 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-md bg-primary px-4 text-body font-semibold text-primary-foreground disabled:opacity-60"
        >
          {pending ? <Loader2 aria-hidden className="size-4 animate-spin" /> : null}
          {pending ? "두 조건 계산 중" : "두 조건 비교하기"}
        </button>
      </form>

      {comparison ? (
        <section className="mt-6" aria-labelledby="loan-comparison-title">
          {/* 결과가 화면 아래에 새로 나타나므로 스크린리더에 한 번 알린다 */}
          <p role="status" className="sr-only">
            두 조건의 계산 결과가 준비되었습니다.
          </p>
          <h2 id="loan-comparison-title" className="text-title text-foreground">계산 결과</h2>
          <p className="mt-1 text-caption text-muted-foreground">
            두 조건을 같은 계산 기준으로 각각 계산해 나란히 보여줍니다.
          </p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <ResultCard title="현재 조건" result={comparison.current} />
            <ResultCard title="바꾼 조건" result={comparison.alternative} />
          </div>
          <div className="mt-4 rounded-lg bg-muted p-4">
            <h3 className="text-body font-semibold text-foreground">계산 가정</h3>
            <ul className="mt-2 flex flex-col gap-1 text-caption text-muted-foreground">
              {comparison.current.assumptions.map((assumption) => (
                <li key={assumption}>· {ASSUMPTION_LABEL[assumption] ?? assumption}</li>
              ))}
            </ul>
          </div>
        </section>
      ) : null}

      <DisclaimerNote>
        이 결과는 입력한 조건을 같은 방식으로 비교하기 위한 시뮬레이션이며 금융기관의 공식 상환표가 아닙니다. 실제 납입일·일수 계산·거치기간·수수료·세금·보험료는 금융기관에서 확인하세요.
      </DisclaimerNote>
    </>
  );
}
