# FinShield Development Log

개발일지는 날짜별 디렉터리와 브랜치별 파일로 관리한다.

## 2026-08-12

- `project-governance.md` — 역할별 브랜치, worktree, PR 및 문서화 규칙 수립
- `frontend-mvp.md` — 프론트엔드 MVP 구현, PM 검수, Scenario Engine 통합
- `frontend-integration.md` — 프론트 PR #4 병합 후 PM 관리 문서 반영
- `fraud-scenario-engine-v0.1.md` — Fraud Scenario Engine v0.1 구현, PM 검수, PR #2 병합
- `scenario-engine-integration.md` — Scenario Engine 병합 후 PM 관리 문서 반영
- `product-catalog-v0.1.md` — 공식 금융상품 adapter와 정규화 계약 구현, PR #7 병합
- `product-catalog-integration.md` — 상품 adapter 병합 후 PM 관리 문서 반영
- `public-data-key-normalization.md` — 일반 인증키 호환 수정과 live 상품 API 검증
- `public-data-key-integration.md` — 인증키 수정 병합 후 PM 관리 문서 반영
- `product-catalog-v0.2-profile.md` — 최신월 상품 live 품질 측정과 PR #13 병합
- `product-profile-integration.md` — 상품 profile 병합 후 PM 관리 문서 반영
- `product-catalog-cache-v0.3.md` — 최신월 snapshot TTL cache와 PR #16 병합
- `product-cache-integration.md` — cache 병합 후 PM 관리 문서 반영
- `product-catalog-identity-v0.4.md` — source identity 무결성과 PR #19 병합
- `product-identity-integration.md` — identity 병합 후 PM 관리 문서 반영
- `product-filtering-v0.1.md` — deterministic filtering과 PR #21 병합
- `product-filtering-integration.md` — filtering 병합 후 PM 관리 문서 반영
- `product-recommendations-ui-v0.1.md` — 공식 상품 후보 UI와 PR #24 병합
- `product-ui-integration.md` — 상품 UI 병합 후 PM 관리 문서 반영
- `financial-profile-crud-v0.1.md` — process-local FinancialProfile CRUD와 PR #26 병합
- `financial-profile-crud-integration.md` — 프로필 CRUD 병합 후 PM 관리 문서 반영
- `profile-frontend-integration-v0.1.md` — backend profile CRUD 프론트 연결과 PR #29 병합
- `profile-frontend-integration.md` — 프로필 프론트 병합 후 PM 관리 문서 반영
- `loan-what-if-ui-v0.1.md` — 대출 조건 비교 UI 구현·실브라우저 검수·병합
- `loan-what-if-integration.md` — 대출 조건 비교 병합 후 PM 관리 문서 반영
- `wealth-guidance-v0.1.md` — 공식 근거 기반 재테크 기초 가이드 구현·검수·병합
- `wealth-guidance-integration.md` — 재테크 가이드 병합 후 PM 관리 문서 반영
- `product-detail-compare-v0.1.md` — 공식 상품 상세·2개 비교 구현·실데이터 검수·PR #36 병합
- `product-detail-compare-integration.md` — 상품 상세·비교 병합 후 PM 관리 문서 반영

## 2026-08-13

- `frontend-accessibility-e2e.md` — 프론트 접근성 v0.1, PM 교정과 3개 viewport 검수
- `fraud-evaluation-integration.md` — PR #54 Linux CI·PM 승인·main 통합 기록
- `fraud-evaluation-benchmark-v0.1.md` — 합성 61건 benchmark, 실패·교정·재검수와 대회 증거 경계
- `profile-metrics-integration.md` — profile metrics PR #38 병합 후 README·백로그·색인 반영
- `profile-database-encryption.md` — encrypted SQLAlchemy profile persistence 구현·검수·PR #40 병합
- `profile-persistence-integration.md` — PR #40 병합 후 README·백로그·색인 반영
- `session-profile-ownership.md` — 익명 세션 인증·profile 소유권 구현과 PM 검수
- `session-profile-ownership-integration.md` — PR #43 병합·로컬 migration·browser E2E 통합 기록
- `session-data-lifecycle.md` — 익명 계정 전체 삭제와 만료 세션/profile 정리 구현·검수
- `session-data-lifecycle-integration.md` — PR #46 병합·데스크톱 최신화·live 삭제 E2E
- `docker-postgres-runtime.md` — Compose, PostgreSQL, 다중 worker와 backup/restore 검증
- `docker-postgres-integration.md` — PR #48 Linux CI 수정·병합·데스크톱 최신화
- `security-https-boundary.md` — 보안 헤더·CSRF·Host·HTTPS 경계 구현 및 검증
- `security-https-integration.md` — PR #50 Linux CI·PM 검수·main 통합 기록
- `observability-pii-masking.md` — 요청 추적·latency·readiness·PII 비노출 구현
- `observability-integration.md` — PR #52 Linux CI·PII 비노출·main 통합 기록
- `frontend-accessibility-e2e.md` — 접근성 패스와 구조적 a11y 회귀 검사

## 2026-08-14

- `code-verification-and-fixes.md` — mutation·독립 재계산 검증과 위험 판정·링크·출처 수정
- `dependency-hash-locking.md` — 해시 고정 universal lock·런타임/개발 분리·CI drift 차단

## 2026-08-15

- `rate-limiting-request-limits.md` — IP 기준 요청 한도·본문 크기 상한·홉 신뢰 경계·429 문구
- `expired-data-retention-schedule.md` — 만료 데이터 정리 주기 실행·heartbeat healthcheck·거짓 성공 차단

## 2026-08-17

- `backup-and-restore-rehearsal.md` — 백업 주기 실행·세대 회전·복호화까지 확인하는 복원 리허설
- `pwa-share-target.md` — PWA manifest·POST 공유 시트 인계·오프라인 셸·설치 유도
- `public-deployment-tls.md` — ACME 연락처 필수화·staging 예행연습 경로·외부 공개 배포 검증기

## 2026-08-18

- `llm-explanation-contract.md` — 고정 model·prompt·provider 계약, PII 최소화, 출력 검증, 판정 경계 (프로바이더 미연결)

## 작성 규칙

상세한 필수 항목과 PR 흐름은 `docs/14-development-workflow.md`를 따른다.
파일이 아직 생성되지 않은 예정 항목은 완료로 표시하지 않는다.
