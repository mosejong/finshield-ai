"use client";

import { useState, type ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import {
  FinancialProfileSchema,
  type FinancialProfile,
} from "@/lib/api/contracts";
import { saveProfile } from "@/lib/store/profile-store";
import { formatWonShort } from "@/lib/format/money";
import {
  AGE_BAND_LABEL,
  CREDIT_BAND_LABEL,
  EMPLOYMENT_LABEL,
  GOAL_LABEL,
  PERSONA_LABEL,
  optionsOf,
} from "@/lib/format/labels";

/**
 * 온보딩 폼 (최소 구현).
 *
 * 검증은 contracts 의 zod 스키마로만 한다. 적격성 판정이나 금융 계산은 하지 않는다.
 * 정확한 나이·신용점수 대신 band 를 받는다. (docs/09-financial-profile-schema.md)
 */

const DEFAULTS: FinancialProfile = {
  ageBand: "20_29",
  employmentStatus: "employed",
  householdSize: 1,
  dependentsCount: 0,
  monthlyNetIncome: 0,
  monthlyFixedExpenses: 0,
  monthlyVariableExpenses: 0,
  liquidAssets: 0,
  emergencyFundTargetMonths: 3,
  totalDebt: 0,
  monthlyDebtPayment: 0,
  creditScoreBand: "unknown",
  businessOwner: false,
  goal: "emergency_cash",
  persona: "early_career",
};

function Step({
  index,
  title,
  hint,
  children,
}: {
  index: number;
  title: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <fieldset className="rounded-lg border border-border bg-card p-4">
      <legend className="px-1 text-caption font-medium text-muted-foreground">
        {index} / 5
      </legend>
      <h2 className="text-title text-foreground">{title}</h2>
      {hint ? (
        <p className="mt-1 text-caption text-muted-foreground">{hint}</p>
      ) : null}
      <div className="mt-4 flex flex-col gap-4">{children}</div>
    </fieldset>
  );
}

function SelectField<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: ReadonlyArray<{ value: T; label: string }>;
  onChange: (value: T) => void;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-body text-foreground">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value as T)}
        className="min-h-11 rounded-md border border-input bg-background px-3 text-body text-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function MoneyField({
  label,
  value,
  onChange,
  hint,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  hint?: string;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-body text-foreground">{label}</span>
      <div className="flex items-center gap-2">
        <input
          type="number"
          inputMode="numeric"
          min={0}
          step={10000}
          value={value === 0 ? "" : value}
          placeholder="0"
          onChange={(event) => onChange(Number(event.target.value) || 0)}
          className="min-h-11 w-full rounded-md border border-input bg-background px-3 text-body tabular-nums text-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none"
        />
        <span className="shrink-0 text-body text-muted-foreground">원</span>
      </div>
      <span className="text-caption text-muted-foreground">
        {value > 0 ? formatWonShort(value) : (hint ?? "대략적인 금액이면 충분합니다")}
      </span>
    </label>
  );
}

function CountField({
  label,
  value,
  onChange,
  max = 10,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  max?: number;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-body text-foreground">{label}</span>
      <input
        type="number"
        inputMode="numeric"
        min={0}
        max={max}
        value={value}
        onChange={(event) => onChange(Number(event.target.value) || 0)}
        className="min-h-11 w-24 rounded-md border border-input bg-background px-3 text-body tabular-nums text-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none"
      />
    </label>
  );
}

