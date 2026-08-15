"""만료 데이터 정리를 주기적으로 실행하는 상주 프로세스.

`cleanup_expired_anonymous_data.py` 는 사람이 부르는 미리보기 도구이고,
이쪽은 아무도 부르지 않아도 도는 쪽이다. 같은 삭제 경로(`RetentionRunner`)를
쓴다.

    python -m scripts.run_retention_scheduler                    # 상주 실행
    python -m scripts.run_retention_scheduler --once             # 1회 실행
    python -m scripts.run_retention_scheduler --check-heartbeat  # 상태 점검
"""

import argparse
import json
from collections.abc import Sequence

from dotenv import load_dotenv

from app.core.data_retention import (
    RetentionConfigurationError,
    build_heartbeat,
    build_retention_scheduler,
    heartbeat_max_age_seconds,
    read_interval_seconds,
)
from app.services.data_retention import configure_retention_logger


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Delete expired anonymous data on a schedule."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--once",
        action="store_true",
        help="Run one cleanup and exit. Non-zero exit if it failed.",
    )
    group.add_argument(
        "--check-heartbeat",
        action="store_true",
        help=(
            "Exit non-zero when the last successful cleanup is too old. "
            "Used as the container healthcheck."
        ),
    )
    args = parser.parse_args(argv)

    load_dotenv(override=False)

    if args.check_heartbeat:
        return _check_heartbeat()

    configure_retention_logger()
    try:
        scheduler = build_retention_scheduler()
    except RetentionConfigurationError as exc:
        # 설정 오류는 재시도해도 낫지 않는다. 조용히 아무것도 안 하는 것보다
        # 컨테이너가 죽어서 눈에 띄는 편이 낫다.
        print(json.dumps({"event": "retention_config_error", "detail": str(exc)}))
        return 2

    if args.once:
        return 0 if scheduler.run_cycle() else 1

    scheduler.run_forever()
    return 0


def _check_heartbeat() -> int:
    """정리가 실제로 돌고 있는지만 본다.

    DB 에 붙지 않는다. healthcheck 가 DB 를 열면, DB 가 잠깐 흔들릴 때
    정리 컨테이너까지 같이 unhealthy 로 떨어져서 원인이 흐려진다.
    """
    try:
        max_age = heartbeat_max_age_seconds(read_interval_seconds())
    except RetentionConfigurationError as exc:
        print(json.dumps({"event": "retention_config_error", "detail": str(exc)}))
        return 2
    heartbeat = build_heartbeat()
    if heartbeat.is_fresh(max_age_seconds=max_age):
        return 0
    elapsed = heartbeat.seconds_since_success()
    print(
        json.dumps(
            {
                "event": "retention_heartbeat_stale",
                "max_age_seconds": max_age,
                "seconds_since_success": elapsed,
            },
            sort_keys=True,
        )
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
