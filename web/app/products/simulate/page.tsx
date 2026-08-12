import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { LoanWhatIf } from "@/components/finance/LoanWhatIf";

export const metadata = {
  title: "대출 조건 비교 | FinShield",
};

export default function LoanSimulationPage() {
  return (
    <AppShell>
      <PageHeader
        title="대출 조건 비교"
        description="같은 원금과 기간에서 현재 금리와 바꾼 금리의 상환 결과를 나란히 확인합니다."
        backHref="/products"
      />
      <LoanWhatIf />
    </AppShell>
  );
}
