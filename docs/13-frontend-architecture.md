# 13. Frontend Architecture

FinShield 프론트엔드는 `web/` 하위 Next.js(App Router) 앱이다.
루트의 Python 패키지 `app/` 과 Next 의 `app/` 디렉토리가 이름 충돌하므로 프론트엔드 전체를 `web/` 안에 둔다.

```
finshield-ai/
  app/      FastAPI 패키지 (프론트 작업에서 수정하지 않음)
  docs/
  tests/
  web/      Next.js
    app/          라우트
    components/   화면 컴포넌트
    lib/          데이터·포맷 레이어
```

스택: Next.js 16 (App Router, Turbopack) · TypeScript · Tailwind CSS v4 · shadcn/ui · zod · lucide-react

---

## 1. IA

최상위 4개 영역. 근거/출처는 탭이 아니라 모든 수치·조언에 붙는 횡단 요소다.

| 경로 | 화면 | 상태 |
| --- | --- | --- |
| `/` | Home 금융 안전 대시보드 | 구현 |
| `/onboarding` | 금융 프로필 입력 | 구현 |
| `/profile` | 내 금융상태 | 구현 |
| `/check` | 의심 메시지 입력 + 피해 단계 선택 | 구현 |
| `/check/result/[id]` | 위험 분석 결과 + 대응 액션 | 구현 |
| `/products` | 금융 목표 기반 공식 상품 후보 | 구현 |
| `/products/simulate` | 현재 금리와 변경 금리의 대출 What-if 비교 | 구현 |
| `/learn/wealth` | 공식 근거 기반 재테크 기초 교육 | 구현 |
| `/products/[id]`, `/products/compare` | 공식 상품 상세·2개 원문 비교 | 구현 |
| `/profile` 파생지표 | backend 월 현금흐름·상환비율·비상자금 기간 | 구현 |
| `/` 현재 금융상태 | 저장 profile + backend 파생지표 live 요약 | 구현 |
| `/evidence/[id]` | 근거 상세 | 미구현 (목록 컴포넌트만 존재) |
| `/check/shared` | 공유 시트 수신 (POST 전용 Route Handler, 화면 아님) | 구현 |
| `/offline` | 연결 없음 안내 (서비스 워커 폴백) | 구현 |

`/check/shared` 는 안드로이드 공유 시트가 POST 하는 곳이고 사용자가 머무는 화면이 아니다. 받은 내용을 `/check` 입력창까지 옮기고 곧바로 `location.replace` 로 빠진다. **GET 쿼리스트링을 쓰지 않는 이유**는 공유되는 값이 사용자가 받은 문자 원문이라 주소에 실으면 브라우저 기록·액세스 로그·`Referer` 에 남기 때문이다. 설계와 검증은 `docs/30-pwa-and-share-target.md`.

설치 유도(`components/pwa/InstallHint.tsx`)는 **결과 화면에만** 둔다. Home 은 블록 4개로 고정이고, 설치의 값어치는 결과를 한 번 본 뒤에야 와닿는다.

**`/check` 는 프로필 없이 동작한다.** 의심 문자를 방금 받은 사람에게 온보딩을 먼저 요구하면 이탈한다. 프로필은 개인화 품질만 올리는 선택 요소이며, 있으면 `persona` 만 요청에 실린다.

---

## 2. 화면 규칙

### Home — 정확히 4블록

1. 현재 금융상태 2. 지금 확인할 금융정보 3. 위험한 금융 연락 확인 4. 다음 행동

블록당 카드 1개. 숫자를 늘어놓는 대시보드로 만들지 않는다.

### 위험 분석 결과 — 순서 고정

```
위험 수준(문장) → 감지된 위험 신호 → 왜 위험한지 → 지금까지 하신 것
  → 지금 해야 할 행동 → 공식 근거 → (접힘) 분석 상세 → 고지
```

숫자 점수는 **`AnalysisDetails` 안에서만** 노출된다. 화면 첫 진입에 점수를 보여주면 사용자가 "87점이 얼마나 위험한가"를 해석하느라 정작 읽어야 할 행동 지시를 지나친다.

### 등급은 문구와 현재 상태를 함께 설명한다

