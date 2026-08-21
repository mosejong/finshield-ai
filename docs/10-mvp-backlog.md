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
- [x] **held-out v0.3** (2026-08-20, 60건) — 엔진 수정 **전에** 동결하고 수정 전 baseline 을 같은 커밋에 넣었다. 커밋 순서가 증거다
- [x] **held-out 이 드러낸 엔진 결함 수정** (2026-08-20) — 네 가지 모두 닫았다. v0.3 에서 f1 0.677 → 0.984, 오탐 10건 → 0건. **v0.2 는 소진됐다.** 이 숫자는 표적 회귀 셋의 값이지 일반화 성능이 아니다. `docs/32`
- [x] **held-out v0.4** (2026-08-21, 60건) — 투자·지인 사칭 탐지가 **존재하기 전에** 동결하고 구현 전 baseline 을 같은 커밋에 넣었다. 커밋 순서가 증거다
- [x] **투자·리딩방 / 지인 사칭 유형** (2026-08-21) — `investment_scheme`·`acquaintance_impersonation` 을 taxonomy 에 넣고 신호 3종(`guaranteed_return_offer`·`private_channel_invite`·`familiar_person_claim`)과 액션 `VERIFY_BY_KNOWN_CONTACT` 로 구현. v0.4 에서 f1 0.655 → 0.946, 미탐 17건 → 1건, **오탐률 0.125 불변**. v0.2·v0.3·개발셋 수치는 한 자리도 안 바뀜. `docs/32`
- [ ] **held-out v0.5** — 아래 결함들을 고치기 **전에** 얼려야 한다. v0.4 는 그 수정에 쓰이는 순간 소진된다
- [ ] **활용형·어휘 폭 보강** — v0.4 잔여 미탐 4건이 전부 같은 부류다. 어휘 "폰이 고장" vs 문장 "폰 고장났어"(`fh-223`), "확정 수익" vs "5배는 확정"(`fh-206`), "오픈채팅방으로" vs "오픈채팅방 입장"(`fh-215`), 미수록 표현(`fh-227`). v0.3 의 `옮기`/`옮겨` 와 같은 문제
- [ ] **반말 요구 표지** — `DEMAND_MARKERS` 가 "-아/어 주세요" 는 덮지만 반말 "보내 줘" 를 못 덮는다(`fh-219`). 지인 사칭 문자는 대부분 반말이다. **공유 게이트를 건드리므로 오탐을 따로 재야 한다**
- [ ] **예방 안내문 표지 보강** — "추천하지 않습니다"·"하지 않습니다" 가 `PREVENTION_STATEMENT_MARKERS` 에 없어 예방 안내문이 사칭으로 잡힌다(`fh-245`·`fh-260`)
- [ ] **요구·대상을 절 단위로 묶기** — 요구·금액 조건이 지금은 메시지 단위라 요구가 어느 대상을 향한 것인지 보지 않는다. v0.2 잔여 오탐 2건(`fh-050`·`fh-063`), v0.4 의 `fh-252`(과거형 자기보고를 요구로 읽음)가 이 형태다
- [ ] **`HIGH_RISK_SIGNAL_COMBINATIONS` 기존 조합 확장** — v0.4 에서는 **새 신호가 들어간 조합만** 추가했다. 기존 신호끼리를 같이 손대면 v0.3 수치가 무엇 때문에 움직였는지 갈라낼 수 없다. v0.3 의 10건이 여전히 대상이다
- [ ] **판정 프롬프트 v0.2 + 유료 재실행** — `FRAUD_JUDGE_PROMPT` 가 6종 taxonomy 위에 있어 이제 3종(`advance_fee_demand`·`investment_scheme`·`acquaintance_impersonation`)을 만들지 못한다. 프롬프트를 바꾸면 sha256 이 바뀌어 기존 판정 파일과의 연결이 끊긴다
- [ ] **투자 사기 공식 근거 확보** — 금융감독원 파인 제도권금융회사조회 URL 을 확인하지 못해 `investment_scheme` 액션이 `police_1394` 에 붙어 있다. 새 외부 참조는 검토 대상(`CLAUDE.md`)
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
- [x] prompt injection benchmark (2026-08-20, 7건 개발셋) — `evaluation/data/injection_golden_v0.1.jsonl`, `tests/test_llm_prompt_injection.py`. **held-out 아니고 방어 교정에 쓴 셋이라 통과율을 방어 성능으로 주장하지 않는다**
- [ ] screenshot/phishing-page analysis
- [ ] advanced personalization
