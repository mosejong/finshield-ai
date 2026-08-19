# FinShield Documentation Index

## Product / research
01 problem definition · 02 research plan · 03 product scope · 05 data/evaluation · 06 roadmap · 07 official API candidates · 09 financial profile · 10 MVP backlog · 32 fraud evaluation benchmark · 33 competition evidence pack

## Architecture / engineering

Fraud evaluation bootstrap policy · `adr/0007-bootstrap-fraud-evaluation.md`
27 observability/PII masking · `adr/0006-privacy-safe-observability.md`
26 HTTP security/HTTPS boundary · `adr/0005-http-security-and-https-boundary.md`
04 architecture · 11 engineering standards · 13 frontend architecture · 14 development workflow · 15 product catalog live profile · 16 product catalog cache · 17 product catalog identity · 18 deterministic product filtering · 19 wealth guidance · 20 product detail/comparison · 21 profile derived metrics · 22 profile persistence/encryption · 23 session/profile ownership · 24 anonymous data lifecycle · 25 Docker/PostgreSQL runtime · 28 production readiness · 29 backup and recovery · 30 PWA and share target · 31 public deployment (domain/DNS/TLS) · 34 LLM explanation runtime · ADR 색인 `adr/README.md`

## Security

Privacy-safe logs and runtime PII regression: `27-observability-pii-masking.md`
HTTP response headers, same-origin state changes, trusted hosts and public TLS: `26-http-security-https.md`
08 AI security alignment · 12 security threat model

## Agent instructions
Root `CLAUDE.md` · root `SKILL.md` · `.claude/skills/finshield/SKILL.md`

동일한 규칙을 Claude 외 agent 도구에도 적용하려고 `AGENTS.md` 와 `.agents/skills/finshield/SKILL.md` 를 미러로 둔다. 넷 다 같은 Language rule·non-negotiables 를 담아야 하며, 한쪽만 고치면 도구별로 규칙이 갈라진다. `web/AGENTS.md` 는 `next dev` 가 자동 생성하는 별개 파일이니 손대지 않는다.

## Development history

- `devlog/2026-08-17/public-deployment-tls.md` — ACME 연락처 필수화·staging 예행연습 경로·외부 공개 배포 검증기
- `devlog/2026-08-17/pwa-share-target.md` — PWA manifest·POST 공유 시트 인계·오프라인 셸·설치 유도
- `devlog/2026-08-17/backup-and-restore-rehearsal.md` — 백업 주기 실행·세대 회전·복호화까지 확인하는 복원 리허설
- `devlog/2026-08-15/expired-data-retention-schedule.md` — 만료 데이터 정리 주기 실행·heartbeat healthcheck·거짓 성공 차단
- `devlog/2026-08-15/rate-limiting-request-limits.md` — IP 기준 요청 한도·본문 크기 상한·홉 신뢰 경계·429 문구
- `devlog/2026-08-14/dependency-hash-locking.md` — 해시 고정 universal lock·런타임/개발 분리·CI drift 차단
- `devlog/2026-08-14/code-verification-and-fixes.md` — mutation·독립 재계산 검증과 위험 판정·링크·출처 수정
- `devlog/2026-08-13/frontend-accessibility-e2e.md` — Claude 구현·PM 교정·실브라우저 반응형 검수
- `devlog/2026-08-13/fraud-evaluation-integration.md` — PR #54 Linux CI·PM 승인·main 통합 기록
- `devlog/2026-08-13/fraud-evaluation-benchmark-v0.1.md` — 합성 golden set·품질 gate·대회 증거 묶음
- `devlog/2026-08-13/observability-pii-masking.md` — 요청 추적·latency·readiness·PII 비노출 구현
- `devlog/2026-08-13/observability-integration.md` — PR #52 Linux CI·PII 비노출·main 통합 기록
- `devlog/2026-08-13/security-https-boundary.md` — 보안 헤더·CSRF·Host·HTTPS 경계 구현 및 검증
- `devlog/2026-08-13/security-https-integration.md` — PR #50 Linux CI·PM 검수·main 통합 기록

Date- and branch-based logs: `devlog/README.md`

