# 31. 공개 배포 — 도메인, DNS, 인증서

목적: 실제 도메인으로 공개하는 절차와 **공개된 상태가 맞는지 확인하는 방법**을 한 문서에 둔다. 작성 기준일 2026-08-17. `28-production-readiness.md` P0-4 의 실행 문서다.

판단 기준은 하나다. **인증서가 발급됐다는 것은 배포가 끝났다는 뜻이 아니다.** 밖에서 붙었을 때 평문으로 새지 않고, 갱신이 멈춰 있지 않고, 내부 포트가 열려 있지 않아야 끝이다.

## 0. 먼저 읽을 것 — 이 배포에서 조용히 실패하는 두 가지

| 실패 | 왜 조용한가 | 대응 |
|---|---|---|
| 인증서 갱신 정지 | Caddy 는 만료 30일 전부터 갱신을 시도하고 실패해도 재시도만 한다. 사용자는 **만료 당일까지** 아무것도 못 느낀다 | ACME 연락처 필수화 + `--certificate-only` 주기 실행 |
| 발급 한도 소진 | Let's Encrypt 운영 디렉터리는 도메인당 검증 실패 5회/시간, 같은 이름 중복 인증서 5장/주. DNS 가 아직 서버를 가리키지 않은 채로 스택을 올리면 재시도가 한도를 태운다 | 첫 발급은 staging 으로 예행연습 |

두 번째가 특히 아프다. 한도를 태운 사실은 **준비가 다 끝난 뒤 발급을 못 받을 때** 알게 된다. 그래서 staging 경로를 미리 만들어 뒀다.

## 1. 구성

| 부분 | 파일 | 하는 일 |
|---|---|---|
| 리버스 프록시 | `deploy/Caddyfile` | 자동 인증서, HTTP→HTTPS, 보안 헤더, XFF 덮어쓰기 |
| HTTPS override | `compose.https.yaml` | `proxy` 서비스, 80/443 공개, SNI healthcheck |
| staging 발급자 | `deploy/acme-staging.caddy` | `acme_ca` 를 Let's Encrypt staging 으로 교체 |
| staging override | `compose.acme-staging.yaml` | 위 파일을 `/etc/caddy/acme/` 에 mount |
| 판정 기준 | `app/core/public_deployment.py` | 순수 함수. 무엇이 합격인지 |
| 실측 | `scripts/verify_public_deployment.py` | 밖에서 두드려 값을 가져온다 |
| 기준 테스트 | `tests/test_public_deployment.py` | 떨어져야 하는 입력이 실제로 떨어지는지 |

판정과 실측을 나눈 이유는 P0-3 에서 겪은 것 때문이다. 검사가 돌고 있었지만 실패할 수 없는 검사였고, 초록불이 아무것도 증명하지 않았다. 판정을 순수 함수로 빼면 네트워크 없이 **기준 자체**를 테스트할 수 있다.

## 2. 환경변수 두 개

```
FINSHIELD_DOMAIN=finshield.example.com
FINSHIELD_ACME_EMAIL=ops@finshield.example.com
```

둘 다 `compose.https.yaml` 에서 필수다(`:?`). 없으면 compose 가 거부하고, 이메일이 빈 문자열이면 Caddy 가 기동 자체를 거부한다.

```
Error: adapting config using caddyfile: parsing caddyfile tokens for 'email':
wrong argument count or unexpected line ending after 'email'
```

이메일을 선택값으로 두지 않은 이유는 0절 첫 줄이다. 갱신 실패를 알려 줄 수 있는 통로가 이 주소 하나뿐인데, 기본값을 주면 **아무도 안 보는 주소로 배포가 성공해 버린다.** 사람이 실제로 읽는 주소를 쓴다.

`FINSHIELD_DOMAIN` 은 apex 이름 하나만 적는다. Caddy 는 정확히 이 이름으로 인증서를 요청한다.

## 3. 절차

### 3-1. 서버와 DNS

1. 80/443 을 인터넷에 열 수 있는 서버를 준비한다. ACME HTTP-01 검증이 80 을 쓴다.
2. DNS 에 A 레코드(IPv6 가 있으면 AAAA 도)를 서버 주소로 건다.
3. **전파를 확인한 다음에 스택을 올린다.** 순서를 바꾸면 0절의 두 번째 실패가 그대로 일어난다.

```bash
dig +short finshield.example.com A
dig +short finshield.example.com AAAA
```

서버 밖에서 80 이 실제로 열렸는지도 본다. 방화벽/보안그룹이 닫혀 있으면 검증이 실패하고 그 실패가 한도에 잡힌다.

### 3-2. staging 예행연습

```bash
FINSHIELD_DOMAIN=finshield.example.com \
FINSHIELD_ACME_EMAIL=ops@finshield.example.com \
docker compose -f compose.yaml -f compose.https.yaml -f compose.acme-staging.yaml up -d
docker compose logs proxy | grep -i "certificate obtained"
```

