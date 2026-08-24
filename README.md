# FinShield AI

> 금융 경험이 부족한 사용자가 AI로 고도화되는 금융 사회공학 공격과 금융범죄에 자신도 모르게 연루되는 위험을 사전에 발견하고, 상황별 안전 행동을 선택하도록 돕는 AI 금융 보안 코파일럿.

## Status

**MVP implementation — 2026-08-19**

목표 대회: **2026 금융 AI Challenge**  
대회 제출물은 `docs/35-competition-proposal.md`(①기획서)와
`docs/36-functional-specification.md`(②기능명세서)에 있다.
Fraud Scenario Engine 백엔드가 `main`에 병합됐다. **판정 경로는 LLM이나 런타임
웹 검색 없이** 결정론적 규칙, 사용자 상태, 정적 공식 근거로만 동작한다. LLM은
별도 엔드포인트에서 **이미 확정된 판정을 설명하는 문장만** 만들며, 실패하면 설명
없이 판정만 나간다.
Next.js 프론트엔드 MVP도 `main`에 병합되어 실제 분석 API의 위험 유형 후보,
요약, 행동과 공식 근거를 live로 표시한다.
공식 금융상품은 최신 활성 기준월 전체를 process-local TTL cache로 재사용하며,
요청 pagination은 같은 snapshot에서 처리한다. source identity 무결성, 보수적 중복
정책, goal 기반 filtering, 공식 상품 후보·상세·2개 비교 UI까지 완료했다.
FinancialProfile CRUD v0.1도 백엔드에 추가되어 생성·단건 조회·전체 교체·삭제가
가능하다. SQLAlchemy 2.x·Alembic 저장 경계와 FinancialProfile 전체 인증 암호화를
추가했다. 배포 환경은 PostgreSQL+psycopg와 암호화 키가 없거나 migration이 누락되면
시작을 거부한다. development·test에서 설정이 없을 때만 process-local 저장으로
동작한다. 개인정보를 추가 수집하지 않는 익명 세션 인증과 profile 소유권 검증도 적용했다. 세션 원문은
HttpOnly·SameSite Strict 쿠키에만 두고 DB에는 SHA-256 해시만 저장한다. 모든 profile CRUD와 metrics는
세션 사용자 ID가 owner와 일치해야 하며 다른 사용자의 UUID 접근은 404로 숨긴다. 온보딩·프로필 화면은
Next same-origin 프록시로 세션을 자동 준비하며 브라우저에는 profile UUID와 fraud persona만 보관한다.
사용자는 profile 1건 삭제와 익명 계정·모든 금융정보 삭제를 구분해 실행할 수 있다. 활성 세션이 없는
익명 사용자와 소유 profile은 dry-run 기본 운영 명령으로 집계·정리하며 식별자나 금융 원문을 로그에
남기지 않는다.
월 현금흐름·월소득 대비 상환액·비상자금
기간도 backend에서 결정론적으로 계산해 profile과 Home에 같은 값으로 표시한다.
Fraud evaluation은 팀이 직접 작성한 합성 61건으로 legacy 5-keyword baseline,
Scenario Engine, LLM-only를 재현 가능하게 비교한다. 고정 model·prompt·provider
계약으로 LLM 단독 판정을 유료 측정했고(F1 0.975000, 필수 행동 coverage 0.600000,
상태 정책 정확도 0.508197, 공식 근거 coverage 0.0), **탐지만 보면 최초 측정에서
모델이 우리 엔진보다 나았다.** 모델이 못 채운 것은 "그래서 지금 뭘 해야 하는가"와
"그 근거가 어디 있는가"였다. 모델이 찾아 준 오답은 판정 로직이 아니라 어휘 구멍이
원인이었으므로, 모델을 판정에 넣는 대신 규칙 어휘를 넓혔다(v0.2). 그 뒤 이 개발셋
기준 Scenario Engine의 이진 판정은 precision·recall·F1 1.000000, FPR 0.000000이고
action-source 근거 연결 coverage는 1.0이다. **이 만점은 성능 주장이 아니다** —
같은 데이터로 규칙을 교정했으므로 독립 held-out 성능이 아니고, 오류가 0건이 된 것은
개발셋이 더 이상 변별하지 못한다는 뜻이다. 사기 유형 분류는 여전히 만점이 아니다
(`loan_policy_impersonation` F1 0.909091, `money_mule_transfer` F1 0.923077).
상세 결과와 주장 한계는 `docs/32-fraud-evaluation-benchmark.md`와
`docs/33-competition-evidence-pack.md`를 따른다.

