# Rate limiting과 요청 본문 크기 제한 (P0-1)

- 날짜: 2026-08-15
- 브랜치: `feature/frontend-accessibility-e2e`
- 범위: `app/core/{client_identity,rate_limit,request_limits}.py`, `app/repositories/rate_limits.py`,
  `app/services/rate_limits.py`, `migrations/versions/20260814_01_rate_limit_counters.py`,
  `web/lib/api/{server-auth,client,proxy-response,request-body,analysis}.ts`, `web/app/api/proxy/**`,
  `scripts/{cleanup_expired_anonymous_data,create_local_docker_secrets,verify_compose_runtime}.py`,
  `compose*.yaml`, `deploy/Caddyfile`, `.env*.example`, `.github/workflows/ci.yml`, 문서

## 배경

`POST /api/v1/analyze`에는 인증 의존성이 없다. `POST /api/v1/auth/session`은 익명 세션을
무제한으로 발급한다. 공개 URL이 붙는 순간 앞은 CPU를, 뒤는 DB 행을 소모한다. 스키마
상한(`text` 10000자)은 요청 **한 건**의 크기만 막을 뿐 **빈도**를 막지 못한다.

## 설계 판단 1 — 식별자를 IP 단독으로 바꿨다

`docs/28` P0-1은 원래 "익명 세션 + IP 조합"을 적어두었다. 구현하면서 뒤집었다.

세션은 공격자가 스스로 발급받을 수 있다. 세션마다 따로 세면 세션을 n개 만들어 한도를
n배로 늘린다. 세션 발급 자체를 제한해도 그 한도가 곧 실질 상한이 되므로, 계층이 하나
늘고 코드가 복잡해질 뿐 상한은 그대로다. IP는 공격자가 임의로 바꿀 수 없는 유일한
축이라, 여기서의 상한이 실제 상한이 된다.

대가는 CGNAT·회사망에서 여러 사용자가 한 버킷을 공유하는 것이다. 그래서 한도를 넉넉히
잡았다. 이 방어의 목적은 공정 분배가 아니라 "한 명이 서비스를 갈아버리는 것"의 차단이다.

| 정책 | 대상 | 한도 |
|---|---|---|
| `auth_session` | `POST /api/v1/auth/session` | 20 / 1시간 |
| `analyze` | `POST /api/v1/analyze` | 30 / 1분 |
| `write` | `/api/v1/` 쓰기 | 60 / 1분 |
| `read` | `/api/v1/` 나머지 | 240 / 1분 |

위에서부터 먼저 맞는 하나만 적용한다. 여러 정책을 겹쳐 세면 요청 한 건에 저장소 쓰기가
여러 번 일어나고, 정작 무엇에 걸렸는지도 흐려진다. `/health`·`/readyz`는 어떤 정책에도
걸리지 않는다 — 컨테이너 healthcheck가 주기적으로 때리는 경로라, 한도를 걸면 스스로를
unhealthy로 만든다.

## 설계 판단 2 — 홉을 오른쪽에서 센다

식별자가 IP라면 그 IP가 맞는지가 이 기능의 정확성 전부다. `X-Forwarded-For`는
클라이언트가 미리 적어 보낼 수 있어서 왼쪽부터 세면 공격자가 심은 값을 고르게 된다.

경로는 Caddy → web → backend다.

- **Caddy**: `header_up X-Forwarded-For {remote_host}`. 이어붙이지 않고 **덮어쓴다.**
  인터넷에 직접 붙어 있으므로 믿을 수 있는 주소는 TCP peer 하나뿐이고, 클라이언트가
  적어 보낸 체인을 남겨두면 backend가 세는 홉 수만 흔들린다.
- **web**: 받은 값을 **그대로 넘기고 자기 홉을 덧붙이지 않는다.** Route Handler는
  TCP peer를 볼 수 없어서 덧붙일 값 자체가 없다.
- **backend**: 따라서 맨 오른쪽 = 실제 클라이언트. `FINSHIELD_TRUSTED_PROXY_HOPS=1`.

기본값은 0이다. 0은 "헤더를 믿지 않고 TCP peer를 쓴다"는 뜻이라, 설정을 잊은 배포가
조용히 위조를 허용하는 대신 조용히 안전한 쪽으로 실패한다.

