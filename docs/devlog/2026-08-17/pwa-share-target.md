# PWA와 공유 시트 연동 (manifest + share_target)

- 날짜: 2026-08-17
- 브랜치: `feature/frontend-accessibility-e2e`
- 범위: `web/app/{manifest.ts,layout.tsx,offline/page.tsx,check/shared/route.ts,check/page.tsx}`,
  `web/lib/share/{handoff,pending}.ts`, `web/lib/api/{request-body,contracts}.ts`,
  `web/components/pwa/{InstallHint,ServiceWorkerRegistration}.tsx`,
  `web/public/{sw.js,share-handoff.js,icons/*}`, `web/next.config.ts`,
  `scripts/generate_pwa_icons.py`, 문서

## 배경

`docs/28` 5절이 정한 순서대로 실도메인(P0-4) 바로 앞 작업이다. 근거는 UI가 아니라 인증
모델이었다. 지금 세션은 `SameSite=Strict` + HttpOnly 쿠키에 trusted-host 허용목록이고 CORS
미들웨어가 없어서, 네이티브·WebView 클라이언트는 이 인증을 그대로 쓸 수 없다. PWA는 같은
오리진에서 돌므로 보안 경계를 다시 세우지 않고도 홈 화면 설치와 **안드로이드 공유 시트
연동**을 얻는다. 후자가 이 제품의 핵심 진입 경로다 — 의심 문자를 받은 순간 앱을 열고 복사해
붙여넣는 대신, 문자 앱의 공유 버튼에서 바로 넘긴다.

작업을 시작하고 첫 번째 판단에서 표준 예제와 갈라졌다. 그 이유가 이 작업의 대부분이다.

## 설계 판단 1 — share_target을 GET이 아니라 POST로 만든다

Web Share Target 예제는 거의 다 이렇게 생겼다.

```json
{ "action": "/check", "method": "GET", "params": { "text": "text" } }
```

구현이 훨씬 짧다. 쿼리스트링으로 오니까 기존 `/check` 페이지가 `searchParams`만 읽으면
끝이고, Route Handler도 인계 스크립트도 필요 없다.

그런데 이 서비스에서 사용자가 공유하는 값은 **본인이 받은 문자 원문**이다. 다루는 데이터 중
가장 민감한 축이고, GET으로 받으면 그 원문이 자동으로 네 군데에 복사된다. 브라우저 주소 기록,
Caddy·Next 액세스 로그, 외부 링크를 눌렀을 때의 `Referer`, 그리고 뒤로 가기.

이건 이미 백엔드에서 막아 둔 것이다. `app/core/observability.py`는 로그 필드를 allowlist로
고정해 쿼리·본문·경로 파라미터가 **구조적으로** 로그에 남지 않게 했고(`docs/27`,
`adr/0004`), 그 규칙은 "건수와 성공 여부만 남긴다"였다. 프론트가 원문을 URL에 실으면 그
allowlist가 아무 의미가 없어진다. 경로 자체가 원문이 되기 때문이다.

그래서 POST로 갔다. 치른 대가는 App Router의 `page.tsx`가 POST를 받지 못한다는 것 하나고,
그래서 `app/check/shared/route.ts`가 응답 HTML을 직접 만든다.

## 설계 판단 2 — 값은 실행되지 않는 태그에만 둔다

POST 응답에서 화면으로 값을 옮겨야 한다. 인라인 스크립트로 `sessionStorage.setItem("...",
"<원문>")`을 찍는 게 가장 짧지만, 그러면 외부에서 들어온 문자열이 **실행되는 코드 안에 직접
박힌다.** 이스케이프 실수 하나가 곧 스크립트 실행이다.

대신 값은 `<script type="application/json">`에만 담고, 그 값을 다루는 코드는 값을 모른 채
정적 파일(`/share-handoff.js`)로 배포된다. 인라인 스크립트가 없으니 `docs/26`이 남겨 둔
nonce 기반 strict CSP(P1-4)를 나중에 켤 때 예외를 뚫을 일도 없다.

이스케이프는 `JSON.stringify` 뒤에 `<`, `>`, `&`, U+2028, U+2029를 `\uXXXX`로 바꾼다. 앞의
셋은 `</script>`로 태그를 닫는 것을 막고, 뒤의 둘은 JSON에서는 합법이지만 JavaScript에서는
줄바꿈이라 파싱을 깨뜨린다. `</script><script>alert(1)</script>`를 공유해 원문이 그대로
왕복하고 문서의 `</script>`가 2개 그대로인 것을 확인했다.

인계 스크립트는 값을 sessionStorage로 옮긴 뒤 JSON 태그를 DOM에서 지우고
`location.replace("/check")`로 넘어간다. `push`면 뒤로 가기가 `/check/shared`로 돌아와
브라우저가 POST 재전송을 묻는다. 이 스크립트는 **어떤 경로로도 값을 기록하지 않는다** —
`console.log` 한 줄이면 문자 원문이 기기 로그로 샌다.

