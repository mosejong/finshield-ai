# Fraud Scenario Engine v0.1 개발일지

## 작업 정보

- 작업일: 2026-08-12 (KST)
- 시작: 14:27 KST
- 종료: 14:56 KST
- 담당 영역: 백엔드
- 작업 브랜치: `feature/fraud-scenario-engine`
- 작업 디렉터리: `C:\Users\user\Documents\Codex\finshield-ai-backend`
- 상태: PR #2 PM 검수·CI 통과 후 `main` 병합 완료

## 목표

의심 문구와 사용자가 이미 취한 행동을 함께 받아 다음의 결정론적 흐름으로 분석하는 Fraud Scenario Engine v0.1을 구현한다.

`risk signals → fraud types → UserState → risk_level → actions → official sources`

기존 `POST /api/v1/analyze` 계약은 유지하면서 `fraud_types`, `summary`, `actions`, `official_sources`를 추가한다. LLM, 런타임 웹 검색, 사용자 제공 URL에 대한 서버 측 요청은 사용하지 않는다.

## 변경 이유

기존 분석기는 다섯 종류의 키워드 가중치를 합산하는 초기 baseline이었다. 이 구조에서는 다음 요구를 충족하기 어려웠다.

- OTP 요구가 단독으로 `low`가 될 수 있었다.
- 이미 송금하거나 앱을 설치한 상태가 위험도와 행동에 반영되지 않았다.
- 사기 유형 후보와 공식 대응 행동이 분리되어 있지 않았다.
- 행동이 어떤 공식 근거에 연결되는지 검증할 수 없었다.
- 요청의 `url` 필드는 받지만 안전 정책이 명시되지 않았다.

## 시간순 작업 기록

### 14:27 — 작업 범위와 브랜치 확인

- 현재 브랜치가 `feature/fraud-scenario-engine`인지 확인했다.
- 작업 시작 시 추적 파일 변경이 없음을 확인했다.
- 원본 저장소와 `web/`은 수정 범위에서 제외했다.
- 루트에 `AGENTS.md`가 존재하지 않아 읽을 수 없었다. 대신 `CLAUDE.md`, `SKILL.md`와 지정 문서를 기준으로 진행했다.

### 14:28 — 기준 문서와 기존 코드 검토

다음 파일을 읽고 제품 범위, 보안 원칙, 평가 기준, 기존 API를 확인했다.

- `CLAUDE.md`
- `SKILL.md`
- `docs/README.md`
- `docs/01-problem-definition.md`
- `docs/03-product-scope.md`
- `docs/05-data-and-evaluation.md`
- `docs/08-ai-security-alignment.md`
- `docs/10-mvp-backlog.md`
- `docs/11-engineering-standards.md`
- `docs/12-security-threat-model.md`
- `app/core/risk_engine.py`
- `app/schemas/analysis.py`
- `app/api/routes/analysis.py`
- `tests/test_analysis.py`

### 14:29 — 설계 결정

- 탐지, 유형 분류, 상태/행동 정책, 근거 로딩을 별도 모듈로 분리했다.
- `UserState`를 선형 진행 단계로 비교하지 않고 상태별 최소 위험도와 행동 표를 각각 정의했다.
- `risk_score`는 텍스트 신호 가중치의 실험적 baseline으로 유지하고 확률로 해석하지 않는다.
- `risk_level`은 신호 baseline과 상태별 최소 위험도 중 더 높은 값을 사용한다.
- 기존 신호 코드 `urgency`, `credential`, `account_access`, `remote_app`, `money_mule`는 새 신호와 함께 반환하되 점수에 중복 합산하지 않는다.
- 행동 우선순위는 숫자 `1`이 가장 긴급하고 `3`이 가장 낮도록 정의했다.
- 공식 근거는 정적 JSON만 읽으며 응답에는 선택된 행동이 실제 참조하는 출처만 포함한다.

### 14:30 — 신호 탐지와 분류 구현

다음 새 신호를 결정론적 키워드 규칙으로 탐지한다.

- `urgency_pressure`
- `authority_impersonation`
- `secrecy_isolation`
- `loan_policy_offer`
- `credential_request`
- `account_access_request`
- `app_install_request`
- `remote_control_request`
- `money_transfer_request`
- `receive_and_forward_money`
- `suspicious_link`
- `card_delivery_claim`

