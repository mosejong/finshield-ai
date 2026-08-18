# 공개 배포 준비 — ACME 연락처, staging 예행연습, 외부 검증기 (P0-4)

- 날짜: 2026-08-17
- 브랜치: `feature/frontend-accessibility-e2e`
- 범위: `deploy/Caddyfile`, `compose.https.yaml`, `compose.acme-staging.yaml`, `deploy/acme-staging.caddy`, `app/core/public_deployment.py`, `scripts/verify_public_deployment.py`, `tests/test_public_deployment.py`, `.github/workflows/ci.yml`, `.env.docker.example`, `docs/26`, `docs/28`, `docs/31`

## 배경

`docs/28` §6 순서에서 다음 항목이 P0-4(실도메인·DNS·TLS)였는데, 완료 기준이 "외부 네트워크에서 실제 도메인으로 전 주요 화면 동작"이라 도메인 없이는 닫을 수 없다. 도메인은 사용자가 정한다.

그렇다고 대기만 할 일은 아니었다. **도메인이 정해진 날 무엇을 어떻게 하고 무엇으로 확인할지**는 지금 만들 수 있고, 오히려 그날 만들면 늦는 것이 하나 있다 — 발급 한도다.

## 설계 판단 1 — ACME 연락처를 선택값이 아니라 필수로

인증서 갱신은 조용히 실패한다. Caddy는 만료 30일 전부터 시도하고, 실패해도 재시도만 하며, 사용자는 만료 당일까지 아무것도 못 느낀다. 발급기관이 그 사실을 알릴 수 있는 통로가 계정 이메일 하나다.

기본값을 주면 아무도 안 보는 주소로 배포가 성공해 버린다. 그래서 `compose.https.yaml`에서 `:?`로 필수화하고, 값이 비면 Caddy가 기동 자체를 거부하는 것을 확인했다.

```
Error: adapting config using caddyfile: parsing caddyfile tokens for 'email':
wrong argument count or unexpected line ending after 'email'
```

알림 경로 없이 공개하는 것보다 기동이 막히는 쪽이 낫다.

## 설계 판단 2 — staging을 환경변수가 아니라 mount되는 파일로

Let's Encrypt 운영 디렉터리는 도메인당 검증 실패 5회/시간, 같은 이름 중복 인증서 5장/주로 막힌다. DNS가 아직 서버를 가리키지 않거나 80이 닫힌 채로 스택을 올리면 재시도가 그 한도를 태우고, **정작 준비가 끝난 뒤에 발급을 못 받는다.**

`FINSHIELD_ACME_CA` 같은 환경변수에 staging 기본값을 넣는 것이 처음 떠오른 방법이었는데, adapt 결과를 보고 접었다.

기본 상태(아무것도 명시하지 않음):

```json
"issuers":[
  {"email":"ops@...","module":"acme"},
  {"ca":"https://acme.zerossl.com/v2/DV90","email":"ops@...","module":"acme"}
]
```

`acme_ca`를 명시하면:

```json
"issuers":[{"ca":"https://acme-staging-v02...","email":"ops@...","module":"acme"}]
```

**두 개가 하나로 대체된다.** 환경변수로 뒀다면 ZeroSSL 대체 발급자가 영구히 사라졌을 것이다. Let's Encrypt가 장애일 때 자동으로 넘어가는 경로를, 쓰지도 않는 기본값 때문에 잃는 셈이다.

그래서 파일 mount로 갔다. 켜는 방법은 `-f compose.acme-staging.yaml` 하나를 더 얹는 것이고, 브라우저가 믿지 않는 인증서로 공개돼 있는 상태가 명령줄에 보인다.

Caddyfile이 조건부 설정을 지원하지 않는데 어떻게 파일 유무로 갈리게 했는가 — glob import를 썼다.

```
import /etc/caddy/acme/*.caddy
```

매칭되는 파일이 없으면 경고 한 줄만 남기고 넘어간다. 실제 기동 로그로 확인했다.

```json
{"level":"warn","msg":"No files matching import glob pattern","pattern":"/etc/caddy/acme/*.caddy"}
```

## 설계 판단 3 — healthcheck는 "발급 실패"를, cron은 "만료"를

`compose.https.yaml`의 proxy healthcheck는 실제 SNI로 자기 자신에 붙는다.

```
curl -fsk --resolve $DOMAIN:443:127.0.0.1 https://$DOMAIN/
```

인증서가 없으면 handshake가 실패하므로 **"Caddy 프로세스는 살아 있는데 발급에 실패한"** 상태가 healthy로 보이지 않는다. 프로세스 존재만 보는 healthcheck였다면 놓친다.

만료는 잡지 못한다. `-k`가 검증을 건너뛰기 때문이다. 이 분담은 의도한 것이다 — healthcheck가 만료를 보게 하면 컨테이너가 만료일에 재시작 루프에 빠진다. 인증서가 없어서 못 뜨는 것과 만료돼서 못 뜨는 것은 대응이 다르다. 만료는 `--certificate-only` cron이 본다.

## 설계 판단 4 — 판정과 실측을 나눈다

`app/core/public_deployment.py`(순수 함수)와 `scripts/verify_public_deployment.py`(네트워크)로 나눴다. P0-3에서 겪은 것이 정확히 이 문제였다. 검사가 돌고 있었지만 실패할 수 없는 검사였고, 초록불이 아무것도 증명하지 않았다.