web이 체인을 다듬을 때 **오른쪽 기준 인덱스가 밀리지 않는 변형만** 한다. 왼쪽에서만
자르고(최대 8개), 형식이 이상한 항목은 삭제가 아니라 `unknown`으로 치환해 자리를
유지한다. 항목을 지우면 홉 인덱스가 밀려 공격자가 심어둔 값이 선택될 수 있다.

## 설계 판단 3 — 저장소가 죽으면 통과시킨다

사기 분석은 안전 기능이다. DB 장애 때문에 위험한 문자를 확인하지 못하게 만드는 쪽이,
그동안 한도가 열려 있는 것보다 나쁘다. `app/domain/fraud/sources.py`와 같은 판단이다.
대신 실패 로그에 식별자를 넣지 않는다 — 로그가 접속 기록이 되면 안 된다.

같은 이유로 버킷 키는 `HMAC(secret, policy|ip)`다. IPv4는 값이 2^32개뿐이라 단순
해시는 표를 만들어 되돌릴 수 있다. 서버 비밀을 섞어야 저장된 행이 접속 기록이 되지
않는다. 비밀은 배포에서 필수이고 32자 미만이면 기동을 거부한다. 워커마다 다른 비밀을
쓰면 같은 IP가 워커마다 다른 버킷으로 흩어져 공유 카운터를 쓰는 의미가 사라진다.

배포에서 SQLite면 기동을 거부한다. 워커 간 카운터를 공유하지 못해 한도가 워커 수만큼
헐거워지는데, 겉으로는 정상으로 보이기 때문이다.

## 설계 판단 4 — 본문 상한은 두 군데에 있어야 한다

백엔드는 순수 ASGI 미들웨어다. `BaseHTTPMiddleware`를 쓸 수 없는 이유는 `receive`를
직접 감싸야 하기 때문이다 — 바이트를 세려면 스트림 자체에 개입해야 한다. `Content-Length`만
믿지 않는다. chunked 전송에는 헤더가 없고, 헤더 값이 실제 본문과 다를 수도 있다.
헤더는 빠른 거부에만 쓰고, 실제 판단은 흘러오는 바이트를 세서 한다.

상한을 넘겼을 때 예외를 던지지 않는다. FastAPI는 `request.body()`에서 나온 예외를 전부
400 "error parsing the body"로 감싸버려서 위로 올라오지 않는다. 대신 연결이 끊긴 것처럼
알려 앱을 즉시 풀어주고, 응답은 send 쪽에서 413으로 갈아끼운다.

**검증 중에 web 쪽 구멍이 나왔다.** 배포 경로에서 인터넷에 노출된 쪽은 web인데,
Next.js Route Handler에는 본문 크기 기본 상한이 없다. `request.json()`을 그냥 부르면
100MB 본문도 전부 메모리에 담은 뒤에야 zod가 거부하고, 백엔드 상한은 그 요청을 구경도
못 한다. `web/lib/api/request-body.ts`를 추가해 본문을 읽는 6개 프록시 라우트를 전부
통과시켰다. 판단 기준은 백엔드와 같다 — 헤더로 먼저 끊고, 없으면 바이트를 센다.
상한을 넘긴 뒤에는 `reader.cancel()`로 남은 업로드를 계속 받아주지 않는다.

두 상한은 같은 환경변수(`FINSHIELD_MAX_REQUEST_BYTES`)를 읽는다. 한쪽만 올리면 web이
작을 때는 백엔드가 받아줄 요청이 413으로 막히고, web이 클 때는 백엔드가 어차피 거부할
본문을 web이 통째로 메모리에 담는다.

## 설계 판단 5 — 429가 "안전하다"로 읽히면 안 된다

이게 이 기능에서 제품상 가장 중요한 부분이다. 사용자는 지금 의심 문자를 손에 들고
있다. 분석이 돌지 않았는데 화면이 조용하면 그걸 "괜찮다"로 읽는다.

- 문구: "요청이 많아 분석을 잠시 멈췄습니다. **아직 위험 여부는 확인되지 않았습니다.**"
  급하면 112 / 1394로 바로 연락하라고 덧붙인다 (두 번호 모두 기존 `CONTACTS`에 있는
  실재 창구다. 새 기관을 지어내지 않았다).