export function ProfileForm({ initial }: { initial: FinancialProfile | null }) {
  const router = useRouter();
  const [draft, setDraft] = useState<FinancialProfile>(initial ?? DEFAULTS);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  function set<K extends keyof FinancialProfile>(
    key: K,
    value: FinancialProfile[K],
  ) {
    setDraft((previous) => ({ ...previous, [key]: value }));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (pending) return;

    const parsed = FinancialProfileSchema.safeParse(draft);
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "입력한 값 중 확인이 필요한 항목이 있습니다.");
      return;
    }
    if (parsed.data.householdSize < 1) {
      setError("가구원 수는 1명 이상이어야 합니다.");
      return;
    }

    setPending(true);
    setError(null);
    try {
      await saveProfile(parsed.data);
      router.push("/profile");
    } catch {
      setError(
        "금융상태를 저장하지 못했습니다. 서버 연결을 확인한 뒤 다시 시도해 주세요.",
      );
      setPending(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <Step index={1} title="나에 대해" hint="정확한 나이 대신 구간만 받습니다.">
        <SelectField
          label="연령대"
          value={draft.ageBand}
          options={optionsOf(AGE_BAND_LABEL)}
          onChange={(value) => set("ageBand", value)}
        />
        <SelectField
          label="하는 일"
          value={draft.employmentStatus}
          options={optionsOf(EMPLOYMENT_LABEL)}
          onChange={(value) => set("employmentStatus", value)}
        />
        <SelectField
          label="나를 가장 잘 설명하는 것"
          value={draft.persona}
          options={optionsOf(PERSONA_LABEL)}
          onChange={(value) => set("persona", value)}
        />
        <CountField
          label="함께 사는 사람 수 (본인 포함)"
          value={draft.householdSize}
          onChange={(value) => set("householdSize", value)}
        />
      </Step>

      <Step index={2} title="버는 돈">
        <MoneyField
          label="매달 손에 들어오는 돈"
          value={draft.monthlyNetIncome}
          onChange={(value) => set("monthlyNetIncome", value)}
          hint="세금을 뗀 실수령액입니다"
        />
        <CountField
          label="비상금으로 준비하고 싶은 기간 (개월)"
          value={draft.emergencyFundTargetMonths}
          onChange={(value) => set("emergencyFundTargetMonths", value)}
          max={60}
        />
      </Step>

      <Step index={3} title="쓰는 돈">
        <MoneyField
          label="매달 나가는 고정지출"
          value={draft.monthlyFixedExpenses}
          onChange={(value) => set("monthlyFixedExpenses", value)}
          hint="월세, 보험료, 통신비처럼 매달 같은 금액"
        />
        <MoneyField
          label="매달 쓰는 생활비"
          value={draft.monthlyVariableExpenses}
          onChange={(value) => set("monthlyVariableExpenses", value)}
          hint="식비, 교통비처럼 달마다 달라지는 금액"
        />
      </Step>

      <Step index={4} title="빚">
        <MoneyField
          label="남은 대출 총액"
          value={draft.totalDebt}
          onChange={(value) => set("totalDebt", value)}
          hint="없으면 비워 두세요"
        />
        <MoneyField
          label="매달 갚는 돈"
          value={draft.monthlyDebtPayment}
          onChange={(value) => set("monthlyDebtPayment", value)}
          hint="원금과 이자를 합한 금액"
        />
      </Step>

      <Step index={5} title="지금 목표">
        <MoneyField
          label="바로 쓸 수 있는 돈"
          value={draft.liquidAssets}
          onChange={(value) => set("liquidAssets", value)}
          hint="예금처럼 필요할 때 꺼낼 수 있는 돈"
        />
        <SelectField
          label="가장 하고 싶은 것"
          value={draft.goal}
          options={optionsOf(GOAL_LABEL)}
          onChange={(value) => set("goal", value)}
        />
        <label className="flex min-h-11 items-center gap-3 text-body text-foreground">
          <input
            type="checkbox"
            checked={draft.businessOwner}
            onChange={(event) => set("businessOwner", event.target.checked)}
            className="size-5 rounded border-input"
          />
          현재 사업체를 운영하고 있어요
        </label>
        <SelectField
          label="신용점수 구간"
          value={draft.creditScoreBand}
          options={optionsOf(CREDIT_BAND_LABEL)}
          onChange={(value) => set("creditScoreBand", value)}
        />
      </Step>

      {error ? (
        <p
          role="alert"
          className="rounded-md border border-risk-medium-border bg-risk-medium-bg px-3 py-2 text-caption text-risk-medium"
        >
          {error}
        </p>
      ) : null}

      <div className="sticky bottom-[calc(4.5rem+env(safe-area-inset-bottom))] flex flex-col gap-2 border-t border-border bg-background py-3 lg:static lg:border-0 lg:py-0">
        <button
          type="submit"
          disabled={pending}
          className="inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-md bg-primary px-4 text-body font-semibold text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-45"
        >
          {pending ? (
            <>
              <Loader2 aria-hidden className="size-4 animate-spin" />
              저장하는 중…
            </>
          ) : (
            "저장하기"
          )}
        </button>
        <p className="text-center text-caption text-muted-foreground">
          서버에는 최소 금융정보만 저장하고, 브라우저에는 프로필 식별자만 남깁니다.
        </p>
      </div>
    </form>
  );
}
