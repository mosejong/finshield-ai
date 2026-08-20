# 기능명세서 — FinShield AI

**2026 금융 AI Challenge** 제출물 ②
기준 버전: `main` (2026-08-19) · 기획서: `docs/35-competition-proposal.md`

---

## 1. 문서 범위와 표기 규칙

이 문서는 **현재 저장소에 구현되어 동작하는 기능만** 기술한다. 계획 중인 기능은
13절에 분리해 적고, 본문 명세에 섞지 않는다.

- `구현 완료` — 코드·테스트가 있고 CI에서 검증된다
- `부분 구현` — 동작하지만 일부 데이터가 정적 fixture다
- 모든 API 경로는 `/api/v1` 접두사를 갖는다(health·internal 제외)
- 금액은 `Decimal`(소수점 2자리)로 다룬다. 부동소수 연산을 쓰지 않는다

## 2. 시스템 구성

```
  브라우저
     |  HTTPS
     v
  Caddy (자동 TLS)  ── 프론트엔드만 노출한다
     |
     v
  Next.js (App Router)
     |  서버 사이드 프록시 (/api/proxy/**)
     v
  FastAPI 백엔드  ──> PostgreSQL (필드 단위 인증 암호화)
     |
     +──> 금융위원회 공공데이터 API   (공식 금융상품)
     +──> Google AI Studio            (설명 문장 전용)
```

**백엔드는 외부에 직접 노출되지 않는다.** 브라우저는 항상 Next.js Route Handler를
거친다. 세션 쿠키가 same-origin으로 유지되고, 백엔드 주소가 클라이언트에 노출되지
않는다.

## 3. 공통 규약

### 3.1 인증·세션

| 항목 | 내용 |
|---|---|
| 방식 | 익명 세션. 아이디·비밀번호·이메일을 받지 않는다 |
| 발급 | `POST /api/v1/auth/session` |
| 저장 | 원문은 HttpOnly·SameSite=Strict 쿠키에만. DB에는 **SHA-256 해시만** |
| 소유권 | 모든 profile 접근은 세션 사용자 ID와 owner 일치를 검증 |
| 미소유 자원 | **404** 반환 (403이 아니다 — 존재 여부를 노출하지 않는다) |
| 종료 | `DELETE /api/v1/auth/session` (세션만) / `DELETE /api/v1/auth/account` (계정·전체 금융정보) |

**위험 분석(F-01)은 세션 없이 동작한다.** 의심 문자를 방금 받은 사람에게 가입을
요구하면 이탈한다. 프로필은 개인화 품질만 올리는 선택 요소다.

### 3.2 요청 한도 (IP 기준, 고정 창)

| 정책 | 대상 | 한도 |
|---|---|---|
| `auth_session` | `POST /auth/session` | 20 / 3600초 |
| `analyze_explanation` | `POST /analyze/explanation` | 10 / 60초 |
| `analyze` | `POST /analyze` | 30 / 60초 |
| `write` | `/api/v1/` POST·PUT·PATCH·DELETE | 60 / 60초 |
| `read` | `/api/v1/` 그 외 | 240 / 60초 |

초과 시 `429` + `Retry-After`. 요청 본문 상한은 기본 128KB, 초과 시 `413`.
설명 경로가 분석 경로보다 좁은 이유는 유료 외부 호출이 나가기 때문이다.

### 3.3 오류 응답

| 코드 | 상황 |
|---|---|
| 400 / 422 | 스키마 위반, 열거형 밖의 값 |
| 404 | 자원 없음 **또는 소유자가 아님** |
| 413 | 본문 크기 초과 |
| 429 | 요청 한도 초과 |
| 502 / 503 | 외부 공식 데이터 제공자 실패 (조용히 빈 값으로 대체하지 않는다) |

**외부 제공자 실패를 성공처럼 꾸미지 않는다.** 상품 데이터를 못 받으면 빈 목록이
아니라 오류를 낸다.

### 3.4 개인정보 원칙

수집하지 않는 항목: **주민등록번호, 은행 비밀번호, OTP, 카드 전체 정보, 불필요한
계좌번호.** 금융 프로필은 금액·구간·목표만 받는다.

### 3.5 고지 문구

분석·시뮬레이션·가이드 응답에는 확정적 판단이 아님을 알리는 `disclaimer`가 항상
포함된다. 화면에서도 생략할 수 없다.

## 4. 데이터 사전

