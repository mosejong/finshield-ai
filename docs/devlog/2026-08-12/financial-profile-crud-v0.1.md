# FinancialProfile CRUD v0.1 개발일지

## 작업 정보

- 작업일: 2026-08-12 (KST)
- 시작: 18:06 KST
- 담당 영역: 백엔드
- 작업 브랜치: `feature/financial-profile-crud-v01`
- 작업 디렉터리: `C:\Users\user\Documents\Codex\finshield-ai-backend`
- 로컬 구현·검증 완료: 18:11 KST
- Draft PR 생성: 18:13 KST
- 상태: Draft PR #26, GitHub Actions CI 진행 중

## 목표

프론트엔드가 `sessionStorage`에만 보관하는 금융 프로필을 백엔드 API로
생성·조회·전체 교체·삭제할 수 있는 최소 CRUD v0.1을 구현한다. 기존
`FinancialProfile`의 최소정보·민감정보 거부 정책을 그대로 사용한다.

## 변경 이유

공식 상품 추천과 대출 What-if를 하나의 사용자 흐름으로 연결하려면 검증된
프로필을 프론트 화면 사이에서 재사용할 백엔드 경계가 필요하다. 현재는 인증과
영구 데이터베이스가 없으므로, 이번 단계는 로컬 프로토타입용 process-local
저장소로 범위를 제한하고 그 한계를 API·문서·테스트에 명시한다.

## 범위

- `POST /api/v1/profiles`: 프로필 생성
- `GET /api/v1/profiles/{profile_id}`: 단건 조회
- `PUT /api/v1/profiles/{profile_id}`: 전체 프로필 교체
- `DELETE /api/v1/profiles/{profile_id}`: 삭제
- UUID 식별자와 UTC 생성·수정 시각 반환
- thread-safe process-local 저장소와 테스트 격리용 의존성 주입
- 입력 필드 제한, 민감정보 거부, 존재하지 않는 식별자 404 처리

## 비범위

- `web/` 프론트엔드 변경
- PostgreSQL·SQLAlchemy·Alembic 영구 저장
- 사용자 인증·계정 연결·프로필 목록 조회
- 부분 수정(PATCH), 변경 이력, 다중 기기 동기화
- 루트 `README.md`, `docs/README.md`, 백로그 수정

## 관련 문서

- `CLAUDE.md`
- `SKILL.md`
- `docs/03-product-scope.md`
- `docs/04-architecture.md`
- `docs/09-financial-profile-schema.md`
- `docs/11-engineering-standards.md`
- `docs/14-development-workflow.md`

## 예정 변경 파일

- `app/main.py`
- `app/api/routes/profiles.py`
- `app/repositories/financial_profiles.py`
- `app/schemas/financial_profile.py`
- `app/services/financial_profiles.py`
- `tests/test_profiles_api.py`
- 본 개발일지

## 검증 계획

- CRUD 정상 흐름과 삭제 후 404
- 잘못된 UUID, 존재하지 않는 UUID, 민감·미승인 필드 거부
- PUT 전체 교체 후 생성 시각 유지·수정 시각 갱신
- 저장·조회 객체의 방어적 복사와 동시 접근 안전성
- OpenAPI 계약 확인
- 전체 `pytest -q`, Python compile, `git diff --check`
- 로그·응답에 원문 프로필이나 비밀정보가 불필요하게 노출되지 않는지 검토

## 알려진 초기 위험

- process-local 저장이므로 서버 재시작·다중 worker에서 데이터가 유지·공유되지 않는다.
- 인증이 없으므로 공개 배포에서 사용하면 안 된다. 불투명 UUID는 접근 통제가 아니다.
- 영구 저장과 인증 설계 전까지 프론트 연결은 로컬 프로토타입 용도로 제한한다.

## 구현 기록

### 18:06 — 브랜치·범위 확정

- 최신 `main` 커밋 `00a71d5`에서 백엔드 전용 브랜치를 생성했다.
- 기존 worktree의 추적 파일이 깨끗한 상태임을 확인했다.
- `web/`과 PM 관리 문서를 비범위로 고정했다.

### 18:07 — API·저장 경계 구현

- 기존 `FinancialProfile`을 요청 계약으로 재사용해 정의되지 않은 필드와
  민감정보를 동일하게 거부한다.
- 서버 관리 필드 `profile_id`, `created_at`, `updated_at`과 검증된 profile을
  묶는 `FinancialProfileResource`를 추가했다.
- 프로필 저장소는 `RLock`으로 생성·조회·교체·삭제와 최대 보관 수 검사를
  원자적으로 처리한다.
- 저장과 반환 양쪽에 deep copy를 사용해 호출자가 반환 객체를 수정해도 저장
  상태가 바뀌지 않도록 했다.
