import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "FinShield — 금융 안전 코파일럿",
    template: "%s · FinShield",
  },
  description:
    "금융 경험이 부족해도 내 금융상태를 이해하고, 위험한 금융 연락을 알아보고, 지금 할 안전한 행동을 찾도록 돕습니다.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ko" className="h-full antialiased">
      <body className="min-h-full">
        {/*
          키보드 사용자가 매 화면마다 좌측 네비를 모두 통과하지 않고 본문으로
          바로 이동할 수 있게 한다. 평소에는 sr-only 로 숨고 포커스될 때만 보인다.
        */}
        <a
          href="#main-content"
          className="sr-only rounded-md bg-primary px-4 py-2 text-body font-semibold text-primary-foreground focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50"
        >
          본문으로 건너뛰기
        </a>
        {children}
      </body>
    </html>
  );
}
