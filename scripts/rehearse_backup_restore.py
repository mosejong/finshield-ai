"""백업 하나를 골라 실제로 복원하고, 프로필이 열리는지까지 확인한다.

"백업이 생성된다" 는 합격 기준이 아니다. 프로필은 애플리케이션 레벨에서
암호화돼 있어서 **DB 만 돌아오고 키가 없으면 남는 것은 열 수 없는 바이트열**
이다. 그래서 이 리허설은 두 가지를 한 번에 확인한다.

    1. dump 파일만으로 스키마와 행이 복원되는가        (postgres client)
    2. 그 행을 지금 가진 키로 복호화할 수 있는가        (backend 이미지)

두 번째가 이 스크립트의 존재 이유다. 첫 번째만 하는 검사는 키를 잃어버린
백업도 통과시킨다.

    python scripts/rehearse_backup_restore.py
    python scripts/rehearse_backup_restore.py --dump finshield-20260815T031500Z.dump

한계: 복원 대상은 같은 PostgreSQL 인스턴스 안의 임시 데이터베이스다. 호스트가
통째로 사라진 상황에서의 복구는 여기서 확인되지 않는다. 그 훈련은 백업 파일을
호스트 밖으로 내보내는 절차와 함께 별도로 해야 한다 (`docs/29`).
"""

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LIVE_DATABASE = os.getenv("POSTGRES_DB", "finshield")
RESTORE_DATABASE = "finshield_rehearsal"
BACKUP_DIR = "/backups"
DUMP_NAME_PATTERN = re.compile(r"^finshield-(\d{8}T\d{6}Z)\.dump$")

BACKUP_INTERVAL = int(os.getenv("FINSHIELD_BACKUP_INTERVAL_SECONDS", "86400"))


def compose(*args: str, capture: bool = False, check: bool = True) -> str:
    completed = subprocess.run(
        ["docker", "compose", *args],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=capture,
    )
    if check and completed.returncode != 0:
        # 종료 코드만 던지면 "psql 이 2 로 끝났다" 까지만 남는다. 접속 실패인지
        # 권한 문제인지 구분하려면 stderr 가 있어야 한다.
        detail = (completed.stderr or "").strip() if capture else ""
        raise RuntimeError(
            f"docker compose {' '.join(args[:3])} failed "
            f"(exit {completed.returncode}){f': {detail}' if detail else ''}"
        )
    return completed.stdout.strip() if capture else ""


def backup_shell(command: str, *, capture: bool = False) -> str:
    return compose("exec", "-T", "backup", "sh", "-ec", command, capture=capture)


def latest_dump() -> str:
    listing = backup_shell(
        f"ls -1t {BACKUP_DIR}/finshield-*.dump 2>/dev/null || true", capture=True
    )
    names = [Path(line).name for line in listing.splitlines() if line.strip()]
    if not names:
        raise RuntimeError(
            "no backup to rehearse; the backup service has not produced a dump yet"
        )
    return names[0]


def dump_age_seconds(name: str) -> float:
    matched = DUMP_NAME_PATTERN.match(name)
    if matched is None:
        raise RuntimeError("backup file name is not in the expected format")
    taken_at = datetime.strptime(matched.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    return (datetime.now(UTC) - taken_at).total_seconds()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Restore a backup into a scratch database and decrypt its profiles."
    )
    parser.add_argument(
        "--dump",
        help="Backup file name inside the backup container. Defaults to the newest.",
    )
    parser.add_argument(
        "--max-age-seconds",
        type=int,
        default=BACKUP_INTERVAL * 2 + 60,
        help="Fail when the chosen backup is older than this.",
    )
    args = parser.parse_args()

    if RESTORE_DATABASE == LIVE_DATABASE:
        raise RuntimeError("rehearsal database name collides with the live database")

    name = args.dump or latest_dump()
    if DUMP_NAME_PATTERN.match(name) is None:
        # 이름을 그대로 셸에 넘기므로 형식을 먼저 고정한다.
        raise RuntimeError("backup file name is not in the expected format")
    age = dump_age_seconds(name)
    if age > args.max_age_seconds:
        # 오래된 백업으로 리허설에 성공해도 그것은 "복구 가능" 이 아니다.
        # 최신 백업이 멈춰 있다는 사실 자체가 발견 사항이다.
        raise RuntimeError(
            f"newest backup is {int(age)}s old, older than the allowed "
            f"{args.max_age_seconds}s"
        )

    existing = backup_shell(
        "psql -d postgres -Atc \"SELECT count(*) FROM pg_database "
        f"WHERE datname = '{RESTORE_DATABASE}'\"",
        capture=True,
    )
    if existing != "0":
        raise RuntimeError("rehearsal database already exists; refusing destructive reuse")

    created = False
    try:
        backup_shell(f"createdb {RESTORE_DATABASE}")
        created = True
        # --exit-on-error: 기본값은 오류를 세면서 계속 진행하고 0 으로 끝난다.
        # 그러면 절반만 복원된 DB 를 성공으로 읽는다.
        backup_shell(
            f"pg_restore --dbname={RESTORE_DATABASE} --exit-on-error "
            f"{BACKUP_DIR}/{name}"
        )

        # 여기부터는 backend 이미지가 필요하다. 키와 봉투 형식을 아는 쪽만
        # 행을 열 수 있다. --no-deps: 이미 떠 있는 서비스를 건드리지 않는다.
        # check=False: 복호화에 실패하면 종료 코드가 1 이다. 그건 이 스크립트가
        # 보고해야 할 결과이지 예외로 삼킬 사건이 아니다.
        decrypted = compose(
            "run",
            "--rm",
            "--no-deps",
            "-T",
            "-e",
            f"DATABASE_NAME={RESTORE_DATABASE}",
            "backend",
            "python",
            "-m",
            "scripts.verify_restored_profiles",
            capture=True,
            check=False,
        )
    finally:
        if created:
            try:
                backup_shell(f"dropdb --if-exists {RESTORE_DATABASE}")
            except (OSError, subprocess.SubprocessError):
                pass

    report = json.loads(decrypted.splitlines()[-1])
    if not report.get("recoverable"):
        print(json.dumps({"rehearsal": "failed", "dump": name, **report}, sort_keys=True))
        return 1

    print(
        json.dumps(
            {
                "rehearsal": "succeeded",
                "dump": name,
                "dump_age_seconds": int(age),
                **report,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
