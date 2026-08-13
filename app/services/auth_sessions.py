from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import secrets
from uuid import uuid4

from app.repositories.auth_sessions import (
    AuthSessionNotFoundError,
    AuthSessionRepository,
)
from app.schemas.auth import SessionPrincipal


@dataclass(frozen=True)
class SessionIssue:
    principal: SessionPrincipal
    raw_token: str | None


class AuthSessionService:
    def __init__(
        self,
        repository: AuthSessionRepository,
        *,
        ttl: timedelta = timedelta(days=30),
        cookie_secure: bool = False,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if ttl < timedelta(minutes=5) or ttl > timedelta(days=365):
            raise ValueError("session ttl must be between 5 minutes and 365 days")
        self._repository = repository
        self._ttl = ttl
        self._cookie_secure = cookie_secure
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def cookie_secure(self) -> bool:
        return self._cookie_secure

    @property
    def ttl_seconds(self) -> int:
        return int(self._ttl.total_seconds())

    def verify_storage(self) -> None:
        self._repository.verify()

    def bootstrap(self, raw_token: str | None) -> SessionIssue:
        if raw_token:
            try:
                return SessionIssue(self.authenticate(raw_token), None)
            except AuthSessionNotFoundError:
                pass

        now = self._utc_now()
        raw_token = secrets.token_urlsafe(32)
        principal = self._repository.create(
            token_hash=_token_hash(raw_token),
            user_id=uuid4(),
            created_at=now,
            expires_at=now + self._ttl,
        )
        return SessionIssue(principal, raw_token)

    def authenticate(self, raw_token: str) -> SessionPrincipal:
        if len(raw_token) < 32 or len(raw_token) > 256:
            raise AuthSessionNotFoundError("invalid session token length")
        return self._repository.get(
            _token_hash(raw_token),
            now=self._utc_now(),
        )

    def revoke(self, raw_token: str | None) -> None:
        if raw_token and 32 <= len(raw_token) <= 256:
            self._repository.delete(_token_hash(raw_token))

    def _utc_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return value.astimezone(timezone.utc)


def _token_hash(raw_token: str) -> str:
    return sha256(raw_token.encode("utf-8")).hexdigest()
