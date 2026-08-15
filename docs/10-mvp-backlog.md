# 10. MVP Backlog

공개 배포까지 남은 항목의 순서·완료 기준은 `28-production-readiness.md`에 있다. 이 문서는 기능 범위, 28은 운영 준비 상태를 다룬다.

## P0 — 반드시 구현
- [x] FinancialProfile CRUD v0.1 (process-local prototype)
- [x] FinancialProfile SQLAlchemy·Alembic 영속화 + application-level 인증 암호화
- [x] 공식 금융상품 API adapter (live 검증 2026-08-12)
- [x] 최신월 공식 상품 live data profile (325건, 2026-08-12)
- [x] Product normalization + latest-month in-memory cache
- [x] source identity integrity / conservative duplicate policy
- [x] 사용자 goal 기반 conservative deterministic filtering v0.1
- [x] 원리금균등/원금균등 대출 시뮬레이터
- [x] Fraud text risk-signal extraction
- [x] Scenario Engine v0.1
- [x] 공식 근거 기반 설명
- [x] 분석 결과 provenance/source
- [x] pytest + CI
- [x] 익명 계정 전체 삭제 + 만료 세션/profile dry-run 정리
- [x] Docker·PostgreSQL runtime + migration + backup/restore CI
- [x] HTTP security headers + same-origin state-change protection + HTTPS deployment config
- [ ] public MVP deployment (real domain/DNS/certificate verification required) — 선행 조건은 `28-production-readiness.md` 2절 P0-1~P0-5
- [x] rate limiting + 요청 본문 크기 제한 (인증 없는 `/api/v1/analyze`·세션 발급 보호)
- [x] 만료 데이터 정리 자동 스케줄 (`adr/0004` 이행)
- [ ] 운영 backup 스케줄 + 복원 리허설 (현재 pg_dump는 CI 검증 경로에만 존재)
- [x] 파이썬 의존성 해시 잠금 + 런타임·개발 의존성 분리

## P1 — 경쟁력
- [ ] Rule-only vs LLM-only vs Hybrid benchmark
- [ ] persona별 scenario golden set
- [x] URL lexical feature analysis (offline safe implementation)
- [ ] URL domain/reputation feature analysis (outbound-fetch policy required)
- [x] financial profile dashboard shell
- [x] financial profile frontend integration (backend CRUD v0.1)
- [x] deterministic profile metrics + live profile/Home status v0.1
- [x] official product detail / 2-product comparison UI
- [x] official product candidate UI (goal-only minimum input)
- [x] What-if loan simulation (backend-only calculation, current vs alternative UI)
- [x] 재테크 기초 가이드 v0.1 (공식 금융교육 근거, 입력·종목·매매 추천 없음)
- [x] API latency instrumentation (exact JSON duration + process histogram; dashboard pending)
- [x] privacy-safe request logging / PII non-disclosure regression
- [ ] account-level audit log (requires identity and retention policy)

## P2 — 본선/Stretch
- [ ] STT
- [ ] voice scam scenario
- [ ] AI red-team suite
- [ ] prompt injection benchmark
- [ ] screenshot/phishing-page analysis
- [ ] advanced personalization
