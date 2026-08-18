import type { Metadata, Viewport } from "next";
import "./globals.css";
import { ServiceWorkerRegistration } from "@/components/pwa/ServiceWorkerRegistration";

export const metadata: Metadata = {
  title: {
    default: "FinShield — 금융 안전 코파일럿",
    template: "%s · FinShield",
  },
  description:
    "금융 경험이 부족해도 내 금융상태를 이해하고, 위험한 금융 연락을 알아보고, 지금 할 안전한 행동을 찾도록 돕습니다.",
  // manifest 는 `app/manifest.ts` 가 만든다. 경로만 알려 주면 된다.
  manifest: "/manifest.webmanifest",
  applicationName: "FinShield",
  appleWebApp: {
    // iOS 는 manifest 를 읽지 않는다. 홈 화면에서 열었을 때 주소창 없이 뜨게
    // 하려면 이 메타 태그가 따로 있어야 한다.
    capable: true,
    title: "FinShield",
    // 상태 표시줄을 배경과 같은 색으로 두면 노치 주변만 다른 색이 되지 않는다.
    statusBarStyle: "default",
  },
  icons: {
    icon: [
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180" }],
  },
  // 공유 인계 문서와 오프라인 화면은 색인될 이유가 없다. 그 둘은 자기 헤더로
  // 따로 막고, 나머지는 평소대로 둔다.
  formatDetection: {
    // 안드로이드 크롬이 본문의 숫자를 임의로 전화번호 링크로 바꾸지 않게 한다.
    // 붙여넣은 문자 안의 계좌번호가 링크가 되면 잘못 누를 수 있다.
    telephone: false,
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  // globals.css 의 --primary / 다크 모드 --background 와 같은 값.
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#1f3a5f" },
    { media: "(prefers-color-scheme: dark)", color: "#101317" },
  ],
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
        <ServiceWorkerRegistration />
      </body>
    </html>
  );
}
