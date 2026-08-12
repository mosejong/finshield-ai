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
      <body className="min-h-full">{children}</body>
    </html>
  );
}
