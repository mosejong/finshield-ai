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
| HTTPS 진입점 | Caddy 자동 인증서, HTTP→HTTPS, HSTS, `FINSHIELD_DOMAIN`·`FINSHIELD_ACME_EMAIL` 필수, SNI healthcheck | `compose.https.yaml`, `deploy/Caddyfile`, `docs/26` |
| 공개 배포 절차 | ACME staging 예행연습 경로, 외부 검증기(리다이렉트·HSTS·헤더·인증서 만료·내부 포트), 갱신 감시 cron | `deploy/acme-staging.caddy`, `scripts/verify_public_deployment.py`, `docs/31` (2절 P0-4) |
| 비밀값 관리 | `*_FILE` 우선 조회 + Docker file secrets. 이미지·환경변수·저장소에 값이 남지 않음 | `app/core/runtime_secrets.py` |
| 저장 데이터 보호 | FinancialProfile 애플리케이션 레벨 암호화, 키 로테이션 경로 | `app/security/profile_encryption.py`, `adr/0002` |
| 로그 개인정보 | 로그 필드 allowlist 고정. 쿼리·본문·경로 파라미터가 구조적으로 로그에 없음 | `app/core/observability.py`, `tests/test_observability.py` |
| HTTP 보안 경계 | 보안 헤더, same-origin 상태 변경 보호, trusted host | `app/core/http_security.py`, `docs/26` |
| 요청 한도·본문 크기 | IP 기준 rate limit(429 + `Retry-After`), 파싱 이전 본문 상한, 카운터는 HMAC 버킷으로 PostgreSQL 저장 | `app/core/rate_limit.py`, `app/core/request_limits.py`, `web/lib/api/request-body.ts` (2절 P0-1) |
| 만료 데이터 정리 | 전용 컨테이너가 주기 실행. 성공 시각 heartbeat 기반 healthcheck, 로그는 건수·성공 여부만 | `app/services/data_retention.py`, `scripts/run_retention_scheduler.py`, `compose.yaml` (2절 P0-2) |
| 모바일 진입 | PWA manifest, 공유 시트 `share_target`(POST — 원문을 주소에 싣지 않는다), 오프라인 셸, 설치 유도 | `web/app/manifest.ts`, `web/app/check/shared/route.ts`, `web/public/sw.js` (5절) |
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
| 창 계산 | `app/services/rate_limits.py` | **epoch 정렬 고정 창.** 창이 닫히기 직전과 열린 직후에 몰아치면 짧은 순간 한도의 **2배** 가 통과한다. 목적이 공정 분배가 아니라 지속적 남용 차단이라 받아들였고, 가정이 굳지 않도록 `test_a_client_can_burst_twice_the_limit_across_a_boundary` 로 고정했다 |
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

### P0-3. 백업 자동화와 복원 리허설 — 완료 (2026-08-17)

문제였던 것이 둘이다. 하나는 알고 있던 것이고, 하나는 작업하다 발견했다.

**(1) 운영 백업 스케줄이 없었다.** `pg_dump`/restore 로직은 `scripts/verify_compose_runtime.py` 안, 즉 CI 검증 경로에만 있었다. 백업이 없는 상태와 "백업 코드가 있는" 상태는 복구 시점에 같은 결과가 된다.

**(2) 기존 복원 검사는 실패할 수 없었다.** 검사 조건이 이거였다.

```sql
SELECT position('2800000' in encode(encrypted_profile, 'escape')) = 0 FROM financial_profiles
```

"알려진 금융 값이 평문으로 보이지 않는다"만 본다. **무작위 바이트열도 통과한다.** 암호화가 됐다는 것만 확인할 뿐 되돌릴 수 있다는 것은 확인하지 못한다. 프로필은 애플리케이션 레벨 암호화라 키를 잃으면 DB를 완벽히 복원해도 열 수 없는 바이트열만 남는데, **그 상태의 백업이 이 검사에서 초록불로 나왔다.** 즉 P0-3이 요구한 "복원이 성공한다"를 기존 검사는 측정할 능력이 없었다.

구조:

| 부분 | 파일 | 판단 |
|---|---|---|
| 백업 루프 | `deploy/backup-loop.sh` | 주기 dump + 세대 회전 + 성공 heartbeat. 회전은 **dump 성공 뒤에만** 돈다 — 먼저 지우면 실패한 날 멀쩡한 세대를 하나 잃는다 |
| 컨테이너 | `compose.yaml`의 `backup` | `db`와 **같은 이미지 digest**. `pg_dump`는 서버보다 major 버전이 낮으면 거부하므로 `x-postgres-image` anchor 한 곳에서만 정의해 어긋날 수 없게 했다 |
| 무결성 확인 | 같은 루프 | 새 dump에 `pg_restore --list`를 걸어 TOC가 읽히는지 본다. `pg_dump`가 0으로 끝나도 파일이 온전하다는 보장은 아니고, 여기서 안 걸러지면 **복원해야 하는 날에야** 알게 된다 |
| 복원 리허설 | `scripts/rehearse_backup_restore.py` | 임시 DB 생성 → 복원 → 복호화 → 정리. `pg_restore --exit-on-error` — 기본값은 오류를 세면서 계속 진행하고 0으로 끝나 **절반만 복원된 DB를 성공으로 읽는다** |
| 복호화 검증 | `app/services/backup_verification.py` | 합격 기준이 "행이 돌아왔다"가 아니라 **"행을 복호화했다"** |
| 운영 절차 | `docs/29` | DB 덤프와 암호화 키 중 **하나만 있으면 복구 불가**라는 점을 표로 먼저 적었다 |

**왜 sh와 python으로 갈랐는가.** postgres 이미지에는 python이 없다. `apk`로 넣으면 P0-5의 해시 고정 의존성 정책에 구멍이 난다. 그렇다고 backend 이미지에 postgres client를 넣으면 인터넷에 노출된 API 이미지에 덤프 도구가 실리고 서버와 맞출 버전이 하나 더 생긴다. 그래서 루프는 `sh`로 최소한만 두고, 진짜 확인이 필요한 복호화는 backend 이미지에서 python이 맡는다.

비밀번호는 `PGPASSWORD`로 넘기지 않는다. 환경변수는 `docker inspect`와 자식 프로세스 전체에 그대로 보인다. tmpfs 위의 `0600` pgpass 파일을 쓰고, 경로는 compose `environment:`에 둔다 — `docker compose exec`는 루프의 환경을 물려받지 않아서, 스크립트 안에서 export만 하면 복원 리허설의 `psql`이 비밀번호를 찾지 못한다.

이 컨테이너만 root로 돈다. postgres 이미지는 `USER`를 지정하지 않고, uid를 강제하면 호스트 bind mount 소유권과 어긋나 **백업이 조용히 실패한다.** 대신 `cap_drop: ALL` / `no-new-privileges` / `read_only` / 포트 미개방으로 막았다.

