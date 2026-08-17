#!/bin/sh
# 주기적으로 PostgreSQL dump 를 뜨고 오래된 세대를 지운다.
#
# 왜 postgres 이미지인가: pg_dump 는 서버보다 major 버전이 낮으면 거부한다.
# db 서비스와 **같은 digest** 를 쓰면 그 조건이 구조적으로 성립한다. backend
# 이미지에 postgres client 를 넣는 방법도 있지만, 그러면 인터넷에 노출된 API
# 이미지에 dump 도구가 실리고 맞춰야 할 버전이 하나 더 생긴다.
#
# 왜 sh 인가: 이 이미지에는 python 이 없다. apk 로 넣으면 해시 고정된 의존성
# 정책(P0-5)에 구멍이 난다. 그래서 루프는 sh 로 최소한만 두고, 진짜 확인이
# 필요한 "복원과 복호화가 되는가" 는 python 리허설이 맡는다
# (`scripts/rehearse_backup_restore.py`).

set -eu

BACKUP_DIR="${FINSHIELD_BACKUP_DIR:-/backups}"
INTERVAL="${FINSHIELD_BACKUP_INTERVAL_SECONDS:-86400}"
KEEP="${FINSHIELD_BACKUP_KEEP:-7}"
HEARTBEAT="${FINSHIELD_BACKUP_HEARTBEAT_PATH:-/tmp/finshield-backup-heartbeat}"
PASSWORD_FILE="${POSTGRES_PASSWORD_FILE:-/run/secrets/postgres_password}"

MIN_INTERVAL=30
MAX_INTERVAL=604800
MAX_KEEP=365

log() {
    # $1 = status, $2 = 이미 만들어진 `,"key":value` 조각 (없으면 빈 문자열).
    # 여기에 파일명 말고는 아무것도 넣지 않는다. 파일명은 시각뿐이라
    # 사용자·세션·프로필 식별자가 로그에 들어갈 경로가 없다 (adr/0004).
    printf '{"event":"backup_run","service":"finshield-backup","status":"%s","timestamp":"%s"%s}\n' \
        "$1" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$2"
}

fail_config() {
    log "misconfigured" ",\"reason\":\"$1\""
    # 설정 오류는 재시도해도 낫지 않는다. 조용히 아무것도 안 하는 것보다
    # 컨테이너가 죽어서 눈에 띄는 편이 낫다.
    exit 2
}

require_int() {
    case "$2" in
        '' | *[!0-9]*) fail_config "$1" ;;
    esac
}

require_int "interval_not_an_integer" "$INTERVAL"
require_int "keep_not_an_integer" "$KEEP"
if [ "$INTERVAL" -lt "$MIN_INTERVAL" ] || [ "$INTERVAL" -gt "$MAX_INTERVAL" ]; then
    fail_config "interval_out_of_range"
fi
if [ "$KEEP" -lt 1 ] || [ "$KEEP" -gt "$MAX_KEEP" ]; then
    fail_config "keep_out_of_range"
fi
[ -r "$PASSWORD_FILE" ] || fail_config "password_file_unreadable"
mkdir -p "$BACKUP_DIR" || fail_config "backup_dir_not_writable"

# 여기에 `[ -w "$BACKUP_DIR" ]` 를 쓰면 안 된다. busybox 의 test 는 euid 가 0
# 이면 모드를 보지도 않고 "root 는 뭐든 읽고 쓸 수 있다" 며 참을 돌려준다.
# 이 컨테이너는 root 지만 cap_drop: ALL 로 CAP_DAC_OVERRIDE 가 없어서, 호스트
# 사용자가 소유한 bind mount 에는 실제로 파일을 못 만든다. 그래서 이 검사는
# 통과해 놓고 pg_dump 만 매 주기 "Permission denied" 로 실패했다 - 절대 실패할
# 수 없는 검사가 고장을 세 시간이든 며칠이든 가려주는, 이 저장소가 반복해서
# 겪은 그 형태다.
#
# 판정은 실제로 하나 만들어 보고 내린다. pg_dump 가 할 일과 같은 동작이다.
probe="$BACKUP_DIR/.finshield-write-probe.$$"
rm -f -- "$probe"
touch "$probe" 2>/dev/null || fail_config "backup_dir_not_writable"
rm -f -- "$probe"

