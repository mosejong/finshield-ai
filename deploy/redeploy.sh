#!/usr/bin/env bash
# 태그 하나를 실제로 서비스에 올린다. VM 안에서 돈다.
#
#   ./deploy/redeploy.sh v0.8.0
#
# `docs/31` 3-6 의 절차를 그대로 실행한다. 절차 자체는 바뀌지 않는다 — 바뀌는
# 것은 **누가 순서를 지키는가** 다.
#
# 2026-09-05 에 사람이 그 절차를 손으로 밟다가 세 번 미끄러졌고, 셋 다 문서를
# 더 잘 써서 막을 수 있는 종류가 아니었다.
#
#   1. `cd ~/finshield-ai` 가 실패했는데 붙여넣은 나머지 줄이 계속 실행됐다.
#      엉뚱한 기계의 홈 디렉터리에 키 파일이 만들어졌다. → `set -e` 와
#      스크립트 자기 위치 기준 `cd` 로 구조적으로 불가능해진다.
#
#   2. `read -rsp` 가 여러 줄 붙여넣기 안에 있어서 입력을 기다리지 않고
#      지나갔다. 0바이트 파일이 생겼다. → 스크립트가 실행하는 `read` 는
#      붙여넣기 버퍼가 아니라 터미널에서 읽는다.
#
#   3. 길이를 확인하기 전에 `chmod 400` 을 걸어서, 비어 있다는 사실을 확인할
#      권한이 그 시점에 사라졌다. → 여기서는 확인이 먼저다.
#
# 그리고 이것보다 오래된 실패가 하나 더 있다. `-f` 목록이 저장소보다 짧아서
# 금융상품이 배포 첫날부터 503 이었다 (`docs/31` 0절). 목록을 다시 손으로 쓰는
# 대신, 여기서는 저장소에 실제로 있는 `compose*.yaml` 과 대조하고 다르면 멈춘다.
#
# 왜 bash 인가: `deploy/` 의 다른 스크립트는 `sh` 다 — 그쪽은 python 도 bash 도
# 없는 postgres alpine 컨테이너 안에서 돌기 때문이다. 이 스크립트는 VM 호스트에서
# 돌고, `read -s` 와 배열이 필요하다.
#
# 이 스크립트가 하지 않는 것: 공개 URL 프로브. 그것은 밖에서 찍어야 의미가 있고
# (`scripts/verify_public_deployment.py`), 배포한 기계가 스스로 배포를 확인하면
# 라우팅·인증서·DNS 가 검사에서 통째로 빠진다. 마지막에 명령만 안내한다.

set -euo pipefail

# 이 스크립트는 3절에서 `git checkout` 을 돌려 **자기 자신을 바꾼다.** bash 는
# 스크립트를 통째로 읽어 두지 않고 실행하면서 조금씩 읽으므로, 파일이 바뀌면
# 남은 절반을 엉뚱한 바이트 위치부터 읽는다 — 운이 좋으면 문법 오류로 죽고,
# 나쁘면 줄 하나가 반쯤 잘린 채 실행된다. 그래서 사본을 만들어 거기서 돈다.
if [ -z "${FINSHIELD_REDEPLOY_COPY:-}" ]; then
    _root="$(cd "$(dirname "$0")/.." && pwd)"
    _copy="$(mktemp)"
    cat "$0" > "$_copy"
    FINSHIELD_REDEPLOY_ROOT="$_root" FINSHIELD_REDEPLOY_COPY="$_copy" \
        exec bash "$_copy" "$@"
fi

# 사본은 지금 지운다. 실행 중이어도 열린 fd 는 살아 있으므로 남은 줄은 그대로
# 읽힌다. 중간에 죽어도 /tmp 에 찌꺼기가 남지 않는다.
rm -f -- "$FINSHIELD_REDEPLOY_COPY"

# backend 이미지의 실행 사용자. 키 파일 소유자가 이 값이 아니면 컨테이너가
# 읽지 못한다. `chmod 600` 은 2026-08-25 에 서비스를 통째로 내렸다 — 소유자가
# 다르면 600 은 아무에게도 권한을 주지 않는다.
readonly BACKEND_UID=10001