신호 조합은 고정된 순서로 다음 사기 유형 후보에 매핑한다.

- `authority_impersonation`
- `loan_policy_impersonation`
- `account_access_request`
- `money_mule_transfer`
- `smishing_malware`
- `card_delivery_impersonation`

이 결과는 범죄 확정 또는 사용자 가담 판단이 아니라 위험 유형 후보이다.

### 14:31 — 상태별 위험도와 행동 정책 구현

`received_only`, `clicked_link`, `shared_personal_info`, `shared_account_access`, `installed_app`, `received_unknown_money`, `transferred_money` 각각에 직접 정책을 연결했다.

다음 네 상태는 텍스트 신호가 없어도 `high`와 긴급 행동을 보장한다.

- `shared_account_access`
- `installed_app`
- `received_unknown_money`
- `transferred_money`

지원 행동 코드는 다음과 같다.

- `STOP_CONTACT`
- `DO_NOT_CLICK`
- `DO_NOT_INSTALL`
- `DO_NOT_SHARE_ACCESS`
- `DO_NOT_FORWARD_MONEY`
- `VERIFY_OFFICIAL_CHANNEL`
- `CONTACT_FINANCIAL_INSTITUTION`
- `CONTACT_1394`
- `CONTACT_112`
- `CONTACT_KISA_118`
- `PRESERVE_EVIDENCE`

### 14:32 — 정적 공식 근거와 무결성 검증 구현

`app/data/fraud/official_sources.json`에 검토일 `2026-08-12` 기준의 허용된 공식 URL 8개를 기록했다.

| source_id | 기관 | 용도 |
|---|---|---|
| `fsec_finance_ai_challenge` | 금융보안원 | 대회 문제 맥락 |
| `fsec_ai_strategy` | 금융보안원 | AI 보안 전략 맥락 |
| `police_1394` | 경찰청 | 1394 상담, 연락 중단, 공식 확인 |
| `police_ecrm_victim_help` | 경찰청 사이버범죄 신고시스템 | 금융기관 연락, 112, 증거 보존 |
| `kisa_118` | 한국인터넷진흥원 | KISA 118 상담 |
| `kisa_smishing` | 한국인터넷진흥원 | 링크·앱 대응 |
| `electronic_financial_transactions_act` | 국가법령정보센터 | 접근매체 공유 금지 |
| `fraud_refund_act` | 국가법령정보센터 | 금융기관 연락과 자금 재전달 방지 |

로딩 시 `source_id`, URL 중복과 검토일을 검증한다. 응답 생성 시 모든 `action.source_ids`가 존재하며 해당 출처의 `supports`에 행동 코드가 포함되는지도 검증한다. 금융보안원 맥락 자료처럼 실제 행동에서 참조하지 않는 출처는 분석 응답에 자동 포함하지 않는다.

### 14:33 — 골든 테스트 추가 및 전체 회귀 검증

다음 시나리오를 테스트했다.

- 기관 사칭 + 송금
- 저금리 대출 + 체크카드
- OTP 단독 `low` 방지
- 앱 설치 + 원격제어
- 돈 수취 후 재송금
- 카드 배송 사칭
- 정상 문자
- 같은 문장 + 다른 `UserState`
- 낮은 텍스트 신호 + 긴급 상태 4종
- 복수 사기 유형의 안정된 순서
- 10,000자 허용 및 10,001자 거절
- 사용자 URL에 대한 outbound fetch 없음
- 행동과 공식 근거의 양방향 무결성
- 공식 출처 metadata, URL 허용 목록, 중복 검증
- 기존 응답 필드와 경로 호환

### 14:34 — 스키마 강화와 최종 검증

- `risk_level`, `fraud_types`, 행동 코드를 `Literal`로 제한했다.
- 선택적 URL 길이를 2,048자로 제한했다.
- 전체 테스트와 Python compile을 다시 수행했다.
- `git diff --check`를 수행했다.

### 14:39 — PM 독립 검수와 PR 차단 이슈 확인

PM 검수에서 다음 두 문제를 PR 전 차단 이슈로 확인했다.