- 저장소 clock은 timezone-aware 시각만 허용하고 UTC로 정규화한다. 전체 교체 시
  `created_at`은 유지하고 `updated_at`은 이전 값보다 반드시 증가한다.
- 프로세스 메모리 과다 사용을 제한하기 위해 기본 최대 1,000개를 허용하고,
  초과 시 빈 결과가 아니라 명시적인 HTTP 503을 반환한다.

### 18:08 — CRUD route와 오류 계약 연결

- `POST`, 단건 `GET`, 전체 교체 `PUT`, `DELETE`를 `/api/v1/profiles` 아래에
  연결했다.
- 존재하지 않는 UUID는 동일한 404 응답을 반환하고, 잘못된 UUID 형식과 잘못된
  profile은 FastAPI/Pydantic의 422 계약을 사용한다.
- 인증이 없는 상태에서 전체 프로필 노출을 만들지 않기 위해 목록 endpoint는
  의도적으로 제공하지 않는다.
- 테스트가 전역 process-local 상태에 의존하지 않도록 service dependency override
  경계를 제공했다.

### 18:09 — 기능·보안·동시성 테스트

- 생성 → 조회 → 전체 교체 → 삭제 → 삭제 후 404 흐름을 검증했다.
- 알 수 없는 UUID, 잘못된 UUID, 민감·미승인 필드, 저장 한도 초과를 검증했다.
- 반환 객체의 방어적 복사, naive datetime 거부, UTC 정규화를 검증했다.
- 20개 동시 생성 요청에서 최대 10개 저장 한도가 정확히 유지됨을 검증했다.
- OpenAPI에 POST와 단건 GET/PUT/DELETE만 노출되는지 검증했다.

## 데이터 흐름

1. FastAPI가 UUID와 `FinancialProfile` 요청을 검증한다.
2. route는 profile service에 작업을 위임한다.
3. service가 process-local repository의 원자적 CRUD를 호출한다.
4. repository는 검증된 profile을 deep copy해 UUID·UTC 시각과 함께 저장한다.
5. API는 `FinancialProfileResource`로 응답하며 원문 profile을 로그에 남기지 않는다.

## 실제 변경 파일

- 수정: `app/main.py`
- 수정: `app/schemas/financial_profile.py`
- 신규: `app/api/routes/profiles.py`
- 신규: `app/repositories/__init__.py`
- 신규: `app/repositories/financial_profiles.py`
- 신규: `app/services/financial_profiles.py`
- 신규: `tests/test_profiles_api.py`
- 신규: `docs/devlog/2026-08-12/financial-profile-crud-v0.1.md`

## 검증 결과

- 프로필 스키마·API 집중 테스트: **29 passed**
- 전체 `pytest -q`: **139 passed**
- Python `compileall app tests`: 통과
- `git diff --check`: 통과
- 기존 FastAPI/Starlette `TestClient` 사용 중단 예정 경고 1건
- sandbox worktree의 `.pytest_cache` 쓰기 권한 경고 1건. 테스트 결과나 제품
  동작에는 영향이 없으며 저장소 추적 파일도 만들지 않았다.

## 보안·개인정보 검토

- 주민번호, 계좌 비밀번호, OTP, 전체 카드번호 등 미승인 입력은 기존
  `extra="forbid"` 계약으로 저장 전에 거부된다.
- 프로필 원문을 application log에 기록하는 코드를 추가하지 않았다.
- 목록 endpoint를 제공하지 않아 전체 보유 profile을 열거하는 API를 만들지 않았다.
- UUID는 인증수단이 아니다. 인증·권한 없이 인터넷에 공개하면 안 된다.
- 외부 API, LLM, URL fetch, 파일 저장, 브라우저 저장소 접근을 추가하지 않았다.

## 남은 위험과 다음 작업

- 서버 재시작과 다중 worker 사이에서 profile이 유지되지 않는다.
- 인증·소유권 검증이 없어 공개 배포 조건을 충족하지 않는다.
- 다음 백엔드 단계는 PostgreSQL·SQLAlchemy·Alembic repository 구현과 인증 경계
  설계다. 로컬 프로토타입에서는 먼저 프론트의 session profile을 이 API에 연결할
  수 있다.
- 영구 저장 전 데이터 보존기간, 삭제 정책, 암호화, audit log의 PII masking을
  별도 ADR로 확정해야 한다.

## 커밋·PR 정보

- 기능 커밋: `97084a09eac6e7075e8805d3e22b89efb9c46a4e`
- 커밋 메시지: `feat: add financial profile CRUD v0.1`
- push 브랜치: `feature/financial-profile-crud-v01`
- PR 방향: `feature/financial-profile-crud-v01` → `main`
- Draft PR #26: `https://github.com/mosejong/finshield-ai/pull/26`
- PR 생성: `2026-08-12 18:13:04 KST`
- 생성 직후 상태: backend `test`, frontend `web` GitHub Actions 실행 중
