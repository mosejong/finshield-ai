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

## 2. 환경변수 세 개

```
FINSHIELD_DOMAIN=finshield.example.com
FINSHIELD_ACME_EMAIL=ops@finshield.example.com
FINSHIELD_IMAGE_TAG=v0.3.0
```

셋 다 필수다(`:?`) — 앞의 둘은 `compose.https.yaml`, 마지막은 `compose.deploy.yaml`. 없으면 compose 가 거부하고, 이메일이 빈 문자열이면 Caddy 가 기동 자체를 거부한다.

`FINSHIELD_IMAGE_OWNER` 는 선택값이고 기본이 `mosejong` 이다. fork 에서 배포할 때만 바꾼다.

```
Error: adapting config using caddyfile: parsing caddyfile tokens for 'email':
wrong argument count or unexpected line ending after 'email'
```

이메일을 선택값으로 두지 않은 이유는 0절 첫 줄이다. 갱신 실패를 알려 줄 수 있는 통로가 이 주소 하나뿐인데, 기본값을 주면 **아무도 안 보는 주소로 배포가 성공해 버린다.** 사람이 실제로 읽는 주소를 쓴다.

`FINSHIELD_DOMAIN` 은 apex 이름 하나만 적는다. Caddy 는 정확히 이 이름으로 인증서를 요청한다.

## 3. 절차

### 3-1. 서버와 DNS

1. 80/443 을 인터넷에 열 수 있는 서버를 준비한다. ACME HTTP-01 검증이 80 을 쓴다. GCP 로 간다면 11절에 이 스택에 맞춘 설정이 있다.
2. DNS 에 A 레코드(IPv6 가 있으면 AAAA 도)를 서버 주소로 건다.
3. **전파를 확인한 다음에 스택을 올린다.** 순서를 바꾸면 0절의 두 번째 실패가 그대로 일어난다.

```bash
dig +short finshield.example.com A
dig +short finshield.example.com AAAA
```

서버 밖에서 80 이 실제로 열렸는지도 본다. 방화벽/보안그룹이 닫혀 있으면 검증이 실패하고 그 실패가 한도에 잡힌다.

### 3-2. 이미지를 받는다

VM 은 빌드하지 않는다(11-1). `compose.deploy.yaml` 을 끼우면 네 서비스의 `build:` 가 사라지고 `ghcr.io` 이미지가 들어간다.

먼저 릴리스 태그를 밀어 이미지를 만든다. 로컬에서:

```bash
git tag v0.3.0
git push origin v0.3.0
```

`.github/workflows/release.yml` 이 `finshield-backend` / `finshield-web` 을 `linux/amd64` 로 빌드해 올린다. Actions 요약에 digest 가 남으므로, 나중에 "그때 무엇이 돌고 있었나" 를 여기서 확인한다.

그다음 VM 에서:

```bash
export FINSHIELD_IMAGE_TAG=v0.3.0
docker compose -f compose.yaml -f compose.https.yaml -f compose.deploy.yaml pull
```

**여기서 인증 오류가 나면 패키지가 private 이다.** 워크플로가 처음 만든 ghcr 패키지는 저장소가 public 이어도 private 으로 생성된다. 패키지 설정에서 공개로 바꾸거나, `read:packages` 만 가진 PAT 으로 `docker login ghcr.io` 한다. 이미지에 비밀은 없으므로(11-1) 공개로 두는 쪽이 단순하다.

아래 3-3/3-4 명령에도 `-f compose.deploy.yaml` 을 그대로 붙인다. 빠뜨리면 VM 이 빌드를 시작하고 OOM 으로 조용히 죽는다.

### 3-3. staging 예행연습

```bash
FINSHIELD_DOMAIN=finshield.example.com \
FINSHIELD_ACME_EMAIL=ops@finshield.example.com \
docker compose -f compose.yaml -f compose.https.yaml -f compose.deploy.yaml -f compose.acme-staging.yaml up -d
docker compose logs proxy | grep -i "certificate obtained"
```

`"issuer":"acme-staging-v02.api.letsencrypt.org-directory"` 가 보이면 경로가 뚫린 것이다. staging 인증서는 브라우저가 신뢰하지 않으므로 이 상태로 공개하지 않는다.