1. 신규 canonical 신호 가중치 합으로 `risk_score`를 계산해 기존 baseline 점수와 의미가 바뀌었다.
2. URL이 존재한다는 사실만으로 `suspicious_link`, `smishing_malware`, `medium`이 생성되어 정상 HTTPS URL도 오탐했다.

커밋·push 없이 동일 브랜치에서 수정에 착수했다.

### 14:40 — legacy baseline과 최종 위험도 분리

- 기존 규칙을 `LEGACY_RULES`로 복원했다.
- 가중치는 `urgency=12`, `credential=25`, `account_access=35`, `remote_app=30`, `money_mule=35`로 정확히 유지했다.
- `risk_score`는 legacy 신호만 합산하고 100에서 상한 처리한다.
- legacy 신호의 응답 `weight`도 기존 값으로 유지한다.
- 같은 legacy 규칙에서 여러 키워드가 잡혀도 규칙당 한 번만 합산한다. 따라서 앱 설치와 원격제어가 함께 있어도 `remote_app=30` 한 번만 반영한다.
- OTP 단독처럼 기존 점수가 25인 입력은 점수를 바꾸지 않고 canonical 신호의 최소 위험도 정책으로 최종 `risk_level`을 `medium`으로 올린다.
- 기관 사칭+송금, 대출 제안+접근수단 요구, 앱 설치+원격제어는 명시적인 신호 조합 정책으로 `high`를 적용한다.
- `receive_and_forward_money`, `remote_control_request`는 단독 고위험 canonical 신호로 관리한다.

### 14:41 — URL offline lexical 정책 교정

- URL 존재 자체는 위험 신호로 사용하지 않도록 변경했다.
- URL에 접속하거나 DNS·평판 API·외부 서비스를 호출하지 않는다.
- 다음과 같은 최소 보수 lexical 특성에만 `suspicious_link`를 부여한다.
  - 비암호화 `http` scheme
  - `localhost` 또는 IP literal
  - URL userinfo
  - 알려진 URL shortener
  - punycode hostname
  - 파싱할 수 없는 괄호 형태
- `https://www.kb.com` 같은 일반 HTTPS URL은 그 존재만으로 신호, 사기 유형, 행동, 위험도 상승을 만들지 않는다.
- 평판 조회를 하지 않았으므로 URL이 입력된 경우 summary에 안전 여부를 보증하지 않는다는 불확실성을 명시한다.

### 14:42 — 회귀·URL 테스트 확장

- 기존 다섯 규칙의 개별 exact score를 고정했다.
- 다섯 규칙 복합 입력의 100점 상한을 고정했다.
- legacy signal `weight` 전체를 회귀 검증했다.
- 앱 설치+원격제어의 legacy 점수가 30으로 한 번만 계산되는지 검증했다.
- 정상 HTTPS URL이 `low`이고 `smishing_malware`가 생성되지 않는지 검증했다.
- 비암호화 HTTP, localhost, IP literal, userinfo, shortener, punycode, malformed URL의 lexical 탐지를 검증했다.
- outbound fetch 금지 테스트를 유지했다.

### 14:43 — 1차 PM 수정사항 재검증

- 전체 테스트: **73 passed**, 경고 1건
- Python compile: 통과
- `git diff --check`: 통과
- commit, push, PR은 수행하지 않았다.

### 14:47 — PM 추가 검수와 public signal 차단 이슈 확인

PM이 내부 판단을 위해 함께 반환하던 canonical/legacy 신호가 프론트에서 중복 표시되는 문제를 확인했다. OTP 하나가 `credential_request`, `credential` 두 항목으로 보이고, 앱 설치+원격제어가 여러 신호로 반복되는 상태였다. 또한 알려진 위험 항목에 URL 존재 여부를 사용한다는 수정 전 설명이 남아 있었다.

### 14:48 — 내부 신호와 public projection 분리

