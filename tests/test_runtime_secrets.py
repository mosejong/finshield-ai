from pathlib import Path
import os
import subprocess

import pytest
import yaml

from app.core.runtime_secrets import (
    RuntimeSecretConfigurationError,
    read_secret_setting,
    resolve_database_url,
    resolve_profile_encryption_keys,
)


def write_secret(path: Path, value: str) -> str:
    path.write_text(value, encoding="utf-8")
    return str(path)


def test_secret_file_is_trimmed_without_exposing_its_path(tmp_path: Path) -> None:
    secret_path = tmp_path / "profile-key"
    values = {"PROFILE_ENCRYPTION_KEYS_FILE": write_secret(secret_path, "key\n")}

    assert resolve_profile_encryption_keys(values) == "key"


def test_direct_and_file_secret_are_mutually_exclusive(tmp_path: Path) -> None:
    secret_path = tmp_path / "database-url"
    values = {
        "DATABASE_URL": "postgresql+psycopg://direct",
        "DATABASE_URL_FILE": write_secret(secret_path, "postgresql+psycopg://file"),
    }

    with pytest.raises(RuntimeSecretConfigurationError, match="cannot both"):
        read_secret_setting(values, "DATABASE_URL")


def test_missing_empty_and_oversized_secret_files_fail_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(RuntimeSecretConfigurationError, match="could not be read"):
        read_secret_setting({"DATABASE_PASSWORD_FILE": str(missing)}, "DATABASE_PASSWORD")

    empty = tmp_path / "empty"
    empty.write_bytes(b"")
    with pytest.raises(RuntimeSecretConfigurationError, match="invalid size"):
        read_secret_setting({"DATABASE_PASSWORD_FILE": str(empty)}, "DATABASE_PASSWORD")

    oversized = tmp_path / "oversized"
    oversized.write_bytes(b"x" * 16_385)
    with pytest.raises(RuntimeSecretConfigurationError, match="invalid size"):
        read_secret_setting(
            {"DATABASE_PASSWORD_FILE": str(oversized)},
            "DATABASE_PASSWORD",
        )


def test_database_components_build_encoded_postgres_url(tmp_path: Path) -> None:
    password_path = tmp_path / "password"
    values = {
        "DATABASE_HOST": "db",
        "DATABASE_PORT": "5432",
        "DATABASE_NAME": "finshield",
        "DATABASE_USER": "finshield_app",
        "DATABASE_PASSWORD_FILE": write_secret(password_path, "p@ss:/word"),
    }

    assert resolve_database_url(values) == (
        "postgresql+psycopg://finshield_app:p%40ss%3A%2Fword@db:5432/finshield"
    )


@pytest.mark.parametrize(
    "values",
    [
        {"DATABASE_HOST": "db"},
        {
            "DATABASE_HOST": "db",
            "DATABASE_NAME": "finshield",
            "DATABASE_USER": "finshield",
            "DATABASE_PASSWORD": "password",
            "DATABASE_PORT": "invalid",
        },
        {
            "DATABASE_URL": "postgresql+psycopg://direct",
            "DATABASE_HOST": "db",
        },
    ],
)
def test_incomplete_or_ambiguous_database_components_fail(values: dict[str, str]) -> None:
    with pytest.raises(RuntimeSecretConfigurationError):
        resolve_database_url(values)


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not authoritative on Windows")
def test_generated_compose_secrets_use_private_directory_readable_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import create_local_docker_secrets

    secret_dir = tmp_path / "secrets"
    monkeypatch.setattr(
        create_local_docker_secrets,
        "__file__",
        str(tmp_path / "scripts" / "create_local_docker_secrets.py"),
    )

    assert create_local_docker_secrets.main() == 0
    assert secret_dir.stat().st_mode & 0o777 == 0o700
    for name in create_local_docker_secrets.SECRET_FILES:
        assert (secret_dir / name).stat().st_mode & 0o777 == 0o644


REPO_ROOT = Path(__file__).resolve().parents[1]


def _git_ignores(path: str) -> bool:
    """git 이 이 경로를 무시하는지 git 에게 직접 물어본다.

    `.gitignore` 를 정규식으로 읽지 않는 이유: 무시 규칙은 부정(`!`)·우선순위·
    하위 `.gitignore` 가 얽혀서 텍스트만 봐서는 결과를 알 수 없다. 여기서
    확인하려는 것은 규칙의 생김새가 아니라 **실제로 커밋 가능한가** 이다.
    """
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--", path],
        cwd=REPO_ROOT,
        capture_output=True,
    )
    assert result.returncode in (0, 1), (
        f"git check-ignore 가 실패했다: {result.returncode}"
    )
    return result.returncode == 0


@pytest.mark.skipif(
    not (REPO_ROOT / ".git").exists(), reason="git 작업 트리가 아니다"
)
def test_every_compose_secret_file_is_ignored_by_git() -> None:
    """compose 가 요구하는 비밀 파일이 저장소에 들어갈 수 없어야 한다.

    이 파일들은 호스트에서 사람이 만든다. 하나라도 커밋되면 되돌릴 수 없다 -
    이력에서 지워도 이미 push 된 값은 유출된 것으로 취급해야 한다.
    """
    compose = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))

    declared = [entry["file"].lstrip("./") for entry in compose["secrets"].values()]
    assert declared, "compose.yaml 에 secrets 선언이 없다"

    leaking = [path for path in declared if not _git_ignores(path)]
    assert not leaking, f"커밋 가능한 비밀 파일: {leaking}"


@pytest.mark.skipif(
    not (REPO_ROOT / ".git").exists(), reason="git 작업 트리가 아니다"
)
def test_secrets_are_ignored_by_directory_not_by_extension() -> None:
    """`secrets/` 안이면 이름과 무관하게 무시돼야 한다.

    규칙이 `secrets/*.txt` 였을 때 `keys.pem` 이나 확장자 없는 파일이 그대로
    커밋 가능했다. 위 검사는 지금 선언된 세 파일만 보므로 이 구멍을 못 잡는다 -
    `.txt` 를 안 쓰는 **새 비밀**이 추가될 때 걸려야 한다.
    """
    committable = [
        name
        for name in ("keys.pem", "backup.key", "profile_encryption_keys", "creds.json")
        if not _git_ignores(f"secrets/{name}")
    ]

    assert not committable, f"secrets/ 안인데 커밋 가능하다: {committable}"
