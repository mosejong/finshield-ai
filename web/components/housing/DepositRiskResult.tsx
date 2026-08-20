import { ExternalLink } from "lucide-react";
import type { DepositCheck, DepositRiskResponse } from "@/lib/api/contracts";
import { riskStrengthLabel, riskStyle } from "@/lib/format/risk";
import {
  DEPOSIT_CHECK_OPTIONS,
  ratioBandLabel,
  ratioBandTextClass,
} from "@/lib/format/housing";
import { SectionHeading } from "@/components/common/SectionHeading";
import { DisclaimerNote } from "@/components/common/DisclaimerNote";

/**
 * 점검 결과.
 *
 * 순서는 사기 분석 결과 화면과 같은 규칙을 따른다.
 *   위험 수준 → 확인이 필요한 항목 → 왜 그런지(숫자·보호 장치)
 *   → 이미 마친 확인 → 지금 해야 할 행동 → 공식 근거
 *
 * 여기서 판정하지 않는다. 백엔드가 준 값을 그대로 배치할 뿐이다.
 */

const PRIORITY_LABEL: Record<number, string> = {
  1: "먼저",
  2: "그다음",
  3: "여유가 되면",
};

const PRIORITY_TEXT: Record<number, string> = {
  1: "text-risk-high",
  2: "text-primary",
  3: "text-muted-foreground",
};