### 4.1 위험 수준 (`risk_level`)

`low` · `medium` · `high`

### 4.2 사용자 상태 (`state` / `scenario`) — 7종

| 값 | 의미 | 최소 위험 |
|---|---|---|
| `received_only` | 받기만 함 | low |
| `clicked_link` | 링크를 눌렀음 | medium |
| `shared_personal_info` | 개인정보를 알려줬음 | medium |
| `shared_account_access` | 계좌·인증 접근권을 넘겼음 | **high** |
| `installed_app` | 앱을 설치했음 | **high** |
| `received_unknown_money` | 모르는 돈이 입금됐음 | **high** |
| `transferred_money` | 송금했음 | **high** |

### 4.3 위험 신호 — 12종

문구 규칙 11종: `urgency_pressure`, `authority_impersonation`, `secrecy_isolation`,
`loan_policy_offer`, `credential_request`, `account_access_request`,
`app_install_request`, `remote_control_request`, `money_transfer_request`,
`receive_and_forward_money`, `card_delivery_claim`

URL 형태 분석 1종: `suspicious_link`

### 4.4 사기 유형 (`fraud_types`) — 6종

| 유형 | 발생 조건 (신호) |
|---|---|
| `authority_impersonation` | `authority_impersonation` |
| `loan_policy_impersonation` | `loan_policy_offer` |
| `account_access_request` | `credential_request` 또는 `account_access_request` |
| `money_mule_transfer` | `receive_and_forward_money` |
| `smishing_malware` | `suspicious_link`·`app_install_request`·`remote_control_request` 중 하나 |
| `card_delivery_impersonation` | `card_delivery_claim` |

### 4.5 대응 행동 (`actions[].code`) — 11종

`STOP_CONTACT`, `DO_NOT_CLICK`, `DO_NOT_INSTALL`, `DO_NOT_SHARE_ACCESS`,
`DO_NOT_FORWARD_MONEY`, `VERIFY_OFFICIAL_CHANNEL`, `CONTACT_FINANCIAL_INSTITUTION`,
`CONTACT_1394`, `CONTACT_112`, `CONTACT_KISA_118`, `PRESERVE_EVIDENCE`

각 행동은 `priority` 1~3을 가지며, **반드시 하나 이상의 `source_ids`를 갖는다.**

### 4.6 공식 근거 — 8건

| source_id | 기관 |
|---|---|
| `fsec_finance_ai_challenge`, `fsec_ai_strategy` | 금융보안원 |
| `police_1394`, `police_ecrm_victim_help` | 경찰청 / 보이스피싱 통합신고대응센터 |
| `kisa_118`, `kisa_smishing` | KISA |
| `electronic_financial_transactions_act` | 전자금융거래법 제6조 |
| `fraud_refund_act` | 전기통신금융사기 피해 방지 및 피해금 환급에 관한 특별법 |

각 근거는 `retrieved_at`(수집일)을 갖고, 응답에 그대로 실린다.

---

## 5. F-01 의심 메시지 위험 분석

| | |
|---|---|
| **상태** | 구현 완료 |
| **API** | `POST /api/v1/analyze` |
| **화면** | `/check` (입력), `/check/result/[id]` (결과) |
| **인증** | 불필요 |
| **LLM** | **호출하지 않음** |

### 5.1 사용자 스토리

> 의심스러운 문자를 받은 사용자로서, 이것이 위험한지와 **지금 무엇을 해야 하는지**를
> 근거와 함께 알고 싶다.

### 5.2 입력

| 필드 | 타입 | 제약 | 기본값 |
|---|---|---|---|
| `text` | string | 1~10,000자 | 필수 |
| `persona` | enum | `early_career` / `small_business` / `unknown` | `unknown` |
| `state` | enum | 4.2의 7종 | `received_only` |
| `url` | string \| null | 최대 2,048자 | `null` |

### 5.3 처리 규칙

```
1. 정규화        casefold
2. 신호 탐지     SIGNAL_RULES 부분 문자열 매칭 (11종)
                 + URL 형태 분석 (suspicious_link)
3. 안전 문맥 억제 예방 안내문이면 해당 신호를 끈다 (5.4)
4. 사기 유형     4.4 표에 따라 결정
5. 위험 수준     아래 네 값의 최댓값
                   a. 점수 밴드      (35점 이상 medium, 70점 이상 high)
                   b. 신호별 최소 위험
                   c. 고위험 신호 조합
                   d. 사용자 상태별 최소 위험 (4.2)
6. 행동 선택     신호별 행동 ∪ 상태별 행동, priority 정렬
7. 근거 연결     각 행동의 source_ids를 공식 근거 카탈로그와 대조
```

