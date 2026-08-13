from collections.abc import Mapping
from pathlib import Path

from sqlalchemy import URL


_MAX_SECRET_BYTES = 16_384


class RuntimeSecretConfigurationError(RuntimeError):
    pass


def read_secret_setting(values: Mapping[str, str], name: str) -> str:
    direct = values.get(name, "").strip()
    file_path = values.get(f"{name}_FILE", "").strip()
    if direct and file_path:
        raise RuntimeSecretConfigurationError(
            f"{name} and {name}_FILE cannot both be configured"
        )
    if direct:
        return direct
    if not file_path:
        return ""

    try:
        payload = Path(file_path).read_bytes()
    except OSError as exc:
        raise RuntimeSecretConfigurationError(
            f"{name}_FILE could not be read"
        ) from exc
    if not payload or len(payload) > _MAX_SECRET_BYTES:
        raise RuntimeSecretConfigurationError(
            f"{name}_FILE has an invalid size"
        )
    try:
        value = payload.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise RuntimeSecretConfigurationError(
            f"{name}_FILE must contain UTF-8 text"
        ) from exc
    if not value:
        raise RuntimeSecretConfigurationError(f"{name}_FILE is empty")
    return value


def resolve_database_url(values: Mapping[str, str]) -> str:
    database_url = read_secret_setting(values, "DATABASE_URL")
    component_names = (
        "DATABASE_HOST",
        "DATABASE_PORT",
        "DATABASE_NAME",
        "DATABASE_USER",
        "DATABASE_PASSWORD",
        "DATABASE_PASSWORD_FILE",
    )
    has_components = any(values.get(name, "").strip() for name in component_names)
    if database_url and has_components:
        raise RuntimeSecretConfigurationError(
            "DATABASE_URL cannot be combined with database components"
        )
    if database_url:
        return database_url
    if not has_components:
        return ""

    host = values.get("DATABASE_HOST", "").strip()
    database = values.get("DATABASE_NAME", "").strip()
    username = values.get("DATABASE_USER", "").strip()
    password = read_secret_setting(values, "DATABASE_PASSWORD")
    if not all((host, database, username, password)):
        raise RuntimeSecretConfigurationError(
            "database component configuration is incomplete"
        )
    raw_port = values.get("DATABASE_PORT", "5432").strip()
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise RuntimeSecretConfigurationError("DATABASE_PORT must be an integer") from exc
    if port < 1 or port > 65_535:
        raise RuntimeSecretConfigurationError("DATABASE_PORT is out of range")

    return URL.create(
        "postgresql+psycopg",
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
    ).render_as_string(hide_password=False)


def resolve_profile_encryption_keys(values: Mapping[str, str]) -> str:
    return read_secret_setting(values, "PROFILE_ENCRYPTION_KEYS")
