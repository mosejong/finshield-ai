"""백업 루프와 healthcheck 를 실제 sh 로 실행해 확인한다.

루프가 sh 인 이유는 `deploy/backup-loop.sh` 상단에 적었다. 그래도 검증까지
포기할 이유는 없다. `pg_dump`·`pg_restore` 를 PATH 앞쪽의 가짜 실행 파일로
바꿔치우면 PostgreSQL 없이 회전 정책·heartbeat·실패 처리를 그대로 돌려볼 수
있다.
"""

import os
from pathlib import Path
import shutil
import subprocess
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
LOOP = ROOT / "deploy" / "backup-loop.sh"
HEALTHCHECK = ROOT / "deploy" / "backup-healthcheck.sh"

def _locate_shell() -> str | None:
    """POSIX sh 를 찾는다.

    CI(리눅스)에서는 PATH 에 있다. Windows 개발 환경에서는 Git 이 함께 깔아준
    sh 가 PATH 밖(`Git/usr/bin`)에 있어 `which` 로는 안 잡힌다. 그대로 두면
    로컬에서 이 파일 전체가 조용히 skip 되고, 셸 스크립트는 CI 에서 처음
    실행된다.
    """
    found = shutil.which("sh")
    if found:
        return found
    git = shutil.which("git")
    if git:
        candidate = Path(git).resolve().parents[1] / "usr" / "bin" / "sh.exe"
        if candidate.exists():
            return str(candidate)
    return None


SHELL = _locate_shell()
requires_shell = pytest.mark.skipif(SHELL is None, reason="POSIX sh is unavailable")

FAKE_DUMP = """#!/bin/sh
target=""
for arg in "$@"; do
    case "$arg" in
        --file=*) target="${{arg#--file=}}" ;;
    esac
done
[ -n "$target" ] || exit 9
printf '%s' '{payload}' > "$target"
exit {exit_code}
"""

FAKE_RESTORE = """#!/bin/sh
exit {exit_code}
"""


class BackupHarness:
    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path
        self.backups = tmp_path / "backups"
        self.backups.mkdir()
        self.heartbeat = tmp_path / "heartbeat"
        self.password_file = tmp_path / "password"
        self.password_file.write_text("s3cret-value\n", encoding="utf-8")
        self.bin = tmp_path / "bin"
        self.bin.mkdir()

    def _install(self, name: str, body: str) -> None:
        path = self.bin / name
        path.write_text(body, encoding="utf-8", newline="\n")
        path.chmod(0o755)

    def environment(self, **overrides: str) -> dict[str, str]:
        # 가짜 pg_dump 가 맨 앞, 그다음 셸이 사는 디렉터리. 후자는 Windows 에서
        # 필요하다 - date·sed·tr 같은 POSIX 유틸이 sh 옆에 같이 있고 PATH 에는
        # 없어서, 빼면 스크립트가 로직이 아니라 "command not found" 로 죽는다.
        assert SHELL is not None
        search_path = os.pathsep.join(
            [self.bin.as_posix(), Path(SHELL).parent.as_posix(), os.environ.get("PATH", "")]
        )
        env = {
            "PATH": search_path,
            "FINSHIELD_BACKUP_DIR": self.backups.as_posix(),
            "FINSHIELD_BACKUP_HEARTBEAT_PATH": self.heartbeat.as_posix(),
            "FINSHIELD_BACKUP_INTERVAL_SECONDS": "3600",
            "FINSHIELD_BACKUP_KEEP": "3",
            "POSTGRES_PASSWORD_FILE": self.password_file.as_posix(),
            "PGPASSFILE": (self.root / "pgpass").as_posix(),
            "PGHOST": "db",
            "PGPORT": "5432",
            "PGDATABASE": "finshield",
            "PGUSER": "finshield_app",
        }
        env.update(overrides)
        return env

    def run(
        self,
        *args: str,
        dump_exit: int = 0,
        restore_exit: int = 0,
        payload: str = "PGDMP-fake-dump",
        **overrides: str,
    ) -> subprocess.CompletedProcess[str]:
        self._install("pg_dump", FAKE_DUMP.format(payload=payload, exit_code=dump_exit))
        self._install("pg_restore", FAKE_RESTORE.format(exit_code=restore_exit))
        assert SHELL is not None
        return subprocess.run(
            [SHELL, LOOP.as_posix(), *args],
            env=self.environment(**overrides),
            capture_output=True,
            text=True,
            timeout=60,
        )

    def healthcheck(self, **overrides: str) -> subprocess.CompletedProcess[str]:
        assert SHELL is not None
        return subprocess.run(
            [SHELL, HEALTHCHECK.as_posix()],
            env=self.environment(**overrides),
            capture_output=True,
            text=True,
            timeout=60,
        )

    def dumps(self) -> list[str]:
        return sorted(path.name for path in self.backups.glob("finshield-*.dump"))

    def seed_dump(self, name: str, *, age_seconds: int) -> Path:
        path = self.backups / name
        path.write_text("old", encoding="utf-8")
        stamp = time.time() - age_seconds
        os.utime(path, (stamp, stamp))
        return path


