# FinShield Documentation Index

## Product / research
01 problem definition · 02 research plan · 03 product scope · 05 data/evaluation · 06 roadmap · 07 official API candidates · 09 financial profile · 10 MVP backlog · 32 fraud evaluation benchmark · 33 competition evidence pack

## Competition submission (2026 금융 AI Challenge)

제출물 ①기획서 · `35-competition-proposal.md`
제출물 ②기능명세서 · `36-functional-specification.md` — **구현된 기능만** 적고, 미구현·미측정은 13절에 분리한다
제출물 ③웹서비스 URL · 배포 절차는 `31-public-deployment.md`

두 문서의 수치는 `evaluation/results/fraud-benchmark-v0.1.json` 을 출처로 한다. 재측정하면 두 문서와 `32`, `33` 을 함께 고쳐야 한다 — 한쪽만 고치면 제출물끼리 숫자가 갈라진다.

## Architecture / engineering

Fraud evaluation bootstrap policy · `adr/0007-bootstrap-fraud-evaluation.md`
27 observability/PII masking · `adr/0006-privacy-safe-observability.md`
26 HTTP security/HTTPS boundary · `adr/0005-http-security-and-https-boundary.md`
04 architecture · 11 engineering standards · 13 frontend architecture · 14 development workflow · 15 product catalog live profile · 16 product catalog cache · 17 product catalog identity · 18 deterministic product filtering · 19 wealth guidance · 20 product detail/comparison · 21 profile derived metrics · 22 profile persistence/encryption · 23 session/profile ownership · 24 anonymous data lifecycle · 25 Docker/PostgreSQL runtime · 28 production readiness · 29 backup and recovery · 30 PWA and share target · 31 public deployment (domain/DNS/TLS) · 34 LLM explanation runtime · 37 housing deposit risk (전세보증금 위험 점검) · ADR 색인 `adr/README.md`

## Security

Privacy-safe logs and runtime PII regression: `27-observability-pii-masking.md` (설명 계층 실패 지표의 닫힌 어휘는 같은 문서 "설명 계층 지표" 절, 설계 이유는 `34-llm-explanation-runtime.md` 12절)
HTTP response headers, same-origin state changes, trusted hosts and public TLS: `26-http-security-https.md`
08 AI security alignment · 12 security threat model

## Agent instructions
Root `CLAUDE.md` · root `SKILL.md` · `.claude/skills/finshield/SKILL.md`

동일한 규칙을 Claude 외 agent 도구에도 적용하려고 `AGENTS.md` 와 `.agents/skills/finshield/SKILL.md` 를 미러로 둔다. 넷 다 같은 Language rule·non-negotiables 를 담아야 하며, 한쪽만 고치면 도구별로 규칙이 갈라진다. `web/AGENTS.md` 는 `next dev` 가 자동 생성하는 별개 파일이니 손대지 않는다.

## Development history

