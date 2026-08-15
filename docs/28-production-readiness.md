# 28. 프로덕션 준비 상태와 남은 작업

목적: FinShield AI를 실제 도메인에 공개 배포할 수 있는 상태로 만든다. 이 문서는 "무엇이 이미 되어 있는가"와 "공개 전에 반드시 끝내야 하는가"를 코드 기준으로 구분한다. 작성 기준일 2026-08-14, 기준 커밋 `c4a98a0`.

판단 기준은 하나다. **공개 URL이 붙는 순간 인증 없는 트래픽이 들어온다.** 그 트래픽이 비용·데이터·개인정보에 남기는 흔적을 통제할 수 있으면 배포 가능, 아니면 불가다.

## 1. 이미 갖춰진 것

이 항목들은 다시 만들 필요가 없다.

| 영역 | 상태 | 근거 |
|---|---|---|
| 컨테이너 이미지 | base 이미지 digest 고정, non-root uid 10001, `read_only`, `cap_drop: ALL`, `no-new-privileges` | `Dockerfile`, `web/Dockerfile`, `compose.yaml` |
| 파이썬 의존성 | 해시 고정 universal lock, 런타임·개발 분리, CI가 lock 드리프트 차단 | `requirements.in`, `requirements.txt`, `.github/workflows/ci.yml` (2절 P0-5) |
| 프로세스 경계 | db / migration / backend / web 분리, 내부 포트 loopback 전용, healthcheck 기반 기동 순서 | `compose.yaml` |
| HTTPS 진입점 | Caddy 자동 인증서, HTTP→HTTPS, HSTS, `FINSHIELD_DOMAIN` 필수 | `compose.https.yaml`, `deploy/Caddyfile`, `docs/26` |
| 비밀값 관리 | `*_FILE` 우선 조회 + Docker file secrets. 이미지·환경변수·저장소에 값이 남지 않음 | `app/core/runtime_secrets.py` |
| 저장 데이터 보호 | FinancialProfile 애플리케이션 레벨 암호화, 키 로테이션 경로 | `app/security/profile_encryption.py`, `adr/0002` |
| 로그 개인정보 | 로그 필드 allowlist 고정. 쿼리·본문·경로 파라미터가 구조적으로 로그에 없음 | `app/core/observability.py`, `tests/test_observability.py` |
| HTTP 보안 경계 | 보안 헤더, same-origin 상태 변경 보호, trusted host | `app/core/http_security.py`, `docs/26` |
| 요청 한도·본문 크기 | IP 기준 rate limit(429 + `Retry-After`), 파싱 이전 본문 상한, 카운터는 HMAC 버킷으로 PostgreSQL 저장 | `app/core/rate_limit.py`, `app/core/request_limits.py`, `web/lib/api/request-body.ts` (2절 P0-1) |
| 만료 데이터 정리 | 전용 컨테이너가 주기 실행. 성공 시각 heartbeat 기반 healthcheck, 로그는 건수·성공 여부만 | `app/services/data_retention.py`, `scripts/run_retention_scheduler.py`, `compose.yaml` (2절 P0-2) |
| CI | pytest / 프론트 build·tsc·lint·test / compose 실기동 + backup·restore + rate limit·본문 상한 + 정리 스케줄 검증 | `.github/workflows/ci.yml`, `scripts/verify_compose_runtime.py` |

정리하면 **배포 스택 자체는 이미 프로덕션 형태다.** 남은 것은 스택이 아니라 운영이다.

## 1-1. 코드 검증 결과 (2026-08-14)

"테스트 199개 통과"는 정확성의 근거가 아니다. 세 가지 독립적인 방법으로 다시 확인했다.

| 방법 | 대상 | 결과 |
|---|---|---|
| 독립 재계산 | `loan_calculator` | 표준 annuity 공식으로 따로 계산해 무작위 800케이스 대조. 참조값 `100000/6%/360 → 599.55` 일치, 원금 합계·잔액 단조감소·최종 잔액 0·회차 분해 전부 통과 |
| 적대적 E2E 탐침 | 세션 소유권 | 실제 쿠키 세션 2개로 프로필 전 엔드포인트 침투. 12/12 차단. 타인 자원은 403이 아니라 **404**로 존재 여부를 감춤 |
| Mutation 감사 | 테스트 자체 | 핵심 로직에 고의로 버그를 심고 스위트가 잡는지 확인 |

