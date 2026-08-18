"""백업 루프와 healthcheck 를 실제 sh 로 실행해 확인한다.

루프가 sh 인 이유는 `deploy/backup-loop.sh` 상단에 적었다. 그래도 검증까지
포기할 이유는 없다. `pg_dump`·`pg_restore` 를 PATH 앞쪽의 가짜 실행 파일로
바꿔치우면 PostgreSQL 없이 회전 정책·heartbeat·실패 처리를 그대로 돌려볼 수
있다.
"""

import os
from pathlib import Path
import shutil
import signal
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


def _can_deny_directory_writes() -> bool:
    """디렉터리 쓰기 권한을 실제로 뺏을 수 있는 환경인가.

    Windows 에서 `chmod 0o555` 는 디렉터리에 파일을 만드는 것을 막지 못하고,
    root 로 돌리면 CAP_DAC_OVERRIDE 가 모드를 무시한다. 둘 중 하나라도
    해당되면 검사 자체가 통과할 수밖에 없으므로 skip 한다 - 이 파일이 잡으려는
    것이 바로 "실패할 수 없는 검사" 다.
    """
    if os.name == "nt":
        return False
    return os.geteuid() != 0


requires_enforced_permissions = pytest.mark.skipif(
    not _can_deny_directory_writes(),
    reason="이 환경에서는 디렉터리 쓰기 권한을 실제로 뺏을 수 없다",
)

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
        {"FINSHIELD_BACKUP_RETRY_SECONDS": "0"},
        {"FINSHIELD_BACKUP_RETRY_SECONDS": "soon"},
        # 재시도가 주기보다 길면 말이 뒤집힌다.
        {"FINSHIELD_BACKUP_INTERVAL_SECONDS": "60", "FINSHIELD_BACKUP_RETRY_SECONDS": "61"},
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
def test_a_backup_dir_that_is_not_a_directory_stops_the_loop(harness: BackupHarness) -> None:
    occupied = harness.root / "occupied"
    occupied.write_text("not a directory", encoding="utf-8")

    result = harness.run("--once", FINSHIELD_BACKUP_DIR=occupied.as_posix())

    assert result.returncode == 2
    assert '"reason":"backup_dir_not_writable"' in result.stdout


@requires_shell
@requires_enforced_permissions
def test_an_unwritable_backup_dir_stops_the_loop(harness: BackupHarness) -> None:
    """`[ -w ]` 로는 이 상황이 잡히지 않는다.

    busybox 의 test 는 euid 가 0 이면 모드를 보지도 않고 "root 는 뭐든 쓸 수
    있다" 며 참을 돌려준다. 컨테이너는 root 로 돌지만 `cap_drop: ALL` 로
    CAP_DAC_OVERRIDE 가 없어서 실제로는 못 쓴다. 그래서 사전 점검은 통과하고
    매 주기 pg_dump 만 "Permission denied" 로 실패했다 (리눅스 CI 에서 확인).

    판정은 실제로 파일을 하나 만들어 보고 내려야 한다.
    """
    harness.backups.chmod(0o555)
    try:
        result = harness.run("--once")
    finally:
        # 실패해도 tmp_path 정리가 되도록 되돌린다.
        harness.backups.chmod(0o755)

    assert result.returncode == 2
    assert '"reason":"backup_dir_not_writable"' in result.stdout
    assert harness.dumps() == []


@requires_shell
def test_the_write_probe_leaves_nothing_behind(harness: BackupHarness) -> None:
    """탐침 파일이 남으면 세대 수 계산과 회전에 끼어든다."""
    harness.run("--once")

    leftovers = sorted(path.name for path in harness.backups.iterdir())
    assert len(leftovers) == 1
    assert leftovers[0].startswith("finshield-")


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


# --- 루프 대기 정책 ---------------------------------------------------------
#
# 위의 검사들은 전부 `--once` 로 돈다. 그래서 `while` 루프의 대기 정책은 지금까지
# **한 번도 실행되지 않았다.** 2026-08-18 GCP VM 재부팅에서 그 사각지대가
# 드러났다: 실패와 성공이 같은 시간을 자고 있었고, 재부팅 경합으로 첫 dump 가
# 실패하자 다음 시도가 24시간 뒤로 밀렸다.

FLAKY_DUMP = """#!/bin/sh
target=""
for arg in "$@"; do
    case "$arg" in
        --file=*) target="${{arg#--file=}}" ;;
    esac
done
[ -n "$target" ] || exit 9
# 첫 호출만 실패한다. 재부팅 직후 db 가 아직 연결을 받지 않는 상황이다.
if [ ! -f "{marker}" ]; then
    : > "{marker}"
    echo 'pg_dump: error: connection to server at "db" failed: Connection refused' >&2
    exit 1
fi
printf '%s' 'PGDMP-fake-dump' > "$target"
exit 0
"""