override 를 **별도 파일**로 둔 이유: 환경변수 하나로 켜고 끄면 "연습 중"인지 "운영 중"인지가 눈에 안 보인다. 브라우저가 믿지 않는 인증서로 공개돼 있는 상태는 `-f` 하나의 존재로 드러나야 한다.

### 3-4. 운영 발급

staging override 만 빼고 다시 올린다. `compose.deploy.yaml` 은 남는다.

```bash
docker compose -f compose.yaml -f compose.https.yaml -f compose.deploy.yaml up -d
```

Caddy 는 staging 인증서를 버리고 운영 발급자로 새로 받는다. 기본 발급자는 Let's Encrypt 이고 실패하면 ZeroSSL 로 넘어간다. adapt 결과로 확인한 값:

```json
"issuers":[
  {"email":"ops@...","module":"acme"},
  {"ca":"https://acme.zerossl.com/v2/DV90","email":"ops@...","module":"acme"}
]
```

`acme_ca` 를 기본값으로 박지 않은 이유가 여기 있다. 명시하면 **두 발급자가 모두 그 하나로 대체된다.** staging 을 환경변수 기본값으로 뒀다면 대체 발급자가 영구히 사라졌을 것이다.

### 3-5. 밖에서 확인

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

### 9-1. 배포한 버전을 되돌린다

이전 태그로 다시 올린다. 그게 전부다.

```bash
export FINSHIELD_IMAGE_TAG=v0.2.0        # 직전에 돌던 태그
docker compose -f compose.yaml -f compose.https.yaml -f compose.deploy.yaml pull
docker compose -f compose.yaml -f compose.https.yaml -f compose.deploy.yaml up -d
```

**`alembic downgrade` 를 부르지 않는다.** `migrations/versions/` 의 `downgrade()` 들은 `drop_table` / `drop_index` / `drop_constraint` 라서, 실행하면 되돌리기가 아니라 데이터 삭제가 된다. 사고 대응 중에 칠 명령이 아니다.

대신 스키마는 새 버전 그대로 두고 코드만 되돌린다. 이게 성립하려면 마이그레이션이 이전 이미지에서도 안전해야 하고, 그래서 `docs/28` P1-3 의 expand/contract 규칙이 있다 — 컬럼 추가는 nullable, 삭제·이름 변경은 한 릴리스 뒤로 미룬다. **그 규칙을 어긴 릴리스는 이 절차로 되돌아가지 않는다.** 그런 릴리스를 되돌려야 한다면 백업 복원(`docs/29`)이 경로이고, 다운타임을 각오해야 한다.

되돌린 뒤 무엇이 돌고 있는지 확인한다. 태그는 옮겨 붙을 수 있으므로 digest 를 본다.

```bash
docker compose -f compose.yaml -f compose.https.yaml -f compose.deploy.yaml images
```

### 9-2. 인증서 발급이 꼬였을 때

```bash
docker compose -f compose.yaml -f compose.https.yaml down
docker volume rm finshield_caddy-data   # 인증서·ACME 계정 전부 삭제
```

`caddy-data` 를 지우면 **ACME 계정도 사라지고 다음 발급이 처음부터 시작한다.** 운영 한도가 이미 빠듯하다면 지우기 전에 staging 으로 먼저 확인한다.

HTTPS 를 통째로 내리려면 `compose.https.yaml` 없이 올린다(`compose.deploy.yaml` 은 남긴다 — 빼면 VM 이 빌드를 시작한다). 그러면 80/443 이 닫히고 `127.0.0.1` bind 만 남는다 — 공개는 중단되지만 데이터는 그대로다.

```bash
docker compose -f compose.yaml -f compose.deploy.yaml up -d
```

## 10. 남은 것

