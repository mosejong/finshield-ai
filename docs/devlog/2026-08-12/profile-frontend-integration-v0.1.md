# FinancialProfile 프론트 연결 v0.1 개발일지

## 작업 정보

- 작업일: 2026-08-12 (KST)
- 시작: 18:27 KST
- 담당 영역: 프론트엔드
- 작업 브랜치: `feature/profile-frontend-integration-v01`
- 작업 디렉터리: `C:\Users\user\Documents\Codex\finshield-ai-main`
- 로컬 구현·검증 완료: 18:45 KST
- Draft PR 생성: 18:46 KST
- PM 검수·초기 CI 완료: 18:48 KST
- Ready 전환·병합: 18:50 KST
- 상태: PR #29 PM 검수·CI 통과 후 `main` 병합 완료

## 목표

온보딩에서 입력한 금융 프로필을 백엔드 `/api/v1/profiles`에 생성·교체하고,
브라우저에는 불투명 profile ID와 사기 분석용 persona만 보관한다. 프로필 화면과
상품·사기 분석 흐름은 ID로 서버 원본을 다시 조회해 사용한다.

## 변경 이유

기존 프론트는 소득·부채를 포함한 profile 전체를 `sessionStorage`에만 저장했다.
백엔드 CRUD v0.1이 병합됐으므로 서버를 source of truth로 전환하고, 프론트·백엔드
enum과 필수 필드 계약을 정확히 일치시켜야 한다.

## 예정 범위

- backend profile 응답 zod 계약과 양방향 어댑터
- Next 서버사이드 profile 프록시
- sessionStorage에는 profile ID와 persona만 저장
- 생성·조회·전체 교체·삭제 UI 연결과 명시적 실패 상태
- 연령·직업·신용·목표 enum을 backend 계약과 정렬
- 프론트 어댑터·저장 흐름 테스트
- 프론트 아키텍처 문서와 본 개발일지

## 비범위

- 백엔드 `app/`, `tests/`, requirements 변경
- 프로필 파생지표 계산
- PostgreSQL·인증·소유권 검증
- 상품 적격성·대출 금액 계산
- `main` 직접 수정

## 개인정보·보안 경계

- 주민번호, 계좌번호, 비밀번호, OTP를 입력 계약에 추가하지 않는다.
- 프로필 원문을 프록시나 브라우저 console에 기록하지 않는다.
- 브라우저에는 서버 UUID와 persona만 보관한다.
- backend 404·503·연결 실패를 빈 프로필이나 저장 성공으로 바꾸지 않는다.
- UUID는 인증이 아니므로 public deployment 준비 완료로 표현하지 않는다.

## 검증 계획

- request mapping에서 UI 전용 persona 제외 확인
- backend enum·snake_case·Decimal 응답 변환 확인
- 생성 후 ID 저장, 재조회, PUT 교체, DELETE 흐름
- 서버 재시작으로 404 발생 시 사용자에게 재입력 안내
- `npm test`, build, TypeScript, lint
- 전체 Python 회귀와 실제 브라우저 생성·조회·삭제 검증
- `git diff --check`, 변경 범위 확인

## 시간순 작업 기록

### 18:27 — 계약 차이 확인·범위 확정

- frontend와 backend의 연령·직업·신용·목표 enum이 서로 달라 임의 매핑 시
  의미가 왜곡될 수 있음을 확인했다.
- backend enum을 UI 계약의 기준으로 사용하고 화면 표시 label만 쉬운 한국어로
  유지하기로 결정했다.
- backend가 요구하지만 기존 UI에 없던 `emergency_fund_target_months`와
  `business_owner`를 사용자에게 직접 입력받도록 했다. 값을 추정하지 않았다.
- fraud용 `persona`는 backend FinancialProfile 필드가 아니므로 profile 요청에서는
  제외하고 브라우저 identity에만 보관한다.

### 18:29 — backend 계약·adapter·proxy 구현

- backend snake_case profile/resource 응답을 zod strict schema로 검증한다.
- Decimal JSON 문자열은 검증 후 화면용 숫자로 변환한다.
- camelCase UI profile을 backend 필수 필드로 변환하며 `loan_items`는 UI가 상세
  대출을 받지 않으므로 빈 목록, 선택 필드는 `null`로 명시한다.
