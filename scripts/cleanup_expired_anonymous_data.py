import argparse
import json

from dotenv import load_dotenv

from app.core.auth_sessions import build_auth_session_service


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preview or delete expired anonymous sessions and owned profiles."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Delete candidates. Without this flag the command is read-only.",
    )
    args = parser.parse_args()

    load_dotenv(override=False)
    summary = build_auth_session_service().cleanup_expired(execute=args.execute)
    print(
        json.dumps(
            {
                "executed": summary.executed,
                "expired_sessions": summary.expired_sessions,
                "anonymous_users": summary.anonymous_users,
                "financial_profiles": summary.financial_profiles,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