**5번의 `max`가 이 기능의 핵심이다.** 문구가 평범해도 이미 계좌 접근권을 넘긴
사용자는 항상 `high`가 된다.

### 5.4 안전 문맥 억제

예방 안내문을 경고로 올리면 사용자가 경고 자체를 무시하게 된다. 두 종류의 억제가
있다.

1. **명시적 부정형** — "OTP는 절대 알려주지 마세요", "출처 불명 앱은 설치하지 마세요",
   "모르는 파일은 내려받지 마세요"
2. **공식 창구 확인 안내** — "공식 누리집에서 확인하세요"처럼 공식 확인을 권하면서
   읽는 사람에게 **아무것도 요구하지 않는** 문장은, 기관명·상품명만으로 켜지는
   신호(`authority_impersonation`, `loan_policy_offer`)를 끈다

**두 억제 모두 요구 문구가 하나라도 있으면 적용되지 않는다.** "OTP는 알려주지
마세요. 하지만 본인 확인을 위해 인증번호를 답장해 주세요"는 억제되지 않는다.
이 두 방향은 테스트로 고정돼 있다.

### 5.5 출력

| 필드 | 설명 |
|---|---|
| `risk_score` | 0~100 |
| `risk_level` | `low` / `medium` / `high` |
| `signals[]` | `code`, `label`, `weight` |
| `fraud_types[]` | 4.4의 6종 중 해당하는 것 |
| `scenario` | 판정에 사용된 사용자 상태 |
| `summary` | 한 문장 요약 |
| `actions[]` | `code`, `priority`, `title`, `reason`, `source_ids[]` |
| `official_sources[]` | `source_id`, `organization`, `title`, `source_url`, `retrieved_at`, `supports[]` |
| `disclaimer` | 확정 판단이 아님을 알리는 고지 |

### 5.6 무결성 검증 (실패 시 예외)

- 알 수 없는 `source_id`를 참조하는 행동 → `ValueError`
- 해당 행동을 지지하지 않는 근거를 참조 → `ValueError`
- 응답의 `official_sources`는 실제 참조된 ID 집합과 **정확히 일치**해야 한다

즉 **근거 없는 조언은 응답에 실릴 수 없다.**

### 5.7 화면 표시 순서 (고정)

```
위험 수준 → 감지된 위험 신호 → 왜 위험한지 → 사용자가 이미 무엇을 했는지
  → 지금 해야 할 행동 → 공식 근거 → (접힘) 분석 상세 → 고지
```

위험 점수 숫자는 **첫 화면에 노출하지 않는다.** 문장이 항상 먼저다. 위험색은 좌측
바·아이콘·텍스트·연한 배경까지만 쓰고 빨강 전면 배경을 쓰지 않는다.

### 5.8 예외

| 상황 | 동작 |
|---|---|
| `text` 빈 문자열 / 10,000자 초과 | 422 |
| 열거형 밖의 `state`·`persona` | 422 |
| 요청 한도 초과 | 429 + `Retry-After` |
| 본문 128KB 초과 | 413 |

**사용자가 준 URL을 서버가 가져오지 않는다.** 형태 분석만 한다.

---

## 6. F-02 AI 설명 생성

| | |
|---|---|
| **상태** | 구현 완료 |
| **API** | `POST /api/v1/analyze/explanation` |
| **화면** | `/check/result/[id]` 내 설명 영역 |
| **LLM** | 사용 |

### 6.1 처리 규칙

입력은 **이미 확정된 `AnalyzeResponse`** 다. 함수 서명이
`explain_analysis(AnalyzeResponse) -> str | None` 이므로 모델은 위험 수준·사기
유형·행동을 구조적으로 바꿀 수 없다.

| 항목 | 값 |
|---|---|
| 프로바이더 | Google AI Studio |
| 주 모델 | `gemini-3.6-flash` |
| 대체 모델 | `gemini-3.1-flash-lite` |
| temperature | 0.0 |
| 프롬프트 | `fraud_explanation` — sha256을 상수로 고정, 테스트가 검증 |

프롬프트를 한 글자라도 고치면 해시가 어긋나 테스트가 깨진다. **모델·프롬프트를
조용히 바꾸는 일이 불가능하다.**