판정을 순수 함수로 빼면 네트워크 없이 **기준 자체**를 테스트할 수 있다. `tests/test_public_deployment.py` 35개는 전부 "떨어져야 하는 입력이 실제로 떨어지는지"를 본다.

존재만 보는 검사가 놓치는 것들을 특히 고정했다.

| 입력 | 존재 검사 | 이 검사 |
|---|---|---|
| `Strict-Transport-Security: max-age=0` | 통과 | 실패 — HSTS를 끄는 값이다 |
| `X-Frame-Options: SAMEORIGIN` | 통과 | 실패 — `docs/26`은 `DENY`다 |
| `Content-Security-Policy: default-src 'self'` | 통과 | 실패 — `frame-ancestors 'none'`이 없다 |
| 만료 21일 전 인증서 | 통과 | 실패 — 갱신이 이미 9일째 실패 중이다 |

## 설계 판단 5 — 검사기가 남의 문자 원문을 만들지 않는다

공유 시트 왕복 검사는 실제 문자 대신 고정 문구를 보낸다.

```python
SHARE_PROBE_TEXT = "배포 확인용 문구입니다. 실제 사용자 메시지가 아닙니다."
```

검사기가 그럴듯한 피싱 문자를 생성할 이유가 없고, 그 문자열은 로그·터미널 기록·CI 아티팩트에 남는다.

## 막힌 것

**도메인과 서버가 없다.** 3절 전체(DNS A/AAAA, staging 예행연습, 운영 발급)와 `certificate_trusted` 실측, 외부 TLS 등급 측정이 여기 묶여 있다. P0-4는 이것이 정해져야 닫힌다.

## 검증

localhost 예행연습으로 경로 전체를 돌렸다. Caddy는 `localhost`를 내부 CA로 발급하므로 ACME를 한 번도 건드리지 않는다.

| 확인 | 방법 | 결과 |
|---|---|---|
| 판정 기준 | `pytest tests/test_public_deployment.py -q` | 35 passed |
| 전체 회귀 | `pytest -q` | 아래 참조 |
| glob import 무매칭 | 기동 로그 | 경고 1줄, 정상 기동 |
| 빈 이메일 거부 | `FINSHIELD_ACME_EMAIL=` + `caddy validate` | exit 1, 파싱 에러 |
| 기본 발급자 유지 | `caddy adapt` (staging 미mount) | LE + ZeroSSL 2개 |
| staging 교체 | `caddy adapt` (staging mount) | `acme-staging-v02` 1개 |
| 로컬 인증서 발급 | 기동 로그 | `"certificate obtained successfully","issuer":"local"` |
| HTTP→HTTPS | 검증기 | `308 → https://localhost/` |
| HSTS | 검증기 | `max-age=31536000; includeSubDomains` |
| 보안 헤더 6종 | 검증기 | 전부 통과 (`Server`·`X-Powered-By` 부재 포함) |
| 주요 화면 9개 | 검증기 | 전부 200 (`/offline`, `/manifest.webmanifest`, `/sw.js` 포함) |
| 서비스 워커 캐시 | 검증기 | `no-cache, no-store, must-revalidate` |
| 공유 시트 왕복 | 검증기 (multipart POST) | 200 + `no-store` + `Set-Cookie` 없음 |
| 액세스 로그 | 27개 요청 후 `docker compose logs proxy` | 기동 로그 31줄뿐. 요청 경로 없음 (`adr/0004`) |
| XFF 덮어쓰기 | `caddy adapt` | `"request":{"set":{"X-Forwarded-For":[...]}}` — append 아님 |
| compose 병합 | https / https+staging `config --quiet` | 둘 다 통과 |

검증기 종합: 27개 검사 중 4개 실패. 그 4개는 전부 예행연습 고유 항목이다 — 내부 CA 인증서가 12시간짜리라 `certificate_expiry`가 걸리고, `compose.yaml`이 로컬 개발용으로 `127.0.0.1`에 publish하는 포트 3개가 `internal_port`에 걸린다. 운영 서버에서는 둘 다 해당하지 않는다.

### 예행연습 중에 실제로 잡힌 것

첫 실행에서 `/offline`, `/manifest.webmanifest`, `/sw.js`, `/check/shared`가 전부 404였다. 원인은 `finshield-web` 이미지가 PWA 커밋 이전 것이었다. `--build`로 다시 올리니 전부 200. **검증기가 만들어지자마자 배포 이미지가 낡았다는 사실을 잡아낸 셈이다.**

같은 실행에서 검사기 자체의 결함도 하나 나왔다. `/sw.js`가 404인데 `service_worker_not_cached`는 통과하고 있었다 — Next의 404 응답에도 `no-store`가 붙기 때문이다. **파일이 없을 때 통과하는 검사**는 P0-3에서 배운 그 실패 모드라, 200일 때만 보도록 고쳤다.

## 남은 것

- 도메인·서버 확보 후 `docs/31` 3절 전체 실행
- 외부 TLS 등급 측정 (SSL Labs 등)
- 갱신 감시를 cron에서 알림으로 (`docs/28` P1-1)
- CAA 레코드는 발급자 확정 후. 지금 걸면 ZeroSSL 대체 경로를 스스로 막는다