Mutation 감사에서 **위험 등급 임계값만 통과했다.** `score >= 70`을 `>= 90`으로 바꿔도 전 테스트가 통과했고, 그 분기는 죽은 코드가 아니라 실제로 등급을 바꾸는 살아있는 로직이었다. 나머지(상태 최소위험, 점수 상한, 반올림 방식, 로그 PII 유출, SQL·메모리 소유자 필터)는 모두 잡혔다.

같은 검증에서 드러나 **함께 수정한 것**:

| 문제 | 수정 |
|---|---|
| 위험 등급 임계값에 테스트 없음 | `HIGH_RISK_SCORE_THRESHOLD` / `MEDIUM_RISK_SCORE_THRESHOLD` 로 명명하고 `tests/test_fraud_risk_level.py` 가 경계 34/35/69/70 + 신호 최소등급 + 조합 규칙 + 상태 최소등급을 각각 고정 |
| 스킴 없는 URL이 링크 검사 통과 (`1.2.3.4/login`) | 스킴 유무와 무관하게 호스트를 뽑아 같은 검사 적용. 본문에서도 스킴 없는 링크를 후보로 추출. `javascript:` / `data:` 같은 비-HTTP 스킴 차단. `tests/test_fraud_urls.py` |
| `retrieved_at` 하드코딩으로 링크 재확인 시 분석 500 | 형식·미래 날짜만 데이터 오류로 막고, 오래된 출처는 `stale_official_sources()` 로 경고. 기동 시 `verify_official_sources()` 호출을 추가해 잘못된 데이터가 health check를 통과하지 못하게 함. `tests/test_official_sources.py` |
| zod ↔ pydantic 계약 드리프트 | `marital_status`·`region` 왕복 보존(수정 시 서버 값이 null로 덮이던 경로 제거), `marital_status`·`annual_business_revenue_band`·`loan_items` 를 느슨한 `string`/`unknown` 에서 실제 enum·객체 스키마로 고정, 금리 소수 자릿수를 백엔드 `decimal_places=4` 에 맞춤 |

**남은 미측정 항목**: `authority_impersonation` 오탐(`"어제 경찰서 다녀왔어요"` → medium)은 규칙 기반 bootstrap의 한계이며 FPR이 측정된 적이 없다. P2-1 평가 하네스 없이는 정량 판단이 불가능하다.

## 2. P0 — 공개 배포 차단 항목

이 다섯 개를 끝내기 전에는 공개 도메인을 붙이지 않는다.

### P0-1. Rate limiting과 요청 본문 크기 제한 — 완료 (2026-08-15)

문제였던 것: `POST /api/v1/analyze`에는 인증 의존성이 없고 (`app/api/routes/analysis.py:9`), `POST /api/v1/auth/session`은 익명 세션을 무제한으로 만들 수 있었다. 분석은 CPU를, 세션은 DB 행을 소모한다. 스키마 상한(`text` 10000자)은 요청 **한 건**의 크기만 막을 뿐 **빈도**를 막지 못한다.

**식별자는 계획을 바꿔 IP 단독으로 갔다.** 당초 이 문서는 "익명 세션 + IP 조합"을 적었지만, 세션은 공격자가 스스로 발급받을 수 있다. 세션마다 따로 세면 세션을 n개 만들어 한도를 n배로 늘린다. 세션 발급 자체를 제한해도 그 한도가 곧 실질 상한이 되어 계층이 하나 늘 뿐이다. IP는 공격자가 임의로 바꿀 수 없는 유일한 축이라, 여기서의 상한이 실제 상한이 된다. 대가는 CGNAT·회사망에서 여러 사용자가 한 버킷을 공유하는 것이고, 그래서 한도를 넉넉히 잡았다. 목적은 공정 분배가 아니라 "한 명이 서비스를 갈아버리는 것"의 차단이다 (`app/services/rate_limits.py` 모듈 docstring).

정책 (위에서부터 먼저 맞는 하나만 적용, `/health`·`/readyz` 는 어떤 정책에도 걸리지 않음):

| 이름 | 대상 | 한도 | 이유 |
|---|---|---|---|
| `auth_session` | `POST /api/v1/auth/session` | 20 / 1시간 | 호출마다 users·auth_sessions 행이 생긴다. 정상 사용자는 브라우저당 한 번 |
| `analyze` | `POST /api/v1/analyze` | 30 / 1분 | 가장 비싸고 인증이 없는 경로 |
| `write` | `/api/v1/` 쓰기 | 60 / 1분 | |
| `read` | `/api/v1/` 나머지 | 240 / 1분 | |

구조:

| 부분 | 파일 | 판단 |
|---|---|---|
| client IP 해석 | `app/core/client_identity.py` | `X-Forwarded-For`를 **오른쪽에서** 홉 수만큼 센다. `FINSHIELD_TRUSTED_PROXY_HOPS` 기본 0 = 헤더 불신, TCP peer 사용 |
| 본문 크기 (백엔드) | `app/core/request_limits.py` | 순수 ASGI. `receive`를 감싸 바이트를 세야 해서 `BaseHTTPMiddleware`를 쓸 수 없다. `Content-Length`는 빠른 거부에만 쓰고 실제 판단은 흘러오는 바이트로 |
| 본문 크기 (web) | `web/lib/api/request-body.ts` | Route Handler에는 본문 크기 기본 상한이 **없다.** 배포 경로가 Caddy → web → backend라 노출된 쪽은 web이고, `request.json()`을 그냥 부르면 100MB 본문도 다 담은 뒤에야 zod에서 거부한다 |
| 카운터 저장 | `app/repositories/rate_limits.py` | InMemory(로컬) / SQLAlchemy(배포). 배포에서 SQLite면 기동 거부 — 워커 간 카운터가 안 공유돼 한도가 워커 수만큼 헐거워지는데 겉으로는 정상으로 보인다 |
| 버킷 키 | `app/services/rate_limits.py` | `HMAC(secret, policy|ip)`. IPv4는 값이 2^32개뿐이라 단순 해시는 표로 되돌릴 수 있다. 저장된 행이 접속 기록이 되면 안 된다 |
| 저장소 장애 | 같은 파일 | **통과시킨다.** DB 장애 때문에 위험한 문자를 확인 못 하게 만드는 쪽이 그동안 한도가 열리는 것보다 나쁘다. `app/domain/fraud/sources.py`와 같은 판단 |
| 만료 행 정리 | `scripts/cleanup_expired_anonymous_data.py` | 닫힌 window 행은 다시 조회되지 않는다. 지우지 않으면 요청 수만큼 무한히 쌓인다. 개인정보 정리 **뒤에** 둔다 |

홉 수가 실제로 맞는지가 이 기능의 정확성을 좌우한다. 경로는 Caddy → web → backend다.

- Caddy는 `header_up X-Forwarded-For {remote_host}` 로 클라이언트가 미리 적어 보낸 체인을 **이어붙이지 않고 덮어쓴다** (`deploy/Caddyfile`). 인터넷에 직접 붙어 있으므로 믿을 수 있는 주소는 TCP peer 하나뿐이다.
- web은 그 값을 **그대로 넘기고 자기 홉을 덧붙이지 않는다** (`web/lib/api/server-auth.ts`). Route Handler는 TCP peer를 볼 수 없어서 덧붙일 값이 없다.
- 따라서 맨 오른쪽 항목 = 실제 클라이언트이고 `FINSHIELD_TRUSTED_PROXY_HOPS=1` 이다 (`compose.https.yaml`). 앞단에 CDN을 두면 Caddyfile과 이 값을 함께 고쳐야 한다.

web이 체인을 다듬을 때 **오른쪽 기준 인덱스가 절대 밀리지 않는 변형만** 한다. 왼쪽에서만 자르고(최대 8개), 형식이 이상한 항목은 삭제가 아니라 `unknown`으로 치환해 자리를 유지한다. 항목을 지우면 홉 인덱스가 밀려 공격자가 심어둔 값이 선택될 수 있다.

프론트 문구는 429가 "안전하다"로 읽히지 않게 고정했다. "요청이 많아 분석을 잠시 멈췄습니다. **아직 위험 여부는 확인되지 않았습니다.**" + 급하면 112 / 1394 안내. `web/lib/api/analysis.test.ts`가 전 실패 종류의 문구에 `/안전|이상 없음|위험 없음|정상입니다/`가 없음을 회귀로 고정한다. 429를 502로 덮지 않는 것도 같은 이유다 — 502는 "서버가 고장났다"로 읽혀서 사용자가 계속 재시도한다 (`web/lib/api/proxy-response.ts`).

검증 결과:

| 확인 | 방법 | 결과 |
|---|---|---|
| 한도 초과 | 백엔드 직접 31회 POST | 30회 200, 31번째 429 + `Retry-After: 22` + `RateLimit-Limit: 30` |
| 버킷 분리 | 다른 `X-Forwarded-For` | 200, `RateLimit-Remaining: 29` |
| 홉 위조 | `198.51.100.7, 203.0.113.10` | 429 유지. 왼쪽에 심은 값으로 버킷을 못 바꾼다 |
| 본문 상한 (백엔드) | 200KB 본문 | 413, 파싱 전 차단 |
| 본문 상한 (web) | 프록시로 200KB | 413. zod 400으로 가려지지 않음 |
| healthcheck 영향 | `/health/ready` 연속 호출 | 전부 200. 스스로를 unhealthy로 만들지 않음 |
| 프록시 경유 문구 | web → backend 30회 | 429 + 한국어 문구 + `Retry-After` 전달 |
| 회귀 | `pytest -q` / `vitest` | 352 passed 1 skipped / 80 passed |