### 6.2 출력 검증

모델 출력은 아래를 전부 통과해야 사용자에게 도달한다.

- 비어 있지 않을 것
- 길이 상한 이내
- **URL을 새로 만들어 내지 않을 것**
- 주민등록번호 형태를 포함하지 않을 것
- 판정에 없던 연락처를 만들어 내지 않을 것

### 6.3 실패 처리

| 상황 | 동작 |
|---|---|
| 프로바이더 장애·타임아웃 | 설명 없이 **판정만** 반환 |
| 출력 검증 실패 | 설명 없이 **판정만** 반환 |
| 주 모델 실패 | 대체 모델 1회 재시도 |

**설명이 없는 것보다 틀린 설명이 나쁘다.** 판정은 항상 살아남는다.

### 6.4 측정된 지연

61건 실측 기준 p50 2.21초, p95 5.41초. 판정(밀리초)과 분리돼 있으므로 사용자는
설명을 기다리지 않고 위험 수준과 행동을 먼저 볼 수 있다.

---

## 7. F-03 공식 금융상품 조회·상세·비교

| | |
|---|---|
| **상태** | 구현 완료 |
| **API** | `GET /products`, `GET /products/{source_product_id}`, `POST /products/compare` |
| **화면** | `/products`, `/products/[id]`, `/products/compare` |
| **출처** | 금융위원회 공공데이터포털 (서민금융 대출상품, dataset 15094787) |

### 7.1 처리 규칙

- **최신 활성 기준월** 전체를 process-local TTL 캐시로 재사용한다. 요청 pagination은
  같은 snapshot 안에서 처리하므로, 페이지를 넘기는 도중 데이터가 바뀌지 않는다
- `source_base_month`(YYYYMM)를 응답에 실어 **어느 시점 데이터인지** 밝힌다
- source identity 무결성 검증: 동일 상품이 서로 다른 식별자로 중복 등재되는 것을
  보수적으로 거부한다
- 비교는 **2건**으로 제한한다. 화면에서 의미 있게 대조할 수 있는 최대치다

### 7.2 예외

제공자 오류·인증키 문제·형식 위반은 각각 구분된 예외로 올린다. **빈 목록으로
대체하지 않는다.**

---

## 8. F-04 금융 프로필과 파생지표

| | |
|---|---|
| **상태** | 구현 완료 |
| **API** | `POST /profiles`, `GET /profiles/{id}`, `PUT /profiles/{id}`, `DELETE /profiles/{id}`, `GET /profiles/{id}/metrics` |
| **화면** | `/onboarding`, `/profile` |
| **인증** | 필요 (소유권 검증) |

### 8.1 입력 (주요 필드)

| 그룹 | 필드 |
|---|---|
| 인적 | `age_band`, `employment_status`, `household_size`, `dependents_count`, `marital_status?`, `region?` |
| 현금흐름 | `monthly_net_income`, `monthly_fixed_expenses`, `monthly_variable_expenses` |
| 자산 | `liquid_assets`, `emergency_fund_target_months` |
| 부채 | `total_debt`, `monthly_debt_payment`, `loan_items[]` (최대 100건) |
| 신용·사업 | `credit_score_band`, `business_owner`, `business_age_months?`, `annual_business_revenue_band?` |
| 목표 | `goal` |

`loan_items[]`는 `category`, `balance`, `annual_rate`, `remaining_months`,
`repayment_type`을 갖는다. **계좌번호·카드번호를 받지 않는다.**

### 8.2 파생지표 (3종, 백엔드 결정론 계산)

| 지표 | 정의 |
|---|---|
| 월 가처분 현금흐름 | 순소득 − 고정지출 − 변동지출 − 월 부채상환 |
| 월소득 대비 상환액 비율 | 월 부채상환 ÷ 월 순소득 (%) |
| 비상자금 커버 기간 | 유동자산 ÷ 필수 월지출 (개월) |

응답에는 계산값과 함께 `assumptions[]`(최소 3개)와 `disclaimer`가 항상 포함된다.

**용어를 쓰지 않는다.** 화면에서는 "소득 대비 빚 부담", "매달 쓸 수 있는 돈"으로
표시하고, 공식 DSR과 다르다는 점을 명시한다.

### 8.3 저장과 삭제

