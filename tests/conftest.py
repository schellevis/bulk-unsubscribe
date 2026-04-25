import os
from collections.abc import Generator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

# Set the Fernet key at conftest import time so app.main can be imported
# from any test module without ad-hoc env setup.
_TEST_FERNET_KEY = Fernet.generate_key().decode()
os.environ.setdefault("BU_FERNET_KEY", _TEST_FERNET_KEY)

from app.config import Settings, get_settings  # noqa: E402
from app.db import Base, get_engine, get_session_factory  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BU_FERNET_KEY", _TEST_FERNET_KEY)
    monkeypatch.setenv("BU_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_engine.cache_clear()


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return get_settings()


@pytest.fixture()
def db_session(tmp_path: Path) -> Generator[Session, None, None]:
    # Use the same URL the app's default settings would resolve to,
    # so jobs/runners/etc. that call get_session_factory() with no URL
    # write to the same SQLite file.
    url = f"sqlite:///{tmp_path}/bulk-unsubscribe.db"
    engine = get_engine(url)
    Base.metadata.create_all(engine)
    SessionLocal = get_session_factory(url)
    with SessionLocal() as session:
        yield session
    Base.metadata.drop_all(engine)
