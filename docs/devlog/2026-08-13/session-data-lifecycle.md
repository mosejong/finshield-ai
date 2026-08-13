# 익명 세션·FinancialProfile 데이터 생명주기 개발일지

- 날짜: 2026-08-13 (Asia/Seoul)
- 역할: PM 통합 작업
- 브랜치: `feature/session-data-lifecycle`
- worktree: `C:\Users\user\Documents\Codex\finshield-ai-main`
- 기준 main: `8a27208a1d19f5ad817e6b56a716f0bb2b9bce67`
- 시작: 15:17
- 상태: PR #46 병합 완료

## 목표와 범위

로그아웃과 개인정보 삭제를 분리하고, 사용자가 익명 계정과 모든 금융정보를 직접 삭제할 수 있게 한다.
만료 세션 때문에 접근 불가능해진 profile은 운영 dry-run/execute 정리 명령으로 제거한다. 다른 금융 계산,
상품·사기 분석 계약과 migration schema는 변경하지 않는다.

## 시간순 작업 기록

- 15:17: `feature/session-data-lifecycle` 브랜치 생성. 계정 삭제·만료 정리·백업 한계 정책 확정.
- 15:19: auth/profile repository에 사용자 전체 삭제와 만료 집계·삭제 경계 구현.
- 15:20: `DELETE /api/v1/auth/account`와 dry-run 기본 정리 명령 추가.
- 15:21: profile 화면에 profile-only 삭제와 구분되는 익명 계정 전체 삭제 UI 추가.
- 15:23: 만료 사용자 cascade와 계정 삭제 API DB 회귀 테스트 추가.
- 15:24: backend 전체 181 passed 확인.
- 15:25: 프론트 삭제 API·로컬 identity 제거 회귀 테스트 추가.
- 15:26: frontend 32 passed, TypeScript, lint 통과.
- 15:27: 생명주기 운영 문서와 ADR, README·백로그·색인 갱신.
- 15:29: Next production build, Python compile, dry-run 실행, diff·비밀값 패턴 검사를 통과.

## 구현 흐름

1. 사용자가 profile 화면에서 전체 삭제를 확인한다.
2. Next same-origin proxy가 FinShield 세션 쿠키만 FastAPI에 전달한다.
3. FastAPI가 현재 세션 소유자를 인증한다.
4. 해당 사용자의 FinancialProfile 전체를 먼저 삭제한다.
5. 익명 사용자 row를 삭제하고 DB cascade로 관련 세션을 제거한다.
6. 응답 쿠키와 브라우저의 profile identity를 삭제한다.
7. 별도 운영 명령은 활성 세션이 없는 익명 사용자만 dry-run으로 집계하거나 명시적 실행으로 삭제한다.

## 검증 기록

- Python: 181 passed
- frontend: 32 passed
- TypeScript: 통과
- lint: 통과
- Next production build: 통과, account proxy 포함 22개 route 생성
- Python compile, `git diff --check`: 통과
- 계정 삭제: 204, 쿠키 만료, 기존 쿠키 401, users/auth_sessions/financial_profiles 0건 확인
- 만료 정리: dry-run 무변경, 활성 사용자 보존, 만료 사용자·세션·profile cascade 확인
- 로그 경계: 정리 출력은 건수와 실행 여부만 포함

## 개인정보·보안 영향

- 새 개인정보를 수집하지 않는다.
- 계정 삭제는 profile-only 삭제와 별도 확인 문구를 사용한다.
- 서버 삭제가 실패하면 브라우저 identity를 먼저 지우지 않는다.
- 백업·WAL의 과거 암호문은 별도 보존·파기 정책 대상이며 즉시 선택 삭제를 보장하지 않는다.

## 변경 범위

- backend: account route, auth/profile repository·service, main route 등록
- operations: `scripts/cleanup_expired_anonymous_data.py`
- frontend: account proxy/API, profile store와 profile 삭제 UI
- tests: 계정 삭제, cascade, dry-run, 프론트 proxy·identity 제거
- docs: 문서 24, ADR 0004, 이 개발일지와 README·백로그·색인

## 남은 위험과 다음 작업

- 운영 스케줄러 등록과 실행 실패 알림
- PostgreSQL live cascade·동시성·backup restore 검증
- 백업 보존기간과 실제 파기 절차
- 정식 계정 전환·다중 기기·복구 정책

## Git/PR

- 기능 commit SHA: `ca70e4d0f334e144e2091c6caec4f7596c4aa402`
- PR: #46 `https://github.com/mosejong/finshield-ai/pull/46`
- 병합 시각: 2026-08-13 15:34:18 KST
- main SHA: `d80af256e66fa84f8c2528d168e160ff40231c73`
- 실제 로컬 통합 결과: `session-data-lifecycle-integration.md`
