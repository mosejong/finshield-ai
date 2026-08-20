"use client";

import { useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import type {
  DepositCheck,
  DepositRiskRequest,
  DepositRiskResponse,
  LeaseStage,
} from "@/lib/api/contracts";
import { checkDepositRisk } from "@/lib/api/housing";
import {
  DEPOSIT_CHECK_OPTIONS,
  LEASE_STAGE_OPTIONS,
  isBlankAmount,
  manwonToKrw,
} from "@/lib/format/housing";
import { formatWonShort } from "@/lib/format/money";
import { SectionHeading } from "@/components/common/SectionHeading";
import { DisclaimerNote } from "@/components/common/DisclaimerNote";
import { DepositRiskResult } from "@/components/housing/DepositRiskResult";
import { cn } from "@/lib/utils";

/**
 * 전세보증금 위험 점검 입력.
 *
 * 이 화면도 프로필과 로그인 없이 동작한다. 계약서에 도장을 찍기 직전인 사람에게
 * 회원가입을 먼저 요구할 이유가 없다.
 *
 * 판정·비율·날짜는 전부 백엔드가 낸다. 여기서는 만원 단위를 원으로 바꾸고
 * 비어 있는 칸을 `null` 로 보내는 것까지만 한다.
 */

/** 브라우저가 있는 곳의 오늘. `toISOString()` 은 UTC 라서 쓰지 않는다. */
function todayLocal(): string {
  const now = new Date();
  const month = `${now.getMonth() + 1}`.padStart(2, "0");
  const day = `${now.getDate()}`.padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

type AmountFieldProps = {
  id: string;
  label: string;
  help: string;
  value: string;
  onChange: (value: string) => void;
  optional?: boolean;
};

function AmountField({
  id,
  label,
  help,
  value,
  onChange,
  optional = false,
}: AmountFieldProps) {
  const krw = manwonToKrw(value);
  const invalid = !isBlankAmount(value) && krw === null;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-body font-medium text-foreground">
        {label}
        {optional ? (
          <span className="ml-1.5 text-caption font-normal text-muted-foreground">
            모르면 비워 두세요
          </span>
        ) : null}
      </label>

      <div className="flex items-center gap-2">
        <input
          id={id}
          inputMode="numeric"
          value={value}
          onChange={(event) => onChange(event.target.value.slice(0, 12))}
          aria-describedby={`${id}-help`}
          aria-invalid={invalid}
          placeholder="예) 20000"
          className="min-h-12 w-full rounded-md border border-input bg-background px-3 text-body tabular-nums text-foreground placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none"
        />
        <span className="shrink-0 text-body text-muted-foreground">만원</span>
      </div>

      <p id={`${id}-help`} className="text-caption text-muted-foreground">
        {invalid
          ? "숫자만 넣어 주세요."
          : krw === null
            ? help
            : `${formatWonShort(krw)} 으로 계산합니다.`}
      </p>
    </div>
  );
}

export function DepositRiskForm() {
  const [stage, setStage] = useState<LeaseStage>("before_contract");
  const [deposit, setDeposit] = useState("");
  const [price, setPrice] = useState("");
  const [lien, setLien] = useState("");
  const [checks, setChecks] = useState<ReadonlySet<DepositCheck>>(new Set());
  const [moveInDate, setMoveInDate] = useState("");

  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<{
    message: string;
    hint?: string;
  } | null>(null);
  const [result, setResult] = useState<DepositRiskResponse | null>(null);
  /** 결과가 어떤 입력에서 나왔는지. 폼을 고쳐도 결과 화면이 흔들리지 않는다. */
  const [answered, setAnswered] = useState<DepositCheck[]>([]);

  const resultRef = useRef<HTMLDivElement>(null);

  const depositKrw = manwonToKrw(deposit);
  const canSubmit = depositKrw !== null && !pending;
  const reportedMoveIn = checks.has("move_in_reported");

  function toggleCheck(value: DepositCheck) {
    setChecks((previous) => {
      const next = new Set(previous);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return next;
    });
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (depositKrw === null || pending) return;

    setPending(true);
    setFailure(null);

    const completedChecks = DEPOSIT_CHECK_OPTIONS.filter((option) =>
      checks.has(option.value),
    ).map((option) => option.value);

    const request: DepositRiskRequest = {
      stage,
      deposit_krw: depositKrw,
      property_price_krw: manwonToKrw(price),
      senior_lien_krw: manwonToKrw(lien),
      completed_checks: completedChecks,
      // 전입신고를 표시하지 않았으면 날짜를 보내지 않는다. 신고하지 않은 날짜는
      // 대항력 발생일 계산에 쓰일 수 없다.
      move_in_reported_on: reportedMoveIn && moveInDate ? moveInDate : null,
    };

    const outcome = await checkDepositRisk(request);
    setPending(false);

    if (!outcome.ok) {
      setResult(null);
      setFailure({ message: outcome.message, hint: outcome.hint });
      return;
    }

    setResult(outcome.result);
    setAnswered(completedChecks);
    requestAnimationFrame(() => {
      resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  return (
    <>
      <form onSubmit={handleSubmit} className="flex flex-col gap-7">
        <section aria-labelledby="deposit-stage">
          <SectionHeading>
            <span id="deposit-stage">지금 어디까지 진행됐나요</span>
          </SectionHeading>
          <p className="mb-3 text-caption text-muted-foreground">
            같은 조건이라도 계약 전과 잔금 뒤에 할 수 있는 일이 다릅니다.
          </p>

          <div
            role="radiogroup"
            aria-label="계약 진행 단계"
            className="flex flex-col gap-2"
          >
            {LEASE_STAGE_OPTIONS.map((option) => {
              const selected = option.value === stage;
              return (
                <label
                  key={option.value}
                  className={cn(
                    "flex min-h-14 cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors",
                    selected
                      ? "border-primary bg-secondary"
                      : "border-border bg-card hover:bg-secondary",
                  )}
                >
                  <input
                    type="radio"
                    name="lease-stage"
                    value={option.value}
                    checked={selected}
                    onChange={() => setStage(option.value)}
                    className="mt-1 size-4 shrink-0 accent-[var(--primary)]"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block text-body font-medium text-foreground">
                      {option.label}
                    </span>
                    <span className="mt-0.5 block text-caption text-muted-foreground">
                      {option.description}
                    </span>
                  </span>
                </label>
              );
            })}
          </div>
        </section>

        <section aria-labelledby="deposit-amounts">
          <SectionHeading>
            <span id="deposit-amounts">금액</span>
          </SectionHeading>

          <div className="flex flex-col gap-5">
            <AmountField
              id="deposit-krw"
              label="보증금"
              help="계약서에 적힌 보증금 전액을 넣어 주세요."
              value={deposit}
              onChange={setDeposit}
            />
            <AmountField
              id="property-price-krw"
              label="주택가격"
              help="시세나 공시가격 등 확인하신 값을 넣어 주세요."
              value={price}
              onChange={setPrice}
              optional
            />
            <AmountField
              id="senior-lien-krw"
              label="선순위 채권최고액"
              help="등기부 을구의 근저당권 채권최고액 합계입니다."
              value={lien}
              onChange={setLien}
              optional
            />
          </div>

          <p className="mt-4 rounded-md bg-muted p-3 text-caption text-muted-foreground">
            모르는 칸은 비워 두세요.{" "}
            <strong className="font-semibold text-foreground">
              비워 두면 0원으로 계산하지 않고 &ldquo;아직 모름&rdquo;으로 둡니다.
            </strong>{" "}
            모르는 값을 0으로 놓으면 등기부를 아직 안 본 사람에게 가장 안심되는
            숫자가 나오기 때문입니다.
          </p>
        </section>

        <section aria-labelledby="deposit-checks">
          <SectionHeading>
            <span id="deposit-checks">이미 마치신 것</span>
          </SectionHeading>
          <p className="mb-3 text-caption text-muted-foreground">
            해당하는 것만 고르세요. 아직 안 하신 게 있어도 지금 하시면 됩니다.
          </p>

          <div className="flex flex-col gap-2">
            {DEPOSIT_CHECK_OPTIONS.map((option) => {
              const selected = checks.has(option.value);
              return (
                <label
                  key={option.value}
                  className={cn(
                    "flex min-h-14 cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors",
                    selected
                      ? "border-primary bg-secondary"
                      : "border-border bg-card hover:bg-secondary",
                  )}
                >
                  <input
                    type="checkbox"
                    checked={selected}
                    onChange={() => toggleCheck(option.value)}
                    className="mt-1 size-4 shrink-0 accent-[var(--primary)]"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block text-body font-medium text-foreground">
                      {option.label}
                    </span>
                    <span className="mt-0.5 block text-caption text-muted-foreground">
                      {option.description}
                    </span>
                  </span>
                </label>
              );
            })}
          </div>

          {reportedMoveIn ? (
            <div className="mt-3 flex flex-col gap-1.5 rounded-lg border border-border bg-card p-3">
              <label
                htmlFor="move-in-reported-on"
                className="text-body font-medium text-foreground"
              >
                전입신고를 마친 날
                <span className="ml-1.5 text-caption font-normal text-muted-foreground">
                  모르면 비워 두세요
                </span>
              </label>
              <input
                id="move-in-reported-on"
                type="date"
                value={moveInDate}
                max={todayLocal()}
                onChange={(event) => setMoveInDate(event.target.value)}
                aria-describedby="move-in-reported-on-help"
                className="min-h-12 w-full rounded-md border border-input bg-background px-3 text-body tabular-nums text-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none"
              />
              <p
                id="move-in-reported-on-help"
                className="text-caption text-muted-foreground"
              >
                대항력이 언제부터 생기는지 알려드리는 데만 씁니다.
              </p>
            </div>
          ) : null}
        </section>

        {failure ? (
          <div
            role="alert"
            className="rounded-lg border border-risk-medium-border bg-risk-medium-bg p-4"
          >
            <p className="text-body font-medium text-risk-medium">
              {failure.message}
            </p>
            {failure.hint ? (
              <p className="mt-1 text-caption text-muted-foreground">
                {failure.hint}
              </p>
            ) : null}
            <p className="mt-2 text-caption text-muted-foreground">
              점검하지 못했다고 해서 계약에 문제가 없다는 뜻은 아닙니다. 등기부
              확인과 전입신고·확정일자는 이 화면과 상관없이 그대로 하셔야 합니다.
            </p>
          </div>
        ) : null}

        <div className="sticky bottom-[calc(4.5rem+env(safe-area-inset-bottom))] flex flex-col gap-2 border-t border-border bg-background py-3 lg:static lg:border-0 lg:py-0">
          <button
            type="submit"
            disabled={!canSubmit}
            aria-busy={pending}
            className="inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-md bg-primary px-4 text-body font-semibold text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-45"
          >
            {pending ? (
              <>
                <Loader2 aria-hidden className="size-4 animate-spin" />
                점검하는 중…
              </>
            ) : (
              "점검하기"
            )}
          </button>

          <p className="text-center text-caption text-muted-foreground">
            {depositKrw === null
              ? "보증금을 넣으면 점검할 수 있습니다."
              : "입력하신 값은 점검에만 쓰이고 저장하지 않습니다."}
          </p>
        </div>
      </form>

      <div ref={resultRef} className="scroll-mt-4">
        {result ? (
          <div className="mt-10 border-t border-border pt-8">
            <DepositRiskResult result={result} completedChecks={answered} />
          </div>
        ) : (
          <DisclaimerNote>
            이 점검은 입력하신 값에 대한 규칙 기반 확인이며 법률 자문이나 계약
            안전 보증이 아닙니다. 주소·임대인 이름·주민등록번호는 받지 않습니다.
          </DisclaimerNote>
        )}
      </div>
    </>
  );
}
