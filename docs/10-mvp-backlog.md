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
- [ ] public MVP deployment (real domain/DNS/certificate verification required) — 선행 P0는 전부 완료. 배포 절차·staging 예행연습·외부 검증기는 `31-public-deployment.md`에 준비돼 있고 `localhost` 예행연습까지 끝났다. 남은 것은 도메인과 서버뿐이다
- [x] rate limiting + 요청 본문 크기 제한 (인증 없는 `/api/v1/analyze`·세션 발급 보호)
- [x] 만료 데이터 정리 자동 스케줄 (`adr/0004` 이행)
- [x] 운영 backup 스케줄 + 복원 리허설 (합격 기준은 "복원됐다"가 아니라 "복호화됐다")
- [x] 파이썬 의존성 해시 잠금 + 런타임·개발 의존성 분리

## P1 — 경쟁력
- [x] Legacy rule vs Scenario Engine bootstrap benchmark (합성 61건, non-held-out)
- [x] persona·전체 UserState scenario golden set v0.1 (합성 bootstrap)
- [ ] 고정 LLM-only vs proposed Hybrid held-out benchmark
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
- [x] frontend accessibility v0.1 (skip link, focus ring, live status, reduced motion, structural regression)
- [x] responsive dark-browser check (375/768/1280, nav transition, horizontal overflow)
- [ ] screen reader + quantitative AA contrast + light mode + iOS Safari device audit
- [x] PWA 설치 + 문자 앱 공유 시트 진입 (`share_target`은 원문을 주소에 싣지 않도록 POST, 오프라인 셸, 설치 유도) — 실기기 공유 확인은 실도메인 이후
- [ ] account-level audit log (requires identity and retention policy)

## P2 — 본선/Stretch
- [ ] STT
- [ ] voice scam scenario
- [ ] AI red-team suite
- [ ] prompt injection benchmark
- [ ] screenshot/phishing-page analysis
- [ ] advanced personalization