로컬에 Docker 데몬을 띄울 수 없어 컨테이너 실기동 대신 uvicorn + `next dev`로 같은 경로를 세워 확인했다. `docker compose config`로 base/https 병합 결과(`FINSHIELD_TRUSTED_PROXY_HOPS` 0/1)는 별도 확인했다.

컨테이너에서의 확인은 CI에 넣었다. `container-runtime` job이 `FINSHIELD_RATE_LIMIT_ENABLED=1`로 스택을 띄우고, `scripts/verify_compose_runtime.py`가 (1) 200KB 본문이 400이 아니라 **413**으로 잘리는지 — 400이면 스키마가 거부했다는 뜻이고 그건 이 방어가 동작하지 않았다는 뜻이다 — (2) 31번째 요청에서 429 + 유효한 `Retry-After`가 나오는지, (3) 카운터가 PostgreSQL 행으로 남는지 — 프로세스 메모리에 있으면 재시작 한 번으로 초기화되고 워커가 여러 개면 워커 수만큼 헐거워진다 — (4) 그 행의 `bucket_key`가 64자 hex인지, 즉 **IP가 그대로 저장되지 않는지**를 검사한다.

남은 것: backend는 이미 `uvicorn --workers 2`로 뜨지만(`Dockerfile`), 위 검증은 **한도 초과가 실제로 429가 되는지**만 확인한다. 두 워커가 같은 카운터 행을 동시에 갱신할 때 경합으로 카운트가 새는지는 측정하지 않았다. 저장소가 PostgreSQL이라 원자적 UPSERT로 처리되지만, 확인된 사실이 아니라 설계상의 기대다. 워커를 더 늘리기 전에 동시 부하로 재확인해야 한다.

### P0-2. 만료 데이터 정리 자동 실행 — 완료 (2026-08-15)

문제였던 것: `scripts/cleanup_expired_anonymous_data.py`는 있었지만 아무도 부르지 않았다. `adr/0004`의 보존기간은 문서상의 약속일 뿐 이행되지 않았고, 그 상태로 공개하면 개인정보 보존 약속 위반과 DB 무한 증가가 동시에 발생한다.

구조:

| 부분 | 파일 | 판단 |
|---|---|---|
| 삭제 로직 | `app/services/data_retention.py` | `RetentionRunner`가 만료 세션 → 소유 프로필 → 닫힌 rate limit window 순으로 지운다. **개인정보가 먼저다** — 뒤 단계가 실패해도 보존기간 약속은 이미 지켜져 있어야 한다 |
| 의존 대상 | 같은 파일 | service가 아니라 **repository**를 받는다. `RateLimitService`를 거치면 정리가 그 설정에 묶여서, rate limit을 끄고 HMAC 비밀을 내리면 개인정보 삭제까지 같이 멈춘다 |
| 주기 실행 | `RetentionScheduler` | 첫 실행을 미루지 않는다. 배포 직후 한 주기를 통째로 기다리면 그동안은 보존기간이 지켜지지 않는 상태로 서비스가 떠 있는 것이다. 실패해도 같은 간격으로 재시도 — backoff는 heartbeat 신선도 기준까지 흔든다 |
| 실행 위치 | `compose.yaml`의 `retention` 서비스 | backend 안의 background task로 넣지 않았다. 워커가 2개라 같은 정리가 동시에 두 번 돌고, API 응답 지연과 정리 지연이 한 프로세스에 얽힌다. 분리하면 API가 죽어도 개인정보 삭제는 계속된다 |
| 진입점 | `scripts/run_retention_scheduler.py` | 상주 / `--once` / `--check-heartbeat` |
| 미리보기 | `scripts/cleanup_expired_anonymous_data.py` | 같은 `RetentionRunner`를 쓴다. 미리보기 건수와 스케줄러가 실제로 지우는 건수가 갈라지면 미리보기가 쓸모없어진다 |

