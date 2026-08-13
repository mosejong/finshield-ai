import http.cookiejar
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = (ROOT / "backups").resolve()
BACKUP_PATH = (BACKUP_DIR / "runtime-verify.dump").resolve()
RESTORE_DATABASE = "finshield_restore_verify"
BACKEND_URL = f"http://127.0.0.1:{os.getenv('BACKEND_PORT', '18000')}"
WEB_URL = f"http://127.0.0.1:{os.getenv('WEB_PORT', '13000')}"

PROFILE = {
    "ageBand": "20_29",
    "employmentStatus": "employed",
    "householdSize": 1,
    "dependentsCount": 0,
    "monthlyNetIncome": 2_800_000,
    "monthlyFixedExpenses": 1_100_000,
    "monthlyVariableExpenses": 600_000,
    "liquidAssets": 4_000_000,
    "emergencyFundTargetMonths": 3,
    "totalDebt": 10_000_000,
    "monthlyDebtPayment": 250_000,
    "creditScoreBand": "unknown",
    "businessOwner": False,
    "goal": "emergency_cash",
    "persona": "early_career",
}


def compose(*args: str, capture: bool = False) -> str:
    completed = subprocess.run(
        ["docker", "compose", *args],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=capture,
    )
    return completed.stdout.strip() if capture else ""


def wait_for(url: str, timeout_seconds: int = 90) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(1)
    raise RuntimeError(f"service did not become healthy: {url}")


def request_json(
    opener: urllib.request.OpenerDirector,
    method: str,
    path: str,
    body: dict[str, object] | None = None,
) -> tuple[int, dict[str, object] | None]:
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        f"{WEB_URL}{path}",
        data=payload,
        method=method,
        headers={"Content-Type": "application/json"} if payload else {},
    )
    with opener.open(request, timeout=10) as response:
        content = response.read()
        parsed = json.loads(content) if content else None
        return response.status, parsed


def db_shell(command: str, *, capture: bool = False) -> str:
    return compose("exec", "-T", "db", "sh", "-ec", command, capture=capture)


def main() -> int:
    if BACKUP_PATH.parent != BACKUP_DIR:
        raise RuntimeError("backup target escaped the repository backup directory")
    if BACKUP_PATH.exists():
        raise RuntimeError("runtime verification backup already exists; refusing overwrite")
    BACKUP_DIR.mkdir(exist_ok=True)
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cookie_jar)
    )
    restore_created = False
    session_created = False
    account_deleted = False

    try:
        initial_counts = db_shell(
            'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc '
            "'SELECT (SELECT count(*) FROM users), "
            "(SELECT count(*) FROM auth_sessions), "
            "(SELECT count(*) FROM financial_profiles)'",
            capture=True,
        )
        if initial_counts != "0|0|0":
            raise RuntimeError(
                "runtime verification requires an empty database and will not delete existing data"
            )
        restore_exists = db_shell(
            'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc '
            f'"SELECT count(*) FROM pg_database WHERE datname = \'{RESTORE_DATABASE}\'"',
            capture=True,
        )
        if restore_exists != "0":
            raise RuntimeError(
                "restore verification database already exists; refusing destructive reuse"
            )

        wait_for(f"{BACKEND_URL}/health")
        wait_for(WEB_URL)
        status, _ = request_json(opener, "POST", "/api/proxy/auth/session")
        if status != 201:
            raise RuntimeError("anonymous session was not created")
        session_created = True

        status, resource = request_json(opener, "POST", "/api/proxy/profiles", PROFILE)
        if status != 201 or not resource:
            raise RuntimeError("profile was not created")
        profile_id = str(resource["profile_id"])
        request_json(opener, "GET", f"/api/proxy/profiles/{profile_id}")
        request_json(opener, "GET", f"/api/proxy/profiles/{profile_id}/metrics")

        compose("restart", "backend")
        wait_for(f"{BACKEND_URL}/health")
        status, restored_resource = request_json(
            opener, "GET", f"/api/proxy/profiles/{profile_id}"
        )
        if status != 200 or not restored_resource:
            raise RuntimeError("profile did not survive backend restart")

        db_shell(
            'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" '
            "--format=custom --file=/backups/runtime-verify.dump"
        )
        db_shell(f'createdb -U "$POSTGRES_USER" {RESTORE_DATABASE}')
        restore_created = True
        db_shell(
            f'pg_restore -U "$POSTGRES_USER" -d {RESTORE_DATABASE} '
            "/backups/runtime-verify.dump"
        )
        restored_count = db_shell(
            f'psql -U "$POSTGRES_USER" -d {RESTORE_DATABASE} -Atc '
            "'SELECT count(*) FROM financial_profiles'",
            capture=True,
        )
        if restored_count != "1":
            raise RuntimeError("restored database did not contain the encrypted profile")
        plaintext_absent = db_shell(
            f'psql -U "$POSTGRES_USER" -d {RESTORE_DATABASE} -Atc '
            '"SELECT position(\'2800000\' in encode(encrypted_profile, \'escape\')) = 0 '
            'FROM financial_profiles"',
            capture=True,
        )
        if plaintext_absent != "t":
            raise RuntimeError("backup unexpectedly exposed a known financial value")

        status, _ = request_json(opener, "DELETE", "/api/proxy/auth/account")
        if status != 204:
            raise RuntimeError("anonymous account was not deleted")
        account_deleted = True
        try:
            request_json(opener, "GET", "/api/proxy/auth/session")
        except urllib.error.HTTPError as exc:
            if exc.code != 401:
                raise
        else:
            raise RuntimeError("deleted session remained authenticated")

        counts = db_shell(
            'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc '
            "'SELECT (SELECT count(*) FROM users), "
            "(SELECT count(*) FROM auth_sessions), "
            "(SELECT count(*) FROM financial_profiles)'",
            capture=True,
        )
        if counts != "0|0|0":
            raise RuntimeError("runtime verification left personal data in PostgreSQL")

        print(
            json.dumps(
                {
                    "backend_restart_persistence": True,
                    "backup_restore": True,
                    "encrypted_backup_plaintext_absent": True,
                    "account_delete_counts": counts,
                    "web_health": True,
                    "web_proxy_e2e": True,
                },
                sort_keys=True,
            )
        )
        return 0
    finally:
        if session_created and not account_deleted:
            try:
                request_json(opener, "DELETE", "/api/proxy/auth/account")
            except (OSError, urllib.error.URLError):
                pass
        if restore_created:
            try:
                db_shell(
                    f'dropdb -U "$POSTGRES_USER" --if-exists {RESTORE_DATABASE}'
                )
            except (OSError, subprocess.SubprocessError):
                pass
        if BACKUP_PATH.exists():
            BACKUP_PATH.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
