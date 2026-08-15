import os
from pathlib import Path
import secrets

from cryptography.fernet import Fernet


SECRET_FILES = {
    "postgres_password.txt": lambda: secrets.token_urlsafe(32),
    "profile_encryption_keys.txt": lambda: Fernet.generate_key().decode("ascii"),
    # Rate limit bucket keys are HMACs of the client address. Every worker must
    # use the same secret or one client lands in a different bucket per worker.
    "rate_limit_secret.txt": lambda: secrets.token_urlsafe(32),
}


def main() -> int:
    secret_dir = Path(__file__).resolve().parents[1] / "secrets"
    # Existing files are never rewritten. Rotating the profile encryption key
    # here would silently make already-stored profiles unreadable.
    missing = {
        name: factory
        for name, factory in SECRET_FILES.items()
        if not (secret_dir / name).exists()
    }
    if not missing:
        print("all local Docker secret files already exist; nothing to do")
        return 0

    secret_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    created: list[Path] = []
    try:
        for name, factory in missing.items():
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

    names = ", ".join(sorted(path.name for path in created))
    print(f"created local Docker secret files (values not displayed): {names}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
