import { AppShell } from "@/components/layout/AppShell";
import { FinancialStatusBlock } from "@/components/home/FinancialStatusBlock";
import { CheckTodayBlock } from "@/components/home/CheckTodayBlock";
import { SuspiciousContactBlock } from "@/components/home/SuspiciousContactBlock";
import { NextActionBlock } from "@/components/home/NextActionBlock";
import { getHomeView } from "@/lib/api/home";

/**
 * Home — 금융 안전 대시보드.
 *
 * 숫자를 잔뜩 늘어놓는 대시보드가 아니라 네 가지만 보인다.
 *   1. 현재 금융상태  2. 지금 확인할 금융정보
 *   3. 위험한 금융 연락 확인  4. 다음 행동
 * 블록당 카드 1개를 넘기지 않는다.
 */
export default function HomePage() {
  const view = getHomeView();

  return (
    <AppShell>
      <div className="mb-6">
        <p className="text-caption text-muted-foreground">FinShield</p>
        <h1 className="mt-0.5 text-display text-foreground">
          오늘 확인할 것을 모았습니다
        </h1>
      </div>

      <div className="flex flex-col gap-7">
        <FinancialStatusBlock snapshot={view.snapshot} />
        <CheckTodayBlock
          items={view.checkItems}
          source={view.checkItemsSource}
        />
        <SuspiciousContactBlock
          recent={view.recentAnalyses}
          source={view.recentAnalysesSource}
        />
        <NextActionBlock
          action={view.nextAction}
          source={view.nextActionSource}
        />
      </div>
    </AppShell>
  );
}
