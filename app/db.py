from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache(maxsize=4)
def get_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().database_url
    assert url is not None
    return create_engine(url, future=True, echo=False)


def get_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(database_url), expire_on_commit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        yield session
