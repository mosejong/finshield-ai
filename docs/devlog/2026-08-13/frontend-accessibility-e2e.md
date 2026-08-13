# 프론트엔드 접근성 패스 · 구조적 a11y 회귀 테스트

- 날짜: 2026-08-13
- Claude 원본 브랜치: `feature/frontend-accessibility-e2e`
- PM 검수 브랜치: `feature/frontend-accessibility-e2e-final`
- PM worktree: `finshield-ai-frontend`
- 범위: `web/` 전용 (문서는 `docs/13-frontend-architecture.md`, 본 devlog만 수정)

## 배경

`docs/13` 8절 "남은 작업"에 접근성 감사와 자동 검사가 미완으로 남아 있었다. 기존
화면은 이미 `aria-labelledby` 섹션, `role="alert"` 오류, 장식 아이콘 `aria-hidden`,
`aria-current`, 44px 터치 타깃, 시맨틱 색 토큰 등 기반이 좋았다. 이번 작업은 그 위에
키보드 흐름·포커스 가시성·라이브 영역·움직임 최소화·구조적 자동 회귀를 프로덕션
관점에서 보강했다. 백엔드 계약과 금융 로직 경계는 건드리지 않았다.

## 사용자에게 보이는 변경

- **본문 건너뛰기 링크**: 모든 화면 첫 포커스로 `본문으로 건너뛰기`가 나타나 좌측
  네비를 건너뛰고 `#main-content`로 이동한다. 평소에는 `sr-only`로 숨는다.
- **공통 포커스 표시**: 키보드 이동(`:focus-visible`) 시 링크·버튼·카드·요약에 항상
  보이는 `--ring` 아웃라인이 뜬다. 마우스 클릭에는 뜨지 않는다. 다크모드 대비 유지.
- **움직임 최소화 존중**: 시스템이 움직임 축소를 요청하면 스피너·펼침 회전·색 전환이
  거의 즉시 끝난다.
- **비동기 상태 안내**: 프로필·상품·재테크·대출·분석 결과의 "불러오는 중/확인하고
  있습니다" 로딩과 대출 계산 완료가 `role="status"`로 스크린리더에 전달된다. 오류는
  기존대로 `role="alert"`.
- **의심 메시지 입력 폼**: textarea에 `id`와 `aria-describedby`(설명·글자수·개인정보
  주의)를 연결하고 글자수 배지에 접근 가능한 라벨을 붙였다. 제출 버튼에 `aria-busy`.
- **개인정보/세션 설명 보강**: `/profile`에 "이 금융상태는 지금 브라우저의 익명
  세션에만 연결되며, 쿠키를 지우거나 다른 브라우저·기기로 열면 복구할 수 없다"는
  안내를 추가했다 (`docs/23`, `docs/24`의 무복구 정책과 일치).

## 안전/개인정보 관점에서 유지한 것

- 실패를 안전으로 바꾸지 않는다: 로딩/오류 문구, "결과를 확인하지 못했다고 안전한
  것은 아니다" 계열 안내를 그대로 두고 표현 계층만 보강했다.
- 근거를 지어내지 않는다: `EvidenceList`는 계속 `verified`에 따라 "공식 확인 전"을
  명시하며, 새 필드·기관·URL·검증 상태를 만들지 않았다.
- 금융 로직 금지선 유지: 컴포넌트에 이자·상환·적격성·점수 계산을 추가하지 않았다.
  live/mock 출처 배지(`MockBadge`)와 disclaimer는 그대로다.
- 삭제 어포던스는 이미 존재(프로필 1건 삭제, 익명 계정 전체 삭제, 분석 결과 삭제)하며
  서버 삭제 성공 후에만 로컬 identity를 지우는 기존 흐름을 바꾸지 않았다.

## 자동 검증

`web/components/a11y.test.tsx` — `react-dom/server`로 컴포넌트를 정적 렌더링해 마크업
문자열의 접근성 계약을 검사한다(브라우저 DOM 불필요, CI 친화적):

- AppShell: `#main-content` + `tabindex="-1"` main 랜드마크, `주요 메뉴` nav 접근 이름
- PageHeader: 화면당 h1 1개 + 뒤로 링크
- EvidenceList: 확인 전 항목 "공식 확인 전" 명시, 확인된 항목만 있으면 미노출, tel 링크
- RiskLevelHeader: "현재 상황 위험도 …" 문구, 좌측 바 `aria-hidden`
- RiskSignalList: 빈 상태 문장 / 목록 렌더
- ActionChecklist: 완료 토글 `aria-pressed` + 접근 가능한 이름
- StateSelector: `role="radiogroup"` + 라디오 7개
- MockBadge: live 무출력, mock 라벨 노출
- MetricList/ProfileFacts: 목록·정의목록 구조

### 실행 결과 (web/)

- `npm test` → 11 파일 47 테스트 통과 (신규 a11y 포함)
- `npm run build` → 성공 (11 라우트 생성, TypeScript 통과)
- `npx tsc --noEmit` → 오류 없음 (exit 0)
- `npm run lint` → 오류 없음 (exit 0)
- `next start` 실서버 SSR HTML 확인:
  - `/` : `본문으로 건너뛰기`, `id="main-content"`, `tabindex="-1"`, `주요 메뉴` nav ×2
  - `/check` : `id="check-message"` + `aria-describedby="check-message-help check-message-count check-message-privacy"`
  - `/products/simulate`, `/onboarding` : 스킵 링크·main 랜드마크 정상

