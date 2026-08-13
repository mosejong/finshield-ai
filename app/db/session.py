from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def build_engine(database_url: str) -> Engine:
    options: dict[str, object] = {"pool_pre_ping": True}
    if database_url in {"sqlite://", "sqlite+pysqlite://"}:
        options.update(
            {
                "connect_args": {"check_same_thread": False},
                "poolclass": StaticPool,
            }
        )
    elif database_url.startswith(("sqlite://", "sqlite+pysqlite://")):
        options["connect_args"] = {"check_same_thread": False}
    return create_engine(database_url, **options)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
