# FinShield AI

> 금융 경험이 부족한 사용자가 AI로 고도화되는 금융 사회공학 공격과 금융범죄에 자신도 모르게 연루되는 위험을 사전에 발견하고, 상황별 안전 행동을 선택하도록 돕는 AI 금융 보안 코파일럿.

## Status

**MVP implementation — 2026-08-12**

목표 대회: **2026 금융 AI Challenge**  
Fraud Scenario Engine v0.1 백엔드가 `main`에 병합됐다. 현재 분석은 LLM이나
런타임 웹 검색 없이 결정론적 규칙, 사용자 상태, 정적 공식 근거로 동작한다.
Next.js 프론트엔드 MVP도 `main`에 병합되어 실제 분석 API의 위험 유형 후보,
요약, 행동과 공식 근거를 live로 표시한다.
공식 금융상품은 최신 활성 기준월 전체를 process-local TTL cache로 재사용하며,
요청 pagination은 같은 snapshot에서 처리한다. 다음 단계는 source identity 무결성과
보수적 중복 정책, goal 기반 filtering과 공식 상품 후보 UI까지 완료했다.
FinancialProfile CRUD v0.1도 백엔드에 추가되어 생성·단건 조회·전체 교체·삭제가
가능하다. 현재 profile 저장은 로컬 프로토타입용 process-local 방식이며 다음 단계는
PostgreSQL·인증 경계다. 온보딩·프로필 화면은 이 API와 연결됐고 브라우저에는
profile UUID와 fraud persona만 보관한다.

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
  clients/          fixed official-provider adapters
  core/             legacy-compatible risk interface
  data/fraud/       reviewed static official sources
  domain/fraud/     detection, classification, policy, provenance
  repositories/     process-local prototype persistence boundaries
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
web/                Next.js frontend MVP
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

공식 금융상품 live 조회를 사용하려면 공공데이터포털 활용신청 후 발급된
`일반 인증키`를 환경변수 `PUBLIC_DATA_SERVICE_KEY`에 그대로 설정한다. backend는
Encoding/Decoding 형식을 한 번 정규화한다. 실제 키는 저장소나 로그에 남기지
않는다. 키가 없으면 상품 API는 빈 목록 대신 503을 반환한다.

프론트엔드는 별도 터미널에서 실행한다.

```bash
cd web
npm install
npm run dev
```

Then open `http://localhost:3000`. 기본 live 모드는 실행 중인 FastAPI를 Next
서버사이드 프록시로 호출한다.

## Test

```bash
pytest -q
cd web
npm run build
npx tsc --noEmit
npm run lint
npm test
```

현재 `main` 기준: Python **139 passed**, frontend **13 passed**, Next build,
TypeScript와 lint 통과. Starlette `TestClient` 사용 중단 예정 경고 1건은 별도
유지보수 항목으로 관리한다.

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
`POST /api/v1/profiles`, 단건 `GET`, 전체 교체 `PUT`, `DELETE`로 검증된 profile을
재사용할 수 있다. 응답은 불투명 UUID와 UTC 생성·수정 시각을 포함하며 전체 목록
endpoint는 제공하지 않는다. 현재 저장소는 기본 최대 1,000개의 process-local
메모리 저장이므로 재시작·다중 worker에서 유지되지 않는다. UUID는 인증이 아니며,
인증·소유권 검증과 PostgreSQL 전환 전에는 공개 배포에 사용하면 안 된다.
프론트는 동일 오리진 Next proxy로 생성·조회·교체·삭제하고 profile 원문을
`sessionStorage`에 저장하지 않는다. backend enum과 UI 계약은 일치시키며 UI 전용
persona는 FinancialProfile 요청에서 제외한다.

`GET /api/v1/products`는 금융위원회 `서민금융상품기본정보`의 고정 HTTPS
endpoint를 호출하고 공식 응답을 내부 상품 계약으로 정규화한다. 금리·한도·기간과
자격조건은 원문 `*_text`로 보존하며 누락값을 추정하지 않는다. 응답에는 provider,
source product ID, 기준월, 조회 시각과 데이터셋 URL을 포함한다. 키 누락은 503,
기관·응답 스키마 오류는 502로 명시해 장애를 “적격 상품 없음”으로 오인하지 않는다.
2026-08-12 live 검증에서 HTTP 200, `NORMAL SERVICE.`, 전체 9,316건과 기준월
`202607`을 확인했다. 최신월 활성 상품은 325건이며 source ID 누락·중복은 없었다.
상품명만 같은 2건은 서로 다른 지역 보증재단 상품이므로 이름만으로 중복 제거하지
않는다. 금리 등 누락 필드는 추정하지 않으며, 상세 품질 기준은
`docs/15-product-catalog-live-profile.md`에 기록했다.

최신월 325건은 기본 300초 동안 process-local cache에서 재사용한다. 응답 최상위의
`source_base_month`와 `fetched_at`으로 빈 페이지에서도 기준월과 수집 시각을 확인할
수 있다. cache 만료 후 갱신 실패는 빈 목록이나 stale data로 숨기지 않고 502를
유지한다. 설정과 한계는 `docs/16-product-catalog-cache.md`에 기록했다.

snapshot 저장 전 공식 source ID와 provider·기준월·수집시각·source URL의
일관성을 검증한다. 동일 source ID는 전체 snapshot 오류로 처리하고, 이름만 같은
서로 다른 source ID는 병합하지 않는다. 응답의 `identity`가 적용 정책과 동명 그룹
수를 제공하며 상세 기준은 `docs/17-product-catalog-identity.md`에 기록했다.

`POST /api/v1/recommendations`는 FinancialProfile의 goal과 공식 `purpose_text`만
비교해 `potential_match`, `mismatch`, `needs_review`를 반환한다. 상세 자격은 항상
공식 원문과 취급기관 확인 대상으로 남기며 적격성·승인·금리를 보장하지 않는다.
`/products`는 backend에서 다시 읽은 profile의 goal 하나만 전송해 이 상태·근거와 공식 상품
원문을 표시한다. 소득·부채·신용·연령은 상품 요청으로 전송하지 않으며 프론트에서
적격성이나 금융 수치를 재계산하지 않는다.

## Next priorities

- 실제 데이터셋 기반 precision, recall, F1, class별 recall, FPR 측정
- 사회초년생과 소상공인 중 Primary Persona 확정
- 상품 상세·비교·What-if 화면과 대출 시뮬레이터 연결
- provider latency·error 계측
- FinancialProfile 기반 deterministic filtering 구현
- PostgreSQL·SQLAlchemy·Alembic 영구 저장과 인증·소유권 경계
- 상품 탐색·비교·What-if 화면 구현 및 대출 시뮬레이터 연결
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
