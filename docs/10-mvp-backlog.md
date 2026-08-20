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
- [ ] public MVP deployment (real domain/DNS/certificate verification required) — 선행 P0는 전부 완료. 배포 절차·staging 예행연습·외부 검증기는 `31-public-deployment.md`에 준비돼 있고 `localhost` 예행연습까지 끝났다. 남은 것은 도메인·서버와, always-free `e2-micro`(1GB)를 고르면서 선행조건이 된 이미지 빌드·배포 파이프라인이다 (`28` P1-3)
- [x] rate limiting + 요청 본문 크기 제한 (인증 없는 `/api/v1/analyze`·세션 발급 보호)
- [x] 만료 데이터 정리 자동 스케줄 (`adr/0004` 이행)
- [x] 운영 backup 스케줄 + 복원 리허설 (합격 기준은 "복원됐다"가 아니라 "복호화됐다")
- [x] 파이썬 의존성 해시 잠금 + 런타임·개발 의존성 분리

## P1 — 경쟁력
- [x] Legacy rule vs Scenario Engine bootstrap benchmark (합성 61건, non-held-out)
- [x] persona·전체 UserState scenario golden set v0.1 (합성 bootstrap)
- [x] 고정 LLM-only vs Hybrid 비교 (2026-08-19, non-held-out 61건. `docs/32`)
- [x] 규칙 신호 어휘 v0.2 — 비교가 찾아 준 오답 3건을 규칙으로 메움 (2026-08-19)
- [x] **held-out v0.2 골든셋** (2026-08-20, 72건) — 동결 후 첫 측정에서 개발셋 1.000 이 기억이었음을 확인: precision 0.854 / recall 0.795 / 오탐률 0.214 / 상태 정책 정확도 0.681. `docs/32`
- [ ] **held-out 이 드러낸 엔진 결함 수정** — ① 은행·기관 자칭 사칭 어휘 부재(`authority_impersonation` 재현율 0.333) ② `classify_fraud_types` 에 `money_transfer_request` 분기 없음(등급은 high 인데 유형이 빔) ③ 한국어 어미를 못 넘는 부분 문자열 매칭 ④ 요구 맥락 없이 맨 명사만으로 켜지는 신호(오탐 6건 전부). **고치면 v0.2 는 소진된다**
- [ ] **held-out v0.3** — 위 수정 이후의 깨끗한 재측정용. 수정 전에 작성·동결해야 한다
- [ ] **투자·리딩방 유형** — `FRAUD_TYPE_ORDER` 에 자리가 없어 해당 사례는 라벨조차 붙일 수 없다. 데이터가 아니라 taxonomy 의 공백
- [ ] held-out v0.2 에 대한 LLM-only / Hybrid 3자 비교 (유료 호출 1회 필요. 현재 `not_run`)
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