- `web/lib/api/analysis.test.ts`가 전 실패 종류의 문구에 `/안전|이상 없음|위험 없음|정상입니다/`가
  없음을 회귀로 고정한다.
- **429를 502로 덮지 않는다.** 502는 "서버가 고장났다"로 읽혀서 사용자가 계속
  재시도한다. 프록시 라우트 11개가 공유하는 `upstreamStatus`가 401/404/413/429/503만
  통과시키고 나머지를 502로 접는다. 이 과정에서 라우트마다 복제돼 있던 같은 헬퍼 4개를
  지웠다.
- `Retry-After`를 초 단위로 파싱해 "43초 뒤에 다시 시도해 주세요"까지 만든다.
  HTTP-date 형식은 `Number.parseInt`가 자연히 거부한다(항상 요일 이름으로 시작).

## 함께 처리한 것

- **만료 행 정리**: 닫힌 window 행은 다시 조회되지 않는다. 지우지 않으면 요청 수만큼
  무한히 쌓이기만 한다. 기존 `scripts/cleanup_expired_anonymous_data.py`에 붙였고,
  **개인정보 보존기간 정리 뒤에** 둔다 — 뒤 단계가 실패해도 앞은 이미 끝나 있어야 한다.
  rate limit 카운터는 식별자를 담지 않으므로 순서상 뒤가 맞다.
- **secret 생성기**: `rate_limit_secret.txt`를 추가하면서, "하나라도 있으면 거부"를
  "없는 것만 만든다"로 바꿨다. 기존 설치에서도 쓸 수 있어야 한다. 기존 파일은 절대
  덮어쓰지 않는다 — 프로필 암호화 키를 여기서 로테이션하면 이미 저장된 프로필이 조용히
  읽히지 않게 된다.

## 검증

| 확인 | 방법 | 결과 |
|---|---|---|
| 전체 회귀 | `pytest -q` | 352 passed, 1 skipped |
| 프론트 | `tsc --noEmit` / `lint` / `vitest` | 클린 / 클린 / 13 files 80 tests |
| 한도 초과 | backend 직접 31회 POST | 30회 200, 31번째 429 + `Retry-After: 22` + `RateLimit-Limit: 30` |
| 버킷 분리 | 다른 `X-Forwarded-For` | 200, `RateLimit-Remaining: 29` |
| 홉 위조 | `198.51.100.7, 203.0.113.10` | 429 유지. 왼쪽에 심은 값으로 버킷을 못 바꾼다 |
| 본문 상한 (backend) | 200KB | 413, 파싱 전 차단 |
| 본문 상한 (web) | 프록시로 200KB | 413. zod 400으로 가려지지 않음 |
| healthcheck 영향 | `/health/ready` 연속 | 전부 200 |
| 프록시 경유 문구 | web → backend 30회 | 429 + 한국어 문구 + `Retry-After` 전달 |
| compose 병합 | `docker compose config` | base 0 / https 1 (`FINSHIELD_TRUSTED_PROXY_HOPS`) |

로컬에 Docker 데몬을 띄울 수 없어 컨테이너 실기동 대신 uvicorn + `next dev`로 같은
경로를 세워 확인했다. 컨테이너에서의 확인은 CI에 넣었다 — `container-runtime` job이
`FINSHIELD_RATE_LIMIT_ENABLED=1`로 스택을 띄우고, `verify_compose_runtime.py`가 413,
429 + `Retry-After`, 카운터가 PostgreSQL 행으로 남는지, 그 행의 `bucket_key`가 64자
hex인지(= IP가 그대로 저장되지 않는지)를 검사한다.

## 남은 것

- 다중 워커에서의 카운터 공유는 backend가 현재 단일 워커라 측정 대상이 아니다.
  워커를 늘릴 때 다시 확인해야 한다.
- 앞단에 CDN을 두게 되면 `deploy/Caddyfile`의 `header_up`과
  `FINSHIELD_TRUSTED_PROXY_HOPS`를 함께 고쳐야 한다. 한쪽만 고치면 위조가 열린다.