**성능 수치는 독립 held-out 쪽을 본다.** 가장 최근은 v1.2(80건)이며, 아래 결함을
**고치기 전에** 얼려 커밋했다(`6635129` → `284aeba`, 순서는 `git log`에서 확인된다).

**진짜 기관도 문자를 보낸다.** 열한 회차 동안 이 셋들은 사칭 문장만 모아 왔고, 그래서
"기관명이 나오면 요구가 없어도 켠다"는 무조건 층이 **한 번도 값을 치르지 않았다.**
경찰청·검찰청·법원·금감원이 실제로 보내는 통지문 열두 건을 처음으로 같은 자리에 놓자
**여덟 건이 사칭으로 읽혔다.**

**갈리는 것은 기관명이 아니라 창구다.** 진짜 기관은 읽는 사람이 이 문자 없이도 갈 수
있는 창구를 댄다 — 경찰청은 이파인을, 검찰청은 형사사법포털을, 법원은 민원실을,
금감원은 파인과 1332 를. 창구를 대는 것은 **읽는 사람을 메시지 밖으로 내보내는 행위**다.
사칭은 그러지 못한다. 대는 순간 읽는 사람이 거기로 가서 거짓이 드러나기 때문이다.

그래서 사칭은 둘 중 하나를 한다 — **창구를 주지 않거나**("담당 조사관이 곧 연락드릴
예정이니 대기해 주십시오"), **진짜 창구를 밀어내려고만 댄다**("홈택스 말고 저희 전용
시스템으로만", "1332는 지금 연결이 안 되니"). v1.2 는 이 대비를 80건 안에 짝지어
넣었다. 사칭 어휘는 양쪽이 거의 같고, 갈리는 자리는 창구 하나다.

| 지표 | 수정 전 | 수정 후 |
|---|---|---|
| f1 / precision / recall | 0.4384 / 0.6154 / 0.3404 | 0.7532 / 0.9667 / 0.6170 |
| 오탐률 (FPR) | 0.3030 | 0.0303 |
| 미탐 / 오탐 | 31건 / 10건 | 18건 / 1건 |
| 필수 signal coverage | 0.3860 | 0.6842 |
| 필수 행동 coverage | 0.5050 | 0.6931 |
| 등급 천장 정확도 | 0.9394 | 1.0000 |
| 상태 정책 정확도 | 0.6500 | 0.8125 |
| 금지 행동 회피 | 0.9072 | 1.0000 |

**수정 후 f1 0.7532 를 현장 추정치로 읽으면 안 된다.** 사기 47건 중 18건이 이번 회차가
손대지 않기로 한 자리를 겨냥한다. 유형별로 움직인 것은 둘뿐이고(`isolation_coercion`
0.2222 → 0.9677, `authority_impersonation` 0.3077 → 0.7273) **나머지 여덟 유형은 한
자리도 움직이지 않았다** — 그 여덟이 정확히 어휘 공백이라 귀속이 깨끗하다.

**창구를 대는 것과 창구를 닫는 것은 반대 방향이다.** 창구 이름은 억제의 표지인데, 그
표지를 그대로 갖추고 부정만 덧붙이는 어형이 실제로 있다. 억제 규칙을 노리는 가장 싼
우회다. `fh-1052` 는 `공식 홈페이지` 라는 낱말 하나로 모든 신호를 껐는데, 문장이 하는
말은 정확히 그 반대였다("공식 홈페이지에는 아직 반영되지 않은 건입니다").

**창구를 화자 하나로 좁히는 것은 고립 요구다.** 고립 어휘는 `저와만 연락` 같은 어형 몇
개뿐이었는데 실제 어형은 훨씬 흔한 자리에 있다 — 화자를 가리키는 말에 배타 조사가
붙는다("이 번호로만", "담당자를 통해서만"). **진짜 기관은 자기를 유일한 통로로 만들지
않는다.** 그럴 필요가 없기 때문이다.

**억제와 탐지가 같은 표지를 공유하면 억제가 먼저 도는 한 탐지는 그 자리를 영원히 못
본다.** "저희 담당 창구에서만 가능합니다" 는 창구 어휘·조사·동사를 다 갖춰서 창구 안내
절로 세어졌고, 안내로 세어진 절은 다음 규칙이 볼 문장에서 빠진다. 같은 어형이 두
판정에서 반대로 작동하므로, 독점 어형을 만나면 그 절을 안내에서 **실격**시킨다.

**`외부에` 는 금지의 대상으로 가른다.** 고립이 막는 것은 **이 연락 자체**이고(이 건·이
통화·저희가 안내드린 절차), 기밀 유지가 막는 것은 **읽는 사람이 이미 쥔 것**이다(초안·
합격 사실·협의 내용·감사 내용). 어미도 함께 잠근다 — **금지여야 한다, 보장은 금지가
아니다**("상담 내용은 외부에 공개되지 않습니다"는 읽는 사람에게 아무것도 요구하지 않는다).
**남겨 두는 집단이 있으면 고립이 아니다** — "팀원들 외에는 아무에게도" 는 전칭 금지
어휘를 갖췄지만 읽는 사람 곁에 남는 사람이 있다.

**상태는 신호를 대신하지 않는다.** 예측에 없던 결함이 하나 나왔다. 신호가 하나도 없는
정상 문장이 상태만으로 `STOP_CONTACT` 를 받아 **회사와·병원과·거래처와 연락을 끊으라는
말**이 나갔다. 상태 표의 나머지 행동은 전부 읽는 사람 쪽에서 끝나는데 `STOP_CONTACT` 만
방향이 반대라 **상대가 적이라는 판단이 먼저** 있어야 하고, 상태는 읽는 사람이 무엇을
했는지만 말한다. 등급 바닥은 건드리지 않았다 — **재는 것은 등급이 아니라 행동이다.**

**한 건짜리 오탐이 무엇의 표본인지는 그 셋만으로 알 수 없다.** v1.1 의 유일한
오탐(`fh-942`, 진짜 경찰 통지문)은 그 회차에 이름만 적히고 넘어갔다. 열두 건을 같은
자리에 놓자 잡음이 아니라 **층 전체의 구멍**이었다. 그 한 건을 고치는 데 80건짜리 셋
하나가 필요했고, 고치자 v1.1 의 f1 이 0.7647 → **0.8286** 이 됐다.

**얼린 셋은 어느 방향으로도 맞춰 쓰지 않는다.** 이번 수정으로 v0.3·v0.4 의 상태 정책
정확도가 내려갔다(0.9333 → 0.8167, 0.8667 → 0.7333). 그 셋들의 **정상** 15건이 상태만으로
`STOP_CONTACT` 를 요구하기 때문이고, 13건은 그 셋의 기준으로 봐도 틀렸다. 나머지
둘(`fh-211`·`fh-228`)은 틀리지 않았고 **이번 수정으로 잃는다** — 피해자의 1인칭 서술이라
어떤 신호도 켜지지 않는다. 라벨을 고치지 않고 떨어진 점수를 결과 파일에 그대로 남겼다.
`policy.py` 에 적힌 **"뒤에 적힌 판단을 따른다"** 로 v1.2 를 따랐고, **두 방향을 다 적어
두는 것이 그 규칙의 값이다.**

**측정할 수 없는 수정은 고친 것이 아니라 옮긴 것이다.** 창구 없는 기관 사칭 네
건(`fh-1013`~`fh-1016`)은 어형이 분명하고 규칙도 썼다가 커밋하지 않았다 — 그 값을 치를
정상 문장이 이 셋에 없기 때문이다. 실제 세계에는 있다("접수되었습니다. 담당자가 확인 후
연락드리겠습니다"). 다음 셋이 그 자리를 먼저 만들어야 한다. 남은 미탐 14건은 순수한
어휘 공백이고, 재는 셋 안의 결함을 고치면 그 셋은 성능이 아니라 기억을 재게 된다.

전세보증금 위험 점검 v0.1을 추가했다(`POST /api/v1/housing/deposit-risk` ·
화면 `/check/deposit`).
공모전이 아니라 **사회초년생이 실제로 가장 큰 금액을 잃는 자리**를 보고 고른
기능이다. 부채비율 `(선순위 채권최고액 + 보증금) ÷ 주택가격` 은 `Decimal`
산술이고 대항력 발생일은 주택임대차보호법 제3조 제1항의 "그 다음 날부터" 를
그대로 옮긴 날짜 덧셈이다 — **이 기능에는 LLM 이 개입하는 지점이 없다.**
위험 구간 60%·80%는 **이 서비스가 정한 보수적 기준이며 공식 기준이 아니고**,
그 사실을 응답 필드·신호 문장·고지 세 곳에 남긴다. 선순위 채권최고액을 모르면
0으로 채우지 않고 계산을 포기한다 — 0으로 두면 등기부를 안 본 사람에게 가장
안전해 보이는 숫자가 나오기 때문이다. 공식 근거 9건은 국가법령정보센터·법제처·
주택도시보증공사에서 직접 열어 확인한 것만 넣었다.
확인 항목에 **임대인의 미납 국세·지방세 열람**이 들어 있다. 국세징수법 제109조·
지방세징수법 제6조가 정한 신청 기간(임대차가 시작되는 날까지) 안의 단계에서만
안내한다 — 할 수 없는 일을 하라고 하면 목록 전체가 소음이 된다. 임대인 동의
없이 열람할 수 있는 보증금 기준액은 시행령을 확인하지 못해 **숫자를 쓰지 않고**
법문의 "대통령령으로 정하는 금액" 표현을 그대로 둔다.
화면은 **로그인 없이** 쓴다 — 계약을 앞둔 사람에게 회원가입을 먼저 요구하지
않는다. 금액은 만원 단위로 받되 빈 칸은 0이 아니라 `null`로 보내서, 모르는 값을
0으로 채우지 않는 규칙이 브라우저를 지나는 동안에도 유지되게 했다.
서버 시각도 이 작업에서 KST로 모았다(`app/core/clock.py`) — 컨테이너는 UTC로
돌기 때문에 하루 9시간 동안 오늘 한 전입신고가 "미래"로 거부되고, 오늘자 출처가
무결성 검사에 걸려 앱 기동을 막았다.
설계는 `docs/37-housing-deposit-risk.md`.
프론트 접근성 v0.1은 본문 건너뛰기, 공통 포커스 링, 로딩·비동기 상태 안내,
움직임 축소 설정과 구조적 회귀 테스트를 포함한다. PM 브라우저 검수에서
375·768·1280 다크 화면의 가로 overflow·nav 전환과 스킵 링크의 main 포커스를
확인했다. 실제 스크린리더·정량 AA 대비·라이트 모드·iOS Safari는 후속 검수다.

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
  db/               SQLAlchemy models and session configuration
  repositories/     encrypted/profile persistence boundaries
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
migrations/         Alembic database migrations
web/                Next.js frontend MVP
.github/workflows/
```

## Run

### 로컬 Python/Node 개발

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install --require-hashes -r requirements-dev.txt
uvicorn app.main:app --reload
```

Then open `/docs`.

### 의존성

원본은 `requirements.in`(런타임)과 `requirements-dev.in`(개발·CI)이고,
`requirements*.txt`는 해시가 박힌 생성물이다. `.txt`를 직접 고치지 않는다.

| 파일 | 쓰는 곳 |
|---|---|
| `requirements.txt` | 컨테이너 이미지, `container-runtime` CI job |
| `requirements-dev.txt` | 로컬 개발, `test`·`deps-lock` CI job |

lock은 `--universal`로 만들어 Windows·Linux·macOS가 한 파일을 공유한다.
플랫폼별 패키지는 marker로 갈린다 (`uvloop`은 non-win32, `colorama`는 win32).

의존성을 바꾸려면 `.in`을 고친 뒤 재생성한다.

```bash
uv pip compile requirements.in     --universal --generate-hashes --python-version 3.12 -o requirements.txt
uv pip compile requirements-dev.in --universal --generate-hashes --python-version 3.12 -o requirements-dev.txt
```

`--upgrade` 없이는 기존 pin을 유지하므로 재생성해도 무관한 패키지가 따라
올라가지 않는다. 버전을 올릴 때만 `--upgrade` 또는 `--upgrade-package <이름>`을
붙인다. `.in`만 고치고 lock을 갱신하지 않으면 `deps-lock` CI job이 막는다.

암호화 DB 저장을 사용하려면 `DATABASE_URL`과 `PROFILE_ENCRYPTION_KEYS`를 함께 설정하고
서버 시작 전에 `alembic upgrade head`를 실행한다. development·test는 SQLite 검증이
가능하지만 staging·production은 `postgresql+psycopg://`만 허용한다. 키 생성·순환,
migration, 삭제·backup 경계는 `docs/22-profile-persistence-encryption.md`를 따른다.

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

### Docker·PostgreSQL 통합 실행

Docker Desktop이 실행 중인 환경에서는 PostgreSQL, migration, FastAPI 2 workers와 Next standalone을
한 스택으로 검증할 수 있다.

```powershell
Copy-Item .env.docker.example .env.docker
.\.venv\Scripts\python.exe scripts\create_local_docker_secrets.py
docker compose --env-file .env.docker up --detach --build
.\.venv\Scripts\python.exe scripts\verify_compose_runtime.py
```

기본 주소는 backend `http://127.0.0.1:18000`, web `http://127.0.0.1:13000`이다. DB port와 secret은
host에 공개하지 않는다. 로컬 HTTP와 공개 HTTPS 환경의 차이, backup/restore 검증과 안전한 종료 방법은
`docs/25-docker-postgres-runtime.md`를 따른다.

## Test

```bash
pytest -q
python -m scripts.evaluate_fraud_engine --check
cd web
npm run build
npx tsc --noEmit
npm run lint
npm test
```

현재 검증 수치는 각 PR의 개발일지와 CI를 기준으로 갱신한다. Python 전체 테스트,
fraud quality gate, frontend test·production build·typecheck·lint를 각각 실행한다.
Starlette `TestClient` 사용 중단 예정 경고 1건은 별도 유지보수 항목으로 관리한다.

## Backend v0.1 API

`POST /api/v1/analyze`는 입력 문구와 사용자가 이미 취한 행동을 바탕으로
다음의 결정론적 흐름을 수행한다.

`risk signals → fraud types → UserState → risk level → actions → official sources`

기존 `risk_score`, `risk_level`, `signals`, `scenario`, `disclaimer` 필드를
유지하면서 `fraud_types`, `summary`, `actions`, `official_sources`를 추가했다.
기존 다섯 신호 코드와 점수 규칙도 그대로 유지한다. URL은 외부로 요청하지
않으며 비암호화 HTTP, localhost/IP literal, userinfo, shortener, punycode,
malformed 구조 같은 최소 lexical 특성만 오프라인으로 검사한다.

`POST /api/v1/analyze/explanation`은 같은 입력을 받아 **판정을 문장으로 옮긴
설명만** 돌려준다. 판정에 붙이지 않고 나눈 이유는 두 가지다. 설명 한 문단에
약 8초가 걸려(2026-08-19 실측) 판정 표시가 그만큼 늦어지고, 판정 응답이
설명을 품으면 "설명이 없으면 판정도 없다"는 상태가 구조적으로 가능해진다.
이 엔드포인트는 클라이언트가 보낸 판정을 설명하지 않는다 — 원문만 받아
서버가 `analyze_fraud`를 다시 돌린 결과만 설명한다. 설명 계층이 꺼져 있으면
오류가 아니라 `available: false`로 답한다. 상세는
`docs/34-llm-explanation-runtime.md`.

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
`POST/GET/DELETE /api/v1/auth/session`은 이름·이메일·전화번호 없이 익명 세션을
생성·확인·폐기한다. 32-byte 불투명 토큰 원문은 HttpOnly 쿠키에만 두고 DB에는
SHA-256 해시를 저장한다. 기본 만료는 30일이며 배포 환경에서는 Secure 쿠키를 강제한다.
`DELETE /api/v1/auth/account`는 현재 익명 사용자, 모든 세션과 소유 FinancialProfile을
삭제한다. 만료 데이터 정리 명령은 기본 dry-run이며 명시적 `--execute`에서만 활성 세션이
없는 익명 사용자와 profile을 cascade 삭제한다. 상세 경계는
`docs/24-anonymous-data-lifecycle.md`에 기록했다.
`POST /api/v1/profiles`, 단건 `GET`, 전체 교체 `PUT`, `DELETE`로 검증된 profile을
재사용할 수 있다. 응답은 불투명 UUID와 UTC 생성·수정 시각을 포함하며 전체 목록
endpoint는 제공하지 않는다. 현재 저장소는 기본 최대 1,000개의 process-local
메모리 fallback 또는 설정된 SQLAlchemy DB를 사용한다. DB mode는 profile 전체를
Fernet 인증 암호화하고 암호문을 profile UUID에 결합해 변조·row swap을 거부한다.
배포 환경은 PostgreSQL과 Alembic migration을 강제한다. UUID는 인증으로 사용하지
않고 모든 query에서 현재 세션의 익명 사용자 ID와 `owner_user_id`를 함께 검증한다.
프론트는 동일 오리진 Next proxy로 생성·조회·교체·삭제하고 profile 원문을
`sessionStorage`에 저장하지 않는다. backend enum과 UI 계약은 일치시키며 UI 전용
persona는 FinancialProfile 요청에서 제외한다.

`GET /api/v1/profiles/{profile_id}/metrics`는 저장된 profile을 다시 읽어 월 현금흐름,
월소득 대비 부채상환액, 비상자금 기간과 목표 부족액을 Decimal로 계산한다. 비율과
기간은 소수 첫째 자리 `ROUND_HALF_UP`을 사용하고, 월소득이나 생활비 분모가 0원이면
0%·무한대로 추정하지 않고 `null`과 `계산 불가`를 반환한다. 상환 비율은 공식 DSR이
아니며 임의의 좋음·나쁨 임계값을 적용하지 않는다. `/profile`과 Home은 계산식 없이
backend 표시값·가정·주의문을 사용한다. 계산 결과는 별도 저장하지 않고 추가 개인정보도
수집하지 않는다. 상세 계약은 `docs/21-profile-derived-metrics.md`에 기록했다.

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

`GET /api/v1/products/{source_product_id}`와 `POST /api/v1/products/compare`는 최신
활성 snapshot의 공식 상품 1개 또는 서로 다른 상품 정확히 2개를 반환한다. 비교는
snapshot을 한 번만 읽어 provider·기준월·수집시각을 고정하고 요청 순서를 보존한다.
하나라도 없으면 부분 성공 대신 404를 반환하며 옛 ID를 새 상품으로 추정 매핑하지 않는다.
`/products/[id]`와 `/products/compare`는 금리·한도·상환·지원조건 원문을 표시하고,
비어 있는 값은 `확인 필요`로 남긴다. 금리 우열·적격성·승인 가능성은 판정하지 않는다.
상세 계약과 검증 경계는 `docs/20-product-detail-comparison.md`에 기록했다.

`/products/simulate`는 같은 원금·기간·상환방식에 현재 금리와 변경 금리를 넣어
backend 시뮬레이션 결과를 나란히 표시한다. 원리금균등은 정기 월 납입액,
원금균등은 첫 달과 마지막 달 납입액을 구분해 보여준다. 브라우저는 이자·차액·
절감액을 계산하지 않으며 두 요청 중 하나라도 실패하면 비교 전체 실패를 명시한다.
결과는 공식 상환표가 아니고 수수료·세금·보험료·중도상환수수료를 포함하지 않는다.

`GET /api/v1/guidance/wealth`와 `/learn/wealth`는 재테크에 관심 있는 사용자가
상품 선택 전에 돈의 흐름, 목표·저축, 부채·신용, 투자 위험을 순서대로 학습하는
기초 가이드다. 입력 없이 versioned 정적 계약을 반환하며 6개 공식 자료의 URL,
검토일, module 지지 관계를 검증한다. 계좌·보유종목·거래내역을 수집하지 않고
특정 상품·종목·매매 시점·수익률을 추천하거나 투자 가능 여부를 판정하지 않는다.

## Next priorities

관측성 v0.1은 개인정보 안전 JSON 요청 로그, route별 latency histogram, request ID, liveness/readiness 분리까지 구현했다. 금융 원문·프로필 값·세션·인증 헤더는 기록하지 않으며 실제 Docker 로그 비노출 검증은 `docs/27-observability-pii-masking.md`를 따른다.

보안 경계 v0.1이 적용되었다. 브라우저·API 보안 헤더, 쿠키 기반 상태 변경 요청의 same-origin 검사, production trusted host fail-closed, loopback 내부 포트, Caddy HTTPS 공개 구성을 포함한다. 실제 공개 완료에는 도메인·DNS·인증서 외부 검증이 남아 있다. 운영법과 제한은 `docs/26-http-security-https.md`를 따른다.

요청 한도와 본문 크기 제한이 적용되었다. 식별자는 client IP 단독이며(세션은 공격자가 스스로 발급할 수 있어 한도를 무력화한다), 카운터는 IP를 그대로 담지 않도록 HMAC 버킷 키로 PostgreSQL에 저장한다. 초과 시 `429` + `Retry-After`를 돌려주고, 프론트는 그것을 "안전하다"가 아니라 "아직 확인되지 않았다"로 표현한다. 본문 상한은 스키마 검증 이전에 backend와 web 양쪽에서 적용된다. 신뢰 proxy 홉 수는 기본 0(헤더 불신)이며 배포에서 명시해야 한다. 설계 판단과 검증 결과는 `docs/28-production-readiness.md` 2절 P0-1을 따른다.

만료 데이터 정리가 자동 실행된다. compose의 `retention` 서비스가 만료 세션·소유 프로필·닫힌 rate limit window를 주기적으로 지운다(기본 1시간). 성공한 실행만 heartbeat를 갱신하고 healthcheck가 그 나이를 보므로, 계속 실패하는 상태가 정상으로 보이지 않는다. 로그에는 건수와 성공 여부만 남기고 예외 메시지조차 남기지 않는다 — SQLAlchemy가 바인딩 값을 메시지에 붙이기 때문이다. 운영법은 `docs/24-anonymous-data-lifecycle.md`, 설계 판단은 `docs/28-production-readiness.md` 2절 P0-2를 따른다.

백업이 자동 실행되고, 복원 리허설의 합격 기준은 "복호화됐다"이다. compose의 `backup` 서비스가 주기적으로 `pg_dump`를 뜨고(기본 하루) 세대를 회전하며, 새 dump마다 `pg_restore --list`로 읽히는지 확인한 뒤에만 파일을 확정한다. 프로필은 애플리케이션 레벨로 암호화되어 있어 **DB만 복원하고 키를 잃으면 백업은 쓸모가 없다** — 기존 CI 검사("알려진 금융 값이 평문으로 안 보인다")는 무작위 바이트열도 통과시켰다. `scripts/rehearse_backup_restore.py`는 임시 DB로 복원한 뒤 프로필을 실제로 복호화해야 통과하고, 키가 없으면 어느 세대 key id가 없는지 짚어준다. 복구 절차와 한계는 `docs/29-backup-and-recovery.md`, 설계 판단은 `docs/28-production-readiness.md` 2절 P0-3을 따른다.

PWA로 설치되고 문자 앱 공유 시트에서 바로 들어온다. manifest의 `share_target`은 **GET이 아니라 POST**다. 사용자가 공유하는 값은 본인이 받은 문자 원문이라, 쿼리스트링으로 받으면 브라우저 주소 기록·액세스 로그·`Referer`에 원문이 그대로 복사되어 로그 allowlist(`docs/27`, `adr/0004`)가 무의미해진다. 받은 값은 실행되지 않는 JSON 태그에 담아 sessionStorage를 거쳐 `/check`에 채워 넣고 자동 분석하지는 않는다 — "이미 하신 행동"은 사용자만 안다. 서비스 워커는 화면 HTML과 `/api/*`를 캐시하지 않고 공유 POST에 개입하지 않으며, 캐시에 남는 것은 해시 붙은 자산·아이콘·오프라인 안내뿐이다. 오프라인 화면은 "확인하지 못했다는 것이 안전하다는 뜻은 아닙니다"를 먼저 말한다. 설계 판단과 검증은 `docs/30-pwa-and-share-target.md`를 따른다. 실기기 공유 시트 확인은 실도메인(P0-4) 이후로 남아 있다.

붙여넣은 문자는 데이터로 취급된다. `docs/12`가 요구하던 instruction-data separation이 코드에 없어서, 사용자가 붙여넣은 원문이 고정 프롬프트의 `{message}` 자리에 그대로 들어가고 있었다. 이제 `app/services/llm/untrusted.py`가 **모델을 수신자로 하는 문장만** 자리표시자로 바꾼다 — "지금 바로 안전계좌로 송금하세요" 같은 사기 명령문은 공격이 아니라 **설명이 딛고 설 증거**라서 바이트 단위로 그대로 통과해야 하고, 사기 골든셋 61건 전문이 그 경계를 테스트로 고정한다. 정화는 **판정 이후**에 일어나므로 입력 필터가 위험 등급을 낮추는 경로는 구조적으로 없다. 두 계층 모두 프롬프트가 아니라 치환되는 값을 고쳐서 고정 프롬프트 sha256은 불변이고, 따라서 기존 유료 벤치마크를 다시 돌리지 않는다. 주입 골든셋 7건(`evaluation/data/injection_golden_v0.1.jsonl`)은 첫 실행에서 구멍 3개를 찾아냈다. **방어를 끄고 실제로 던진 유료 측정에서는 `gemini-3.6-flash`가 7건 중 0건 넘어갔다** — 이 계층은 관측된 사고의 수정이 아니라 다층 방어의 한 겹이다. 정작 위험했던 것은 공격이 아니라 출력 검증의 첫 판이었고, 서술어만 보던 그 판은 실제 모델이 낸 정당한 경고 8건 중 4건을 거부했다(지금은 0건). 병합 후 코덱스 검토가 결함 2건을 더 짚었고 재현 과정에서 2건이 더 나왔다 — 서술어 목록을 우회하는 안심 문구, **마침표 없는 문자가 통째로 지워지던 문제**(한국어 문자는 부호 없이 종결어미로 끝나는 것이 보통이다), 줄바꿈으로 패턴을 가르는 우회, 자리표시자 뒤에 남던 지시문. 좁히기를 문장→절→구간 3단계로 바꿨고 "좁히다 흘리지 않는다"를 불변식으로 고정했다. 기록은 `docs/devlog/2026-08-20/prompt-injection-boundary.md`.

공개 배포는 도메인만 남았다. ACME 계정 연락처를 필수로 두어(비면 Caddy가 기동을 거부한다) 인증서 갱신이 조용히 실패해도 발급기관이 알릴 통로가 있게 했고, 첫 발급은 Let's Encrypt staging으로 예행연습한다 — 운영 디렉터리는 검증 실패 5회/시간·중복 인증서 5장/주로 막히는데 **한도를 태운 사실은 준비가 끝난 뒤에 알게 된다.** staging을 환경변수가 아니라 mount되는 파일로 둔 이유는 `acme_ca`를 명시하면 기본 발급자 두 개(Let's Encrypt + ZeroSSL 대체)가 모두 하나로 대체되기 때문이다. `scripts/verify_public_deployment.py`가 외부에서 리다이렉트·HSTS·보안 헤더·인증서 만료·주요 화면·공유 시트·내부 포트를 확인하고, 판정 기준 자체는 `tests/test_public_deployment.py`가 네트워크 없이 고정한다. `localhost` 예행연습으로 경로 전체를 확인했다. 절차와 완료 기준은 `docs/31-public-deployment.md`를 따른다.

- **독립 작성·동결한 held-out fraud golden v0.2 평가** — 개발셋이 변별력을 잃었으므로
  이제 이것이 추가 측정의 전제 조건이다
- 설명 문장 자체의 품질 측정 (근거 이탈률, 안전 필터 차단율) — 프롬프트 인젝션
  내성은 2026-08-20 에 측정했다(아래 문단)
- 사회초년생과 소상공인 중 Primary Persona 확정
- provider latency·error 계측
- FinancialProfile 기반 deterministic filtering 구현
- 익명 계정 전환·복구와 다중 기기 정책
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