## 설계 판단 3 — CSRF 검사 대신 악용할 대상을 없앤다

공유 대상은 정의상 다른 앱이 보내는 교차 출처 POST다. `Sec-Fetch-Site: cross-site`로 오니
`app/core/http_security.py`의 same-origin 규칙을 그대로 걸 수 없다. 여기서 선택지는 예외를
만드는 것과, 예외가 위험하지 않게 핸들러를 설계하는 것 둘이다. 후자로 갔다.

이 핸들러는 상태를 바꾸지 않고, 백엔드를 부르지 않고, 받은 값을 저장하지 않는다. 분석 요청은
사용자가 `/check`에서 눌러야 나간다. 공격자가 이 주소로 요청을 유도해도 얻는 것은 **자기가
보낸 문자열이 담긴 HTML 한 장**이고 그마저 `no-store`다. 응답에 `Set-Cookie`가 없다는 것은
테스트로 고정해서, 나중에 누가 여기에 세션을 붙이면 테스트가 깨진다.

크기 상한은 파싱 앞에 둔다. `request.formData()`를 바로 부르면 본문 전체를 메모리에 올린
뒤에야 크기를 알 수 있어 P0-1의 상한이 무의미해진다. `readLimitedBody()`로 64KB까지만 읽고
그 바이트만 다시 파싱한다. 이 함수를 새로 만들면서 `readJsonBody`도 그 위로 옮겼다 — 상한
로직이 두 벌로 갈라지면 한쪽만 고쳐지는 날이 온다.

## 설계 판단 4 — 캐시할 것보다 캐시하지 않을 것을 먼저 정한다

`docs/28` 5절이 "분석 결과는 캐시하지 않는다 — 민감 데이터다"를 범위에 박아 두었다. 그래서
서비스 워커는 제외 목록부터 썼다.

| 대상 | 처리 | 이유 |
|---|---|---|
| GET이 아닌 요청 | 개입 안 함 | **공유 POST를 워커가 건드리면 본문이 사라진다** |
| 교차 출처 | 개입 안 함 | 우리가 판단할 것이 아니다 |
| `/api/*` | 개입 안 함 | 오래된 위험 판정을 새 판정처럼 보여주는 것은 없느니만 못하다 |
| 화면 HTML | network-only → `/offline` | 결과 화면에 붙여넣은 문자 원문이 들어 있다 |
| `/_next/static/*`, `/icons/*` | cache-first | 내용이 바뀌면 경로도 바뀐다 |

결과적으로 캐시에 들어갈 수 있는 것은 해시 붙은 빌드 산출물, 아이콘, 오프라인 화면 셋뿐이다.
사용자 데이터가 캐시에 들어갈 경로가 구조적으로 없다.

오프라인 화면은 배포가 바뀌면 옛 빌드의 스타일시트를 가리키게 되므로, 온라인 상태의 첫
내비게이션에서 워커 생애당 한 번만 다시 받아 둔다. 실패는 무시한다 — 있던 사본이 남는 편이
낫다.

`/offline`은 "연결이 없다"만 말하지 않는다. **"확인하지 못했다는 것이 안전하다는 뜻은
아닙니다"** 를 먼저 적었다. P0-1에서 429 문구를 정할 때와 같은 원칙이다. 확인에 실패한 상태를
안전으로 읽히게 두면 안 된다. 그 아래에 링크를 누르지 말 것, 공식 대표번호로 직접 확인할 것을
두고 112·1332·118을 `tel:` 링크로 준다. 번호는 `web/lib/mock/evidence.ts`에 이미 있는
실재 기관 것만 쓴다.

## 설계 판단 5 — 설치 유도는 결과를 본 뒤에

홈이 아니라 `/check/result/[id]`에 뒀다. 홈은 블록 4개로 고정돼 있고(`docs/13`), 무엇보다
설치의 값어치는 결과를 한 번 본 뒤에야 와닿는다. 뭘 해주는지 모르는 사람에게 설치부터 권하면
그냥 배너 하나다.

`beforeinstallprompt`가 왔을 때만 버튼을 띄우는데, 이 이벤트는 보통 React가 마운트되기 전에
한 번 발생하고 만다. 컴포넌트 안에서 구독하면 영영 못 받으므로 모듈 평가 시점에 창에 붙여
두고 컴포넌트는 잡아 둔 값을 구독만 한다. iOS Safari에는 이 이벤트가 없어서 방법을 글로
알려주고, 이미 홈 화면에서 열렸거나 사용자가 닫았으면 아무것도 그리지 않는다.

## 막힌 것

