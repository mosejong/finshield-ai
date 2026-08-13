import type { ReactNode } from "react";
import { BottomNav } from "@/components/layout/BottomNav";
import { SideNav } from "@/components/layout/SideNav";

/**
 * 반응형 3단계 프레임.
 *   < 640  단일 컬럼 + 하단 네비
 *   640–1023  본문 560px 중앙 정렬, 하단 네비 유지
 *   >= 1024  좌측 네비 + 본문 680px
 */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto flex w-full lg:max-w-[1100px]">
      <SideNav />

      <div className="min-w-0 flex-1">
        {/* 하단 네비 높이 + safe area 만큼 본문 아래를 비워 둔다 */}
        <main
          id="main-content"
          tabIndex={-1}
          className="mx-auto w-full max-w-[560px] px-4 pb-[calc(4.5rem+env(safe-area-inset-bottom))] pt-4 lg:max-w-[680px] lg:px-8 lg:pb-12 lg:pt-8"
        >
          {children}
        </main>
      </div>

      <BottomNav />
    </div>
  );
}
