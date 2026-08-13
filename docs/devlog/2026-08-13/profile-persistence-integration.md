# FinancialProfile 암호화 영속화 통합

- 날짜: 2026-08-13
- 담당: PM
- 브랜치: `docs/profile-persistence-integration`
- worktree: `C:\Users\user\Documents\Codex\finshield-ai-main`
- 시작: 14:13 KST
- 종료: 14:14 KST
- 상태: 통합·로컬 적용 완료

## 목적

PR #40의 병합 결과를 `main` 기준 공용 문서에 반영해 README와 docs만 읽어도 현재
profile 저장·암호화 경계, 실행 방법, 검증 수치와 남은 공개 배포 차단 조건을 알 수
있게 한다.

## 기준

- 기능 PR: #40, https://github.com/mosejong/finshield-ai/pull/40
- 기능 head: `d04809f8cc9b8e4dac1b4d3f6ee27016ba6fd1d7`
- squash merge: `70d9215b73d269c797fe9ac903c86c09fe902d05`
- GitHub Actions: `test` 2회, `web` 2회 통과
- 로컬: Python 170 passed, frontend 24 passed, TypeScript·lint·Next build 통과

## 반영 내용

- README의 process-local 전용 설명을 SQLAlchemy DB + encrypted fallback 경계로 교정
- 실행 절차에 migration·DB URL·암호화 키 요구사항 연결
- 테스트 수치를 Python 170 passed로 갱신
- backlog에서 암호화 영속화를 완료 처리하고 인증·소유권을 후속 경계로 유지
- docs 및 날짜별 개발일지 색인에 설계 문서·기능일지·통합일지 연결

## 보안·개인정보 경계

- 암호화를 공개 배포 완료로 과장하지 않는다.
- UUID는 인증이 아니며 사용자별 소유권, PostgreSQL live·복구, secret manager,
  보존·삭제 정책이 남아 있음을 README에 유지한다.
- 실제 DB URL·비밀번호·Fernet 키는 문서에 기록하지 않는다.

## 검증·Git

- `git diff --check`: 통과
- 오래된 158 passed·process-local 전용·PostgreSQL 미구현 문구 검색: 0건
- 통합 커밋: `1befba66ee402b53c93a31d47c78ec4d345480ad`
- 통합 PR: #41, https://github.com/mosejong/finshield-ai/pull/41
- 통합 merge: `b849944e3d62c758ab57ad7faeea37ee2607f9a1`
- PR #41 GitHub Actions: `test` 2회, `web` 2회 통과

## 데스크톱 로컬 적용

- 14:17: 역할 브랜치를 최종 main `b849944`로 fast-forward. 기존 `.agents/`,
  `AGENTS.md`는 수정·스테이징하지 않음.
- 기존 `.env`의 `PUBLIC_DATA_SERVICE_KEY`를 보존하고 값 출력 없이 로컬 SQLite URL과
  신규 Fernet 키를 추가. `.env`와 DB는 Git ignore 상태를 유지.
- Alembic `20260813_01 (head)` 적용 후 암호화 DB 설정으로 backend 8000 재시작.
- backend 8000과 frontend 3001 HTTP 200 확인.
- 실제 profile API 생성·조회 일치, SQLite binary에서 테스트 금액·목표 평문 미검출,
  임시 profile API 삭제 204와 최종 row 0건 확인.
- Docker가 설치되어 있지 않아 PostgreSQL live 검증은 수행하지 않았으며 공개 배포
  차단 조건으로 유지한다.