- `detect_canonical_signals`는 분류, 행동, 최종 위험도 계산에만 사용하는 내부 신호를 반환한다.
- `detect_legacy_signals`는 기존 `risk_score` 계산과 `analyze_rules` 호환에만 사용한다.
- `project_public_signals`는 응답 직전에 내부 신호를 의미상 중복 없는 public 신호로 변환한다.
- 기존 다섯 개념은 public code를 `urgency`, `credential`, `account_access`, `remote_app`, `money_mule`로 유지한다.
- 앱 설치와 원격제어가 동시에 탐지돼도 public `remote_app`은 한 번만 반환한다.
- 수취·재전달 신호가 있으면 더 일반적인 `money_transfer_request` public 신호는 생략하고 `money_mule` 하나로 표현한다.
- 기관 사칭, 대출 제안, 일반 송금 요구, 카드 배송, 의심 링크 등 신규 전용 개념은 canonical code를 public에 유지한다.
- 내부 canonical 신호를 노출하는 별도 응답 필드는 추가하지 않았다.

### 14:49 — public signal 회귀 테스트와 문서 교정

- OTP public 신호가 `credential` 하나인지 검증했다.
- 자금 수취·재전달 public 신호가 `money_mule` 하나인지 검증했다.
- 앱 설치+원격제어에서 `remote_app`이 한 번만 나오는지 검증했다.
- public signal code 전체에 중복이 없고 기존 소비자 code가 유지되는지 검증했다.
- 신규 전용 개념이 canonical public code로 남는지 검증했다.
- URL 알려진 위험 설명을 현재 offline lexical 정책과 일치하도록 수정했다.
- 전체 테스트: **75 passed**, 경고 1건

### 14:51 — PM 승인 커밋과 최신 main 동기화

- PM이 변경 파일 11개의 범위와 전체 diff를 확인했다.
- `feat: add fraud scenario engine v0.1` 커밋을 생성했다.
- 개발 규칙 PR #1이 병합된 최신 `origin/main` 위로 rebase했다.
- rebase 후 커밋 SHA는 `a7bab2f126dbf3b0996d0268b2d84dcbe6acf58a`이다.
- rebase 후 전체 테스트 **75 passed**, Python compile, `git diff --check`를 다시 통과했다.

### 14:52 — 원격 push와 Draft PR 생성

- `feature/fraud-scenario-engine` 브랜치를 `origin`에 최초 push했다.
- `main` 대상 Draft PR #2를 생성했다.
- PR URL: `https://github.com/mosejong/finshield-ai/pull/2`
- GitHub 생성 시각: `2026-08-12T05:52:49Z` (`2026-08-12 14:52:49 KST`)
- PR 생성 직후 GitHub Actions CI가 시작됐다. 최종 결과는 PM이 별도로 확인한 뒤 Ready 전환과 병합 여부를 결정한다.

### 14:54 — GitHub Actions CI 통과

- 개발일지 기록 커밋 `0a13963a27180e6607179a07f132714277d586ae`를 push했다.
- push와 pull request 이벤트로 실행된 GitHub Actions `test` 2건이 모두 성공했다.
- 완료 시각은 각각 `2026-08-12 14:54:09 KST`, `2026-08-12 14:54:13 KST`이다.
- GitHub가 PR을 `MERGEABLE`로 판정했으며 PM의 로컬·원격 검증이 모두 완료됐다.

### 14:56 — Ready 전환 및 main 병합

- 최종 PR head `ec749efb85a0ba900a3a8e72057598d30d673f4d`에서 GitHub Actions `test` 2건이 다시 통과했다.
- Draft PR #2를 Ready for review로 전환했다.
- PM이 변경 파일 범위와 병합 가능 상태를 최종 확인한 뒤 `main`에 병합했다.
- 병합 시각: `2026-08-12T05:56:34Z` (`2026-08-12 14:56:34 KST`)
- 병합 커밋: `27a45e1d5f4c7eeab084397ec734f62299a318bc`

## 설계 흐름

1. `AnalyzeRequest`가 입력 길이, persona, 상태, URL 길이를 검증한다.
2. `detect_canonical_signals`가 텍스트와 URL의 보수적 offline lexical 특성에서 내부 구조화 신호를 추출한다.
3. `detect_legacy_signals`와 `baseline_score`가 기존 다섯 legacy 규칙만 정확한 기존 가중치로 합산하고 0~100으로 제한한다.
4. `classify_fraud_types`가 내부 canonical 신호 집합을 사기 유형 후보 목록으로 변환한다.
5. `determine_risk_level`이 legacy baseline, canonical 신호별 최소 위험도, 명시적인 고위험 신호 조합, 현재 상태의 최소 위험도를 결합한다.
6. `select_actions`가 내부 canonical 신호별 행동과 상태별 행동을 합치고 중복을 제거해 우선순위순으로 정렬한다.
7. `sources_for_actions`가 행동의 근거 무결성을 검증하고 실제 관련 출처만 선택한다.
8. `project_public_signals`가 내부 canonical 신호를 legacy 호환 code 우선의 의미상 중복 없는 응답 신호로 변환한다.
9. 서비스가 고정 템플릿 summary와 면책문구를 포함한 `AnalyzeResponse`를 생성한다.
10. route는 요청을 서비스에 전달하는 역할만 수행한다.

