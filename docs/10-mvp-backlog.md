# 10. MVP Backlog

## P0 — 반드시 구현
- [x] FinancialProfile CRUD v0.1 (process-local prototype)
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
- [ ] Docker
- [ ] public MVP deployment

## P1 — 경쟁력
- [ ] Rule-only vs LLM-only vs Hybrid benchmark
- [ ] persona별 scenario golden set
- [x] URL lexical feature analysis (offline safe implementation)
- [ ] URL domain/reputation feature analysis (outbound-fetch policy required)
- [x] financial profile dashboard shell
- [x] financial profile frontend integration (process-local backend CRUD v0.1)
- [ ] product comparison UI
- [x] official product candidate UI (goal-only minimum input)
- [ ] What-if loan simulation
- [ ] API p50/p95 instrumentation
- [ ] audit log / PII masking

## P2 — 본선/Stretch
- [ ] STT
- [ ] voice scam scenario
- [ ] AI red-team suite
- [ ] prompt injection benchmark
- [ ] screenshot/phishing-page analysis
- [ ] advanced personalization