- `devlog/2026-08-12/project-governance.md` — 역할별 브랜치·worktree·PR 규칙
- `devlog/2026-08-12/fraud-scenario-engine-v0.1.md` — Scenario Engine 구현·PM 검수·PR 병합
- `devlog/2026-08-12/scenario-engine-integration.md` — 병합 후 README·색인·백로그 반영
- `devlog/2026-08-12/frontend-mvp.md` — 프론트 MVP 구현·PM 검수·Scenario Engine 통합
- `devlog/2026-08-12/frontend-integration.md` — 프론트 병합 후 README·백로그 반영
- `devlog/2026-08-12/product-catalog-v0.1.md` — 공식 금융상품 adapter 구현·PM 검수·PR 병합
- `devlog/2026-08-12/product-catalog-integration.md` — 상품 adapter 병합 후 README·백로그 반영
- `devlog/2026-08-12/public-data-key-normalization.md` — 일반 인증키 Encoding/Decoding 호환 수정·live 검증
- `devlog/2026-08-12/public-data-key-integration.md` — 인증키 수정 병합 후 README·백로그 반영
- `devlog/2026-08-12/product-catalog-v0.2-profile.md` — 최신월 상품 live 품질 측정·PM 검수·PR 병합
- `devlog/2026-08-12/product-profile-integration.md` — 상품 profile 병합 후 README·색인·백로그 반영
- `devlog/2026-08-12/product-catalog-cache-v0.3.md` — 최신월 snapshot TTL cache 구현·검수·병합
- `devlog/2026-08-12/product-cache-integration.md` — cache 병합 후 README·색인·백로그 반영
- `devlog/2026-08-12/product-catalog-identity-v0.4.md` — source identity 무결성 구현·검수·병합
- `devlog/2026-08-12/product-identity-integration.md` — identity 병합 후 PM 문서 반영
- `devlog/2026-08-12/product-filtering-v0.1.md` — 보수적 filtering API 구현·검수·병합
- `devlog/2026-08-12/product-filtering-integration.md` — filtering 병합 후 PM 문서 반영
- `devlog/2026-08-12/product-recommendations-ui-v0.1.md` — 공식 상품 후보 화면 구현·검수·병합
- `devlog/2026-08-12/product-ui-integration.md` — 상품 화면 병합 후 PM 문서 반영
- `devlog/2026-08-12/financial-profile-crud-v0.1.md` — FinancialProfile CRUD 구현·검수·병합
- `devlog/2026-08-12/financial-profile-crud-integration.md` — 프로필 CRUD 병합 후 PM 문서 반영
- `devlog/2026-08-12/profile-frontend-integration-v0.1.md` — 프로필 프론트 연결·검수·병합
- `devlog/2026-08-12/profile-frontend-integration.md` — 프로필 프론트 병합 후 PM 문서 반영
- `devlog/2026-08-12/loan-what-if-ui-v0.1.md` — 대출 조건 비교 화면 구현·실브라우저 검수·병합
- `devlog/2026-08-12/loan-what-if-integration.md` — 대출 비교 병합 후 README·백로그 반영
- `devlog/2026-08-12/wealth-guidance-v0.1.md` — 공식 근거 기반 재테크 기초 가이드 구현·검수·병합
- `devlog/2026-08-12/wealth-guidance-integration.md` — 재테크 가이드 병합 후 README·백로그 반영
- `devlog/2026-08-12/product-detail-compare-v0.1.md` — 공식 상품 상세·2개 비교 구현·실데이터 검수·병합
- `devlog/2026-08-12/product-detail-compare-integration.md` — 상품 상세·비교 병합 후 README·백로그 반영
- `devlog/2026-08-12/profile-metrics-v0.1.md` — backend 파생지표·profile/Home live 연결 구현·검수·병합
- `devlog/2026-08-13/profile-metrics-integration.md` — profile metrics 병합 후 README·색인·백로그 반영
- `devlog/2026-08-13/profile-database-encryption.md` — SQLAlchemy·Alembic·profile 암호화 구현·검수·PR 병합
- `devlog/2026-08-13/profile-persistence-integration.md` — 암호화 영속화 병합 후 README·색인·백로그 반영
- `devlog/2026-08-13/session-profile-ownership.md` — 익명 세션 인증·profile 소유권 구현·검수·통합 기록
- `devlog/2026-08-13/session-profile-ownership-integration.md` — PR #43 병합·로컬 migration·browser E2E 기록
- `devlog/2026-08-13/session-data-lifecycle.md` — 익명 계정 삭제·만료 데이터 정리 구현·검수 기록
- `devlog/2026-08-13/session-data-lifecycle-integration.md` — PR #46 병합·로컬 DB·브라우저 E2E 기록
- `devlog/2026-08-13/docker-postgres-runtime.md` — Docker·PostgreSQL·backup/restore 운영 스택 기록
- `devlog/2026-08-13/docker-postgres-integration.md` — PR #48 Linux CI·병합·로컬 종료 기록
