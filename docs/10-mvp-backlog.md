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
- [x] **held-out v0.5** (2026-08-21, 72건) — 아래 네 결함을 고치기 **전에** 얼리고 수정 전 baseline 을 같은 커밋에 넣었다. 정상 28건(39%)을 네 수정이 깨질 자리에 몰아 놓아서, **수정 전 오탐률 0.3929 는 성능이 아니라 가격표다**. v0.4 소진
- [x] **활용형·어휘 폭 보강** (2026-08-21) — "폰 고장"·"번호 바꿨"·"배 확정"·"오픈채팅방 입장"·"깔아"·"비번" 등. 한국어 어미가 앞 음절에 합쳐지므로 기본형이 활용형의 접두사가 아니다("메워 드리" 는 "메워 드립니다" 를 못 잡는다)
- [x] **반말 요구 표지** (2026-08-21) — `CASUAL_DEMAND_PATTERN`. 존댓말 목록을 넓힌 게 아니라 **거울**로 만들었다("-아/어 주다" 반말 활용 + "-아/어 놓다" 명령형, 맨 명령형 어미 제외). 지인 사칭은 거의 전부 반말이라 게이트가 **가장 잡아야 할 사기에서 가장 자주 안 열렸다**
- [x] **예방 안내문 표지 보강** (2026-08-21) — 어간이 붙은 서술형만 넣었다. **맨 "하지 않" 은 넣지 않는다** — 넣으면 "소명하지 않으면 계좌가 동결됩니다" 가 예방 안내문이 된다. v0.5 양성 6건이 6개 유형에 걸쳐 이 실수를 즉시 드러내도록 배치돼 있다
- [x] **요구·대상을 절 단위로 묶기** (2026-08-21) — **거리로는 못 가른다.** `fh-321`(사기)과 `fh-356`(정상)은 요구·대상 거리가 같고, 진짜 사기는 요구를 마지막 절에 몰아 쓴다. 가르는 것은 **절의 시제**이며, 절 끝에 붙은 과거형만 센다. v0.5 f1 0.625 → 0.935, v0.4 미탐 1건 → 0건, v0.2 오탐 2건 → 0건. `docs/32`
- [x] **필수 signal 코드 이름 오류** (2026-08-21) — v0.4 11건·v0.5 24건이 응답에 실리지 않는 **내부 규칙 이름**을 요구하고 있어서 `required_signal_coverage` 가 탐지가 아니라 이름 불일치를 재고 있었다. 허용 목록을 규칙 표에서 끌어오고 검증기로 고정
- [x] **held-out v0.6** (2026-08-22, 72건) — 아래 세 결함을 고치기 **전에** 얼리고 수정 전 baseline 을 같은 커밋에 넣었다(`ef60a5e`). **이번 회차는 수정의 방향이 반대라 안전장치도 반대다** — 셋 중 둘이 좁히는 수정이고 그 값은 정상 문장이 아니라 사기 쪽에서 치러지므로, 부정 사례 수가 아니라 **좁히기가 끊을 수 있는 자리에 놓인 양성 사례 수**를 테스트로 고정했다. v0.5 소진
- [x] **`private_channel_invite` 의 투자·매매 맥락 조건** (2026-08-22) — 조사 붙은 활용형(`단톡방으로`·`오픈채팅방 입장`)을 목록에서 지우고 맨 방 이름을 새 게이트 `investment_gated_keywords` 로 내렸다. **매매 맥락 어휘에 "투자"와 "주식"은 넣지 않는다** — 정상 문장이 매일 쓰는 말이라 방 이름과 만나면 학부모 단톡방이 걸린다. v0.4 `fh-244` / v0.5 `fh-308` 이 남긴 질문이 여기서 닫혔다
- [x] **`authority_impersonation` 의 게이트 모양** (2026-08-22) — **자칭 신분은 요구의 대상이 아니다.** (a) 절 시제로 가릴 대상이 아니므로 메시지 **전체**에서 찾고, (b) 게이트를 요구의 *존재*가 아니라 요구의 *내용*(인증정보·계좌·앱 설치·원격·송금·의심스러운 링크)으로 좁혔다. 규칙 표에 `request_gated_keywords` 를 두고 탐지를 두 바퀴로 나눴다 — 한 바퀴면 규칙 표의 **순서**가 판정을 바꾼다. v0.6 유형 f1 0.526 → 0.947, v0.2 `fh-005` 신호 손실 닫힘
- [x] **공식 창구 안내 절을 요구에서 빼기** (2026-08-22) — **정상 기관은 이미 아는 창구로 보내고 사기는 자기가 만든 창구로 부른다.** 창구 이름 + 방향 조사 + 안내 서술어를 같은 절에서 볼 때만 적용한다(메시지 단위로 보면 안전한 첫 문장 하나로 나머지가 통과한다). 거울상인 "담당자 번호로 연락" 계열은 반대로 민감 요구로 친다. v0.5 `fh-360`·`fh-361` 오탐 닫힘
- [ ] **`HIGH_RISK_SIGNAL_COMBINATIONS` 기존 조합 확장** — v0.4 에서는 **새 신호가 들어간 조합만** 추가했다. 기존 신호끼리를 같이 손대면 v0.3 수치가 무엇 때문에 움직였는지 갈라낼 수 없다. v0.3 의 10건에 더해 v0.6 의 6건(`fh-415`·`fh-416`·`fh-418`~`fh-421`, 전부 `authority_impersonation` + 넘겨주기 신호)이 대상이다. **탐지가 아니라 가격표 문제**이므로 정책 단독 커밋
- [ ] **held-out v0.7 동결** — 위 정책 확장과 아래 두 결함을 고치기 **전에**. v0.6 은 그 수정에 쓰이는 순간 소진된다
- [ ] **`receive_and_forward_money` 어휘 구멍** — "그 돈 빼서 다른 계좌로 넣어 주세요"(v0.6 `fh-446`, v0.3 `fh-138`). 어휘가 "다시 보내"·"전달해" 뿐이라 '빼서 넣어' 어형이 없다
- [ ] **`secrecy_isolation` 에 대응하는 사기 유형** — v0.6 `fh-454`. 신호는 켜지는데 유형이 비어 이진 판정이 정상으로 나간다. 탐지 실패가 아니라 taxonomy 의 공백이라 v0.4 와 같은 모양의 확장이 필요하다
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
