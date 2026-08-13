from pathlib import Path

import pytest

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