검증 결과:

| 확인 | 방법 | 결과 |
|---|---|---|
| 실제로 백업이 뜨는가 | 짧은 주기로 compose 기동 | `{"status":"succeeded","bytes":8093,"generations":1,"pruned":0}` |
| 세대 회전 | 가짜 `pg_dump`를 PATH 앞에 두고 실제 `sh`로 구동 | `KEEP=3`에서 오래된 것부터 삭제, 최신 3개 유지 |
| 실패가 세대를 지우지 않는가 | dump 실패 주입 | 기존 3세대 그대로. `.tmp` 잔여물 없음 |
| 중단된 쓰기 | `*.tmp`를 세대로 세는지 | 세지 않음. 세면 실제 보관 수가 조용히 줄어든다 |
| 깨진 dump | `pg_restore --list` 실패 주입 | 파일 폐기, `"stage":"verify"` |
| heartbeat | 실패 → 성공 → 실패 | 성공만 기록. 실패는 이전 성공 시각을 건드리지 않음 |
| healthcheck | heartbeat 없음 / 신선 / 두 주기 경과 / 손상 | exit 1 → 0 → 1 → 1 |
| 설정 오류 | 주기 5초, `keep=0`, 정수 아닌 값, 비밀번호 파일 없음 | 전부 exit 2 + `"status":"misconfigured"` |
| 비밀번호 노출 | 로그·stdout에서 검색 | 없음. pgpass 파일에만 존재 |
| **키를 잃은 백업** | 다른 키로 복원 검증 | `failed=1`, `unavailable_key_ids`에 해당 key id. **옛 검사는 여기서 통과했다** |
| 무작위 바이트열 | 옛 기준 / 새 기준 대조 | 옛 기준 통과, 새 기준 실패 |
| 빈 복원 | 행 0건 | `recoverable=false`. 증명한 게 없으면 합격이 아니다 |
| 행 결합 파손 | 봉투의 `profile_id`를 다르게 | 실패. 키는 멀쩡하므로 `unavailable_key_ids`는 비어 있음 |
| 키 로테이션 | 두 세대 키로 쓰인 행 | 둘 다 있으면 전부 열림. 옛 키를 내리면 그 행만 실패 |
| 출력 PII | 리허설 출력에서 금융 값 검색 | 건수와 key id뿐. key id는 이미 행에 평문으로 있는 값 |
| pgpass가 다른 DB에도 통하는가 | 데이터베이스 칸 검사 + `psql -d postgres` | `db:5432:*:finshield_app:…`, `SELECT 1` → `1` |
| 전체 실기동 | `verify_compose_runtime.py` (주기 60초) | `"backup_schedule": {"decrypted": 1, "dump": "finshield-20260817T022522Z.dump", "healthy": true, "scheduled_within_interval_seconds": 60}` |
| 회귀 | `pytest -q` | 417 passed, 1 skipped (+34) |

**CI 검증도 갈아치웠다.** `verify_compose_runtime.py`가 직접 `pg_dump`를 부르던 부분을 지우고, `backup` 서비스가 **제 주기에 남긴** 최신 파일을 기다렸다가 복원 리허설에 넘긴다. P0-2에서 배운 것과 같다 — 스크립트를 한 번 돌려보는 것은 스케줄이 걸려 있다는 확인이 아니다. 검증기가 직접 덤프를 뜨면 백업 스케줄이 아예 없어도 통과한다. CI는 이를 위해 `FINSHIELD_BACKUP_INTERVAL_SECONDS=60`으로 스택을 띄운다.

남은 것 두 가지. **(1) 백업이 아직 같은 호스트 안이다.** `./backups`는 `postgres-data` 볼륨 밖이라 볼륨 손상에는 안전하지만 호스트가 통째로 사라지면 같이 사라진다. P0-4 가 닫혔으므로 이제 이것이 다음 차례다. **(2) 암호화 키 보관은 사람이 하는 절차이고 자동 점검이 없다.** 리허설이 통과하는 이유는 지금 이 호스트에 키가 있기 때문이지 키가 안전하게 보관돼 있기 때문이 아니다. 키를 덤프와 같은 곳에 두면 백업 하나 유출로 프로필이 통째로 열리므로, 자동화 대신 `docs/29` 0절에 절차로 적었다.

**(2)는 2026-08-19 에 수행됐다** — VM 의 `secrets/` 가 `drwx------` 인 것을 확인하고, `profile_encryption_keys.txt` 를 호스트 밖 암호 관리자로 옮겼다. 자동 점검이 없다는 사실은 그대로다. 그래서 (1)의 GCS 반출을 할 때 **키를 같은 버킷에 넣지 않는 것**이 사람이 지켜야 할 조건으로 남는다. 상태 표는 `docs/29` 0절.

### P0-4. 실도메인·DNS·TLS 실환경 검증 — 완료 (2026-08-18)

`docs/devlog/2026-08-13/`가 명시한 미완료 항목이다. Caddy 설정과 compose는 검증됐지만 실제 도메인·DNS·인증서 발급은 한 번도 돌지 않았다. 자동 인증서는 DNS가 실제로 가리키기 전에는 검증할 수 없다.

- 도메인 확정 → DNS A/AAAA → `FINSHIELD_DOMAIN` 주입 → 인증서 자동 발급 확인
- 외부에서 HTTP→HTTPS 리다이렉트, HSTS, TLS 등급 측정
- 인증서 갱신 실패 시 알림 경로 (갱신은 60일 뒤에 조용히 실패한다)
- 완료 기준: 외부 네트워크에서 실제 도메인으로 전 주요 화면 동작

#### 도메인 없이 끝낸 것 (2026-08-17)

도메인은 사용자가 정해야 하지만, **도메인이 정해진 날 무엇을 어떻게 하고 무엇으로 확인할지**는 미리 만들 수 있다. 절차 전체는 `31-public-deployment.md`.

| 부분 | 파일 | 왜 지금 하는가 |
|---|---|---|
| ACME 연락처 필수화 | `deploy/Caddyfile`, `compose.https.yaml` | 갱신 실패를 알려 줄 유일한 통로다. 선택값으로 두면 아무도 안 보는 주소로 배포가 성공한다. 비면 Caddy가 기동을 거부하는 것까지 확인했다 |
| staging 예행연습 경로 | `deploy/acme-staging.caddy`, `compose.acme-staging.yaml` | Let's Encrypt 운영 한도(검증 실패 5회/시간, 중복 인증서 5장/주)는 **한도를 태운 뒤에** 알게 된다. 첫 발급 당일에 만들 수 있는 물건이 아니다 |
| proxy healthcheck | `compose.https.yaml` | 실제 SNI로 자기 자신에 붙는다. "프로세스는 살아 있는데 발급에 실패한" 상태를 healthy로 보고하지 않는다 |
| 외부 검증기 | `scripts/verify_public_deployment.py` | 완료 기준을 문장이 아니라 종료코드로 만든다 |
| 판정 기준 | `app/core/public_deployment.py`, `tests/test_public_deployment.py` | 판정을 순수 함수로 빼서 네트워크 없이 기준 자체를 테스트한다 (P0-3의 교훈) |

