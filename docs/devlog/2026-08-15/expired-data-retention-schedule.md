# 만료 데이터 정리 자동 실행 (P0-2)

- 날짜: 2026-08-15
- 브랜치: `feature/frontend-accessibility-e2e`
- 범위: `app/services/data_retention.py`, `app/core/{data_retention,observability}.py`,
  `scripts/{run_retention_scheduler,cleanup_expired_anonymous_data,verify_compose_runtime}.py`,
  `tests/test_data_retention.py`, `compose.yaml`, `compose.https.yaml`, `.env*.example`,
  `.github/workflows/ci.yml`, 문서

## 배경

`scripts/cleanup_expired_anonymous_data.py`는 이미 있었다. 문제는 **아무도 부르지 않는다는
것**이었다. `adr/0004`가 "만료 후 다음 정리 작업에서 삭제한다"고 적어두었지만 그 정리 작업이
실행된 적이 없으므로, 보존기간은 문서상의 약속일 뿐이었다. 이 상태로 공개하면 두 가지가
동시에 발생한다. 개인정보 보존 약속 위반, 그리고 DB 무한 증가.

`docs/24`가 이 사실을 스스로 적어두고 있었다는 점이 특히 나빴다. "2026-08-14 기준 이
스크립트는 자동 실행되지 않는다"는 문장이 문서에 남아 있는 동안, 같은 문서의 보존 정책
절은 마치 지켜지고 있는 것처럼 읽혔다.

## 설계 판단 1 — backend 안이 아니라 별도 컨테이너

FastAPI의 background task나 lifespan에 붙이는 쪽이 파일 수는 적다. 그렇게 하지 않았다.

`Dockerfile`의 CMD는 `uvicorn ... --workers 2`다. 워커 안에 스케줄러를 넣으면 **같은 정리가
동시에 두 번 돈다.** 삭제 자체는 멱등이라 데이터가 깨지지는 않지만, 건수 로그가 둘로
갈라져 무엇이 실제로 지워졌는지 알 수 없게 된다. 워커를 3개로 늘리면 조용히 3배가 된다.

더 큰 이유는 장애 격리다. API 프로세스에 얹으면 정리가 DB를 붙잡는 동안 그 워커의 응답이
늦어지고, 반대로 API가 죽으면 개인정보 삭제도 함께 멈춘다. 후자가 특히 나쁘다 — 서비스가
내려간 상태는 사람이 금방 알아채고 고치지만, "내려가 있는 동안 보존기간이 지켜지지
않았다"는 사실은 아무 데도 기록되지 않는다.

## 설계 판단 2 — service가 아니라 repository에 의존한다

`RetentionRunner`는 `AuthSessionRepository`와 `RateLimitRepository`를 직접 받는다.
`RateLimitService`를 거치는 편이 계층상 자연스러워 보이지만, 그러면 정리가 rate limit 설정에
묶인다. `FINSHIELD_RATE_LIMIT_ENABLED=0`으로 내리거나 HMAC 비밀을 회수하는 순간 **개인정보
삭제까지 같이 멈춘다.** 운영자는 요청 한도를 껐다고 생각하지 보존 정책을 껐다고 생각하지
않는다.

정리는 결국 타임스탬프 비교 하나다. 그 위에 있는 정책 레이어를 통과할 이유가 없다.

## 설계 판단 3 — liveness가 아니라 heartbeat

"실패가 조용히 넘어가지 않게 한다"는 요구를 로그로 만족시킬 수는 없다. 아무도 안 본다.

컨테이너 healthcheck로 옮기는 것까지는 쉬운데, **무엇을 볼 것인가**가 문제였다. 프로세스
liveness는 답이 아니다. 정리가 매번 실패하는 loop도 프로세스는 멀쩡히 살아 있다. 살아
있음은 정리가 되고 있다는 증거가 못 된다.

그래서 **성공한 실행만** heartbeat 파일에 시각을 쓴다. 실패한 cycle은 파일을 건드리지 않고
이전 성공 시각을 그대로 남겨둔다. healthcheck는 그 시각의 나이를 본다.

- 임계값은 `interval * 2 + 60`초. 한 주기를 놓친 것은 DB 순간 장애일 수 있지만 두 주기
  연속은 실제 고장이다. 첫 실패에 바로 unhealthy를 내면 재기동 루프에 빠진다.
- 쓰기는 임시 파일 + `os.replace`로 원자적이다. 그러지 않으면 healthcheck가 쓰는 도중에
  읽어 잘린 내용을 보고 **멀쩡한 실행을 실패로 판정한다.**
- `--check-heartbeat`는 DB를 건드리지 않는다. DB가 흔들릴 때 정리 컨테이너까지 unhealthy로
  떨어지면 원인이 흐려진다. 그때 봐야 할 것은 db 서비스의 healthcheck다.
- 파일은 기본적으로 `tempfile.gettempdir()` 아래에 둔다. 컨테이너가 `read_only`라 쓸 수 있는
  곳이 tmpfs 뿐이고, 재시작하면 사라지는 편이 오히려 맞다 — 재시작 직후에는 "최근에 성공한
  적 없음"이 정확한 상태다.

## 설계 판단 4 — 거짓 성공을 두 군데서 막았다

이 기능에서 가장 위험한 실패는 예외가 아니라 **아무것도 지우지 않으면서 성공을 기록하는
것**이다. 그 상태는 healthcheck도 로그도 정상으로 보인다.

