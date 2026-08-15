import argparse
import json

from dotenv import load_dotenv

from app.core.auth_sessions import build_auth_session_service
from app.core.rate_limit import build_rate_limit_service


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

    # 개인정보 보존기간이 먼저다. 뒤이은 정리가 실패해도 이건 이미 끝나 있어야
    # 한다. rate limit 카운터는 식별자를 담지 않으므로 순서상 뒤에 둔다.
    sessions = build_auth_session_service().cleanup_expired(execute=args.execute)
    # 닫힌 window 행은 다시 조회되지 않는다. 지우지 않으면 요청 수만큼
    # 무한히 쌓이기만 한다.
    counters = build_rate_limit_service().cleanup_expired(execute=args.execute)

    print(
        json.dumps(
            {
                "executed": sessions.executed,
                "expired_sessions": sessions.expired_sessions,
                "anonymous_users": sessions.anonymous_users,
                "financial_profiles": sessions.financial_profiles,
                "rate_limit_counters": counters.counters,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