## 남은 한계 (미검증으로 명시)

- 이 환경에는 브라우저 자동화(Playwright 등)·디스플레이 도구가 없어 실제 렌더링
  기반 검증(키보드 탭 순서 실동작, 포커스 링 시각 확인, 다크모드 토글, 375/768/1280
  뷰포트 레이아웃, 실제 스크린리더 낭독)은 수행하지 못했다. SSR HTML 구조와 구조적
  회귀 테스트로만 확인했으며, 후속으로 `docs/13` 4절의 헤드리스 Chrome iframe 하네스
  절차로 육안·상호작용 검수가 필요하다.
- iOS Safari의 `env(safe-area-inset-bottom)`·`100dvh`는 실기기·시뮬레이터가 없어
  이번에도 미검증이다.
- 폼 필드별 오류를 `aria-invalid`/`aria-describedby`로 개별 연결하는 것은 후속 과제로
  남긴다(현재는 폼 단위 `role="alert"` 요약).
- 클라이언트 라우팅 시 결과 화면으로의 포커스 이동은 Next 기본 route announcer에
  의존한다. 명시적 포커스 매니저는 도입하지 않았다.

## PM 검수·교정

- 스킵 링크가 `main#main-content`로 이동한 뒤 전역 `main:focus`가 포커스
  표시를 지우는 문제를 확인해 해당 억제를 제거했다.
- 프로필의 “로컬 프로토타입 서버” 설명을 현재 서버 저장 경계·배포 환경 암호화
  계약에 맞게 교정했다.
- 파생지표 endpoint와 익명 데이터 수명주기가 이미 구현됐는데도 미구현으로 남아 있던
  아키텍처 문서와 계약 주석을 현재 live 흐름에 맞췄다.
- 브라우저에서 mock 배지가 “백엔드 연동 전”이라고 설명하는 오래된 문구를 발견해
  “실제 사용자 데이터가 아닌 고정 예시”로 교정했다.
- 루트 `SKILL.md`의 잘못된 fraud·evidence API 방향을 실제
  `/api/v1/analyze` 응답 계약과 현재 auth·metrics·guidance endpoint에 맞췄다.
- mock evidence 주석·안내도 미구현 evidence endpoint를 기다리는 표현에서
  `analyze.official_sources`와 구분되는 고정 예시 표현으로 교정했다.

### PM 재검증 (17:52~18:01 KST)

- 최신 `origin/main`(`5c45429`) 기반 별도 검수 워크트리로 Claude 변경만 복제했다.
- 인앱 브라우저의 실제 viewport를 375×812, 768×900, 1280×900으로 바꿔
  `/check`를 검사했다. 세 크기 모두 가로 overflow가 없었다.
- 375·768에서는 하단 네비가 보이고 side nav가 숨었으며, 1280에서는 side nav가
  보이고 하단 네비가 숨었다. main 폭은 각각 375, 560, 680px이었다.
- 스킵 링크를 활성화한 뒤 URL hash가 `#main-content`로 바뀌고
  `main#main-content[tabindex="-1"]`가 포커스를 받으며 2px solid outline이
  유지되는 것을 확인했다.
- 현재 브라우저의 다크 색상 모드에서 3개 viewport를 화면으로 확인했다.
- `/profile`에서 가로 overflow가 없고, 서버 저장 경계·배포 암호화·익명 세션
  무복구 안내와 새 mock 배지 설명이 실제 DOM에 노출되는 것을 확인했다.
- 인앱 브라우저에서는 로컬 Next 클라이언트 입력 이벤트가 React state까지 전달되지
  않아 분석 submit·sessionStorage 결과 이동은 SSR 상태를 벗어나지 못했다. 따라서
  이 항목은 브라우저 E2E 통과로 기록하지 않고 기존 unit/API 회귀로 보완했다.
- frontend: 11 files, 47 tests passed; production build·TypeScript·lint 통과.
- 최신 main Python: 209 passed, 1 skipped, 기존 TestClient 경고 1건.
- `git diff --check`: 통과.

## 커밋·PR

- 구현·PM 교정 commit: `7b8135e`
- PR: #56, https://github.com/mosejong/finshield-ai/pull/56
- 생성: 2026-08-13 18:05:43 KST, draft
- GitHub Actions Linux CI: 진행 중
- 병합 시각·merge commit: PM 승인 후 기록

## 변경 파일

- `web/app/globals.css` — `:focus-visible` 공통 아웃라인, `prefers-reduced-motion`
- `web/app/layout.tsx` — 본문 건너뛰기 링크
- `web/components/layout/AppShell.tsx` — `main#main-content` `tabindex=-1`
- `web/app/check/page.tsx` — textarea `id`/`aria-describedby`, 글자수 라벨, 제출 `aria-busy`
- `web/app/onboarding/page.tsx`, `web/app/profile/page.tsx`,
  `web/app/check/result/[id]/page.tsx` — 로딩 `role="status"`, 프로필 세션 안내 보강
- `web/components/finance/LoanWhatIf.tsx` — 결과 `role="status"`, 제출 `aria-busy`
- `web/components/finance/ProductRecommendations.tsx`,
  `web/components/finance/ProductDetail.tsx`,
  `web/components/finance/ProductComparison.tsx`,
  `web/components/finance/WealthGuidance.tsx` — 로딩 `role="status"`
- `web/components/a11y.test.tsx` — 신규 구조적 접근성 회귀 테스트