- Next route handler에 POST와 UUID 단건 GET/PUT/DELETE proxy를 추가했다.
- FastAPI 주소는 서버에만 두며 프로필 원문을 console이나 application log에
  기록하지 않는다.
- provider 실패는 502, profile 저장 한도는 503, 존재하지 않는 ID는 404로
  전달하고 성공·빈 profile로 바꾸지 않는다.

### 18:32 — session identity와 화면 흐름 구현

- 기존 `finshield:profile` 전체 JSON 저장을 중단했다.
- 새 session 값에는 `profileId`, fraud 분석용 `persona`만 기록한다.
- 저장 성공 시 legacy profile 원문을 session에서 제거한다.
- `useSyncExternalStore` 기반 상태가 ID로 backend profile을 다시 조회하고
  loading/ready/error/empty를 구분한다.
- 서버 재시작 또는 잘못된 ID로 400/404가 발생하면 identity를 제거하고 재입력
  안내를 표시한다.
- 온보딩은 최초 POST와 기존 ID의 PUT을 구분하고, 프로필 화면 삭제는 backend
  DELETE 성공 전까지 로컬 성공 상태로 바꾸지 않는다.
- 상품과 fraud 화면은 비동기 profile 조회가 끝난 후 goal/persona를 사용한다.

### 18:36 — 단위·정적 검증과 환경 복구

- 별도 worktree에 `node_modules`가 없어 최초 검사 도구가 의존성을 찾지 못했다.
- `package-lock.json` 그대로 `npm ci`를 실행했고 699 packages, 취약점 0건을
  확인했다. package manifest와 lockfile은 변경되지 않았다.
- build 전에 직접 `tsc`를 실행하면 Next 생성 타입 `LayoutProps`가 없어 실패하는
  기존 실행 순서를 확인했다. 문서대로 build 후 TypeScript를 실행해 통과했다.
- strict frontend 입력 계약에 미승인 필드 거부와 backend 일관성 검증을 추가했다.

### 18:39 — 실제 브라우저 E2E

- 새 frontend를 `http://localhost:3002`에서 backend `127.0.0.1:8000`과 연결했다.
- 온보딩 POST → `/profile` 표시 → 새로고침 GET → 소득 수정 PUT → DELETE →
  예시/재입력 상태 복귀를 실제 브라우저에서 확인했다.
- 첫 확인에서 `127.0.0.1:3002`를 사용했을 때 Next dev의 cross-origin dev resource
  보호로 hydration이 되지 않아 native form reload처럼 보였다. 동일 서버의 공식
  local URL인 `localhost:3002`로 재검증해 정상 동작을 확인했다. 제품 코드 오류나
  CORS 우회가 아니므로 `allowedDevOrigins` 완화는 추가하지 않았다.

### 18:48 — Draft PR CI·PM 독립 검수

- PR #29의 push·pull request 실행에서 backend `test` 2건과 frontend `web`
  2건이 모두 성공했다.
- PM이 `main...HEAD`의 21개 파일과 backend 비변경 범위를 확인했다.
- 입력 strict 검증, persona 제외, Decimal 변환, UUID path 검증, POST/GET/PUT/DELETE
  실패 처리, session 최소 저장과 legacy 제거 순서를 재검토했다.
- profile loading 중 상품·fraud 화면이 빈 profile을 확정하지 않고, 400/404에서는
  재입력을 안내하며 502/503은 저장 성공으로 바꾸지 않음을 확인했다.
- PR은 `MERGEABLE`, merge state `CLEAN`이며 차단 이슈는 발견하지 않았다.

## 변경 파일