- 프로필 필드는 **인증 암호화**해 저장한다. 암호화 키가 없으면 앱이 기동을 거부한다
- `DELETE /profiles/{id}` — 프로필 1건 삭제
- `DELETE /auth/account` — 익명 계정과 **모든 금융정보** 삭제
- 만료 세션·프로필은 dry-run 기본의 운영 명령으로 정리하며, 식별자나 금융 원문을
  로그에 남기지 않는다

### 8.4 프론트엔드가 계산하지 않는다

금융 계산·적격성 판정 로직은 `web/` 어디에도 없다. 프론트엔드는 완성된 값의 **표시**
만 담당한다.

---

## 9. F-05 대출 조건 시뮬레이션

| | |
|---|---|
| **상태** | 구현 완료 |
| **API** | `POST /loans/simulate` |
| **화면** | `/products/simulate` |

### 9.1 입력

`principal`(> 0), `annual_interest_rate`(0~100), `months`(1~600), `repayment_type`

### 9.2 출력

`monthly_payment`, `schedule[]`(월별 원금·이자·상환액·잔액), `total_repayment`,
`total_interest`, `assumptions[]`

계산은 순수 함수이며 `Decimal`로 수행한다. **LLM을 사용하지 않는다.** 이 값은
개별 금융회사의 실제 산정과 다를 수 있음을 `assumptions`에 명시한다.

---

## 10. F-06 목표 기반 상품 후보 제시

| | |
|---|---|
| **상태** | 구현 완료 |
| **API** | `POST /recommendations` |
| **화면** | `/products` |

`goal` 하나만 입력받아 공식 상품 목록을 **보수적으로** 분류한다.

| 상태 | 의미 |
|---|---|
| `potential_match` | 목적이 부합할 가능성 |
| `mismatch` | 목적 불일치 |
| `needs_review` | 자동 판정하지 않는다 — **사람이 확인해야 한다** |

각 결과는 `reasons[]`를 갖고, 각 이유는 판단 근거가 된 **원본 필드**
(`purpose_text` 또는 `eligibility`)를 밝힌다.

**적격성을 확정하지 않는다.** 자격 요건은 `needs_review`로 넘긴다 — 이 서비스가
대출 승인 여부를 판정할 근거를 갖고 있지 않기 때문이다.

---

## 11. F-07 재테크 기초 가이드 · F-08 PWA · F-09 운영 기능

### F-07 재테크 기초 가이드 (구현 완료)

`GET /guidance/wealth` · 화면 `/learn/wealth`. 공식 근거에 연결된 기초 가이드를
제공한다. 개별 상품 추천이나 수익률 예측을 하지 않는다.

### F-08 PWA·공유 시트 (구현 완료)

- 앱 설치 유도, 오프라인 셸 (`/offline`)
- **POST 공유 타깃** — 문자 앱에서 "공유"로 의심 메시지를 바로 넘길 수 있다.
  사기 문자를 받은 순간 복사·붙여넣기 단계를 없애는 것이 목적이다

### F-09 상태·관측 (구현 완료)

| 경로 | 용도 |
|---|---|
| `GET /health`, `/health/live`, `/health/ready` | 상태 확인. readiness는 DB·설정을 실제로 검사 |
| `GET /internal/metrics` | route별 요청 수·latency histogram (Prometheus text, OpenAPI 비공개) |

**로그에는 카운트와 성공/실패만 남긴다.** 사용자 식별자, 세션 ID, 프로필 ID, 금융
원문을 기록하지 않으며 이 경계는 회귀 테스트로 지킨다.

---

## 11-2. F-10 전세보증금 위험 점검 (구현 완료)

`POST /api/v1/housing/deposit-risk` · 화면 `/check/deposit`. 세션·프로필을
요구하지 않고 입력값을 저장하지 않는다. 외부 호출과 LLM 을 쓰지 않는다.

**로그인 없이 쓴다.** 계약을 앞둔 사람에게 회원가입을 먼저 요구하지 않는다.
프록시(`web/app/api/proxy/housing/deposit-risk`)도 세션 쿠키를 넘기지 않는다.
진입 경로는 두 곳 — Home "지금 확인할 것" 항목과 `/check` 하단 링크다. 후자를
폼 **아래**에 두는 이유는, 방금 사기 문자를 받은 사람의 경로를 전세 도구가
가로막지 않게 하기 위해서다.

