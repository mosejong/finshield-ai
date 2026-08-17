# 30. PWA와 공유 시트 연동

목적: 폰 홈 화면에 설치되고, 문자 앱의 **공유 버튼에서 곧바로 확인 화면으로** 들어오게 한다. 작성 기준일 2026-08-17.

판단 기준은 하나다. **공유된 문자 원문은 주소에 실리지 않는다.** 설치되는 것보다 중요하다.

## 0. 먼저 읽을 것 — 공유 내용은 쿼리스트링에 담을 수 없다

Web Share Target 예제는 대부분 이렇게 생겼다.

```json
{ "action": "/check", "method": "GET", "params": { "text": "text" } }
```

이 한 줄이 이 제품에서는 안 된다. 사용자가 공유하는 값은 **본인이 받은 문자 원문**이고, 이 서비스가 다루는 데이터 중 가장 민감한 축이다. GET으로 받으면 그 원문이 아래 네 군데에 자동으로 복사된다.

| 경로 | 무엇이 남는가 |
|---|---|
| 브라우저 주소 기록 | 원문이 통째로. 폰을 빌려준 사람도 본다 |
| Caddy·Next 액세스 로그 | 경로가 곧 원문. `adr/0004`의 로그 allowlist가 무의미해진다 |
| `Referer` 헤더 | 그 화면에서 외부 링크를 누르면 원문이 제3자에게 간다 |
| 뒤로 가기·공유 재전송 | 지웠다고 생각한 뒤에도 되살아난다 |

`app/core/observability.py`가 쿼리·본문·경로 파라미터를 구조적으로 로그에서 뺀 것(`docs/27`)과 정면으로 충돌한다. 프론트에서 URL에 실어 보내면 백엔드에서 막아 둔 것이 아무 소용이 없다.

그래서 **`method: "POST"` + `enctype: "multipart/form-data"`** 로 간다. 대가는 구현이 길어진다는 것 하나다. App Router의 `page.tsx`는 POST를 받지 못하므로 화면이 아니라 Route Handler가 받아야 하고, 받은 값을 화면까지 옮기는 경로를 직접 만들어야 한다. 1절 이후가 전부 그 경로에 대한 설명이다.

## 1. 구성

| 부분 | 파일 | 하는 일 |
|---|---|---|
| manifest | `web/app/manifest.ts` | `/manifest.webmanifest` 생성. 이름·아이콘·`share_target`·바로가기 |
| 공유 수신 | `web/app/check/shared/route.ts` | 공유 시트의 POST를 받아 인계 문서를 돌려준다 |
| 문서 생성 | `web/lib/share/handoff.ts` | 공유 칸 3개를 한 덩어리로 합치고, 실행되지 않는 JSON 태그로 감싼다 |
| 인계 스크립트 | `web/public/share-handoff.js` | JSON → sessionStorage → `/check`로 `replace` |
| 인계 소비 | `web/lib/share/pending.ts` | 모듈 평가 시 한 번 꺼내고 **즉시 지운다** |
| 서비스 워커 | `web/public/sw.js` | 오프라인 안내 + 불변 자산만 캐시 |
| 워커 등록 | `web/components/pwa/ServiceWorkerRegistration.tsx` | production 빌드에서만 등록 |
| 오프라인 화면 | `web/app/offline/page.tsx` | "확인하지 못한 것이 안전하다는 뜻은 아니다" + 공식 번호 |
| 설치 유도 | `web/components/pwa/InstallHint.tsx` | 결과 화면에서만, 설치 가능할 때만 |
| 아이콘 생성 | `scripts/generate_pwa_icons.py` | 표준 라이브러리만으로 PNG 생성 |
| 응답 헤더 | `web/next.config.ts` | `/sw.js` 무캐시 + `Service-Worker-Allowed: /` |

## 2. 공유 한 번에 무슨 일이 일어나는가

```
문자 앱 공유 → POST /check/shared (multipart)
  → 64KB 넘으면 여기서 끝 (413, 파싱 전)
  → title/text/url 을 한 덩어리로 합치고 10,000자에서 자름
  → <script type="application/json"> 에 담은 HTML 한 장 (no-store, noindex)
  → /share-handoff.js 가 sessionStorage 로 옮기고 태그를 지움
  → location.replace("/check")
  → usePendingShare() 가 꺼내면서 저장소에서 삭제
  → 입력창에 채워진 채로 멈춘다. 자동 분석하지 않는다.
```

**왜 인라인 스크립트가 아닌가.** 문서에 심는 값은 외부에서 들어온 문자열이다. 인라인으로 만들면 그 문자열이 실행되는 코드 안에 직접 박히고, 이스케이프 실수 하나가 곧 스크립트 실행이 된다. 값은 실행되지 않는 `type="application/json"` 태그에만 두고, 이 값을 다루는 스크립트는 값을 모른 채 정적 파일로 배포된다. `docs/26`의 CSP를 강화할 때 예외를 뚫지 않아도 된다는 부수 효과도 있다.