def _kill_tree(process: "subprocess.Popen[bytes]") -> None:
    """셸만 죽이면 안 된다.

    `terminate()` 는 `sh` 만 끝내고 그 자식인 `sleep` 은 그대로 남는다.
    처음 이 검사를 파이프로 쓰고 `communicate()` 를 불렀더니, 살아있는
    `sleep` 이 stdout 핸들을 잡고 있어 10초 timeout 으로 죽었다. 그리고
    성공 경로에서는 `sleep 600` 이 그만큼 고아로 남는다.
    """
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True
        )
    else:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def _run_loop(
    harness: BackupHarness, dump_body: str, *, seconds: float, **overrides: str
) -> subprocess.CompletedProcess[str]:
    """진짜 루프를 띄우고 `seconds` 만큼 지켜본 뒤 끝낸다.

    출력은 파이프 대신 파일로 받는다. 끝나지 않고 죽이는 프로세스라,
    파이프를 쓰면 읽는 쪽과 죽이는 쪽이 서로를 기다리게 된다.
    """
    harness._install("pg_dump", dump_body)
    harness._install("pg_restore", FAKE_RESTORE.format(exit_code=0))
    assert SHELL is not None
    out = harness.root / "loop-stdout"
    err = harness.root / "loop-stderr"
    with out.open("wb") as stdout, err.open("wb") as stderr:
        process = subprocess.Popen(
            [SHELL, LOOP.as_posix()],
            env=harness.environment(**overrides),
            stdout=stdout,
            stderr=stderr,
            start_new_session=os.name != "nt",
        )
        try:
            time.sleep(seconds)
        finally:
            _kill_tree(process)
    return subprocess.CompletedProcess(
        process.args,
        process.returncode,
        out.read_text(encoding="utf-8"),
        err.read_text(encoding="utf-8"),
    )


@requires_shell
def test_a_failed_run_retries_without_waiting_a_whole_interval(
    harness: BackupHarness,
) -> None:
    """재부팅 경합으로 첫 dump 가 실패해도 하루를 기다리지 않는다.

    실제로 겪은 형태 그대로다. `restart: unless-stopped` 로 데몬이 컨테이너를
    되살릴 때 compose 의 `depends_on` 은 적용되지 않아서, 이 루프가 db 보다 먼저
    떠서 첫 `pg_dump` 가 "connection refused" 로 죽었다. 고치기 전에는 다음
    시도가 `INTERVAL` 뒤였다.

    주기를 600초로 두었으므로, 주기를 기다리는 구현에서는 dump 가 하나도 생기지
    않는다.
    """
    marker = (harness.root / "dump-attempted").as_posix()

    result = _run_loop(
        harness,
        FLAKY_DUMP.format(marker=marker),
        seconds=4,
        FINSHIELD_BACKUP_INTERVAL_SECONDS="600",
        FINSHIELD_BACKUP_RETRY_SECONDS="1",
    )

    assert '"status":"failed"' in result.stdout
    assert '"status":"succeeded"' in result.stdout
    assert len(harness.dumps()) == 1
    # 성공한 실행만 heartbeat 를 갱신하므로, 재시도가 healthcheck 를 되살린
    # 것까지가 이 결함의 완전한 수정이다. heartbeat 는 tmpfs 라 재시작으로
    # 사라지고, 고치기 전에는 하루 동안 unhealthy 로 남았다.
    assert harness.healthcheck(FINSHIELD_BACKUP_INTERVAL_SECONDS="600").returncode == 0


@requires_shell
def test_a_successful_run_waits_the_full_interval(harness: BackupHarness) -> None:
    """재시도 간격이 정상 주기를 대체하지 않는다.

    위 검사만 있으면 `sleep "$RETRY"` 를 무조건 자는 구현도 통과한다. 그러면
    하루 한 번이어야 할 백업이 1초마다 돌고, 세대 회전이 순식간에 전부 같은
    시각의 dump 로 덮인다.
    """
    result = _run_loop(
        harness,
        FAKE_DUMP.format(payload="PGDMP-fake-dump", exit_code=0),
        seconds=4,
        FINSHIELD_BACKUP_INTERVAL_SECONDS="600",
        FINSHIELD_BACKUP_RETRY_SECONDS="1",
    )

    assert result.stdout.count('"status":"succeeded"') == 1
    assert len(harness.dumps()) == 1
