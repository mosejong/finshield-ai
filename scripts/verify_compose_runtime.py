import http.cookiejar
import json
import os
from pathlib import Path
import re
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

# analyze 정책은 30회/분이다 (`app/services/rate_limits.py`).
ANALYZE_LIMIT = 30
ANALYZE_PAYLOAD = {"text": "계좌를 빌려주시면 수수료를 드립니다", "state": "received_only"}
# HMAC-SHA256 hex. IP 나 세션 값이 그대로 저장되면 이 형태가 아니다.
BUCKET_KEY_PATTERN = re.compile(r"^[0-9a-f]{64}$")

# 정리가 "돌 수 있다" 가 아니라 "스케줄에 따라 실제로 지웠다" 를 확인하려면
# 한 주기를 기다려야 한다. 기본 3600초로는 검증이 끝나지 않는다.
RETENTION_INTERVAL = int(os.getenv("FINSHIELD_RETENTION_INTERVAL_SECONDS", "3600"))
MAX_VERIFIABLE_RETENTION_INTERVAL = 120

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
        headers={
            **({"Content-Type": "application/json"} if payload else {}),
            **({"Origin": WEB_URL} if method not in {"GET", "HEAD"} else {}),
        },
    )
    with opener.open(request, timeout=10) as response:
        content = response.read()
        parsed = json.loads(content) if content else None
        return response.status, parsed


def db_shell(command: str, *, capture: bool = False) -> str:
    return compose("exec", "-T", "db", "sh", "-ec", command, capture=capture)