- `devlog/2026-08-24/fraud-holdout-v1.1.md` — **재는 자리가 말라붙었다** - 발견이 엔진이 아니라 **셋**에 있었던 첫 회차·열 회차에 걸쳐 `received_only` 가 아닌 사례가 27건에서 6건까지 줄었고 **아무도 그것을 정하지 않은** 것(매 회차의 결함이 문장 안에 있었고 문장 안의 결함은 상태를 고정해야 깨끗하게 재지므로 회차마다 옳은 선택이었다)·**지표가 만점에 가까울 때 물어야 할 것은 "무엇이 남았나" 가 아니라 "이 숫자의 분모가 무엇인가" 다**·상태 정책 정확도 0.9571 → **0.6582** 가 엔진이 나빠진 게 아니라 재지 않던 것을 재기 시작한 값이라는 것·**상태가 있는 정상의 천장은 그 상태가 강제하는 바닥이다**(정상에 `low` 를 걸면 그 라벨이 상태 정책 자체를 결함으로 선언한다 — 사기가 아니라는 사실은 등급이 아니라 유형과 행동으로 표현되어야 한다)·일곱 상태 중 둘만 예방 행동을 내던 것을 넷에 더하면서 **상태는 신호를 대신하지 않는다**로 게이트를 건 이유(계좌를 알려 주는 일도 앱을 까는 일도 대부분 정상이다)와 네 상태 24건을 전부 덤프해 **게이트가 닫히는 사기 여덟이 전부 이미 이름 적힌 어휘 공백**임을 확인한 것·**사건 어휘가 창구를 가리킨다**(사기 문자의 절반은 누구인지 말하지 않고 무슨 일이 일어났는지만 말한다)와 창구가 없다고 판단하면 폴백이 아는 연락처를 내므로 **미탐 하나가 틀린 행동 하나를 함께 낸다**는 것·`확인`·`절차`·`신청` 을 **일부러 뺀** 이유(흔해서가 아니라 창구를 지목하지 않아서)·고립을 어휘가 아니라 **대상 × 금지의 절 안 교차**로 본 것과 v1.0 이 요구 쪽에서 이미 만난 같은 어형이라는 것·넓히자마자 v0.9 `fh-741`(한국에서 가장 흔한 **정상** 보안 문자)이 오탐이 되고 **화자를 예외로 두는 첫 안을 버린** 이유(사기가 흉내 낼 수 있다)와 **금지의 대상이 읽는 사람이 쥔 비밀이면 고립이 아니라 보안 안내다** — 인증번호를 말하지 말라는 문장은 인증번호를 요구하지 않는다·**얼린 셋이 예측 둘을 반증한** 것(`-하셔야 합니다` 는 이미 다른 어간이 받고 있었고 스토어 이름 추가는 방향이 반대였다 — 없는 결함을 고치지 않는 것도 회차의 결과다)·v1.0 이 이름 적어 둔 `fh-803` 이 닫혀 **결함을 이름으로 적어 두면 다음 회차가 갚는다**가 두 번 연속 확인된 것·v1.0 `fh-803` 과 v1.1 `fh-901` 이 사실상 같은 문장에 **반대 라벨**을 달아 `forbidden_action_avoidance` 를 1.0000 → 0.9231 로 내린 것과 **뒤에 적힌 판단을 따르고 숫자에 그대로 남긴** 것, 그리고 **얼린 셋을 태우지 않으면서 회귀와 불일치를 구분하는 방법은 불일치의 목록을 고정하는 것뿐**이라 테스트가 "이 한 건" 과 "다른 불일치 없음" 을 함께 못 박은 것·놓친 필수 행동 39 → **21** 이고 남은 21이 **하나도 빠짐없이 신호 누락의 하류**라 행동 표의 구멍은 닫히고 남은 것이 전부 어휘가 된 것·오탐 `fh-942` 가 **진짜 경찰 통지문**이라 **버텨 온 판단과 재 본 적 있는 판단은 다르다**는 것
- `devlog/2026-08-24/fraud-holdout-v1.0.md` — **자리에서 본다** - 새로 상상한 사기 어형이 하나도 없이 **앞선 회차가 이름으로 적어 둔 결함 다섯만** 재려고 얼린 회차·동결 시점 오탐 일곱 중 **다섯이 한 어형**(`-(으)면 안 됩니다`)이었고 예방 안내문은 위험한 행동을 말리려고 그 행동을 입에 올려야 해서 **하지 말라는 문장이 요구를 세는 자리에서 요구로 세어졌던** 것·어형을 하나씩 빼는 대신 **금지 앞자락을 잘라 내고 남은 말로 판단**하게 한 것(어형은 무한하고 어휘는 유한하다)·절을 통째로 버리면 사기가 금지 **뒤에서** 하는 요구까지 사라져 오탐 다섯을 지우는 대신 미탐 하나를 만든다는 것·**금지된 창구는 창구 안내가 아니다**로 반대편까지 한 수정으로 닫힌 것·채널 어휘에 스토어·홈택스를 넣으면서 **목록에 없다는 것이 곧 아는 창구가 아니라는 뜻**이라 메시지 안의 앱은 그대로 걸리는 것·긴급 어휘를 여섯에서 열둘로 늘리면서 **점수 표는 일부러 건드리지 않은** 이유(같은 시간 표현을 평범한 청구서도 쓴다)·띄어 쓴 `대환 대출` 을 무조건 층이 아닌 요구 게이트에 넣은 이유·고립 요구를 민감 요구 목록에 넣어 **넘겨줄 물건이 없을 뿐 요구가 없는 것이 아니다**를 살린 것과 기밀 유지를 여전히 넣지 않은 이유·다섯이 전부 넓히기라 값이 한 방향으로만 치러져 **정상 32건 전부가 천장을 선언하고 그중 스물여섯이 넓히려는 바로 그 어형을 쓰는 정상 문장**인 것·여섯 회차 묵은 빚이던 v0.9 오탐 둘이 함께 닫혀 그 셋이 만점이 된 것과 v0.7 이 양방향으로 움직여 **잃은 쪽도 그대로 적고 옛 라벨은 고치지 않은** 것·**얼리는 커밋에 얼린 것을 지키는 테스트가 없으면 얼린 것이 아니라 적어 둔 것이다** — 등록 직후 v0.9 문장 둘을 그대로 물려받은 것이 걸려 **다시 쓰지 않고 뺐다**는 결정(수정이 존재하는 지금 쓰는 문장은 수정을 알고 쓰는 문장이다)·수정 뒤에 baseline 을 동결 시점 엔진으로 다시 재고 재현 명령을 공개한 것·고치지 않은 4건과 **재려던 것을 재지 못하게 하는 스키마 제약도 결함이다**
- `devlog/2026-08-23/fraud-holdout-v0.9.md` — **갈아 끼우기** - 이진 판정이 만점이라 사기/정상 사례를 더 넣어도 잴 것이 없어져 **행동**을 정면으로 겨냥한 회차·행동 지표가 `required ⊆ predicted` 만 세어 **전부 붙이는 엔진이 1.0 을 받던 것**을 셋을 얼리기 **전에** 닫은 것(`forbidden_action_avoidance`, 금지를 선언하지 않은 셋에는 `1.0` 이 아니라 `None`)·같은 요구를 이름 있는 쪽과 없는 쪽에 하나씩 놓아 A ↔ A' 로 짠 것과 얼리기 전에 **결함을 재현하지 않는 여덟 건을 다시 쓴** 이유·**틀린 행동은 없는 행동보다 나쁘다**(없는 창구로 보내면 사용자는 메시지에 적힌 번호로 건다)와 확인 행동을 신호 표에서 떼어 `resolve_verification_actions` 로 옮긴 것·**자칭으로 가른 첫 안이 71건을 잃고 틀렸음이 드러난 것**·v0.7 `fh-523` 과 v0.8 `fh-627` 이 정반대 라벨이라 **뒤에 적힌 판단을 따르고 옛 라벨은 고치지 않은** 것·위협 + 접근수단 요구를 자칭 없이 high 로 올린 것과 **고발은 요구가 아니다**(게이트는 두고 대상 탐색만 좁힘)·이진 판정 네 칸과 오탐·미탐이 열 셋 어디에서도 안 움직이고 값이 전부 **옛 셋의 라벨**에서 치러진 원장·판정 프롬프트 해시가 끼워 넣은 action title 을 덮지 않는다는 발견·고치지 않은 6건
- `devlog/2026-08-23/fraud-holdout-v0.8.md` — **넓히기 다섯을 한 번에** - v0.7 이 남긴 결함이 거의 전부 어휘를 넓히는 수정이라 정상 36건을 **각 넓히기가 깨질 수 있는 자리에 하나씩** 배치한 것·동결 시점 precision 1.0000 / FPR 0.0000 은 올라갈 자리가 없다는 것·작업 중 두 번 깨졌고 두 번 다 **어휘를 좁히는 대신 구조적 원인에서** 고친 것(예방 표지를 쓰는 두 번째 호출 자리·금지형은 어휘가 아니라 자리의 문제)·`-지 않` 을 금지 어미에서 일부러 뺀 이유(협박은 요구의 다른 얼굴이다)·낱말에 담기지 않는 요구를 순서로 보는 `demand_gated_sequences` 와 조합을 손으로 적지 않고 곱한 이유·**등급을 점수에서 다시 계산하지 않고 점수를 등급의 띠까지 올린** 이유와 바닥을 등급 계산 **뒤에** 깐 이유·`test_legacy_baseline_exact_scores` 가 API 를 떠나 채점기를 직접 부르게 된 것·**옛 셋 재측정이 잡은 회귀**(v0.5 `fh-317` - 지표는 한 칸인데 손해는 이름에 있다)·v0.7 개선을 성능 주장으로 읽지 않는 이유·이진 판정이 만점이 되면서 남은 변별력이 이름·행동·등급으로 옮겨 간 것과 고치지 않은 7건
- `devlog/2026-08-22/fraud-ceiling-and-grade-raising.md` — **재는 자에 천장이 없었다** - 등급을 올리는 수정은 `_scenario_policy_accuracy` 의 `>=` 아래에서 어디서도 점수를 잃을 수 없으므로 셋을 쓰기 **전에** `expected_max_risk`·`risk_ceiling_accuracy` 를 먼저 넣은 것·**천장은 정상 문장에만 선언한다**(사기를 높게 매기는 것은 결함이 아니라 신중함이다)·천장 없는 셋에 `1.0` 이 아니라 `None` 을 돌려준 이유(재지 않은 것을 만점으로 적으면 그것이 지어낸 근거다)·미선언 필드를 dataset sha 에서 뺀 이유(선언하지 않은 라벨은 라벨이 아니다)·held-out v0.7 을 수정 **전에** 동결·**비밀 유지는 정상이고 확인 차단이 신호다** - 유형을 붙이기 전에 어휘를 좁혀야 했던 것을 baseline 이 먼저 기록한 것·**재전달을 만드는 것은 동사도 목적어도 아니고 요구다** 와 맨 명령형 어미를 게이트 안에서만 읽은 이유·**기관은 자칭과 같은 메시지에서 넘겨 달라고 하지 않는다** 와 조합 목록을 사례가 아니라 `SENSITIVE_REQUEST_SIGNALS` 에서 끌어온 것·등급이 오른 39건이 전부 사기이고 정상 문장이 한 건도 안 움직였다는 것을 천장이 처음으로 말할 수 있게 된 것·일부러 고치지 않은 7건과 `risk_score`/`risk_level` 분리
- `devlog/2026-08-22/fraud-request-gated-identity.md` — held-out v0.6 을 수정 **전에** 동결하고 세 가지 탐지 수정(기관 자칭의 민감 요구 게이트·공식 창구 안내 절 제외·폐쇄 채널 초대의 매매 맥락 조건)·**자칭 신분은 요구의 대상이 아니다** - 정체는 절 시제로 가릴 것도 요구의 목적어도 아니라 메시지 전체에서 찾고 요구의 *내용*으로 게이트를 건다는 판단·**정상 기관은 이미 아는 창구로 보내고 사기는 자기가 만든 창구로 부른다**와 그 거울상·앞선 다섯 판과 달리 이번엔 **좁히는** 수정이라 값이 정상 문장이 아니라 사기 쪽에서 치러진다는 것과 그래서 안전장치를 양성 사례 수로 세운 것·매매 맥락 어휘에 "투자"·"주식"을 넣지 않은 이유·이미 소진된 셋에서 나온 회귀 7건을 보수한 것이 규칙 위반이 아닌 이유·일부러 고치지 않은 4건
- `devlog/2026-08-21/fraud-clause-scoped-demand.md` — held-out v0.5 를 수정 **전에** 동결하고 네 가지 탐지 수정(활용형 어휘·반말 요구 표지·예방 안내문 표지·절 범위 결합)·**거리는 신호가 아니다** - 요구와 대상을 묶는 것은 절간 거리가 아니라 절의 시제라는 판단·맨 "하지 않" 을 예방 표지에 넣지 않은 이유·한국어 어미가 앞 음절에 합쳐져 기본형이 활용형의 접두사가 아니라는 함정·필수 signal 코드 이름 오류로 coverage 가 탐지가 아니라 이름 불일치를 재고 있던 것·일부러 고치지 않은 6건
- `devlog/2026-08-21/fraud-taxonomy-investment-acquaintance.md` — 투자·리딩방 유인과 지인 사칭을 유형 표에 넣고 탐지 구현·held-out v0.4 를 구현 **전에** 동결(두 유형 baseline f1 0.000 이 커밋에 남아 있음)·호칭이 아니라 "원래 번호로 되걸 수 없게 만드는 핑계" 를 잡은 이유·"원금 보장" 이 예금 안내문에서는 사실이라 조사 붙은 형태를 어휘에서 뺀 것·맨 명사 "리딩방" 을 쓰지 않아 피해자 자기보고가 통과한 것·오탐률이 움직이지 않은 것이 왜 f1 상승보다 중요한지·확인 못 한 금감원 URL 대신 유형만 이름 붙인 것·남은 결함 8건을 고치지 않고 적은 이유
- `devlog/2026-08-20/fraud-engine-demand-gating.md` — held-out 이 드러낸 네 결함 수정·재는 셋을 보지 않고 고치려고 커밋을 넷으로 나눈 것(동결·baseline 이 수정보다 먼저)·"누가 누구에게 무엇을 요구하는가" 를 어미가 아니라 어근에 붙은 형태로 판정·요구 판정을 두 번 만에 맞춘 과정·`advance_fee_demand` 유형 신설·v0.3 의 FPR 0.000 을 자랑으로 쓰면 안 되는 이유
- `devlog/2026-08-20/fraud-holdout-v0.2.md` — held-out 72건을 동결한 뒤 처음 측정·개발셋 1.000 이 성능이 아니라 기억이었음·오탐 6건이 전부 "누가 누구에게" 를 안 보는 한 가지 원인·`money_transfer_request` 가 유형 표에 없어 등급만 높고 유형이 비는 것·일부러 고치지 않고 남긴 이유
- `devlog/2026-08-20/prompt-injection-boundary.md` — 붙여넣은 문자를 데이터로 취급·사기 명령문은 증거이므로 보존·주입 골든셋 7건이 첫 실행에서 구멍 3개 발견·유료 측정 0/7·서술어만 보던 출력 검증이 정상 경고 4/8 을 지울 뻔한 것 / 후속: 코덱스 검토 2건 + 재현 중 발견 2건·좁히기를 문장→절→구간 3단계로·마침표 없는 문자가 통째로 지워지던 문제
- `devlog/2026-08-20/housing-tax-arrears.md` — 임대인 미납 국세·지방세 열람 추가·법이 정한 신청 기간을 단계 창으로·확인 못 한 시행령 금액은 쓰지 않음·조문 직링크 형태(`lsLinkProc.do`) 고정
- `devlog/2026-08-20/housing-deposit-frontend.md` — `/check/deposit` 화면·"모름"이 브라우저에서 0 이 되지 않게·422를 502로 덮던 문제·서버 시각을 KST 로 모음
- `devlog/2026-08-19/housing-deposit-risk.md` — 전세보증금 위험 점검 v0.1 백엔드·근거 6건 선확인·못 연 조문은 넣지 않음·출처 무결성 규칙 공통화
- `devlog/2026-08-19/first-tagged-release.md` — 첫 태그 릴리스 `v0.1.0`·설명 계층을 담은 이미지가 없었다는 발견·재배포 절차와 릴리스 대장
- `devlog/2026-08-19/competition-submission-docs.md` — 제출물 ①기획서 ②기능명세서 작성·명세를 코드에서 확인·신호 12종 정정·낡은 README 수치 교체
- `devlog/2026-08-19/rule-vocabulary-v0.2.md` — 모델이 찾아 준 오답 3건을 규칙 어휘로 메움·골든셋 밖 검증·개발셋 변별력 소진
- `devlog/2026-08-19/llm-only-benchmark.md` — LLM 단독 판정 유료 측정·Rule/LLM/Hybrid 3자 비교·채택하지 않은 조합
- `devlog/2026-08-18/post-merge-devlog-shas.md` — squash 후 SHA 정정·첫 릴리스 실측·rate limit 고정 창 flake
- `devlog/2026-08-18/deploy-image-pipeline.md` — ghcr 릴리스 워크플로·배포 override·expand/contract 롤백 전략
- `devlog/2026-08-18/llm-explanation-contract.md` — 고정 model·prompt·provider 계약·PII 최소화·출력 검증·판정 경계
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