**"실패가 조용히 넘어가지 않는다"를 healthcheck로 옮겼다.** 로그만 남기면 아무도 안 본다. 그렇다고 프로세스 liveness를 보면 안 되는데, **계속 실패하는 loop도 프로세스는 살아 있기 때문이다.** 그래서 성공한 실행만 heartbeat 파일에 시각을 쓰고, healthcheck는 그 시각의 나이를 본다. 임계값은 `interval * 2 + 60`초 — 한 주기 놓친 것은 DB 순간 장애지만 두 주기 연속은 실제 고장이다. heartbeat 쓰기는 임시 파일 + `os.replace`로 원자적이다. 그러지 않으면 healthcheck가 쓰는 도중에 읽어 잘린 내용을 보고 멀쩡한 실행을 실패로 판정한다. `--check-heartbeat`는 **DB를 건드리지 않는다** — DB가 흔들릴 때 정리 컨테이너까지 unhealthy로 떨어지면 원인이 흐려진다.

거짓 성공을 두 군데서 막았다. (1) `DATABASE_URL`이 없으면 기동을 거부한다. in-memory 저장소를 상대로 돌면 아무것도 지우지 않으면서 매번 성공을 기록하는데, **"정리가 되고 있다"는 거짓 신호는 정리가 아예 없는 것보다 나쁘다.** (2) 배포 환경에서 `postgresql+psycopg://`가 아니면 거부한다. `compose.https.yaml`이 `retention`의 `APP_ENV`도 production으로 올리는 이유가 이것이다 — 여기만 development로 남으면 정리 컨테이너만 SQLite를 허용하게 된다.

로그는 `adr/0004` 제약을 그대로 따른다. 성공은 건수 4종 + 소요시간, 실패는 **예외 타입만** 남기고 메시지는 버린다. SQLAlchemy는 실패한 문장과 바인딩 값을 `str(exc)`에 붙이는데, 그러면 정리 로그가 개인정보 유출 경로가 된다.

검증 결과:

| 확인 | 방법 | 결과 |
|---|---|---|
| 실제로 지워지는가 | SQLite에 만료/활성 데이터를 2건씩 넣고 스케줄러를 실제 프로세스로 기동 | users·profiles·counters 2/2/2 → 1/1/1. 활성 데이터는 살아남음 |
| 스케줄이 걸려 있는가 | 첫 실행이 sleep보다 먼저인지, 실패 후에도 loop가 이어지는지 | `["cleanup", "sleep:900", "cleanup", "sleep:900"]` 순서 고정 |
| 실패를 노출하는가 | heartbeat 없음 / 성공 직후 / 5시간 과거로 조작 | `--check-heartbeat` exit 1 → 0 → 1 |
| 실패가 heartbeat를 오염시키지 않는가 | 실행 실패 후 heartbeat 파일 | 갱신되지 않음. 이전 성공 시각 유지 |
| 로그에 식별자가 없는가 | 삭제된 사용자 UUID를 스케줄러 stdout에서 검색 | 없음. 건수만 |
| 예외 메시지가 새지 않는가 | `RuntimeError("session=abc123 user=42 ...")`를 던지는 저장소 | 로그에 `error_type`만. `abc123`·`user=42` 없음 |
| 설정 오류가 조용히 넘어가지 않는가 | `DATABASE_URL` 없이 기동 | exit 2 + `retention_config_error`. 컨테이너가 죽어서 눈에 띈다 |
| compose 렌더링 | `docker compose config`, https 오버레이 병합 | `retention` 서비스 정상, `APP_ENV: production` 병합 확인 |
| 회귀 | `pytest -q` | 383 passed, 1 skipped (+31) |

완료 기준("만료 데이터를 넣고 스케줄 주기를 지난 뒤 자동으로 사라지는 것을 실환경에서 확인")은 CI에서 이행한다. 로컬에 Docker 데몬을 띄울 수 없어 위 첫 줄은 SQLite + 실제 subprocess로 확인했고, 컨테이너 확인은 `scripts/verify_compose_runtime.py`의 `verify_retention_schedule()`이 맡는다. **`--once`로 한 번 돌려보는 것으로는 부족하다.** 그건 스크립트가 동작한다는 확인이지 스케줄이 걸려 있다는 확인이 아니고, P0-2가 막고 있던 것은 후자다. 그래서 실제로 세션을 만들고 `expires_at`을 과거로 밀어(TTL이 30일이라 기다려서 만료시킬 수 없다) 한 주기를 기다린 뒤 행이 사라졌는지, `retention` 컨테이너가 `healthy`인지, 로그에 `"status":"succeeded"`가 있고 `user_id`는 없는지를 검사한다. CI는 이를 위해 `FINSHIELD_RETENTION_INTERVAL_SECONDS=60`으로 스택을 띄운다.