| 입력 | 내용 |
|---|---|
| `stage` | 계약 단계 6종 (계약 전 / 계약금 / 잔금·입주 / 전입신고·확정일자 / 종료 예정 / 미반환) |
| `deposit_krw`, `property_price_krw`, `senior_lien_krw` | 금액. 모르는 값은 비운다 |
| `completed_checks` | 이미 마친 확인 5종 |
| `move_in_reported_on` | 전입신고일 |

주민등록번호·계좌번호·주소·임대인 이름은 받지 않는다.

| 출력 | 내용 |
|---|---|
| `risk_level` | low / medium / high. **점수는 만들지 않는다** — 가중치를 조정할 실측 데이터가 아직 없다 |
| `ratio` | 부채비율 `(선순위 채권최고액 + 보증금) ÷ 주택가격 × 100`, `Decimal` 소수 한 자리 |
| `protection` | 대항력 발생일, 대항요건·우선변제권 요건 충족 여부 |
| `signals` | 신호 10종 |
| `actions` | 행동 8종. 전부 공식 근거 id 를 갖는다 |
| `official_sources` | 국가법령정보센터·법제처·주택도시보증공사 6건 |

**구간 이름은 이 서비스의 보수적 기준이며 공식 기준이 아니다.** 어떤 기관도
60%·80% 를 고시하지 않았다. 응답의 `ratio.band_is_service_rule`, 신호 문장,
`disclaimer` 세 곳에 같은 사실을 남긴다.

**모르는 값은 0 으로 채우지 않는다.** 선순위 채권최고액을 0 으로 두면 비율이
실제보다 낮게 나와, 등기부를 안 본 사람에게 가장 안전해 보이는 숫자를 준다.

대항력 발생일만 날짜로 돌려준다 — 주택임대차보호법 제3조 제1항의 "그 다음
날부터" 를 그대로 옮긴 것이다. 우선변제권은 요건 충족 여부만 돌려준다. 취득
시점을 날짜로 단정하려면 법문에 없는 해석이 필요하기 때문이다.

화면은 금액을 **만원 단위**로 받는다. 사회초년생이 0 을 아홉 개 세지 않게
하려는 것이고, ×10,000 은 단위 환산이지 금융 계산이 아니다. 빈 칸은 0 이 아니라
`null` 로 보낸다 — 프론트에서도 모르는 값을 0 으로 채우지 않는다.

설계 근거는 `docs/37-housing-deposit-risk.md`.

---

## 12. 비기능 요구사항

### 12.1 보안

| 항목 | 적용 |
|---|---|
| 전송 | HTTPS, 자동 TLS |
| 헤더 | HTTP 보안 헤더 적용 |
| CSRF | 동일 출처 상태 변경 검증 |
| 호스트 | 신뢰 호스트 제한 |
| SSRF | **사용자 URL을 서버가 가져오지 않는다** |
| 인젝션 | 판정 경로가 LLM을 부르지 않음 + 설명 출력 검증 |
| 저장 | 프로필 필드 단위 인증 암호화, 세션은 해시만 |
| 백업 | 암호화 백업, 세대 회전, **복호화까지 확인하는** 복원 리허설 |
| 의존성 | 해시 고정 lock, CI drift 차단 |

### 12.2 성능 (측정값)

| 항목 | 값 |
|---|---|
| 판정 API (in-process ASGI, 1,220 샘플) | p50 2.222ms / p95 3.565ms |
| 설명 LLM 호출 (61건 실측) | p50 2.21초 / p95 5.41초 |

**이 수치는 개발기 측정이며 배포 SLO가 아니다.** 네트워크·TLS·프록시·동시 사용자를
포함하지 않는다.

### 12.3 정확도 (합성 개발셋 61건)

| 항목 | Scenario Engine |
|---|---|
| 위험/안전 이진 판정 Precision / Recall / F1 | 1.000000 / 1.000000 / 1.000000 |
| FPR | 0.000000 |
| 필수 신호 coverage | 0.981132 |
| 필수 행동 coverage | 1.000000 |
| 상태 정책 정확도 | 1.000000 |
| 공식 근거 coverage | 1.000000 |

**만점인 것은 이진 판정뿐이다.** 사기 유형 분류는 만점이 아니다 —
`loan_policy_impersonation` F1 0.909091(recall 0.833333),
`money_mule_transfer` F1 0.923077(precision 0.857143). 즉 "위험하다"는 판단은
개발셋에서 전부 맞혔지만 **유형 이름을 붙이는 데서는 여전히 틀린다.**