**React Compiler 린트가 `useEffect` 안의 `setState`를 막는다.** 처음에는 공유 내용도 설치
힌트 상태도 효과 안에서 읽어 `setState`했고 `react-hooks/set-state-in-effect`가 두 곳에서
걸렸다. 규칙을 끄는 대신 이 저장소에 이미 있는 방식(`web/lib/store/session-store.ts`의
`useHydrated`)을 따라 `useSyncExternalStore`로 옮겼다. sessionStorage나 창 이벤트는 애초에
React 밖의 스토어라 이쪽이 맞고, 서버 스냅샷을 `null`/숨김으로 두면 하이드레이션 불일치도
같이 사라진다. 입력창은 `edited ?? shared ?? ""`로 파생값이 됐다.

**vitest가 "ReadableStream is already closed"로 종료 코드 1을 냈다.** 크기 초과 테스트에서
`readLimited`가 리더를 취소하는데, undici의 `FormData` 본문은 async generator라 취소 뒤에도
계속 밀어 넣는다. 그 테스트만 multipart 본문을 문자열로 직접 만들어 보내도록 바꿨다 — 단순
바이트 소스라 `Content-Length`가 붙고 파싱 이전 fast-reject 경로가 그대로 돈다.

**`Uint8Array`가 `BodyInit`에 안 들어갔다.** 기본 타입 `Uint8Array<ArrayBufferLike>`는
SharedArrayBuffer도 포함해서 `new Response(bytes)`에 넘길 수 없다. `Uint8Array<ArrayBuffer>`로
좁혔다.

**아이콘 생성에 Pillow를 넣지 않았다.** 설치돼 있지 않고, 추가하면 아이콘 만들자고 P0-5의
해시 고정 lock에 이미지 라이브러리를 들이는 셈이 된다. `zlib`과 `struct`만으로 PNG를 직접
쓰고 4배 supersampling으로 가장자리를 정리했다. 이 스크립트는 CI에서 돌지 않는다 — 산출물이
커밋돼 있고 아이콘을 바꿀 때만 사람이 돌린다.

## 검증

| 확인 | 방법 | 결과 |
|---|---|---|
| manifest | 프로덕션 서버 `GET /manifest.webmanifest` | `share_target`이 POST/multipart, 아이콘 3종, 바로가기 1개 |
| 공유 POST | 실제 multipart 전송 | 200 `text/html; charset=utf-8` |
| UTF-8 왕복 | 한글 문자 + URL | 원문 일치. 값은 주소가 아니라 본문 JSON 태그 안 |
| 적대적 입력 | `</script><script>alert(1)</script>` | 원문 그대로 왕복, `</script>` 2개 그대로 |
| 응답 잔존 | 헤더 | `no-store, must-revalidate`, `noindex, nofollow` |
| 쿠키 | 헤더 | `set-cookie` 없음 (테스트로 고정) |
| 크기 상한 | 60,000자 multipart | 413, 파싱 전 거절 |
| multipart 아님 | JSON POST | 400 + 붙여넣기 안내 |
| 주소창 직접 접근 | `GET /check/shared` | 303 → `/check` |
| 워커 배포 | `/sw.js` 헤더 | `no-cache, no-store, must-revalidate` + `Service-Worker-Allowed: /` |
| 오프라인 화면 | `GET /offline` | 200, 112·1332·118 `tel:` 링크 |
| 프론트 회귀 | `npm test` | 15 files, **103 passed** |
| 타입·린트 | `npx tsc --noEmit`, `npm run lint` | 둘 다 통과 |
| 프로덕션 빌드 | `npm run build` | 성공. `○ /manifest.webmanifest`, `○ /offline`, `ƒ /check/shared` |
| 백엔드 무변경 | `pytest -q` | 417 passed, 1 skipped |

콘솔에서 curl로 본 공유 내용이 한때 깨져 보였는데, 서버가 아니라 Windows 콘솔 코드페이지가
`curl -F`의 **입력**을 망가뜨린 것이었다. 파이썬으로 같은 multipart를 직접 만들어 보내
원문 일치를 확인했다.

## 남은 것

**공유 시트에서 실제로 고르는 것은 확인되지 않았다.** 설치와 서비스 워커는 HTTPS를 요구하고,
안드로이드 공유 목록에 뜨려면 실제로 설치돼 있어야 한다. 지금 검증된 것은 서버 쪽 왕복까지고,
나머지는 P0-4 다음이다. 이 작업을 P0-4 바로 앞에 둔 이유이기도 하다.

**iOS는 공유 시트에 뜨지 않는다.** Safari는 `share_target`을 구현하지 않는다. iOS에서는 홈
화면 추가와 오프라인 화면까지만 얻고 공유는 복사·붙여넣기로 남는다.

**공유 인계가 sessionStorage에 의존한다.** 프라이빗 모드 등에서 막히면 `/check`가 빈
입력창으로 열린다. 조용히 실패하는 대신 알려주는 편이 나은지는 실기기 확인 뒤에 판단한다.

**서비스 워커 업데이트 알림이 없다.** `skipWaiting`으로 새 워커가 바로 올라오지만 열려 있는
탭에 알리는 경로는 없다. 화면 HTML을 캐시하지 않으므로 다음 이동에서 새 코드를 받는다.
