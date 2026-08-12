import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { WealthGuidance } from "@/components/finance/WealthGuidance";


export const metadata = {
  title: "재테크 기초 가이드",
};


export default function WealthGuidancePage() {
  return (
    <AppShell>
      <PageHeader
        title="재테크 기초 가이드"
        description="무엇을 살지 고르기 전에 내 금융생활과 투자 위험을 차근차근 확인합니다."
        backHref="/products"
      />
      <WealthGuidance />
    </AppShell>
  );
}