최상단 라벨은 **"현재 상황 위험도 낮음/주의/높음"** 이다.

Scenario Engine v0.1은 legacy 텍스트 점수와 별도로 canonical 위험 신호, 고위험 조합,
사용자가 선택한 `UserState`의 최소 위험도를 결합해 최종 `risk_level`을 정한다.
따라서 계좌 접근수단 공유, 앱 설치, 출처 불명 자금 수취, 송금 상태는 문구 신호가
낮아도 `high`가 된다.

대응:
- `risk_level`은 백엔드 값을 그대로 사용한다
- recovery state를 프론트에서 다시 승격하거나 낮추지 않는다
- `risk_score`는 legacy baseline, `risk_level`은 현재 상태를 포함한 최종 등급이라는 차이를 분석 상세에 설명한다

### 공포 유발 방지 (강제)

- 위험색 full-bleed 배경 금지 — 좌측 4px 바 / 아이콘 / 텍스트 / tint 배경까지만
- 사이렌·해골 아이콘, 경고 애니메이션 금지
- "당신은 사기 피해자입니다" 같은 단정 금지 → "이 요청은 정상 절차에 없는 요구입니다"
- 피해 단계 선택지는 사용자를 탓하지 않는 평서문 ("계좌·카드·인증번호를 넘겼어요")

---

## 3. 디자인 토큰

`web/app/globals.css` 한 곳에서만 색을 정의한다.

| 토큰 | Light |
| --- | --- |
| `--primary` | `#1F3A5F` 딥 네이비 (신뢰) |
| `--safe` | `#0E7C6B` 틸 (안전·확인됨) |
| `--risk-low` | `#157347` / bg `#ECF7F0` |
| `--risk-medium` | `#B26B00` / bg `#FDF5E6` |
| `--risk-high` | `#B3401F` / bg `#FBEDE8` (rust, 순빨강 아님) |

**컴포넌트에서 `dark:` 유틸리티를 쓰지 않는다.** 색은 항상 시맨틱 토큰으로 참조하고, 다크모드는 `@media (prefers-color-scheme: dark)` 와 `.dark` 에서 토큰 값만 교체한다. 이렇게 해야 색 결정이 한 파일에 모인다.

타이포 4단: `text-display`(화면당 1개) / `text-title` / `text-body` / `text-caption`.
웹폰트를 내려받지 않는다 — 시스템 한글 폰트 스택을 쓴다. 숫자는 `tabular-nums`.

전문용어는 쓰지 않는다: DSR → "소득 대비 빚 부담"(공식 DSR과 다름 명시), 가처분소득 → "매달 쓸 수 있는 돈", provenance → "출처".

---

## 4. 반응형

375px 기준 mobile-first.

| 뷰포트 | 레이아웃 |
| --- | --- |
| `< 640` | 단일 컬럼 + 하단 네비 |
| `640–1023` | 본문 `max-w-[560px]` 중앙, 하단 네비 유지 |
| `>= 1024` | 좌측 `SideNav w-60` + 본문 `max-w-[680px]`, 하단 네비 숨김 |

터치 타깃 최소 44px. 폼의 주 CTA 는 하단 네비 위에 sticky.

### 375px 확인 방법 (헤드리스 함정)

헤드리스 Chrome 은 창 너비를 **최소 500px 로 강제**한다. `--window-size=375,900 --screenshot` 을 주면 500px 로 레이아웃한 뒤 375px 만 잘라 저장하므로, 멀쩡한 화면이 오른쪽이 잘린 것처럼 보인다. 이것으로 오버플로를 판단하면 안 된다.

실제 375px 을 보려면 폭 375px `<iframe>` 안에 페이지를 띄우고 창은 500px 이상으로 잡는다. 이때 **하네스 HTML 을 `web/public/` 에 두어 같은 오리진에서 띄운다.** `file://` 에서 띄우면 서드파티 iframe 이 되어 스토리지가 파티셔닝되고, sessionStorage 를 읽는 화면(`/profile`, `/check/result/[id]`)이 하이드레이션되지 않은 채 "불러오는 중…"에서 멈춘다 — 앱 버그가 아니라 하네스 문제다.