이스케이프는 `JSON.stringify` 뒤에 `<`, `>`, `&`, U+2028, U+2029를 `\uXXXX`로 바꾼다. 앞의 셋은 `</script>`로 태그를 닫는 것을 막고, 뒤의 둘은 JSON에서는 합법이지만 JavaScript에서는 줄바꿈으로 취급돼 파싱을 깨뜨린다.

**왜 `replace`인가.** `push`로 넘어가면 뒤로 가기가 `/check/shared`로 돌아오고 브라우저가 POST 재전송을 묻는다. 주소 기록에 공유 경로 자체를 남기지 않는 것도 겸한다.

**왜 자동으로 분석하지 않는가.** 결과 품질이 "이미 하신 행동"(`UserState`)에 달려 있고, 그건 사용자만 안다. 공유하자마자 분석을 쏘면 그 값이 항상 기본값이 된다. 넘어온 내용을 먼저 보여주고 고칠 수 있게 하는 편이 낫다 — 사용자가 실수로 다른 대화를 통째로 공유했을 수도 있다.

**왜 `useEffect`가 아니라 `useSyncExternalStore`인가.** sessionStorage는 React 밖의 저장소다. 효과 안에서 읽어 `setState`하면 마운트 직후 렌더가 한 번 더 돌고, React Compiler 린트(`react-hooks/set-state-in-effect`)가 이를 막는다. 서버 스냅샷을 `null`로 두면 하이드레이션 불일치도 생기지 않는다. `web/lib/store/session-store.ts`의 `useHydrated`와 같은 방식이다.

### CSRF를 검사하지 않는 이유

공유 대상은 정의상 다른 앱이 보내는 교차 출처 POST다. `Sec-Fetch-Site: cross-site`로 오므로 `app/core/http_security.py`의 same-origin 규칙을 그대로 적용할 수 없다. 대신 이 핸들러는 **악용할 대상 자체를 없애 두었다.**

- 상태를 바꾸지 않는다 — 쓰기도, 세션 변경도 없다
- 백엔드를 부르지 않는다 — 분석 요청은 사용자가 `/check`에서 눌러야 나간다
- 받은 값을 저장하지 않는다 — 응답 문서에 담아 돌려줄 뿐이다

공격자가 이 주소로 요청을 유도해도 얻는 것은 **자기가 보낸 문자열이 담긴 HTML 한 장**이고, 그마저 `no-store`다. 응답에 `Set-Cookie`가 없다는 사실은 테스트로 고정했다.

### 크기 상한을 파싱 앞에 두는 이유

`request.formData()`를 바로 부르면 본문 전체를 메모리에 올린 뒤에야 크기를 알 수 있다. `readLimitedBody()`로 64KB까지만 읽고, 그 바이트를 다시 `Response`로 감싸 파싱한다(`web/lib/api/request-body.ts`). P0-1에서 만든 본문 상한과 같은 함수를 쓴다 — 상한 로직이 두 벌로 갈라지지 않게 `readJsonBody`도 이 함수 위로 옮겼다.

## 3. 서비스 워커가 캐시하지 않는 것

캐시할 것보다 **캐시하지 않을 것을 먼저 정하고** 시작했다. `docs/28` 5절이 "분석 결과는 캐시하지 않는다 — 민감 데이터다"를 작업 범위에 못 박았기 때문이다.

| 대상 | 처리 | 이유 |
|---|---|---|
| GET이 아닌 요청 | `respondWith` 자체를 부르지 않음 | 공유 POST를 워커가 건드리면 본문이 사라진다 |
| 교차 출처 | 개입 없음 | 우리 오리진 밖은 우리가 판단할 것이 아니다 |
| `/api/*` | 개입 없음 | 오래된 위험 판정을 새 판정처럼 보여주는 것은 없느니만 못하다 |
| 화면 HTML | network-only, 실패 시 `/offline` | 결과 화면에는 붙여넣은 문자 원문이 들어 있다 |
| `/_next/static/*`, `/icons/*` | cache-first | 내용이 바뀌면 경로도 바뀐다 |

즉 캐시에 남는 것은 **해시가 붙은 빌드 산출물, 아이콘, 오프라인 안내 화면** 세 가지뿐이다. 사용자 데이터가 캐시에 들어갈 경로가 구조적으로 없다.

오프라인 화면은 배포가 바뀌면 옛 빌드의 스타일시트를 가리키게 된다. 온라인 상태의 첫 내비게이션에서 **워커 생애당 한 번만** 다시 받아 둔다. 실패는 무시한다 — 있던 사본이 남는 편이 낫다.

`/offline` 화면은 "연결이 없다"만 말하지 않는다. **"확인하지 못했다는 것이 안전하다는 뜻은 아닙니다"** 를 먼저 적고, 링크를 누르지 말 것·공식 대표번호로 직접 확인할 것을 안내한 뒤 112·1332·118을 `tel:` 링크로 준다. 오프라인은 판단을 미루는 상황이지 안전해지는 상황이 아니다.

## 4. 설치 유도는 결과 화면에만 둔다

