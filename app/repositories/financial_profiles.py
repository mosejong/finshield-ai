from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from threading import RLock
from uuid import UUID, uuid4

from app.schemas.financial_profile import FinancialProfile, FinancialProfileResource


class FinancialProfileNotFoundError(KeyError):
    pass


class FinancialProfileCapacityError(RuntimeError):
    pass


class InMemoryFinancialProfileRepository:
    """Thread-safe, process-local prototype storage.

    The repository deliberately does not pretend to be durable. PostgreSQL and
    authentication must replace this implementation before public deployment.
    """

    def __init__(
        self,
        *,
        max_profiles: int = 1_000,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if max_profiles < 1:
            raise ValueError("max_profiles must be at least 1")

        self._max_profiles = max_profiles
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._profiles: dict[UUID, FinancialProfileResource] = {}
        self._lock = RLock()

    def create(self, profile: FinancialProfile) -> FinancialProfileResource:
        with self._lock:
            if len(self._profiles) >= self._max_profiles:
                raise FinancialProfileCapacityError("profile capacity reached")

            now = self._utc_now()
            record = FinancialProfileResource(
                profile_id=uuid4(),
                profile=profile.model_copy(deep=True),
                created_at=now,
                updated_at=now,
            )
            self._profiles[record.profile_id] = record.model_copy(deep=True)
            return record.model_copy(deep=True)

    def get(self, profile_id: UUID) -> FinancialProfileResource:
        with self._lock:
            try:
                record = self._profiles[profile_id]
            except KeyError as exc:
                raise FinancialProfileNotFoundError(profile_id) from exc
            return record.model_copy(deep=True)

    def replace(
        self, profile_id: UUID, profile: FinancialProfile
    ) -> FinancialProfileResource:
        with self._lock:
            try:
                current = self._profiles[profile_id]
            except KeyError as exc:
                raise FinancialProfileNotFoundError(profile_id) from exc

            now = self._utc_now()
            if now <= current.updated_at:
                now = current.updated_at + timedelta(microseconds=1)

            replacement = FinancialProfileResource(
                profile_id=profile_id,
                profile=profile.model_copy(deep=True),
                created_at=current.created_at,
                updated_at=now,
            )
            self._profiles[profile_id] = replacement.model_copy(deep=True)
            return replacement.model_copy(deep=True)

    def delete(self, profile_id: UUID) -> None:
        with self._lock:
            try:
                del self._profiles[profile_id]
            except KeyError as exc:
                raise FinancialProfileNotFoundError(profile_id) from exc

    def _utc_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return value.astimezone(timezone.utc)
