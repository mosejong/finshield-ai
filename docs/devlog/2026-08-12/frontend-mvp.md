# Frontend MVP 개발일지

## 작업 정보

- 작업일: 2026-08-12 (KST)
- Claude Code 작업 종료: PM 인수 시점 이전, 정확한 시각 미기록
- PM 검수 시작: 15:00 KST
- 담당 영역: 프론트엔드 및 API 표시 어댑터
- 작업 브랜치: `feature/frontend-mvp`
- 상태: 최신 Scenario Engine 계약 통합 및 PM 검증 완료, push·PR 대기

## 목표

금융 경험이 적은 사용자가 금융상태, 의심 연락의 위험 신호, 이미 취한 행동,
지금 해야 할 대응과 공식 근거를 모바일 우선 화면에서 이해하도록 한다. 금융 계산과
위험도 판정은 프론트에서 수행하지 않는다.

## Claude Code 구현 인수

- `/`, `/onboarding`, `/profile`, `/check`, `/check/result/[id]`, `/products` 구현
- 375/768/1280 반응형과 light/dark 캡처 확인
- `lib/api`, `lib/mock`, `lib/format`, `lib/store` 레이어 분리
- CORS를 피하는 Next 서버사이드 `/api/proxy/analyze` 구현
- sessionStorage를 `useSyncExternalStore`로 구독해 렌더 안정성 확보
- 실패 시 502와 안전 불확실성 문구 유지
- build, TypeScript, lint와 당시 백엔드 39 tests 통과 보고
- 루트 `AGENTS.md`, `.agents/`는 시작부터 있던 미추적 파일로 작업 범위에서 제외

## PM 검수에서 확인한 차단 이슈

1. 프론트 브랜치가 Scenario Engine v0.1 병합 전 `main`을 기준으로 해 백엔드
   `summary`, `actions`, `official_sources`를 사용하지 않고 mock으로 덮고 있었다.
2. 문서와 최상단 라벨이 `risk_level`을 문구 전용 등급으로 설명했지만, 최신
   백엔드는 canonical 신호와 `UserState` 최소 위험도까지 최종 등급에 반영한다.
3. 분석 상세가 모든 public signal 가중치를 `risk_score`에 합산한다고 설명했지만,
   점수는 기존 다섯 legacy 규칙만 사용하는 호환 baseline이다.
4. live 분석 어댑터의 신규 계약 변환을 고정하는 자동 회귀 테스트가 없었다.

## PM 수정 방향

- Claude Code 원본은 `feat: add frontend MVP shell` 독립 커밋으로 보존한다.
- 최신 `main` 위로 rebase하고 문서 색인에서 13·14 문서를 모두 유지한다.
- Scenario Engine 응답의 유형 후보, 요약, 행동, 공식 근거를 live로 변환한다.
- 행동 code/priority는 표시 그룹과 전화 링크로만 변환하며 위험도를 재판정하지 않는다.
- 공식 근거는 백엔드 검토일과 URL을 보존하고 `verified: true`로 표시한다.
- Vitest로 live 변환, 안전한 unknown 위험도 처리, 구형 계약 거절을 회귀 검증한다.

## 시간순 PM 통합 기록

### 15:00 — 인수 및 변경 동결

- Claude Code가 더 이상 파일을 수정하지 않는다는 사용자 확인을 받았다.
- 프론트 build, TypeScript, lint와 구형 기준 백엔드 39 tests를 재현했다.
- 최신 Scenario Engine과의 계약 차이를 PR 차단 이슈로 분류했다.

### 15:04 — Claude Code 원본 커밋

- 프론트 82개 파일만 명시적으로 스테이징했다.
- 루트 `AGENTS.md`, `.agents/`는 미추적 상태로 제외했다.
- 원본 커밋 메시지: `feat: add frontend MVP shell`

### 15:06 — 최신 main rebase

- PR #2 Scenario Engine과 PR #3 PM 문서가 포함된 최신 `origin/main` 위로 rebase했다.
- `docs/README.md` 한 곳의 충돌에서 13 frontend architecture와 14 development workflow를 모두 보존했다.

### 15:12 — Scenario Engine live 계약 통합

- 신규 응답 필드를 Zod로 검증한다.
- `summary`, `actions`, `official_sources`를 mock 없이 화면 계약으로 변환한다.
- `fraud_types`를 분석 상세의 쉬운 한국어 유형 후보로 표시한다.
- `DO_NOT_*`는 하지 말 것, priority 1은 지금 바로, 나머지는 오늘 안에 표시한다.
- 112, 1394, KISA 118 행동은 전화 링크를 제공한다.
- 공식 출처 URL과 검토일을 보존하고 live 근거로 표시한다.
- `risk_score`와 최종 `risk_level`의 의미 차이를 화면과 문서에 반영했다.

### 15:14 — 자동 검증 추가

- Vitest 3개: live 변환·행동/근거 연결, unknown 위험도 보수 처리, 구형 계약 거절
- GitHub Actions web job에 `npm test`를 추가했다.
- npm audit 결과 알려진 취약점 0건을 확인했다.

### 15:19 — production live 통합 검증

- 실제 FastAPI와 production Next 서버를 함께 실행했다.
- `shared_account_access`와 OTP 요구 문구를 제출해 최종 `high`를 확인했다.
- 요약, 행동 6개, 112·1394 전화 링크, 공식 출처 4개와 검토일이 모두 live로 표시됐다.
- live 결과에 `준비 중` 또는 `예시` 배지가 없음을 확인했다.
- 분석 상세에서 legacy 점수 25와 현재 상태 기반 high 등급의 차이가 설명되는지 확인했다.
- 375px 뷰포트에서 헤더, 신호, 요약, 상태, 행동과 하단 네비에 가로 오버플로가 없음을 확인했다.

### 15:23 — 디자인 토큰 규칙 최종 교정

- 금지 패턴 재검사에서 shadcn 생성 UI 7개에 남은 `dark:` 유틸리티 10곳을 확인했다.
- `badge`, `button`, `checkbox`, `input`, `radio-group`, `select`, `textarea`의
  dark 전용 변형을 제거하고 `globals.css` 시맨틱 토큰만 사용하도록 맞췄다.
- 앱 로직과 상태 판정에는 변경이 없다.

## 범위 통제

- 백엔드 `app/`, `tests/`, `requirements.txt` 수정 없음
- 루트 `AGENTS.md`, `.agents/` 수정·스테이징 없음
- 금융 계산·대출 적격성·위험도 재계산 추가 없음

## 검증 계획

- `npm run build`
- `npx tsc --noEmit`
- `npm run lint`
- `npm test`
- 최신 `main` 기준 `pytest -q`
- `git diff --check`
- live FastAPI + Next proxy 통합 확인

## 검증 결과

- `npm run build`: 통과, 8 routes
- `npx tsc --noEmit`: 통과
- `npm run lint`: 통과
- `npm test`: **3 passed**
- 최신 `main` 기준 `pytest -q`: **75 passed**
- `git diff --check`: 통과
- production live 통합과 375px 시각 검수: 통과
- 알려진 경고: Starlette `TestClient` 사용 중단 예정 경고 1건

## 커밋·PR 정보

- Claude Code 원본 커밋: `3713e40cdb65b8024594d82f18820f9a9b17d65b`
- 통합 수정 커밋: `9fe562c8530fc77c2fba2c959fcc266e5f210552`
- 통합 커밋 메시지: `fix: integrate frontend with scenario engine`
- push: 수행 전
- PR 방향: `feature/frontend-mvp` → `main`
- PR: 생성 전
