import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { DepositRiskForm } from "@/components/housing/DepositRiskForm";


export const metadata = {
  title: "전세보증금 위험 점검",
};


/**
 * `/check` 아래에 둔 이유.
 *
 * 최상위 영역은 4개로 고정되어 있고 늘리지 않는다. 전세 계약을 확인하는 일은
 * "안전 확인" 과 같은 성격이라 그 아래로 들어간다. 하단 내비게이션의 활성
 * 표시도 그대로 맞는다.
 */
export default function DepositRiskPage() {
  return (
    <AppShell>
      <PageHeader
        title="전세보증금 위험 점검"
        description="계약이 어디까지 갔는지와 확인하신 금액을 넣으면, 지금 무엇이 비어 있고 무엇부터 해야 하는지 알려드립니다."
        backHref="/check"
      />
      <DepositRiskForm />
    </AppShell>
  );
}