`DATABASE_URL`이 없으면 저장소 팩토리가 in-memory 구현을 내준다. 스케줄러가 그것을 상대로
돌면 매 주기 0건을 세고 성공을 남긴다. 정리가 아예 없는 것보다 나쁘다 — 없으면 최소한
아무도 지켜지고 있다고 믿지 않는다. 그래서 기동을 거부한다.

배포 환경에서 `postgresql+psycopg://`가 아니어도 거부한다. 같은 이유로 `compose.https.yaml`이
`retention`의 `APP_ENV`를 production으로 올린다. 여기만 development로 남으면 정리 컨테이너만
SQLite를 허용하게 되고, 그러면 운영 DB가 아닌 곳을 비운다.

## 설계 판단 5 — 실패 로그에 예외 메시지를 남기지 않는다

`adr/0004`는 "운영 로그에는 건수와 성공 여부만 기록하고 사용자·세션·프로필 식별자 및 금융
원문은 남기지 않는다"고 못박았다. 실패 경로에서 이것이 깨지기 쉽다.

SQLAlchemy는 실패한 SQL 문장과 **바인딩된 파라미터**를 예외 메시지에 붙인다. 정리 쿼리의
바인딩 값에는 사용자 ID가 들어간다. `str(exc)`를 로그에 넣는 순간 정리 로그가 개인정보 유출
경로가 된다. 그래서 `type(exc).__name__`만 남긴다. 디버깅 정보가 줄지만, 어느 저장소가 어떤
종류로 실패했는지는 타입만으로도 대개 충분하다.

회귀 테스트는 `RuntimeError("session=abc123 user=42 could not be deleted")`를 던지는 저장소를
넣고 로그에 `abc123`·`user=42`가 없음을 고정한다.

## 미리보기와 스케줄러가 같은 경로를 쓴다

`cleanup_expired_anonymous_data.py`를 같은 `RetentionRunner` 위로 다시 얹었다. 두 벌로 두면
미리보기에서 본 건수와 스케줄러가 실제로 지우는 건수가 갈라질 수 있고, 그러면 미리보기가
쓸모없어진다. `--execute` 플래그는 그대로 남겼다.

작업 중 이 스크립트가 로컬에서 `RateLimitStorageError` traceback을 뱉는 것을 발견했다. 로컬
`finshield.sqlite3`에 `rate_limit_counters` migration이 올라가 있지 않아서였고, 이전 코드도
같은 경로를 탔으므로 이번 변경이 만든 문제는 아니다. traceback 대신 JSON 오류 + exit 1로
바꿨다 — 대부분은 migration이 안 올라간 DB를 가리키고 있다는 뜻인데, traceback을 뱉으면 그
사실이 묻힌다.

## 검증

`pytest -q` → **383 passed, 1 skipped** (+31). 테스트는 heartbeat / 실행 / 스케줄러 / 로그 /
설정 / 진입점으로 나눴다.

로컬에 Docker 데몬을 띄울 수 없어 실제 삭제는 SQLite + 실제 subprocess로 확인했다.

| 확인 | 결과 |
|---|---|
| 만료 2건 / 활성 2건 → 스케줄러 기동 | users·profiles·counters 2/2/2 → 1/1/1. 활성 데이터 생존 |
| 첫 실행이 sleep보다 먼저인가 | `["cleanup", "sleep:900", "cleanup", "sleep:900"]` |
| heartbeat 없음 → 성공 직후 → 5시간 과거 | `--check-heartbeat` exit 1 → 0 → 1 |
| 실패 cycle이 heartbeat를 갱신하는가 | 갱신 안 함. 이전 성공 시각 유지 |
| 삭제된 사용자 UUID가 로그에 있는가 | 없음 |
| 실패 로그에 예외 메시지가 있는가 | 없음. `error_type`만 |
| `DATABASE_URL` 없이 기동 | exit 2 + `retention_config_error` |
| `docker compose config` (base / https) | `retention` 정상, `APP_ENV: production` 병합됨 |

## CI — "돌 수 있다"가 아니라 "돌았다"

`--once`를 CI에서 한 번 실행하는 것으로 끝내려다 그만뒀다. 그건 스크립트가 동작한다는
확인이지 **스케줄이 걸려 있다는 확인이 아니다.** P0-2가 막고 있던 것은 정확히 후자다.
스크립트는 처음부터 동작했고, 실행되지 않았을 뿐이다.

그래서 `verify_compose_runtime.py`가 실제로 세션을 만들고, `expires_at`을 과거로 밀고(TTL이
30일이라 기다려서 만료시킬 수 없다), **한 주기를 기다린 뒤** 행이 사라졌는지를 본다. 이어서
`retention` 컨테이너가 `healthy`인지, 로그에 `"status":"succeeded"`가 있고 `user_id`는 없는지
검사한다. 기본 주기 1시간으로는 CI 안에서 끝나지 않으므로
`FINSHIELD_RETENTION_INTERVAL_SECONDS=60`으로 스택을 띄우고, 스크립트도 같은 값을 받아 대기
시간을 정한다. 주기가 120초를
넘으면 검증 자체를 거부한다 — 조용히 건너뛰면 검증이 있는 척만 하게 된다.

## 남은 것

정리 실패가 컨테이너 밖으로 알려지지 않는다. healthcheck가 unhealthy를 띄워도 그것을 보고
사람에게 알리는 경로는 `28-production-readiness.md`의 P1-1이다. 그때까지는
`docker compose ps`를 봐야 안다.