def backend_post(path: str, payload: bytes) -> tuple[int, str | None]:
    """web 을 거치지 않고 backend 포트로 직접 보낸다.

    이 경로의 client IP 는 docker gateway 라서, web 컨테이너를 통해 오는
    프록시 호출과 다른 bucket 에 들어간다. 아래 프로필·세션 검증 흐름의
    한도를 소모하지 않는다.
    """
    request = urllib.request.Request(
        f"{BACKEND_URL}{path}",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
            return response.status, response.headers.get("Retry-After")
    except urllib.error.HTTPError as exc:
        exc.read()
        return exc.code, exc.headers.get("Retry-After")


def verify_request_size_limit() -> None:
    """스키마 검증 이전에 잘리는지 본다.

    `text` 상한은 10000자다. 400 이 돌아오면 본문을 끝까지 읽은 뒤 스키마가
    거부했다는 뜻이고, 그건 이 방어가 동작하지 않았다는 뜻이다.
    """
    oversized = json.dumps({"text": "가" * 200_000}).encode("utf-8")
    status, _ = backend_post("/api/v1/analyze", oversized)
    if status != 413:
        raise RuntimeError(
            f"oversized request body was not rejected at the HTTP boundary: {status}"
        )


def verify_rate_limit() -> dict[str, object]:
    payload = json.dumps(ANALYZE_PAYLOAD).encode("utf-8")
    limited_at = None
    retry_after = None
    for attempt in range(1, ANALYZE_LIMIT + 11):
        status, header = backend_post("/api/v1/analyze", payload)
        if status == 200:
            continue
        if status != 429:
            raise RuntimeError(f"unexpected status while probing rate limit: {status}")
        limited_at = attempt
        retry_after = header
        break
    if limited_at is None:
        raise RuntimeError(
            "rate limit never engaged; FINSHIELD_RATE_LIMIT_ENABLED must be set for this run"
        )
    if limited_at <= ANALYZE_LIMIT:
        raise RuntimeError(f"rate limit engaged too early at attempt {limited_at}")
    if not retry_after or not retry_after.isdigit() or int(retry_after) <= 0:
        raise RuntimeError("429 response did not carry a usable Retry-After")

    # 카운터가 프로세스 메모리에 있으면 backend 재시작 한 번으로 한도가
    # 초기화된다. 워커가 여러 개면 아예 워커 수만큼 헐거워진다. 행이
    # PostgreSQL 에 있다는 것이 그 두 가지가 아니라는 증거다.
    row = db_shell(
        'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc '
        "'SELECT bucket_key, hit_count FROM rate_limit_counters "
        "ORDER BY hit_count DESC LIMIT 1'",
        capture=True,
    )
    if not row:
        raise RuntimeError("rate limit counters were not stored in PostgreSQL")
    bucket_key, _, hit_count = row.partition("|")
    if int(hit_count) <= ANALYZE_LIMIT:
        raise RuntimeError("stored counter does not match the requests that were sent")
    # 저장된 행이 접속 기록이 되면 안 된다.
    if not BUCKET_KEY_PATTERN.match(bucket_key):
        raise RuntimeError("rate limit bucket key was not a hashed identifier")

    return {"limited_at": limited_at, "retry_after_seconds": int(retry_after)}


def verify_retention_schedule(
    opener: urllib.request.OpenerDirector,
) -> dict[str, object]:
    """만료된 데이터가 아무도 부르지 않아도 사라지는지 본다.

    `--once` 로 한 번 돌려보는 것으로는 부족하다. 그건 스크립트가 동작한다는
    확인이지, 스케줄이 걸려 있다는 확인이 아니다. P0-2 가 막고 있던 것은
    후자다. 그래서 실제로 한 주기를 기다린다.
    """
    if RETENTION_INTERVAL > MAX_VERIFIABLE_RETENTION_INTERVAL:
        raise RuntimeError(
            "FINSHIELD_RETENTION_INTERVAL_SECONDS must be at most "
            f"{MAX_VERIFIABLE_RETENTION_INTERVAL} for this run; "
            f"got {RETENTION_INTERVAL}"
        )

    status, _ = request_json(opener, "POST", "/api/proxy/auth/session")
    if status != 201:
        raise RuntimeError("retention verification could not create a session")
    user_id = db_shell(
        'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc '
        "'SELECT user_id FROM users LIMIT 1'",
        capture=True,
    )
    if not user_id:
        raise RuntimeError("retention verification session was not persisted")

    # TTL 이 30일이라 기다려서 만료시킬 수 없다. 만료 시각만 과거로 옮긴다.
    db_shell(
        'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc '
        "\"UPDATE auth_sessions SET expires_at = now() - interval '1 day'\""
    )

    deadline = time.monotonic() + RETENTION_INTERVAL * 2 + 30
    while time.monotonic() < deadline:
        remaining = db_shell(
            'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc '
            "'SELECT count(*) FROM users'",
            capture=True,
        )
        if remaining == "0":
            break
        time.sleep(2)
    else:
        raise RuntimeError(
            "expired anonymous data survived the retention interval"
        )

    health = compose(
        "ps", "--format", "{{.Service}}|{{.Health}}", capture=True
    )
    if "retention|healthy" not in health:
        raise RuntimeError(f"retention container did not report healthy: {health}")

    logs = compose("logs", "--no-color", "retention", capture=True)
    if '"status":"succeeded"' not in logs:
        raise RuntimeError("retention did not emit a structured success log")
    if user_id in logs:
        raise RuntimeError("retention logs exposed the identifier it deleted")

    return {"deleted_within_interval_seconds": RETENTION_INTERVAL, "healthy": True}


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
        verify_request_size_limit()
        rate_limit = verify_rate_limit()
        status, _ = request_json(opener, "POST", "/api/proxy/auth/session")
        if status != 201:
            raise RuntimeError("anonymous session was not created")
        session_created = True
        session_tokens = [cookie.value for cookie in cookie_jar]
        if len(session_tokens) != 1:
            raise RuntimeError("runtime verification did not receive exactly one session cookie")

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

        backend_logs = compose("logs", "--no-color", "backend", capture=True)
        for secret in ("2800000", profile_id, session_tokens[0]):
            if secret in backend_logs:
                raise RuntimeError("backend logs exposed runtime verification personal data")
        if '"event":"http_request"' not in backend_logs:
            raise RuntimeError("structured request observability log was not emitted")

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

        # 여기서부터는 DB 가 비어 있다. 만료 데이터를 새로 하나 넣고,
        # 아무도 부르지 않아도 사라지는지 본다.
        retention = verify_retention_schedule(opener)

        print(
            json.dumps(
                {
                    "backend_restart_persistence": True,
                    "backup_restore": True,
                    "encrypted_backup_plaintext_absent": True,
                    "logs_exclude_profile_and_session_values": True,
                    "structured_request_logs": True,
                    "account_delete_counts": counts,
                    "oversized_body_rejected": True,
                    "rate_limit": rate_limit,
                    "rate_limit_counters_hashed": True,
                    "retention_schedule": retention,
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
