from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import Base, get_engine, get_session_factory


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BU_FERNET_KEY", "x" * 44 + "=")
    monkeypatch.setenv("BU_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_engine.cache_clear()


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return get_settings()


@pytest.fixture()
def db_session(tmp_path: Path) -> Generator[Session, None, None]:
    url = f"sqlite:///{tmp_path}/test.db"
    engine = get_engine(url)
    Base.metadata.create_all(engine)
    SessionLocal = get_session_factory(url)
    with SessionLocal() as session:
        yield session
    Base.metadata.drop_all(engine)