# 첫 인증서 발급 예행연습 전용. 운영에 얹으면 브라우저가 믿지 않는 인증서가
# 나간다. `tests/test_public_routing.py` 가 같은 예외를 안다.
readonly STAGING_ONLY="compose.acme-staging.yaml"

# 순서가 있다. 뒤 파일이 앞을 덮으므로 알파벳순으로 만들면 안 된다 —
# `compose.yaml` 이 마지막에 와서 `compose.deploy.yaml` 이 `!reset` 으로 지운
# `build:` 가 되살아나고, e2-micro 는 그 빌드에서 OOM 으로 죽는다.
#
# 그래서 목록은 적어 두되, 저장소에 있는 것과 다르면 아래 `check_compose_list`
# 가 멈춘다. 적어 둔 목록이 조용히 짧아지는 것이 원래의 사고였다.
readonly COMPOSE_ORDER=(
    compose.yaml
    compose.https.yaml
    compose.deploy.yaml
    compose.gemini.yaml
    compose.public-data.yaml
)

readonly LEDGER="docs/31-public-deployment.md"
readonly CADDY_CONFIG="/etc/caddy/Caddyfile"

# 사용법에 찍을 이름. 사본에서 돌고 있으므로 `$0` 은 /tmp 경로다.
readonly SELF="deploy/redeploy.sh"

die() {
    printf '\n실패: %s\n' "$*" >&2
    exit 1
}

step() {
    printf '\n== %s\n' "$*"
}

# --------------------------------------------------------------------------
# 0. 어디서 도는가

usage() {
    printf '사용법: %s <태그>\n  예: %s v0.8.0\n' "$SELF" "$SELF" >&2
    exit 2
}

[ $# -eq 1 ] || usage
readonly TAG="$1"
case "$TAG" in
    -h | --help) usage ;;
    v[0-9]*) ;;
    *) die "태그는 v 로 시작해야 한다: $TAG" ;;
esac

# 저장소 최상위로 옮긴다. 홈 디렉터리에 저장소가 있다고 가정하지 않는다.
# 사본에서 돌고 있으므로 `$0` 은 못 쓴다 — 원본 위치에서 계산해 둔 값을 쓴다.
cd "$FINSHIELD_REDEPLOY_ROOT"

[ -f compose.yaml ] && [ -f deploy/Caddyfile ] || die "저장소 최상위가 아니다: $PWD"
command -v docker >/dev/null || die "docker 가 없다. VM 이 아니라 다른 기계일 수 있다"
docker compose version >/dev/null 2>&1 || die "docker compose v2 가 없다"

printf '재배포: %s\n저장소: %s\n' "$TAG" "$PWD"

# --------------------------------------------------------------------------
# 1. compose 목록이 저장소와 같은가
#
# 문법 검사가 아니다. `docker compose config` 도 `caddy validate` 도 이것을
# 못 잡는다 — 짧은 목록은 문법이 맞기 때문이다.

check_compose_list() {
    local present missing extra name
    present="$(ls compose*.yaml | grep -vx "$STAGING_ONLY" | sort)"
    missing=""
    for name in $present; do
        case " ${COMPOSE_ORDER[*]} " in
            *" $name "*) ;;
            *) missing="$missing $name" ;;
        esac
    done
    extra=""
    for name in "${COMPOSE_ORDER[@]}"; do
        [ -f "$name" ] || extra="$extra $name"
    done
    [ -z "$missing" ] || die "저장소에 있는데 이 스크립트의 목록에 없다:$missing
새 override 를 추가했다면 COMPOSE_ORDER 의 어느 자리에 넣을지 정해야 한다.
순서가 결과를 바꾸므로 자동으로 끼워 넣지 않는다."
    [ -z "$extra" ] || die "목록에 있는데 저장소에 없다:$extra"
}

step "compose override 목록"
check_compose_list
printf '%s\n' "${COMPOSE_ORDER[@]}" | sed 's/^/  /'

DC=(docker compose)
for name in "${COMPOSE_ORDER[@]}"; do DC+=(-f "$name"); done

# --------------------------------------------------------------------------
# 2. 키 파일
#
# compose 가 요구하는 것을 compose 에서 읽는다. 여기에 목록을 또 적으면 1절과
# 같은 종류로 어긋난다.