`next start` 는 시작 시점에 `public/` 목록을 읽으므로, 하네스 파일을 넣은 뒤 서버를 재시작해야 서빙된다. 확인이 끝나면 하네스 파일은 지운다.

---

## 5. 데이터 레이어

```
lib/api/contracts.ts   zod — Scenario Engine과 프론트 화면 계약
lib/api/client.ts      fetch 래퍼 (타임아웃 8초, ApiError)
lib/api/analysis.ts    어댑터: live 응답 변환, 필드별 source 태깅
lib/api/explanation.ts LLM 설명 — 판정과 별도 호출 (타임아웃 25초)
lib/api/mode.ts        NEXT_PUBLIC_API_MODE=mock|live
lib/mock/*.ts          백엔드 미구현 영역의 임시 데이터
lib/format/*.ts        표시 포맷팅만
lib/store/*.ts         sessionStorage의 분석 결과·profile identity 보관
lib/store/explanation-store.ts  원문 인계 — 저장소가 아니라 메모리만 쓴다
```

### 하이브리드 모드

**필드마다 `source: "live" | "mock"` 을 붙여** 실제 Scenario Engine 결과와
백엔드 없이 보는 고정 예시를 구분한다.

| 화면 요소 | 백엔드 | 처리 |
| --- | --- | --- |
| 위험 수준 / 점수 / 신호 / scenario | 있음 | live |
| 위험 유형 후보 / 결정론적 요약 | 있음 | live |
| 대응 액션 | 있음 | live |
| 공식 근거 | 있음 | live + 검토일 표시 |
| 금융 프로필 CRUD | `/api/v1/profiles` | live, session에는 ID+persona만 보관 |
| 파생지표 | `/api/v1/profiles/{id}/metrics` | live 계산 완료값 표시 |
| 상품 후보 | `/api/v1/recommendations` | live, backend 상태·reason 그대로 표시 |
| 대출 What-if 시뮬레이션 | `/api/v1/loans/simulate` | live, 현재·변경 조건을 각각 계산 |
| 재테크 기초 가이드 | `/api/v1/guidance/wealth` | live, 입력 없는 고정 교육 계약 |
| 공식 상품 상세·비교 | `/api/v1/products/{id}`, `/api/v1/products/compare` | live, 같은 snapshot 원문 |
| 왜 위험한지 — 쉬운 말 설명 | `/api/v1/analyze/explanation` | live, 판정과 별도 호출. 배포에서 꺼져 있으면 자리를 만들지 않는다 |

### 금융 로직 금지선

- `web/` 어디에도 이자 계산, 상환액 계산, 적격성 판정이 없다.
- 파생지표는 프론트가 계산하지 않는다. live 모드는 백엔드
  `/api/v1/profiles/{id}/metrics`의 포맷된 `display` 값을 그대로 표시하고,
  mock 모드는 계산식 없는 고정 fixture를 표시한다.
- `lib/format/` 의 `risk_level → 색` 매핑은 표현이지 판정이 아니다.
- mock 은 백엔드 `risk_engine.py` 의 키워드 규칙을 복제하지 않는다. mock 모드는 입력과 무관한 고정 예시를 돌려주고 화면에 "예시"라고 적는다.

### 모델 문장은 결정론 요약을 대체하지 않는다

"왜 위험한지" 블록의 첫 문단은 백엔드 `summary` 다 — 규칙에서 바로 나오는 값이고
즉시 그려진다. LLM 설명은 그것을 **대체하지 않고 아래에 덧붙는다.** 8초쯤 뒤에
도착하며, 없어도 블록은 성립한다. 판단 근거의 자격을 갖는 것은 결정론 쪽이고,
화면에도 "위험 수준과 행동은 이 문장이 아니라 규칙 엔진이 정합니다" 를 적는다.

설명 요청은 판정이 아니라 **원문**을 보낸다. 클라이언트가 위험 수준을 실어
보내면 모델에게 안심시키는 문장을 쓰게 할 수 있기 때문에, 백엔드가 원문으로
판정을 다시 만든다. 그래서 결과 화면이 원문을 다시 갖고 있어야 하는데, 이것은
`sessionStorage` 가 아니라 모듈 메모리로만 넘긴다 — 붙여넣은 문자에는 이름과
계좌번호가 그대로 들어 있을 수 있다. 대가는 **새로고침하면 설명이 다시 붙지
않는 것**이고, 그 편이 낫다고 봤다. 자세한 근거는 `docs/34` 10절.

