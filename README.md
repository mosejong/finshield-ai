# FinShield AI

> 금융 경험이 부족한 사용자가 AI로 고도화되는 금융 사회공학 공격과 금융범죄에 자신도 모르게 연루되는 위험을 사전에 발견하고, 상황별 안전 행동을 선택하도록 돕는 AI 금융 보안 코파일럿.

## Status

**MVP implementation — 2026-08-12**

목표 대회: **2026 금융 AI Challenge**  
Fraud Scenario Engine v0.1 백엔드가 `main`에 병합됐다. 현재 분석은 LLM이나
런타임 웹 검색 없이 결정론적 규칙, 사용자 상태, 정적 공식 근거로 동작한다.
프론트엔드 MVP는 `feature/frontend-mvp` 브랜치에서 별도로 개발 중이다.

## Problem

금융사기 대응 서비스는 보통 이미 알려진 전화번호·URL 또는 사기 문구 탐지에 집중한다.

FinShield AI는 다음 질문에서 시작한다.

> 금융 경험이 부족한 사람이 금융사기의 피해자가 되는 것뿐 아니라,
> 계좌·카드·인증정보 등을 넘겨 자신도 모르게 금융범죄에 연루되는 순간까지
> 사전에 위험을 설명하고 막을 수 있을까?

### Candidate personas

1. **사회초년생**
   - 취업/알바 사칭
   - 급여계좌 사칭
   - 대출·전세·청년지원 사칭
   - 계좌/체크카드/OTP 전달 요구
2. **소상공인**
   - 정책자금 사칭
   - 사업자대출 사칭
   - 세무사/거래처 사칭
   - 정산·세금계산서·첨부파일 기반 피싱

최종 Primary Persona는 데이터 조사 후 결정한다.

## Core hypothesis

단순한 `AI-generated text detector`를 만들지 않는다.

위험을 네 축으로 분석한다.

- **Content** — 긴급성, 금전 요구, 개인정보 요구, 사회공학 표현
- **Context** — 사용자 상황과 요청의 정합성
- **Behavior** — 송금, 계좌 제공, 앱 설치, 인증정보 전달 등 요구 행동
- **Infrastructure** — URL/domain/redirect 등 기술적 위험 신호

분석 결과는 다음 흐름으로 연결한다.

`Detect → Explain → Act`

## Tentative architecture

```text
Text / Message / URL / (later: Audio)
               |
        Input Processing
               |
       Feature Extraction
       /       |        \
 Content    Context   Infrastructure
       \       |        /
        Fraud/Risk Engine
               |
         Scenario Engine
               |
       Evidence Retrieval
               |
        LLM Explanation
               |
      Personalized Action
```

LLM은 최종 금융·법률 판단자가 아니다. 가능한 범위에서 규칙/모델/검증된 근거가 위험 신호와 대응 절차를 결정하고, LLM은 설명과 상호작용을 담당한다.

## MVP candidate

사용자가 의심스러운 메시지를 입력하면:

1. 위험 신호 추출
2. 위험 유형 분류
3. 위험 점수 및 근거 표시
4. 사용자가 이미 수행한 행동 확인
5. 현재 단계에 맞는 안전 행동 체크리스트 제공
6. 공식 근거 출처 표시

현재 백엔드 v0.1은 위 흐름을 `POST /api/v1/analyze`로 제공한다. 결과는 범죄
확정이나 법률 판단이 아니라 비교·의사결정을 돕는 위험 유형 후보와 행동
안내다.

## Repository

```text
app/
  api/routes/       API endpoints
  core/             legacy-compatible risk interface
  data/fraud/       reviewed static official sources
  domain/fraud/     detection, classification, policy, provenance
  schemas/          request/response schemas
  services/         application orchestration
docs/
  01-problem-definition.md
  02-research-plan.md
  03-product-scope.md
  04-architecture.md
  05-data-and-evaluation.md
  06-roadmap.md
  devlog/           date- and branch-based development history
tests/
.github/workflows/
```

## Run

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open `/docs`.

## Test

```bash
pytest -q
```

현재 `main` 기준: **75 passed**. Starlette `TestClient` 사용 중단 예정 경고 1건은
별도 유지보수 항목으로 관리한다.

## Backend v0.1 API

`POST /api/v1/analyze`는 입력 문구와 사용자가 이미 취한 행동을 바탕으로
다음의 결정론적 흐름을 수행한다.

`risk signals → fraud types → UserState → risk level → actions → official sources`

기존 `risk_score`, `risk_level`, `signals`, `scenario`, `disclaimer` 필드를
유지하면서 `fraud_types`, `summary`, `actions`, `official_sources`를 추가했다.
기존 다섯 신호 코드와 점수 규칙도 그대로 유지한다. URL은 외부로 요청하지
않으며 비암호화 HTTP, localhost/IP literal, userinfo, shortener, punycode,
malformed 구조 같은 최소 lexical 특성만 오프라인으로 검사한다.

`POST /api/v1/loans/simulate`는 LLM 없이 원리금균등상환 또는
원금균등상환 월별 일정을 계산한다. 월 단위 명목금리(`연이율 / 12`)를
사용하며, 금액은 소수 둘째 자리에서 `ROUND_HALF_UP`으로 처리하고 마지막
회차에 잔여 원금을 조정한다. 실제 금융기관의 일수 계산, 납입일, 거치기간은
아직 지원하지 않으므로 공식 상환표가 아닌 비교·의사결정 지원용
시뮬레이션이다. 응답의 `assumptions`에는 월 이율 기준과 제외 비용이 명시된다.

TODO: 현재 최대 600개월의 전체 schedule을 반환한다. 실제 사용량을 측정한 뒤
응답 크기 최적화가 필요한지 검토하되, pagination 또는 summary-only 정책은
별도 API 설계로 결정한다.

FinancialProfile의 최소 입력 스키마는 `app/schemas/financial_profile.py`에
정의되어 있으며, 정의되지 않은 필드와 민감정보 입력을 허용하지 않는다.

## Next priorities

- 프론트엔드 MVP 브랜치 검수 및 API 계약 통합
- 실제 데이터셋 기반 precision, recall, F1, class별 recall, FPR 측정
- 사회초년생과 소상공인 중 Primary Persona 확정
- 공식 금융상품 API adapter와 deterministic filtering 구현
- Starlette `TestClient` 사용 중단 예정 경고 대응

## Verified official-data direction (2026-08-11)

MVP의 금융상품 정보는 공식 OpenAPI를 우선 사용한다.

- 금융위원회 `서민금융상품기본정보` — REST, JSON/XML, 실시간 업데이트
- 서민금융진흥원 `대출상품한눈에 정보 서비스` — REST, XML
- 서민금융진흥원 `서민대출상품 취급기관 정보 서비스` — 취급기관 연결

세부 설계는 `docs/07-official-api-candidates.md` 참고.

AI 보안은 공격자 측 AI 악용뿐 아니라 FinShield 자체의 prompt injection,
PII leakage, unsafe URL fetching, hallucinated financial guidance도 위협모델에 포함한다.
`docs/08-ai-security-alignment.md` 참고.
