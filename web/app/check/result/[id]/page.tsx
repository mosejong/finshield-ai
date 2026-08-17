"use client";

import { use, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { SectionHeading } from "@/components/common/SectionHeading";
import { MockBadge } from "@/components/common/MockBadge";
import { DisclaimerNote } from "@/components/common/DisclaimerNote";
import { EvidenceList } from "@/components/evidence/EvidenceList";
import { ActionChecklist } from "@/components/safety/ActionChecklist";
import { AnalysisDetails } from "@/components/safety/AnalysisDetails";
import { RiskLevelHeader } from "@/components/safety/RiskLevelHeader";
import {
  RiskSignalList,
  SignalExplanationBadge,
} from "@/components/safety/RiskSignalList";
import { UserStateRecap } from "@/components/safety/UserStateRecap";
import { WhyRiskyPanel } from "@/components/safety/WhyRiskyPanel";
import { InstallHint } from "@/components/pwa/InstallHint";
import { demoAnalysisFor } from "@/lib/mock/analysis";
import { clearAnalysis, useStoredAnalysis } from "@/lib/store/analysis-store";
import { useHydrated } from "@/lib/store/session-store";

/**
 * 위험 분석 결과.
 *
 * 섹션 순서는 고정이다.
 *   위험 수준 → 감지된 신호 → 왜 위험한지 → 내가 이미 한 것
 *   → 지금 해야 할 행동 → 공식 근거 → (접힌) 분석 상세
 *
 * "위험도 87점"으로 끝내지 않기 위한 순서다. 사용자는 점수를 해석하러 온 게
 * 아니라 지금 무엇을 해야 하는지 알고 싶어서 왔다. 숫자는 맨 아래 접어 둔다.
 */
export default function CheckResultPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();

  const loaded = useHydrated();
  const stored = useStoredAnalysis(id);
  const demo = useMemo(() => demoAnalysisFor(id), [id]);

  const result = stored ?? demo;
  const isDemo = stored === null && demo !== null;

  if (!loaded) {
    return (
      <AppShell>
        <p role="status" className="py-8 text-body text-muted-foreground">불러오는 중…</p>
      </AppShell>
    );
  }

  if (!result) {
    return (
      <AppShell>
        <PageHeader
          title="결과를 찾을 수 없습니다"
          description="분석 결과는 브라우저 세션에만 저장되어, 탭을 닫거나 새로 열면 사라집니다."
          backHref="/"
        />
        <Link
          href="/check"
          className="inline-flex min-h-12 w-full items-center justify-center rounded-md bg-primary px-4 text-body font-semibold text-primary-foreground transition-opacity hover:opacity-90"
        >
          다시 확인하기
        </Link>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageHeader title="확인 결과" backHref="/check" />

      {isDemo ? (
        <p className="mb-4 rounded-md border border-dashed border-border bg-secondary/60 px-3 py-2 text-caption text-muted-foreground">
          화면 구조를 보여주기 위한 예시 결과입니다. 실제 분석이 아닙니다.
        </p>
      ) : null}

      <div className="flex flex-col gap-7">
        {/* 1. 위험 수준 — 점수가 아니라 한 문장 */}
        <RiskLevelHeader
          level={result.level}
          headline={result.headline}
          source={result.headlineSource}
        />

        {/* 2. 감지된 위험 신호 */}
        <section aria-labelledby="result-signals">
          <SectionHeading badge={<SignalExplanationBadge signals={result.signals} />}>
            <span id="result-signals">감지된 위험 신호</span>
          </SectionHeading>
          <RiskSignalList signals={result.signals} />
        </section>

        {/* 3. 왜 위험한지 */}
        <section aria-labelledby="result-why">
          <SectionHeading badge={<MockBadge source={result.whySource} />}>
            <span id="result-why">왜 위험한지</span>
          </SectionHeading>
          <WhyRiskyPanel paragraphs={result.why} />
        </section>

        {/* 4. 사용자가 이미 한 것 */}
        <section aria-labelledby="result-state">
          <SectionHeading>
            <span id="result-state">지금까지 하신 것</span>
          </SectionHeading>
          <UserStateRecap state={result.state} summary={result.stateSummary} />
        </section>

        {/* 5. 지금 해야 할 행동 */}
        <section aria-labelledby="result-actions">
          <SectionHeading badge={<MockBadge source={result.actionsSource} />}>
            <span id="result-actions">지금 해야 할 행동</span>
          </SectionHeading>
          <ActionChecklist actions={result.actions} />
        </section>

        {/* 6. 공식 근거 */}
        {result.evidence.length > 0 ? (
          <section aria-labelledby="result-evidence">
            <SectionHeading badge={<MockBadge source={result.evidenceSource} />}>
              <span id="result-evidence">공식 근거</span>
            </SectionHeading>
            <EvidenceList items={result.evidence} />
          </section>
        ) : null}

        {/* 7. 분석 상세 — 숫자 점수는 여기에만 */}
        <AnalysisDetails result={result} />
      </div>

      <div className="mt-6 flex flex-col items-center gap-3">
        <Link
          href="/check"
          className="inline-flex min-h-12 w-full items-center justify-center rounded-md border border-border bg-card px-4 text-body font-medium text-foreground transition-colors hover:bg-secondary"
        >
          다른 연락 확인하기
        </Link>

        {/* 붙여넣은 내용이 담긴 결과다. 탭을 닫을 때까지 기다리지 않고 지울 수 있어야 한다 */}
        {!isDemo ? (
          <button
            type="button"
            onClick={() => {
              clearAnalysis(id);
              router.replace("/check");
            }}
            className="min-h-9 text-caption font-medium text-muted-foreground underline underline-offset-2 hover:text-foreground"
          >
            이 결과 지우기
          </button>
        ) : null}
      </div>

      {/*
        설치 안내는 결과를 한 번 본 뒤에 둔다. 무엇을 해주는 앱인지 알고 난
        다음이라야 "다음엔 공유 버튼으로"가 제안으로 읽힌다.
      */}
      <InstallHint />

      <DisclaimerNote>{result.disclaimer}</DisclaimerNote>
    </AppShell>
  );
}