### 근거를 지어내지 않는다

`lib/mock/evidence.ts`는 백엔드 없이 화면을 보는 mock 모드에서만 사용한다.
live 모드는 백엔드 `official_sources`를 `verified: true`로 변환하고
`retrieved_at`을 확인일로 표시한다.

---

## 6. 백엔드 연동

현재 백엔드: `GET /health`, `POST /api/v1/analyze`,
`POST /api/v1/analyze/explanation`,
`POST/GET/DELETE /api/v1/auth/session`, `DELETE /api/v1/auth/account`,
`GET /api/v1/products`, `POST /api/v1/recommendations`,
`POST /api/v1/loans/simulate`, `POST/GET/PUT/DELETE /api/v1/profiles`,
`GET /api/v1/profiles/{id}/metrics`, `GET /api/v1/guidance/wealth`

`analyze`는 기존 필드에 더해 `fraud_types`, `summary`, `actions`,
`official_sources`를 반환한다. 프론트는 이 값을 mock으로 대체하지 않는다.

### CORS — 백엔드 수정 없이

FastAPI 에 `CORSMiddleware` 가 없어 브라우저가 `localhost:8000` 을 직접 호출하면 차단된다. 백엔드를 고치는 대신 **Next Route Handler 를 서버 사이드 프록시로** 쓴다.

```
브라우저 → POST /api/proxy/analyze (Next, 같은 오리진)
         → POST /api/v1/analyze     (FastAPI, 서버-서버)
```

설명은 같은 구조로 `/api/proxy/analyze/explanation` 을 따로 거친다. 하나로 합치지
않는 이유는 백엔드가 나눠 둔 이유와 같다 — 판정은 즉시 나오고 설명은 8초쯤 걸리므로,
합치면 위험 수준 표시가 설명을 기다리게 된다.

프로필도 같은 구조로 `/api/proxy/profiles`를 거친다. 프론트 enum은 backend의
연령·직업·신용·목표 enum과 일치시키고, adapter가 camelCase를 snake_case로
변환한다. `persona`는 fraud 입력용 UI 값이므로 FinancialProfile backend 요청에서
제외하고 profile ID와 함께 session에만 둔다.

대출 What-if는 `/api/proxy/loans/simulate`를 두 번 호출한다. 두 응답을 화면에서
나란히 표시할 뿐 차액·절감액·상환액을 프론트에서 계산하지 않는다. 한쪽이라도
실패하면 비교 전체를 실패로 처리하며 빈 값이나 유리한 결과로 대체하지 않는다.

재테크 기초 가이드는 `/api/proxy/guidance/wealth`를 통해 versioned 정적 교육
계약을 읽는다. 프로필·계좌·보유종목을 보내지 않고 backend module과 공식 source를
그대로 표시한다. 프론트는 투자 가능 여부, 상품 선택, 예상수익률을 판정하지 않는다.

부수 효과로 백엔드 주소가 클라이언트 번들에 노출되지 않는다. 그래서 `FINSHIELD_API_URL` 에는 `NEXT_PUBLIC_` 접두사를 붙이지 않는다.

### 실패를 안전으로 바꾸지 않는다

- 백엔드 호출 실패는 502 와 실제 사유로 전달한다. 조용히 "위험 없음"으로 바꾸지 않는다.
- 알 수 없는 `risk_level` 값은 `high` 로 매핑한다. 낙관하지 않는다.
- 실패 화면에도 "결과를 확인하지 못했다고 안전한 것은 아니다"라고 적는다.

### 개인정보

