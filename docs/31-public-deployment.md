# 31. 공개 배포 — 도메인, DNS, 인증서

목적: 실제 도메인으로 공개하는 절차와 **공개된 상태가 맞는지 확인하는 방법**을 한 문서에 둔다. 작성 기준일 2026-08-17. `28-production-readiness.md` P0-4 의 실행 문서다.

판단 기준은 하나다. **인증서가 발급됐다는 것은 배포가 끝났다는 뜻이 아니다.** 밖에서 붙었을 때 평문으로 새지 않고, 갱신이 멈춰 있지 않고, 내부 포트가 열려 있지 않아야 끝이다.

## 0. 먼저 읽을 것 — 이 배포에서 조용히 실패하는 세 가지

| 실패 | 왜 조용한가 | 대응 |
|---|---|---|
| 인증서 갱신 정지 | Caddy 는 만료 30일 전부터 갱신을 시도하고 실패해도 재시도만 한다. 사용자는 **만료 당일까지** 아무것도 못 느낀다 | ACME 연락처 필수화 + `--certificate-only` 주기 실행 |
| 발급 한도 소진 | Let's Encrypt 운영 디렉터리는 도메인당 검증 실패 5회/시간, 같은 이름 중복 인증서 5장/주. DNS 가 아직 서버를 가리키지 않은 채로 스택을 올리면 재시도가 한도를 태운다 | 첫 발급은 staging 으로 예행연습 |
| **배포 목록 누락** | `docker compose config` 도 `caddy validate` 도 **문법만** 본다. 적어 둔 목록이 실제로 필요한 것보다 **짧다**는 것은 어느 쪽도 잡지 못한다. 빠진 기능만 죽고 나머지는 전부 멀쩡하다 | 재배포 명령줄과 라우팅을 `tests/test_public_routing.py` 가 검사한다 |

두 번째가 특히 아프다. 한도를 태운 사실은 **준비가 다 끝난 뒤 발급을 못 받을 때** 알게 된다. 그래서 staging 경로를 미리 만들어 뒀다.

세 번째는 2026-09-05 외부 검수에서 두 건이 한꺼번에 드러났다. 재배포 명령줄에 `compose.public-data.yaml` 이 **한 번도 없었고**, 그래서 공개 서비스의 금융상품은 공개 이후 한 번도 동작한 적이 없다(전부 `503`). 그런데 컨테이너는 내내 healthy 였다 — `/health/ready` 는 저장소만 보고 상품 제공자는 보지 않는다. 같은 검수에서 `/health` 세 경로가 밖에서 `404` 라는 것도 나왔는데, 이쪽은 `deploy/Caddyfile` 이 **모든** 요청을 `web:3000` 으로 보내고 있었다. 둘 다 코드는 맞았고 **배포 설정이 그 코드에 닿지 못한** 경우다.

## 1. 구성

| 부분 | 파일 | 하는 일 |
|---|---|---|
| 리버스 프록시 | `deploy/Caddyfile` | 자동 인증서, HTTP→HTTPS, 보안 헤더, XFF 덮어쓰기 |
| HTTPS override | `compose.https.yaml` | `proxy` 서비스, 80/443 공개, SNI healthcheck |
| staging 발급자 | `deploy/acme-staging.caddy` | `acme_ca` 를 Let's Encrypt staging 으로 교체 |
| staging override | `compose.acme-staging.yaml` | 위 파일을 `/etc/caddy/acme/` 에 mount |
| 설명 계층 override | `compose.gemini.yaml` | Gemini 키를 secret 으로 backend 에 붙인다 |
| 금융상품 override | `compose.public-data.yaml` | 공공데이터 서비스키를 secret 으로 backend 에 붙인다 |
| 판정 기준 | `app/core/public_deployment.py` | 순수 함수. 무엇이 합격인지 |
| 실측 | `scripts/verify_public_deployment.py` | 밖에서 두드려 값을 가져온다 |
| 기준 테스트 | `tests/test_public_deployment.py` | 떨어져야 하는 입력이 실제로 떨어지는지 |
| 라우팅·목록 대조 | `tests/test_public_routing.py` | Caddy 가 보내는 곳과 FastAPI 가 가진 경로, 그리고 3-6 의 재배포 목록과 저장소의 override 파일이 같은지 |

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