# 비밀번호를 환경변수(PGPASSWORD)로 넘기지 않는다. 환경변수는 `docker inspect`
# 와 자식 프로세스 전체에 그대로 노출된다. pgpass 파일은 tmpfs 에만 두고
# 소유자만 읽게 만든다. pgpass 형식에서 `:` 와 `\` 는 escape 가 필요하다.
#
# 경로는 compose 의 PGPASSFILE 로 받는다. `docker compose exec` 는 이 루프의
# 환경을 물려받지 않으므로, 여기서 export 만 하면 복원 리허설이 쓰는 psql 은
# 비밀번호를 찾지 못한다.
#
# 데이터베이스 칸은 `*` 다. pgpass 는 데이터베이스별로 매칭되는데, 복원
# 리허설은 `postgres`(임시 DB 존재 확인)와 `finshield_rehearsal`(복원 대상)
# 에도 접속한다. 여기를 `finshield` 로 고정하면 그 두 접속만 비밀번호를 못
# 찾아 실패한다. host·port·user 는 그대로 고정해 둔다.
PGPASSFILE="${PGPASSFILE:-/tmp/finshield-pgpass}"
export PGPASSFILE
(
    umask 077
    printf '%s:%s:*:%s:%s\n' \
        "${PGHOST:-db}" \
        "${PGPORT:-5432}" \
        "${PGUSER:-finshield_app}" \
        "$(sed 's/[\\:]/\\&/g' "$PASSWORD_FILE")" \
        > "$PGPASSFILE"
)

mark_success() {
    # healthcheck 가 쓰는 도중에 읽으면 잘린 내용을 보고 멀쩡한 백업을 실패로
    # 판정한다. 임시 파일에 쓰고 원자적으로 바꿔치운다. epoch 초로 적는 이유는
    # sh 에서 ISO 문자열을 신뢰성 있게 파싱할 방법이 없기 때문이다.
    printf '%s\n' "$(date -u +%s)" > "$HEARTBEAT.tmp"
    mv -- "$HEARTBEAT.tmp" "$HEARTBEAT"
}

rotate() {
    # 새 dump 가 성공한 **뒤에만** 부른다. 먼저 지우면 새 백업이 실패했을 때
    # 멀쩡한 세대를 하나 잃은 채로 끝난다.
    #
    # `.tmp` 는 세지 않는다. 중단된 쓰기가 세대 하나로 잡히면 실제 보관 수가
    # 조용히 줄어든다. 파일명은 이 스크립트가 만들고 시각뿐이라 공백이 없다.
    removed=0
    for stale in $(ls -1t "$BACKUP_DIR"/finshield-*.dump 2>/dev/null | tail -n +"$((KEEP + 1))"); do
        rm -f -- "$stale"
        removed=$((removed + 1))
    done
    printf '%s' "$removed"
}

run_once() {
    started="$(date -u +%s)"
    target="$BACKUP_DIR/finshield-$(date -u +%Y%m%dT%H%M%SZ).dump"
    temporary="$target.tmp"
    rm -f -- "$temporary"

    if ! pg_dump --format=custom --file="$temporary"; then
        rm -f -- "$temporary"
        log "failed" ',"stage":"dump"'
        return 1
    fi

    # pg_dump 가 0 으로 끝나도 파일이 온전하다는 보장은 아니다. TOC 를 읽어
    # 실제로 복원 가능한 형식인지 확인한다. 여기서 안 걸러지면 복원해야 하는
    # 날에야 알게 된다.
    if ! pg_restore --list "$temporary" > /dev/null; then
        rm -f -- "$temporary"
        log "failed" ',"stage":"verify"'
        return 1
    fi

    # 원자적 교체. 리허설이나 복사 스크립트가 쓰다 만 파일을 집지 않는다.
    mv -- "$temporary" "$target"

    bytes="$(wc -c < "$target" | tr -d ' ')"
    pruned="$(rotate)"
    kept="$(ls -1 "$BACKUP_DIR"/finshield-*.dump 2>/dev/null | wc -l | tr -d ' ')"

    mark_success
    log "succeeded" ",\"bytes\":$bytes,\"generations\":$kept,\"pruned\":$pruned,\"duration_s\":$(( $(date -u +%s) - started ))"
    return 0
}

if [ "${1:-}" = "--once" ]; then
    run_once
    exit $?
fi

# 첫 백업을 미루지 않는다. 배포 직후 한 주기를 통째로 기다리면 그동안은
# 백업이 하나도 없는 상태로 서비스가 떠 있는 것이다.
while true; do
    # 실패해도 루프를 세우지 않는다. 다음 주기에 다시 시도하고, 그 사이
    # heartbeat 가 낡으면 healthcheck 가 대신 소리를 낸다.
    run_once || true
    sleep "$INTERVAL"
done