## 변경 파일

### 수정

- `app/api/routes/analysis.py`: route를 얇게 만들고 서비스 호출로 교체
- `app/core/risk_engine.py`: 기존 `analyze_rules`, `risk_level` 호환 유지
- `app/schemas/analysis.py`: 신규 응답 스키마 및 입력 URL 제한 추가

### 신규

- `app/data/fraud/official_sources.json`: 정적 공식 근거 8개
- `app/domain/fraud/signals.py`: 신호 탐지, legacy code 매핑, baseline 점수
- `app/domain/fraud/classification.py`: 사기 유형 후보 분류
- `app/domain/fraud/policy.py`: 상태별 위험도와 신호/상태별 행동 정책
- `app/domain/fraud/sources.py`: 정적 근거 로딩과 무결성 검증
- `app/services/fraud_analysis.py`: 분석 흐름 orchestration과 summary
- `tests/test_fraud_scenario.py`: Scenario Engine 골든·보안·호환 테스트
- `docs/devlog/2026-08-12/fraud-scenario-engine-v0.1.md`: 본 개발일지

## API 계약

### 요청

`POST /api/v1/analyze`

- `text`: 1~10,000자
- `persona`: `early_career | small_business | unknown`, 기본 `unknown`
- `state`: 후보 상태 7종, 기본 `received_only`
- `url`: 선택, 최대 2,048자. 서버가 방문하지 않으며 URL 존재 자체는 위험 신호가 아니다. 명백한 lexical 위험 특성만 오프라인으로 검사한다.

### 기존 응답 필드 유지

- `risk_score`: 0~100 legacy 규칙 baseline. 기존 다섯 규칙의 점수와 의미를 유지하며 확률이 아님
- `risk_level`: `low | medium | high`
- `signals`
- `scenario`
- `disclaimer`

### 신규 응답 필드

- `fraud_types`: 확정 판정이 아닌 유형 후보 목록
- `summary`: 입력과 상태에 따른 결정론적 템플릿 설명
- `actions`: `code`, `priority`, `title`, `reason`, `source_ids`
- `official_sources`: 실제 선택된 행동이 참조한 출처만 포함

기존 다섯 신호 개념은 호환을 위해 public `signals`에 legacy code 하나만 반환한다. 신규 전용 개념만 canonical code를 사용하며 내부 판단용 canonical 신호를 별도 필드로 노출하지 않는다. `risk_score`에는 legacy 규칙과 기존 가중치만 반영하며 신규 canonical 신호는 점수를 변경하지 않는다. URL이 있으면 summary에 외부 평판을 확인하지 않았다는 불확실성을 표시한다.

## 테스트 결과

- 실행 환경: Python 3.12.10, 기존 원본 저장소의 검증된 `.venv`를 읽기 전용으로 사용
- 최초 구현 `pytest -q`: 57 passed, 경고 1건
- 1차 PM 차단 이슈 수정 후 `pytest -q`: 73 passed, 경고 1건
- public signal projection 수정 후 최종 `pytest -q`: **75 passed**, 경고 1건
- Python compile: 통과
- `git diff --check`: 통과
- 경고: FastAPI `TestClient` 내부의 Starlette/httpx 사용 중단 예정 경고

백엔드 전용 worktree에는 `.venv`가 없었으므로 원본 저장소의 Python 3.12.10 가상환경 실행 파일을 사용했다. 테스트 대상 코드와 생성된 cache는 현재 백엔드 worktree이며 원본 저장소 파일은 수정하지 않았다.

## 보안·개인정보 검토