export function DepositRiskResult({
  result,
  completedChecks,
}: {
  result: DepositRiskResponse;
  completedChecks: DepositCheck[];
}) {
  const style = riskStyle(result.risk_level);
  const sourcesById = new Map(
    result.official_sources.map((source) => [source.source_id, source]),
  );
  const priorities = [...new Set(result.actions.map((a) => a.priority))].sort(
    (a, b) => a - b,
  );
  const doneOptions = DEPOSIT_CHECK_OPTIONS.filter((option) =>
    completedChecks.includes(option.value),
  );

  return (
    <div className="flex flex-col gap-7">
      {/* 1. 위험 수준 — 문장이 먼저다. 숫자는 아래 칸에서 따로 본다. */}
      <div
        className={`relative overflow-hidden rounded-lg border p-4 pl-5 ${style.container}`}
      >
        <span aria-hidden className={`absolute inset-y-0 left-0 w-1 ${style.bar}`} />
        <p className={`text-caption font-semibold ${style.text}`}>
          지금 확인된 위험도 {riskStrengthLabel(result.risk_level)}
        </p>
        <p className="mt-1 text-display text-foreground">{result.summary}</p>
      </div>

      {/* 2. 확인이 필요한 항목 */}
      <section aria-labelledby="deposit-signals">
        <SectionHeading>
          <span id="deposit-signals">확인이 필요한 항목</span>
        </SectionHeading>

        {result.signals.length === 0 ? (
          <p className="rounded-lg border border-border bg-card p-4 text-body text-muted-foreground">
            입력하신 범위에서는 걸리는 항목이 없습니다. 입력하지 않은 부분까지
            확인된 것은 아닙니다.
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {result.signals.map((signal) => (
              <li
                key={signal.code}
                className="rounded-lg border border-border bg-card p-4"
              >
                <p className="text-body font-medium text-foreground">
                  {signal.label}
                </p>
                <p className="mt-1 text-caption text-muted-foreground">
                  {signal.detail}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* 3. 왜 그렇게 봤는지 — 비율과 보호 장치 */}
      <section aria-labelledby="deposit-basis">
        <SectionHeading>
          <span id="deposit-basis">이렇게 본 근거</span>
        </SectionHeading>

        <div className="rounded-lg border border-border bg-card p-4">
          <div className="flex items-baseline justify-between gap-3">
            <p className="text-body font-medium text-foreground">
              보증금을 포함한 빚 부담
            </p>
            <p
              className={`text-title tabular-nums ${ratioBandTextClass(result.ratio.band)}`}
            >
              {result.ratio.ratio_percent === null
                ? "계산 못 함"
                : `${result.ratio.ratio_percent}%`}
            </p>
          </div>

          <p className="mt-1 text-caption text-muted-foreground">
            {result.ratio.formula}
          </p>

          {result.ratio.ratio_percent === null ? (
            <p className="mt-3 rounded-md bg-muted p-3 text-caption text-muted-foreground">
              주택가격이나 선순위 채권최고액을 아직 모르기 때문에 계산하지
              않았습니다. 모르는 값을 0원으로 놓으면 실제보다 낮은 숫자가 나와서
              확인하지 않은 쪽이 더 안심되는 결과를 받게 됩니다.
            </p>
          ) : (
            <p className="mt-3 rounded-md bg-muted p-3 text-caption text-muted-foreground">
              이 서비스 기준으로 {ratioBandLabel(result.ratio.band)}입니다.
              60%·80% 구간은 <strong className="font-semibold">이 서비스가 정한
              보수적 기준</strong>이며 공식 기준이 아닙니다.
            </p>
          )}
        </div>

        <div className="mt-2 rounded-lg border border-border bg-card p-4">
          <p className="text-body font-medium text-foreground">
            지금 서 있는 보호 장치
          </p>

          <dl className="mt-2 flex flex-col gap-2">
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-caption text-muted-foreground">
                대항력 요건(입주 + 전입신고)
              </dt>
              <dd className="text-body text-foreground">
                {result.protection.has_opposing_power_requirements
                  ? "갖춤"
                  : "아직"}
              </dd>
            </div>

            {result.protection.opposing_power_effective_on ? (
              <div className="flex items-baseline justify-between gap-3">
                <dt className="text-caption text-muted-foreground">
                  대항력 발생일
                </dt>
                <dd className="text-body tabular-nums text-foreground">
                  {result.protection.opposing_power_effective_on}
                </dd>
              </div>
            ) : null}

            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-caption text-muted-foreground">
                우선변제권 요건(대항요건 + 확정일자)
              </dt>
              <dd className="text-body text-foreground">
                {result.protection.has_priority_repayment_requirements
                  ? "갖춤"
                  : "아직"}
              </dd>
            </div>
          </dl>

          <p className="mt-3 text-caption text-muted-foreground">
            우선변제권은 요건 충족 여부만 알려드립니다. 언제 생겼는지를 날짜
            하나로 단정하려면 법에 적혀 있지 않은 해석이 필요해서, 이 서비스는
            그 날짜를 만들지 않습니다.
          </p>
        </div>
      </section>

      {/* 4. 이미 마친 확인 */}
      <section aria-labelledby="deposit-done">
        <SectionHeading>
          <span id="deposit-done">이미 마치신 것</span>
        </SectionHeading>

        {doneOptions.length === 0 ? (
          <p className="rounded-lg border border-border bg-card p-4 text-body text-muted-foreground">
            아직 표시하신 항목이 없습니다. 지금부터 하나씩 하시면 됩니다.
          </p>
        ) : (
          <ul className="rounded-lg border border-border bg-card p-4">
            {doneOptions.map((option) => (
              <li
                key={option.value}
                className="text-body text-foreground before:mr-2 before:text-safe before:content-['✓']"
              >
                {option.label}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* 5. 지금 해야 할 행동 */}
      <section aria-labelledby="deposit-actions">
        <SectionHeading>
          <span id="deposit-actions">지금 해야 할 일</span>
        </SectionHeading>

        <div className="flex flex-col gap-4">
          {priorities.length === 0 ? (
            <p className="rounded-lg border border-border bg-card p-4 text-body text-muted-foreground">
              입력하신 범위에서 지금 더 하실 일은 나오지 않았습니다. 계약 종료가
              가까워지면 갱신 여부와 보증금 반환 일정을 다시 확인하세요.
            </p>
          ) : null}
          {priorities.map((priority) => (
            <div key={priority}>
              <p
                className={`mb-2 text-caption font-semibold ${PRIORITY_TEXT[priority]}`}
              >
                {PRIORITY_LABEL[priority]}
              </p>
              <ul className="flex flex-col gap-2">
                {result.actions
                  .filter((action) => action.priority === priority)
                  .map((action) => (
                    <li
                      key={action.code}
                      className="rounded-lg border border-border bg-card p-4"
                    >
                      <p className="text-body font-medium text-foreground">
                        {action.title}
                      </p>
                      <p className="mt-1 text-caption text-muted-foreground">
                        {action.reason}
                      </p>
                      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
                        {action.source_ids.map((sourceId) => {
                          const source = sourcesById.get(sourceId);
                          if (!source) return null;
                          return (
                            <a
                              key={sourceId}
                              href={source.source_url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex min-h-11 items-center gap-1 text-caption font-medium text-primary underline underline-offset-2"
                            >
                              {source.title}
                              <ExternalLink aria-hidden className="size-3.5" />
                            </a>
                          );
                        })}
                      </div>
                    </li>
                  ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      {/* 6. 공식 근거 */}
      <section aria-labelledby="deposit-sources">
        <SectionHeading>
          <span id="deposit-sources">확인한 공식 자료</span>
        </SectionHeading>

        <ul className="flex flex-col gap-2">
          {result.official_sources.map((source) => (
            <li
              key={source.source_id}
              className="rounded-lg border border-border bg-card p-3"
            >
              <a
                href={source.source_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex min-h-11 items-center gap-1 text-body font-medium text-primary underline underline-offset-2"
              >
                {source.title}
                <ExternalLink aria-hidden className="size-4" />
              </a>
              <p className="text-caption text-muted-foreground">
                {source.organization} · 확인일 {source.retrieved_at}
              </p>
            </li>
          ))}
        </ul>
      </section>

      <DisclaimerNote>{result.disclaimer}</DisclaimerNote>
    </div>
  );
}