남은 것: 정리 실패가 **컨테이너 밖으로** 알려지지 않는다. healthcheck가 unhealthy를 띄워도 그것을 보고 사람에게 알리는 경로는 P1-1이다. 그때까지는 `docker compose ps`를 봐야 안다.

### P0-3. 백업 자동화와 복원 리허설

`pg_dump`/restore 로직은 현재 `scripts/verify_compose_runtime.py` 안, 즉 CI 검증 경로에만 있다. 운영 백업 스케줄은 없다. 저장 데이터가 암호화된 프로필이라 **DB만 복원하고 키를 잃으면 백업은 쓸모가 없다.**

- 주기적 dump + 보존 세대 관리 + 저장 위치(볼륨 밖)
- 암호화 키와 DB 백업의 복구 절차를 한 문서에 함께 적는다. 둘 중 하나만 있으면 복구 불가라는 점을 명시
- 정기 복원 리허설. "백업이 생성된다"가 아니라 "복원이 성공한다"가 완료 기준
- 완료 기준: 빈 환경에서 백업만으로 서비스를 기동해 프로필 복호화까지 성공

### P0-4. 실도메인·DNS·TLS 실환경 검증

`docs/devlog/2026-08-13/`가 명시한 미완료 항목이다. Caddy 설정과 compose는 검증됐지만 실제 도메인·DNS·인증서 발급은 한 번도 돌지 않았다. 자동 인증서는 DNS가 실제로 가리키기 전에는 검증할 수 없다.

- 도메인 확정 → DNS A/AAAA → `FINSHIELD_DOMAIN` 주입 → 인증서 자동 발급 확인
- 외부에서 HTTP→HTTPS 리다이렉트, HSTS, TLS 등급 측정
- 인증서 갱신 실패 시 알림 경로 (갱신은 60일 뒤에 조용히 실패한다)
- 완료 기준: 외부 네트워크에서 실제 도메인으로 전 주요 화면 동작

### P0-5. 파이썬 의존성 잠금 — 완료 (2026-08-14)

문제였던 것: base 이미지는 digest로 고정했는데 `requirements.txt`는 `fastapi>=0.116,<1.0` 같은 범위 지정이었다. 같은 커밋을 다시 빌드해도 다른 버전이 설치돼, 장애 시 "어제와 무엇이 달라졌는가"에 답할 수 없었다. 부수적으로 `pytest`가 런타임 목록에 있어 프로덕션 이미지에 테스트 프레임워크가 실려 나갔다.

구조:

| 파일 | 성격 | 쓰는 곳 |
|---|---|---|
| `requirements.in` | 사람이 고침 (런타임) | lock 원본 |
| `requirements-dev.in` | 사람이 고침 (`-r requirements.in` + pytest, uv) | lock 원본 |
| `requirements.txt` | 생성물, 해시 고정 | 컨테이너 이미지, `container-runtime` job |
| `requirements-dev.txt` | 생성물, 해시 고정 | 로컬 개발, `test`·`deps-lock` job |

`uv pip compile --universal --generate-hashes`로 만든다. `--universal`을 쓰는 이유는 개발이 Windows, 배포가 Linux이기 때문이다. 플랫폼별로 해석하면 lock이 두 벌로 갈라지는데, universal은 marker로 한 파일에 담는다 (`uvloop`은 non-win32, `colorama`는 win32). 설치는 양쪽 모두 `pip install --require-hashes`다. `--no-deps`를 쓰지 않으므로 lock에 전이 의존성이 빠져 있으면 조용히 넘어가지 않고 설치가 실패한다.

CI `deps-lock` job이 `.in`과 lock의 어긋남을 막는다. `--upgrade` 없이 재컴파일하면 기존 pin이 유지되므로, 상류에 새 버전이 나왔다는 이유로는 실패하지 않고 `.in`을 고치고 lock을 갱신하지 않은 경우에만 diff가 생긴다.

검증 결과:

| 확인 | 방법 | 결과 |
|---|---|---|
| lock이 Windows에서 설치되는가 | 새 venv에 `pip install --require-hashes -r requirements-dev.txt` | 성공 |
| 잠긴 버전에서 회귀가 없는가 | 그 venv로 `pytest -q` | 277 passed, 1 skipped |
| lock이 Linux에서 설치되는가 | `docker build` (linux/amd64) | 성공 |
| 재컴파일이 멱등한가 | `--upgrade` 없이 재생성 후 byte diff | 동일 |
| 이미지가 lock과 정확히 일치하는가 | 이미지 `pip freeze` vs lock pin 대조 | 32개 전부 일치, lock 밖 패키지 0개 |
| 개발 의존성이 이미지에서 빠졌는가 | 이미지 안에서 import 확인 | `pytest`·`uv` 없음, `uvloop` 있음, `colorama` 없음 |