**패키지 공개 범위는 짐작하지 말고 확인한다.** 첫 실행(2026-08-18, `Release images` #1)에서 만들어진 두 패키지는 **둘 다 public 으로 생성됐다.** 저장소가 public 이고 `GITHUB_TOKEN` 으로 밀었기 때문으로 보이지만 그 인과는 확인하지 못했다 — 확실한 건 관측 결과뿐이다. VM 에 붙기 전에 로그인 없이 확인할 수 있다.

```bash
img=finshield-backend   # finshield-web 도 같은 방법으로
tok=$(curl -s "https://ghcr.io/token?scope=repository:mosejong/$img:pull" \
  | sed -n 's/.*"token":"\([^"]*\)".*/\1/p')
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $tok" \
  "https://ghcr.io/v2/mosejong/$img/tags/list"
```

`200` 이면 익명으로 받을 수 있다 = public 이고 VM 에서 `docker login` 이 필요 없다. `401`/`403` 이면 private 이라 위의 `pull` 이 인증 오류로 죽는다. 그때는 패키지 설정에서 공개로 바꾸거나(이미지에 비밀은 없다 — 11-1 참고), `read:packages` 만 가진 PAT 으로 `docker login ghcr.io` 한다.

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

### 3-6. 재배포

3-1~3-4 를 이미 한 서버에는 인증서도 DNS 도 그대로 있다. 보통은 이미지 태그
하나만 바꾸면 되지만, **항상 그런 것은 아니다.**

#### 한 줄로 돌리려면 — `deploy/redeploy.sh`

아래 절차 전체를 그대로 실행하는 스크립트가 있다. VM 안에서 돈다.

```bash
cd ~/finshield-ai
./deploy/redeploy.sh v0.9.0
```

**문서가 원본이고 스크립트가 사본이다.** 절차를 바꿀 때는 이 절을 먼저 고친다 —
`tests/test_public_routing.py` 가 둘의 override 목록이 같은지, 둘 다 존재하는
서비스 이름을 부르는지, 둘 다 `--force-recreate` 로 Caddy 를 반영하는지 본다.

스크립트가 손 절차보다 나은 점은 셋뿐이고, 셋 다 **2026-09-05 에 실제로 난
사고**다. 나머지는 똑같다.

- **붙여넣기 사고가 구조적으로 불가능하다.** 그날 `cd ~/finshield-ai` 가 실패했는데
  붙여넣은 나머지 줄이 계속 실행돼서 엉뚱한 기계의 홈 디렉터리에 키 파일이
  만들어졌다. 스크립트에서는 `set -e` 가 거기서 멈춘다.
- **`read -rs` 가 붙여넣기 버퍼가 아니라 터미널에서 읽는다.** 여러 줄을 한꺼번에
  붙여넣으면 `read` 가 입력을 기다리지 않고 지나가서 **0바이트 키 파일**이 생긴다.
- **길이 확인이 `chmod 400` 보다 먼저다.** 순서를 뒤집으면 비어 있다는 사실을
  확인할 권한이 그 시점에 사라진다.

**처음 한 번은 스크립트부터 가져와야 한다.** VM 의 작업본은 스크립트가 생기기
이전 태그에 멈춰 있다 — 없는 파일은 실행할 수 없다.

```bash
cd ~/finshield-ai
git fetch --tags
git checkout v0.9.1 -- deploy/redeploy.sh
./deploy/redeploy.sh v0.9.1
```

**가져오는 태그와 배포하는 태그는 같아야 한다.** 스크립트는 작업본이 더러우면
멈추는데, 이 두 줄이 정확히 작업본을 더럽힌다. 그래서 예외를 딱 하나 두었다 —
**`deploy/redeploy.sh` 한 파일, 그리고 내용이 배포할 태그와 같을 때만.** 다른
태그에서 가져오거나 손으로 고쳤으면 그대로 걸린다.

**두 번째부터는 이 두 줄이 필요 없다.** 스크립트가 태그 전체를 checkout 하기
때문이고, 바로 그때 **자기 자신도 함께 바뀐다.** bash 는 스크립트를 통째로 읽어
두지 않고 실행하면서 조금씩 읽으므로, 그대로 두면 남은 절반을 엉뚱한 바이트
위치부터 읽는다. 그래서 스크립트는 시작하자마자 자기 사본을 만들어 거기서 다시
실행한다(`exec`). **손 절차에는 없던 위험이고 자동화하면서 새로 생긴 것이다.**

스크립트는 **공개 URL 을 찍지 않는다.** 배포한 기계가 스스로 확인하면
라우팅·인증서·DNS 가 검사에서 통째로 빠진다. 마지막에 밖에서 돌릴 명령을
안내하고 끝난다 (3-5).

아래는 그 스크립트가 무엇을 왜 하는지다. **스크립트를 안 쓰더라도 그대로
성립한다.**

#### 먼저: 이미지 밖에서 오는 파일이 바뀌었는가

서버가 쓰는 파일 전부가 이미지 안에 있는 것이 아니다. 두 종류가 **VM 의 저장소
작업본에서 직접** 온다.

| 파일 | 어떻게 쓰이는가 |
|---|---|
| `deploy/Caddyfile` | `compose.https.yaml` 이 `:ro` 로 bind mount 한다 |
| `compose*.yaml` | `docker compose` 가 실행할 때 읽는다 |

**이 둘은 `pull` 로 안 바뀐다.** 태그를 올리고 digest 를 대조해서 전부 맞아도,
작업본이 옛것이면 라우팅과 override 는 옛것 그대로다. 그리고 컨테이너 digest 는
맞으므로 **확인 절차를 정직하게 다 밟아도 통과한다.**

```bash
git diff --name-only <직전에_배포한_SHA>..<새_태그> -- deploy/ 'compose*.yaml'
```

비어 있지 않으면 `.env` 를 고치기 전에 작업본부터 올린다.

```bash
cd ~/finshield-ai
git fetch --tags
git status --short          # 손으로 고친 것이 없어야 한다. .env 는 추적 대상이 아니다
git checkout <새_태그>
```

`deploy/Caddyfile` 이 바뀌었다면 **`up -d` 만으로는 반영되지 않는다.** compose 는
서비스 정의가 같으면 컨테이너를 다시 만들지 않고, mount 된 파일의 내용은 그
정의에 안 들어간다. Caddy 는 그 파일을 뜰 때 한 번 읽는다. **그리고 다시
읽히는 것만으로도 부족하다** — 아래 `up -d` 뒤 두 줄과 그 이유를 본다.

#### 그다음: 마이그레이션이 끼어 있는가

없으면 이 절차가 성립하고, 있으면
`docs/28` P1-3 의 expand/contract 규칙을 지킨 릴리스인지 확인한 뒤에 진행한다.

```bash
git diff --name-only <직전에_배포한_SHA>..<새_태그> -- migrations/
```

비어 있으면 코드만 바뀐 것이다.

**override 목록을 한 번 정하고 변수에 담는다.** 이 절차에서 사고가 나는 자리는
`pull` 도 `up -d` 도 아니고 **`-f` 를 하나 빠뜨리는 것**이다. 세 줄에 같은 목록을
손으로 세 번 쓰면 반드시 한 번은 다르게 쓴다.

```bash
cd ~/finshield-ai

# .env 의 태그 한 줄만 바꾼다. 줄이 없으면 추가한다
if grep -q '^FINSHIELD_IMAGE_TAG=' .env; then
  sed -i 's/^FINSHIELD_IMAGE_TAG=.*/FINSHIELD_IMAGE_TAG=v0.7.0/' .env
else
  echo 'FINSHIELD_IMAGE_TAG=v0.7.0' >> .env
fi
grep '^FINSHIELD_IMAGE_TAG=' .env

DC="docker compose -f compose.yaml -f compose.https.yaml -f compose.deploy.yaml -f compose.gemini.yaml -f compose.public-data.yaml"

$DC pull
$DC up -d

# deploy/Caddyfile 이 바뀐 릴리스에서만. up -d 도, reload 도 이 파일을 반영하지
# 못한다(아래 이유). validate 는 새 컨테이너로 돌린다 — 떠 있는 컨테이너 안에서
# 보면 옛 내용을 본다.
$DC run --rm --no-deps --entrypoint caddy proxy validate --config /etc/caddy/Caddyfile
$DC up -d --force-recreate proxy

$DC images
```

**`reload` 로는 안 된다.** 2026-09-05 에 이 문서가 시키는 대로 `validate` 와
`reload` 를 돌렸고 **둘 다 성공했는데 `/health` 는 계속 404** 였다.

Docker 의 단일 파일 bind mount 는 경로가 아니라 **inode 에 붙는다.** `git checkout`
은 파일을 제자리에서 고치지 않고 **새로 써서 이름을 바꿔 단다.** inode 가 바뀌고,
컨테이너는 이름이 사라진 **옛 inode 를 계속 읽는다.** 그래서 `validate` 도
`reload` 도 **옛 내용을 상대로 정직하게 성공한다** — 거짓말이 아니라 다른 파일을
보고 있는 것이다. 그날 호스트에서 `grep -c public_health deploy/Caddyfile` 은 `2`,
같은 명령을 컨테이너 안에서 돌리면 `0` 이었는데 `reload` 는 `Valid configuration`
이라고 답했다.

**이것이 이 문서에서 네 번째로 발견된 「조용한 성공」이다.** 앞의 셋 —
문서의 `-f` 목록이 저장소보다 짧은 것, `$DC pull` 이 작업본에서 오는 파일을 안
건드리는 것, `up -d` 가 mount 된 파일 내용 변화로 컨테이너를 안 다시 만드는 것 —
과 성질이 같다. **확인 명령이 통과했다는 사실 자체가 반영을 뜻하지 않는다.**

그래서 `--force-recreate` 다. 컨테이너를 다시 만들면 mount 가 지금의 경로를
다시 찾는다. 인증서는 `caddy-data` 볼륨에 있어 재생성으로 잃지 않는다. 문법은
`run --rm` 으로 **뜨기 전에** 본다 — 그 컨테이너는 방금 만들어져서 지금 파일을
본다. 재생성 동안 몇 초 끊기지만, **끊긴 것은 보이고 반영 안 된 것은 안 보인다.**

`.env` 는 **`grep` 으로 그 한 줄만 본다.** 같은 파일에 DB 비밀번호와 프로필 암호화
키가 있어서 `cat` 하지 않는다. 2절의 나머지 두 값(`FINSHIELD_DOMAIN`,
`FINSHIELD_ACME_EMAIL`)은 이미 떠 있는 스택이라면 `.env` 에 있다 — 없으면 compose 가
`:?` 로 거부하므로 애초에 지금 떠 있지 않았을 것이다.

빠뜨리면 안 되는 세 개, 그리고 각각 무엇이 되는지:

| 빠뜨린 것 | 일어나는 일 |
|---|---|
| `-f compose.deploy.yaml` | VM 이 **빌드를 시작하고** OOM 으로 조용히 죽는다 (11-1) |
| `-f compose.gemini.yaml` | 키 secret 이 사라져 설명 계층이 `status: off` 로 떨어진다. 판정은 살아 있어서 화면상으로는 멀쩡해 보인다 |
| `-f compose.public-data.yaml` | 공공데이터 키 secret 이 사라져 **금융상품 전체가 `503`** 이 된다. 판정도 설명도 멀쩡하고 상품만 죽는다 |

두 번째가 더 위험하다. 첫 번째는 죽어서 알게 되고, 두 번째는 **안 죽어서 모른다.**

세 번째는 그 말을 실제로 증명했다. **2026-09-05 검수 전까지 이 줄에 `compose.public-data.yaml` 이 없었다.** 아무도 안 죽었고 아무도 몰랐다. 그래서 지금은 이 명령줄을 `tests/test_public_routing.py` 가 읽어서 저장소의 `compose*.yaml` 전부(staging 제외)와 같은 집합인지 검사한다. **문서가 짧아지면 테스트가 떨어진다.** 새 override 를 만들면 이 줄에 더하는 것이 선택이 아니게 됐다.

마지막 `images` 로 digest 를 확인한다 — 태그는 옮겨 붙지만 digest 는 아니다.
그 값을 12절 릴리스 대장의 값과 대조하면 "무엇이 떠 있는가" 에 답이 된다.

#### 설명 계층을 켜려면 키 파일이 서버에 있어야 한다

`compose.gemini.yaml` 은 `./secrets/gemini_api_key.txt` 를 **파일로** 요구한다.
compose 의 `secrets:` 는 파일이 없으면 스택 자체를 못 올리므로, 키가 아직
서버에 없다면 **override 없이 먼저 올린다.** 그것만으로도
`POST /api/v1/analyze/explanation` 이 404 에서 200 + `available: false` 가 된다 —
경로가 생기고, 계층만 꺼져 있는 상태다. 판정 경로는 어느 쪽이든 영향이 없다.

키를 올릴 때는 **셸 기록에 남기지 않는다.**

```bash
mkdir -p secrets
read -rsp 'Gemini API key: ' KEY && printf '%s' "$KEY" > secrets/gemini_api_key.txt
unset KEY
sudo chown 10001:10001 secrets/gemini_api_key.txt
sudo chmod 400 secrets/gemini_api_key.txt
ls -ln secrets/gemini_api_key.txt      # -r-------- 1 10001 10001
```

`read -rs` 는 입력을 화면에도 히스토리에도 남기지 않는다. `echo '키' > 파일` 로
쓰면 `~/.bash_history` 에 그대로 박힌다. `printf '%s'` 를 쓰는 이유는 `echo` 가
줄바꿈을 붙이기 때문이다 — 뒤에 개행이 붙은 키는 인증에 실패한다.

**소유자를 옮기는 것이 이 절차의 핵심이다.** 이 문서는 2026-08-25 까지
`chmod 600` 만 적어 두었고, 그것이 실제로 서비스를 내렸다. `Dockerfile` 은
`USER finshield`(uid 10001)로 돌고, compose 의 파일 secret 은 호스트 파일의
권한을 그대로 들고 들어간다. uid 1000 소유의 `600` 파일은 컨테이너 안의
uid 10001 에게는 **읽기 거부**다. 그리고 `app/main.py` 의 lifespan 이 시작할 때
런타임을 실제로 조립해 보기 때문에(`verify_llm_runtime_configuration`), 키를
못 읽으면 설명만 꺼지는 것이 아니라 **백엔드가 아예 뜨지 않는다** —
`/analyze` 까지 502 가 된다.

`chmod 644` 로 푸는 것은 답이 아니다. 그러면 VM 의 모든 계정이 키를 읽는다.
소유자를 컨테이너 uid 로 넘기고 `400` 으로 잠그면, 읽을 수 있는 것은 그
컨테이너뿐이다. 호스트 계정은 그 뒤로 키를 못 읽지만 읽을 일이 없다 —
마운트는 root 로 도는 docker 데몬이 한다.

증상과 원인이 멀어지는 자리라 로그를 어디서 보는지 적어 둔다.

```bash
$DC logs --tail=40 backend
```

`$DC` 는 3-6 에서 정의한 그 변수다. 여기서 파일 목록을 다시 적지 않는 이유가 있다 — 이 문서는 목록을 네 군데에 적어 두고 있었고, 그중 하나에만 새 override 를 더하면 나머지 셋이 조용히 옛 구성으로 돈다. 실제로 그렇게 어긋났다.

`LlmRuntimeConfigurationError: ... the API key is missing` 은 **키가 없다는
뜻이 아니다.** `read_secret_setting` 의 `OSError` 가 거기까지 접혀 온 것이고,
`--tail` 을 짧게 주면 뿌리가 잘려서 안 보인다.

그다음 override 를 끼워 다시 올린다.

```bash
$DC up -d
```

키 파일은 `.gitignore` 의 `secrets/` 에 걸려 있어 커밋되지 않는다. 값은 어떤
로그·이슈·채팅에도 붙여 넣지 않는다.

#### 확인

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  https://finshield-ai.duckdns.org/api/proxy/analyze/explanation \
  -H 'Content-Type: application/json' \
  -d '{"text":"검찰청 수사관입니다. 안전계좌로 즉시 이체하세요.","state":"received_only"}'
```

| 결과 | 뜻 |
|---|---|
| 404 | 아직 옛 이미지다. pull 이 안 됐거나 `up -d` 가 web 을 갈아끼우지 않았다 |
| 200 + `status: off` | 새 이미지는 떴고 설명 계층만 꺼져 있다 (override 없이 올림) |
| 200 + `status: failed` | 계층은 켜졌는데 호출이 실패한다 (바로 아래) |
| 502 | **백엔드가 안 떠 있다.** 키 파일 권한을 먼저 본다 |
| 200 + 설명 문장 | 완료 |

`status: failed` 가 1~2초 만에 나오면 모델을 부르기도 전에 거절당한 것이다.
정상 호출은 6~8초 걸린다. 키를 드러내지 않고 컨테이너 안에서 확인한다.

```bash
$DC exec backend python -c '
import io, httpx
k = io.open("/run/secrets/gemini_api_key").read().strip()
print("key_len", len(k))
r = httpx.get("https://generativelanguage.googleapis.com/v1beta/models",
              headers={"x-goog-api-key": k}, timeout=20.0)
print("list_status", r.status_code)
if r.status_code != 200:
    print(r.text[:200].replace(k, "<RED>"))
'
```

`403 Gemini API has not been used in project <번호> before or it is disabled`
가 이 프로젝트에서 실제로 나왔다(2026-08-25). **키가 유효한 것과 그 키의
프로젝트에서 API 가 켜져 있는 것은 다른 조건이다.** AI Studio 에서 키를
만들었다고 해서 그 프로젝트의 `generativelanguage.googleapis.com` 이
활성화되는 것은 아니다.

```bash
gcloud services enable generativelanguage.googleapis.com --project=<PROJECT_ID>
```

재배포도 재시작도 필요 없다 — 활성화는 Google 쪽 상태라 몇 분 뒤 반영되면
돌고 있는 백엔드가 그냥 성공하기 시작한다. **켜기 전에 예산 알림을 먼저
건다.** 이 프로젝트에는 결제 계정이 붙어 있고, 켜는 순간 상한 없는 유료
호출 경로가 하나 열린다. 예산은 알림이지 차단이 아니다 — 실제 제동은
`analyze_explanation` 요청 한도(60초당 10회, IP 기준)가 건다.

API 를 켠 뒤에도 같은 프로브가 `403` 을 냈다. 이번에는 문구가 다르다.

```
Requests to this API generativelanguage.googleapis.com method
google.ai.generativelanguage.v1beta.ModelService.ListModels are blocked.
PERMISSION_DENIED
```

**"켜져 있지 않다" 가 아니라 "차단됐다" 다.** 앞의 것은 프로젝트 상태이고
이것은 키 자신의 제한이다. 콘솔에서 키를 열어 보면 갈래가 둘이다.

| 칸 | 이 프로젝트에서 나온 값 | 뜻 |
|---|---|---|
| 애플리케이션 제한사항 | 없음 | 어디서 불러도 됨 |
| **API 제한사항** | **API 1개 — `Agent Platform API`** | 그 API 말고는 전부 차단 |

이 키는 Vertex Express 경로로 만들어져 서비스 계정에 묶여 있었고, 그래서
목록에 `Gemini API` 를 더하려 하면 **체크박스가 비활성화되고** "현재 선택된
API 제한사항과 결합할 수 없습니다" 가 뜬다. 둘은 상호 배타다 —
`Agent Platform API` 를 **먼저 해제한 뒤** `Gemini API` 를 선택해야 한다.
더하는 것이 아니라 **바꾸는 것**이라는 게 이 화면에서 안 보인다.

바꾸고 나면 재배포 없이 다음 호출부터 성공한다. 실측 `status: ready`,
`model: gemini-3.6-flash`, 5~7초.

세 가지가 전부 `403` 이고 전부 다른 조치를 요구한다는 점을 적어 둔다.

| 본문 | 원인 | 조치 |
|---|---|---|
| `API key not valid` | 키 값 자체 | 키를 다시 만든다 |
| `has not been used in project … or it is disabled` | 프로젝트에서 API 가 꺼짐 | `gcloud services enable` |
| `Requests to this API … are blocked` | 키의 API 제한 목록 | 콘솔에서 제한을 바꾼다 |

#### 금융상품을 켜려면 공공데이터 키 파일이 서버에 있어야 한다

`compose.public-data.yaml` 은 `./secrets/public_data_service_key.txt` 를 **파일로**
요구한다. 파일이 없으면 스택 자체가 안 뜨므로, 키가 아직 서버에 없다면 그
override 없이 먼저 올린다 — 금융상품만 꺼진 채 판정·설명·전세는 전부 돈다.

키는 공공데이터포털에서 「금융위원회 서민금융진흥원 대출상품 정보」 활용신청을
하고 받은 **일반 인증키(Decoding)** 다. 올리는 절차는 Gemini 키와 같다.

```bash
mkdir -p secrets
read -rsp '공공데이터 서비스키: ' KEY && printf '%s' "$KEY" > secrets/public_data_service_key.txt
unset KEY
sudo chown 10001:10001 secrets/public_data_service_key.txt
sudo chmod 400 secrets/public_data_service_key.txt
ls -ln secrets/public_data_service_key.txt      # -r-------- 1 10001 10001
```

`read -rs`·`printf '%s'`·`chown 10001:10001`·`chmod 400` 이 왜 그래야 하는지는 바로
위 Gemini 절에 적은 그대로다. `600` 은 컨테이너가 못 읽고 `644` 는 VM 의 모든
계정이 읽는다.

**Gemini 키와 다른 점이 하나 있다. 이쪽은 없어도 백엔드가 뜬다.** 설명 계층은
lifespan 이 기동할 때 조립을 시도하므로 키가 잘못되면 백엔드가 아예 안 뜨고,
그래서 바로 알게 된다. 상품 쪽은 `get_product_catalog_service()` 가 **첫 요청
때** 조립을 시도하고 실패하면 `503` 을 돌려준다. 컨테이너는 계속 healthy 이고
`/health/ready` 도 초록이다 — 그 검사는 저장소만 보고 상품 제공자는 보지 않는다.
**밖에서 상품을 실제로 불러 보는 것 말고는 알 방법이 없다.** 2026-09-05 까지
아무도 안 불러 봤다.

#### 확인

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  https://finshield-ai.duckdns.org/api/proxy/recommendations \
  -H 'Content-Type: application/json' -d '{"goal":"emergency_cash"}'
```

| 결과 | 뜻 |
|---|---|
| **503** | **설정 누락.** `-f compose.public-data.yaml` 이 빠졌거나 키 파일이 서버에 없다 |
| **502** | **제공자 실패.** 키는 붙었고 공공데이터 호출이 실패했다. 키 값이 틀렸거나 상대편 장애다 |
| 400 | `goal` 값이 enum 에 없다. 부르는 쪽 문제다 |
| 200 | 완료. 본문의 `results` 가 비어 있지 않은지도 같이 본다 |

**이 두 줄을 가르는 것이 이 절의 전부다.** 503 과 502 는 손댈 곳이 다르다 —
앞은 compose 목록이고 뒤는 키 값과 상대편 상태다. Next 프록시가 503 을 그대로
통과시키기 때문에(`web/lib/api/proxy-response.ts` 의 `PASSTHROUGH_STATUSES`)
**VM 에 들어가지 않고도** 이 구분이 밖에 남는다. 2026-09-05 에 돌아온 것은
`503` 이었고, 그래서 서버에 붙기 전에 원인이 정해졌다.

키 값 자체는 로그·이슈·채팅 어디에도 출력하지 않는다. 붙었는지만 본다.

```bash
$DC exec backend python -c '
import io
print("key_len", len(io.open("/run/secrets/public_data_service_key").read().strip()))
'
```

#### 그 릴리스에서 처음 생긴 경로를 하나 찍는다

위 확인은 **설명 계층**만 본다. 12절에 적은 2026-08-25 의 일은 그것만으로는
부족하다는 것을 보여준다 — `verify_public_deployment` 27개 검사가 전부 통과한
상태에서 화면 하나가 통째로 없었다.

그래서 재배포마다 **이번 릴리스에서 처음 들어온 경로**를 하나 골라 같이 찍는다.

```bash
for p in / /check /check/deposit /learn/wealth; do
  printf '%-18s %s\n' "$p" \
    "$(curl -s -o /dev/null -w '%{http_code}' "https://finshield-ai.duckdns.org$p")"
done
```

`v0.3.0` 기준으로 넷 다 `200` 이어야 한다. `/check/deposit` 이 `404` 면 web
이미지가 `bd69925` (#78) 이전이다. 어느 경로를 골라야 하는지는
`git log --diff-filter=A <직전_태그>..<새_태그> -- web/app/` 으로 찾는다.

#### 경로가 없는 릴리스에서는 응답이 표지다

`v0.4.0` 에서 위 명령이 **빈 결과**를 낸다. 새 경로가 하나도 없기 때문이다 — 바뀐
것은 화면이 아니라 **언제 모델을 부르는가**다. 이럴 때 경로를 찍으면 옛 이미지와
새 이미지가 똑같이 `200` 을 내므로 아무것도 구분하지 못한다.

**그 릴리스가 처음 만드는 응답을 찍는다.** `v0.4.0` 의 표지는 근거가 빈 판정에서
모델을 부르지 않는다는 것이고, 그것은 응답에 그대로 보인다.

```bash
python3 -c 'import io,json; io.open("/tmp/low.json","w",encoding="utf-8").write(
  json.dumps({"text":"이번 달 관리비 고지서가 발송되었습니다."}, ensure_ascii=False))'

curl -s --max-time 30 -X POST \
  https://finshield-ai.duckdns.org/api/proxy/analyze/explanation \
  -H 'Content-Type: application/json' --data-binary @/tmp/low.json
```

한글을 셸에 인라인으로 넣지 않는 이유는 12절에 적힌 그대로다 — 깨진 입력을 엔진이
정직하게 `low` 로 판정하고, 그러면 이 검사가 통과한 것처럼 보인다.

| 결과 | 뜻 |
|---|---|
| `status: not_asked` | **`v0.4.0` 이 떠 있다.** 근거가 비어 모델을 부르지 않았다 |
| `status: ready` + 문장 | 아직 `v0.3.0` 이하다. 근거 없는 판정에 유료 호출이 나가고 있다 |
| `status: off` | 새 이미지는 떴고 설명 계층만 꺼져 있다 |

이 문장은 신호·행동·근거가 전부 0 인 판정을 만든다(`analyze_fraud` 로 로컬에서
확인 가능). **`ready` 가 나오면 그 배포는 아무 근거도 없는 자리에서 모델에게 문장을
요구하고 있다는 뜻이다** — `docs/34` 13절이 없는 전화번호가 나온다고 적은 바로 그
자리다.

2026-08-26 에 실제로 찍어 보고 `ready` + 229자를 받았다. 그래서 이 릴리스가 있다.

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
| `health:*` | `/health`·`/health/live`·`/health/ready` 가 200 **이고 본문이 backend 가 낸 값** | 404 면 프록시가 backend 로 안 보낸다는 뜻이다. 상태 코드만 보면 Next 가 낸 200 과 구분되지 않아 본문 값까지 본다 |
| `product:list` / `:detail` / `:compare` | 200 + 1건 이상 | `page:/products` 는 껍데기만 본다. 상품은 브라우저가 따로 부르므로 상품이 전부 죽어도 그 검사는 초록이다 |
| `service_worker_not_cached` | `/sw.js` 에 `no-store` | 낡은 워커가 캐시에 박히면 배포가 사용자에게 도달하지 않는다 |
| `share_target_*` | 200 + `no-store` + `Set-Cookie` 없음 | 공유된 문자 원문이 담긴 응답이다 (`docs/30`) |
| `internal_port:*` | 18000 / 13000 / 5432 전부 닫힘 | 열려 있으면 Caddy 를 우회해 평문으로 붙을 수 있고 HTTPS 를 붙인 의미가 없다 |

공유 왕복 검사는 **고정된 검사 문구**만 보낸다(`SHARE_PROBE_TEXT`). 검사기가 남의 문자 원문을 만들어 낼 이유가 없다.

상품 검사는 목록 → 상세 → 비교를 **목록이 돌려준 식별자로** 이어서 찍는다. 검사기가 식별자를 지어내면 404 가 나고 그 404 는 배포가 아니라 검사기 탓이다. 목록이 실패하면 뒤의 둘은 아예 찍지 않는다 — 원인 하나를 세 번 세면 실패 개수가 원인 개수를 속인다.

`page:*` 와 `product:*` 를 나눈 이유가 이 표에서 제일 중요하다. **화면이 200 이라는 것과 그 화면이 부르는 API 가 산다는 것은 다른 사실이다.** 2026-09-05 에 `page:/products` 는 초록이었고 상품은 전부 503 이었다.

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

**그 숫자는 더 이상 27이 아니다.** 2026-09-05 에 `health:*` 셋과 `product:*` 셋을 더했다. 그리고 위 예행연습 명령줄에는 `compose.public-data.yaml` 이 없으므로 — 예행연습 머신에 키 파일이 없을 수 있고, 없으면 스택이 아예 안 뜬다 — `product:list` 가 `503` 으로 하나 더 실패한다. **그것이 이 검사가 존재하는 이유이므로 예행연습에서는 정상이다.** 상품까지 보려면 키 파일을 올린 뒤 `-f compose.public-data.yaml` 을 붙여 다시 올린다. 이 절의 개수는 2026-09-05 이후 아직 다시 재지 않았다 — 잰 것과 안 잰 것을 구분해서 적는다.

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

3절 전체가 2026-08-18 에 `finshield-ai.duckdns.org` 로 실행됐다. 검증기 **27개 전부 통과, 종료코드 0** — `certificate_trusted` 를 포함해서다. 릴리스 파이프라인도 `workflow_dispatch` 로 두 번 돌아 이미지가 실제로 만들어졌다. 남은 것은 아래다.

- 외부 TLS 등급 측정(SSL Labs 등). 검증기는 프로토콜 버전과 체인까지 보고 암호 스위트 등급은 매기지 않는다.
- ~~갱신 감시를 cron 이 아니라 알림으로 옮기는 것~~ → 2026-08-19 완료. `.github/workflows/certificate-watch.yml` 이 매일 **VM 밖에서** `--certificate-only` 를 돌린다. **첫 갱신은 2026-10-17 무렵**(만료 30일 전). 알림이 실제로 도착하려면 계정 쪽 설정이 필요하고, 이 방식이 조용히 죽는 경우가 둘 있다 — `docs/28` P1-1 에 적었다. 외부 감시(UptimeRobot 등)는 아직 안 걸었다.
- CAA 레코드는 발급자가 확정된 뒤에 건다. 지금 걸면 ZeroSSL 대체 발급 경로를 스스로 막는다.
- **태그 push 경로(`type=ref,event=tag`)는 아직 안 돌았다.** 지금까지 전부 `workflow_dispatch` 였고, 그쪽은 `sha-` 태그만 붙인다. 즉 9-1 의 "이전 버전 태그" 가 아직 사람이 읽을 수 있는 이름으로 존재하지 않는다.
- 롤백(9-1) 리허설 없음. `docs/29` 의 복원 리허설처럼 실제로 이전 태그로 되돌려 보는 절차가 필요하다.
- **부하 시 수치를 모른다.** 11-6 의 메모리·지연은 전부 idle 실측이다. idle 에서 `available` 이 319MB 이고 스왑이 이미 214MB 들어차 있으므로, 부하가 걸렸을 때 먼저 무너지는 쪽은 CPU 가 아니라 메모리일 가능성이 높다.

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
| 리전 | `us-west1-b` (오리건) | **always-free 대상 리전은 `us-west1` / `us-central1` / `us-east1` 뿐이다.** 서울(`asia-northeast3`)에는 무료 등급이 없다. 셋 중 한국에서 가장 가까운 것을 고른다 — 오리건 왕복 110~130ms 대, 아이오와 150~170ms 대. 무료 조건은 셋이 동일하므로 더 먼 쪽을 고를 이유가 없다 |
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

**이 때문에 작업 순서가 바뀐다.** `docs/28` P1-3(배포/롤백)은 원래 공개 이후로 미뤄둔 항목인데, e2-micro 를 고른 이상 **P0-4 의 선행조건**이 된다. 손해만 있는 것은 아니다. 지금의 수동 배포에는 롤백 수단이 아예 없는데, 태그된 이미지를 pull 하는 방식에는 되돌릴 지점이 생긴다. → 2026-08-18 에 `release.yml` + `compose.deploy.yaml` 로 착지했고, 수동 실행(run #1)으로 두 이미지가 ghcr 에 올라가 pull 까지 되는 것을 확인했다. **다만 `v*` 태그를 밀어 본 적은 아직 없다** — 태그 경로만 미검증이다.

> **결제 계정 확인 (2026-08-18).** 후불 Google Cloud 결제 계정이 활성 상태이고 미결제 잔액 ₩0, 청구 기준액 ₩100,000 이다. always-free `e2-micro` 가 요구하는 것은 활성 결제 계정 하나뿐이므로 **이 절의 선행조건은 충족됐다.** $300 무료 체험 크레딧은 없고, 필요하지도 않다 — always-free 는 체험과 별개 프로그램이다. AI Studio 선불 크레딧 ₩70,000 은 Gemini API 전용이라 Compute Engine 요금에는 쓰이지 않는다.

### 11-2. 고정 IP를 먼저 잡는다

기본값인 ephemeral IP 는 인스턴스를 정지했다 켜면 **바뀐다.** 그러면 DNS 가 죽은 주소를 가리키고, Caddy 는 계속 재시도하며, ACME 검증 실패가 0절의 시간당 5회 한도를 태운다. 도메인을 붙이기 전에 잡아 둔다.

먼저 프로젝트를 고르고 **Compute Engine API 를 켠다.** 새 프로젝트에서는 꺼져 있고, 켜지 않으면 아래 첫 명령이 `Compute Engine API has not been used in project ... before or it is disabled` 로 그냥 실패한다. 결제 계정이 프로젝트에 연결돼 있어야 켜진다 — always-free 등급도 활성 결제 계정을 요구한다(11-1).

```bash
gcloud projects list                       # PROJECT_ID 확인
gcloud config set project <PROJECT_ID>
gcloud beta billing projects describe <PROJECT_ID>   # billingEnabled: true 인지
gcloud services enable compute.googleapis.com        # 1~2분 걸린다
```

그다음 주소를 잡는다.

```bash
gcloud compute addresses create finshield-ip --region=us-west1
gcloud compute addresses describe finshield-ip --region=us-west1 --format='value(address)'
```

**2024년부터는 붙어 있어도 과금된다.** 실행 중인 인스턴스에 붙은 외부 IPv4 가 무료였던 것은 그 이전 이야기다. 지금은 시간당 $0.005 선이고, 아무 데도 안 붙어 있으면 요율이 더 높다. always-free 구성에서 실제로 청구되는 항목은 이것 하나뿐이니, 안 쓰게 되면 지운다.

### 11-3. 인스턴스와 방화벽

```bash
gcloud compute instances create finshield \
  --zone=us-west1-b \
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

`gcloud compute ssh finshield --zone=us-west1-b` 로 붙는다. 별도 키 설정은 필요 없다 — gcloud 가 OS Login 으로 처리한다.

### 11-4. VM 안에서

**swap 을 가장 먼저 만든다.** 뒤이어 오는 apt 와 pip 가 메모리를 쓰는데, 1GB 에는 여유가 없다.

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

**Docker 는 배포판 저장소가 아니라 Docker 공식 저장소에서 받는다.** Debian 12(bookworm)에는 `docker-compose-v2` 패키지가 **없다** — compose v2 가 Debian 에 들어온 것은 13(trixie)부터다. `apt-get install docker.io docker-compose-v2` 는 `E: Unable to locate package` 로 실패한다. `docker.io` 만 깔면 엔진은 뜨지만 `docker compose` 가 없어서 이 스택은 한 줄도 못 올린다.

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg git python3-venv

sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources > /dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: $(. /etc/os-release && echo "$VERSION_CODENAME")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker $USER && exec newgrp docker
```

`docker-buildx-plugin` 은 일부러 뺐다. 이 VM 은 빌드하지 않는다(11-1). 필요해지는 상황이 곧 "VM 에서 빌드하려 하고 있다" 는 신호이므로, 없는 편이 낫다.

`python3-venv` 도 **별도 패키지다.** Debian 은 `venv` 모듈을 python3 본체에서 분리해 놓았고, 없으면 아래 `python3 -m venv` 가 `ensurepip is not available` 로 죽는다.

```bash
git clone https://github.com/mosejong/finshield-ai.git && cd finshield-ai
python3 -m venv .venv && .venv/bin/pip install --require-hashes -r requirements.txt
.venv/bin/python scripts/create_local_docker_secrets.py
```

호스트 venv 가 필요한 이유는 앱이 아니라 **스크립트** 다. 앱은 컨테이너 안에서 돈다. 호스트에서 도는 것은 비밀 생성기와 인증서 갱신 감시(6절)뿐이고, 둘 다 `cryptography` 를 쓴다.

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

### 11-6. 실측 (2026-08-18)

도메인 없이 `compose.yaml` + `compose.deploy.yaml` 만으로 한 번 올려 봤다. 포트가 전부 loopback 바인딩이라 외부 노출이 없어서, DNS 와 인증서가 정해지기 전에 해도 되는 검증이다. 여기서 답이 나오는 질문이 두 개다 — **1GB 에서 뜨는가**, 그리고 **재부팅하면 저절로 돌아오는가.**

#### 메모리

| 컨테이너 | 사용 |
|---|---|
| backend (uvicorn worker 2) | 155 MiB |
| web (Next standalone) | 79.7 MiB |
| retention | 50.3 MiB |
| db | 40.1 MiB |
| backup | 0.7 MiB |
| **합계** | **326 MiB** |

호스트 전체는 `used` 735 MiB / `available` 234 MiB 였다. 컨테이너 밖 약 409 MiB 는 `dockerd`(74MB) · `containerd`(31MB) · shim 5개 · GCE 게스트 에이전트 3종(49MB) · systemd 다. 특별히 큰 것은 없다.

`vmstat 1 5` 의 `si`/`so` 가 전부 0 이라 **활성 스와핑은 없다.** `free` 에 잡힌 swap 은 앞선 `pip install` 이 밀어낸 잔재다 — 리눅스는 여유가 생겨도 swap 페이지를 자동으로 되돌리지 않는다. CPU 는 5개 샘플 중 4개가 idle 92~100% 였다.

**Caddy 는 아직 얹지 않았다.** 30~50 MiB 를 더 쓸 것이므로 `available` 은 190 MiB 근처가 된다. 들어가지만 여유가 그만큼 준다. 그리고 위 숫자는 전부 **idle** 이다 — 부하 시 수치는 모른다.

#### 재부팅

`sudo reboot` 뒤 swap 이 `/etc/fstab` 으로 자동 복구됐고, 컨테이너 5개가 자동 기동해 **39초 만에** `/health/ready` 가 `ready` 를 냈다.

**그런데 여기서 결함이 하나 나왔다.** 데이터도 도메인도 없을 때 재부팅해 본 이유가 이것이다.

```
pg_dump: error: connection to server at "db" (172.18.0.6), port 5432 failed: Connection refused
{"event":"backup_run","status":"failed","timestamp":"2026-08-18T10:08:24Z","stage":"dump"}
```

`restart: unless-stopped` 로 데몬이 컨테이너를 되살릴 때는 compose 의 `depends_on` 이 **적용되지 않는다.** 그건 `docker compose up` 이 해석하는 조건이다. 그래서 backup 이 db 보다 먼저 떴다. 여기까지는 정상적인 경합이고, 문제는 그 다음이었다 — 루프가 실패에도 성공과 같은 `INTERVAL`(기본 24시간)을 자고 있어서 다음 시도가 하루 뒤였다. heartbeat 는 tmpfs 라 재시작으로 사라지므로, 그동안 healthcheck 도 unhealthy 다. **재부팅 한 번이 하루치 백업 공백을 만드는 구조였다.**

`FINSHIELD_BACKUP_RETRY_SECONDS`(기본 60초)로 고쳤다. 상세는 `docs/29` 2절.

기존 백업 테스트 32건이 이걸 놓친 이유도 분명하다. **전부 `--once` 로 돌아서 `while` 루프의 대기 정책을 한 번도 실행하지 않았다.** 진짜 루프를 띄우는 검사 2건을 추가했다.

#### backend 가 영구히 굳었다 — uvicorn 멀티워커

여기가 이번 배포에서 제일 오래 걸린 부분이다. `APP_ENV=production` 조합으로 처음 `docker compose up -d` 를 했더니 backend 가 **끝내 healthy 가 되지 않았다.** 저절로 낫지도 않았다.

```
finshield-backend-1  | Waiting for child process [7]
finshield-backend-1  | Child process [7] died
finshield-backend-1  | Waiting for child process [9]
finshield-backend-1  | Child process [9] died
        (무한 반복)
```

이 로그가 전부다. **트레이스백이 한 줄도 없다.** healthcheck 는 `exit=-1 Health check exceeded timeout (5s)`, 밖에서 `curl` 하면 `(56) Recv failure: Connection reset by peer`, `docker stats` 는 backend 1694% / db 526% CPU 였다.

진단이 두 번 틀렸다. 기록해 둔다.

| 가설 | 왜 틀렸나 |
|---|---|
| OOM 이다 | `dmesg` 에 OOM killer 흔적이 없고 `available` 이 427 MiB 였다 |
| e2-micro 버스트 크레딧 소진이다 | `load average 0.09`, `vmstat` 의 `st` 가 내내 0. 게다가 워커 2개를 **포그라운드로** 띄우니 2분 동안 `/health/ready` 가 20~30ms 로 멀쩡히 답했다 |

세 번째는 추측을 멈추고 uvicorn 소스를 읽었다. 기여 요인이 셋이다.

1. **워커는 fork 가 아니라 spawn 이다.** `uvicorn/_subprocess.py` 가 `multiprocessing.get_context("spawn")` 을 쓴다. 리눅스에서도 그렇다. 워커 하나마다 인터프리터가 처음부터 부팅되고 FastAPI 앱을 새로 import 한다.
2. **ping 에 답하는 스레드는 그 부팅이 끝난 뒤에 생긴다.** `Process.target()` 안에서 `always_pong` 스레드를 띄운다. 그 전까지는 **아무도 답하지 않는 창** 이다.
3. **부모는 5초를 기다리고 SIGKILL 한다.** `Multiprocess.keep_subprocess_alive()` 가 0.5초마다 돌면서 `timeout_worker_healthcheck`(기본 5초) 안에 답이 없으면 `process.kill()` 후 새 워커를 띄운다.

그래서 `up -d` 가 migration·retention·web·backend 를 한꺼번에 올려 부팅이 5초를 넘기는 순간, 부모가 자식을 죽이고 곧바로 **새 인터프리터를 두 개 더** 띄운다. 경합이 원인인데 대응이 경합을 키우는 자기강화 루프다. 한 번 들어가면 나오지 못한다. SIGKILL 이라 파이썬은 아무것도 남기지 못하고, `STARTUP_FAILURE` 분기도 타지 않는다 — uvicorn 은 이걸 "기동 실패" 가 아니라 "굳었다" 로 판정하기 때문이다.

고친 것은 둘이고, 성격이 다르다.

- **`--timeout-worker-healthcheck 30`** (`Dockerfile`) — 이쪽이 결함 수정이다. 기본 5초는 호스트가 무엇이든 기동이 느려지는 순간 위 루프로 들어간다. 30초인 이유는 컨테이너 healthcheck 예산(5초 × 12회 ≈ 60초)보다 짧아야 굳은 워커를 uvicorn 이 먼저 잡기 때문이다.
- **`FINSHIELD_UVICORN_WORKERS=1`** (`.env`) — 이쪽은 사양 결정이다. 워커가 1개면 uvicorn 은 `Multiprocess` 를 아예 만들지 않고 `server.run()` 을 직접 부른다. ping·SIGKILL 경로가 완화되는 게 아니라 **존재하지 않는다.** 1GB 에서 두 번째 워커는 메모리만 쓰고 처리량을 주지 않는다.

이 값으로 `up -d` 하니 backend 가 **12.4초** 만에 healthy 가 됐고 7개 컨테이너가 전부 올라왔다.

검사는 `tests/test_backend_workers.py` 8건이다. `--workers` 가 CMD 로 돌아오면(그러면 uvicorn 이 `WEB_CONCURRENCY` 를 무시한다) 실패하고, 타임아웃을 기본값으로 되돌려도, 컨테이너 예산 밖으로 늘려도, 이미지 기본값과 compose 기본값이 갈라져도 실패한다.

VM 에서 급히 고칠 때는 추적되지 않는 `compose.host-small.yaml` 을 직접 만들어 썼다. 위 수정이 배포된 뒤 그 파일을 지우고 `COMPOSE_FILE` 에서 뺐다 — 안 지우면 저장소 설정과 실제로 도는 설정이 조용히 갈라진다. **지우는 순서가 중요하다.** 이전 이미지는 CMD 에 `--workers 2` 가 박혀 있어서 `WEB_CONCURRENCY` 를 무시한다. 새 이미지를 `pull` 하기 **전에** override 를 빼면 그대로 다시 굳는다. 지금 `COMPOSE_FILE` 은 추적되는 세 파일뿐이고, `docker compose top backend` 에 uvicorn 프로세스가 **하나만** 보인다(로그도 `Started parent process` 가 아니라 `Started server process`).

#### HTTPS 발급

`compose.acme-staging.yaml` 로 먼저 예행연습했다. 백엔드가 위 문제로 서 있는 동안 proxy 는 아예 뜨지 못했으므로 **발급 시도가 0회였다 — Let's Encrypt 쿼터를 한 건도 쓰지 않았다.** staging 을 먼저 거는 이유가 이것이다.

| | staging | 운영 |
|---|---|---|
| challenge | `tls-alpn-01` | `http-01` |
| issuer | `(STAGING) Baloney Bulgur YE2` | `Let's Encrypt YE2` |
| 체인 검증 | (신뢰 안 함) | `Verify return code: 0 (ok)` |

Caddy 는 `tls-alpn-01` 을 먼저 시도하고 안 되면 `http-01` 로 내려간다. **80 과 443 이 둘 다 열려 있어야 한다.** 운영 발급이 `http-01` 로 됐다는 것은 80 이 실제로 쓰였다는 뜻이다.

staging→운영 전환은 볼륨을 지우지 않아도 된다. Caddy 가 CA 디렉터리별로 인증서를 따로 보관해서, override 를 빼고 `up -d proxy` 하면 새로 발급받는다.

도메인은 **DuckDNS 무료 서브도메인**을 썼다. 비용이 0 이어야 했다. `duckdns.org` 는 Public Suffix List 에 있어서 Let's Encrypt 주당 발급 제한이 다른 사용자와 공유되지 않는다 (`mooo.com` 은 목록에 없어서 전 세계가 주 50장을 나눠 쓴다 — 무료 도메인이라고 다 같지 않다). 다만 이 도메인 계열은 피싱 호스트로 차단하는 곳이 있다. 사기 방어 제품을 그런 도메인에 올리는 것은 제품으로서 어색하므로, 돈이 생기면 바꾼다.

#### 그밖에 확인된 것

- `docker compose pull` 로 backend 331MB / web 303MB 를 받았다. VM 에서 빌드하지 않는 경로가 실제로 성립한다.
- 첫 dump 가 `backups/finshield-…Z.dump` (8093B, `root:root`) 로 떨어졌다. **`cap_add: DAC_OVERRIDE` 가 실기에서 처음 검증됐다** — 지금까지 리눅스 CI 에서만 확인한 수정이다.
- `scripts/verify_public_deployment.py` 를 **VM 밖의 개발 PC**(다른 네트워크)에서 돌려 27/27 통과했다. 이 중 `internal_port` 세 건(18000·13000·5432)이 처음으로 밖에서 실증됐다 — 지금까지 loopback 바인딩과 방화벽은 설정으로만 참이었고 실제로 두드려 본 적이 없었다.
- dump 는 `0644`, `backups/` 는 `0755` 라 로컬 사용자면 읽을 수 있다. 지금은 문제가 아니다 — 프로필은 암호화 저장이고 복호화 키는 `secrets/`(`0700`) 안에 있어서 dump 하나로는 아무것도 열리지 않는다. 0절의 분리가 의도대로 작동하는 상태다.

#### 첫 응답이 1초 걸린다 — 콜드 페이지지 코드가 아니다

배포 직후 로그에 `/health/ready` 가 `duration_ms 1000.032` 로 찍혔다. 손으로 5회 재보니 **3.75 / 1.02 / 1.00 / 1.23 / 0.24초** 였다. 1초 근처가 반복되니 상수처럼 보였고, 실제로 `verify()` 안의 카탈로그 리플렉션(`inspect(...).has_table()`)을 범인으로 지목했다. **틀렸다.**

경로를 나눠 재니 갈라졌다. `/health` 는 DB 를 전혀 건드리지 않는다.

| | 5회 실측 |
|---|---|
| `/health` (DB 없음) | 3.7 ~ 5.1 ms |
| `/health/ready` (DB 2회 + 리플렉션 2회) | 21.0 ~ 21.8 ms, 산포 1ms 미만 |

**`verify()` 전체가 17ms 다.** 컨테이너 healthcheck 예산 60초 대비 고칠 이유가 없다. 여기를 최적화하려 들지 말 것 — 앞의 1초와 무관하다.

원인은 메모리다. `vmstat` 의 steal 은 0 이라 하이퍼바이저 throttling 이 아니었고, 대신 이렇게 나왔다.

```
Mem:  969Mi total   650Mi used   319Mi available
Swap: 2.0Gi total   214Mi used          <- si 8 (되읽는 중)
```

1GB 호스트에 214MB 가 디스크로 밀려나 있고, 샘플링 순간 실제로 되읽고 있었다. 필요한 페이지가 스왑에 있으면 요청이 디스크 I/O 를 기다린다 — 그래서 0.24초와 3.75초가 같은 루프에서 나온다. **고정 비용이 아니라 콜드 스타트 비용이고**, 그 5회 루프 자체가 페이지를 되읽어 놓은 덕에 이어진 측정이 21ms 로 안정됐다. 사양 문제이지 결함이 아니다.

**`docker stats --no-stream` 의 CPU% 를 믿지 말 것.** 같은 조사에서 web 컨테이너가 205.77% 로 찍혔다. 2 코어를 태우는 것처럼 보이지만 아티팩트다 — 직전 샘플 없이 첫 델타를 계산해서 부풀려 찍는다. 3초 간격 5회로 다시 재니 `0 / 0 / 154.80 / 0 / 0` 이었고, 결정적인 반증은 `docker compose top web` 의 누적 CPU 시간이다.

```
C   STIME  TIME
2   12:11  00:00:35     <- 약 29분 동안 CPU 35초 = 평균 2%
```

CPU 를 볼 때는 `docker stats` 순간값이 아니라 누적 `TIME` 이나 `uptime` 의 load average 로 교차 확인한다.

## 12. 릴리스 대장

태그는 옮겨 붙을 수 있고 digest 는 그렇지 않다. 사고 조사 때 "그때 무엇이 돌고
있었나" 에 답하는 것은 아래 오른쪽 칸이다.

| 태그 | 커밋 | 만든 날 | 이미지 | digest |
|---|---|---|---|---|
| `v0.1.0` | `30ba35b` | 2026-08-19 | `finshield-backend` | `sha256:c9c0864ccc28cd5ff500f548b617a3f21200103f3efbd7a1140cd24fc2f00ffe` |
| `v0.1.0` | `30ba35b` | 2026-08-19 | `finshield-web` | `sha256:38ed9740a6d320fae3b174187246ac5f99202b4da8f383b811502f7e9fb25f15` |
| `v0.2.0` | `d11bdaf` | 2026-08-23 | `finshield-backend` | `sha256:5c7f6e4eba7e1aa7fac96f6b7db2c0c6f0da8988fa714623e1104fc274692f23` |
| `v0.2.0` | `d11bdaf` | 2026-08-23 | `finshield-web` | `sha256:529b18bc02d72a4e7e998a257dd8fc3e3c6749b9908adf2fe781e17294500727` |
| `v0.3.0` | `ec43f86` | 2026-08-25 | `finshield-backend` | `sha256:2337229408dba3cb53d74e538e374eebe69e5f13d97ddab23c0a43703ae77e1e` |
| `v0.3.0` | `ec43f86` | 2026-08-25 | `finshield-web` | `sha256:99ebf6c6732cf1f4187d0a9e09e16b77960ba8a3d51c33a0964b8c7aebf79d1e` |
| `v0.4.0` | `3511c3d` | 2026-08-26 | `finshield-backend` | `sha256:98af77a9a8177e18905ab5ffb346e6cb85469ffe00257b2dfe74ac19cc468146` |
| `v0.4.0` | `3511c3d` | 2026-08-26 | `finshield-web` | `sha256:1a259cd8e30980590e29ffd301450f992c06ba13c2a6cbede80ac7b9aacd2897` |
| `v0.5.0` | `6777a74` | 2026-09-04 | `finshield-backend` | `sha256:11426233598f5bdfeddc1993e53278320f344dc0da3566920a380f0230fe182f` |
| `v0.5.0` | `6777a74` | 2026-09-04 | `finshield-web` | `sha256:fd95124c5a958667c376c0603702a21e9bd007e044cc6e137a96e07a5f45209a` |
| `v0.6.0` | `ec59a9f` | 2026-09-04 | `finshield-backend` | `sha256:2260f03b106fecb38e09aee2c16d005dbff6da90ebfb07575550990bcaf96824` |
| `v0.6.0` | `ec59a9f` | 2026-09-04 | `finshield-web` | `sha256:6d4783e4c3f6b2389053e3d695622788aecbf1789672bbe3f22fc20f3a9fa697` |
| `v0.7.0` | `4a99418` | 2026-09-04 | `finshield-backend` | `sha256:a140a7a49b910c4613e53780cfd512e32e7cd42f411bcb4401a5452767c24c00` |
| `v0.7.0` | `4a99418` | 2026-09-04 | `finshield-web` | `sha256:c99bb50e1edef4d2dc1fe4e64f662eb5691a6eb355c18f9d22358c9c152785f2` |
| `v0.8.0` | `c64e199` | 2026-09-05 | `finshield-backend` | `sha256:3cf82928330fea3e082b83d9fe21ae08a51b3b350911fdc4614881cbb0629d77` |
| `v0.8.0` | `c64e199` | 2026-09-05 | `finshield-web` | `sha256:cfe3eb9826b9d516bb138b9f6521238502cb022e604937c82a20707711a9272e` |
| `v0.9.0` | `60adf09` | 2026-09-05 | `finshield-backend` | `sha256:a0fae15682800ee7aab18348da69f1990ec423cf4c244d5b904cf34c03134fae` |
| `v0.9.0` | `60adf09` | 2026-09-05 | `finshield-web` | `sha256:7bb59525427d613dd23b80b062773d1fccbf1ce742d6d97ba69d7dc57066092c` |
| `v0.9.1` | `27b250c` | 2026-09-05 | `finshield-backend` | `sha256:2683568ffe4592261a49586499291004cdeb51f98ee070e7ee3b8639d8a7aab3` |
| `v0.9.1` | `27b250c` | 2026-09-05 | `finshield-web` | `sha256:b1d0aea40097566b3fbd048c47adaabcf4e507d6c6006010cdde6163107cc3b9` |

`v0.1.0` 은 **태그로 만든 첫 릴리스**다. 그 이전 두 번은 `workflow_dispatch` 라
`sha-<커밋>` 태그만 붙었다.

**이미지를 만든 것과 배포한 것은 다르다.** 위 표는 만들어진 이미지의 대장이고,
그중 무엇이 실제로 공개 URL 에서 돌고 있었는지는 아래에서 따로 적는다. 이 둘을
같은 줄에 적어 두면 "태그를 밀었으니 배포됐겠지" 로 읽히고, 실제로 그렇게 읽어서
아래의 일이 났다.

### 만들었지만 배포하지 않은 태그 — `v0.9.0`

`v0.9.0` 의 이미지 두 개는 실제로 만들어졌고 위 대장에 그대로 남겨 둔다. 지우면
**왜 건너뛰었는지가 같이 사라진다.**

배포에 쓰지 않은 이유는 그 태그의 `deploy/redeploy.sh` 가 **자기 자신의 첫
실행을 통과하지 못하기 때문**이다. 구멍이 둘이었고, 둘 다 스크립트를 실제로
올리려고 명령을 적어 보다가 나왔다 — **코드가 초록인 것과 아무 상관이 없었다.**

- 스크립트를 먼저 가져오는 `git checkout <태그> -- deploy/redeploy.sh` 가
  작업본을 더럽히고, 스크립트의 "작업본에 손댄 것이 있다" 검사에 **자기 자신이
  걸린다.**
- digest 대조를 **체크아웃된 `docs/31`** 에서 했다. 그런데 digest 는 태그를 민
  **뒤에** 만들어지므로 **어떤 태그도 자기 digest 를 담을 수 없다.** 항상 "릴리스
  대장에 태그가 없다" 로 죽는다. 대장은 태그가 아니라 **main 에서 계속 자라는
  기록**이므로, 이제 `git show origin/main:docs/31-...` 로 읽는다.

`v0.9.1` 이 이 둘을 고친 태그다. **태그를 옮겨 붙이지 않았다** — `v0.9.0` 이
가리키는 이미지는 그대로 두고 새 번호를 썼다. 태그가 움직이면 대장의 digest 가
무엇을 가리키는지 아무도 확신할 수 없다.

### 공개 URL 이 실제로 돌리고 있던 것 (2026-08-25 확인)

`v0.2.0` 을 만든 뒤에도 **VM 은 그것을 받지 않았다.** 밖에서 경로를 찍어 보면
어느 이미지인지 좁혀진다.

| 경로 | 응답 | 그 경로가 들어온 커밋 |
|---|---|---|
| `/learn/wealth` | `200` | `d2ce019` (#34) |
| `/check/deposit` | `404` | `bd69925` (#78) |
| `POST /api/proxy/analyze/explanation` | `404` | `c5fca16` (#67) |

`#34` 는 있고 `#67` 은 없는 이미지는 하나뿐이다 —
`sha-4457f0efa3ec0053ae2b5ab0135167fdec80bc7c` (2026-08-18 빌드), 즉 9-1 이
"되돌릴 대상" 으로 적어 둔 바로 그 이미지다. 공개 URL 은 `v0.1.0` 도 `v0.2.0` 도
아니라 **그 이전 이미지를 7일 동안 서비스하고 있었다.**

여기서 배울 것은 두 가지다.

1. **`verify_public_deployment` 는 이 상태를 잡지 못한다.** 27개 검사가 전부
   통과했는데도 화면의 절반이 없었다. 그 스크립트가 재는 것은 TLS·헤더·포트이지
   *어떤 빌드가 떠 있는가* 가 아니다. 배포 확인에는 **그 릴리스에서 처음 생긴
   경로를 하나 골라 찍는 검사**가 따로 있어야 한다.
2. **릴리스 대장에 배포 칸이 없었다.** 만든 날만 적고 올린 날을 적지 않으면,
   대장을 보면서도 안 올라간 것을 알 수 없다.

### 배포 대장 — 공개 URL 에 실제로 올라간 것

위 표의 짝이다. 만든 날이 아니라 **올린 날**을 적는다.

| 올린 날 | 태그 | 올린 방법 | 확인한 경로 |
|---|---|---|---|
| 2026-08-18 | `sha-4457f0e…` | 3-4 최초 기동 | — |
| 2026-08-25 | `v0.3.0` | 3-6 재배포 | `/check/deposit` `200`, `POST /api/proxy/analyze` `200`, `.../explanation` `200 status: ready` |
| ~~2026-08-26~~ | ~~`v0.4.0`~~ | **올라간 적 없음** | 2026-09-04 확인 — 바로 아래 |
| 2026-09-04 | `v0.5.0` | 3-6 재배포 | 근거 없는 문장에 `status: not_asked`, held-out v1.0 `fh-806` 에 `level: high` + 신호 2종, 실제 관리비 고지에 `level: low`, `verify_public_deployment` 27/27 |
| ~~2026-09-04~~ | ~~`v0.6.0`~~ | **올라간 적 없음** | 2026-09-04 확인 — 아래 `v0.6.0 도 올라가지 않았다` |
| 2026-09-04 | `v0.7.0` | 3-6 재배포 | 프로브 셋 다 통과 — 데모 문장 `status: ready` 3/3(`gemini-3.6-flash`, 263·261·232자, 8.4~12.8초), 관리비 문장 `not_asked`, 예방 안내문 `level: low`·`score: 0`. 데모 `/analyze` `high`·70점·신호 4·유형 3·행동 5·근거 3. `images` 의 IMAGE ID 가 12절 대장 digest 와 일치(`a140a7a49b91` / `c99bb50e1ede`). `verify_public_deployment` 27/27 |
| 2026-09-05 | `v0.9.1` | **`deploy/redeploy.sh` 가 처음으로 배포함** | 프로브 1~11 전부 통과. 콜드 상품요청 `200` 5.65초 → 바로 다음 요청 `200` 1.01초(직전 회차의 9.64초 `502` 가 사라짐), 상세 `200` 0.50초, 비교 `200` 0.48초 2건, `/health` `200 ok`·`/health/live` `alive`·`/health/ready` `ready`, `/internal/metrics` `404`(열지 않은 대로), 데모 `status: ready`(`gemini-3.6-flash`, 259자, 8.76초), 관리비 `not_asked` 0.50초, 예방 안내문 `level: low`·`score: 0`, 송금 상태 전환 시 행동 5→9·근거 3→5, 전세 120% `high`. `images` digest 가 12절 대장의 v0.9.1 두 줄과 일치. `verify_public_deployment` 33/33. **브라우저 전용 두 칸도 같은 날 확인** — 상태 전환 시 결과 id 가 바뀌고 행동 5→9·근거 3→5 가 화면에서도 같은 값, 프로필 저장·재접속·삭제·삭제 후 재접속까지 정상. 화면 폭만 못 쟀다(검수 도구에 viewport emulation 없음) |

`v0.4.0` 줄에는 **취소선을 쳤다.** 2026-08-26 에 이 줄을 미리 적어 두고 확인 칸을
`*(배포 후 채운다)*` 로 비워 두었는데, 2026-09-04 에 밖에서 찍어 보니 그 배포는
일어나지 않았다. 이미지는 만들어졌고 위 대장에 digest 도 있지만 VM 은 받지 않았다.

배운 것을 한 줄로: **확인 칸을 "배포 후 채운다" 로 비워 두면, 배포가 빠진 줄과
확인만 아직 안 한 줄이 구분되지 않는다.** 앞으로 이 표에는 **밖에서 찍어 본 뒤에만
줄을 추가한다.** 미리 적어 둔 줄은 대장이 아니라 계획이고, 계획을 대장에 적으면
대장이 하는 일이 없어진다.

#### `v0.6.0` 을 올린 뒤 찍을 것 — **근거가 있는** 문장 하나

`v0.5.0` 배포 확인은 "근거 없는 문장에 `status: not_asked`" 를 찍었다. 그 검사는
통과했고, 같은 날 **근거가 있는 문장은 `status: failed`** 였다 — 설명 계층이 죽어
있었는데 확인 절차가 그것을 묻지 않았다(`docs/34` 18절).

그래서 이 릴리스의 확인은 **두 방향을 다** 찍는다. 하나만 찍으면 그 방향만 알게
된다.

```bash
cat > demo.json <<'EOF'
{"text": "[국제발신] 고객님 명의로 개설된 계좌가 대포통장 범죄에 연루되어 검찰 수사가 진행 중입니다. 오늘 중 아래 안전계좌로 자금을 이체하지 않으면 계좌가 전부 동결됩니다. 수사기밀이므로 가족을 포함해 누구에게도 알리지 마시고, 원격 확인 앱을 설치한 뒤 담당 수사관에게 직접 연락 주십시오.", "state": "received_only", "persona": "early_career"}
EOF

cat > normal.json <<'EOF'
{"text": "[○○아파트 관리사무소] 9월분 관리비 고지서가 발송되었습니다. 납부 기한은 9월 30일이며, 세대별 고지 금액은 관리사무소 게시판과 우편 고지서에서 확인하실 수 있습니다.", "state": "received_only", "persona": "early_career"}
EOF

BASE=https://finshield-ai.duckdns.org/api/proxy/analyze/explanation

# 1. 근거가 있는 문장 — status 가 ready 여야 하고 text 가 비어 있으면 안 된다
curl -s -X POST "$BASE" -H 'Content-Type: application/json' --data-binary @demo.json

# 2. 근거가 없는 문장 — 여전히 not_asked 여야 한다 (v0.4.0 동작이 살아 있는가)
curl -s -X POST "$BASE" -H 'Content-Type: application/json' --data-binary @normal.json
```

1번이 `{"status":"failed"}` 로 오면 이 릴리스가 안 올라간 것이다. `v0.5.0` 이 그
응답을 내고 있었고, 그것이 이 릴리스가 존재하는 이유다.

한글 payload 는 **UTF-8 파일에 담아 `@file` 로 보낸다.** 셸에 직접 적으면 인코딩이
조용히 깨져서 "모델이 이상한 답을 했다" 로 보인다.

`v0.1.0` 과 `v0.2.0` 은 **이 표에 줄이 없다.** 만들어졌지만 배포된 적이 없다.
줄이 없는 것이 이 표가 하는 일이다 — 위 대장만 보면 세 릴리스가 나란히
있으니 다 올라간 것처럼 읽힌다.

#### 공개 URL 이 실제로 돌리고 있던 것 (2026-09-04 확인)

제출 마감 사흘 전에 다시 찍었다. 이번에는 릴리스마다 **처음 생긴 경로**를 찍는
8월 25일 방법이 통하지 않는다 — `v0.4.0` 과 `v0.5.0` 은 새 경로를 만들지 않았고
같은 경로의 **답이 달라졌을** 뿐이다. 그래서 응답 모양을 찍었다.

| 찍은 것 | 받은 답 | 무엇을 말해 주나 |
|---|---|---|
| `POST /api/proxy/analyze/explanation`<br>`{"text":"이번 달 관리비 고지서가 발송되었습니다."}` | `status: ready` + 문장 | **`v0.4.0` 이전.** `v0.4.0` 은 근거가 없으면 모델을 안 부르고 `not_asked` 를 돌려준다 |
| `POST /api/proxy/analyze`<br>held-out v1.0 `fh-806` 본문 | `level: low`, `signals: []`, `fraudTypes: []` | **PR #109 이전.** 지금 코드는 이 문장에 신호를 켠다 |

두 검사 다 **유료 호출을 쓰지 않는다.** 첫 줄은 `not_asked` 가 돌아오면 모델을
부르지 않은 것이고, 거꾸로 `ready` 가 돌아왔다는 것 자체가 **근거 하나 없는 문장에
유료 호출이 나가고 있었다**는 뜻이다. 이 배포 지연은 화면이 낡았다는 문제만이 아니라
**돈이 새고 있었다**는 문제이기도 했다.

`v0.3.0` 이후 `main` 에 커밋 40개가 들어왔다. 그중 사용자가 보는 답이 바뀌는 것은
설명 프롬프트 v2, 근거 없을 때 모델 안 부르기, 출력 검증기(grounding checks),
결제 목적지 게이트다.

**이 표가 두 번째로 같은 일을 잡았다.** 8월 25일에는 `v0.1.0`·`v0.2.0` 이 만들어만
지고 7일 동안 안 올라간 것을 잡았고, 이번에는 `v0.4.0` 이 아흐레다. 두 번 다 원인이
같다 — 릴리스는 태그 push 로 자동인데 재배포는 사람이 Cloud Shell 에서 손으로
하는 일이라, **자동인 쪽만 일어나고 손으로 하는 쪽이 빠진다.** 대장을 두 개로
나눠 둔 것이 이 격차를 보이게 하는 유일한 장치다.

#### 2026-09-04 재배포 (`v0.3.0` → `v0.5.0`)

열흘 만에 올렸다. 마이그레이션도 compose 변경도 없어 **순수 이미지 교체**였다
(`git diff --name-only v0.3.0..main -- migrations/ alembic.ini` 가 비어 있고,
`compose*.yaml` 과 두 `Dockerfile` 도 마찬가지다). 백엔드가 읽는 환경변수에도
새로 생긴 것이 없다.

`pull` 이 127초, 스택 전체 교체가 134초. `migration` 은 이미 head 라 no-op 으로
끝났다. `images` 의 IMAGE ID 가 12절 릴리스 대장의 digest 앞 12자리와 일치했다 —
`11426233598f`(backend), `fd95124c5a95`(web).

밖에서 찍은 것:

| 찍은 것 | 받은 답 | 뜻 |
|---|---|---|
| 근거 없는 관리비 문장 → `/explanation` | `status: not_asked`, `text: null` | `v0.4.0` 이상. **모델을 안 부른다** |
| held-out v1.0 `fh-806` → `/analyze` | `level: high`, 신호 `authority_impersonation`·`money_transfer_request` | #109 이상. 열흘 전에는 `low` + `signals: []` 였다 |
| 실제 관리비 고지(`납부 기한` 포함) | `level: low`, 신호 없음 | 결제 목적지 게이트가 **정상 쪽에서 값을 치르지 않았다** |
| `verify_public_deployment --domain finshield-ai.duckdns.org` | 27/27, 실패 0 | TLS 73일 남음(만료 2026-11-16), 내부 포트 셋 다 닫힘 |

세 번째 줄이 이 배포에서 제일 확인하고 싶었던 것이다. #109 는 셋 안에서 공짜로
보였던 어휘 추가를 셋 밖의 진짜 고지 문자로 반증하고 목적지 조건으로 바꾼
회차였는데, 그 판단이 운영에서도 같은지는 여기서만 확인된다.

2026-08-25 재배포에서 실제로 일어난 일을 순서대로 적어 둔다. 이미지 교체
자체는 한 번에 됐고, 시간을 쓴 것은 그다음이다.

1. `.env` 의 `FINSHIELD_IMAGE_TAG` 를 `v0.3.0` 으로 바꾸고 `pull` → `up -d`.
   네 컨테이너 전부 교체, `migration` 은 이미 head 라 no-op 으로 종료.
   `/check/deposit` 이 `404` 에서 `200` 이 됐다.
2. VM 의 저장소가 `4457f0e` 에 멈춰 있어 `compose.gemini.yaml` 이 없었다.
   그 파일은 `f6d5485` (#66) 에서 들어왔다. `git pull --ff-only` 로 해결.
   **compose 파일들은 그 사이 하나도 바뀌지 않았으므로**(`compose.yaml`,
   `compose.https.yaml`, `compose.deploy.yaml`, `Caddyfile` 전부 무변경)
   당겨도 돌고 있는 스택에 영향이 없다.
3. 키 파일 권한 때문에 백엔드가 startup 에서 죽었다. `/analyze` 까지 `502`.
   3-6 에 적어 둔 `chmod 600` 이 원인이었다 — 지금은 고쳤다.
4. 백엔드는 살아났지만 설명이 `status: failed`. 프로젝트에서 Gemini API 가
   꺼져 있었다(`403`). 3-6 의 확인 절차에 이 갈래를 추가했다.
5. API 를 켠 뒤에도 `403`. 이번에는 키가 `Agent Platform API` 로 제한돼
   있었다. 제한을 `Gemini API` 로 바꾸자 `status: ready`. 3-6 에 세 가지
   `403` 을 갈라 적었다.

3번과 4번은 둘 다 **설명 계층에서만 생긴 문제인데 3번은 서비스 전체를
내렸다.** 있으면 좋고 없어도 되는 기능이 필수 경로를 끌고 내려가는 구조라는
뜻이고, 이건 권한을 고친 것과 별개로 남아 있는 설계 문제다 (`docs/34` 참조).

#### 2026-09-04 재확인 — `v0.6.0` 도 올라가지 않았다

바로 위 절이 "`v0.6.0` 을 올린 뒤 찍을 것" 으로 프로브 두 개를 적어 뒀다. 그
프로브를 그대로 돌렸고, **1번이 `{"status":"failed"}` 로 왔다.** 그 절이 미리
적어 둔 판정문이 이것이다 — "1번이 `failed` 로 오면 이 릴리스가 안 올라간 것이다."

| 찍은 것 | 받은 답 | 뜻 |
|---|---|---|
| 데모 문장 → `/explanation` (4회) | `status: failed` (3.8s / 4.1s / 9.9s / 12.0s) | 재현된다. 우연이 아니다 |
| 짧은 사칭 문장 → `/explanation` (3회) | `status: ready`, `model: gemini-3.6-flash`, 239~244자 | 키도 주 모델도 살아 있다 |
| 관리비 문장 → `/explanation` | `status: not_asked` | `v0.4.0` 이상은 맞다 |
| 데모 문장 → `/analyze` | `level: high`, 신호 4, 유형 3, 행동 5, 근거 3 | 판정 계층은 로컬과 **완전히 같다** |
| held-out v0.2 `fh-061` → `/analyze` | `level: medium`, `score: 35`, 신호 0, 행동 0 | **PR #117 이전.** 지금 코드는 이 문장에 `low` · 0점을 준다 |

**두 번째 줄이 이 표에서 제일 헷갈리는 자리다.** 설명이 돌아오니까 처음에는
`v0.6.0` 이 올라간 줄 알았다. 아니다 — `v0.5.0` 도 짧은 사건에서는 통과한다.
`v0.6.0` 이 고친 것은 **기관 이름 앞에 평범한 낱말이 하나 붙었을 때** 그 이름을
지어낸 것으로 보는 결함이고, 그 결함은 근거가 여러 줄인 사건에서만 터진다.
그래서 확인 프로브를 **근거가 있는 문장 하나**로 못 박아 뒀던 것이고, 그
문장에서만 갈렸다.

원인을 코드로 되짚었다. 같은 입력을 로컬에서 세 벌의 코드로 돌렸다 (`--limit`
없이 사건 하나, 모델 둘씩).

| 코드 | 주 모델 | 대체 모델 | 결과 |
|---|---|---|---|
| `main` (`7665acf`) | `ok` 245자 | `ok` 304자 | `ready` |
| `v0.6.0` (`ec59a9f`) | `ok` 315자 | `ok` 304자 | `ready` |
| `v0.5.0` (`6777a74`) | `rejected_ungrounded_org` | `rejected_ungrounded_org` | **`failed`** |

**공개 URL 이 내는 답과 일치하는 것은 `v0.5.0` 뿐이다.** 두 모델이 같은 사유로
함께 죽는 것까지 같다. `v0.6.0` 태그 메시지가 예고한 모양 그대로다.

같은 일이 **세 번째**다. `v0.1.0`·`v0.2.0` 이 7일, `v0.4.0` 이 아흐레,
`v0.6.0` 이 당일. 원인도 세 번 다 같다 — 릴리스는 태그 push 로 자동이고
재배포는 사람이 Cloud Shell 에서 손으로 하는 일이라, **자동인 쪽만 일어난다.**

세 번째에 와서 이 표가 하는 일이 하나 더 보인다. 앞의 두 번은 "화면이 낡았다"
였는데, 이번에는 **고쳐 둔 안전 검사가 사용자에게 닿지 않고 있었다.** 공개 URL
에서 서비스의 대표 데모 문장을 넣으면 지금 이 순간에도 "왜 위험한지" 가 비어
있다. 판정은 맞게 나오므로 화면은 반쯤 정상으로 보이고, 그래서 눈으로는
못 잡는다.

**그래서 다음 배포는 `v0.6.0` 이 아니라 `v0.7.0` 이다.** `v0.6.0` 을 올리면
데모 문장은 살아나지만, 그 뒤에 들어온 두 가지가 여전히 빠진다.

| 빠지는 것 | 공개 URL 에서 지금 보이는 증상 |
|---|---|
| PR #115 (`e0f43c5`) | 엔진이 근거로 붙인 `전자금융거래법 제6조` 를 모델이 읽으면 그 설명을 거부한다. 계좌·인증수단을 넘긴 **가장 심각한 상태**에서 설명이 사라진다 |
| PR #117 (`6d013e7`) | 계좌 대여를 **말리는** 예방 안내문에 `주의 · 35점` 이 붙고, 그 아래 신호도 행동도 근거도 없다 |

#### `v0.7.0` 을 올린 뒤 찍을 것

위 절의 프로브 두 개를 **그대로** 쓴다. 바꾸지 않는다 — 바꾸면 지난 회차와
대조가 안 된다. 거기에 이번 릴리스가 고친 것 하나를 더한다.

```bash
cat > lend.json <<'EOF'
{"text": "통장이나 체크카드를 빌려주면 본인도 처벌받을 수 있습니다. 어떤 이유로도 전달하지 마세요.", "state": "received_only"}
EOF

# 3. 예방 안내문 — level 이 low 이고 score 가 0 이어야 한다
curl -s -X POST https://finshield-ai.duckdns.org/api/proxy/analyze \
  -H 'Content-Type: application/json' --data-binary @lend.json
```

| 프로브 | `v0.7.0` 이 맞으면 | 안 올라갔으면 |
|---|---|---|
| 1. 데모 문장 → `/explanation` | `status: ready` + 문장 | `failed` (= `v0.5.0`) |
| 2. 관리비 문장 → `/explanation` | `not_asked` | `ready` (= `v0.4.0` 미만) |
| 3. 예방 안내문 → `/analyze` | `level: low`, `score: 0` | `medium` · `35` (= `v0.7.0` 미만) |

세 개를 다 찍는 이유는 **각각 다른 릴리스 경계를 가리키기** 때문이다. 하나만
찍으면 그 경계만 알게 되고, 이번 회차가 바로 그것으로 틀렸다 — 2번만 보고
`v0.4.0` 이상이라는 것까지는 알았지만 그 위 세 릴리스는 구분하지 못했다.

한글 payload 는 **UTF-8 파일에 담아 `@file` 로 보낸다.**

#### 2026-09-04 — `v0.7.0` 이 올라갔다

위 표를 그대로 찍었다. 세 칸이 다 왼쪽이다.

| 프로브 | 나온 값 | 가리키는 경계 |
|---|---|---|
| 1. 데모 문장 → `/explanation` | `status: ready` · `gemini-3.6-flash` · 263자 (3회 반복 263·261·232자, 8.4~12.8초) | `v0.6.0` 이상 ✅ |
| 2. 관리비 문장 → `/explanation` | `not_asked` (0.48초) | `v0.4.0` 이상 ✅ |
| 3. 예방 안내문 → `/analyze` | `level: low` · `score: 0` (0.55초) | `v0.7.0` 이상 ✅ |

**1번은 같은 날 오전에 4회 전부 `failed` 였다.** 같은 입력, 같은 URL 이다. 바뀐 것은 올라간 이미지 하나뿐이다.

곁들여 찍은 것:

- 데모 문장 `/analyze` → `high` · 70점 · 신호 4 · 유형 3 · 행동 5 · 근거 3 — 로컬 `main` 과 값이 같다.
- held-out `fh-061` → `low` · 0점. 오전에는 이 자리가 `medium` · 35점이었다 (PR #117 이 고친 것).
- `/` `200` 0.69초, `verify_public_deployment --domain finshield-ai.duckdns.org` **27/27**, 실패 0.
- `$DC images` 의 IMAGE ID 가 `a140a7a49b91`(backend) · `c99bb50e1ede`(web) 로 12절 대장의 digest 앞 12자리와 일치한다. **태그가 아니라 digest 로 확인한 것이다.**

`migration-1` 은 `Exited` 로 정상 종료했다. `v0.5.0..v0.7.0` 에 `migrations/` 변경이 없으므로 할 일이 없는 것이 맞다.

#### `v0.8.0` 을 올린 뒤 찍을 것

**올리기 전에 적는다.** 찍고 나서 기준을 정하면 나온 값이 기준이 된다.

앞 회차 프로브 3개를 **그대로 유지**하고 네 개를 더한다. 이번 릴리스는 앞의
어느 회차와도 성격이 다르다 — 고친 것 셋이 **서로 다른 곳에서** 오기 때문에
한 칸이 통과했다고 다른 칸을 유추하면 안 된다.

| 무엇이 고쳐졌나 | 어디서 오는가 | 안 됐으면 무엇이 빠진 것 |
|---|---|---|
| 판정·화면 (프로브 1~3) | **이미지** | `.env` 태그 / `$DC pull` |
| `/health` 공개 (프로브 4~5) | **VM 작업본의 `deploy/Caddyfile`** | `git checkout` / `up -d --force-recreate proxy` |
| 금융상품 (프로브 6~7) | **VM 의 키 파일 + override 목록** | `secrets/public_data_service_key.txt` / `-f compose.public-data.yaml` |

```bash
# 4. 공개 health — 리버스 프록시가 backend 로 보내는가
curl -s -o /dev/null -w '%{http_code}\n' https://finshield-ai.duckdns.org/health
curl -s https://finshield-ai.duckdns.org/health

# 5. 준비 상태
curl -s https://finshield-ai.duckdns.org/health/ready

# 6. 금융상품 목록
curl -s -X POST https://finshield-ai.duckdns.org/api/proxy/recommendations \
  -H 'Content-Type: application/json' -d '{"goal":"emergency_cash"}'

# 7. /internal/metrics 는 열지 않았다 — 404 가 나오는 것이 맞다
curl -s -o /dev/null -w '%{http_code}\n' https://finshield-ai.duckdns.org/internal/metrics
```

| 프로브 | `v0.8.0` 이 맞으면 | 안 됐으면, 그리고 그 뜻 |
|---|---|---|
| 4. `/health` | `200` + `"status":"ok"` | `404` = 작업본이 옛 `Caddyfile` · `400` = Host 재작성이 안 먹었다 |
| 5. `/health/ready` | `200` + `"ready"` | 같은 원인. `503` 이면 라우팅은 됐고 **백엔드가 준비 안 된 것** — 원인이 다르다 |
| 6. 상품 목록 | `200` + 상품 1건 이상 | `503` = 키 파일 없음 또는 override 누락 · `502` = 키는 있고 공공데이터가 실패 |
| 7. `/internal/metrics` | `404` | `200` 이면 **의도와 다르게 열린 것**이다 |

**4번과 5번이 200 이어도 본문을 본다.** Next 가 그럴듯한 200 을 줄 수 있으므로
`"ok"`/`"ready"` 라는 낱말이 실제로 있어야 한다. 검사기의 `health:*` 칸이 같은
것을 보고, 그 규칙을 지키는 테스트가
`tests/test_public_deployment.py::TestPublicHealth` 에 있다.

**7번을 표에 넣은 이유**는 이번 수정이 세 경로만 열었기 때문이다. 열지 않기로
한 것이 열려 있으면 그것도 배포 결함이고, 제출 원고가 이 경로를 「내부 전용」
이라고 적고 있으므로 원고와도 어긋난다.

그다음 검사기를 밖에서 한 번 돌린다. **칸 수가 27 에서 늘었다** — 늘어난
숫자를 여기 미리 적지 않는 이유는 아직 실제 배포에서 재 본 적이 없기 때문이다.
실패 0 인지만 본다.

```bash
python -m scripts.verify_public_deployment --domain finshield-ai.duckdns.org
```

마지막으로 **브라우저에서만 확인되는 것 하나** — 결과 화면의 「상황이
달라졌어요」. 문자를 넣어 결과를 본 뒤 상태를 「송금함」으로 바꿔 다시 확인하면
**주소의 결과 id 가 바뀌고** 행동 목록이 늘어야 한다. curl 로는 확인되지
않는다(메모리 한 칸에 사는 값이라 서버에 흔적이 없다).

#### `v0.9.1` 을 올린 뒤 찍을 것

**올리기 전에 적는다.** 찍고 나서 기준을 정하면 나온 값이 기준이 된다.

이번 회차는 **처음으로 스크립트가 배포한다.** 그래서 확인할 것이 두 겹이다 —
서비스가 맞게 떴는가, 그리고 **스크립트가 절차를 실제로 밟았는가.**

올리는 명령. 스크립트가 VM 작업본에 아직 없으므로 가운데 두 줄이 한 번 필요하다.

```bash
cd ~/finshield-ai
git fetch --tags
git checkout v0.9.1 -- deploy/redeploy.sh
./deploy/redeploy.sh v0.9.1
```

**`v0.9.0` 이 아니라 `v0.9.1` 이다.** `v0.9.0` 의 이미지는 만들어졌지만 그
태그의 스크립트로는 배포가 시작되지도 못한다 — 아래 "만들었지만 배포하지 않은
태그" 를 본다.

앞 회차 프로브 1~7 을 **그대로 유지**하고 네 개를 더한다. 이번에 고친 것은
**콜드 경로의 시간**이므로, 새 프로브는 상태 코드만이 아니라 **걸린 시간**을
같이 잰다.

```bash
# 8. 콜드 경로 — 재배포 직후 첫 요청. 느린 것은 통과, 502 는 실패다
curl -s -o /dev/null -w '첫번째 %{http_code} %{time_total}s\n' \
  -X POST https://finshield-ai.duckdns.org/api/proxy/recommendations \
  -H 'Content-Type: application/json' -d '{"goal":"emergency_cash"}'

# 9. 바로 이어서 두 번째. 캐시가 찼으면 1초대다
curl -s -o /dev/null -w '두번째 %{http_code} %{time_total}s\n' \
  -X POST https://finshield-ai.duckdns.org/api/proxy/recommendations \
  -H 'Content-Type: application/json' -d '{"goal":"emergency_cash"}'

# 10. 상세 — 8번 응답에서 꺼낸 id 를 URL 인코딩해서 넣는다 (`:` 는 %3A)
curl -s -o /dev/null -w '%{http_code}\n' \
  'https://finshield-ai.duckdns.org/api/proxy/products/202608%3A1'

# 11. 두 개 비교 — 같은 목록에서 꺼낸 id 두 개
curl -s -X POST https://finshield-ai.duckdns.org/api/proxy/products/compare \
  -H 'Content-Type: application/json' \
  -d '{"product_ids":["202608:1","202608:2"]}'
```

| 프로브 | `v0.9.1` 이 맞으면 | 안 됐으면, 그리고 그 뜻 |
|---|---|---|
| 8. 첫 요청 | `200`, **20초 안** | `502` = 예산이 아직 8초 (이미지가 안 바뀌었다) · `503` = 키 또는 override 누락이라 원인이 다른 것 |
| 9. 두 번째 | `200`, **3초 안** | 첫 번째와 비슷하게 느리면 **캐시가 안 물린 것**이고 TTL 변경이 안 올라간 것이다 |
| 10. 상세 | `200` | `404` = id 형식이 다르다(8번 응답에서 그대로 꺼낸다) · `502` = 예산 문제가 이 경로에만 남았다 |
| 11. 비교 | `200` + 상품 2건 | 같은 구분 |

**8번이 9초대여도 통과다.** 이번 수정은 콜드 경로를 **빠르게** 만든 것이 아니라
**끊기지 않게** 만든 것이다. 빠른 것과 안 죽는 것을 같은 칸에서 재면, 다음에
제공자가 조금 느려졌을 때 또 「고장」으로 읽는다.

그리고 **스크립트가 밟았는지**를 따로 본다. 스크립트의 출력이 아니라 결과를
본다 — 스스로 「했다」고 말하는 것은 증거가 아니다.

```bash
cd ~/finshield-ai
git describe --tags               # v0.9.1 이어야 한다
grep '^FINSHIELD_IMAGE_TAG=' .env # v0.9.1 이어야 한다
$DC images                        # digest 가 12절 대장의 v0.9.1 두 줄과 같아야 한다
$DC exec proxy grep -c public_health /etc/caddy/Caddyfile
```

마지막 줄이 **이번 회차에서 가장 중요한 한 칸이다.** 호스트가 아니라
**컨테이너 안**에서 세는 것이고, 여기서 `0` 이 나오면 `--force-recreate` 가
안 먹었다는 뜻이다 — 그때는 `/health` 가 200 이어도 다음 Caddyfile 변경이
같은 방식으로 조용히 빠진다.

그다음 검사기를 밖에서 돌린다. 실패 0 인지만 본다.

```bash
python -m scripts.verify_public_deployment --domain finshield-ai.duckdns.org
```

#### 2026-09-05 — `v0.9.1` 이 올라갔다

위에 미리 적어 둔 표를 그대로 찍었다. **기준을 나중에 만들지 않았다.**

| 프로브 | 미리 적은 기준 | 나온 값 |
|---|---|---|
| 1. 데모 문장 → `/explanation` | `ready` + 문장 | `ready` · `gemini-3.6-flash` · 259자 · 8.76초 ✅ |
| 2. 관리비 문장 → `/explanation` | `not_asked` | `not_asked` · 0.50초 ✅ |
| 3. 예방 안내문 → `/analyze` | `low` · `0` | `low` · `0` · 0.50초 ✅ |
| 4. `/health` | `200` + `"ok"` | `200` `{"status":"ok"}` ✅ |
| 5. `/health/ready` | `200` + `"ready"` | `200` `ready` (`/health/live` 는 `alive`) ✅ |
| 6. 상품 목록 | `200` + 1건 이상 | `200` · 325건 · 기준월 202608 · 제공자 `financial_services_commission` ✅ |
| 7. `/internal/metrics` | `404` | `404` ✅ |
| 8. 콜드 첫 요청 | `200`, 20초 안 | `200` · **5.65초** ✅ |
| 9. 바로 두 번째 | `200`, 3초 안 | `200` · **1.01초** ✅ |
| 10. 상세 | `200` | `200` · 0.50초 (`202608:1`) ✅ |
| 11. 두 개 비교 | `200` + 2건 | `200` · 0.48초 · `items` 2 ✅ |

**8번이 이번 회차의 이유다.** 직전 확인에서 같은 요청이 9.64초에 `502` 였고,
바로 이어 찍은 두 번째가 1.11초에 `200` 이었다. 두 번 찍은 것이 원인을 갈랐다 —
제공자가 죽은 것이 아니라 **우리가 기다리기를 멈춘 것**이었다. 이번에는 첫
요청이 살아서 돌아왔고, 5.65초는 예산 안이다.

전세와 상태 전환도 같이 찍었다. 둘 다 이번 릴리스가 고친 것은 아니지만,
**고치지 않은 것이 그대로인지**를 보는 칸이다.

| 찍은 것 | 나온 값 |
|---|---|
| 전세 보증금 2억 / 시세 2.5억 / 선순위 1억 | `200` 0.66초 · `high` · 비율 **120%** · `band_is_service_rule: true` · 신호 4 · 행동 3 · 공식 근거 4 |
| 데모 문장, 상태 `received_only` | `high` · 70점 · 신호 4 · 유형 3 · 행동 5 · 근거 3 · 전부 `live` |
| 같은 문장, 상태 `transferred_money` | `high` · 70점(같음) · **행동 5 → 9** · **근거 3 → 5** · 결과 id 다름 |
| 정상 관리비 문장 | `low` · 0점 · 신호 0 · 행동 0 · 근거 0 |

상태를 바꿨을 때 **점수는 그대로이고 행동만 늘어난다.** 맞는 모양이다 — 문장의
위험도는 내가 무엇을 했는지와 무관하고, 달라지는 것은 **지금 해야 할 일**이다.
늘어난 넷은 `CONTACT_112`, `CONTACT_FINANCIAL_INSTITUTION`,
`DO_NOT_FORWARD_MONEY`, `PRESERVE_EVIDENCE` 로 전부 수습 쪽이다.

전세의 `band_is_service_rule: true` 도 그대로다. 120% 라는 숫자와 "80% 를 넘으면
높은 구간" 이라는 기준이 **같은 응답 안에서 출처가 갈라져 있다.** 비율은 계산이고
구간은 이 서비스의 보수적 판단이며, 화면도 그렇게 말한다.

**`$DC exec proxy grep -c public_health` 는 따로 찍지 않았다.** 대신 밖에서
`/health` 가 `200 {"status":"ok"}` 로 왔다 — 이 경로는 새 `Caddyfile` 에만 있고,
**돌고 있는 설정**이 그것을 backend 로 보내지 않으면 나올 수 없는 답이다. 컨테이너
안의 grep 보다 강한 증거다(파일이 맞아도 안 물렸을 수 있지만, 라우팅이 되면
물린 것이다). 다음 회차에는 둘 다 찍는다 — 한쪽만 남기면 다음 사람이 왜
안 찍었는지 모른다.

#### 같은 날 — 브라우저에서만 보이는 두 칸도 확인됐다

위 표의 상태 전환은 **엔진이 답을 바꾼다**는 것까지만 말해 준다. 화면이 그 답을
다시 받아 오는지는 사람이 눌러 봐야 안다 — 그 값은 메모리 한 칸에 살아서
서버에 흔적이 없다. Cloud Browser 로 실제 클릭·입력한 결과다.

| 눌러 본 것 | 나온 값 |
|---|---|
| 결과 화면 「상황이 달라졌어요」 → 「돈을 보냈어요」 | 정상 동작 |
| 결과 id | `a-mtogd8cd-l1m7dd` → `a-mtogdvbz-11uxwu` **바뀜** |
| 행동 목록 | **5 → 9** (curl 로 잰 값과 같다) |
| 공식 근거 | **3 → 5**, 출처 링크 표시 |
| AI 설명 | 두 상태 모두 `gemini-3.6-flash` 설명 표시 |
| 프로필 저장 | 입력값과 계산 결과 `90만 원 / 10.0% / 2.8개월` |
| 저장 후 새로고침 | `/profile` 동일 값 유지 |
| 프로필 삭제 → 재접속 | 검수값 없음, 고정 예시와 「직접 입력하기」만 |
| 상품 목록 · 상세 · 비교 | 202608 · 325건 / `새희망홀씨Ⅱ` 원문·출처 / 선택 2/2 비교 |
| `/health` · `/health/ready` · `/internal/metrics` | `ok` · `ready` · 의도한 `404` |

**행동 5 → 9 가 화면과 API 에서 같은 값이다.** 이 한 줄이 이번 확인의 요점이다 —
엔진이 답을 바꾸는 것과 화면이 그 답을 받아 오는 것은 서로 다른 고장이 될 수
있고, 이제 둘 다 찍혔다.

검수용 프로필은 **삭제하고 재접속까지 확인했다.** 남겨 두면 다음 사람이 남의
데이터를 보고 판단하게 된다.

#### 이 회차에서 확인하지 못한 한 칸 — 화면 폭

Cloud Browser API 에 **viewport / device emulation 이 없다.** 그래서 공개 URL 에
붙은 상태로는 특정 모바일 폭에서의 배치를 재지 못했다. 위 표의 어느 칸도 이것을
대신하지 않는다.

지금 있는 증거는 **2026-08-13 실측**이다(`docs/devlog/2026-08-13/`) — 375×812 ·
768×900 · 1280×900 에서 하단 네비/사이드 네비 전환과 본문 폭 375 · 560 · 680px 을
직접 쟀다. 그 뒤로 `web/components/layout/` 과 `web/app/globals.css` 는
**한 번도 바뀌지 않았다.** 즉 그때 잰 셸이 지금 배포된 셸이다.

**그래도 "확인함" 이 아니라 "그때 쟀고 그 뒤로 안 바뀌었다" 로 적는다.** 그 사이
새로 생긴 화면이 둘 있고(`/check/deposit`, `/offline`) 그 둘은 폭을 재 본 적이
없다. 셸이 같다는 것과 그 안의 내용이 좁은 폭에서 넘치지 않는다는 것은 다른
주장이다.

**재는 대신 훑기라도 했다.** 폭을 못 재니 그 둘의 마크업에서 **좁은 폭에서
넘치는 알려진 원인**을 찾았다. 없었다.

| 흔한 원인 | `/check/deposit` · `/offline` |
|---|---|
| 고정 px 폭 (`w-[…px]`) | 없음 |
| `table` / `whitespace-nowrap` | 없음 |
| 링크 텍스트가 원문 URL | 없음 — 한국어 제목을 쓴다(`국세징수법 제109조 미납국세 등의 열람`). 한글은 어디서나 줄바꿈된다 |
| flex 자식이 안 줄어듦 | `min-w-0` 이 걸려 있다 — 폭을 강제하는 것이 아니라 넘침을 막는 쪽이다 |
| 근거 링크 줄바꿈 | `flex-wrap` |

**이것은 좁힌 것이지 잰 것이 아니다.** 알려진 원인이 없다는 것과 375px 에서
실제로 안 넘친다는 것은 여전히 다른 주장이다. 다음에 브라우저 폭을 바꿀 수 있는
도구가 손에 들어오면 이 두 화면부터 재면 된다 — 무엇을 재야 하는지가 이 표에
적혀 있다.

#### 2026-09-05 — Gemini 키에 IP 제한을 걸었다

제출 전 마지막 운영 변경이다. 키가 새더라도 **VM 의 주소 밖에서는 못 쓰게** 만든다.

**거는 순서가 이 작업의 전부다.** IP 제한은 잘못 걸면 조용히 전부 막는다 —
사이트는 200 으로 뜨고 「왜 위험한지」 칸만 안 그려진다. 그래서 주소를 두 번,
서로 다른 뜻으로 확인했다.

| 확인 | 명령 | 값 |
|---|---|---|
| 예약된 고정 주소인가 | `addresses describe finshield-ip --format='value(address,addressType,status)'` | `104.198.12.219  EXTERNAL  IN_USE` |
| 그 주소가 **이 VM 에** 붙어 있나 | 같은 명령 `--format='value(users)'` | `.../zones/us-west1-b/instances/finshield` |
| VM 이 **실제로 나갈 때** 쓰는 주소인가 | `instances describe finshield --format='value(networkInterfaces[0].accessConfigs[0].natIP)'` | `104.198.12.219` |

**앞의 둘과 마지막은 다른 질문이다.** 앞의 둘은 "붙어 있는 주소", 마지막은
"구글 API 서버가 보게 될 발신 주소"다. Cloud NAT 를 쓰면 이 둘이 갈리고, 그때
앞의 값을 걸면 전부 막힌다. 셋이 같은 것을 보고 나서 걸었다.

건 값은 애플리케이션 제한 **IP 주소 `104.198.12.219`** ＋ API 제한
**Generative Language API** 하나다.

**걸기 전에 먼저 찍었다.**

| 프로브 | 제한 전 | 제한 후 |
|---|---|---|
| 데모 문장 (받기만 함) | `ready` · `gemini-3.6-flash` · 11.53초 | `ready` · `gemini-3.6-flash` · 7.69초 |
| 같은 문장 (송금함) | — | `ready` · `gemini-3.6-flash` · **2.45초** |
| 정상 관리비 문장 | — | **`not_asked`** · 0.46초 |

**제한 전 값이 없으면 제한 후 값이 무엇을 뜻하는지 알 수 없다.** 실패했을 때
"원래 그랬던 것" 과 "방금 내가 막은 것" 이 같은 화면으로 보인다. 이 프로젝트가
`502` 를 두 번 찍어 갈랐던 것과 같은 이유다.

두 번째 프로브가 **2.45초에 성공한 것**이 이번 확인의 요점이다. 제한이 잘못
걸렸다면 여기서 걸린다. 세 번째의 `not_asked` 는 근거가 없을 때 모델을 부르지
않는 경계가 그대로라는 뜻이다 — **막힌 것과 안 부른 것은 다르고**, 그 둘을
가르지 않으면 정상 동작이 고장으로 보고된다.

CI 는 이 제한에 걸리지 않는다. `ci.yml` 이 실제 키가 아니라
`ci-placeholder-not-a-real-key` 를 쓴다 — 이 키의 사용처는 VM 하나뿐이다.

**되돌리는 법:** 애플리케이션 제한을 「없음」으로 바꾸고 저장한다. 심사 기간에
AI 설명이 죽는 것이 제한을 못 거는 것보다 훨씬 나쁘므로, 원인 분석보다
되돌리기가 먼저다.

### 되돌릴 대상

`v0.1.0` 직전에 배포돼 있던 것은 `sha-4457f0efa3ec0053ae2b5ab0135167fdec80bc7c`
(2026-08-18 빌드) 다. 9-1 의 절차에 이 값을 그대로 `FINSHIELD_IMAGE_TAG` 로 넣으면
된다 — 버전 태그가 아니어도 태그는 태그다.

`4457f0e..30ba35b` 사이에 `migrations/` 변경이 없으므로 이 되돌리기는 스키마를
건드리지 않는다. **`alembic downgrade` 는 어느 경우에도 부르지 않는다** (9-1).

`4457f0e..ec43f86` 사이에도 `migrations/` 변경이 없다 (2026-08-25 확인:
`git diff --name-status 4457f0e ec43f86 -- migrations/` 가 빈 출력). 즉 지금
밀려 있는 이미지에서 `v0.3.0` 으로 올라가는 것도, 다시 내려오는 것도 스키마를
건드리지 않는다. 되돌리기는 `FINSHIELD_IMAGE_TAG` 를 이전 값으로 되돌리고
`up -d` 하는 것으로 끝난다.

`.env.example` 에 그 사이 늘어난 항목은 `FINSHIELD_LLM_PROVIDER`,
`GEMINI_API_KEY` / `GEMINI_API_KEY_FILE` 셋뿐이고 **셋 다 선택이다.** 비워 두면
설명 계층이 꺼진 채로 뜨고 `POST /api/v1/analyze/explanation` 이 `200` +
`available: false` 를 돌려준다. 판정 경로는 영향을 받지 않는다. 그러므로
**키 없이 먼저 올려도 안전하다** — 키는 그다음에 붙인다 (3-6).

### 두 이미지 모두 익명 pull 가능하다

2026-08-25 재확인. `ghcr.io/mosejong/finshield-backend`, `finshield-web` 둘 다
토큰 없이 `tags/list` 가 `200` 이고 `v0.3.0` manifest 도 익명으로 읽힌다. VM 에서
`docker login` 이 필요 없다. 확인 방법은 3-2 에 있다 — **공개 범위는 짐작하지 말고
매번 확인한다.**

### `latest` 는 붙지 않기로 했는데 붙어 있었다

`release.yml` 주석은 "`latest` 를 붙이지 않는다" 라고 적어 두었지만,
`docker/metadata-action` 의 기본 `flavor` 가 `latest=auto` 라 semver 태그를 밀
때마다 `latest` 가 따라 붙고 있었다. 2026-08-25 확인 시점에 두 패키지의
`latest` 는 `v0.3.0` 과 같은 digest 를 가리키고 있었다.

`flavor: latest=false` 를 명시해 앞으로는 붙지 않게 했다. **이미 올라간
`latest` 태그는 그대로 남아 있으므로 배포에 쓰지 않는다** — 대장에 없는 태그는
되돌릴 좌표가 되지 못한다.
