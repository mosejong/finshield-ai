import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

/**
 * 구조적 접근성 회귀 테스트.
 *
 * 실브라우저·스크린리더 검수를 대체하지는 않지만, 랜드마크·폼 라벨·라이브 영역·
 * 장식 아이콘 숨김 같은 접근성 계약이 리팩터링으로 조용히 깨지는 것을 CI에서 잡는다.
 * 브라우저 DOM 없이 react-dom/server 로 정적 렌더링한 마크업 문자열을 검사한다.
 */

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...rest
  }: {
    href: string | { pathname?: string };
    children: React.ReactNode;
  }) =>
    createElement(
      "a",
      { href: typeof href === "string" ? href : (href?.pathname ?? "#"), ...rest },
      children,
    ),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { EvidenceList } from "@/components/evidence/EvidenceList";
import { RiskLevelHeader } from "@/components/safety/RiskLevelHeader";
import { RiskSignalList } from "@/components/safety/RiskSignalList";
import { ActionChecklist } from "@/components/safety/ActionChecklist";
import { StateSelector } from "@/components/safety/StateSelector";
import { MockBadge } from "@/components/common/MockBadge";
import { MetricList } from "@/components/finance/MetricList";
import { ProfileFacts } from "@/components/finance/ProfileFacts";
import type {
  Action,
  DerivedMetric,
  Evidence,
  FinancialProfile,
  RiskSignal,
} from "@/lib/api/contracts";

function render(element: React.ReactElement): string {
  return renderToStaticMarkup(element);
}

describe("AppShell 랜드마크", () => {
  it("본문 건너뛰기 대상과 포커스 가능한 main 랜드마크를 제공한다", () => {
    const html = render(<AppShell>본문</AppShell>);
    expect(html).toContain('id="main-content"');
    expect(html).toContain('tabindex="-1"');
    expect(html).toContain("<main");
  });

  it("주요 메뉴 네비게이션에 접근 가능한 이름을 붙인다", () => {
    const html = render(<AppShell>본문</AppShell>);
    expect(html).toContain('aria-label="주요 메뉴"');
    expect(html).toContain("<nav");
  });
});

describe("PageHeader", () => {
  it("화면당 h1 을 하나 렌더링하고 뒤로 링크를 제공한다", () => {
    const html = render(<PageHeader title="확인 결과" backHref="/check" />);
    expect(html.match(/<h1/g)).toHaveLength(1);
    expect(html).toContain('href="/check"');
  });
});

describe("EvidenceList 근거 표시", () => {
  const verified: Evidence = {
    id: "e1",
    title: "금융감독원",
    publisher: "금융감독원",
    phone: "1332",
    verified: true,
    fetchedAt: "2026-08-13",
  };
  const unverified: Evidence = {
    id: "e2",
    title: "OO은행 고객센터",
    publisher: "OO은행",
    verified: false,
  };

  it("확인 전 항목은 '공식 확인 전'으로 명시한다", () => {
    const html = render(<EvidenceList items={[unverified]} />);
    expect(html).toContain("공식 확인 전");
  });

  it("모두 확인된 경우 확인 전 안내를 노출하지 않는다", () => {
    const html = render(<EvidenceList items={[verified]} />);
    expect(html).not.toContain("공식 확인 전");
    expect(html).toContain('href="tel:1332"');
  });
});

describe("RiskLevelHeader", () => {
  it("현재 상황 위험도 문구를 보여주고 좌측 바는 장식으로 숨긴다", () => {
    const html = render(
      <RiskLevelHeader
        level="high"
        headline="이 요청은 정상 절차에 없는 요구입니다"
        source="live"
      />,
    );
    expect(html).toContain("현재 상황 위험도 높음");
    expect(html).toContain('aria-hidden="true"');
  });
});

describe("RiskSignalList", () => {
  it("신호가 없으면 안내 문장을, 있으면 목록을 렌더링한다", () => {
    expect(render(<RiskSignalList signals={[]} />)).toContain(
      "위험 신호는 감지되지",
    );

    const signals: RiskSignal[] = [
      { code: "ACCOUNT_ACCESS", label: "계좌·접근수단 요구", weight: 40, source: "live" },
    ];
    const html = render(<RiskSignalList signals={signals} />);
    expect(html).toContain("<ul");
    expect(html).toContain("계좌·접근수단 요구");
  });
});

describe("ActionChecklist", () => {
  it("완료 토글 버튼에 눌림 상태와 접근 가능한 이름을 제공한다", () => {
    const actions: Action[] = [
      {
        id: "a1",
        title: "상대에게 계좌·카드를 절대 보내지 마세요",
        kind: "avoid",
        evidenceIds: [],
      },
    ];
    const html = render(<ActionChecklist actions={actions} />);
    expect(html).toContain('aria-pressed="false"');
    expect(html).toContain("완료 표시: 상대에게 계좌·카드를 절대 보내지 마세요");
  });
});

describe("StateSelector", () => {
  it("radiogroup 과 라디오 입력을 접근 가능한 이름으로 묶는다", () => {
    const html = render(<StateSelector value="received_only" onChange={() => {}} />);
    expect(html).toContain('role="radiogroup"');
    expect(html).toContain('aria-label="이미 하신 행동"');
    expect(html.match(/type="radio"/g)?.length).toBeGreaterThanOrEqual(7);
  });
});

describe("MockBadge 출처 정직성", () => {
  it("live 출처는 배지를 만들지 않고 mock 출처만 표시한다", () => {
    expect(render(<MockBadge source="live" />)).toBe("");
    expect(render(<MockBadge source="mock" label="예시" />)).toContain("예시");
  });
});

describe("MetricList / ProfileFacts 정의 목록 구조", () => {
  it("파생지표를 dl 없이 ul 목록으로 표현한다", () => {
    const metrics: DerivedMetric[] = [
      {
        key: "disposable_cashflow",
        label: "매달 쓸 수 있는 돈",
        display: "1,100,000원",
        hint: "소득에서 고정지출을 뺀 값",
        tone: "positive",
      },
    ];
    const html = render(<MetricList metrics={metrics} />);
    expect(html).toContain("<ul");
    expect(html).toContain("매달 쓸 수 있는 돈");
  });

  it("입력값을 dt/dd 정의 목록으로 되돌려 보여준다", () => {
    const profile: FinancialProfile = {
      ageBand: "20_29",
      employmentStatus: "employed",
      householdSize: 1,
      dependentsCount: 0,
      maritalStatus: null,
      region: null,
      monthlyNetIncome: 2_800_000,
      monthlyFixedExpenses: 1_100_000,
      monthlyVariableExpenses: 600_000,
      liquidAssets: 4_000_000,
      emergencyFundTargetMonths: 3,
      totalDebt: 0,
      monthlyDebtPayment: 0,
      creditScoreBand: "unknown",
      businessOwner: false,
      goal: "emergency_cash",
      persona: "early_career",
    };
    const html = render(<ProfileFacts profile={profile} />);
    expect(html).toContain("<dl");
    expect(html).toContain("<dt");
    expect(html).toContain("<dd");
  });
});