@pytest.fixture
def harness(tmp_path: Path) -> BackupHarness:
    return BackupHarness(tmp_path)


@requires_shell
def test_a_single_run_writes_one_dump(harness: BackupHarness) -> None:
    result = harness.run("--once")

    assert result.returncode == 0, result.stderr
    assert len(harness.dumps()) == 1
    assert '"status":"succeeded"' in result.stdout


@requires_shell
def test_the_dump_is_renamed_into_place(harness: BackupHarness) -> None:
    """쓰다 만 파일이 백업으로 보이면 안 된다.

    복원 리허설은 최신 파일을 집는다. 쓰는 중인 파일을 그대로 노출하면
    반쯤 쓰인 dump 를 복원 대상으로 고를 수 있다.
    """
    harness.run("--once")

    assert not list(harness.backups.glob("*.tmp"))


@requires_shell
def test_only_the_newest_generations_survive(harness: BackupHarness) -> None:
    for index, age in enumerate((400, 300, 200, 100)):
        harness.seed_dump(f"finshield-2026081{index}T000000Z.dump", age_seconds=age)

    harness.run("--once", FINSHIELD_BACKUP_KEEP="3")

    remaining = harness.dumps()
    assert len(remaining) == 3
    # 가장 오래된 것부터 사라진다. 새로 뜬 것은 반드시 남는다.
    assert "finshield-20260810T000000Z.dump" not in remaining


@requires_shell
def test_partial_writes_do_not_count_as_a_generation(harness: BackupHarness) -> None:
    """중단된 쓰기가 세대로 잡히면 실제 보관 수가 조용히 줄어든다."""
    harness.seed_dump("finshield-20260810T000000Z.dump", age_seconds=300)
    harness.seed_dump("finshield-20260811T000000Z.dump", age_seconds=200)
    stale_partial = harness.backups / "finshield-20260812T000000Z.dump.tmp"
    stale_partial.write_text("half", encoding="utf-8")

    harness.run("--once", FINSHIELD_BACKUP_KEEP="3")

    assert len(harness.dumps()) == 3


@requires_shell
def test_a_failed_dump_keeps_the_existing_generations(harness: BackupHarness) -> None:
    """회전을 먼저 돌리면 실패한 날 멀쩡한 백업을 하나 잃는다."""
    for index, age in enumerate((400, 300, 200)):
        harness.seed_dump(f"finshield-2026081{index}T000000Z.dump", age_seconds=age)

    result = harness.run("--once", dump_exit=1, FINSHIELD_BACKUP_KEEP="3")

    assert result.returncode == 1
    assert len(harness.dumps()) == 3
    assert not list(harness.backups.glob("*.tmp"))
    assert '"status":"failed"' in result.stdout
    assert '"stage":"dump"' in result.stdout


@requires_shell
def test_an_unreadable_dump_is_discarded(harness: BackupHarness) -> None:
    """pg_dump 가 0 으로 끝나도 파일이 온전하다는 보장은 아니다.

    TOC 를 읽어보지 않으면 복원해야 하는 날에야 알게 된다.
    """
    result = harness.run("--once", restore_exit=1)

    assert result.returncode == 1
    assert harness.dumps() == []
    assert '"stage":"verify"' in result.stdout