완료 기준("서로 다른 시점의 빌드가 동일한 패키지 버전 집합을 설치")은 마지막 두 줄로 충족된다. 이미지에 설치된 집합이 lock pin 집합과 완전히 일치하고, lock은 `--upgrade` 없이는 변하지 않는다.

남는 것: **버전 상승을 관측할 경로가 없다.** lock은 사람이 `--upgrade`를 붙일 때만 움직이므로, 보안 패치가 나와도 아무도 알려주지 않는다. Dependabot 또는 주기적 `--upgrade` PR을 P1-5로 둔다.

## 3. P1 — 공개 직후 필요한 운영 역량

배포는 가능하지만 이것 없이는 오래 운영하지 못한다.

### P1-1. 장애 알림과 에러 추적

`/metrics`가 Prometheus 텍스트를 내지만 수집하는 쪽이 없다. 지금 구조에서는 장애를 사용자가 먼저 안다. 최소한 헬스체크 실패, 5xx 급증, 외부 공식 API 실패율 상승에 대한 알림이 필요하다. 에러 추적을 붙일 때 **로그 allowlist 원칙을 깨지 않는지** 반드시 확인한다 — 대부분의 에러 추적 SDK는 기본값으로 요청 본문을 보낸다.

### P1-2. Audit log

계정 삭제, 프로필 변경처럼 되돌릴 수 없는 동작의 기록이 없다. `docs/10`에서 "identity와 보존 정책 필요"로 미뤄둔 항목이다. 익명 세션 모델 위에서 무엇을 남길 수 있는지부터 정해야 한다. 감사 로그가 개인정보 보존기간 정책과 충돌하지 않게 설계한다.

### P1-3. 배포·롤백 절차

현재 CI는 검증까지만 하고 배포하지 않는다. 수동 배포는 롤백이 안 된다. migration 컨테이너가 앞서 도는 구조이므로 **마이그레이션 되돌리기 전략**을 배포 절차와 함께 정한다. 스키마 변경과 코드 배포를 같은 순간에 되돌릴 수 없다는 점이 핵심 제약이다.

### P1-4. nonce 기반 strict CSP

`docs/26`의 남은 항목. Next.js standalone과 함께 쓸 때 nonce 전달 경로를 확인해야 한다.

### P1-5. 의존성 버전 상승 관측

P0-5로 버전은 고정했지만, 고정은 그 자체로 위험을 만든다. lock은 사람이 `--upgrade`를 붙일 때만 움직이므로 취약점 패치가 나와도 저장소는 조용하다. Dependabot(`pip` + `npm` + `docker`) 또는 주기적 `--upgrade` PR로 **상승 사실을 알리는 경로**를 만든다. 자동 병합은 하지 않는다. `deps-lock` job이 이미 lock 무결성을 검증하므로, 필요한 것은 알림뿐이다.

## 4. P2 — 제품·대회 완성도

배포와 무관하지만 이 프로젝트의 주장을 증명하는 부분이다.

### P2-1. 평가 하네스

**현재 저장소에 평가 코드가 전혀 없다.** `eval/`도 `benchmarks/`도 없고 precision/recall/F1을 계산하는 코드도 없다. `CLAUDE.md`의 Evaluation 조항과 `docs/05`가 요구하는 Rule-only / LLM-only / Hybrid 비교가 문서로만 존재한다.

이건 단순 누락이 아니다. 이 프로젝트의 논지는 "hybrid가 더 안전하고 정확하다"인데, 그걸 뒷받침하는 숫자가 하나도 없다. 지금 상태로는 아키텍처 주장이 근거 없는 선언이다.

- golden set 먼저 (`docs/05`의 scenario engine 항목 형식: 입력 상황, 이미 한 행동, 예상 scenario, 허용/금지 행동)
- 재현 가능한 실행 진입점, 결과 산출물 포맷 고정
- 지표: fraud 분류 precision/recall/F1과 class별 recall, 신호 추출 precision/recall, scenario 일치율, FPR
- **먼저 Rule-only 베이스라인을 측정한다.** LLM 없이도 지금 당장 낼 수 있는 숫자이고, 이후 모든 비교의 기준선이 된다

### P2-2. LLM 설명 계층

