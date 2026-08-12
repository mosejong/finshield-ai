# FinShield AI

> 금융 경험이 부족한 사용자가 AI로 고도화되는 금융 사회공학 공격과 금융범죄에 자신도 모르게 연루되는 위험을 사전에 발견하고, 상황별 안전 행동을 선택하도록 돕는 AI 금융 보안 코파일럿.

## Status

**Planning / Research — 2026-08-11**

목표 대회: **2026 금융 AI Challenge**  
현재 방향은 확정안이 아니라 연구 가설이며, 공식 통계·기존 서비스·데이터 가용성을 검증한 뒤 MVP 범위를 확정한다.

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

## Repository

```text
app/
  api/routes/       API endpoints
  core/             risk/scenario engine
  schemas/          request/response schemas
docs/
  01-problem-definition.md
  02-research-plan.md
  03-product-scope.md
  04-architecture.md
  05-data-and-evaluation.md
  06-roadmap.md
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
pytest
```

## Backend v0.1 API

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

## Tomorrow first

**코딩보다 먼저 `docs/02-research-plan.md`의 근거 조사를 수행한다.**

특히:
- 사회초년생 vs 소상공인 중 어느 타깃의 문제가 더 강한가?
- 대포통장/계좌양도/구직·대출 사기의 실제 규모는?
- 생성형 AI가 금융 사회공학 공격을 어떻게 변화시키는가?
- 이미 금융권/KISA/보안업계가 해결한 기능은 무엇인가?
- 공개 학습/평가 데이터는 확보 가능한가?

조사 결과에 따라 MVP를 줄이거나 바꾼다.

## Verified official-data direction (2026-08-11)

MVP의 금융상품 정보는 공식 OpenAPI를 우선 사용한다.

- 금융위원회 `서민금융상품기본정보` — REST, JSON/XML, 실시간 업데이트
- 서민금융진흥원 `대출상품한눈에 정보 서비스` — REST, XML
- 서민금융진흥원 `서민대출상품 취급기관 정보 서비스` — 취급기관 연결

세부 설계는 `docs/07-official-api-candidates.md` 참고.

AI 보안은 공격자 측 AI 악용뿐 아니라 FinShield 자체의 prompt injection,
PII leakage, unsafe URL fetching, hallucinated financial guidance도 위협모델에 포함한다.
`docs/08-ai-security-alignment.md` 참고.