홈이 아니라 `/check/result/[id]`에 둔 이유가 둘이다. 홈은 블록 4개로 고정돼 있고(`docs/13`), 무엇보다 **설치의 값어치는 결과를 한 번 본 뒤에야 와닿는다.** 뭘 해주는지 모르는 사람에게 설치부터 권하면 그냥 배너 하나다.

브라우저가 `beforeinstallprompt`로 설치 가능하다고 알려줄 때만 버튼을 띄운다. 이 이벤트는 보통 React가 마운트되기 전에 한 번 발생하고 마니까 모듈 평가 시점에 창에 붙여 두고, 컴포넌트는 잡아 둔 값을 구독만 한다. iOS Safari에는 이 이벤트가 없어서 방법을 글로 알려주고, 이미 홈 화면에서 열렸거나 사용자가 닫았으면 아무것도 그리지 않는다. **설치할 수 없는 곳에서 설치를 권하지 않는다.**

## 5. 아이콘

`scripts/generate_pwa_icons.py`가 `zlib`과 `struct`만으로 PNG를 직접 쓴다. 4배 supersampling으로 가장자리를 정리한다.

Pillow를 쓰지 않은 이유는 P0-5다. 지금 설치돼 있지 않고, 추가하면 해시 고정 lock에 아이콘 만들자고 이미지 라이브러리를 넣는 셈이 된다. 이 스크립트는 CI에서 돌지 않는다 — 산출물이 저장소에 커밋돼 있고, 아이콘을 바꿀 때만 사람이 돌린다.

`purpose: "maskable"` 사본을 따로 두는 이유는 안드로이드가 아이콘을 기기 모양대로 잘라내기 때문이다. 여백 없는 아이콘을 그대로 쓰면 로고 가장자리가 잘린다.

## 6. 검증

| 확인 | 방법 | 결과 |
|---|---|---|
| manifest가 나오는가 | 프로덕션 서버 `GET /manifest.webmanifest` | `share_target`이 `POST`/`multipart/form-data`, 아이콘 3종 |
| 공유 POST | 실제 multipart 전송 | 200 `text/html; charset=utf-8` |
| 원문이 주소에 없는가 | 응답 헤더·본문 | 주소는 `/check/shared` 고정, 값은 본문 JSON 태그 안 |
| 응답이 남지 않는가 | 응답 헤더 | `cache-control: no-store, must-revalidate`, `x-robots-tag: noindex, nofollow` |
| 쿠키를 굽지 않는가 | 응답 헤더 | `set-cookie` 없음 (테스트로 고정) |
| UTF-8 왕복 | 한글 문자 + URL 전송 후 JSON 파싱 | 원문 일치 |
| 적대적 입력 | `</script><script>alert(1)</script>` 공유 | 원문 그대로 왕복, 문서의 `</script>`는 2개 그대로 |
| 크기 상한 | 60,000자 multipart | 413, 파싱 전에 거절 |
| multipart가 아닌 본문 | JSON POST | 400 + 붙여넣기 안내 |
| 주소창 직접 접근 | `GET /check/shared` | 303 → `/check` |
| 워커 캐시 정책 | `/sw.js` 헤더 | `no-cache, no-store, must-revalidate` + `Service-Worker-Allowed: /` |
| 오프라인 화면 | `GET /offline` | 200, 112·1332·118 `tel:` 링크 |
| 프론트 회귀 | `npm test` | 15 files, **103 passed** |
| 타입·린트 | `npx tsc --noEmit`, `npm run lint` | 둘 다 통과 |
| 프로덕션 빌드 | `npm run build` | 성공. `/manifest.webmanifest`·`/offline`·`/check/shared` 라우트 생성 |
| 백엔드 무변경 | `pytest -q` | 417 passed, 1 skipped |

## 7. 남은 것

**실도메인에서 설치를 해 본 적이 없다.** PWA 설치와 서비스 워커는 HTTPS(또는 localhost)를 요구하고, 안드로이드 공유 시트에 앱이 뜨려면 실제로 설치돼 있어야 한다. 즉 **이 문서의 공유 경로는 서버 쪽 왕복까지만 검증됐고, 공유 시트에서 실제로 고르는 것은 P0-4 이후에야 확인된다.** 그래서 이 작업을 P0-4 바로 앞에 두었다.

**iOS는 공유 시트에 뜨지 않는다.** Safari는 `share_target`을 구현하지 않는다. iOS에서는 홈 화면 추가와 오프라인 화면까지만 얻고, 공유는 복사·붙여넣기로 남는다.

**서비스 워커 업데이트 알림이 없다.** `skipWaiting`으로 새 워커가 바로 올라오지만, 이미 열려 있는 탭에 "새 버전이 있다"를 알리는 경로는 없다. 화면 HTML을 캐시하지 않으므로 다음 이동에서 새 코드를 받는다.

**공유 인계는 sessionStorage에 의존한다.** 프라이빗 모드 등에서 접근이 막히면 `/check`가 빈 입력창으로 열린다. 조용히 실패하는 대신 알려주는 편이 나은지는 실기기 확인 뒤에 판단한다.
