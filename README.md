# FinShield AI

> 사회초년생을 위한 **금융 사기 판별 · 공식 근거 기반 행동 안내** 서비스.
> 위험 판정은 결정론 규칙 엔진이 확정하고, **LLM 은 확정된 판정을 설명만 한다.**
> 금융위원회 공공데이터를 출처로 붙여, "이게 사기인가"에서 끝내지 않고
> "지금 무엇을 해야 하는가"까지 한 화면에서 답한다.

### 🔗 Live Demo — <https://finshield-ai.duckdns.org>

**공개 URL 로 배포·운영 중** (`v0.9.2` · GCP · Docker Compose · HTTPS).
심사·데모용 공개 인스턴스이며, 실사용자 트래픽 지표는 없다.

**2026 금융 AI Challenge 출품작** — 2026-09-06 제출, **심사 진행 중**.

[![CI](https://github.com/mosejong/finshield-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/mosejong/finshield-ai/actions/workflows/ci.yml)

| | |
|---|---|
| 백엔드 | Python 3.12 · FastAPI · PostgreSQL |
| 프론트엔드 | Next.js 16 · React 19 · TypeScript |
| 자동화 테스트 | 백엔드 **1,294건** · 프론트엔드 **155건** (GitHub Actions CI) |
| 사기 탐지 | held-out 865건 **F1 0.983** · 판정 지연 **p95 3.9ms** |
| 설계 문서 | [docs/](docs/) 38편 |

---

## 무엇을 하는가

| 기능군 | 하는 일 |
|---|---|
| **① 의심 문자 위험 판정** | 붙여넣은 문자를 결정론 규칙 엔진이 분석해 위험도 · 사기 유형 · 근거 신호를 낸다. 이 경로에는 **LLM 도 런타임 웹 검색도 없다.** |
| **② 판정 설명 생성** | 이미 확정된 판정을 사회초년생이 읽을 문장으로 바꾼다. 생성에 실패하면 설명 없이 판정만 나간다 — 설명이 없다고 판정이 멈추지 않는다. |
| **③ 공식 금융상품 조회 · 상세 · 비교** | 금융위원회 공공데이터에서 받아온 상품만 보여준다. **출처와 기준월이 없는 상품·금리는 화면에 나오지 않는다.** |
| **④ 금융 상태와 조건 시뮬레이션** | 금융 프로필 CRUD 와 파생지표, 대출 조건 시뮬레이션, 목표 기반 상품 후보, 전세보증금 위험 점검. 금융 계산은 전부 **백엔드 결정론 코드**가 한다. |
| **⑤ 기초 가이드와 진입 경로** | 공식 금융교육 근거에 기반한 재테크 기초 가이드. PWA 설치와 문자 앱 공유 시트에서의 직접 진입을 지원한다. |

---

## 왜 이렇게 만들었는가

같은 데이터로 **LLM 단독** 구성을 대조군으로 돌렸다. 탐지만 보면 LLM 이 나쁘지
않았다 — F1 **0.975**. 실패는 다른 데서 났다.

- **공식 근거 coverage 0.000** — 근거를 붙이라고 시켜도 붙이지 못하거나 지어냈다.
- **필수 행동 coverage 0.600** — 지급정지·신고처럼 빠지면 안 되는 행동의 40%를 빠뜨렸다.

금융에서 이 둘이 빠진 판정은 탐지 점수가 높아도 쓸 수 없다. 그래서 **판정을
LLM 에서 떼어냈다.** 규칙 엔진이 위험도·유형·행동을 확정하고, LLM 은 확정된
결과를 설명하는 자리에만 둔다.

측정 상세: [docs/32-fraud-evaluation-benchmark.md](docs/32-fraud-evaluation-benchmark.md)

---

## 처리 흐름

```
사용자 입력 (문자 원문 · 이미 취한 행동)
   │
   ├─ ① 입력 검증 · 개인정보 최소화   저장 원문은 그대로, 모델에 보내는 문장만 치환
   │
   ├─ ② 결정론 규칙 엔진              위험도 · 사기 유형 · 신호 — 판정은 여기서 끝난다
   │                                 LLM 없음 · 런타임 웹 검색 없음
   │
   ├─ ③ 공식 근거 결합                금융위 공공데이터 · 기관 공식 연락처 · 법령
   │
   ├─ ④ LLM 설명 생성                 확정된 판정을 사회초년생 문장으로
   │                                 실패해도 판정은 그대로 나간다
   │
   └─ ⑤ 출력 검증 4종                 기관 · 법령 · 수치 · 확정 약속
                                     근거에 없는 것을 말한 문장은 버린다
   ↓
 화면
```

이 다섯 단계를 하나의 프롬프트로 합치지 않는다. 합치는 순간 ②의 결정론성과
⑤의 검증 대상이 동시에 사라진다.

---

## 기술 스택

| 영역 | 사용 |
|---|---|
| 백엔드 | Python 3.12, FastAPI 0.141, Pydantic v2, SQLAlchemy 2.x, Alembic |
| 데이터베이스 | PostgreSQL — 금융 프로필은 애플리케이션 레벨 암호화, 키 회전 지원 |
| 프론트엔드 | Next.js 16.3, React 19.2, TypeScript 5, Tailwind CSS, PWA |
| LLM | Google Gemini (`gemini-3.6-flash`, 실패 시 `gemini-3.1-flash-lite` 로 대체) |
| 공식 데이터 | 공공데이터포털 — 금융위원회 금융상품 데이터셋 |
| 인프라 | Docker Compose 6 컨테이너, Caddy(자동 TLS), GCP Compute Engine |
| CI | GitHub Actions — `test` · `web` · `container-runtime` · `deps-lock` |
| 테스트 | pytest, vitest |

---

## 검증

### 사기 탐지 — held-out 12셋 865건

| 지표 | 값 |
|---|---|
| Precision / Recall / **F1** | 0.9872 / 0.9789 / **0.9830** |
| Accuracy / FPR | 0.9815 / 0.0153 |
| 오탐 · 미탐 | 6건 · 10건 |
| **공식 근거 coverage** | **1.0000** |
| 위험 상한 정확도 | 1.0000 |
| 상태 정책 정확도 | 0.9341 |
| 금지 행동 회피 | 0.9882 |
| 판정 지연 p50 / p95 | 2.626ms / **3.921ms** |

유형 분류에서 가장 약한 지점은 `isolation_coercion` 이다 (F1 0.8983, 정밀도
0.8548 / 재현율 0.9464, n=56). **덜 잡는 쪽이 아니라, 그 유형이 아닌 사례를
그 유형으로 부르는 쪽**으로 틀린다.

### 이 수치를 읽을 때의 한계

- **평가 데이터는 팀이 직접 작성한 합성 한국어 문자다.** 실제로 수집된 라벨
  데이터가 아니므로, 이 F1 을 실사용 환경의 성능으로 읽으면 안 된다.
- 규칙을 튜닝한 개발셋(61건)의 수치는 여기 싣지 않는다. 튜닝 대상이라 이미
  변별력이 없다. 전체 기록은 [docs/32](docs/32-fraud-evaluation-benchmark.md) 에 있다.
- held-out 셋은 규칙을 확정한 **뒤에** 작성·동결했다.

### 자동화 테스트

| | |
|---|---|
| 백엔드 | **1,294건** (GitHub Actions CI 기준) |
| 프론트엔드 | **155건** / 23 파일 (vitest) |

---

## 배포 · CI

- 공개 URL **<https://finshield-ai.duckdns.org>** — `v0.9.2` 가동 중
- GCP Compute Engine `e2-micro`, Docker Compose 6 컨테이너
  (`proxy` / `web` / `backend` / `db` / `retention` / `backup`)
- Caddy 자동 TLS(Let's Encrypt), HSTS, 내부 포트는 loopback 만 노출
- 자동 실행: 만료 세션·프로필 정리(`retention`), `pg_dump` 백업 세대 회전(`backup`)
- 관측성: 개인정보 안전 JSON 요청 로그, route 별 latency histogram,
  liveness/readiness 분리. **금융 원문·프로필 값·세션·인증 헤더는 기록하지 않는다.**
- **배포는 `main` push 가 아니라 `v*` 태그 push 로만 일어난다**
  ([release.yml](.github/workflows/release.yml)). CI 는 push/PR 마다 4개 job 을 돌린다.

운영 절차 [docs/31](docs/31-public-deployment.md) ·
백업과 복구 [docs/29](docs/29-backup-and-recovery.md) ·
관측성 [docs/27](docs/27-observability-pii-masking.md)

---

## 해결한 기술 문제

이 프로젝트에서 가장 오래 붙잡았던 다섯 가지다. 각 항목은 "그렇게 하는 편이
좋아 보여서"가 아니라 **측정이나 실제 결함이 먼저 있었고 그 결과로** 그렇게 됐다.

### 1. LLM 을 판정에서 떼어낸 근거를 측정으로 만들었다

"LLM 은 못 믿으니까"가 아니다. 실제로 돌려 보니 **탐지는 LLM 단독이 더 나은
회차도 있었다**(F1 0.975). 문제는 공식 근거 coverage **0.0**, 필수 행동
coverage **0.600** 이었다. 판정을 규칙 엔진에 두고 LLM 을 설명 계층으로 내린
것은 취향이 아니라 이 두 숫자 때문이다.
→ [docs/32-fraud-evaluation-benchmark.md](docs/32-fraud-evaluation-benchmark.md)

### 2. 출력 검증 4종 — 근거에 없으면 그 문장을 버린다

생성된 문장에서 기관명 · 법령 · 수치 · 확정 약속을 뽑아 근거 집합과 대조하고,
근거에 없는 것을 말한 문장은 폐기한다. 첫 판은 서술어만 보다가 **모델이 낸
정당한 경고 8건 중 4건을 거부했다**(지금은 0건). 검증기가 과하면 그건 안전
기능이 아니라 고장이다.
→ [docs/34-llm-explanation-runtime.md](docs/34-llm-explanation-runtime.md)

### 3. 프롬프트 인젝션 경계 — 사기 명령문은 지우면 안 되는 증거다

붙여넣은 문자는 데이터로 취급한다. 그런데 "지금 바로 안전계좌로 송금하세요"
같은 문장은 공격이 아니라 **설명이 딛고 설 증거**라서 바이트 단위로 그대로
통과해야 한다. 그래서 **모델을 수신자로 하는 문장만** 자리표시자로 바꾸고,
정화를 판정 **이후**에 돌려 입력 필터가 위험 등급을 낮추는 경로를 구조적으로
없앴다. 초기 구현은 마침표 없는 한국어 문자를 통째로 지웠다 — 한국어 문자는
부호 없이 종결어미로 끝나는 것이 보통이다.
→ [docs/12-security-threat-model.md](docs/12-security-threat-model.md),
`app/services/llm/untrusted.py`

### 4. PWA 공유 대상을 GET 이 아니라 POST 로

문자 앱 공유 시트로 들어오는 값은 사용자가 방금 받은 문자 원문이다.
`share_target` 을 GET 으로 두면 그 원문이 **브라우저 주소 기록 · 액세스 로그 ·
`Referer`** 에 그대로 복사되어, 공들여 만든 로그 allowlist 가 무의미해진다.
→ [docs/30-pwa-and-share-target.md](docs/30-pwa-and-share-target.md)

### 5. 백업 복원의 합격 기준을 "복호화됐다"로 바꿨다

금융 프로필은 애플리케이션 레벨로 암호화돼 있어서 **DB 만 복원하고 키를 잃으면
백업은 쓸모가 없다.** 기존 검사("알려진 금융 값이 평문으로 보이지 않는다")는
무작위 바이트열도 통과시켰다. 지금은 임시 DB 로 복원한 뒤 프로필을 실제로
복호화해야 통과하고, 실패하면 어느 세대의 key id 가 없는지 짚어준다.
→ [docs/29-backup-and-recovery.md](docs/29-backup-and-recovery.md),
`scripts/rehearse_backup_restore.py`

---

## 저장소 구조

| 경로 | 역할 |
|---|---|
| [app/](app/) | FastAPI 백엔드. `api`(라우트) · `services`(오케스트레이션) · `domain`(사기 규칙·금융 계산) · `repositories` · `schemas` · `core` · `db` · `security` |
| [web/](web/) | Next.js 프론트엔드. `app`(App Router) · `components` · `lib`(API 어댑터·표시 포맷). **금융 계산은 여기 없다** |
| [docs/](docs/) | 설계 문서 38편, ADR([adr/](docs/adr/)), 개발일지([devlog/](docs/devlog/)), 제출 원고([submission/](docs/submission/)) |
| [evaluation/](evaluation/) | 사기 탐지 평가. `data/`(골든셋·held-out JSONL) · `results/`(측정 결과 JSON) |
| [tests/](tests/) | 백엔드 pytest 47파일. 프론트엔드 테스트는 `web/` 안에 함께 있다 |
| [scripts/](scripts/) | 운영·검증 진입점 — retention 스케줄러, 백업 복원 리허설, 배포 검증, 벤치마크 실행 |
| [deploy/](deploy/) | Caddy 설정과 VM 운영 셸 스크립트 |
| [migrations/](migrations/) | Alembic 마이그레이션 |
| [.github/workflows/](.github/workflows/) | `ci.yml`(테스트) · `release.yml`(태그 릴리스) · `certificate-watch.yml`(인증서 만료 감시) |
| `compose*.yaml` | Docker Compose 진입점. **루트에 두는 이유**는 CI·`deploy/redeploy.sh`·VM 운영 명령이 전부 루트 기준이기 때문이다 |

---

## 실행 방법

### 백엔드

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |   macOS·Linux: source .venv/bin/activate
pip install --require-hashes -r requirements-dev.txt
uvicorn app.main:app --reload
```

### 프론트엔드

```bash
cd web && npm install && npm run dev   # http://localhost:3000
```

### Docker · PostgreSQL 통합 실행

```powershell
Copy-Item .env.docker.example .env.docker
.\.venv\Scripts\python.exe scripts\create_local_docker_secrets.py
docker compose --env-file .env.docker up --detach --build
.\.venv\Scripts\python.exe scripts\verify_compose_runtime.py
```

backend `http://127.0.0.1:18000`, web `http://127.0.0.1:13000`.

### 환경변수

- `DATABASE_URL` 과 `PROFILE_ENCRYPTION_KEYS` 를 설정한 뒤 `alembic upgrade head`.
  staging·production 은 `postgresql+psycopg://` 만 허용한다.
- `PUBLIC_DATA_SERVICE_KEY` 는 공공데이터포털에서 발급한다.
  **실제 키는 저장소나 로그에 남기지 않는다.** 키가 없으면 빈 목록이 아니라
  `503` 이 나간다 — 데이터가 없는 것과 설정이 빠진 것은 다른 상태다.

### 의존성 잠금

`requirements.in` / `requirements-dev.in` 이 원본이고 `requirements*.txt` 는
해시로 고정된 생성물이다. **`.txt` 를 직접 편집하지 않는다.**

```bash
uv pip compile requirements.in     --universal --generate-hashes --python-version 3.12 -o requirements.txt
uv pip compile requirements-dev.in --universal --generate-hashes --python-version 3.12 -o requirements-dev.txt
```

### 테스트

```bash
pytest -q
python -m scripts.evaluate_fraud_engine --check
cd web && npm test && npx tsc --noEmit && npm run lint
```

---

## 문서

| 주제 | 문서 |
|---|---|
| 문제 정의 · 제품 범위 | [01](docs/01-problem-definition.md) · [03](docs/03-product-scope.md) |
| 아키텍처 · 엔지니어링 기준 · 프론트엔드 | [04](docs/04-architecture.md) · [11](docs/11-engineering-standards.md) · [13](docs/13-frontend-architecture.md) |
| AI 보안 · 위협모델 | [08](docs/08-ai-security-alignment.md) · [12](docs/12-security-threat-model.md) |
| 공식 데이터 · 상품 카탈로그 | [07](docs/07-official-api-candidates.md) · [15](docs/15-product-catalog-live-profile.md)~[18](docs/18-deterministic-product-filtering.md) |
| 금융 프로필 · 암호화 · 생명주기 | [09](docs/09-financial-profile-schema.md) · [21](docs/21-profile-derived-metrics.md)~[24](docs/24-anonymous-data-lifecycle.md) |
| 평가 · LLM 설명 계층 | [32](docs/32-fraud-evaluation-benchmark.md) · [34](docs/34-llm-explanation-runtime.md) |
| 운영 · 배포 · 백업 | [25](docs/25-docker-postgres-runtime.md)~[31](docs/31-public-deployment.md) |
| 공모전 제출 원고 | [38](docs/38-submission-forms.md) |

전체 색인은 [docs/README.md](docs/README.md), 현재 백로그는
[docs/10-mvp-backlog.md](docs/10-mvp-backlog.md) 에 있다.

---

## 변경 이력

2026-08-19 까지 이 README 에 쌓여 있던 개발 기록은 [CHANGELOG.md](CHANGELOG.md)
로 옮겼다. **한 줄도 지우지 않았다.**

---

## 고지

FinShield AI 의 위험 분석은 **실험적 규칙 기반 위험 신호 분석**이며, 범죄 확정,
금융·법률 판단 또는 공식 신고 절차를 대신하지 않는다. 서비스는 주민등록번호,
계좌 비밀번호, OTP, 카드 전체 정보를 요구하지 않는다.
