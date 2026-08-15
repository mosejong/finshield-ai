"""고정 window rate limit 카운터 저장소.

Redis 를 쓰지 않는다. CLAUDE.md 가 "demonstrated need" 를 요구하는데, 지금
필요한 것은 워커 간 공유와 재시작 후 유지뿐이고 이미 있는 PostgreSQL 로
둘 다 된다. 운영 대상이 하나 늘어나는 비용이 그 이득보다 크다.

증가 연산은 반드시 원자적이어야 한다. `SELECT` 후 `UPDATE` 로 나누면 워커가
여러 개일 때 같은 window 를 동시에 읽어 서로의 증가를 덮어쓴다. 제한이
워커 수만큼 헐거워진다 - 조용히, 부하가 높을 때만.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Protocol

from sqlalchemy import delete as sqlalchemy_delete
from sqlalchemy import func, inspect, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import RateLimitCounterRecord


class RateLimitStorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class RateLimitCleanupSummary:
    counters: int
    executed: bool


class RateLimitRepository(Protocol):
    def verify(self) -> None: ...

    def increment(
        self, *, bucket_key: str, window_start: datetime, window_end: datetime
    ) -> int:
        """window 안의 요청 수를 1 늘리고 늘어난 값을 돌려준다."""
        ...

    def cleanup_expired(
        self, *, now: datetime, execute: bool
    ) -> RateLimitCleanupSummary: ...


class InMemoryRateLimitRepository:
    def __init__(self) -> None:
        self._counters: dict[tuple[str, datetime], tuple[datetime, int]] = {}
        self._lock = RLock()

    def verify(self) -> None:
        return None

    def increment(
        self, *, bucket_key: str, window_start: datetime, window_end: datetime
    ) -> int:
        key = (bucket_key, _as_utc(window_start))
        with self._lock:
            _, count = self._counters.get(key, (_as_utc(window_end), 0))
            count += 1
            self._counters[key] = (_as_utc(window_end), count)
            return count

    def cleanup_expired(
        self, *, now: datetime, execute: bool
    ) -> RateLimitCleanupSummary:
        now = _as_utc(now)
        with self._lock:
            stale = [
                key
                for key, (window_end, _) in self._counters.items()
                if window_end <= now
            ]
            if execute:
                for key in stale:
                    del self._counters[key]
            return RateLimitCleanupSummary(counters=len(stale), executed=execute)


class SqlAlchemyRateLimitRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def verify(self) -> None:
        with self._session_factory() as session:
            try:
                inspector = inspect(session.get_bind())
                if RateLimitCounterRecord.__tablename__ not in set(
                    inspector.get_table_names()
                ):
                    raise RateLimitStorageError("rate limit migration is not applied")
            except RateLimitStorageError:
                raise
            except SQLAlchemyError:
                raise RateLimitStorageError(
                    "rate limit storage is unavailable"
                ) from None

    def increment(
        self, *, bucket_key: str, window_start: datetime, window_end: datetime
    ) -> int:
        window_start = _as_utc(window_start)
        window_end = _as_utc(window_end)
        with self._session_factory() as session:
            try:
                statement = _upsert(session).values(
                    bucket_key=bucket_key,
                    window_start=window_start,
                    window_end=window_end,
                    hit_count=1,
                )
                statement = statement.on_conflict_do_update(
                    index_elements=["bucket_key", "window_start"],
                    set_={
                        "hit_count": RateLimitCounterRecord.hit_count + 1,
                    },
                ).returning(RateLimitCounterRecord.hit_count)
                hit_count = session.scalar(statement)
                session.commit()
            except SQLAlchemyError:
                session.rollback()
                raise RateLimitStorageError("rate limit counter write failed") from None
        if hit_count is None:
            raise RateLimitStorageError("rate limit counter write returned no row")
        return int(hit_count)

    def cleanup_expired(
        self, *, now: datetime, execute: bool
    ) -> RateLimitCleanupSummary:
        now = _as_utc(now)
        with self._session_factory() as session:
            try:
                counters = session.scalar(
                    select(func.count())
                    .select_from(RateLimitCounterRecord)
                    .where(RateLimitCounterRecord.window_end <= now)
                ) or 0
                if execute and counters:
                    session.execute(
                        sqlalchemy_delete(RateLimitCounterRecord).where(
                            RateLimitCounterRecord.window_end <= now
                        )
                    )
                    session.commit()
                return RateLimitCleanupSummary(counters=counters, executed=execute)
            except SQLAlchemyError:
                session.rollback()
                raise RateLimitStorageError("rate limit cleanup failed") from None


def _upsert(session: Session):
    """`ON CONFLICT DO UPDATE` 는 dialect 별 construct 로만 쓸 수 있다.

    PostgreSQL 은 운영, SQLite 는 테스트다. 문법은 같지만 SQLAlchemy 는
    별도 함수로 노출한다.
    """
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        return postgresql_insert(RateLimitCounterRecord)
    if dialect == "sqlite":
        return sqlite_insert(RateLimitCounterRecord)
    raise RateLimitStorageError(f"unsupported database dialect: {dialect}")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