@requires_shell
def test_only_a_successful_run_marks_the_heartbeat(harness: BackupHarness) -> None:
    failed = harness.run("--once", dump_exit=1)
    assert failed.returncode == 1
    assert not harness.heartbeat.exists()

    succeeded = harness.run("--once")
    assert succeeded.returncode == 0
    assert harness.heartbeat.read_text(encoding="utf-8").strip().isdigit()


@requires_shell
def test_a_failure_leaves_the_previous_success_time_alone(harness: BackupHarness) -> None:
    harness.run("--once")
    recorded = harness.heartbeat.read_text(encoding="utf-8")

    harness.run("--once", dump_exit=1)

    assert harness.heartbeat.read_text(encoding="utf-8") == recorded


@requires_shell
def test_logs_carry_no_credentials(harness: BackupHarness) -> None:
    result = harness.run("--once")

    assert "s3cret-value" not in result.stdout
    assert "s3cret-value" not in result.stderr


@requires_shell
@pytest.mark.parametrize(
    "overrides",
    [
        {"FINSHIELD_BACKUP_INTERVAL_SECONDS": "5"},
        {"FINSHIELD_BACKUP_INTERVAL_SECONDS": "hourly"},
        {"FINSHIELD_BACKUP_KEEP": "0"},
        {"FINSHIELD_BACKUP_KEEP": "many"},
    ],
)
def test_a_misconfigured_loop_exits_instead_of_idling(
    harness: BackupHarness, overrides: dict[str, str]
) -> None:
    """조용히 아무것도 안 하는 것보다 컨테이너가 죽어서 눈에 띄는 편이 낫다."""
    result = harness.run("--once", **overrides)

    assert result.returncode == 2
    assert '"status":"misconfigured"' in result.stdout


@requires_shell
def test_an_unreadable_password_file_stops_the_loop(harness: BackupHarness) -> None:
    result = harness.run(
        "--once", POSTGRES_PASSWORD_FILE=(harness.root / "absent").as_posix()
    )

    assert result.returncode == 2
    assert '"reason":"password_file_unreadable"' in result.stdout


@requires_shell
def test_the_password_never_reaches_the_environment(harness: BackupHarness) -> None:
    """PGPASSWORD 로 넘기면 `docker inspect` 와 자식 프로세스에 그대로 보인다."""
    harness.run("--once")

    passfile = harness.root / "pgpass"
    assert passfile.exists()
    assert "s3cret-value" in passfile.read_text(encoding="utf-8")


@requires_shell
def test_the_credentials_cover_every_database_on_the_server(harness: BackupHarness) -> None:
    """pgpass 는 데이터베이스별로 매칭된다.

    복원 리허설은 `postgres` 와 임시 복원 DB 에도 접속한다. 데이터베이스 칸을
    `finshield` 로 고정하면 그 두 접속만 조용히 비밀번호를 못 찾는다 - 백업은
    잘 뜨는데 리허설만 실패하는, 원인을 짚기 어려운 형태로 나타난다.
    """
    harness.run("--once")

    host, port, database, user, _ = (
        (harness.root / "pgpass").read_text(encoding="utf-8").strip().split(":")
    )

    assert database == "*"
    # 나머지는 넓히지 않는다.
    assert (host, port, user) == ("db", "5432", "finshield_app")


@requires_shell
def test_health_is_refused_before_the_first_success(harness: BackupHarness) -> None:
    assert harness.healthcheck().returncode == 1


@requires_shell
def test_health_follows_the_last_success(harness: BackupHarness) -> None:
    harness.run("--once")
    assert harness.healthcheck().returncode == 0


@requires_shell
def test_two_missed_intervals_are_unhealthy(harness: BackupHarness) -> None:
    """한 주기를 놓친 것은 순간 장애일 수 있지만 두 주기 연속은 고장이다."""
    harness.heartbeat.write_text(str(int(time.time()) - 400), encoding="utf-8")

    fresh = harness.healthcheck(FINSHIELD_BACKUP_INTERVAL_SECONDS="3600")
    stale = harness.healthcheck(FINSHIELD_BACKUP_INTERVAL_SECONDS="60")

    assert fresh.returncode == 0
    assert stale.returncode == 1


@requires_shell
def test_a_damaged_heartbeat_is_not_read_as_healthy(harness: BackupHarness) -> None:
    harness.heartbeat.write_text("not-a-timestamp", encoding="utf-8")

    assert harness.healthcheck().returncode == 1