`"issuer":"acme-staging-v02.api.letsencrypt.org-directory"` 가 보이면 경로가 뚫린 것이다. staging 인증서는 브라우저가 신뢰하지 않으므로 이 상태로 공개하지 않는다.

override 를 **별도 파일**로 둔 이유: 환경변수 하나로 켜고 끄면 "연습 중"인지 "운영 중"인지가 눈에 안 보인다. 브라우저가 믿지 않는 인증서로 공개돼 있는 상태는 `-f` 하나의 존재로 드러나야 한다.

### 3-3. 운영 발급

override 를 빼고 다시 올린다.

```bash
docker compose -f compose.yaml -f compose.https.yaml up -d
```

Caddy 는 staging 인증서를 버리고 운영 발급자로 새로 받는다. 기본 발급자는 Let's Encrypt 이고 실패하면 ZeroSSL 로 넘어간다. adapt 결과로 확인한 값:

```json
"issuers":[
  {"email":"ops@...","module":"acme"},
  {"ca":"https://acme.zerossl.com/v2/DV90","email":"ops@...","module":"acme"}
]
```

`acme_ca` 를 기본값으로 박지 않은 이유가 여기 있다. 명시하면 **두 발급자가 모두 그 하나로 대체된다.** staging 을 환경변수 기본값으로 뒀다면 대체 발급자가 영구히 사라졌을 것이다.

### 3-4. 밖에서 확인

**서버 안에서 돌리면 의미가 없다.** loopback 에만 bind 된 내부 포트가 열려 보이고, 방화벽도 이미 통과한 뒤다. 다른 네트워크(집 회선, 휴대폰 테더링)에서 돌린다.

```bash
python -m scripts.verify_public_deployment --domain finshield.example.com
```

실패가 하나도 없어야 P0-4 완료다. 종료코드는 0 통과 / 1 실패 / 2 설정 오류.

## 4. 무엇을 검사하는가

| 검사 | 통과 기준 | 왜 |
|---|---|---|
| `https_redirect` | 평문 요청이 301/302/307/308 로 **같은 도메인의 https** 로 | 200 이면 사용자가 친 `http://` 요청이 그대로 처리된다는 뜻이고 세션 쿠키가 평문으로 오간다 |
| `certificate_trusted` | 공개 CA 체인·호스트명 검증 통과 | staging 인증서가 운영에 남아 있는 상태를 잡는다 |
| `certificate_expiry` | 21일 초과 남음 | 21일 남았다 = 갱신이 이미 9일째 실패 중이다. 만료 직전에 알면 늦다 |
| `tls_version` | TLS 1.2 또는 1.3 | 여기서 걸리면 앞단에 모르는 종단점이 하나 더 있다는 뜻 |
| `hsts` | `max-age` 1년 이상 + `includeSubDomains` | `max-age=0` 은 헤더가 있으면서 HSTS 를 끄는 값이다. 존재만 보는 검사가 놓친다 |
| `header:*` | `docs/26` 의 값과 정확히 일치 | 존재만 보면 `X-Frame-Options: ALLOWALL` 같은 무력화를 못 잡는다 |
| `header:server`, `header:x-powered-by` | 없음 | 버전을 알려 줄 이유가 없다 |
| `page:*` | 주요 화면 9개 전부 200 | `/offline`, `/manifest.webmanifest`, `/sw.js` 포함 — PWA 는 이 세 개가 없으면 설치되지 않는다 |
| `service_worker_not_cached` | `/sw.js` 에 `no-store` | 낡은 워커가 캐시에 박히면 배포가 사용자에게 도달하지 않는다 |
| `share_target_*` | 200 + `no-store` + `Set-Cookie` 없음 | 공유된 문자 원문이 담긴 응답이다 (`docs/30`) |
| `internal_port:*` | 18000 / 13000 / 5432 전부 닫힘 | 열려 있으면 Caddy 를 우회해 평문으로 붙을 수 있고 HTTPS 를 붙인 의미가 없다 |

공유 왕복 검사는 **고정된 검사 문구**만 보낸다(`SHARE_PROBE_TEXT`). 검사기가 남의 문자 원문을 만들어 낼 이유가 없다.

## 5. localhost 예행연습 — 도메인 없이 경로 전체 확인

Caddy 는 `localhost` 를 내부 CA 로 발급한다. ACME 를 한 번도 건드리지 않으므로 한도와 무관하다.

```powershell
$env:FINSHIELD_DOMAIN = "localhost"
$env:FINSHIELD_ACME_EMAIL = "ops@example.com"
docker compose -f compose.yaml -f compose.https.yaml up -d --build proxy
python -m scripts.verify_public_deployment --domain localhost --insecure
```

**이 예행연습에서는 정확히 4개가 실패해야 한다.** 그보다 많으면 진짜 문제고, 적으면 검사가 죽은 것이다.