- LLM과 외부 모델 호출 없음
- 런타임 웹 검색 없음
- 사용자 URL outbound fetch 없음
- 사용자 URL은 길이 제한 후 링크 신호로만 처리
- 원문 또는 PII 저장·로그 기록 없음
- HTML 또는 script 실행·렌더링 없음
- 사용자가 입력한 텍스트는 지시문이 아니라 데이터로만 취급
- 범죄 확정, 법률상 유죄, 사용자 가담 여부를 생성하지 않음
- 공식 행동 근거는 코드와 정적 JSON의 무결성 검증을 통과해야 응답 가능

## 주요 결정

1. 위험 상태는 선형 단계가 아니다. 상태별 정책표를 사용한다.
2. `risk_score`와 `risk_level`의 역할을 분리한다. 전자는 정확한 legacy baseline, 후자는 canonical 신호와 상태 긴급성을 포함한 최종 등급이다.
3. 행동은 점수를 만들지 않는다. 분석 결과와 상태가 행동을 선택한다.
4. 정상 메시지는 행동과 공식 출처를 빈 목록으로 반환해 과도한 경고를 피한다.
5. 공식 출처 전체를 매번 노출하지 않고 실제 행동에 사용된 출처만 반환한다.
6. URL 평판 조회나 접속은 v0.1 범위에서 금지한다. URL 존재는 사기 판정 근거가 아니며 최소 보수 lexical 특성만 위험 신호로 사용한다.

## 알려진 위험과 후속 TODO

- 키워드 규칙과 가중치는 실험적 baseline이며 실제 데이터셋으로 precision, recall, F1, class별 recall, FPR을 측정해야 한다.
- 한국어 표현 변형, 오탈자, 맥락 부정, 인용문에 대한 오탐·미탐 가능성이 있다.
- `비밀번호는 누구에게도 알려주지 마세요` 같은 안전 경고문도 현재 keyword baseline에서는 `credential`로 잡힐 수 있다. 이는 알려진 negation/context 한계이며 이번 차단 이슈 수정에서 무리한 NLP 예외를 추가하지 않았다.
- `suspicious_link`는 비암호화 HTTP, localhost/IP literal, userinfo, shortener, punycode, malformed 구조 같은 최소 offline lexical 특성만 사용한다. 도메인 평판을 조회하지 않으며 URL의 안전성을 판정하거나 보증하지 않는다.
- 공식 출처의 내용·시행일·URL 변경을 본선 제출 전 재검증해야 한다.
- 정적 행동은 일반 안내이며 금융기관별 세부 절차와 법률 자문을 대신하지 않는다.
- persona별 행동 설명과 접근성 조정은 아직 적용하지 않았다.
- 설치 패키지 배포 시 JSON data file 포함 여부를 패키징 설정에서 확인해야 한다.
- Starlette `TestClient` 사용 중단 예정 경고는 별도 유지보수 작업으로 처리해야 한다.

## PM 관리 문서 변경 제안

`README.md`와 `docs/README.md`는 PM 관리 범위이므로 이번 브랜치에서 수정하지 않았다. PM 승인 후 다음 내용을 반영할 것을 제안한다.

- 루트 `README.md`: Fraud Scenario Engine v0.1 구현 상태, 신규 응답 필드, 정적 근거 기반 정책, 테스트 수 갱신
- `docs/README.md`: `docs/devlog/2026-08-12/fraud-scenario-engine-v0.1.md` 링크와 일별 개발일지 규칙 추가
- `docs/10-mvp-backlog.md`: Scenario Engine, 공식 근거 기반 설명, provenance/source 항목의 완료 여부를 PM 검수 후 갱신

## 커밋·PR 정보

- 기능 커밋: `a7bab2f126dbf3b0996d0268b2d84dcbe6acf58a`
- 커밋 메시지: `feat: add fraud scenario engine v0.1`
- push 브랜치: `feature/fraud-scenario-engine`
- Draft PR: `https://github.com/mosejong/finshield-ai/pull/2`
- PR 방향: `feature/fraud-scenario-engine` → `main`
- PR 생성: `2026-08-12 14:52:49 KST`
- 검증된 최종 PR head: `ec749efb85a0ba900a3a8e72057598d30d673f4d`
- 병합 커밋: `27a45e1d5f4c7eeab084397ec734f62299a318bc`
- 최종 상태: `main` 병합 완료
