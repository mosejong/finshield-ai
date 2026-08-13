# Docker·PostgreSQL 운영 스택 개발일지

- 날짜: 2026-08-13 (Asia/Seoul)
- 역할: PM 통합 작업
- 브랜치: `feature/docker-postgres-runtime`
- worktree: `C:\Users\user\Documents\Codex\finshield-ai-main`
- 기준 main: `da4877b8b4ff3b617e5786edaea6ef332b118b5d`
- 시작: 15:41
- 상태: 구현·로컬 live 검증 완료, PR 준비

## 목표

PostgreSQL, Alembic migration, FastAPI 다중 worker, Next standalone server를 한 Compose 스택으로 재현한다.
실제 profile 생성·재시작 후 조회, 암호화 DB backup/restore, 계정 삭제를 자동 검증하고 CI에서도 같은 경로를
실행한다.

## 비범위

- 공개 도메인과 실제 TLS 인증서
- 클라우드 secret manager/KMS
- 외부 staging 계정 생성과 과금 발생 배포

위 항목은 다음 보안·배포 단계에서 별도 결정한다.

## 시간순 작업 기록

- 15:41: main 최신화 후 `feature/docker-postgres-runtime` 브랜치 생성.
- 15:42: 로컬에 Docker CLI/Desktop이 설치되지 않은 사실 확인. WSL2 상태와 설치 경로 검토 시작.
- 15:43: Docker Compose `service_healthy`/`service_completed_successfully`, FastAPI 컨테이너화와 Next standalone
  공식 문서를 기준으로 시작 순서·이미지 구조 결정.
- 15:45: 로컬 HTTP 스택과 공개 HTTPS 배포의 cookie policy를 분리하기로 결정. Compose 기본은
  `APP_ENV=development`, 공개 배포는 TLS 뒤에서 `production`을 명시해야 한다.
- 15:46: DB 비밀번호·profile 암호화 키를 Git·image·일반 환경값이 아닌 Compose file secret으로 주입하는
  설정 경계 구현 시작.
- 15:48: backend/web non-root Dockerfile, Compose health/migration dependency, secret 생성기와 PostgreSQL
  restart·backup/restore 자동 검증기 구현.
- 15:49: secret-file 설정 회귀를 포함한 backend 190 passed, frontend 32 passed, Next standalone production
  build, TypeScript, lint, Python compile 통과.
- 15:50: 로컬 secret 생성 성공 및 기존 파일 덮어쓰기 거부 확인. 실제 값은 출력·Git 추적하지 않음.
- 15:51: WSL2 2.6.3 준비 상태와 Docker Desktop 4.86.0 패키지를 확인하고 설치 시작. installer가 계속
  실행 중이므로 완료 여부를 별도 확인하며 CI container 검증을 병행.
- 15:53: Docker Desktop 4.86.0 설치 완료, 공식 CLI로 Linux engine 시작. Docker Engine 29.7.2,
  Compose v5.3.1 확인.
- 15:54: 첫 image build는 현재 PowerShell PATH가 설치 전 상태라 credential helper를 찾지 못해 실패.
  명령 범위에 Docker bin을 추가해 재시도.
- 15:57: Python 3.12.10 backend와 Node 22 Next standalone image build 통과. 빌드 과정 npm audit은
  알려진 취약점 0건을 보고.
- 15:58: 실제 PostgreSQL 16 healthy → Alembic head 성공 → FastAPI healthy → Next healthy 시작 순서 통과.
- 15:59: 합성 profile 생성·metrics → backend restart → 재조회 → custom pg_dump → 임시 DB restore →
  알려진 금융값 평문 부재 → 계정 삭제 → 원본 3개 table 0건 자동 E2E 통과.
- 16:00: backend worker 2개와 backend/web UID 10001 non-root 실행 확인. base image digest를 고정.
- 16:02: 최종 리뷰에서 검증 DB가 비어 있다는 전제가 강제되지 않는 문제 발견. 기존 row, 동일 backup,
  동일 복원 DB가 있으면 변경 없이 중단하도록 fail-closed 보호 추가. 합성 기존 사용자 1건 보존 확인 후 정리.
- 16:05: 공공데이터 일반 인증키도 선택 override file secret으로 분리. 읽기 실패는 기존 503 유지.
- 16:09: backend 전체 192 passed, frontend 32 passed, Next build·TypeScript·lint·Python compile,
  digest 고정 image rebuild 통과.
- 16:11: 검증기를 Next 프록시 전체 경로로 전환하면서 browser/backend camelCase·snake_case 계약 불일치로
  400 발견. browser 계약으로 수정하고 중간 실패 계정 best-effort 정리 추가.
- 16:13: Next proxy → FastAPI 2 workers → PostgreSQL → backup/restore → 계정 삭제 최종 E2E 통과.
  종료 후 원본 3개 table `0|0|0`, 복원 DB 0, backup artifact는 `.gitkeep`만 존재.

## 검증 결과

- Python 192 passed, frontend 32 passed, Next build·TypeScript·lint·Python compile 통과
- Compose config·backend/web image build 통과
- PostgreSQL health → migration exit 0 → backend health → web health 순서 통과
- FastAPI Python 3.12.10, worker 2개, backend/web UID 10001 확인
- profile 생성 → backend restart → 같은 세션 조회 통과
- custom-format pg_dump → 임시 DB restore → 암호화 profile row 1건, `2800000` 평문 부재
- 계정 삭제 후 users/session/profile `0|0|0`, 기존 세션 401
- Next same-origin proxy 전체 경로 통과, 실패 중간 데이터 best-effort cleanup 확인
- backend image 350MB, standalone web image 303MB
- GitHub Actions container runtime job: PR 생성 후 결과 기록

## 보안·개인정보 경계

- secret 원문을 커밋·image layer·로그에 남기지 않는다.
- 실제 금융정보 대신 고정 합성 profile만 통합검증에 사용한다.
- DB는 host port를 공개하지 않는다.
- backend/web은 non-root, capability drop, no-new-privileges로 실행한다.
- backup은 암호문을 포함하며 `backups/` 실제 파일은 Git에서 제외한다.

## Git/PR

- commit/PR/병합: 검증 후 기록
