import type { MetadataRoute } from "next";

/**
 * 웹 앱 manifest.
 *
 * 이 제품을 쓰는 순간은 대부분 "방금 이상한 문자를 받았을 때"다. 그때 브라우저를
 * 열고 주소를 치고 문자 앱으로 돌아가 복사하고 다시 붙여넣게 만들면, 대부분은
 * 그냥 링크를 눌러 본다. share_target 을 두는 이유가 이것이다 - 문자 앱의 공유
 * 버튼에서 바로 넘어오면 단계가 하나로 줄어든다.
 *
 * method 가 POST 인 것은 편의가 아니라 필수 조건이다. GET 이면 공유된 문자
 * 원문이 쿼리스트링에 실려 방문 기록·액세스 로그·Referer 에 남는다. 자세한
 * 근거는 `@/lib/share/handoff` 주석에 적었다.
 *
 * `manifest.json` 대신 이 파일을 쓰는 이유는 Next 가 타입을 검사해 주기
 * 때문이다. share_target 은 오타가 나도 브라우저가 조용히 무시하고 공유 목록에만
 * 안 뜬다 - 손으로 쓴 JSON 이었으면 알아채기 어려웠다.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "FinShield — 금융 안전 코파일럿",
    // 홈 화면 아이콘 아래에 들어가는 이름. 12자를 넘으면 잘린다.
    short_name: "FinShield",
    description:
      "받은 문자가 정상 절차와 어떻게 다른지 확인하고, 지금 해야 할 안전한 행동을 찾습니다.",
    lang: "ko",
    dir: "ltr",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#ffffff",
    // globals.css 의 --primary 와 같은 값. 상태 표시줄 색이 헤더와 어긋나면
    // 설치된 앱에서 위쪽에 다른 색 띠가 하나 더 있는 것처럼 보인다.
    theme_color: "#1f3a5f",
    categories: ["finance", "utilities", "security"],
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      {
        // maskable 이 없으면 Android 가 아이콘을 흰 원 안에 축소해 넣는다.
        src: "/icons/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
    share_target: {
      action: "/check/shared",
      method: "POST",
      // 공유 시트는 텍스트만 보내도 multipart 로 보낼 수 있다. 나중에 스크린샷
      // 공유를 받게 되더라도 enctype 을 바꾸지 않아도 되도록 이쪽으로 맞춘다.
      enctype: "multipart/form-data",
      params: { title: "title", text: "text", url: "url" },
    },
    shortcuts: [
      {
        name: "받은 연락 확인하기",
        short_name: "연락 확인",
        description: "받은 문자나 메신저 내용을 붙여넣어 위험 신호를 확인합니다.",
        url: "/check",
        icons: [{ src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" }],
      },
    ],
  };
}