그리고 **이 만점은 성능 주장이 아니다.** 같은 데이터로 규칙을 교정했으므로 독립
held-out 성능이 아니며, 오류가 0건이 됐다는 것은 **개발셋이 더 이상 변별하지
못한다**는 뜻이다. 근거와 해석은 `docs/32-fraud-evaluation-benchmark.md`.

### 12.4 접근성

본문 건너뛰기, 공통 포커스 링, 로딩·비동기 상태 안내, 움직임 축소 설정 존중,
구조적 회귀 테스트. 375 / 768 / 1280 뷰포트 검수 완료. 터치 타깃 최소 44px.

정량 명도대비 AA 측정과 실제 스크린리더 검수는 미완이다.

### 12.5 표현 규칙 (강제)

- 위험을 공포로 표현하지 않는다 — 해골·사이렌 아이콘, 경고 애니메이션, 빨강 전면
  배경 금지
- 단정하지 않는다 — "당신은 사기 피해자입니다"(X) / "이 요청은 정상 절차에 없는
  요구입니다"(O)
- 점수를 문장보다 먼저 보여주지 않는다
- 전문용어를 쓰지 않는다 (DSR → "소득 대비 빚 부담", 가처분소득 → "매달 쓸 수 있는 돈")

### 12.6 품질 게이트

`pytest -q` **648 passed, 2 skipped.** 프론트엔드 `vitest` **137 passed.** CI는 매 push마다 테스트, 사기 판정 품질
게이트, 의존성 해시 검사, 프론트엔드 빌드·타입·린트·테스트, 컨테이너 런타임 검증을
수행한다. 품질 게이트는 **낡은 평가 결과를 자동으로 거부**한다.

---

## 13. 미구현·제한 사항

명세에 넣지 않은 것을 분명히 적는다.

### 13.1 아직 정적 fixture인 부분

| 항목 | 현재 |
|---|---|
| 위험 신호별 "왜 위험한가" 설명 문구 | 신호 코드별 정적 한국어 문구 (`web/lib/mock/analysis.ts`) |
| `/check/result/demo` 데모 결과 | 정적 예시. 실제 분석 결과는 백엔드 live |
| 프로필 입력 전 예시 화면 | 정적 fixture (`web/lib/api/home.ts`). 실제 Home 금융상태는 live |

**위험 판정·행동·근거·금융 계산은 전부 live 백엔드 값이다.**

**F-10 전세보증금 위험 점검에는 위험 점수가 없다.** 다른 판정과 달리 실측
평가셋이 없어서 `risk_level` 만 돌려주고 숫자를 만들지 않는다. 부채비율
60%·80% 구간 역시 이 서비스가 정한 보수적 기준이며 공식 기준이 아니다.

### 13.2 측정하지 않은 것

- 설명 문장 자체의 품질 (근거 이탈률, 안전 필터 차단율)
- 프롬프트 인젝션 시도 성공률
- 실제 배포 환경의 latency·오류율 (TLS·프록시·동시성 포함)
- 정량 접근성 AA 대비

### 13.3 구현하지 않은 기능

URL 도메인·평판 조회(외부 호출 정책 선행), 음성 통화·STT 대응, 스크린샷·피싱
페이지 분석, 계정 단위 감사 로그, 고급 개인화.

### 13.4 명시적 비목표

이 서비스는 **금융 자문·법률 자문이 아니며, 사기 여부를 확정하지 않는다.**
공격용 기능(피싱 생성, 자격증명 탈취, 탐지 회피)은 어떤 형태로도 구현하지 않는다.

---

## 14. 근거 문서

| 내용 | 경로 |
|---|---|
| 기획서 (제출물 ①) | `docs/35-competition-proposal.md` |
| 심사 증거 묶음 | `docs/33-competition-evidence-pack.md` |
| 평가 방법·결과 | `docs/32-fraud-evaluation-benchmark.md` |
| LLM 설명 계층 설계 | `docs/34-llm-explanation-runtime.md` |
| 보안 위협 모델 | `docs/12-security-threat-model.md` |
| 전세보증금 위험 점검 설계 | `docs/37-housing-deposit-risk.md` |
| 아키텍처 | `docs/04-architecture.md` |
| 프론트엔드 아키텍처 | `docs/13-frontend-architecture.md` |
| 운영 준비도 | `docs/28-production-readiness.md` |
| 설계 결정 기록 | `docs/adr/` |
| 시간순 개발·리뷰 | `docs/devlog/` |