- **도메인과 서버가 아직 없다.** 3절 전체와 `certificate_trusted` 실측이 여기 묶여 있다. P0-4 는 이것이 정해져야 닫힌다.
- 외부 TLS 등급 측정(SSL Labs 등)은 공개된 도메인이 있어야 돌릴 수 있다.
- 갱신 감시를 cron 이 아니라 알림으로 옮기는 것은 `docs/28` P1-1.
- CAA 레코드는 발급자가 확정된 뒤에 건다. 지금 걸면 ZeroSSL 대체 발급 경로를 스스로 막는다.
- **릴리스 파이프라인이 한 번도 돈 적 없다.** 3-2 절은 YAML 파싱과 compose 해석까지만 검증됐다. 도메인을 기다리는 동안 `workflow_dispatch` 로 이미지 빌드만 먼저 돌려 두면, 첫 실패가 도메인 작업과 섞이지 않는다.
- 롤백(9-1) 리허설 없음. `docs/29` 의 복원 리허설처럼 실제로 이전 태그로 되돌려 보는 절차가 필요하다.

## 11. 부록 — GCP Compute Engine

### 11-0. 왜 Compute Engine 인가

| 후보 | 판단 |
|---|---|
| **Compute Engine VM** | 지금 스택 그대로 올라간다. `docker compose` + PostgreSQL 볼륨 + `./backups` bind mount + Caddy 인증서 볼륨이 전부 필요한데, 이걸 다 만족하는 가장 단순한 형태다 |
| Cloud Run | 안 된다. 파일시스템이 요청 단위로 사라지고 상시 실행 루프(retention, backup)를 둘 수 없다. PostgreSQL 을 Cloud SQL 로 빼고 백업을 GCS 로 다시 짜야 한다 — 스택을 다시 만드는 일이다 |
| GKE | 컨테이너 6개에 control plane 비용을 얹을 이유가 없다 |

Cloud Run 으로 옮기는 것 자체는 나중에 검토할 수 있지만, **공개를 그 재작업 뒤로 미룰 이유는 없다.**

### 11-1. 사양 — always-free `e2-micro` (2026-08-18 결정)

이 계정은 **$300 무료 크레딧을 받지 못했다.** 체험판 대상이 아니어서 되돌릴 방법이 없다. 그래서 상시 비용이 사실상 0 에 가까운 구성을 고른다. 아래 값은 그 제약에서 나온 것이지 성능상 최선이 아니다.

| 항목 | 값 | 이유 |
|---|---|---|
| 리전 | `us-central1` (아이오와) | **always-free 대상 리전은 `us-west1` / `us-central1` / `us-east1` 뿐이다.** 서울(`asia-northeast3`)에는 무료 등급이 없다. 한국에서 왕복 150ms 대를 감수한다 |
| 머신 | `e2-micro` (공유 vCPU, 1GB) | 월 1대 always-free. 상시 사용량 800MB 남짓이 1GB 안에 아슬아슬하게 들어간다. **빌드는 여기서 하지 않는다**(아래) |
| 디스크 | `pd-standard` 30GB | always-free 는 **standard** 30GB 까지다. `pd-balanced` 는 무료 대상이 아니다 |
| swap | 2GB 파일 | 1GB 에는 여유가 없다. 순간 피크에서 OOM killer 가 고르는 것은 대개 가장 큰 프로세스, 즉 PostgreSQL 이다 |
| OS | Debian 12 (bookworm) | Container-Optimized OS 는 루트가 읽기 전용이고 compose plugin 이 기본으로 없다. 이 스택은 `deploy/*.sh` 와 `./backups` 를 bind mount 한다 |
| 외부 IP | **고정(static)** | 아래 참조. **이것만은 무료가 아니다** |

실제 청구액은 고정 IP 월 $3~4 가 사실상 전부다. e2-medium 구성이 월 3~4만원인 것과의 차이가 이 선택의 이유다.