- 사용자가 붙여넣은 원문과 분석 결과는 `sessionStorage` 에만 둔다. `localStorage` 가 아니다 — 탭을 닫으면 사라진다.
- 프록시는 요청 본문을 로그로 남기지 않는다.
- 프로필은 주민등록번호·계좌번호·실명을 받지 않고, 나이·신용점수는 band 로만 받는다.
- 프로필 원문은 `sessionStorage`에 저장하지 않는다. 암호화 backend DB가 원본을
  보관하고 브라우저에는 profile UUID와 persona만 둔다. profile 요청 전 same-origin
  인증 프록시가 익명 세션을 확인·생성하며 원문 세션 토큰은 HttpOnly 쿠키에만 둔다.
  현재 브라우저 세션의 소유 profile을 찾지 못하면 재입력을 안내하며 빈 프로필이나
  저장 성공으로 바꾸지 않는다.
- 상품 후보 요청에는 session profile 전체가 아니라 backend 규칙이 실제 사용하는
  `goal` 하나만 보낸다. 소득·부채·신용·연령은 전송하지 않는다.

---

## 7. 실행

```bash
cd web
npm install
npm run dev            # http://localhost:3000

# 실제 분석 서버와 함께 (별도 터미널)
uvicorn app.main:app --reload
```

환경변수는 `web/.env.example` 참고. 백엔드 없이 화면만 보려면 `NEXT_PUBLIC_API_MODE=mock`.

검증: `npm run build` → `npx tsc --noEmit` → `npm run lint` (타입 생성이 build 에 포함되므로 순서를 지킨다)

---

## 8. 접근성 계약

프로덕션 지향 접근성 패스로 다음을 보강했다 (`docs/devlog/2026-08-13/frontend-accessibility-e2e.md`).

- **본문 건너뛰기 링크**: `app/layout.tsx`의 첫 포커스 요소가 `#main-content`로 이동한다. 대상은 `AppShell`의 `main#main-content`(`tabIndex=-1`)다.
- **공통 포커스 표시**: `globals.css`가 `:focus-visible`에 `--ring` 아웃라인을 한 곳에서 보장한다. 개별 컴포넌트는 추가 링을 붙여도 되지만 없어도 항상 보인다.
- **움직임 최소화**: `@media (prefers-reduced-motion: reduce)`로 스피너·전환을 즉시 종료한다.
- **라이브 영역**: 로딩은 `role="status"`(polite), 오류는 `role="alert"`(assertive). 비동기 결과(대출 계산 등)는 별도 `role="status"`로 한 번 알린다.
- **폼 라벨**: 의심 메시지 textarea는 `aria-describedby`로 설명·글자수·개인정보 주의를 연결하고, 제출 버튼은 `aria-busy`로 진행 상태를 노출한다.

PM 검수에서 375·768·1280 viewport의 가로 overflow와 nav 전환, 다크 화면,
스킵 링크 활성화 후 main 포커스·2px outline을 실제 인앱 브라우저로 확인했다.
검수 범위와 브라우저 클라이언트 이벤트 제한은 개발일지에 구분해 기록한다.

### 자동 검사

`web/components/a11y.test.tsx`가 `react-dom/server` 정적 렌더링으로 랜드마크·폼 라벨·라이브 영역·장식 아이콘 숨김·근거 표시 계약을 CI에서 검증한다. 브라우저 DOM은 필요 없다. 검증 순서는 기존과 같다: `npm test` → `npm run build` → `npx tsc --noEmit` → `npm run lint`.

## 9. 남은 작업

- 로그인 기반 계정 전환·기기 간 복구는 익명 MVP 범위 밖이며 현재 지원하지 않음
- 접근성 후속 검수: 실제 스크린리더 낭독, 명도대비 AA 정량 측정, 전체 키보드
  탭 순서, 라이트 색상 모드. 다크 화면·375/768/1280·스킵 링크 포커스는 PM 확인 완료.
- 실기기 확인 (지금까지는 헤드리스 Chrome 캡처와 실서버 SSR HTML 확인만). iOS Safari 의 `env(safe-area-inset-bottom)` 과 `100dvh` 동작은 시뮬레이터로 재확인 필요
- 폼 필드별 `aria-invalid`/오류 개별 연결 (현재는 폼 단위 `role="alert"` 요약)
- 실기기 PWA 확인 — 홈 화면 설치, 안드로이드 공유 시트에 실제로 뜨는지, 서비스 워커 오프라인 폴백. HTTPS 요건 때문에 실도메인(`docs/28` P0-4) 이후에야 가능하다