secret_files() {
    grep -h 'file: \./secrets/' "${COMPOSE_ORDER[@]}" | sed 's#.*file: \./##' | sort -u
}

create_secret() {
    local path="$1" value size
    [ -t 0 ] || die "$path 가 없는데 터미널이 아니다. 대화형으로 다시 실행한다"

    printf '  %s 가 없다. 값을 입력한다 (화면에 표시되지 않는다): ' "$path" >&2
    IFS= read -rs value < /dev/tty
    printf '\n' >&2
    [ -n "$value" ] || die "빈 값이다. $path 를 만들지 않았다"

    mkdir -p "$(dirname "$path")"
    # 파일이 만들어지는 순간부터 남에게 안 보이게 한다. 아래 chmod 까지의
    # 사이에도 0644 인 순간이 없다.
    ( umask 077; printf '%s' "$value" > "$path" )
    unset value

    # 잠그기 **전에** 확인한다. 잠근 뒤에는 이 확인에 sudo 가 필요해진다.
    size="$(stat -c %s "$path")"
    [ "$size" -gt 0 ] || die "$path 가 0바이트다"

    sudo chown "$BACKEND_UID:$BACKEND_UID" "$path"
    sudo chmod 400 "$path"
    printf '  %s: %s bytes, uid=%s, mode=400\n' "$path" "$size" "$BACKEND_UID"
}

step "키 파일"
mapfile -t SECRET_PATHS < <(secret_files)
for path in "${SECRET_PATHS[@]}"; do
    # sudo test: 이미 잠긴 파일은 현재 사용자가 읽을 수 없는 것이 정상이다.
    if sudo test -s "$path"; then
        printf '  %s: 있음 (%s bytes)\n' "$path" "$(sudo stat -c %s "$path")"
    else
        create_secret "$path"
    fi
done

# --------------------------------------------------------------------------
# 3. 작업본
#
# 이미지 밖에서 오는 파일이 있다. `deploy/Caddyfile` 은 bind mount 이고
# `compose*.yaml` 은 CLI 가 읽는다. `pull` 은 둘 다 안 바꾼다.

step "작업본"
git fetch --tags --quiet
git rev-parse -q --verify "refs/tags/$TAG^{commit}" >/dev/null \
    || die "태그를 못 찾았다: $TAG"

dirty="$(git status --porcelain)"
[ -z "$dirty" ] || die "작업본에 손댄 것이 있다. 먼저 정리한다:
$dirty"

previous="$(git rev-parse HEAD)"
printf '  %s -> %s\n' "$(git rev-parse --short HEAD)" "$TAG"

outside_images="$(git diff --name-only "$previous" "$TAG" -- deploy/ 'compose*.yaml')"
migrations="$(git diff --name-only "$previous" "$TAG" -- migrations/)"

if [ -n "$migrations" ]; then
    printf '\n  이 릴리스에는 마이그레이션이 있다:\n%s\n' "$(printf '%s\n' "$migrations" | sed 's/^/    /')"
    printf '  docs/28 P1-3 의 expand/contract 를 지킨 릴리스인지 확인했는가? [yes/no] '
    [ -t 0 ] || die "마이그레이션이 있는데 터미널이 아니다"
    read -r answer < /dev/tty
    [ "$answer" = "yes" ] || die "중단했다. 아무것도 바꾸지 않았다"
fi

git checkout --quiet "$TAG"

# 체크아웃으로 목록이 바뀌었을 수 있다. 새 작업본 기준으로 한 번 더 본다.
check_compose_list

# --------------------------------------------------------------------------
# 4. 태그
#
# `.env` 는 그 한 줄만 만진다. 같은 파일에 DB 비밀번호와 프로필 암호화 키가 있다.

step "이미지 태그"
[ -f .env ] || die ".env 가 없다. 이 VM 에 스택이 떠 있던 적이 없다"
if grep -q '^FINSHIELD_IMAGE_TAG=' .env; then
    sed -i "s/^FINSHIELD_IMAGE_TAG=.*/FINSHIELD_IMAGE_TAG=$TAG/" .env
else
    printf 'FINSHIELD_IMAGE_TAG=%s\n' "$TAG" >> .env
fi
grep '^FINSHIELD_IMAGE_TAG=' .env | sed 's/^/  /'