- `web/lib/api/contracts.ts`: backend profile strict 계약과 frontend enum 정렬
- `web/lib/api/client.ts`: GET/PUT/DELETE를 위한 공용 서버 요청 확장
- `web/lib/api/profiles.ts`: profile 양방향 adapter와 브라우저 API
- `web/app/api/proxy/profiles/route.ts`: profile 생성 proxy
- `web/app/api/proxy/profiles/[profileId]/route.ts`: 단건 조회·교체·삭제 proxy
- `web/lib/store/profile-store.ts`: 전체 원문 대신 ID+persona session identity
- `web/components/finance/ProfileForm.tsx`: backend 필수 입력과 비동기 저장 UI
- `web/components/finance/ProfileFacts.tsx`: 새 입력 표시
- `web/app/onboarding/page.tsx`: backend 조회·오류 상태
- `web/app/profile/page.tsx`: backend 조회·삭제 상태
- `web/components/finance/ProductRecommendations.tsx`: profile loading/error 구분
- `web/app/check/page.tsx`: live profile persona 사용
- `web/lib/format/labels.ts`, `web/lib/mock/profile.ts`: enum·fixture 정렬
- `web/lib/api/products.ts`, `web/lib/api/products.test.ts`: business goal 정렬
- `web/lib/api/profiles.test.ts`: adapter·브라우저 API 테스트
- `web/lib/store/profile-store.test.ts`: session 최소 저장·legacy 제거 테스트
- `web/lib/api/home.ts`: 구현 상태 설명 교정
- `docs/13-frontend-architecture.md`: live profile 데이터 흐름과 한계 반영
- 본 개발일지

## 최종 검증 결과

- `npm test`: **4 files, 13 passed**
- `npm run lint`: 통과
- `npm run build`: 통과, profile proxy 포함 11 routes
- build 후 `npx tsc --noEmit`: 통과
- 전체 `pytest -q`: **139 passed**
- `git diff --check`: 통과
- `app/`, `tests/`, requirements 변경 없음
- 실제 브라우저 POST/GET/PUT/DELETE E2E: 통과
- 기존 FastAPI/Starlette `TestClient` 사용 중단 예정 경고 1건
- sandbox `.pytest_cache` 쓰기 권한 경고 1건, 제품·추적 파일 영향 없음

## 보안·개인정보 검토

- frontend profile schema는 strict이며 OTP 같은 미승인 필드를 거부한다.
- backend 요청에서 UI 전용 persona를 제외한다.
- profile 원문을 sessionStorage, localStorage, console log에 저장하지 않는다.
- browser에는 UUID와 persona만 남는다. 기존 session profile은 다음 정상 저장·삭제
  시 제거한다.
- profile ID는 proxy에서 UUID로 검증하며 arbitrary backend path를 만들지 못한다.
- UUID는 인증이 아니다. process-local backend와 인증 부재 한계를 화면·문서에
  유지했다.
- 금융 파생지표, 상품 적격성, 대출 계산을 frontend에 추가하지 않았다.

## 남은 위험과 다음 작업

- backend 재시작·다중 worker에서 profile이 사라지므로 PostgreSQL 전환이 필요하다.
- 인증·소유권 검증 전에는 다른 사람이 UUID를 알면 접근할 수 있어 public deployment
  대상이 아니다.
- 기존 session-only profile의 enum은 backend와 달라 자동 이관하지 않는다. 사용자가
  새 계약으로 다시 저장하면 legacy 원문을 제거한다.
- 파생지표 API가 없어 실제 profile에는 지표를 계산·표시하지 않는다.
- 후속 우선순위는 PostgreSQL·SQLAlchemy·Alembic 또는 상품 비교·What-if 중 PM이
  P0 배포 순서에 맞춰 선택한다.

## 커밋·PR 정보

- 기능 커밋: `6cba4c69366d9f9aca9b9d0bc8e08c71d5a589ab`
- 커밋 메시지: `feat: connect financial profile frontend`
- push 브랜치: `feature/profile-frontend-integration-v01`
- PR 방향: `feature/profile-frontend-integration-v01` → `main`
- Draft PR #29: `https://github.com/mosejong/finshield-ai/pull/29`
- PR 생성: `2026-08-12 18:46:16 KST`
- 생성 직후 상태: backend `test`, frontend `web` GitHub Actions 진행 중
- 검수한 PR head: `8c587780639460df6ef15463c40d3b90bb94c91d`
- 초기 GitHub Actions: backend `test` 2건, frontend `web` 2건 모두 성공
- PM 리뷰: 차단 이슈 없음, 최종 문서 커밋 CI 확인 후 Ready 전환 예정
- 최종 PR head: `7d9979b8b6d484a28df9870277f56f023307518c`
- 최종 GitHub Actions: backend `test` 2건, frontend `web` 2건 모두 성공
- Ready 전환 후 squash merge 완료
- 병합 시각: `2026-08-12 18:50:31 KST`
- 병합 커밋: `f9c121295481ca9d0c1db0c432ecf0dfefc96625`
