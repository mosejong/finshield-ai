import os
from pathlib import Path
import secrets

from cryptography.fernet import Fernet


SECRET_FILES = {
    "postgres_password.txt": lambda: secrets.token_urlsafe(32),
    "profile_encryption_keys.txt": lambda: Fernet.generate_key().decode("ascii"),
}


def main() -> int:
    secret_dir = Path(__file__).resolve().parents[1] / "secrets"
    targets = [secret_dir / name for name in SECRET_FILES]
    existing = [path.name for path in targets if path.exists()]
    if existing:
        names = ", ".join(sorted(existing))
        raise SystemExit(
            f"secret generation refused because files already exist: {names}"
        )

    secret_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    created: list[Path] = []
    try:
        for name, factory in SECRET_FILES.items():
            path = secret_dir / name
            # Compose file secrets are bind-mounted with their host mode. The
            # directory stays owner-only while 0644 lets the non-root container
            # UID read the mounted file on Linux runners.
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(factory())
                stream.write("\n")
            created.append(path)
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise

    print("created local Docker secret files (values not displayed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
