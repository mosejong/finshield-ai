from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import inspect, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import FinancialProfileRecord
from app.schemas.financial_profile import FinancialProfile, FinancialProfileResource
from app.security.profile_encryption import (
    ProfileDecryptionError,
    ProfileEncryptionKeyring,
)


class FinancialProfileNotFoundError(KeyError):
    pass


class FinancialProfileCapacityError(RuntimeError):
    pass


class FinancialProfileStorageError(RuntimeError):
    pass


class FinancialProfileRepository(Protocol):
    def verify(self) -> None: ...

    def create(self, profile: FinancialProfile) -> FinancialProfileResource: ...

    def get(self, profile_id: UUID) -> FinancialProfileResource: ...

    def replace(
        self, profile_id: UUID, profile: FinancialProfile
    ) -> FinancialProfileResource: ...

    def delete(self, profile_id: UUID) -> None: ...


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

    def verify(self) -> None:
        return None

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


class SqlAlchemyFinancialProfileRepository:
    """Durable repository storing only authenticated ciphertext profile data."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        keyring: ProfileEncryptionKeyring,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._keyring = keyring
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def verify(self) -> None:
        with self._session_factory() as session:
            try:
                session.execute(select(1))
                if not inspect(session.get_bind()).has_table(
                    FinancialProfileRecord.__tablename__
                ):
                    raise FinancialProfileStorageError(
                        "financial profile migration is not applied"
                    )
            except FinancialProfileStorageError:
                raise
            except SQLAlchemyError:
                raise FinancialProfileStorageError(
                    "financial profile storage is unavailable"
                ) from None

    def create(self, profile: FinancialProfile) -> FinancialProfileResource:
        profile_id = uuid4()
        now = self._utc_now()
        encrypted = self._keyring.encrypt(profile, profile_id)
        record = FinancialProfileRecord(
            profile_id=str(profile_id),
            encrypted_profile=encrypted.ciphertext,
            encryption_key_id=encrypted.key_id,
            created_at=now,
            updated_at=now,
        )
        with self._session_factory() as session:
            try:
                session.add(record)
                session.commit()
            except SQLAlchemyError as exc:
                session.rollback()
                raise FinancialProfileStorageError(
                    "financial profile write failed"
                ) from exc
        return self._resource_from_record(record)

    def get(self, profile_id: UUID) -> FinancialProfileResource:
        with self._session_factory() as session:
            try:
                record = session.get(FinancialProfileRecord, str(profile_id))
            except SQLAlchemyError as exc:
                raise FinancialProfileStorageError(
                    "financial profile read failed"
                ) from exc
            if record is None:
                raise FinancialProfileNotFoundError(profile_id)
            return self._resource_from_record(record)

    def replace(
        self, profile_id: UUID, profile: FinancialProfile
    ) -> FinancialProfileResource:
        with self._session_factory() as session:
            try:
                record = session.get(
                    FinancialProfileRecord,
                    str(profile_id),
                    with_for_update=True,
                )
                if record is None:
                    raise FinancialProfileNotFoundError(profile_id)

                current_updated_at = _as_utc(record.updated_at)
                now = self._utc_now()
                if now <= current_updated_at:
                    now = current_updated_at + timedelta(microseconds=1)

                encrypted = self._keyring.encrypt(profile, profile_id)
                record.encrypted_profile = encrypted.ciphertext
                record.encryption_key_id = encrypted.key_id
                record.updated_at = now
                session.commit()
            except FinancialProfileNotFoundError:
                session.rollback()
                raise
            except SQLAlchemyError as exc:
                session.rollback()
                raise FinancialProfileStorageError(
                    "financial profile write failed"
                ) from exc
            return self._resource_from_record(record)

    def delete(self, profile_id: UUID) -> None:
        with self._session_factory() as session:
            try:
                record = session.get(
                    FinancialProfileRecord,
                    str(profile_id),
                    with_for_update=True,
                )
                if record is None:
                    raise FinancialProfileNotFoundError(profile_id)
                session.delete(record)
                session.commit()
            except FinancialProfileNotFoundError:
                session.rollback()
                raise
            except SQLAlchemyError as exc:
                session.rollback()
                raise FinancialProfileStorageError(
                    "financial profile delete failed"
                ) from exc

    def _resource_from_record(
        self, record: FinancialProfileRecord
    ) -> FinancialProfileResource:
        try:
            profile_id = UUID(record.profile_id)
            profile = self._keyring.decrypt(
                record.encrypted_profile,
                record.encryption_key_id,
                profile_id,
            )
        except (ProfileDecryptionError, ValueError) as exc:
            raise FinancialProfileStorageError(
                "financial profile decryption failed"
            ) from exc
        return FinancialProfileResource(
            profile_id=profile_id,
            profile=profile,
            created_at=_as_utc(record.created_at),
            updated_at=_as_utc(record.updated_at),
        )

    def _utc_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return value.astimezone(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