`app/` 전체에 LLM 클라이언트가 없다. 아키텍처 다이어그램의 "LLM explanation" 단계가 코드에 존재하지 않고, 현재 시스템은 순수 규칙 기반이다. 프론트의 설명 텍스트는 mock 계층에서 온다.

도입 시 함께 필요한 것: 출력 스키마 검증(`docs/04`의 model output schema validation), prompt injection golden set, 근거 이탈 검출. 규칙 판정을 LLM이 덮어쓰지 못하게 하는 경계가 코드로 강제되어야 한다 — `CLAUDE.md`의 첫 번째 non-negotiable이다.

**P2-1을 먼저 한다.** 베이스라인 없이 LLM을 넣으면 개선됐는지 나빠졌는지 알 수 없다.

### P2-3. 접근성 실기기 검수

구조적 자동 회귀는 `web/components/a11y.test.tsx`가 상시 실행 중이다. 남은 것은 스크린리더 낭독, 명도대비 AA 실측, 실기기 iOS Safari 확인이다. 상세는 `docs/13` 9절.

## 5. 모바일 전략 — PWA 우선, 네이티브는 나중

사용자 대부분이 폰으로 쓸 것이라는 전제는 타당하다. 의심 문자를 받은 순간 쓰는 서비스이므로 폰이 기본 환경이다. 다만 **지금 필요한 것은 안드로이드 앱이 아니라 PWA다.**

이유는 UI가 아니라 인증 모델이다. 현재 세션은 `SameSite=Strict` + HttpOnly 쿠키에 trusted-host 허용목록이고 CORS 미들웨어가 없다 (`app/core/http_security.py`, `app/api/routes/auth.py`). **네이티브 앱이나 WebView 클라이언트는 이 인증을 그대로 쓸 수 없다.** 네이티브로 가려면 토큰 기반 인증, CORS 정책, 그리고 그에 딸린 위협 모델을 새로 만들어야 한다. 화면을 옮기는 작업이 아니라 보안 경계를 다시 세우는 작업이다.

PWA는 같은 오리진에서 돌기 때문에 지금 인증 모델을 그대로 쓴다. 얻는 것:

- 홈 화면 설치, 전체화면 실행 — 체감상 앱과 같다
- **Android 공유 시트 연동 (`share_target`)** — 문자 앱에서 의심 메시지를 바로 넘길 수 있다. 이 제품의 핵심 진입 경로다
- 배포 심사 없음, 스토어 계정 없음, 단일 코드베이스

포기하는 것: iOS의 공유 시트·푸시 제약, `READ_SMS` 자동 수집. 후자는 Play Store 제한 권한이라 어차피 심사를 통과하기 어렵고, `CLAUDE.md`의 PII 최소화 원칙과도 정면으로 충돌한다. 자동 수집은 하지 않는다.

작업 범위: manifest, 아이콘, `share_target` 라우트, 오프라인 셸(분석 결과는 캐시하지 않는다 — 민감 데이터다), 설치 유도 UI. **실도메인(P0-4) 앞에 넣는다.** HTTPS가 PWA 설치 요건이고, 공개 직후 바로 폰에 설치되는 편이 낫기 때문이다.

Capacitor로 감싸는 선택지는 스토어 등록이 실제로 필요해질 때 다시 판단한다. 그 시점의 선결 조건은 위에 적은 토큰 기반 인증이다.

## 6. 권장 순서

```
0. 접근성 브랜치 병합 (작업 중 브랜치 정리)
1. P0-5 의존성 잠금        ← 완료 (2026-08-14)
2. P0-1 rate limit + 본문 크기 제한   ← 완료 (2026-08-15)
3. P0-2 만료 데이터 정리 자동화   ← 완료 (2026-08-15)
4. P0-3 백업 자동화 + 복원 리허설   ← 다음
5. PWA (manifest + share_target)  ← 실도메인 직전
6. P0-4 실도메인·DNS·TLS   ← 공개 배포
7. P1-1 알림 → P1-5 의존성 상승 관측 → P1-3 배포·롤백 → P1-2 audit log → P1-4 CSP
8. P2-1 평가 하네스 → P2-2 LLM 계층
```

P0-5를 맨 앞에 둔 이유는 의존성이 고정돼야 이후 rate limit·백업 검증 결과가 재현되기 때문이다. P0-4를 마지막에 두는 이유는 공개 노출이 되돌리기 가장 어려운 단계라서다.

대회 일정이 공개 URL보다 우선한다면 P2-1(평가 하네스)을 P0-1 다음으로 올린다. Rule-only 베이스라인 측정은 배포 상태와 무관하게 지금 바로 가능하다.
