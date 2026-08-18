#!/bin/sh
# 마지막으로 "성공한" 백업 시각을 본다.
#
# 프로세스가 살아 있는지는 보지 않는다. 매 주기 실패하는 루프도 살아 있으므로
# 살아 있음은 백업이 되고 있다는 증거가 못 된다. 성공한 실행만 heartbeat 를
# 갱신하고, 여기서는 그 시각의 나이만 본다.

set -eu

HEARTBEAT="${FINSHIELD_BACKUP_HEARTBEAT_PATH:-/tmp/finshield-backup-heartbeat}"
INTERVAL="${FINSHIELD_BACKUP_INTERVAL_SECONDS:-86400}"

case "$INTERVAL" in
    '' | *[!0-9]*) exit 1 ;;
esac

# 한 주기를 놓친 것은 DB 순간 장애일 수 있지만 두 주기 연속은 실제 고장이다.
# 여유 60초는 dump 자체에 걸리는 시간을 덮는다.
MAX_AGE=$((INTERVAL * 2 + 60))

recorded="$(cat "$HEARTBEAT" 2>/dev/null || true)"
recorded="$(printf '%s' "$recorded" | tr -d '[:space:]')"
case "$recorded" in
    # 기록이 없으면 아직 한 번도 성공하지 못한 것이다. 기동 직후의 공백은
    # healthcheck 의 start_period 가 덮는다.
    '' | *[!0-9]*) exit 1 ;;
esac

age=$(($(date -u +%s) - recorded))
[ "$age" -ge 0 ] || exit 1
[ "$age" -le "$MAX_AGE" ] || exit 1