| 실패 | 이유 |
|---|---|
| `certificate_expiry` | 내부 CA 인증서는 12시간짜리다. 만료 검사가 실제로 발화한다는 증거이기도 하다 |
| `internal_port:18000` / `:13000` / `:5432` | `compose.yaml` 이 로컬 개발용으로 `127.0.0.1` 에 publish 한다. 운영 서버에서는 publish 하지 않는다 |

`--insecure` 는 체인 검증 실패만 봐준다. 만료·헤더·리다이렉트는 그대로 엄격하다. 출력에 `--insecure: 체인 검증을 건너뛴 예행연습` 이 보이면 예행연습이라는 뜻이고, **실도메인 출력에 이 줄이 보이면 잘못된 것이다.**

2026-08-17 실행 결과: 27개 검사 중 위 4개만 실패. 나머지는 전부 통과했다.

## 6. 갱신 감시

인증서 갱신은 조용히 실패한다(0절). 최소한의 감시는 주기 실행이다.

```
0 9 * * * cd /srv/finshield && python -m scripts.verify_public_deployment \
    --certificate-only --domain finshield.example.com
```

종료코드가 1 이면 21일 미만이다. 이 시점에 손쓰면 아직 2주 이상 여유가 있다.

`compose.https.yaml` 의 proxy healthcheck 는 다른 것을 본다.

```
curl -fsk --resolve $DOMAIN:443:127.0.0.1 https://$DOMAIN/
```

실제 SNI 로 자기 자신에게 붙는다. 인증서가 없으면 handshake 가 실패하므로 **"Caddy 프로세스는 살아 있는데 발급에 실패한"** 상태가 healthy 로 보이지 않는다. 다만 `-k` 로 검증을 건너뛰므로 **만료는 잡지 못한다.** 만료는 이 절 첫머리의 cron 담당이다. 이 분담은 의도한 것이다 — healthcheck 가 만료를 보게 하면 컨테이너가 만료일에 재시작 루프에 빠진다.

`docs/28` P1-1(장애 알림)이 붙으면 cron 출력을 그쪽으로 옮긴다.

## 7. 로그 — 요청 경로를 남기지 않는다

Caddy 는 `log` 지시어가 없으면 액세스 로그를 쓰지 않는다. `deploy/Caddyfile` 에는 없다. localhost 예행연습에서 27개 요청을 보낸 뒤 `docker compose logs proxy` 는 기동 로그 31줄뿐이었다.

의도한 상태다. 액세스 로그를 켜면 `/check/result/{id}` 같은 경로가 그대로 남고, `adr/0004`("운영 로그에는 건수와 성공 여부만 기록하고 사용자·세션·프로필 식별자 및 금융 원문은 남기지 않는다")를 어긴다. 나중에 켜야 한다면 URI 를 지우는 필터를 함께 붙인다.

## 8. X-Forwarded-For 경고는 무시한다

Caddy 는 기동할 때 이렇게 경고한다.

```
Unnecessary header_up X-Forwarded-For: the reverse proxy's default behavior
is to pass headers to the upstream
```

**경고를 믿고 지우면 안 된다.** 기본 동작은 클라이언트가 보낸 XFF **뒤에 덧붙이는** append 이고, 우리가 쓴 것은 통째로 바꾸는 set 이다. adapt 결과로 확인했다.

```json
"handler":"reverse_proxy",
"headers":{"request":{"set":{"X-Forwarded-For":["{http.request.remote.host}"]}}}
```

이 Caddy 가 인터넷에 직접 붙어 있으므로 믿을 수 있는 주소는 TCP peer 하나뿐이다. append 로 두면 클라이언트가 홉을 마음대로 늘려 backend 의 `FINSHIELD_TRUSTED_PROXY_HOPS=1` 계산을 흔들 수 있다.

## 9. 되돌리기

발급이 꼬였을 때:

```bash
docker compose -f compose.yaml -f compose.https.yaml down
docker volume rm finshield_caddy-data   # 인증서·ACME 계정 전부 삭제
```

`caddy-data` 를 지우면 **ACME 계정도 사라지고 다음 발급이 처음부터 시작한다.** 운영 한도가 이미 빠듯하다면 지우기 전에 staging 으로 먼저 확인한다.

HTTPS 를 통째로 내리려면 `compose.https.yaml` 없이 올린다. 그러면 80/443 이 닫히고 `127.0.0.1` bind 만 남는다 — 공개는 중단되지만 데이터는 그대로다.

## 10. 남은 것

- **도메인과 서버가 아직 없다.** 3절 전체와 `certificate_trusted` 실측이 여기 묶여 있다. P0-4 는 이것이 정해져야 닫힌다.
- 외부 TLS 등급 측정(SSL Labs 등)은 공개된 도메인이 있어야 돌릴 수 있다.
- 갱신 감시를 cron 이 아니라 알림으로 옮기는 것은 `docs/28` P1-1.
- CAA 레코드는 발급자가 확정된 뒤에 건다. 지금 걸면 ZeroSSL 대체 발급 경로를 스스로 막는다.
