# FinancialProfile DB 영속화·암호화

- 날짜: 2026-08-13
- 담당: Backend / PM
- 브랜치: `feature/profile-database-encryption`
- worktree: `C:\Users\user\Documents\Codex\finshield-ai-main`
- 시작: 13:45 KST
- 종료: 14:07 KST
- 상태: 구현·로컬 검증 완료, PR 준비

## 목표

- process-local profile 저장을 SQLAlchemy repository로 교체할 수 있게 한다.
- PostgreSQL migration을 제공한다.
- 소득·자산·부채를 포함한 profile 전체를 인증 암호화해 DB 평문 저장을 막는다.
- 기존 profile CRUD·metrics·프론트 API 계약을 유지한다.
- 운영 환경의 DB·키 누락을 fail-closed로 처리한다.

## 비범위

- 로그인과 사용자별 소유권 검증
- 기존 메모리 profile 데이터 이전
- DB 필드 검색과 분석용 복호화 파이프라인
- secret manager·KMS 구축과 배포 인프라

## 관련 문서

- `docs/09-financial-profile-schema.md`
- `docs/11-engineering-standards.md`
- `docs/12-security-threat-model.md`
- `docs/14-development-workflow.md`
- `docs/adr/0002-encrypted-profile-persistence.md`

## 설계·구현 흐름

- 13:45: `main` 청결 상태와 저장소 지침, profile CRUD·metrics 회귀 계약 확인.
- 13:48: PostgreSQL·SQLAlchemy·Alembic과 profile 전체 인증 암호화를 선택. API 계약과
  프론트 소유 영역 `web/`은 변경하지 않기로 확정.
- 13:52: 암호문, key ID, UTC 생성·수정 시각만 갖는 초기 migration 작성.
- 13:55: Fernet keyring, SQLAlchemy repository, SQLite migration round-trip, 키 순환,
  변조·누락 키·설정 실패 테스트 구현.
- 13:59: PM 자체 보안 리뷰에서 유효한 암호문을 다른 UUID row로 교체하는 공격 경계를
  발견. 암호화 envelope에 version과 profile UUID를 포함하고 DB row UUID와 일치하지
  않으면 복호화 실패로 처리하도록 수정.
- 14:02: development·test 외 모든 배포 환경에서 PostgreSQL+psycopg와 키를 요구하고,
  앱 lifespan에서 DB 연결·migration 적용 여부를 검증하도록 강화.
- 14:04: 임시 SQLite DB에 실제 Alembic migration을 적용하고 uvicorn을 두 번 실행.
  첫 실행에서 생성한 profile의 ID·목표·소득이 재시작 후 모두 동일함을 확인했고,
  DB binary에서 테스트 금액·목표 평문이 없음을 확인. 임시 DB·키·로그 제거.

## 보안·개인정보 판단

- DB에 금융 금액·지역·부채 상세를 평문 column으로 저장하지 않는다.
- 환경변수의 실제 키를 출력하거나 개발일지·테스트 fixture에 고정하지 않는다.
- 복호화 실패와 DB 오류는 profile 원문·암호문 없이 일반화된 503으로 반환한다.
- UUID는 인증 수단이 아니므로 공개 배포 전 인증·소유권 경계가 여전히 필수다.

## 검증 계획

- 암호문에 profile 금액·목표 문자열이 없는지 검사
- CRUD, 삭제, metrics와 재시작 후 영속성
- 잘못된 키·변조 암호문·누락 키 fail-closed
- 이전 키 복호화와 활성 키 신규 쓰기
- Alembic upgrade/downgrade/upgrade
- 전체 Python 및 frontend 회귀검사

## 변경 파일

- 설정·의존성: `.env.example`, `requirements.txt`, `alembic.ini`
- DB·migration: `app/db/`, `migrations/`
- 암호화: `app/security/profile_encryption.py`
- 저장·서비스·시작 검증: `app/core/profile_storage.py`,
  `app/repositories/financial_profiles.py`, `app/services/financial_profiles.py`,
  `app/api/routes/profiles.py`, `app/main.py`
- 테스트: `tests/test_profile_persistence.py`
- 문서: `docs/22-profile-persistence-encryption.md`,
  `docs/adr/0002-encrypted-profile-persistence.md`, 이 개발일지

## 검증 결과

- profile 집중 회귀: 34 passed, 기존 Starlette 예정 경고 1건
- 최종 전체 Python 회귀: 170 passed, 기존 경고 1건
- Python compile: 통과
- frontend: 8 files / 24 tests, TypeScript, lint, Next production build 통과
- Alembic: SQLite upgrade → downgrade → upgrade 통과
- 실제 서버 재시작 영속성: profile ID·목표·소득 일치
- DB 평문 검사: 테스트 금액 `3500000`, 목표 `asset_building` 미검출
- Docker/PostgreSQL live 검증: 이 PC에 Docker가 없어 미실행. 운영 배포 전 필수

## 리뷰·수정 이력

- PM 리뷰 1: 암호문 인증만으로 row swap을 막지 못함 → envelope UUID binding 추가.
- PM 리뷰 2: production 문자열만 검사하면 staging이 메모리 저장으로 실행될 수 있음 →
  development·test allowlist 외 모든 환경을 배포 환경으로 간주.
- PM 리뷰 3: 설정만 맞고 migration이 없으면 첫 요청까지 실패가 늦어짐 → 앱 시작 시
  연결·table 검증 추가.
- 첫 통합 스모크의 합성 비교가 PowerShell Decimal 형변환 때문에 false로 기록됨 →
  ID·목표·소득 조건을 분리하고 Decimal 명시 변환 후 모두 true 확인. 최초 결과를
  통과로 기록하지 않음.

## 알려진 위험과 다음 작업

- 사용자 인증·profile 소유권이 없어 UUID를 아는 사용자의 접근을 막지 못한다.
- PostgreSQL live·backup restore·다중 worker·부하 테스트가 필요하다.
- 이전 키로 저장된 모든 row를 능동 재암호화하는 운영 명령은 후속 작업이다.
- DELETE 이후 WAL·backup 보존 정책과 개인정보 처리방침이 필요하다.

## Git

- 커밋 SHA: 커밋 후 기록
- PR: 생성 후 기록
