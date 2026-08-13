from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Protocol
from uuid import UUID

from sqlalchemy import delete as sqlalchemy_delete
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AuthSessionRecord, FinancialProfileRecord, UserRecord
from app.schemas.auth import SessionPrincipal


class AuthSessionNotFoundError(KeyError):
    pass


class AuthSessionStorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class AuthCleanupSummary:
    expired_sessions: int
    anonymous_users: int
    financial_profiles: int
    executed: bool


class AuthSessionRepository(Protocol):
    def verify(self) -> None: ...

    def create(
        self,
        *,
        token_hash: str,
        user_id: UUID,
        created_at: datetime,
        expires_at: datetime,
    ) -> SessionPrincipal: ...

    def get(self, token_hash: str, *, now: datetime) -> SessionPrincipal: ...

    def delete(self, token_hash: str) -> None: ...

    def delete_user(self, user_id: UUID) -> None: ...

    def cleanup_expired(
        self, *, now: datetime, execute: bool
    ) -> AuthCleanupSummary: ...


class InMemoryAuthSessionRepository:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionPrincipal] = {}
        self._users: set[UUID] = set()
        self._lock = RLock()

    def verify(self) -> None:
        return None

    def create(
        self,
        *,
        token_hash: str,
        user_id: UUID,
        created_at: datetime,
        expires_at: datetime,
    ) -> SessionPrincipal:
        principal = SessionPrincipal(
            user_id=user_id,
            created_at=_as_utc(created_at),
            expires_at=_as_utc(expires_at),
        )
        with self._lock:
            if token_hash in self._sessions:
                raise AuthSessionStorageError("session token collision")
            self._users.add(user_id)
            self._sessions[token_hash] = principal
        return principal.model_copy(deep=True)

    def get(self, token_hash: str, *, now: datetime) -> SessionPrincipal:
        with self._lock:
            principal = self._sessions.get(token_hash)
            if principal is None or principal.expires_at <= _as_utc(now):
                raise AuthSessionNotFoundError(token_hash)
            return principal.model_copy(deep=True)

    def delete(self, token_hash: str) -> None:
        with self._lock:
            self._sessions.pop(token_hash, None)

    def delete_user(self, user_id: UUID) -> None:
        with self._lock:
            token_hashes = [
                token_hash
                for token_hash, principal in self._sessions.items()
                if principal.user_id == user_id
            ]
            for token_hash in token_hashes:
                del self._sessions[token_hash]
            self._users.discard(user_id)

    def cleanup_expired(
        self, *, now: datetime, execute: bool
    ) -> AuthCleanupSummary:
        now = _as_utc(now)
        with self._lock:
            expired_tokens = {
                token_hash
                for token_hash, principal in self._sessions.items()
                if principal.expires_at <= now
            }
            active_users = {
                principal.user_id
                for token_hash, principal in self._sessions.items()
                if token_hash not in expired_tokens
            }
            stale_users = self._users - active_users
            if execute:
                for token_hash in expired_tokens:
                    del self._sessions[token_hash]
                self._users.difference_update(stale_users)
            return AuthCleanupSummary(
                expired_sessions=len(expired_tokens),
                anonymous_users=len(stale_users),
                financial_profiles=0,
                executed=execute,
            )


class SqlAlchemyAuthSessionRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def verify(self) -> None:
        with self._session_factory() as session:
            try:
                inspector = inspect(session.get_bind())
                required = {
                    UserRecord.__tablename__,
                    AuthSessionRecord.__tablename__,
                    FinancialProfileRecord.__tablename__,
                }
                if not required.issubset(set(inspector.get_table_names())):
                    raise AuthSessionStorageError(
                        "authentication migration is not applied"
                    )
                profile_columns = {
                    column["name"]
                    for column in inspector.get_columns(
                        FinancialProfileRecord.__tablename__
                    )
                }
                if "owner_user_id" not in profile_columns:
                    raise AuthSessionStorageError(
                        "profile ownership migration is not applied"
                    )
            except AuthSessionStorageError:
                raise
            except SQLAlchemyError:
                raise AuthSessionStorageError(
                    "authentication storage is unavailable"
                ) from None

    def create(
        self,
        *,
        token_hash: str,
        user_id: UUID,
        created_at: datetime,
        expires_at: datetime,
    ) -> SessionPrincipal:
        created_at = _as_utc(created_at)
        expires_at = _as_utc(expires_at)
        user = UserRecord(
            user_id=str(user_id),
            kind="anonymous",
            status="active",
            created_at=created_at,
        )
        auth_session = AuthSessionRecord(
            token_hash=token_hash,
            user_id=str(user_id),
            created_at=created_at,
            expires_at=expires_at,
        )
        with self._session_factory() as session:
            try:
                session.add(user)
                session.flush()
                session.add(auth_session)
                session.commit()
            except IntegrityError:
                session.rollback()
                raise AuthSessionStorageError("session identity collision") from None
            except SQLAlchemyError:
                session.rollback()
                raise AuthSessionStorageError(
                    "authentication session write failed"
                ) from None
        return SessionPrincipal(
            user_id=user_id,
            created_at=created_at,
            expires_at=expires_at,
        )

    def get(self, token_hash: str, *, now: datetime) -> SessionPrincipal:
        now = _as_utc(now)
        with self._session_factory() as session:
            try:
                row = session.execute(
                    select(AuthSessionRecord, UserRecord)
                    .join(UserRecord, AuthSessionRecord.user_id == UserRecord.user_id)
                    .where(
                        AuthSessionRecord.token_hash == token_hash,
                        AuthSessionRecord.expires_at > now,
                        UserRecord.status == "active",
                    )
                ).one_or_none()
            except SQLAlchemyError:
                raise AuthSessionStorageError(
                    "authentication session read failed"
                ) from None
            if row is None:
                raise AuthSessionNotFoundError(token_hash)
            auth_session, user = row
            return SessionPrincipal(
                user_id=UUID(user.user_id),
                created_at=_as_utc(auth_session.created_at),
                expires_at=_as_utc(auth_session.expires_at),
            )

    def delete(self, token_hash: str) -> None:
        with self._session_factory() as session:
            try:
                auth_session = session.get(AuthSessionRecord, token_hash)
                if auth_session is not None:
                    session.delete(auth_session)
                    session.commit()
            except SQLAlchemyError:
                session.rollback()
                raise AuthSessionStorageError(
                    "authentication session delete failed"
                ) from None

    def delete_user(self, user_id: UUID) -> None:
        with self._session_factory() as session:
            try:
                user = session.get(UserRecord, str(user_id))
                if user is not None:
                    session.delete(user)
                    session.commit()
            except SQLAlchemyError:
                session.rollback()
                raise AuthSessionStorageError(
                    "anonymous account delete failed"
                ) from None

    def cleanup_expired(
        self, *, now: datetime, execute: bool
    ) -> AuthCleanupSummary:
        now = _as_utc(now)
        with self._session_factory() as session:
            try:
                active_session = select(AuthSessionRecord.token_hash).where(
                    AuthSessionRecord.user_id == UserRecord.user_id,
                    AuthSessionRecord.expires_at > now,
                )
                stale_user_ids = list(
                    session.scalars(
                        select(UserRecord.user_id).where(
                            UserRecord.kind == "anonymous",
                            ~active_session.exists(),
                        )
                    )
                )
                if not stale_user_ids:
                    return AuthCleanupSummary(0, 0, 0, execute)

                expired_sessions = session.scalar(
                    select(func.count())
                    .select_from(AuthSessionRecord)
                    .where(AuthSessionRecord.user_id.in_(stale_user_ids))
                ) or 0
                financial_profiles = session.scalar(
                    select(func.count())
                    .select_from(FinancialProfileRecord)
                    .where(FinancialProfileRecord.owner_user_id.in_(stale_user_ids))
                ) or 0
                if execute:
                    session.execute(
                        sqlalchemy_delete(UserRecord).where(
                            UserRecord.user_id.in_(stale_user_ids)
                        )
                    )
                    session.commit()
                return AuthCleanupSummary(
                    expired_sessions=expired_sessions,
                    anonymous_users=len(stale_user_ids),
                    financial_profiles=financial_profiles,
                    executed=execute,
                )
            except SQLAlchemyError:
                session.rollback()
                raise AuthSessionStorageError(
                    "expired anonymous data cleanup failed"
                ) from None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
