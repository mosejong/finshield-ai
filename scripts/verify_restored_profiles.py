"""복원된 DB 의 금융 프로필이 실제로 복호화되는지 확인한다.

backend 이미지 안에서 돈다. postgres client 로는 이 확인을 할 수 없다 -
암호화가 애플리케이션 레벨이라 키와 봉투 형식을 아는 쪽만 열 수 있다.

    python -m scripts.verify_restored_profiles

읽을 DB 는 환경변수로 준다. 복원 리허설은 임시 DB 이름을 넘겨 부른다:

    docker compose run --rm -e DATABASE_NAME=finshield_restore_verify \
        backend python -m scripts.verify_restored_profiles

출력에는 건수와 key id 만 담는다. key id 는 이미 행에 평문으로 저장된 값이고,
복호화된 프로필은 어디에도 남기지 않는다.
"""

import json
from dataclasses import asdict

from dotenv import load_dotenv
from sqlalchemy.exc import SQLAlchemyError

from app.core.backup_verification import (
    RestoreVerificationConfigurationError,
    verify_from_environment,
)


def main() -> int:
    load_dotenv(override=False)

    try:
        verification, database = verify_from_environment()
    except RestoreVerificationConfigurationError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    except SQLAlchemyError as exc:
        # 대개 복원이 끝나지 않았거나 임시 DB 이름을 잘못 준 경우다.
        # 예외 메시지에는 문장과 바인딩 값이 붙으므로 종류만 남긴다.
        print(json.dumps({"error": type(exc).__name__}, ensure_ascii=False))
        return 1

    print(
        json.dumps(
            {
                "database": database,
                "recoverable": verification.recoverable,
                **asdict(verification),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    # 행이 0 건이거나 하나라도 못 열면 실패다. "복원됐다" 는 합격 기준이
    # 아니다 - 열리는 것까지가 복구다.
    return 0 if verification.recoverable else 1


if __name__ == "__main__":
    raise SystemExit(main())
