"""만료 데이터 정리를 사람이 직접 한 번 돌리는 도구.

주기 실행은 `run_retention_scheduler.py` 가 한다. 삭제 경로는 둘이 같은
`RetentionRunner` 를 쓴다 - 미리보기에서 본 건수와 스케줄러가 실제로 지우는
건수가 갈라지면 미리보기가 쓸모없어진다.
"""

import argparse
import json
from dataclasses import asdict

from dotenv import load_dotenv

from app.core.data_retention import (
    RetentionConfigurationError,
    build_retention_runner,
)
from app.repositories.auth_sessions import AuthSessionStorageError
from app.repositories.rate_limits import RateLimitStorageError


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preview or delete expired anonymous sessions, owned profiles, "
            "and closed rate limit windows."
        )
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Delete candidates. Without this flag the command is read-only.",
    )
    args = parser.parse_args()

    load_dotenv(override=False)

    try:
        runner = build_retention_runner()
    except RetentionConfigurationError as exc:
        # DATABASE_URL 이 없으면 in-memory 저장소를 상대로 0 건을 세고
        # 끝난다. "지울 것이 없다" 와 "아무 데도 안 봤다" 는 다른 결과인데
        # 출력만 보면 구분되지 않는다.
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2

    try:
        summary = runner.run_once(execute=args.execute)
    except (AuthSessionStorageError, RateLimitStorageError) as exc:
        # 대부분은 migration 이 안 올라간 DB 를 가리키고 있는 경우다.
        # traceback 을 뱉으면 그 사실이 묻힌다.
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1

    print(json.dumps(asdict(summary), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
