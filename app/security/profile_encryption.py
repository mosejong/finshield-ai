from dataclasses import dataclass
from hashlib import sha256
import json
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken

from app.schemas.financial_profile import FinancialProfile


class ProfileEncryptionConfigurationError(ValueError):
    pass


class ProfileDecryptionError(RuntimeError):
    pass


@dataclass(frozen=True)
class EncryptedProfile:
    ciphertext: bytes
    key_id: str


class ProfileEncryptionKeyring:
    """Authenticated profile encryption with explicit key rotation support.

    The first configured Fernet key is active for new writes. Remaining keys
    are decrypt-only keys retained while existing rows are migrated.
    """

    def __init__(self, encoded_keys: list[str]) -> None:
        normalized = [value.strip() for value in encoded_keys if value.strip()]
        if not normalized:
            raise ProfileEncryptionConfigurationError(
                "at least one profile encryption key is required"
            )

        ciphers: dict[str, Fernet] = {}
        ordered_ids: list[str] = []
        for encoded_key in normalized:
            try:
                cipher = Fernet(encoded_key.encode("ascii"))
            except (ValueError, UnicodeEncodeError) as exc:
                raise ProfileEncryptionConfigurationError(
                    "PROFILE_ENCRYPTION_KEYS contains an invalid Fernet key"
                ) from exc

            key_id = _key_id(encoded_key)
            if key_id in ciphers:
                continue
            ciphers[key_id] = cipher
            ordered_ids.append(key_id)

        self._ciphers = ciphers
        self._active_key_id = ordered_ids[0]

    @classmethod
    def from_comma_separated(cls, value: str) -> "ProfileEncryptionKeyring":
        return cls(value.split(","))

    @property
    def active_key_id(self) -> str:
        return self._active_key_id

    def encrypt(self, profile: FinancialProfile, profile_id: UUID) -> EncryptedProfile:
        envelope = {
            "version": 1,
            "profile_id": str(profile_id),
            "profile": profile.model_dump(mode="json"),
        }
        plaintext = json.dumps(
            envelope,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        ciphertext = self._ciphers[self._active_key_id].encrypt(plaintext)
        return EncryptedProfile(ciphertext=ciphertext, key_id=self._active_key_id)

    def decrypt(
        self,
        ciphertext: bytes,
        key_id: str,
        expected_profile_id: UUID,
    ) -> FinancialProfile:
        cipher = self._ciphers.get(key_id)
        if cipher is None:
            raise ProfileDecryptionError("profile encryption key is unavailable")
        try:
            plaintext = cipher.decrypt(ciphertext)
            envelope = json.loads(plaintext)
            if envelope.get("version") != 1:
                raise ValueError("unsupported encrypted profile version")
            if envelope.get("profile_id") != str(expected_profile_id):
                raise ValueError("encrypted profile row binding mismatch")
            return FinancialProfile.model_validate(envelope["profile"])
        except (AttributeError, InvalidToken, KeyError, TypeError, ValueError) as exc:
            raise ProfileDecryptionError("encrypted profile could not be verified") from exc


def _key_id(encoded_key: str) -> str:
    return sha256(encoded_key.encode("ascii")).hexdigest()[:32]