# --------------------------------------------------------------------------
# 5. 올린다

step "pull"
"${DC[@]}" pull

step "up -d"
"${DC[@]}" up -d

# `up -d` 는 mount 된 파일의 내용 변화로 컨테이너를 다시 만들지 않는다. compose
# 는 서비스 정의만 비교하고, 파일 내용은 그 정의에 없다.
#
# 그리고 `reload` 로도 안 된다. 2026-09-05 에 validate 와 reload 가 둘 다
# 성공했는데 `/health` 는 계속 404 였다. 단일 파일 bind mount 는 경로가 아니라
# inode 에 붙고, `git checkout` 은 파일을 제자리에서 고치지 않고 새로 써서 이름을
# 바꿔 단다. inode 가 바뀌면 컨테이너는 이름이 사라진 옛 inode 를 계속 읽고, 두
# 명령은 그 옛 내용을 상대로 정직하게 성공한다. 그날 호스트의
# `grep -c public_health` 는 2, 컨테이너 안의 같은 명령은 0 이었다.
#
# 그래서 다시 만든다. 문법은 새 컨테이너로 뜨기 전에 본다 — 방금 만들어진
# 컨테이너만 지금 파일을 본다. 인증서는 caddy-data 볼륨에 있어 잃지 않는다.
#
# 바뀌지 않은 릴리스에서도 돌린다. 변화 감지가 틀렸을 때 조용히 건너뛰는 쪽이,
# 안 바뀐 설정으로 몇 초 끊기는 쪽보다 나쁘다. 끊긴 것은 보이고, 반영 안 된 것은
# 안 보인다.
step "Caddy 설정"
if [ -n "$outside_images" ]; then
    printf '  이미지 밖에서 바뀐 파일:\n%s\n' "$(printf '%s\n' "$outside_images" | sed 's/^/    /')"
fi
"${DC[@]}" run --rm --no-deps --entrypoint caddy proxy validate --config "$CADDY_CONFIG"
"${DC[@]}" up -d --force-recreate proxy

# --------------------------------------------------------------------------
# 6. 무엇이 돌고 있는가
#
# 태그는 증거가 아니다. 같은 태그가 다른 이미지를 가리키게 만들 수 있다.
# 릴리스 대장(`docs/31` 12절)에 적힌 digest 와 실제로 받은 것을 대조한다.

step "digest"
owner="$(grep -E '^FINSHIELD_IMAGE_OWNER=' .env | cut -d= -f2- || true)"
owner="${owner:-mosejong}"

ledger="$(grep -F "| \`$TAG\` |" "$LEDGER" || true)"
[ -n "$ledger" ] || die "릴리스 대장에 $TAG 가 없다. 이미지가 만들어졌는지부터 본다"

mismatch=0
while IFS='|' read -r _ _ _ _ image digest _; do
    image="$(printf '%s' "$image" | tr -d ' `')"
    digest="$(printf '%s' "$digest" | tr -d ' `')"
    ref="ghcr.io/$owner/$image:$TAG"
    have="$(docker image inspect --format '{{join .RepoDigests "\n"}}' "$ref" 2>/dev/null || true)"
    case "$have" in
        *"$digest"*) printf '  %-20s %s  일치\n' "$image" "${digest:0:19}" ;;
        *)
            printf '  %-20s %s  **다르다**\n' "$image" "${digest:0:19}" >&2
            mismatch=1
            ;;
    esac
done <<< "$ledger"

[ "$mismatch" -eq 0 ] || die "받은 이미지가 릴리스 대장과 다르다. 배포된 것이 무엇인지 모르는 상태다"

"${DC[@]}" images

# --------------------------------------------------------------------------

cat <<'NEXT'

== 여기까지가 이 기계에서 확인할 수 있는 전부다

배포됐다는 증거는 아직 없다. 밖에서 찍어야 라우팅·인증서·DNS 가 검사에 들어간다.
개발 머신에서:

  python -m scripts.verify_public_deployment --domain finshield-ai.duckdns.org

그리고 `docs/31` 의 "v0.8.0 을 올린 뒤 찍을 것" 표를 따라간다.
통과한 뒤에 12절 배포 대장에 줄을 적는다 — 먼저 적지 않는다.
NEXT