**요율 확인 (2026-08-18).** VM 에 붙은 외부 IPv4 는 **시간당 $0.005** 다 — 2024-02-01 자 인상($0.004 → $0.005)이 그대로다. 월 730시간 기준 **$3.65**, 환율에 따라 ₩5,000 안팎. 출처: [external IPv4 요금 변경 공지](https://cloud.google.com/vpc/pricing-announce-external-ips).

always-free 목록([free-cloud-features](https://docs.cloud.google.com/free/docs/free-cloud-features))에 들어 있는 것은 **인스턴스 1대 / `pd-standard` 30GB-month / 북미발 이그레스 1GB** 뿐이고, 외부 IP 는 목록에도 면제 문구에도 없다. 즉 "always-free VM" 이어도 IP 요금은 나온다. 이 스택은 ACME HTTP-01 검증에 공인 IPv4 가 필요하므로 피할 방법이 없고, 피하려 들 금액도 아니다.

같은 페이지가 **"To use products that have a Free Tier, you need a Google Cloud billing account"** 라고 명시한다. 활성 후불 결제 계정이면 충족이고, $300 체험 크레딧은 요건이 아니다.

무료 이그레스는 **북미발 월 1GB** 다(중국·호주 제외). Next 첫 로드가 수백 KB 이므로 월 수천 페이지뷰 근처에서 넘어가는데, 초과분이 GB 당 $0.12 선이라 금액 자체는 문제가 안 된다. 트래픽이 늘면 비용보다 **1GB RAM 이 먼저 한계에 닿는다.**

#### 이미지를 VM 안에서 만들지 않는다

`docker compose build` 의 Next 빌드는 2GB 이상을 쓴다. e2-micro 에서는 반드시 죽고, OOM 은 조용히 죽기 때문에 원인도 잘 안 보인다. 그래서 배포 형태가 하나 바뀐다.

- 이미지는 **GitHub Actions 에서 빌드**해 `ghcr.io/mosejong/finshield-*` 로 올린다. 저장소가 public 이라 공개 패키지는 용량 제한 없이 무료다. Artifact Registry 는 무료가 0.5GB 뿐이라 이 스택에는 모자란다.
- VM 은 `docker compose pull` 만 한다. `compose.yaml` 의 `build:` 를 `image:` 로 바꾸는 배포용 override 가 `compose.deploy.yaml` 이다 (2026-08-18 작성).
- 이미지에 비밀은 들어가지 않는다. `secrets/` 는 지금도 런타임 마운트라 레지스트리가 공개여도 노출 경로가 생기지 않는다.

**이 때문에 작업 순서가 바뀐다.** `docs/28` P1-3(배포/롤백)은 원래 공개 이후로 미뤄둔 항목인데, e2-micro 를 고른 이상 **P0-4 의 선행조건**이 된다. 손해만 있는 것은 아니다. 지금의 수동 배포에는 롤백 수단이 아예 없는데, 태그된 이미지를 pull 하는 방식에는 되돌릴 지점이 생긴다. → 2026-08-18 에 `release.yml` + `compose.deploy.yaml` 로 착지했다. **다만 아직 한 번도 태그를 밀어 보지 않았다.**

> **결제 계정 확인 (2026-08-18).** 후불 Google Cloud 결제 계정이 활성 상태이고 미결제 잔액 ₩0, 청구 기준액 ₩100,000 이다. always-free `e2-micro` 가 요구하는 것은 활성 결제 계정 하나뿐이므로 **이 절의 선행조건은 충족됐다.** $300 무료 체험 크레딧은 없고, 필요하지도 않다 — always-free 는 체험과 별개 프로그램이다. AI Studio 선불 크레딧 ₩70,000 은 Gemini API 전용이라 Compute Engine 요금에는 쓰이지 않는다.

### 11-2. 고정 IP를 먼저 잡는다

기본값인 ephemeral IP 는 인스턴스를 정지했다 켜면 **바뀐다.** 그러면 DNS 가 죽은 주소를 가리키고, Caddy 는 계속 재시도하며, ACME 검증 실패가 0절의 시간당 5회 한도를 태운다. 도메인을 붙이기 전에 잡아 둔다.

```bash
gcloud config set project <PROJECT_ID>
gcloud compute addresses create finshield-ip --region=us-central1
gcloud compute addresses describe finshield-ip --region=us-central1 --format='value(address)'
```

**2024년부터는 붙어 있어도 과금된다.** 실행 중인 인스턴스에 붙은 외부 IPv4 가 무료였던 것은 그 이전 이야기다. 지금은 시간당 $0.005 선이고, 아무 데도 안 붙어 있으면 요율이 더 높다. always-free 구성에서 실제로 청구되는 항목은 이것 하나뿐이니, 안 쓰게 되면 지운다.

### 11-3. 인스턴스와 방화벽

```bash
gcloud compute instances create finshield \
  --zone=us-central1-a \
  --machine-type=e2-micro \
  --image-family=debian-12 --image-project=debian-cloud \
  --boot-disk-size=30GB --boot-disk-type=pd-standard \
  --address=finshield-ip \
  --tags=finshield-web
```

GCP 기본 VPC 는 **인그레스를 막는다.** `default-allow-http` / `default-allow-https` 규칙이 있긴 하지만 `http-server` / `https-server` 태그가 붙은 인스턴스에만 적용되고, **둘 다 TCP 만 연다.**

```bash
gcloud compute firewall-rules create finshield-web \
  --allow=tcp:80,tcp:443,udp:443 \
  --target-tags=finshield-web \
  --description="Caddy HTTP/HTTPS + HTTP/3"
```

`udp:443` 을 빼먹기 쉽다. `compose.https.yaml` 이 `443:443/udp` 를 열고 Caddy 가 HTTP/3 리스너를 띄우는데, UDP 가 막혀 있으면 **브라우저가 HTTP/3 를 시도했다가 TCP 로 되돌아온다.** 겉으로는 동작해서 눈치채기 어렵고, 첫 접속마다 왕복이 한 번 더 붙는다.

`gcloud compute ssh finshield --zone=us-central1-a` 로 붙는다. 별도 키 설정은 필요 없다 — gcloud 가 OS Login 으로 처리한다.

### 11-4. VM 안에서

```bash
# 1GB 에는 여유가 없다. swap 이 없으면 순간 피크에서 OOM killer 가 돈다.
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git
sudo usermod -aG docker $USER && exec newgrp docker

git clone https://github.com/mosejong/finshield-ai.git && cd finshield-ai
python3 -m venv .venv && .venv/bin/pip install --require-hashes -r requirements.txt
.venv/bin/python scripts/create_local_docker_secrets.py
```

이름은 `create_local_docker_secrets` 지만 생성값은 운영에 써도 되는 강도다(`token_urlsafe(32)`, `Fernet.generate_key()`). 이미 있는 파일은 절대 덮어쓰지 않는다.

> **여기서 멈추고 `secrets/profile_encryption_keys.txt` 를 다른 곳에 복사한다.**
> 프로필이 하나라도 저장된 뒤에 이 키를 잃으면 백업 7세대가 전부 열리지 않는 바이트열이 된다(`docs/29` 0절). 백업 파일과 **같은 곳에 두지 않는다** — 그러면 백업 하나 유출로 프로필이 통째로 열린다.

그 다음 3절로 돌아간다. DNS A 레코드를 11-2 의 고정 IP 로 걸고, 전파를 확인하고, staging 예행연습부터 한다.

### 11-5. GCP 라서 달라지는 것

| 항목 | 내용 |
|---|---|
| 검증기 실행 위치 | VM 안에서 돌리면 안 된다(3-5절). 로컬 PC 에서 `--domain` 만 주고 돌린다. VM 안에서는 내부 포트가 열려 보이고 방화벽도 이미 통과한 뒤다 |
| 백업이 같은 디스크 | `./backups` 는 부트 디스크 위에 있다. 디스크가 날아가면 DB 와 백업이 같이 날아간다. GCS 버킷 + VM 서비스 계정으로 반출하는 것이 자연스러운 다음 단계다 (`docs/28` P0-3 의 남은 항목). **암호화 키는 그 버킷에 넣지 않는다** |
| 스냅샷 | 디스크 스냅샷 스케줄은 `pg_dump` 백업을 대체하지 않는다. 스냅샷은 실행 중인 PostgreSQL 의 순간 상태라 복구 시 복구 모드를 거치고, 무엇보다 **복호화되는지를 확인하지 않는다.** 둘 다 두되 합격 기준은 `docs/29` 를 따른다 |
| Cloud DNS | 필수가 아니다. 등록기관 DNS 에 A 레코드만 걸면 된다. Cloud DNS 는 존당 월 요금이 붙는다 |
| 요금 알림 | Billing 예산 알림을 걸어 둔다. 크레딧이 없으므로 처음부터 실비 청구다. 정상 상태에서는 고정 IP 월 $3~4 뿐이니, 예산을 그보다 조금 위에 잡아 두면 **의도치 않은 과금이 시작된 순간**을 바로 알 수 있다 |