`acme_ca`를 기본값으로 박지 않은 것이 이 설계의 핵심이다. 명시하면 기본 발급자 **두 개(Let's Encrypt + ZeroSSL 대체)가 모두 그 하나로 대체된다.** adapt 결과로 확인했다. 그래서 staging은 환경변수가 아니라 mount되는 파일이고, 연습 중이라는 사실이 `-f` 하나의 존재로 드러난다.

localhost 예행연습(Caddy 내부 CA, ACME 무관) 실측: 27개 검사 중 4개 실패, 그 4개는 전부 예행연습 고유 항목(12시간짜리 내부 인증서 1개 + 로컬 개발용으로 publish된 내부 포트 3개)이었다. 리다이렉트·HSTS·보안 헤더·주요 화면 9개·PWA 3종·공유 시트 왕복은 전부 통과했다. 액세스 로그가 요청 경로를 남기지 않는 것도 같은 실행에서 확인했다(`adr/0004`).

**2026-08-18, 실제로 발급됐다.** `https://finshield-ai.duckdns.org` 가 Let's Encrypt 운영 인증서로 서비스 중이다. staging 예행연습을 먼저 거쳤고, 그 사이 백엔드가 서 있던 덕분에 발급 시도가 0회여서 운영 쿼터를 한 건도 쓰지 않았다.

| 확인 | 결과 |
|---|---|
| HTTP → HTTPS | `308 Permanent Redirect`, `Server: Caddy` |
| 체인 검증 (VM 밖에서) | `Verify return code: 0 (ok)` |
| 발급자 | `"issuer":"acme-v02.api.letsencrypt.org-directory"`, challenge `http-01` |
| 화면 | `/`, `/check`, `/onboarding` 이 HTTPS 로 200 |

도메인은 비용 0 을 조건으로 **DuckDNS 무료 서브도메인**을 썼다. 사기 방어 제품에 어울리는 이름은 아니다 — 그 도메인 계열을 피싱 호스트로 차단하는 곳이 있다. 돈이 생기면 바꾼다. 판단 근거는 `31-public-deployment.md` 11-6.

**검증기 실행 결과: 27개 전부 통과, 실패 0, 종료코드 0** (2026-08-18, VM 밖의 개발 PC 에서). 이 항목의 완료 기준은 문장이 아니라 이 종료코드였고, 이제 그것을 봤다.

localhost 예행연습에서 실패했던 4건이 전부 뒤집혔다. 그 4건은 예행연습 고유 항목이었으므로 이것이 정상이다.

| 예행연습에서 | 실환경에서 |
|---|---|
| `certificate_expiry` — 12시간짜리 내부 인증서 | 89일 남음 (만료 2026-11-16) |
| `certificate_trusted` — 내부 CA 라 검증 불가 | 체인·호스트명 검증 통과, TLSv1.3 |
| `internal_port` 18000 / 13000 / 5432 열림 | **세 개 다 밖에서 닫힘** |

마지막 줄이 특히 이번에 처음 실증된 것이다. 지금까지 "loopback 바인딩 + 방화벽" 은 설정으로만 참이었고, 밖에서 두드려 본 적이 없었다.

**남은 것: 외부 TLS 등급 측정** (SSL Labs 등). 검증기는 프로토콜 버전과 체인까지 보지만 암호 스위트 등급을 매기지는 않는다. 공개는 이 항목에 걸려 있지 않다.

서버는 **GCP Compute Engine** 으로 간다(2026-08-17 결정). Cloud Run 은 파일시스템이 요청 단위로 사라지고 상시 실행 루프를 둘 수 없어 PostgreSQL·백업·retention 을 전부 다시 짜야 하는데, 공개를 그 재작업 뒤로 미룰 이유가 없다. 사양·방화벽·고정 IP 판단은 `31-public-deployment.md` 11절.

머신은 **always-free `e2-micro`(us-west1-b, 오리건)** 로 간다(2026-08-18 결정). $300 크레딧을 받지 못한 계정이라 상시 비용이 사실상 0 인 구성이 이것뿐이다. 대가가 둘 있다. 무료 리전이 미국 3곳뿐이라 한국에서 왕복 110ms 대이고, 1GB 로는 **Next 빌드가 반드시 죽는다.** 후자 때문에 이미지를 GitHub Actions 에서 빌드해 `ghcr.io` 로 올리고 VM 은 pull 만 해야 하는데, 그것이 아래 P1-3 이다. **즉 P1-3 이 P0-4 의 선행조건이 됐다.** 상세는 `31-public-deployment.md` 11-1.

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

### P1-1. 장애 알림과 에러 추적 — 인증서 만료만 완료 (2026-08-19)

`/metrics`가 Prometheus 텍스트를 내지만 수집하는 쪽이 없다. 지금 구조에서는 장애를 사용자가 먼저 안다. 최소한 헬스체크 실패, 5xx 급증, 외부 공식 API 실패율 상승에 대한 알림이 필요하다. 에러 추적을 붙일 때 **로그 allowlist 원칙을 깨지 않는지** 반드시 확인한다 — 대부분의 에러 추적 SDK는 기본값으로 요청 본문을 보낸다.

이 중 **인증서 만료 하나만** 먼저 붙였다. 나머지보다 급해서가 아니라, 실패했을 때 **되돌릴 시간이 가장 짧기** 때문이다. 5xx 급증은 겪는 즉시 알게 되지만, 갱신 실패는 만료 당일까지 아무 증상이 없다가 그날 사이트 전체가 브라우저 경고 뒤로 사라진다. 첫 갱신 시점은 2026-10-17 무렵이다(`docs/31` 10절).

#### 무엇을 만들었나

판정 로직은 새로 쓰지 않았다. `app/core/public_deployment.py`의 `evaluate_certificate`와 기준(`CERTIFICATE_WARN_DAYS = 21`, `CERTIFICATE_FAIL_DAYS = 7`)이 P0-4 때 이미 들어가 있었고, `scripts/verify_public_deployment.py --certificate-only`가 그걸 부른다. **없던 것은 주기와 알림 경로 둘뿐이었다.**

| 파일 | 역할 |
|---|---|
| `.github/workflows/certificate-watch.yml` | 매일 02:17 UTC 에 검사기를 `--certificate-only` 로 돌린다 |
| `tests/test_certificate_watch.py` | 그 배선이 끊기지 않았는지 검사한다 (5건) |

**VM 밖에서 돈다는 것이 설계의 전부다.** VM 안 cron 으로 두면 VM 이 죽었을 때 감시도 같이 죽어서, 정작 가장 알아야 할 장애를 못 잡는다. GitHub 러너는 별개 시스템이라 호스트가 통째로 사라져도 검사가 돌고 실패한다.

테스트는 워크플로 YAML 을 읽어 네 가지를 본다 — `schedule` 트리거가 있는가, 주기가 21일 창 안에 최소 3번 들어가는가, `--insecure`가 안 붙었는가(붙으면 체인 검증을 건너뛰어 **검사가 실패할 수 없게 된다**), 도메인을 `run:` 문자열이 아니라 `env:`로 넘기는가. 다섯 가지 변이를 실제로 주입해 전부 잡히는 것을 확인했다(`schedule` 제거 / 주간 cron / `--insecure` / `${{ }}` 인라인 / `contents: write`).

그 테스트는 배선만 본다. **검사기가 정말 빨간불을 낼 수 있는지는 만료된 인증서에 직접 물어봤다.**

| 도메인 | 결과 | 종료코드 |
|---|---|---|
| `finshield-ai.duckdns.org` | 3개 통과 (`89일 남음, 만료 2026-11-16`) | 0 |
| `expired.badssl.com` | `certificate_trusted`·`certificate_expiry` 실패 (`4147일 전에 만료됐다`) | **1** |

종료코드가 1이어야 워크플로가 실패하고, 실패해야 알림이 나간다. 문장이 아니라 이 숫자가 P0-4 를 닫은 근거와 같은 종류의 근거다. 만료 항목뿐 아니라 체인 검증까지 함께 걸린 것도 확인했다 — `--insecure` 가 붙었다면 두 번째 줄이 통과로 바뀐다.

#### 알림이 실제로 도착하려면 — 계정 쪽 설정이 필요하다

워크플로가 실패해도 **자동으로 아무에게도 안 간다.** 예약 워크플로의 실패 알림은 GitHub 이 보내는데, 조건이 두 개다.

1. 수신자는 **cron 을 마지막으로 수정한 사용자**다. 저장소 소유자도, 최근 커미터도 아니다.
2. 계정의 Settings → Notifications → Actions 에서 이메일 수신이 켜져 있어야 한다. 여기 "Only notify for failed workflows" 옵션이 있고, 이 워크플로는 성공하는 날이 압도적으로 많으므로 그 옵션을 켜는 편이 낫다.

둘 중 하나라도 어긋나면 워크플로는 매일 정상적으로 실패하면서 아무도 모르는 상태가 된다. **이 문서를 읽는 시점에 한 번은 직접 확인해야 하는 항목이다.**

#### 이 방식이 조용히 죽는 방법 두 가지

첫째, **공개 저장소의 예약 워크플로는 저장소가 60일간 활동이 없으면 자동 비활성화된다.** push·릴리스·PR 병합은 타이머를 되돌리지만 이슈 댓글이나 star 는 아니다. 개발이 멈춘 채로 운영만 하는 기간이 두 달을 넘기면 — 즉 감시가 가장 필요해지는 상황에서 — 감시가 먼저 꺼진다. 비활성화 알림은 오지만, 그것도 위 알림 설정에 걸려 있다.

둘째, 알림 경로가 GitHub 하나뿐이다. GitHub 이 안 보내면 대안이 없다.

그래서 **UptimeRobot 같은 외부 감시를 함께 걸어 두는 것이 원래 계획**이고(이번 작업의 채널 선택도 그쪽이었다), 아직 안 걸었다. 둘은 겹치는 게 아니라 서로의 사각을 덮는다.

| | 워크플로 | 외부 감시(UptimeRobot 등) |
|---|---|---|
| 무엇을 보나 | 만료일 + 체인 신뢰 + TLS 버전 | 만료일, 사이트 응답 |
| 저장소 활동에 의존하나 | **한다** (60일 규칙) | 안 한다 |
| 알림 경로 | GitHub 이메일 설정에 의존 | 자체 발송 |
| 버전 관리되나 | 된다 (기준·근거가 코드 옆에) | 안 된다 (콘솔 설정) |

#### 남은 것

사이트 다운, 5xx 급증, 외부 공식 API 실패율 상승은 그대로 남아 있다. 헬스체크 실패를 컨테이너 밖으로 알리는 경로도 아직 없다(위 P0-2 참조).

### P1-2. Audit log

계정 삭제, 프로필 변경처럼 되돌릴 수 없는 동작의 기록이 없다. `docs/10`에서 "identity와 보존 정책 필요"로 미뤄둔 항목이다. 익명 세션 모델 위에서 무엇을 남길 수 있는지부터 정해야 한다. 감사 로그가 개인정보 보존기간 정책과 충돌하지 않게 설계한다.

### P1-3. 배포·롤백 절차 — HTTPS 공개까지 확인 (2026-08-18), 태그 경로·롤백 미검증

수동 배포에는 되돌릴 대상 자체가 없었다. 태그 붙은 이미지가 없으니 "이전 버전"이라는 게 가리킬 곳이 없고, 되돌리려면 이전 커밋을 다시 빌드해야 하는데 그 빌드는 1GB VM 에서 죽는다. 그래서 이번 작업은 롤백 절차를 문서로 적는 대신 **되돌릴 수 있는 물건을 먼저 만드는** 쪽으로 갔다.

| 파일 | 역할 |
|---|---|
| `.github/workflows/release.yml` | `v*` 태그를 밀면 `finshield-backend` / `finshield-web` 을 만들어 `ghcr.io` 로 올린다 |
| `compose.deploy.yaml` | 네 서비스의 `build:` 를 `!reset` 으로 지우고 `ghcr.io` 이미지를 박는다 |
| `tests/test_deploy_images.py` | 두 파일의 대응 관계를 검사한다 (21건) |
| `.github/workflows/ci.yml` | 배포 조합의 `config --quiet` + 태그 없을 때 거부 확인 |
| `tests/test_backend_workers.py` | backend 를 어떤 프로세스 모양으로 띄우는지 검사한다 (8건) |

마지막 줄은 첫 실배포에서 나온 것이다. `up -d` 로 전부 동시에 올리자 backend 가 **영구히 굳었다** — uvicorn 이 워커를 spawn 하는데 부모는 5초 안에 ping 응답이 없으면 SIGKILL 하고 새 워커를 띄우는 구조라, 기동 경합이 자기강화 루프가 됐다. SIGKILL 이라 트레이스백도 없다. 워커 수를 호스트가 정하게 빼고 `--timeout-worker-healthcheck` 를 올려 고쳤다. 기전과 실측은 `31-public-deployment.md` 11-6.

#### 왜 `latest` 를 쓰지 않는가

`compose.deploy.yaml` 은 `${FINSHIELD_IMAGE_TAG:?...}` 로 태그를 **필수**로 받는다. 기본값이 없으니 태그를 빼면 `docker compose` 가 거부한다. `release.yml` 도 `latest` 태그를 붙이지 않는다.

`latest` 는 편의를 주고 되돌릴 능력을 가져간다. 지금 무엇이 돌고 있는지 모르면 "이전 것으로 돌린다" 를 실행할 수 없다. 사고 조사 중에 그 사실을 알게 되는 것이 최악이라, 불편한 쪽을 택했다. 같은 이유로 `release.yml` 은 빌드 digest 를 job summary 에 남긴다 — 태그는 옮겨 붙을 수 있고 digest 는 그렇지 않다.

#### 마이그레이션을 되돌리는 문제

여기가 실제 어려운 부분이고, 이번에 코드로 해결하지 못한 부분이다.

`compose.yaml` 의 `migration` 서비스는 `alembic upgrade head` 를 돌고 끝난다. 즉 새 이미지를 올리면 스키마가 먼저 바뀌고 그다음 앱이 뜬다. 되돌릴 때 이 순서를 뒤집을 수 없다 — **스키마 변경과 코드 배포는 같은 순간에 되돌아가지 않는다.**

그리고 지금 `migrations/versions/` 의 `downgrade()` 들은 전부 `drop_table` / `drop_index` / `drop_constraint` 다. 즉 **`alembic downgrade` 는 되돌리기가 아니라 데이터 삭제다.** 사고 대응 중에 실행할 명령이 아니다.

그래서 규칙을 이렇게 정한다.

1. **롤백 = 이전 태그로 다시 올린다.** `alembic downgrade` 가 아니다. 스키마는 그대로 두고 코드만 되돌린다.
2. **그러려면 마이그레이션이 이전 이미지에서도 안전해야 한다.** 새 스키마 위에서 구버전 코드가 돌 수 있어야 롤백이 성립한다. 이것이 expand/contract 다.
   - **expand**: 컬럼·테이블 추가는 nullable 또는 기본값 있음. 새 코드는 이것을 쓰기 시작하고, 구 코드는 무시한다.
   - **contract**: 컬럼 삭제·이름 변경은 **그 컬럼을 안 쓰게 된 릴리스에서 하지 않는다.** 한 릴리스 이상 지나 롤백 대상에서 벗어난 뒤에 별도 릴리스로 뺀다.
   - 이름 변경은 rename 이 아니라 "추가 → 양쪽 쓰기 → 읽기 이전 → 삭제" 로 쪼갠다. rename 은 구 코드를 즉시 깨뜨려 롤백 경로를 없앤다.
3. **`downgrade()` 는 유지하되 수동 조작 전용으로 둔다.** 자동 배포 경로에서 절대 부르지 않는다. 부를 일이 생기면 백업 먼저(`docs/29`), 리허설 먼저.
4. **파괴적 마이그레이션은 릴리스를 혼자 쓴다.** 코드 변경과 섞지 않는다. 그래야 문제가 생겼을 때 무엇을 되돌리는지가 분명하다.

이 규칙의 대가는 컬럼 하나 지우는 데 릴리스가 두 번 필요하다는 것이다. 받아들인다 — 되돌릴 수 없는 배포를 하는 것보다 낫다.

#### ghcr 패키지 공개 범위 (배포 전에 반드시 확인)

첫 실행에서 두 패키지 모두 **public 으로 생성됐다** (2026-08-18 실측). 저장소가 public 이라서로 보이지만 인과는 확인하지 못했으므로, 배포 전 확인 절차는 그대로 남긴다 — private 으로 생성되면 VM 에서 `docker compose pull` 이 인증 오류로 죽고, 원인이 코드에 없어서 한참 헤맨다. 확인 명령은 `docs/31` 3-2 절에 있다(익명 토큰으로 `tags/list`, `200` 이면 public). private 이면 둘 중 하나를 택한다.

- 패키지 설정에서 공개로 바꾼다 (이미지에 비밀이 없다는 전제. 우리 이미지는 secrets 를 런타임 mount 로 받으므로 해당).
- 또는 VM 에서 `read:packages` 만 가진 PAT 으로 `docker login ghcr.io` 한다.

#### 여기까지 확인된 것 (2026-08-18)

`release.yml` 을 `workflow_dispatch` 로 한 번 돌렸다 (run #1, main `1809997`, 2분 14초, backend/web 두 job 모두 성공). 이미지가 ghcr 에 올라갔고, 로컬에서 `FINSHIELD_IMAGE_TAG=sha-1809997… docker compose -f compose.yaml -f compose.deploy.yaml pull` 이 성공했다. digest 와 매니페스트 형태는 devlog 에 남겼다.

**그리고 실제 e2-micro 에 올렸다 (2026-08-18).** 이것이 이 절의 가장 큰 미지수였다 — 1GB 에서 이 스택이 도는지는 문서로 답할 수 없는 질문이었다. 도는 것을 확인했다. 측정값은 `docs/31` 11-6.

| 확인 | 결과 |
|---|---|
| `docker compose pull` (VM) | 성공. backend 331MB / web 303MB |
| 컨테이너 5개 상태 | 전부 `healthy` (`migration` 은 `exited (0)`) |
| `/health`, `/health/ready` | `ok`, `ready` |
| `backup` 첫 dump | `backups/finshield-…Z.dump` 8093B, `root:root`. **`cap_add: DAC_OVERRIDE` 가 실기에서 처음 검증됐다** — 지금까지는 리눅스 CI 에서만 확인한 수정이다 |
| 메모리 | 컨테이너 합계 326MiB, `available` 234MiB, 활성 스와핑 없음(`vmstat` si/so = 0) |
| 재부팅 복구 | swap 이 `/etc/fstab` 으로 자동 복구, 컨테이너 5개 자동 기동, **39초 만에 `ready`**. 다만 `backup` 은 여기서 걸렸다 — 아래 참고 |

**재부팅 테스트가 백업 루프의 결함을 하나 찾았다.** 데이터도 도메인도 없는 시점에 재부팅해 본 이유가 이것이다. 상세와 수정은 `docs/31` 11-6 및 해당 devlog.

#### 아직 안 된 것

- **태그 push 경로는 안 돌려 봤다.** run #1 은 수동 실행이라 `type=ref,event=tag` 가 아무 태그도 만들지 않았고, 붙은 태그는 `sha-…` 하나뿐이다. `v*` 태그를 미는 순간의 동작은 미검증이다.
- **HTTPS 를 얹은 상태는 미검증이다.** 위 측정은 `compose.yaml` + `compose.deploy.yaml` 조합이고 포트는 전부 loopback 바인딩이었다. `compose.https.yaml` 의 Caddy 가 더해지면 30~50MiB 가 추가로 든다 — `available` 234MiB 안에 들어가지만 여유가 그만큼 줄어든다. 도메인이 정해져야 확인할 수 있다.
- **부하를 준 적이 없다.** 위 숫자는 전부 idle 이다. 동시 요청이 들어왔을 때 uvicorn worker 2개와 Next 가 얼마나 더 먹는지는 모른다.
- 롤백 리허설 없음. `docs/29` 의 복원 리허설처럼 실제로 되돌려 보는 절차가 필요하다.
- expand/contract 를 강제하는 검사 없음. 지금은 규칙일 뿐이고, 어기면 리뷰에서만 걸린다.

### P1-4. nonce 기반 strict CSP

`docs/26`의 남은 항목. Next.js standalone과 함께 쓸 때 nonce 전달 경로를 확인해야 한다.

### P1-5. 의존성 버전 상승 관측

P0-5로 버전은 고정했지만, 고정은 그 자체로 위험을 만든다. lock은 사람이 `--upgrade`를 붙일 때만 움직이므로 취약점 패치가 나와도 저장소는 조용하다. Dependabot(`pip` + `npm` + `docker`) 또는 주기적 `--upgrade` PR로 **상승 사실을 알리는 경로**를 만든다. 자동 병합은 하지 않는다. `deps-lock` job이 이미 lock 무결성을 검증하므로, 필요한 것은 알림뿐이다.

## 4. P2 — 제품·대회 완성도

배포와 무관하지만 이 프로젝트의 주장을 증명하는 부분이다.

### P2-1. 평가 하네스 — bootstrap 완료 (2026-08-13)

이 항목이 처음 쓰일 때는 저장소에 평가 코드가 한 줄도 없었고, "hybrid 가 더 안전하고 정확하다"는 이 프로젝트의 논지를 뒷받침하는 숫자가 하나도 없었다. 지금은 `evaluation/` 이 있다.

- `evaluation/fraud_golden.py` — 합성 61건 골든셋. 7개 UserState 를 상태당 최소 3건 덮는다. **비합성 케이스는 `ValueError` 로 거부한다**
- `evaluation/fraud_benchmark.py` — precision/recall/F1, class별 recall, 신호 coverage, scenario 일치율, evidence coverage. 최저 품질 gate 포함
- `scripts/evaluate_fraud_engine.py` — 재현 가능한 진입점, p50/p95 실측
- `tests/test_fraud_evaluation.py` — gate 와 **알려진 오답 3건(fg-046/047/049)이 보고서에서 사라지지 않는지**를 고정한다

Rule-only 베이스라인은 이것으로 확보됐다. 남은 것 셋이다.

- **held-out v0.2** — 현재 데이터는 non-held-out 이라 보고서가 `dataset.held_out = False` 를 그대로 싣는다. 독립 작성·동결이 필요하다
- **LLM-only 측정** — 보고서가 `llm_only.status = "not_run"` 이고 사유가 "고정된 model·prompt·provider 계약이 없다" 이다. 즉 P2-2 의 어댑터가 선행이다
- **Hybrid 비교** — `proposed_hybrid.status = "not_implemented"`

### P2-2. LLM 설명 계층 — 계약 경계와 AI Studio 프로바이더 착지 (2026-08-18), 미측정

`app/services/llm/` 에 설명 계층의 경계가, `app/clients/google_ai_studio.py` 에 실제 프로바이더가 들어왔다. **아직 한 번도 실행하지 않았다** — 키를 꽂은 적이 없고, 어떤 라우트에도 연결돼 있지 않으며, 벤치마크도 돌리지 않았다. 프론트의 설명 텍스트는 여전히 mock 계층에서 온다.

| 파일 | 역할 |
|---|---|
| `contract.py` | provider·model·prompt sha256 고정. 셋 중 하나라도 바뀌면 그 전 측정값은 이 시스템을 설명하지 않는다 |
| `prompts.py` | 고정 프롬프트 본문 |
| `minimization.py` | 주민등록번호·카드·계좌·전화·이메일을 자리표시자로 치환. 금액·기관명·URL 은 남긴다 |
| `validation.py` | 근거에 없는 연락처, URL, 주민등록번호 형태를 거른다 |
| `provider.py` | `LlmProvider` Protocol 과 나간 프롬프트를 기록하는 `StubProvider` |
| `explanation.py` | 고정 계약 인스턴스와 `explain_analysis` |
| `app/clients/google_ai_studio.py` | 실제 프로바이더. 키는 헤더로, 실패는 전부 `LlmUnavailable` 로 |

경계를 **어떻게** 강제하는지가 핵심이다. `explain_analysis` 는 `AnalyzeResponse` 를 받아 `str | None` 을 돌려준다. 모델 출력이 위험 수준·점수·시나리오·권고 행동에 닿을 경로가 타입에 존재하지 않는다. 주석이나 프롬프트 지시가 아니라 함수 서명이 `CLAUDE.md` 의 첫 번째 non-negotiable 을 지킨다. 프로바이더가 죽으면 설명만 비고 판정은 그대로 나간다.

프롬프트 해시는 프롬프트에서 계산하지 않고 리터럴로 적어 뒀다. 계산하면 항상 일치해서 아무것도 증명하지 못한다 — busybox `[ -w ]` 와 백업 SQL 검사에서 이미 두 번 밟은 함정이다. 프롬프트를 한 글자 고치면 `tests/test_llm_contract.py` 가 깨지고, 고친 사람이 벤치마크를 다시 돌리게 되는 것이 의도다.

출력 검증의 허용 연락처 목록은 따로 두지 않고 **모델에게 보여 준 근거에서 그때그때 뽑는다.** 별도 목록을 두면 근거와 어긋나는 날이 오고, 그날 정당한 설명이 거부되거나 지어낸 신고번호가 통과한다. 가짜 번호를 안내하는 것은 이 서비스가 낼 수 있는 가장 나쁜 출력이다. 사용자가 실제로 그 번호로 전화를 건다.

검증 32건은 전부 가짜 프로바이더로 돈다(`tests/test_llm_contract.py`). 네트워크가 필요한 검사였다면 CI 에서 꺼졌을 것이고, 꺼진 검사는 없는 검사다.

**남은 것:** 키 발급과 `secrets/gemini_api_key.txt` 배치, `evaluation/` 연결로 `llm_only.status` 를 `not_run` 에서 옮기기, 안전 필터 차단율 측정, prompt injection 골든셋, 라우트 연결(그때 비동기 경계를 다시 본다 — 지금 프로바이더는 동기다). 사람 이름과 주소는 한국어에서 신뢰할 만하게 잡히지 않아 최소화 계층이 걸러 주지 못한다 — 이 계층은 "덜 보낸다" 이지 "안전하다" 가 아니다.

#### 프로바이더 — 유료 등급 (2026-08-18, 앞선 판단 정정)

**AI Studio 유료 등급을 쓴다.** 선불 크레딧 ₩70,000 이 계정에 들어 있어 Gemini API 호출은 처음부터 유료 등급으로 나간다.

이 절의 앞 판단은 틀렸다. 원래 "무료 등급으로 벤치마크하되 제출물이 제품 개선에 쓰일 수 있으니 합성 골든셋만 보낸다" 로 적었는데, 크레딧이 있으면 애초에 무료 등급이 아니다. 2026-08-18 에 `https://ai.google.dev/gemini-api/terms` 를 직접 확인한 결과는 이렇다.

| | 무료 등급 | 유료 등급 |
|---|---|---|
| 제품 개선에 사용 | 사용한다 | **사용하지 않는다** |
| 사람 검토 | 있다 | 제품 개선 목적으로는 없다 |
| 보존 | 개선 목적 보존 | **남용 탐지·법적 대응 목적으로 제한된 기간** |

바뀌는 것과 안 바뀌는 것을 나눠 둔다.

- **바뀐다:** Vertex 로 서둘러 옮겨야 할 *데이터 사용* 사유는 사라졌다. 유료 등급에서는 프롬프트가 학습에 쓰이지 않는다.
- **안 바뀐다:** 최소화 계층은 그대로 필요하다. 유료 등급도 남용 탐지 목적으로 **제한된 기간 프롬프트와 응답을 로깅한다.** 주민등록번호를 보내지 않을 이유는 학습 여부와 무관하다.
- **안 바뀐다:** Vertex 로 옮길 *자격증명* 사유는 그대로다. AI Studio 는 만료 없는 API 키를 쓰고, GCE 에 서비스 계정을 붙이면 메타데이터 서버가 단기 토큰을 준다. 서버에 만료 없는 키 파일을 두는 순간 `docs/29` 0절이 막으려던 형태 — 백업 하나가 새면 전부 열리는 비밀 — 가 다시 생긴다. 이건 약관이 아니라 우리 쪽 사고 반경 문제라 유료 등급이라고 없어지지 않는다.

**비용은 제약이 아니다.** Gemini 2.5 Flash 기준 입력 $0.30 / 출력 $2.50 per 1M tokens 다. 골든셋 61건은 요청당 1천 토큰 남짓이라 한 번 돌리는 데 센트 단위다. 크레딧 ₩70,000 으로는 벤치마크를 수백 번 돌려도 남는다. 다만 **크레딧은 구매일로부터 1년 뒤 만료** 되므로 (₩62,000 은 2026-08-17 충전분, 2027-08-17 만료) 쓰지 않으면 그냥 사라진다.

**주의 하나.** 유료 등급은 계정이 아니라 **프로젝트** 에 붙는다. 키를 결제가 연결되지 않은 다른 프로젝트에서 만들면 그 키는 무료 등급이고 위 표의 왼쪽 열이 적용된다. 키를 발급할 때 AI Studio 가 해당 프로젝트를 유료로 표시하는지 확인해야 한다.

#### 프로바이더 구현에서 지킨 것

- **키는 헤더로 보낸다.** `x-goog-api-key` 다. 쿼리스트링에 실으면 URL 이 남는 모든 곳 — 로그, 프록시, 오류 보고서 — 에 키가 같이 남는다.
- **예외에 응답 본문을 넣지 않는다.** 400 응답이 요청 일부를 되돌려 주는 경우가 있어서, 상태 코드만 올린다. 키와 원문이 예외 메시지에 없다는 것을 테스트가 확인한다.
- **재시도하지 않는다.** 설명은 없어도 되는 것이다. 실패한 호출을 다시 보내면 지연만 늘고 유료 호출이 두 번 나간다.
- **잘린 문장을 보여 주지 않는다.** `finishReason` 이 `STOP` 이 아니면 (MAX_TOKENS·SAFETY·RECITATION) 설명 없이 간다. 반쯤 끊긴 안내는 없는 안내보다 나쁘다.
- **모든 실패가 `LlmUnavailable` 로 수렴한다.** 그래야 `explain_analysis` 에서 `None` 이 되고 판정이 그대로 나간다. 새 예외 타입이 새어 나가면 그 경로가 깨진다.
- 로거를 import 하지 않고, `follow_redirects=False` 다. 리다이렉트를 따라가면 키가 실린 요청이 우리가 고르지 않은 호스트로 간다.

**아직 안 본 것:** Gemini 안전 필터가 사기 문자를 얼마나 자주 막는지 모른다. 사기 분석 서비스가 사기 문자에서 거절당하면 실제 기능 문제인데, 측정 전에 `safetySettings` 를 낮추는 것은 순서가 틀렸다. 벤치마크에서 차단율을 먼저 재고, 그 숫자를 보고 정한다.

### P2-3. 접근성 실기기 검수

구조적 자동 회귀는 `web/components/a11y.test.tsx`가 상시 실행 중이다. 남은 것은 스크린리더 낭독, 명도대비 AA 실측, 실기기 iOS Safari 확인이다. 상세는 `docs/13` 9절.

## 5. 모바일 전략 — PWA 우선, 네이티브는 나중 (PWA 완료 2026-08-17)

사용자 대부분이 폰으로 쓸 것이라는 전제는 타당하다. 의심 문자를 받은 순간 쓰는 서비스이므로 폰이 기본 환경이다. 다만 **지금 필요한 것은 안드로이드 앱이 아니라 PWA다.**

이유는 UI가 아니라 인증 모델이다. 현재 세션은 `SameSite=Strict` + HttpOnly 쿠키에 trusted-host 허용목록이고 CORS 미들웨어가 없다 (`app/core/http_security.py`, `app/api/routes/auth.py`). **네이티브 앱이나 WebView 클라이언트는 이 인증을 그대로 쓸 수 없다.** 네이티브로 가려면 토큰 기반 인증, CORS 정책, 그리고 그에 딸린 위협 모델을 새로 만들어야 한다. 화면을 옮기는 작업이 아니라 보안 경계를 다시 세우는 작업이다.

PWA는 같은 오리진에서 돌기 때문에 지금 인증 모델을 그대로 쓴다. 얻는 것:

- 홈 화면 설치, 전체화면 실행 — 체감상 앱과 같다
- **Android 공유 시트 연동 (`share_target`)** — 문자 앱에서 의심 메시지를 바로 넘길 수 있다. 이 제품의 핵심 진입 경로다
- 배포 심사 없음, 스토어 계정 없음, 단일 코드베이스

포기하는 것: iOS의 공유 시트·푸시 제약, `READ_SMS` 자동 수집. 후자는 Play Store 제한 권한이라 어차피 심사를 통과하기 어렵고, `CLAUDE.md`의 PII 최소화 원칙과도 정면으로 충돌한다. 자동 수집은 하지 않는다.

작업 범위였던 것: manifest, 아이콘, `share_target` 라우트, 오프라인 셸(분석 결과는 캐시하지 않는다 — 민감 데이터다), 설치 유도 UI. **실도메인(P0-4) 앞에 넣는다.** HTTPS가 PWA 설치 요건이고, 공개 직후 바로 폰에 설치되는 편이 낫기 때문이다.

### 구현 결과 (2026-08-17)

전 범위 구현했다. 상세는 `docs/30`. 설계에서 하나가 계획과 달라졌다.

**`share_target`을 GET이 아니라 POST로 만들었다.** 일반적인 예제는 `method: "GET"`에 쿼리스트링으로 `text`를 받는다. 그러면 사용자가 받은 문자 원문이 브라우저 주소 기록·액세스 로그·`Referer`에 그대로 복사된다. `app/core/observability.py`가 쿼리와 본문을 구조적으로 로그에서 빼 둔 것(`docs/27`, `adr/0004`)이 프론트에서 무효화되는 셈이다. POST로 받고, 응답 문서에 실행되지 않는 JSON 태그로 담아 sessionStorage를 거쳐 `/check`로 넘긴다. 대가는 App Router의 `page.tsx`가 POST를 못 받아 Route Handler를 따로 만들어야 했다는 것뿐이다.

| 부분 | 파일 | 판단 |
|---|---|---|
| manifest | `web/app/manifest.ts` | `MetadataRoute.Manifest`가 `share_target`·`shortcuts`를 타입으로 보증한다 |
| 공유 수신 | `web/app/check/shared/route.ts` | 상태 변경·백엔드 호출·저장이 모두 없어서 **CSRF로 악용할 대상 자체가 없다**. 응답은 `no-store` + `noindex` |
| 본문 상한 | `web/lib/api/request-body.ts` | `request.formData()`를 바로 부르면 P0-1의 상한을 건너뛴다. 64KB까지 읽고 그 바이트만 파싱한다 |
| 서비스 워커 | `web/public/sw.js` | GET이 아닌 요청·교차 출처·`/api/*`에는 개입하지 않고, 화면 HTML은 캐시하지 않는다. 캐시에 남는 것은 해시 붙은 자산·아이콘·오프라인 화면뿐 |
| 오프라인 화면 | `web/app/offline/page.tsx` | "확인하지 못했다는 것이 안전하다는 뜻은 아닙니다"를 먼저 적는다 |
| 설치 유도 | `web/components/pwa/InstallHint.tsx` | 홈이 아니라 결과 화면에. 설치 가능 신호가 있을 때만 |

검증 결과:

| 확인 | 방법 | 결과 |
|---|---|---|
| manifest | 프로덕션 서버 `GET /manifest.webmanifest` | `share_target`이 POST/multipart, 아이콘 3종 |
| 공유 왕복 | 한글 문자 + URL multipart POST | 200, 원문 일치. 값은 주소가 아니라 본문 JSON 태그 안 |
| 적대적 입력 | `</script><script>alert(1)</script>` 공유 | 원문 그대로 왕복, 문서의 `</script>`는 2개 그대로 |
| 응답 잔존 | 헤더 검사 | `no-store, must-revalidate`, `noindex, nofollow`, `set-cookie` 없음 |
| 크기 상한 | 60,000자 multipart | 413, 파싱 전 거절 |
| 주소창 직접 접근 | `GET /check/shared` | 303 → `/check` |
| 워커 배포 | `/sw.js` 헤더 | `no-cache, no-store, must-revalidate` + `Service-Worker-Allowed: /` |
| 프론트 회귀 | `npm test` / `tsc --noEmit` / `lint` / `build` | 103 passed, 나머지 전부 통과 |
| 백엔드 무변경 | `pytest -q` | 417 passed, 1 skipped |

남은 것: **공유 시트에서 실제로 고르는 것은 아직 확인되지 않았다.** 설치와 서비스 워커는 HTTPS를 요구하므로 P0-4 이후에야 실기기에서 검증된다. iOS Safari는 `share_target`을 구현하지 않아 홈 화면 추가와 오프라인 화면까지만 얻는다.

Capacitor로 감싸는 선택지는 스토어 등록이 실제로 필요해질 때 다시 판단한다. 그 시점의 선결 조건은 위에 적은 토큰 기반 인증이다.

## 6. 권장 순서

```
0. 접근성 브랜치 병합 (작업 중 브랜치 정리)
1. P0-5 의존성 잠금        ← 완료 (2026-08-14)
2. P0-1 rate limit + 본문 크기 제한   ← 완료 (2026-08-15)
3. P0-2 만료 데이터 정리 자동화   ← 완료 (2026-08-15)
4. P0-3 백업 자동화 + 복원 리허설   ← 완료 (2026-08-17)
5. PWA (manifest + share_target)  ← 완료 (2026-08-17)
6. P1-3 배포·롤백 (밖에서 빌드, VM 은 pull)  ← e2-micro 실기동·HTTPS 확인 (2026-08-18), 태그 경로·롤백 미검증
7. P0-4 실도메인·DNS·TLS   ← 완료 (2026-08-18), 검증기 27/27
8. P1-1 알림  ← 인증서 만료만 완료 (2026-08-19) → 외부 감시·5xx → P1-5 의존성 상승 관측 → P1-2 audit log → P1-4 CSP
9. P2-1 평가 하네스 bootstrap ← 완료 (2026-08-13) → P2-2 LLM 어댑터 ← 경계·프로바이더 완료 (2026-08-18), 미측정 → held-out·LLM-only·Hybrid
```

P0-5를 맨 앞에 둔 이유는 의존성이 고정돼야 이후 rate limit·백업 검증 결과가 재현되기 때문이다. P0-4를 마지막에 두는 이유는 공개 노출이 되돌리기 가장 어려운 단계라서다. P1-3 이 P0-4 앞으로 올라온 것은 우선순위가 바뀌어서가 아니라, 1GB 머신에서는 배포 파이프라인 없이 배포 자체가 불가능하기 때문이다.

7번은 2026-08-18 에 실제로 실행됐다(`31-public-deployment.md`). 그 결과로 8번의 성격이 바뀌었다 — 공개 전에는 알림이 "있으면 좋은 것" 이었지만, 공개된 뒤로는 **인증서 갱신이 조용히 실패할 수 있는 시계가 이미 돌기 시작했다**(첫 갱신 2026-10-17 무렵). 그래서 8번 중 인증서 만료 감시만 먼저 떼어 2026-08-19 에 붙였고, 나머지 알림은 순서대로 남아 있다.

6번은 파이프라인만 섰고 **아직 한 번도 배포해 보지 않았다.** 첫 태그를 미는 순간이 곧 첫 검증이므로, 7번의 도메인이 정해지기 전에 `workflow_dispatch` 로 이미지 빌드만 먼저 돌려 보는 편이 낫다. 그러면 실패가 도메인 작업과 섞이지 않는다.

대회 일정이 공개 URL보다 우선한다면 P2-1(평가 하네스)을 P0-1 다음으로 올린다. Rule-only 베이스라인 측정은 배포 상태와 무관하게 지금 바로 가능하다.
