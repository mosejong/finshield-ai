from datetime import datetime, timezone
from threading import RLock
from typing import Protocol
from uuid import UUID

from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AuthSessionRecord, FinancialProfileRecord, UserRecord
from app.schemas.auth import SessionPrincipal


class AuthSessionNotFoundError(KeyError):
    pass


class AuthSessionStorageError(RuntimeError):
    pass


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


class InMemoryAuthSessionRepository:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionPrincipal] = {}
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


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
