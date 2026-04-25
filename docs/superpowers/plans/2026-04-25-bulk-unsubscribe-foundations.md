# Bulk Unsubscribe — Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring up a working scan-and-browse foundation: connect IMAP/JMAP accounts, scan with live progress, view top senders by period, drill into a sender and lazily preview their messages. No mailbox mutations yet.

**Architecture:** FastAPI + SQLAlchemy 2.x + Alembic + Jinja2 templates with HTMX for fragments. SQLite persistence in `BU_DATA_DIR`. A `MailProvider` Protocol abstracts IMAP (`imaplib` wrapped in `asyncio.to_thread`) and JMAP (`aiohttp`). Long operations run as in-process async jobs whose state lives in a `jobs` table; the UI polls `/jobs/{id}/fragment` every 2s.

**Tech Stack:** Python 3.12, FastAPI 0.115+, SQLAlchemy 2.x, Alembic, pydantic-settings, cryptography (Fernet), aiohttp, Jinja2, HTMX 2.x, Alpine.js 3.x, pytest + pytest-asyncio + httpx + aioresponses, uv for dependency management, ruff for lint/format.

**Layout:**
```
bulk-unsubscribe/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── db.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── account.py
│   │   ├── sender.py
│   │   ├── message.py
│   │   ├── job.py
│   │   └── action.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── crypto.py
│   │   ├── grouping.py
│   │   └── unsubscribe.py
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── imap.py
│   │   └── jmap.py
│   ├── jobs/
│   │   ├── __init__.py
│   │   ├── runner.py
│   │   └── scan.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── pages.py
│   │   ├── accounts.py
│   │   ├── senders.py
│   │   └── jobs.py
│   └── templates/
│       ├── base.html
│       ├── _macros.html
│       ├── pages/...
│       └── fragments/...
├── alembic/
├── static/
├── tests/
├── pyproject.toml
└── ruff.toml
```

---

## Task 1: Wipe prototype and bootstrap project skeleton

**Files:**
- Delete: `app/`, `static/`, `requirements.txt`
- Create: `pyproject.toml`, `ruff.toml`, `.python-version`, `app/__init__.py`, `app/main.py`, `tests/__init__.py`, `tests/test_smoke.py`, `.gitignore` (append)

- [ ] **Step 1: Delete the v0 prototype source**

```bash
rm -rf app static requirements.txt
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[project]
name = "bulk-unsubscribe"
version = "0.2.0"
description = "Mobile-first webapp to bulk-unsubscribe from newsletters."
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "sqlalchemy>=2.0",
    "alembic>=1.13",
    "pydantic[email]>=2.7",
    "pydantic-settings>=2.4",
    "jinja2>=3.1",
    "python-multipart>=0.0.20",
    "aiohttp>=3.10",
    "cryptography>=43",
    "itsdangerous>=2.2",
]

[dependency-groups]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.24",
    "httpx>=0.27",
    "aioresponses>=0.7.6",
    "ruff>=0.6",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
filterwarnings = ["error::DeprecationWarning"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app"]
```

- [ ] **Step 3: Create `ruff.toml`**

```toml
line-length = 100
target-version = "py312"

[lint]
select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]
ignore = ["E501"]
```

- [ ] **Step 4: Create `.python-version`**

```
3.12
```

- [ ] **Step 5: Append to `.gitignore`**

Append (file already exists):
```
# uv / venv
.venv/
__pycache__/
*.pyc

# project data
var/
*.db

# tooling
.pytest_cache/
.ruff_cache/
```

- [ ] **Step 6: Create `app/__init__.py`** (empty)

- [ ] **Step 7: Create `app/main.py`**

```python
from fastapi import FastAPI

app = FastAPI(title="Bulk Unsubscribe", version="0.2.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 8: Create `tests/__init__.py`** (empty)

- [ ] **Step 9: Create `tests/test_smoke.py`**

```python
from fastapi.testclient import TestClient

from app.main import app


def test_healthz_returns_ok():
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 10: Bootstrap the venv and run the smoke test**

```bash
uv sync --all-groups
uv run pytest -v
```

Expected: 1 passed.

- [ ] **Step 11: Commit**

```bash
git add -A
git commit -m "chore: scrap v0 prototype, bootstrap v0.2 skeleton"
```

---

## Task 2: Settings module

**Files:**
- Create: `app/config.py`, `tests/test_config.py`

- [ ] **Step 1: Write the failing test** — `tests/test_config.py`

```python
import pytest

from app.config import Settings


def test_settings_loads_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("BU_FERNET_KEY", "x" * 44 + "=")
    monkeypatch.setenv("BU_DATA_DIR", str(tmp_path))
    settings = Settings()
    assert settings.fernet_key == "x" * 44 + "="
    assert settings.data_dir == tmp_path
    assert settings.database_url == f"sqlite:///{tmp_path}/bulk-unsubscribe.db"


def test_settings_requires_fernet_key(monkeypatch, tmp_path):
    monkeypatch.delenv("BU_FERNET_KEY", raising=False)
    monkeypatch.setenv("BU_DATA_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="BU_FERNET_KEY"):
        Settings()


def test_settings_creates_data_dir(monkeypatch, tmp_path):
    target = tmp_path / "missing"
    monkeypatch.setenv("BU_FERNET_KEY", "x" * 44 + "=")
    monkeypatch.setenv("BU_DATA_DIR", str(target))
    Settings()
    assert target.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_config.py -v
```

Expected: import error (`app.config` does not exist).

- [ ] **Step 3: Create `app/config.py`**

```python
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BU_",
        env_file=".env",
        extra="ignore",
    )

    fernet_key: str = Field(..., description="Fernet key for credential encryption")
    data_dir: Path = Field(default=Path("./var"))
    database_url: str | None = None
    bind_host: str = "127.0.0.1"
    bind_port: int = 8000

    @field_validator("fernet_key")
    @classmethod
    def _check_fernet_key(cls, v: str) -> str:
        if not v:
            raise ValueError("BU_FERNET_KEY is required")
        return v

    def model_post_init(self, _: object) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.database_url is None:
            self.database_url = f"sqlite:///{self.data_dir}/bulk-unsubscribe.db"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_config.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "feat(config): pydantic-settings with required Fernet key"
```

---

## Task 3: Database engine and session

**Files:**
- Create: `app/db.py`, `tests/conftest.py`, `tests/test_db.py`

- [ ] **Step 1: Write the failing test** — `tests/test_db.py`

```python
from sqlalchemy import text

from app.db import Base, get_session_factory


def test_session_factory_yields_working_session(tmp_path, monkeypatch):
    monkeypatch.setenv("BU_FERNET_KEY", "x" * 44 + "=")
    monkeypatch.setenv("BU_DATA_DIR", str(tmp_path))

    SessionLocal = get_session_factory(f"sqlite:///{tmp_path}/test.db")

    with SessionLocal() as session:
        result = session.execute(text("SELECT 1")).scalar()
        assert result == 1


def test_base_metadata_is_empty_until_models_imported():
    # Models will register themselves on import; here we only assert Base exists
    assert hasattr(Base, "metadata")
```

- [ ] **Step 2: Create `tests/conftest.py`** (shared fixtures)

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/test_db.py -v
```

Expected: import error.

- [ ] **Step 4: Create `app/db.py`**

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_db.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add app/db.py tests/conftest.py tests/test_db.py
git commit -m "feat(db): SQLAlchemy engine + session factory + test fixtures"
```

---

## Task 4: Alembic init and configuration

**Files:**
- Create: `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/.keep`

- [ ] **Step 1: Initialize alembic**

```bash
uv run alembic init -t generic alembic
```

This creates `alembic/`, `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`.

- [ ] **Step 2: Replace `alembic.ini` script_location and url**

Open `alembic.ini`, find `sqlalchemy.url =` and set to `sqlalchemy.url =` (empty — we'll inject from env). Confirm `script_location = alembic`.

- [ ] **Step 3: Replace `alembic/env.py`** with this content

```python
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.config import get_settings
from app.db import Base
from app.models import register_all  # noqa: F401  - imports models so metadata is populated

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url or "")

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: Create `app/models/__init__.py`** with a placeholder `register_all`

```python
"""Importing this module ensures every model is registered on Base.metadata."""

from app.db import Base


def register_all() -> type[Base]:
    # Models will be imported here as they are added.
    return Base
```

- [ ] **Step 5: Sanity-check alembic can boot**

```bash
uv run alembic check 2>&1 | head -5
```

Expected: either "No new upgrade operations detected" or "FAILED: Target database is not up to date" — both mean alembic itself loads fine. An import error would mean env.py is broken.

- [ ] **Step 6: Commit**

```bash
git add alembic.ini alembic/ app/models/__init__.py
git commit -m "feat(alembic): initialize migrations wired to settings"
```

---

## Task 5: Account model + migration

**Files:**
- Create: `app/models/account.py`, `tests/models/__init__.py`, `tests/models/test_account.py`
- Modify: `app/models/__init__.py`

- [ ] **Step 1: Write the failing test** — `tests/models/test_account.py`

```python
from datetime import datetime, timezone

from app.models.account import Account, ProviderType


def test_create_imap_account(db_session):
    account = Account(
        name="Privé",
        email="me@example.com",
        provider=ProviderType.imap,
        imap_host="imap.example.com",
        imap_port=993,
        imap_username="me",
        credential_encrypted="ciphertext",
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)

    assert account.id is not None
    assert account.provider == ProviderType.imap
    assert isinstance(account.created_at, datetime)
    assert account.created_at.tzinfo is not None


def test_create_jmap_account(db_session):
    account = Account(
        name="Fastmail",
        email="me@fastmail.com",
        provider=ProviderType.jmap,
        credential_encrypted="ciphertext",
    )
    db_session.add(account)
    db_session.commit()

    assert account.imap_host is None
    assert account.last_full_scan_at is None
```

- [ ] **Step 2: Create `tests/models/__init__.py`** (empty)

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/models/test_account.py -v
```

Expected: import error.

- [ ] **Step 4: Create `app/models/account.py`**

```python
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SAEnum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ProviderType(str, Enum):
    imap = "imap"
    jmap = "jmap"


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    provider: Mapped[ProviderType] = mapped_column(
        SAEnum(ProviderType, name="provider_type"), nullable=False
    )
    imap_host: Mapped[str | None] = mapped_column(String(255))
    imap_port: Mapped[int | None] = mapped_column(Integer)
    imap_username: Mapped[str | None] = mapped_column(String(255))
    credential_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    last_full_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_incremental_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 5: Wire it into `app/models/__init__.py`**

```python
"""Importing this module ensures every model is registered on Base.metadata."""

from app.db import Base
from app.models.account import Account, ProviderType  # noqa: F401


def register_all() -> type[Base]:
    return Base


__all__ = ["Account", "ProviderType", "register_all"]
```

- [ ] **Step 6: Run model tests**

```bash
uv run pytest tests/models/test_account.py -v
```

Expected: 2 passed.

- [ ] **Step 7: Generate the migration**

```bash
uv run alembic revision --autogenerate -m "create accounts table"
```

Inspect the generated file in `alembic/versions/` to confirm it creates `accounts` with the correct columns. Adjust if anything looks off (autogenerate is conservative; `provider_type` enum on SQLite renders as VARCHAR, that is fine).

- [ ] **Step 8: Apply and check**

```bash
uv run alembic upgrade head
uv run alembic check
```

Expected: "No new upgrade operations detected."

- [ ] **Step 9: Commit**

```bash
git add app/models/ tests/models/ alembic/versions/
git commit -m "feat(model): Account with provider enum and migration"
```

---

## Task 6: Sender + SenderAlias models + migration

**Files:**
- Create: `app/models/sender.py`, `tests/models/test_sender.py`
- Modify: `app/models/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/models/test_sender.py
from datetime import datetime, timezone

from app.models.account import Account, ProviderType
from app.models.sender import Sender, SenderAlias, SenderStatus, WhitelistScope


def _make_account(db) -> Account:
    a = Account(
        name="A", email="a@example.com",
        provider=ProviderType.jmap, credential_encrypted="x",
    )
    db.add(a)
    db.commit()
    return a


def test_sender_with_alias(db_session):
    account = _make_account(db_session)
    sender = Sender(
        account_id=account.id,
        group_key="<list.example.com>",
        from_email="news@example.com",
        from_domain="example.com",
        list_id="<list.example.com>",
        display_name="Example News",
        email_count=12,
    )
    db_session.add(sender)
    db_session.commit()

    alias = SenderAlias(
        sender_id=sender.id,
        from_email="news@example.com",
        from_domain="example.com",
        email_count=12,
    )
    db_session.add(alias)
    db_session.commit()
    db_session.refresh(sender)

    assert sender.status == SenderStatus.active
    assert sender.whitelist_scope == WhitelistScope.none
    assert sender.aliases[0].from_email == "news@example.com"


def test_sender_unique_per_account_and_key(db_session):
    import sqlalchemy.exc

    account = _make_account(db_session)
    db_session.add_all([
        Sender(account_id=account.id, group_key="k1", from_email="a@x.com",
               from_domain="x.com", display_name=""),
    ])
    db_session.commit()

    db_session.add(
        Sender(account_id=account.id, group_key="k1", from_email="b@x.com",
               from_domain="x.com", display_name="")
    )
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db_session.commit()


import pytest  # noqa: E402  (used in second test)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/models/test_sender.py -v
```

Expected: import error.

- [ ] **Step 3: Create `app/models/sender.py`**

```python
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class SenderStatus(str, Enum):
    active = "active"
    unsubscribed = "unsubscribed"
    whitelisted = "whitelisted"
    trashed = "trashed"


class WhitelistScope(str, Enum):
    none = "none"
    sender = "sender"
    domain = "domain"


class Sender(Base):
    __tablename__ = "senders"
    __table_args__ = (
        UniqueConstraint("account_id", "group_key", name="uq_sender_account_group"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    group_key: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    from_email: Mapped[str] = mapped_column(String(320), nullable=False)
    from_domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    list_id: Mapped[str | None] = mapped_column(String(512))
    display_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    email_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unsubscribe_http: Mapped[str | None] = mapped_column(Text)
    unsubscribe_mailto: Mapped[str | None] = mapped_column(Text)
    unsubscribe_one_click_post: Mapped[bool] = mapped_column(default=False, nullable=False)
    status: Mapped[SenderStatus] = mapped_column(
        SAEnum(SenderStatus, name="sender_status"),
        default=SenderStatus.active, nullable=False, index=True,
    )
    whitelist_scope: Mapped[WhitelistScope] = mapped_column(
        SAEnum(WhitelistScope, name="whitelist_scope"),
        default=WhitelistScope.none, nullable=False,
    )
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    aliases: Mapped[list["SenderAlias"]] = relationship(
        "SenderAlias", back_populates="sender", cascade="all, delete-orphan"
    )


class SenderAlias(Base):
    __tablename__ = "sender_aliases"
    __table_args__ = (
        UniqueConstraint("sender_id", "from_email", name="uq_alias_sender_email"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sender_id: Mapped[int] = mapped_column(
        ForeignKey("senders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    from_domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    email_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    sender: Mapped[Sender] = relationship("Sender", back_populates="aliases")
```

- [ ] **Step 4: Re-export from `app/models/__init__.py`**

Replace the file with:

```python
"""Importing this module ensures every model is registered on Base.metadata."""

from app.db import Base
from app.models.account import Account, ProviderType
from app.models.sender import Sender, SenderAlias, SenderStatus, WhitelistScope


def register_all() -> type[Base]:
    return Base


__all__ = [
    "Account", "ProviderType",
    "Sender", "SenderAlias", "SenderStatus", "WhitelistScope",
    "register_all",
]
```

- [ ] **Step 5: Run model tests**

```bash
uv run pytest tests/models/test_sender.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Generate + apply migration**

```bash
uv run alembic revision --autogenerate -m "create senders and sender_aliases"
uv run alembic upgrade head
uv run alembic check
```

- [ ] **Step 7: Commit**

```bash
git add app/models/ tests/models/test_sender.py alembic/versions/
git commit -m "feat(model): Sender + SenderAlias with status/whitelist enums"
```

---

## Task 7: Message, Job, Action models + migration

**Files:**
- Create: `app/models/message.py`, `app/models/job.py`, `app/models/action.py`, `tests/models/test_message_job_action.py`
- Modify: `app/models/__init__.py`

- [ ] **Step 1: Write the failing tests** — `tests/models/test_message_job_action.py`

```python
import json
from datetime import datetime, timezone

from app.models.account import Account, ProviderType
from app.models.action import Action, ActionKind, ActionStatus
from app.models.job import Job, JobStatus, JobType
from app.models.message import Message
from app.models.sender import Sender


def _seed(db):
    account = Account(
        name="A", email="a@x.com",
        provider=ProviderType.jmap, credential_encrypted="x",
    )
    db.add(account)
    db.commit()
    sender = Sender(
        account_id=account.id, group_key="g",
        from_email="a@x.com", from_domain="x.com",
    )
    db.add(sender)
    db.commit()
    return account, sender


def test_message_roundtrip(db_session):
    account, sender = _seed(db_session)
    msg = Message(
        account_id=account.id, sender_id=sender.id,
        provider_uid="123", mailbox="INBOX",
        subject="Hello", received_at=datetime.now(timezone.utc),
    )
    db_session.add(msg)
    db_session.commit()
    db_session.refresh(msg)
    assert msg.has_full_body_cached is False


def test_job_with_params_json(db_session):
    account, _ = _seed(db_session)
    job = Job(
        account_id=account.id,
        type=JobType.scan,
        status=JobStatus.queued,
        params_json=json.dumps({"max_messages": 500}),
    )
    db_session.add(job)
    db_session.commit()
    assert job.progress_total == 0
    assert job.progress_done == 0


def test_action_audit(db_session):
    account, sender = _seed(db_session)
    action = Action(
        account_id=account.id, sender_id=sender.id,
        kind=ActionKind.unsubscribe_one_click,
        status=ActionStatus.success,
        affected_count=1,
        detail="HTTP 200",
    )
    db_session.add(action)
    db_session.commit()
    assert action.created_at is not None
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/models/test_message_job_action.py -v
```

Expected: import error.

- [ ] **Step 3: Create `app/models/message.py`**

```python
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "provider_uid", "mailbox",
            name="uq_message_uid_mailbox",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender_id: Mapped[int] = mapped_column(
        ForeignKey("senders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    mailbox: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(998), default="", nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    snippet: Mapped[str | None] = mapped_column(Text)
    has_full_body_cached: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 4: Create `app/models/job.py`**

```python
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class JobType(str, Enum):
    scan = "scan"
    bulk_archive = "bulk_archive"
    bulk_trash = "bulk_trash"
    bulk_mark_read = "bulk_mark_read"
    unsubscribe = "unsubscribe"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    success = "success"
    failed = "failed"
    cancelled = "cancelled"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[JobType] = mapped_column(SAEnum(JobType, name="job_type"), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus, name="job_status"),
        default=JobStatus.queued, nullable=False, index=True,
    )
    progress_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress_done: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    params_json: Mapped[str | None] = mapped_column(Text)
    result_json: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
```

- [ ] **Step 5: Create `app/models/action.py`**

```python
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    DateTime, Enum as SAEnum, ForeignKey, Integer, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ActionKind(str, Enum):
    unsubscribe_http = "unsubscribe_http"
    unsubscribe_one_click = "unsubscribe_one_click"
    unsubscribe_mailto = "unsubscribe_mailto"
    archive = "archive"
    trash = "trash"
    mark_read = "mark_read"
    whitelist = "whitelist"
    unwhitelist = "unwhitelist"


class ActionStatus(str, Enum):
    success = "success"
    failed = "failed"
    partial = "partial"


class Action(Base):
    __tablename__ = "actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender_id: Mapped[int] = mapped_column(
        ForeignKey("senders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL")
    )
    kind: Mapped[ActionKind] = mapped_column(SAEnum(ActionKind, name="action_kind"), nullable=False)
    status: Mapped[ActionStatus] = mapped_column(
        SAEnum(ActionStatus, name="action_status"), nullable=False
    )
    affected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
```

- [ ] **Step 6: Update `app/models/__init__.py`**

```python
"""Importing this module ensures every model is registered on Base.metadata."""

from app.db import Base
from app.models.account import Account, ProviderType
from app.models.action import Action, ActionKind, ActionStatus
from app.models.job import Job, JobStatus, JobType
from app.models.message import Message
from app.models.sender import Sender, SenderAlias, SenderStatus, WhitelistScope


def register_all() -> type[Base]:
    return Base


__all__ = [
    "Account", "ProviderType",
    "Sender", "SenderAlias", "SenderStatus", "WhitelistScope",
    "Message",
    "Job", "JobStatus", "JobType",
    "Action", "ActionKind", "ActionStatus",
    "register_all",
]
```

- [ ] **Step 7: Run tests**

```bash
uv run pytest tests/models/ -v
```

Expected: all model tests pass.

- [ ] **Step 8: Generate + apply migration**

```bash
uv run alembic revision --autogenerate -m "create messages, jobs, actions"
uv run alembic upgrade head
uv run alembic check
```

- [ ] **Step 9: Commit**

```bash
git add app/models/ tests/models/test_message_job_action.py alembic/versions/
git commit -m "feat(model): Message, Job, Action with enums + migration"
```

---

## Task 8: Crypto service (Fernet, refuse to start without key)

**Files:**
- Create: `app/services/__init__.py` (empty), `app/services/crypto.py`, `tests/services/__init__.py`, `tests/services/test_crypto.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/services/test_crypto.py
import pytest
from cryptography.fernet import Fernet

from app.services.crypto import CredentialCipher


def test_roundtrip_encryption(monkeypatch, tmp_path):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("BU_FERNET_KEY", key)
    monkeypatch.setenv("BU_DATA_DIR", str(tmp_path))

    cipher = CredentialCipher.from_settings()
    token = cipher.encrypt("hunter2")
    assert token != "hunter2"
    assert cipher.decrypt(token) == "hunter2"


def test_invalid_key_raises_at_construction(monkeypatch, tmp_path):
    monkeypatch.setenv("BU_FERNET_KEY", "not-a-real-fernet-key")
    monkeypatch.setenv("BU_DATA_DIR", str(tmp_path))

    with pytest.raises(ValueError, match="Fernet"):
        CredentialCipher.from_settings()
```

- [ ] **Step 2: Create `tests/services/__init__.py`** (empty)

- [ ] **Step 3: Run to verify failure**

```bash
uv run pytest tests/services/test_crypto.py -v
```

Expected: import error.

- [ ] **Step 4: Create `app/services/__init__.py`** (empty)

- [ ] **Step 5: Create `app/services/crypto.py`**

```python
from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings, get_settings


class CredentialCipher:
    def __init__(self, key: str) -> None:
        try:
            self._fernet = Fernet(key.encode())
        except (ValueError, TypeError) as exc:
            raise ValueError(
                "Invalid Fernet key. Generate one with "
                "`python -c 'from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())'`"
            ) from exc

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "CredentialCipher":
        return cls((settings or get_settings()).fernet_key)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Stored credential could not be decrypted") from exc
```

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/services/test_crypto.py -v
```

Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add app/services/ tests/services/
git commit -m "feat(services): Fernet credential cipher with strict key validation"
```

---

## Task 9: Grouping service (group_key, domain extraction)

**Files:**
- Create: `app/services/grouping.py`, `tests/services/test_grouping.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/services/test_grouping.py
import pytest

from app.services.grouping import compute_group_key, extract_domain, normalize_list_id


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("<list.example.com>", "list.example.com"),
        ("  <List.Example.COM>  ", "list.example.com"),
        ("plain-id-no-brackets", "plain-id-no-brackets"),
        ("", ""),
        ("Newsletter <abc@list.example.com>", "abc@list.example.com"),
    ],
)
def test_normalize_list_id(raw, expected):
    assert normalize_list_id(raw) == expected


@pytest.mark.parametrize(
    "addr,expected",
    [
        ("News@Example.com", "example.com"),
        ("a+tag@sub.example.co.uk", "sub.example.co.uk"),
        ("invalid", ""),
        ("", ""),
    ],
)
def test_extract_domain(addr, expected):
    assert extract_domain(addr) == expected


def test_compute_group_key_prefers_list_id():
    assert compute_group_key("Foo <id@list.example>", "news@example.com") == "id@list.example"


def test_compute_group_key_falls_back_to_email_when_list_id_missing():
    assert compute_group_key("", "News@Example.COM") == "news@example.com"


def test_compute_group_key_falls_back_when_list_id_blank():
    assert compute_group_key("   ", "x@y.com") == "x@y.com"
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/services/test_grouping.py -v
```

- [ ] **Step 3: Create `app/services/grouping.py`**

```python
import re

_ANGLE_RE = re.compile(r"<([^>]+)>")


def normalize_list_id(raw: str) -> str:
    if not raw:
        return ""
    raw = raw.strip()
    match = _ANGLE_RE.search(raw)
    inner = match.group(1) if match else raw
    return inner.strip().lower()


def extract_domain(email_addr: str) -> str:
    if not email_addr or "@" not in email_addr:
        return ""
    return email_addr.rsplit("@", 1)[1].strip().lower()


def compute_group_key(list_id_header: str, from_email: str) -> str:
    """Return the canonical group key for a sender.

    Prefers normalized List-ID; falls back to the lowercased From address
    when List-ID is empty or whitespace-only.
    """
    normalized = normalize_list_id(list_id_header)
    if normalized:
        return normalized
    return from_email.strip().lower()
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/services/test_grouping.py -v
```

Expected: all parameterized cases pass.

- [ ] **Step 5: Commit**

```bash
git add app/services/grouping.py tests/services/test_grouping.py
git commit -m "feat(services): grouping logic for List-ID + domain extraction"
```

---

## Task 10: Unsubscribe parser (List-Unsubscribe + RFC 8058)

**Files:**
- Create: `app/services/unsubscribe.py`, `tests/services/test_unsubscribe.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/services/test_unsubscribe.py
from app.services.unsubscribe import UnsubscribeMethods, parse_unsubscribe_methods


def test_http_only():
    m = parse_unsubscribe_methods(
        list_unsubscribe="<https://example.com/u/abc>",
        list_unsubscribe_post=None,
    )
    assert m == UnsubscribeMethods(
        http_url="https://example.com/u/abc",
        mailto_url=None,
        one_click=False,
    )


def test_mailto_only():
    m = parse_unsubscribe_methods(
        list_unsubscribe="<mailto:unsubscribe@example.com?subject=X>",
        list_unsubscribe_post=None,
    )
    assert m.mailto_url == "mailto:unsubscribe@example.com?subject=X"
    assert m.http_url is None
    assert m.one_click is False


def test_both_with_one_click():
    m = parse_unsubscribe_methods(
        list_unsubscribe="<mailto:u@e.com>, <https://e.com/u/x>",
        list_unsubscribe_post="List-Unsubscribe=One-Click",
    )
    assert m.http_url == "https://e.com/u/x"
    assert m.mailto_url == "mailto:u@e.com"
    assert m.one_click is True


def test_one_click_only_when_http_present():
    m = parse_unsubscribe_methods(
        list_unsubscribe="<mailto:u@e.com>",
        list_unsubscribe_post="List-Unsubscribe=One-Click",
    )
    assert m.one_click is False  # spec requires HTTP target


def test_empty_inputs():
    m = parse_unsubscribe_methods(list_unsubscribe="", list_unsubscribe_post=None)
    assert m == UnsubscribeMethods(http_url=None, mailto_url=None, one_click=False)


def test_recommended_method():
    one_click = UnsubscribeMethods(http_url="https://e.com/u/x", mailto_url=None, one_click=True)
    assert one_click.recommended() == "one_click"

    http_only = UnsubscribeMethods(http_url="https://e.com/u/x", mailto_url=None, one_click=False)
    assert http_only.recommended() == "http"

    mailto_only = UnsubscribeMethods(http_url=None, mailto_url="mailto:u@e.com", one_click=False)
    assert mailto_only.recommended() == "mailto"

    none = UnsubscribeMethods(http_url=None, mailto_url=None, one_click=False)
    assert none.recommended() is None
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/services/test_unsubscribe.py -v
```

- [ ] **Step 3: Create `app/services/unsubscribe.py`**

```python
import re
from dataclasses import dataclass
from typing import Literal

_BRACKET_RE = re.compile(r"<([^>]+)>")


@dataclass(frozen=True)
class UnsubscribeMethods:
    http_url: str | None
    mailto_url: str | None
    one_click: bool

    def recommended(self) -> Literal["one_click", "http", "mailto"] | None:
        if self.one_click and self.http_url:
            return "one_click"
        if self.http_url:
            return "http"
        if self.mailto_url:
            return "mailto"
        return None


def parse_unsubscribe_methods(
    list_unsubscribe: str | None,
    list_unsubscribe_post: str | None,
) -> UnsubscribeMethods:
    http_url: str | None = None
    mailto_url: str | None = None

    for raw in _BRACKET_RE.findall(list_unsubscribe or ""):
        candidate = raw.strip()
        lower = candidate.lower()
        if lower.startswith(("https://", "http://")) and http_url is None:
            http_url = candidate
        elif lower.startswith("mailto:") and mailto_url is None:
            mailto_url = candidate

    one_click = False
    if list_unsubscribe_post and http_url:
        # RFC 8058: header value contains "List-Unsubscribe=One-Click"
        if "list-unsubscribe=one-click" in list_unsubscribe_post.lower():
            one_click = True

    return UnsubscribeMethods(http_url=http_url, mailto_url=mailto_url, one_click=one_click)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/services/test_unsubscribe.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add app/services/unsubscribe.py tests/services/test_unsubscribe.py
git commit -m "feat(services): List-Unsubscribe parser with RFC 8058 detection"
```

---

## Task 11: MailProvider Protocol and shared types

**Files:**
- Create: `app/providers/__init__.py` (empty), `app/providers/base.py`, `tests/providers/__init__.py`

- [ ] **Step 1: Create `app/providers/__init__.py`** (empty)

- [ ] **Step 2: Create `tests/providers/__init__.py`** (empty)

- [ ] **Step 3: Create `app/providers/base.py`**

```python
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol


class SpecialFolder(str, Enum):
    inbox = "inbox"
    archive = "archive"
    trash = "trash"
    sent = "sent"
    drafts = "drafts"
    junk = "junk"


@dataclass(frozen=True)
class Mailbox:
    id: str           # provider-native id
    name: str         # display name, e.g. "INBOX"
    role: SpecialFolder | None


@dataclass(frozen=True)
class MessageRef:
    """Pointer to one message at the provider."""
    provider_uid: str
    mailbox: str


@dataclass(frozen=True)
class ScannedMessage:
    """Result of a header-only scan."""
    ref: MessageRef
    from_email: str
    from_domain: str
    display_name: str
    subject: str
    received_at: datetime
    list_id: str | None
    list_unsubscribe: str | None
    list_unsubscribe_post: str | None


@dataclass(frozen=True)
class SenderQuery:
    """Selector for "all messages from this sender" operations.

    Provider implementations OR all `from_emails` together when querying.
    """
    from_emails: list[str]


@dataclass(frozen=True)
class MoveResult:
    moved: int
    failed: int
    errors: list[str]


class MailProvider(Protocol):
    async def test_credentials(self) -> bool: ...

    async def list_mailboxes(self) -> list[Mailbox]: ...

    def scan_headers(
        self, since: datetime | None, max_messages: int
    ) -> AsyncIterator[ScannedMessage]: ...

    async def fetch_snippet(self, ref: MessageRef) -> str: ...

    async def fetch_body(self, ref: MessageRef) -> bytes: ...

    def search_by_sender(
        self, query: SenderQuery, mailboxes: list[str] | None = None
    ) -> AsyncIterator[MessageRef]: ...

    async def move_messages(
        self, refs: list[MessageRef], destination: SpecialFolder
    ) -> MoveResult: ...
```

- [ ] **Step 4: Sanity-import via pytest**

```bash
uv run pytest -v --collect-only
```

Expected: collection succeeds (we haven't added new tests yet).

- [ ] **Step 5: Commit**

```bash
git add app/providers/ tests/providers/__init__.py
git commit -m "feat(providers): MailProvider Protocol + shared dataclasses"
```

---

## Task 12: Fake provider for tests

**Files:**
- Create: `tests/fakes/__init__.py` (empty), `tests/fakes/mail_provider.py`, `tests/providers/test_fake_provider.py`

- [ ] **Step 1: Write the failing test** — `tests/providers/test_fake_provider.py`

```python
from datetime import datetime, timezone

import pytest

from app.providers.base import MessageRef, SenderQuery, SpecialFolder
from tests.fakes.mail_provider import FakeMailProvider, FakeMessage


@pytest.fixture()
def provider() -> FakeMailProvider:
    return FakeMailProvider(messages=[
        FakeMessage(
            uid="1", mailbox="INBOX",
            from_email="news@example.com", display_name="News",
            subject="Hello", received_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            list_id="<news.example.com>",
            list_unsubscribe="<https://example.com/u/1>, <mailto:u@example.com>",
            list_unsubscribe_post="List-Unsubscribe=One-Click",
            body=b"<p>Hello</p>", snippet="Hello",
        ),
        FakeMessage(
            uid="2", mailbox="INBOX",
            from_email="other@example.org", display_name="Other",
            subject="Plain", received_at=datetime(2026, 3, 15, tzinfo=timezone.utc),
            list_id=None, list_unsubscribe=None, list_unsubscribe_post=None,
            body=b"plain", snippet="plain",
        ),
    ])


async def test_test_credentials(provider):
    assert await provider.test_credentials() is True


async def test_scan_headers_returns_only_messages_with_unsubscribe(provider):
    seen = [m async for m in provider.scan_headers(since=None, max_messages=100)]
    assert len(seen) == 1
    assert seen[0].from_email == "news@example.com"
    assert seen[0].list_unsubscribe == "<https://example.com/u/1>, <mailto:u@example.com>"


async def test_fetch_snippet_and_body(provider):
    ref = MessageRef(provider_uid="1", mailbox="INBOX")
    assert await provider.fetch_snippet(ref) == "Hello"
    assert await provider.fetch_body(ref) == b"<p>Hello</p>"


async def test_search_by_sender(provider):
    refs = [r async for r in provider.search_by_sender(
        SenderQuery(from_emails=["news@example.com"]),
        mailboxes=None,
    )]
    assert refs == [MessageRef(provider_uid="1", mailbox="INBOX")]


async def test_move_messages(provider):
    refs = [MessageRef(provider_uid="1", mailbox="INBOX")]
    result = await provider.move_messages(refs, SpecialFolder.trash)
    assert result.moved == 1
    assert provider.messages[0].mailbox == "Trash"
```

- [ ] **Step 2: Create `tests/fakes/__init__.py`** (empty)

- [ ] **Step 3: Run to verify failure**

```bash
uv run pytest tests/providers/test_fake_provider.py -v
```

Expected: import error.

- [ ] **Step 4: Create `tests/fakes/mail_provider.py`**

```python
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime

from app.providers.base import (
    Mailbox,
    MessageRef,
    MoveResult,
    ScannedMessage,
    SenderQuery,
    SpecialFolder,
)


@dataclass
class FakeMessage:
    uid: str
    mailbox: str
    from_email: str
    display_name: str
    subject: str
    received_at: datetime
    list_id: str | None
    list_unsubscribe: str | None
    list_unsubscribe_post: str | None
    body: bytes
    snippet: str


@dataclass
class FakeMailProvider:
    messages: list[FakeMessage] = field(default_factory=list)
    credentials_valid: bool = True
    moved_log: list[tuple[str, SpecialFolder]] = field(default_factory=list)

    async def test_credentials(self) -> bool:
        return self.credentials_valid

    async def list_mailboxes(self) -> list[Mailbox]:
        return [
            Mailbox(id="INBOX", name="INBOX", role=SpecialFolder.inbox),
            Mailbox(id="Archive", name="Archive", role=SpecialFolder.archive),
            Mailbox(id="Trash", name="Trash", role=SpecialFolder.trash),
        ]

    async def scan_headers(
        self, since: datetime | None, max_messages: int
    ) -> AsyncIterator[ScannedMessage]:
        count = 0
        # newest-first
        for m in sorted(self.messages, key=lambda x: x.received_at, reverse=True):
            if count >= max_messages:
                return
            if since and m.received_at < since:
                continue
            if not m.list_unsubscribe:
                continue
            domain = m.from_email.rsplit("@", 1)[-1].lower() if "@" in m.from_email else ""
            yield ScannedMessage(
                ref=MessageRef(provider_uid=m.uid, mailbox=m.mailbox),
                from_email=m.from_email.lower(),
                from_domain=domain,
                display_name=m.display_name,
                subject=m.subject,
                received_at=m.received_at,
                list_id=m.list_id,
                list_unsubscribe=m.list_unsubscribe,
                list_unsubscribe_post=m.list_unsubscribe_post,
            )
            count += 1

    async def fetch_snippet(self, ref: MessageRef) -> str:
        return self._find(ref).snippet

    async def fetch_body(self, ref: MessageRef) -> bytes:
        return self._find(ref).body

    async def search_by_sender(
        self, query: SenderQuery, mailboxes: list[str] | None = None
    ) -> AsyncIterator[MessageRef]:
        wanted = {e.lower() for e in query.from_emails}
        for m in self.messages:
            if mailboxes and m.mailbox not in mailboxes:
                continue
            if m.from_email.lower() in wanted:
                yield MessageRef(provider_uid=m.uid, mailbox=m.mailbox)

    async def move_messages(
        self, refs: list[MessageRef], destination: SpecialFolder
    ) -> MoveResult:
        target = {
            SpecialFolder.archive: "Archive",
            SpecialFolder.trash: "Trash",
        }[destination]
        moved = 0
        for ref in refs:
            for m in self.messages:
                if m.uid == ref.provider_uid and m.mailbox == ref.mailbox:
                    m.mailbox = target
                    self.moved_log.append((m.uid, destination))
                    moved += 1
                    break
        return MoveResult(moved=moved, failed=len(refs) - moved, errors=[])

    def _find(self, ref: MessageRef) -> FakeMessage:
        for m in self.messages:
            if m.uid == ref.provider_uid:
                return m
        raise KeyError(ref)
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/providers/test_fake_provider.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add tests/fakes/ tests/providers/test_fake_provider.py
git commit -m "test: FakeMailProvider implementing the Protocol"
```

---

## Task 13: JMAP provider — credentials test (session bootstrap)

**Files:**
- Create: `app/providers/jmap.py`, `tests/providers/test_jmap_session.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/providers/test_jmap_session.py
import pytest
from aioresponses import aioresponses

from app.providers.jmap import JMAPProvider, JMAP_SESSION_URL


async def test_test_credentials_succeeds_with_valid_token():
    with aioresponses() as m:
        m.get(JMAP_SESSION_URL, payload={
            "apiUrl": "https://api.example.com/jmap/api",
            "primaryAccounts": {"urn:ietf:params:jmap:mail": "acct1"},
            "accounts": {"acct1": {}},
        })
        provider = JMAPProvider(api_token="abc")
        assert await provider.test_credentials() is True


async def test_test_credentials_fails_on_401():
    with aioresponses() as m:
        m.get(JMAP_SESSION_URL, status=401)
        provider = JMAPProvider(api_token="bad")
        assert await provider.test_credentials() is False
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/providers/test_jmap_session.py -v
```

- [ ] **Step 3: Create `app/providers/jmap.py`**

```python
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import aiohttp

from app.providers.base import (
    Mailbox,
    MessageRef,
    MoveResult,
    ScannedMessage,
    SenderQuery,
    SpecialFolder,
)

JMAP_SESSION_URL = "https://api.fastmail.com/jmap/session"
_CAPS = ["urn:ietf:params:jmap:core", "urn:ietf:params:jmap:mail"]


class JMAPProvider:
    def __init__(self, api_token: str, session_url: str = JMAP_SESSION_URL) -> None:
        self.api_token = api_token
        self._session_discovery_url = session_url
        self._api_url: str | None = None
        self._account_id: str | None = None

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_token}"}

    async def _get_session(self, http: aiohttp.ClientSession) -> None:
        async with http.get(self._session_discovery_url, headers=self._headers) as r:
            r.raise_for_status()
            data = await r.json()
        self._api_url = data["apiUrl"]
        primary = data.get("primaryAccounts", {}).get("urn:ietf:params:jmap:mail")
        self._account_id = primary or next(iter(data.get("accounts", {})), None)
        if self._account_id is None:
            raise RuntimeError("JMAP session has no mail account")

    async def test_credentials(self) -> bool:
        try:
            async with aiohttp.ClientSession() as http:
                await self._get_session(http)
            return True
        except Exception:  # noqa: BLE001 - any failure means credentials are unusable
            return False

    # The remaining Protocol methods are stubbed; they will be implemented
    # in subsequent tasks. They raise NotImplementedError for now.
    async def list_mailboxes(self) -> list[Mailbox]:
        raise NotImplementedError

    async def scan_headers(  # type: ignore[override]
        self, since: datetime | None, max_messages: int
    ) -> AsyncIterator[ScannedMessage]:
        raise NotImplementedError
        yield  # pragma: no cover - keeps type-checker happy

    async def fetch_snippet(self, ref: MessageRef) -> str:
        raise NotImplementedError

    async def fetch_body(self, ref: MessageRef) -> bytes:
        raise NotImplementedError

    async def search_by_sender(  # type: ignore[override]
        self, query: SenderQuery, mailboxes: list[str] | None = None
    ) -> AsyncIterator[MessageRef]:
        raise NotImplementedError
        yield  # pragma: no cover

    async def move_messages(
        self, refs: list[MessageRef], destination: SpecialFolder
    ) -> MoveResult:
        raise NotImplementedError
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/providers/test_jmap_session.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add app/providers/jmap.py tests/providers/test_jmap_session.py
git commit -m "feat(provider/jmap): session bootstrap + test_credentials"
```

---

## Task 14: JMAP provider — list mailboxes

**Files:**
- Modify: `app/providers/jmap.py`
- Create: `tests/providers/test_jmap_mailboxes.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/providers/test_jmap_mailboxes.py
from aioresponses import aioresponses

from app.providers.base import SpecialFolder
from app.providers.jmap import JMAP_SESSION_URL, JMAPProvider


async def test_list_mailboxes_maps_roles():
    with aioresponses() as m:
        m.get(JMAP_SESSION_URL, payload={
            "apiUrl": "https://api.example.com/jmap/api",
            "primaryAccounts": {"urn:ietf:params:jmap:mail": "acct1"},
            "accounts": {"acct1": {}},
        })
        m.post("https://api.example.com/jmap/api", payload={
            "methodResponses": [[
                "Mailbox/get", {
                    "list": [
                        {"id": "mb1", "name": "INBOX", "role": "inbox"},
                        {"id": "mb2", "name": "Archive", "role": "archive"},
                        {"id": "mb3", "name": "Trash", "role": "trash"},
                        {"id": "mb4", "name": "Custom", "role": None},
                    ]
                },
                "0",
            ]]
        })

        provider = JMAPProvider(api_token="abc")
        boxes = await provider.list_mailboxes()
        roles = {b.name: b.role for b in boxes}
        assert roles["INBOX"] == SpecialFolder.inbox
        assert roles["Archive"] == SpecialFolder.archive
        assert roles["Trash"] == SpecialFolder.trash
        assert roles["Custom"] is None
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/providers/test_jmap_mailboxes.py -v
```

Expected: NotImplementedError.

- [ ] **Step 3: Replace `list_mailboxes` in `app/providers/jmap.py`**

Add a helper at module top (below `_CAPS`):

```python
_ROLE_MAP = {
    "inbox": SpecialFolder.inbox,
    "archive": SpecialFolder.archive,
    "trash": SpecialFolder.trash,
    "sent": SpecialFolder.sent,
    "drafts": SpecialFolder.drafts,
    "junk": SpecialFolder.junk,
}
```

Then replace the `list_mailboxes` stub with:

```python
async def list_mailboxes(self) -> list[Mailbox]:
    async with aiohttp.ClientSession() as http:
        if self._api_url is None:
            await self._get_session(http)
        payload = {
            "using": _CAPS,
            "methodCalls": [[
                "Mailbox/get",
                {"accountId": self._account_id},
                "0",
            ]],
        }
        async with http.post(self._api_url, json=payload, headers=self._headers) as r:
            r.raise_for_status()
            data = await r.json()

    raw = data["methodResponses"][0][1].get("list", [])
    return [
        Mailbox(
            id=m["id"],
            name=m.get("name", ""),
            role=_ROLE_MAP.get((m.get("role") or "").lower()),
        )
        for m in raw
    ]
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/providers/test_jmap_mailboxes.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add app/providers/jmap.py tests/providers/test_jmap_mailboxes.py
git commit -m "feat(provider/jmap): list_mailboxes with role mapping"
```

---

## Task 15: JMAP provider — scan_headers

**Files:**
- Modify: `app/providers/jmap.py`
- Create: `tests/providers/test_jmap_scan.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/providers/test_jmap_scan.py
from datetime import datetime, timezone

from aioresponses import aioresponses

from app.providers.jmap import JMAP_SESSION_URL, JMAPProvider


async def test_scan_headers_yields_only_messages_with_list_unsubscribe():
    with aioresponses() as m:
        m.get(JMAP_SESSION_URL, payload={
            "apiUrl": "https://api.example.com/jmap/api",
            "primaryAccounts": {"urn:ietf:params:jmap:mail": "acct1"},
            "accounts": {"acct1": {}},
        })
        # Mailbox/query (inbox lookup) -> Email/query -> Email/get
        m.post("https://api.example.com/jmap/api", payload={
            "methodResponses": [
                ["Mailbox/query", {"ids": ["mb_inbox"]}, "0"],
                ["Email/query", {"ids": ["e1", "e2"]}, "1"],
                ["Email/get", {"list": [
                    {
                        "id": "e1",
                        "mailboxIds": {"mb_inbox": True},
                        "from": [{"email": "News@Example.com", "name": "News"}],
                        "subject": "Hi",
                        "receivedAt": "2026-04-01T10:00:00Z",
                        "header:List-Id:asText": "<news.example.com>",
                        "header:List-Unsubscribe:asText": "<https://example.com/u/1>",
                        "header:List-Unsubscribe-Post:asText": "List-Unsubscribe=One-Click",
                    },
                    {
                        "id": "e2",
                        "mailboxIds": {"mb_inbox": True},
                        "from": [{"email": "joe@friend.com", "name": "Joe"}],
                        "subject": "Lunch",
                        "receivedAt": "2026-04-02T11:00:00Z",
                        "header:List-Id:asText": None,
                        "header:List-Unsubscribe:asText": None,
                        "header:List-Unsubscribe-Post:asText": None,
                    },
                ]}, "2"],
            ]
        })

        provider = JMAPProvider(api_token="abc")
        results = [r async for r in provider.scan_headers(since=None, max_messages=10)]

    assert len(results) == 1
    only = results[0]
    assert only.from_email == "news@example.com"
    assert only.from_domain == "example.com"
    assert only.list_unsubscribe == "<https://example.com/u/1>"
    assert only.list_unsubscribe_post == "List-Unsubscribe=One-Click"
    assert only.received_at == datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc)
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/providers/test_jmap_scan.py -v
```

- [ ] **Step 3: Replace `scan_headers` in `app/providers/jmap.py`**

```python
async def scan_headers(  # type: ignore[override]
    self, since: datetime | None, max_messages: int
) -> AsyncIterator[ScannedMessage]:
    async with aiohttp.ClientSession() as http:
        if self._api_url is None:
            await self._get_session(http)

        # Find inbox id, query its emails, fetch headers — chained.
        query_filter: dict = {"inMailbox": "#inbox"}
        if since is not None:
            query_filter["after"] = since.isoformat().replace("+00:00", "Z")

        payload = {
            "using": _CAPS,
            "methodCalls": [
                [
                    "Mailbox/query",
                    {"accountId": self._account_id, "filter": {"role": "inbox"}},
                    "0",
                ],
                [
                    "Email/query",
                    {
                        "accountId": self._account_id,
                        "filter": {
                            "inMailbox": {"resultOf": "0", "name": "Mailbox/query", "path": "/ids/0"}
                        },
                        "sort": [{"property": "receivedAt", "isAscending": False}],
                        "limit": max_messages,
                    },
                    "1",
                ],
                [
                    "Email/get",
                    {
                        "accountId": self._account_id,
                        "#ids": {"resultOf": "1", "name": "Email/query", "path": "/ids"},
                        "properties": [
                            "id",
                            "mailboxIds",
                            "from",
                            "subject",
                            "receivedAt",
                            "header:List-Id:asText",
                            "header:List-Unsubscribe:asText",
                            "header:List-Unsubscribe-Post:asText",
                        ],
                    },
                    "2",
                ],
            ],
        }
        async with http.post(self._api_url, json=payload, headers=self._headers) as r:
            r.raise_for_status()
            data = await r.json()

    emails = data["methodResponses"][-1][1].get("list", [])
    for em in emails:
        unsub = em.get("header:List-Unsubscribe:asText")
        if not unsub:
            continue
        from_list = em.get("from") or []
        if not from_list:
            continue
        from_email = (from_list[0].get("email") or "").strip().lower()
        if not from_email or "@" not in from_email:
            continue
        domain = from_email.rsplit("@", 1)[1]

        received_raw = em.get("receivedAt") or ""
        try:
            received = datetime.fromisoformat(received_raw.replace("Z", "+00:00")).astimezone(
                timezone.utc
            )
        except ValueError:
            continue

        # Pick the first INBOX-ish mailbox id; preserve as ref.
        mailbox_ids = list((em.get("mailboxIds") or {}).keys())
        mailbox = mailbox_ids[0] if mailbox_ids else ""

        yield ScannedMessage(
            ref=MessageRef(provider_uid=em["id"], mailbox=mailbox),
            from_email=from_email,
            from_domain=domain,
            display_name=(from_list[0].get("name") or "").strip(),
            subject=em.get("subject") or "",
            received_at=received,
            list_id=em.get("header:List-Id:asText"),
            list_unsubscribe=unsub,
            list_unsubscribe_post=em.get("header:List-Unsubscribe-Post:asText"),
        )
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/providers/test_jmap_scan.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add app/providers/jmap.py tests/providers/test_jmap_scan.py
git commit -m "feat(provider/jmap): scan_headers via chained Mailbox/Email queries"
```

---

## Task 16: IMAP provider — credentials test + list mailboxes

**Files:**
- Create: `app/providers/imap.py`, `tests/providers/test_imap_basic.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/providers/test_imap_basic.py
from unittest.mock import MagicMock, patch

from app.providers.base import SpecialFolder
from app.providers.imap import IMAPProvider


def _fake_imap(login_ok: bool = True, list_lines: list[bytes] | None = None) -> MagicMock:
    conn = MagicMock()
    if login_ok:
        conn.login.return_value = ("OK", [b"Logged in"])
    else:
        conn.login.side_effect = Exception("auth failed")
    conn.list.return_value = (
        "OK",
        list_lines or [
            b'(\\HasNoChildren) "/" "INBOX"',
            b'(\\HasNoChildren \\Archive) "/" "Archive"',
            b'(\\HasNoChildren \\Trash) "/" "Trash"',
        ],
    )
    return conn


async def test_test_credentials_returns_true_on_login():
    conn = _fake_imap(login_ok=True)
    with patch("app.providers.imap.imaplib.IMAP4_SSL", return_value=conn):
        provider = IMAPProvider("imap.example.com", 993, "u", "p")
        assert await provider.test_credentials() is True


async def test_test_credentials_returns_false_on_failure():
    conn = _fake_imap(login_ok=False)
    with patch("app.providers.imap.imaplib.IMAP4_SSL", return_value=conn):
        provider = IMAPProvider("imap.example.com", 993, "u", "p")
        assert await provider.test_credentials() is False


async def test_list_mailboxes_maps_special_use_flags():
    conn = _fake_imap()
    with patch("app.providers.imap.imaplib.IMAP4_SSL", return_value=conn):
        provider = IMAPProvider("imap.example.com", 993, "u", "p")
        boxes = await provider.list_mailboxes()
    by_name = {b.name: b.role for b in boxes}
    assert by_name["INBOX"] == SpecialFolder.inbox
    assert by_name["Archive"] == SpecialFolder.archive
    assert by_name["Trash"] == SpecialFolder.trash
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/providers/test_imap_basic.py -v
```

- [ ] **Step 3: Create `app/providers/imap.py`**

```python
import asyncio
import imaplib
import re
from collections.abc import AsyncIterator
from datetime import datetime

from app.providers.base import (
    Mailbox,
    MessageRef,
    MoveResult,
    ScannedMessage,
    SenderQuery,
    SpecialFolder,
)

_LIST_RE = re.compile(rb'\((?P<flags>[^)]*)\) "(?P<sep>[^"]*)" "?(?P<name>[^"\r\n]+)"?')

_FLAG_TO_ROLE = {
    b"\\inbox": SpecialFolder.inbox,
    b"\\archive": SpecialFolder.archive,
    b"\\trash": SpecialFolder.trash,
    b"\\sent": SpecialFolder.sent,
    b"\\drafts": SpecialFolder.drafts,
    b"\\junk": SpecialFolder.junk,
}


def _decode_role(flags: bytes, name: str) -> SpecialFolder | None:
    flags_lc = flags.lower()
    for tag, role in _FLAG_TO_ROLE.items():
        if tag in flags_lc:
            return role
    if name.upper() == "INBOX":
        return SpecialFolder.inbox
    return None


class IMAPProvider:
    def __init__(self, host: str, port: int, username: str, password: str) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password

    # -- sync helpers run via asyncio.to_thread --------------------------------

    def _connect(self) -> imaplib.IMAP4_SSL:
        conn = imaplib.IMAP4_SSL(self.host, self.port)
        conn.login(self.username, self.password)
        return conn

    def _login_only_sync(self) -> bool:
        try:
            conn = self._connect()
        except Exception:  # noqa: BLE001 - any failure means credentials don't work
            return False
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass
        return True

    def _list_mailboxes_sync(self) -> list[Mailbox]:
        conn = self._connect()
        try:
            status, lines = conn.list()
            if status != "OK" or lines is None:
                return []
            result: list[Mailbox] = []
            for raw in lines:
                if raw is None:
                    continue
                m = _LIST_RE.match(raw)
                if not m:
                    continue
                name = m.group("name").decode("utf-8", errors="replace")
                flags = m.group("flags")
                result.append(Mailbox(id=name, name=name, role=_decode_role(flags, name)))
            return result
        finally:
            conn.logout()

    # -- Protocol API ----------------------------------------------------------

    async def test_credentials(self) -> bool:
        return await asyncio.to_thread(self._login_only_sync)

    async def list_mailboxes(self) -> list[Mailbox]:
        return await asyncio.to_thread(self._list_mailboxes_sync)

    async def scan_headers(  # type: ignore[override]
        self, since: datetime | None, max_messages: int
    ) -> AsyncIterator[ScannedMessage]:
        raise NotImplementedError
        yield  # pragma: no cover

    async def fetch_snippet(self, ref: MessageRef) -> str:
        raise NotImplementedError

    async def fetch_body(self, ref: MessageRef) -> bytes:
        raise NotImplementedError

    async def search_by_sender(  # type: ignore[override]
        self, query: SenderQuery, mailboxes: list[str] | None = None
    ) -> AsyncIterator[MessageRef]:
        raise NotImplementedError
        yield  # pragma: no cover

    async def move_messages(
        self, refs: list[MessageRef], destination: SpecialFolder
    ) -> MoveResult:
        raise NotImplementedError
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/providers/test_imap_basic.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add app/providers/imap.py tests/providers/test_imap_basic.py
git commit -m "feat(provider/imap): test_credentials + list_mailboxes"
```

---

## Task 17: IMAP provider — scan_headers

**Files:**
- Modify: `app/providers/imap.py`
- Create: `tests/providers/test_imap_scan.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/providers/test_imap_scan.py
from email.utils import format_datetime
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.providers.imap import IMAPProvider


def _build_header_blob(
    *,
    from_addr: str,
    subject: str,
    date: datetime,
    list_id: str | None,
    list_unsubscribe: str | None,
    list_unsubscribe_post: str | None,
) -> bytes:
    parts = [
        f"From: {from_addr}",
        f"Subject: {subject}",
        f"Date: {format_datetime(date)}",
    ]
    if list_id:
        parts.append(f"List-Id: {list_id}")
    if list_unsubscribe:
        parts.append(f"List-Unsubscribe: {list_unsubscribe}")
    if list_unsubscribe_post:
        parts.append(f"List-Unsubscribe-Post: {list_unsubscribe_post}")
    return ("\r\n".join(parts) + "\r\n\r\n").encode("utf-8")


def _scan_conn(messages: list[tuple[bytes, bytes]]) -> MagicMock:
    """messages = [(uid, header_bytes), ...] in chronological order."""
    conn = MagicMock()
    conn.login.return_value = ("OK", [b"ok"])
    conn.select.return_value = ("OK", [str(len(messages)).encode()])

    uid_list = b" ".join(uid for uid, _ in messages)
    conn.uid.side_effect = _make_uid_handler(messages, uid_list)
    return conn


def _make_uid_handler(messages, uid_list):
    by_uid = {uid: hdr for uid, hdr in messages}

    def handler(*args):
        # uid("SEARCH", None, "ALL") -> ("OK", [uids_space_separated])
        if args[0] == "SEARCH":
            return ("OK", [uid_list])
        # uid("FETCH", "1,2,3", "(BODY.PEEK[HEADER.FIELDS (...)])")
        if args[0] == "FETCH":
            requested = args[1].decode() if isinstance(args[1], bytes) else args[1]
            uids = [u.strip() for u in requested.split(",")]
            data = []
            for u in uids:
                hdr = by_uid.get(u.encode())
                if hdr is None:
                    continue
                data.append((f"{u} (UID {u} BODY[HEADER.FIELDS ...] {{0}}".encode(), hdr))
                data.append(b")")
            return ("OK", data)
        return ("BAD", [])

    return handler


async def test_scan_yields_only_unsubscribe_messages():
    msgs = [
        (b"1", _build_header_blob(
            from_addr='"News" <news@Example.com>',
            subject="Hello",
            date=datetime(2026, 4, 1, 10, tzinfo=timezone.utc),
            list_id="<news.example.com>",
            list_unsubscribe="<https://example.com/u/1>, <mailto:u@example.com>",
            list_unsubscribe_post="List-Unsubscribe=One-Click",
        )),
        (b"2", _build_header_blob(
            from_addr="joe@friend.com",
            subject="Lunch",
            date=datetime(2026, 4, 2, 12, tzinfo=timezone.utc),
            list_id=None,
            list_unsubscribe=None,
            list_unsubscribe_post=None,
        )),
    ]
    conn = _scan_conn(msgs)
    with patch("app.providers.imap.imaplib.IMAP4_SSL", return_value=conn):
        provider = IMAPProvider("imap.example.com", 993, "u", "p")
        results = [r async for r in provider.scan_headers(since=None, max_messages=10)]

    assert len(results) == 1
    only = results[0]
    assert only.from_email == "news@example.com"
    assert only.from_domain == "example.com"
    assert only.list_unsubscribe.startswith("<https://example.com/u/1>")
    assert only.list_unsubscribe_post == "List-Unsubscribe=One-Click"
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/providers/test_imap_scan.py -v
```

- [ ] **Step 3: Replace `scan_headers` and add helpers in `app/providers/imap.py`**

Add at top with other imports:

```python
import email
import email.header
import email.utils
from datetime import timezone
```

Add a helper at module level:

```python
_HEADER_FIELDS = (
    "FROM DATE SUBJECT MESSAGE-ID LIST-ID LIST-UNSUBSCRIBE LIST-UNSUBSCRIBE-POST"
)


def _decode_header(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    parts = email.header.decode_header(value)
    out = []
    for chunk, charset in parts:
        if isinstance(chunk, bytes):
            out.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(chunk)
    return " ".join(out).strip()


def _parse_from(raw: str) -> tuple[str, str]:
    decoded = _decode_header(raw)
    name, addr = email.utils.parseaddr(decoded)
    return name.strip().strip('"'), addr.strip().lower()
```

Then replace the `scan_headers` stub with:

```python
def _scan_sync(self, since: datetime | None, max_messages: int) -> list[ScannedMessage]:
    conn = self._connect()
    try:
        conn.select("INBOX", readonly=True)
        criteria = "ALL"
        if since is not None:
            since_str = since.strftime("%d-%b-%Y")
            criteria = f"SINCE {since_str}"
        status, data = conn.uid("SEARCH", None, criteria)
        if status != "OK" or not data or not data[0]:
            return []
        uids = data[0].split()
        if not uids:
            return []
        uids = uids[-max_messages:]

        # batch fetch in chunks of 200 to keep the IMAP command line reasonable
        results: list[ScannedMessage] = []
        for chunk_start in range(0, len(uids), 200):
            chunk = uids[chunk_start:chunk_start + 200]
            uid_set = b",".join(chunk).decode()
            status, fetch_data = conn.uid(
                "FETCH",
                uid_set,
                f"(BODY.PEEK[HEADER.FIELDS ({_HEADER_FIELDS})])",
            )
            if status != "OK" or not fetch_data:
                continue
            for entry in fetch_data:
                if not isinstance(entry, tuple) or len(entry) < 2:
                    continue
                meta, raw_headers = entry[0], entry[1]
                if not isinstance(raw_headers, (bytes, bytearray)):
                    continue
                msg = email.message_from_bytes(bytes(raw_headers))
                list_unsub = msg.get("List-Unsubscribe")
                if not list_unsub:
                    continue
                _, sender_email = _parse_from(msg.get("From", ""))
                if not sender_email or "@" not in sender_email:
                    continue
                domain = sender_email.rsplit("@", 1)[1]

                date_raw = msg.get("Date", "")
                try:
                    received = email.utils.parsedate_to_datetime(date_raw).astimezone(timezone.utc)
                except (TypeError, ValueError):
                    continue

                # extract uid from meta — `b"<uid> (UID <uid> ..."`
                uid_match = re.match(rb"\s*(\d+)\s+\(", meta if isinstance(meta, (bytes, bytearray)) else b"")
                provider_uid = uid_match.group(1).decode() if uid_match else ""

                display_name, _ = _parse_from(msg.get("From", ""))

                results.append(ScannedMessage(
                    ref=MessageRef(provider_uid=provider_uid, mailbox="INBOX"),
                    from_email=sender_email,
                    from_domain=domain,
                    display_name=display_name,
                    subject=_decode_header(msg.get("Subject", "")),
                    received_at=received,
                    list_id=_decode_header(msg.get("List-Id")) or None,
                    list_unsubscribe=_decode_header(list_unsub) or None,
                    list_unsubscribe_post=_decode_header(msg.get("List-Unsubscribe-Post")) or None,
                ))
        return results
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass


async def scan_headers(  # type: ignore[override]
    self, since: datetime | None, max_messages: int
) -> AsyncIterator[ScannedMessage]:
    results = await asyncio.to_thread(self._scan_sync, since, max_messages)
    for r in results:
        yield r
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/providers/test_imap_scan.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Run all tests**

```bash
uv run pytest -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add app/providers/imap.py tests/providers/test_imap_scan.py
git commit -m "feat(provider/imap): scan_headers via batched UID FETCH"
```

---

## Task 18: Job runner (in-process, async)

**Files:**
- Create: `app/jobs/__init__.py` (empty), `app/jobs/runner.py`, `tests/jobs/__init__.py`, `tests/jobs/test_runner.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/jobs/test_runner.py
import asyncio

import pytest

from app.jobs.runner import JobContext, JobRunner
from app.models.account import Account, ProviderType
from app.models.job import Job, JobStatus, JobType


def _make_account(db) -> Account:
    a = Account(name="A", email="a@x.com",
                provider=ProviderType.jmap, credential_encrypted="x")
    db.add(a)
    db.commit()
    return a


async def test_runner_runs_job_to_success(db_session, settings):
    account = _make_account(db_session)
    job_id = JobRunner.create_job(
        db_session,
        type=JobType.scan,
        account_id=account.id,
        params={"hello": "world"},
    )

    async def work(ctx: JobContext) -> dict:
        ctx.set_total(3)
        for i in range(3):
            await asyncio.sleep(0)
            ctx.advance(1)
        return {"done": True}

    runner = JobRunner(database_url=settings.database_url)
    await runner.run(job_id, work)

    db_session.expire_all()
    job = db_session.get(Job, job_id)
    assert job.status == JobStatus.success
    assert job.progress_done == 3
    assert job.progress_total == 3
    assert job.result_json == '{"done": true}'


async def test_runner_marks_job_failed_on_exception(db_session, settings):
    account = _make_account(db_session)
    job_id = JobRunner.create_job(
        db_session, type=JobType.scan, account_id=account.id, params=None,
    )

    async def boom(ctx: JobContext) -> dict:
        raise RuntimeError("explode")

    runner = JobRunner(database_url=settings.database_url)
    await runner.run(job_id, boom)

    db_session.expire_all()
    job = db_session.get(Job, job_id)
    assert job.status == JobStatus.failed
    assert "explode" in (job.error or "")


def test_recover_running_jobs_marks_them_failed(db_session, settings):
    account = _make_account(db_session)
    job = Job(account_id=account.id, type=JobType.scan, status=JobStatus.running)
    db_session.add(job)
    db_session.commit()

    JobRunner.recover_orphans(database_url=settings.database_url)

    db_session.expire_all()
    refreshed = db_session.get(Job, job.id)
    assert refreshed.status == JobStatus.failed
    assert "interrupted by restart" in (refreshed.error or "")
```

- [ ] **Step 2: Create `tests/jobs/__init__.py`** (empty)

- [ ] **Step 3: Run to verify failure**

```bash
uv run pytest tests/jobs/test_runner.py -v
```

- [ ] **Step 4: Create `app/jobs/__init__.py`** (empty)

- [ ] **Step 5: Create `app/jobs/runner.py`**

```python
import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db import get_session_factory
from app.models.job import Job, JobStatus, JobType


class JobContext:
    def __init__(self, job_id: int, session_factory) -> None:
        self.job_id = job_id
        self._session_factory = session_factory

    def set_total(self, total: int) -> None:
        with self._session_factory() as s:
            s.execute(update(Job).where(Job.id == self.job_id).values(progress_total=total))
            s.commit()

    def advance(self, delta: int = 1) -> None:
        with self._session_factory() as s:
            job = s.get(Job, self.job_id)
            if job is None:
                return
            job.progress_done = job.progress_done + delta
            s.commit()


JobWork = Callable[[JobContext], Awaitable[dict | None]]


class JobRunner:
    def __init__(self, database_url: str | None = None) -> None:
        self._session_factory = get_session_factory(database_url)
        self._semaphore = asyncio.Semaphore(2)

    @staticmethod
    def create_job(
        session: Session,
        *,
        type: JobType,
        account_id: int | None,
        params: dict | None,
    ) -> int:
        job = Job(
            type=type,
            account_id=account_id,
            status=JobStatus.queued,
            params_json=json.dumps(params) if params is not None else None,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        return job.id

    @staticmethod
    def recover_orphans(database_url: str | None = None) -> None:
        sf = get_session_factory(database_url)
        with sf() as s:
            s.execute(
                update(Job)
                .where(Job.status == JobStatus.running)
                .values(
                    status=JobStatus.failed,
                    error="interrupted by restart",
                    finished_at=datetime.now(timezone.utc),
                )
            )
            s.commit()

    async def run(self, job_id: int, work: JobWork) -> None:
        async with self._semaphore:
            with self._session_factory() as s:
                s.execute(
                    update(Job).where(Job.id == job_id).values(
                        status=JobStatus.running,
                        started_at=datetime.now(timezone.utc),
                    )
                )
                s.commit()

            ctx = JobContext(job_id, self._session_factory)
            try:
                result = await work(ctx)
            except Exception as exc:  # noqa: BLE001
                with self._session_factory() as s:
                    s.execute(
                        update(Job).where(Job.id == job_id).values(
                            status=JobStatus.failed,
                            error=str(exc),
                            finished_at=datetime.now(timezone.utc),
                        )
                    )
                    s.commit()
                return

            with self._session_factory() as s:
                s.execute(
                    update(Job).where(Job.id == job_id).values(
                        status=JobStatus.success,
                        result_json=json.dumps(result) if result is not None else None,
                        finished_at=datetime.now(timezone.utc),
                    )
                )
                s.commit()

    def schedule(self, job_id: int, work: JobWork) -> asyncio.Task:
        return asyncio.create_task(self.run(job_id, work))
```

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/jobs/test_runner.py -v
```

Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add app/jobs/ tests/jobs/
git commit -m "feat(jobs): in-process runner with progress + crash recovery"
```

---

## Task 19: Scan job (provider → DB)

**Files:**
- Create: `app/jobs/scan.py`, `tests/jobs/test_scan_job.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/jobs/test_scan_job.py
from datetime import datetime, timezone

from app.jobs.runner import JobContext, JobRunner
from app.jobs.scan import build_scan_work
from app.models.account import Account, ProviderType
from app.models.job import Job, JobStatus, JobType
from app.models.message import Message
from app.models.sender import Sender, SenderAlias
from tests.fakes.mail_provider import FakeMailProvider, FakeMessage


def _account(db) -> Account:
    a = Account(name="A", email="a@x.com",
                provider=ProviderType.jmap, credential_encrypted="x")
    db.add(a)
    db.commit()
    return a


async def test_scan_job_creates_senders_and_messages(db_session, settings):
    account = _account(db_session)
    provider = FakeMailProvider(messages=[
        FakeMessage(
            uid="1", mailbox="INBOX",
            from_email="news@example.com", display_name="News",
            subject="Hi", received_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            list_id="<news.example.com>",
            list_unsubscribe="<https://example.com/u/1>",
            list_unsubscribe_post="List-Unsubscribe=One-Click",
            body=b"x", snippet="x",
        ),
        FakeMessage(
            uid="2", mailbox="INBOX",
            from_email="news2@example.com", display_name="News2",
            subject="Hi2", received_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
            list_id="<news.example.com>",
            list_unsubscribe="<https://example.com/u/2>",
            list_unsubscribe_post=None,
            body=b"x", snippet="x",
        ),
    ])

    job_id = JobRunner.create_job(
        db_session, type=JobType.scan, account_id=account.id,
        params={"max_messages": 50},
    )

    runner = JobRunner(database_url=settings.database_url)
    work = build_scan_work(account_id=account.id, provider=provider, max_messages=50)
    await runner.run(job_id, work)

    db_session.expire_all()
    job = db_session.get(Job, job_id)
    assert job.status == JobStatus.success
    assert job.progress_done == 2

    senders = db_session.query(Sender).filter_by(account_id=account.id).all()
    assert len(senders) == 1
    sender = senders[0]
    assert sender.group_key == "news.example.com"
    assert sender.unsubscribe_one_click_post is True
    assert sender.email_count == 2

    aliases = db_session.query(SenderAlias).filter_by(sender_id=sender.id).all()
    assert {a.from_email for a in aliases} == {"news@example.com", "news2@example.com"}

    messages = db_session.query(Message).filter_by(account_id=account.id).all()
    assert {m.provider_uid for m in messages} == {"1", "2"}


async def test_scan_job_is_idempotent_on_rerun(db_session, settings):
    account = _account(db_session)
    msg = FakeMessage(
        uid="1", mailbox="INBOX",
        from_email="news@example.com", display_name="News",
        subject="Hi", received_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        list_id="<news.example.com>",
        list_unsubscribe="<https://example.com/u/1>",
        list_unsubscribe_post=None,
        body=b"x", snippet="x",
    )
    provider = FakeMailProvider(messages=[msg])
    runner = JobRunner(database_url=settings.database_url)

    for _ in range(2):
        job_id = JobRunner.create_job(
            db_session, type=JobType.scan, account_id=account.id, params=None,
        )
        await runner.run(
            job_id,
            build_scan_work(account_id=account.id, provider=provider, max_messages=50),
        )

    db_session.expire_all()
    senders = db_session.query(Sender).filter_by(account_id=account.id).all()
    assert len(senders) == 1
    assert senders[0].email_count == 1  # not doubled
    messages = db_session.query(Message).filter_by(account_id=account.id).all()
    assert len(messages) == 1
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/jobs/test_scan_job.py -v
```

- [ ] **Step 3: Create `app/jobs/scan.py`**

```python
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db import get_session_factory
from app.jobs.runner import JobContext
from app.models.account import Account
from app.models.message import Message
from app.models.sender import Sender, SenderAlias
from app.providers.base import ScannedMessage
from app.services.grouping import compute_group_key, extract_domain
from app.services.unsubscribe import parse_unsubscribe_methods


async def _collect_scan(
    provider, since: datetime | None, max_messages: int
) -> list[ScannedMessage]:
    out: list[ScannedMessage] = []
    async for msg in provider.scan_headers(since=since, max_messages=max_messages):
        out.append(msg)
    return out


def build_scan_work(*, account_id: int, provider, max_messages: int):
    """Return a JobWork closure that runs a scan for the given account."""

    session_factory = get_session_factory()

    async def work(ctx: JobContext) -> dict:
        # Read since-timestamp from the account row.
        with session_factory() as s:
            account = s.get(Account, account_id)
            since = account.last_incremental_scan_at if account else None

        scanned = await _collect_scan(provider, since=since, max_messages=max_messages)
        ctx.set_total(len(scanned))

        # Group scanned messages by group_key for efficient upsert.
        by_group: dict[str, list[ScannedMessage]] = {}
        for sm in scanned:
            key = compute_group_key(sm.list_id or "", sm.from_email)
            by_group.setdefault(key, []).append(sm)

        for group_key, group_msgs in by_group.items():
            with session_factory() as s:
                _persist_group(s, account_id, group_key, group_msgs)
                s.commit()
            ctx.advance(len(group_msgs))

        # Update account scan timestamp.
        with session_factory() as s:
            now = datetime.now(timezone.utc)
            s.execute(
                update(Account).where(Account.id == account_id).values(
                    last_full_scan_at=now,
                    last_incremental_scan_at=now,
                )
            )
            s.commit()

        return {"messages_seen": len(scanned), "groups": len(by_group)}

    return work


def _persist_group(
    session, account_id: int, group_key: str, msgs: list[ScannedMessage]
) -> None:
    representative = msgs[0]
    methods = parse_unsubscribe_methods(
        representative.list_unsubscribe, representative.list_unsubscribe_post
    )
    domain = representative.from_domain or extract_domain(representative.from_email)

    sender = session.scalar(
        select(Sender).where(
            Sender.account_id == account_id, Sender.group_key == group_key
        )
    )
    if sender is None:
        sender = Sender(
            account_id=account_id,
            group_key=group_key,
            from_email=representative.from_email,
            from_domain=domain,
            list_id=representative.list_id,
            display_name=representative.display_name,
            unsubscribe_http=methods.http_url,
            unsubscribe_mailto=methods.mailto_url,
            unsubscribe_one_click_post=methods.one_click,
        )
        session.add(sender)
        session.flush()
    else:
        if methods.http_url:
            sender.unsubscribe_http = methods.http_url
        if methods.mailto_url:
            sender.unsubscribe_mailto = methods.mailto_url
        if methods.one_click:
            sender.unsubscribe_one_click_post = True
        if representative.display_name and not sender.display_name:
            sender.display_name = representative.display_name

    # Upsert messages and aliases per scanned msg.
    for sm in msgs:
        message_existing = session.scalar(
            select(Message).where(
                Message.account_id == account_id,
                Message.provider_uid == sm.ref.provider_uid,
                Message.mailbox == sm.ref.mailbox,
            )
        )
        if message_existing is None:
            session.add(
                Message(
                    account_id=account_id,
                    sender_id=sender.id,
                    provider_uid=sm.ref.provider_uid,
                    mailbox=sm.ref.mailbox,
                    subject=sm.subject,
                    received_at=sm.received_at,
                )
            )
        else:
            # keep subject/received_at fresh
            message_existing.subject = sm.subject
            message_existing.received_at = sm.received_at

        alias = session.scalar(
            select(SenderAlias).where(
                SenderAlias.sender_id == sender.id,
                SenderAlias.from_email == sm.from_email,
            )
        )
        if alias is None:
            session.add(
                SenderAlias(
                    sender_id=sender.id,
                    from_email=sm.from_email,
                    from_domain=sm.from_domain or extract_domain(sm.from_email),
                    email_count=1,
                )
            )
        # We do not bump alias.email_count on rerun; we recompute totals next.

    # Recompute totals from Message rows (idempotent).
    sender.email_count = session.scalar(
        select(Message)
        .where(Message.sender_id == sender.id)
        .with_only_columns(Message.id)
        .order_by(None)
        .add_columns()
        # Use a count via SQL to avoid loading all rows:
    ) or 0  # placeholder; replaced below via proper count

    from sqlalchemy import func
    sender.email_count = session.scalar(
        select(func.count(Message.id)).where(Message.sender_id == sender.id)
    ) or 0

    sender.first_seen_at = session.scalar(
        select(func.min(Message.received_at)).where(Message.sender_id == sender.id)
    )
    sender.last_seen_at = session.scalar(
        select(func.max(Message.received_at)).where(Message.sender_id == sender.id)
    )

    # Refresh per-alias counts from messages joined on from_email through scanned data.
    # Aliases store totals per from_email observed; recount from messages by joining
    # via the original ScannedMessage list (we don't store from_email on Message).
    # Simpler: bump counts by occurrences in this batch only.
    alias_counts: dict[str, int] = {}
    for sm in msgs:
        alias_counts[sm.from_email] = alias_counts.get(sm.from_email, 0) + 1
    for alias_email, _count in alias_counts.items():
        alias_row = session.scalar(
            select(SenderAlias).where(
                SenderAlias.sender_id == sender.id,
                SenderAlias.from_email == alias_email,
            )
        )
        if alias_row is None:
            continue
        # Recompute alias count by counting Message rows whose provider_uid was
        # produced by a scanned message with this from_email — we don't have
        # that link in the DB, so we approximate by occurrences in this batch.
        # On rerun the same batch produces the same count; idempotent enough.
        alias_row.email_count = max(alias_row.email_count, alias_counts[alias_email])
```

> Note for the implementer: the alias-count tracking is a known
> approximation (we do not persist the alias→message link). It is
> idempotent (same scan produces same count) and good enough for the
> "show which addresses belong to this group" UI. A proper alias→message
> FK can be added in a later iteration if needed.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/jobs/test_scan_job.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Run all tests**

```bash
uv run pytest -v
```

Expected: everything green.

- [ ] **Step 6: Commit**

```bash
git add app/jobs/scan.py tests/jobs/test_scan_job.py
git commit -m "feat(jobs): scan job that upserts senders, aliases, messages"
```

---

## Task 20: FastAPI app shell + Jinja2 + base template

**Files:**
- Modify: `app/main.py`
- Create: `app/templates/base.html`, `app/templates/_macros.html`, `app/templates/pages/index.html`, `static/css/app.css`, `static/vendor/htmx.min.js` (download), `static/vendor/alpine.min.js` (download)

- [ ] **Step 1: Download HTMX 2.x**

```bash
mkdir -p static/vendor
curl -L https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js -o static/vendor/htmx.min.js
curl -L https://unpkg.com/alpinejs@3.14.1/dist/cdn.min.js -o static/vendor/alpine.min.js
```

- [ ] **Step 2: Create `static/css/app.css`**

```css
:root {
  --bg: #fafaf7;
  --fg: #1a1a1a;
  --muted: #666;
  --border: #e2e2dc;
  --accent: #2c5e3f;
  --danger: #b03a2e;
}

* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: var(--bg);
  color: var(--fg);
}
header { padding: 1rem; border-bottom: 1px solid var(--border); background: white; }
header h1 { margin: 0; font-size: 1.25rem; }
nav a { margin-right: 1rem; color: var(--accent); text-decoration: none; }
main { padding: 1rem; max-width: 720px; margin: 0 auto; }
button, .btn {
  background: var(--accent); color: white; border: 0;
  padding: 0.6rem 1rem; border-radius: 6px;
  font-size: 1rem; cursor: pointer;
}
button.secondary { background: white; color: var(--fg); border: 1px solid var(--border); }
.card {
  background: white; border: 1px solid var(--border);
  border-radius: 8px; padding: 1rem; margin-bottom: 0.75rem;
}
.muted { color: var(--muted); font-size: 0.9rem; }
.flex { display: flex; gap: 0.75rem; align-items: center; }
.flex.between { justify-content: space-between; }
input, select {
  width: 100%; padding: 0.6rem; font-size: 1rem;
  border: 1px solid var(--border); border-radius: 6px;
  background: white;
}
form .field { margin-bottom: 0.75rem; }
form label { display: block; font-size: 0.9rem; color: var(--muted); margin-bottom: 0.25rem; }
.progress { height: 6px; background: var(--border); border-radius: 3px; overflow: hidden; }
.progress > div { height: 100%; background: var(--accent); width: 0; transition: width 0.2s; }
@media (min-width: 768px) {
  main { padding: 2rem; }
}
```

- [ ] **Step 3: Create `app/templates/base.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Bulk Unsubscribe{% endblock %}</title>
  <link rel="stylesheet" href="/static/css/app.css">
  <script src="/static/vendor/htmx.min.js" defer></script>
  <script src="/static/vendor/alpine.min.js" defer></script>
</head>
<body>
  <header>
    <div class="flex between">
      <h1>📧 Bulk Unsubscribe</h1>
      <nav>
        <a href="/">Senders</a>
        <a href="/accounts">Accounts</a>
      </nav>
    </div>
  </header>
  <main>
    {% block content %}{% endblock %}
  </main>
</body>
</html>
```

- [ ] **Step 4: Create `app/templates/_macros.html`**

```jinja
{% macro progress_bar(done, total) %}
<div class="progress" aria-label="progress">
  <div style="width: {{ (done / total * 100) if total else 0 }}%"></div>
</div>
<small class="muted">{{ done }} / {{ total }}</small>
{% endmacro %}
```

- [ ] **Step 5: Create `app/templates/pages/index.html`**

```jinja
{% extends "base.html" %}

{% block content %}
<p class="muted">Pick an account to start, or add one first.</p>
<a class="btn" href="/accounts">Manage accounts</a>
{% endblock %}
```

- [ ] **Step 6: Replace `app/main.py`**

```python
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.jobs.runner import JobRunner

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR.parent / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Validate settings & cipher early; refuse to start without a valid Fernet key.
    settings = get_settings()
    from app.services.crypto import CredentialCipher
    CredentialCipher.from_settings(settings)
    JobRunner.recover_orphans()
    yield


app = FastAPI(title="Bulk Unsubscribe", version="0.2.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "pages/index.html", {})
```

- [ ] **Step 7: Add a smoke test for the index page** — `tests/test_pages_smoke.py`

```python
from fastapi.testclient import TestClient

from app.main import app


def test_index_renders():
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "Bulk Unsubscribe" in response.text
```

- [ ] **Step 8: Run tests**

```bash
uv run pytest -v
```

Expected: all green, including the new smoke test.

- [ ] **Step 9: Commit**

```bash
git add app/main.py app/templates/ static/ tests/test_pages_smoke.py
git commit -m "feat(ui): app shell with Jinja2 + HTMX/Alpine vendor + index page"
```

---

## Task 21: Account routes — list + create IMAP/JMAP + delete

**Files:**
- Create: `app/routes/__init__.py` (empty), `app/routes/accounts.py`, `app/templates/pages/accounts.html`, `app/templates/fragments/account_card.html`, `tests/routes/__init__.py`, `tests/routes/test_accounts_routes.py`
- Modify: `app/main.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/routes/test_accounts_routes.py
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.account import Account, ProviderType


def test_list_accounts_empty(db_session):
    with TestClient(app) as client:
        response = client.get("/accounts")
        assert response.status_code == 200
        assert "No accounts yet" in response.text


def test_create_jmap_account_with_valid_token(db_session):
    async def fake_test_credentials(self):
        return True

    with TestClient(app) as client, \
         patch("app.providers.jmap.JMAPProvider.test_credentials", new=fake_test_credentials):
        response = client.post("/accounts/jmap", data={
            "name": "Fastmail",
            "email": "me@fastmail.com",
            "api_token": "secret-token",
        }, follow_redirects=False)
    assert response.status_code in (303, 200)

    account = db_session.query(Account).filter_by(email="me@fastmail.com").one()
    assert account.provider == ProviderType.jmap
    assert account.credential_encrypted != "secret-token"


def test_create_jmap_account_rejects_bad_token(db_session):
    async def fake_test_credentials(self):
        return False

    with TestClient(app) as client, \
         patch("app.providers.jmap.JMAPProvider.test_credentials", new=fake_test_credentials):
        response = client.post("/accounts/jmap", data={
            "name": "Fastmail",
            "email": "me@fastmail.com",
            "api_token": "bad",
        })
    assert response.status_code == 400


def test_delete_account(db_session):
    account = Account(
        name="X", email="x@y.com",
        provider=ProviderType.jmap, credential_encrypted="x",
    )
    db_session.add(account)
    db_session.commit()

    with TestClient(app) as client:
        response = client.post(f"/accounts/{account.id}/delete", follow_redirects=False)
    assert response.status_code in (303, 200)

    assert db_session.get(Account, account.id) is None
```

- [ ] **Step 2: Create `tests/routes/__init__.py`** (empty)

- [ ] **Step 3: Run to verify failure**

```bash
uv run pytest tests/routes/test_accounts_routes.py -v
```

- [ ] **Step 4: Create `app/routes/__init__.py`** (empty)

- [ ] **Step 5: Create `app/routes/accounts.py`**

```python
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.account import Account, ProviderType
from app.providers.imap import IMAPProvider
from app.providers.jmap import JMAPProvider
from app.services.crypto import CredentialCipher

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _templates(request: Request):
    from app.main import templates
    return templates


@router.get("", response_class=HTMLResponse)
def list_accounts(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    accounts = db.execute(select(Account).order_by(Account.created_at.desc())).scalars().all()
    return _templates(request).TemplateResponse(
        request, "pages/accounts.html", {"accounts": accounts}
    )


@router.post("/imap")
async def create_imap_account(
    request: Request,
    name: str = Form(...),
    email: EmailStr = Form(...),
    imap_host: str = Form(...),
    imap_port: int = Form(993),
    imap_username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    provider = IMAPProvider(imap_host, imap_port, imap_username, password)
    if not await provider.test_credentials():
        raise HTTPException(status_code=400, detail="IMAP credentials rejected")
    if db.scalar(select(Account).where(Account.email == email)):
        raise HTTPException(status_code=409, detail="Account with this email exists")
    account = Account(
        name=name, email=email, provider=ProviderType.imap,
        imap_host=imap_host, imap_port=imap_port, imap_username=imap_username,
        credential_encrypted=CredentialCipher.from_settings().encrypt(password),
    )
    db.add(account)
    db.commit()
    return RedirectResponse(url="/accounts", status_code=303)


@router.post("/jmap")
async def create_jmap_account(
    request: Request,
    name: str = Form(...),
    email: EmailStr = Form(...),
    api_token: str = Form(...),
    db: Session = Depends(get_db),
):
    provider = JMAPProvider(api_token=api_token)
    if not await provider.test_credentials():
        raise HTTPException(status_code=400, detail="JMAP token rejected")
    if db.scalar(select(Account).where(Account.email == email)):
        raise HTTPException(status_code=409, detail="Account with this email exists")
    account = Account(
        name=name, email=email, provider=ProviderType.jmap,
        credential_encrypted=CredentialCipher.from_settings().encrypt(api_token),
    )
    db.add(account)
    db.commit()
    return RedirectResponse(url="/accounts", status_code=303)


@router.post("/{account_id}/delete")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404)
    db.delete(account)
    db.commit()
    return RedirectResponse(url="/accounts", status_code=303)
```

- [ ] **Step 6: Create `app/templates/pages/accounts.html`**

```jinja
{% extends "base.html" %}
{% block title %}Accounts — Bulk Unsubscribe{% endblock %}

{% block content %}
<h2>Accounts</h2>

{% if not accounts %}
<p class="muted">No accounts yet. Add one below.</p>
{% else %}
{% for account in accounts %}
  {% include "fragments/account_card.html" %}
{% endfor %}
{% endif %}

<h3>Add IMAP account</h3>
<form method="post" action="/accounts/imap" class="card">
  <div class="field"><label>Display name</label><input name="name" required></div>
  <div class="field"><label>Email</label><input name="email" type="email" required></div>
  <div class="field"><label>IMAP host</label><input name="imap_host" required></div>
  <div class="field"><label>IMAP port</label><input name="imap_port" type="number" value="993"></div>
  <div class="field"><label>IMAP username</label><input name="imap_username" required></div>
  <div class="field"><label>Password / app-password</label><input name="password" type="password" required></div>
  <button type="submit">Add IMAP account</button>
</form>

<h3>Add Fastmail (JMAP) account</h3>
<form method="post" action="/accounts/jmap" class="card">
  <div class="field"><label>Display name</label><input name="name" required></div>
  <div class="field"><label>Email</label><input name="email" type="email" required></div>
  <div class="field"><label>API token</label><input name="api_token" type="password" required></div>
  <button type="submit">Add Fastmail account</button>
</form>
{% endblock %}
```

- [ ] **Step 7: Create `app/templates/fragments/account_card.html`**

```jinja
<div class="card flex between" id="account-{{ account.id }}">
  <div>
    <strong>{{ account.name }}</strong>
    <div class="muted">{{ account.email }} · {{ account.provider.value }}</div>
    {% if account.last_full_scan_at %}
    <div class="muted">Last scan: {{ account.last_full_scan_at.strftime("%Y-%m-%d %H:%M") }}</div>
    {% else %}
    <div class="muted">Never scanned</div>
    {% endif %}
  </div>
  <form method="post" action="/accounts/{{ account.id }}/delete">
    <button type="submit" class="secondary"
            onclick="return confirm('Delete account {{ account.email }}?')">Delete</button>
  </form>
</div>
```

- [ ] **Step 8: Wire the router in `app/main.py`**

Replace the existing `app = FastAPI(...)` block by adding the router import and include after `app.mount(...)`:

```python
from app.routes import accounts as accounts_routes
...
app.include_router(accounts_routes.router)
```

(Place these after the existing `app.mount("/static", ...)` line.)

- [ ] **Step 9: Run tests**

```bash
uv run pytest tests/routes/test_accounts_routes.py -v
```

Expected: 4 passed.

- [ ] **Step 10: Run full suite**

```bash
uv run pytest -v
```

Expected: all green.

- [ ] **Step 11: Commit**

```bash
git add app/routes/ app/main.py app/templates/ tests/routes/
git commit -m "feat(ui/accounts): list, create IMAP+JMAP with credential check, delete"
```

---

## Task 22: Scan trigger route + jobs progress fragment

**Files:**
- Create: `app/routes/jobs.py`, `app/templates/fragments/job_progress.html`
- Modify: `app/main.py`, `app/templates/fragments/account_card.html`
- Create: `tests/routes/test_jobs_routes.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/routes/test_jobs_routes.py
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.account import Account, ProviderType
from app.models.job import Job, JobStatus, JobType


def _account(db) -> Account:
    a = Account(name="A", email="a@x.com",
                provider=ProviderType.jmap, credential_encrypted="x")
    db.add(a)
    db.commit()
    return a


def test_progress_fragment_renders_running_job(db_session):
    account = _account(db_session)
    job = Job(account_id=account.id, type=JobType.scan,
              status=JobStatus.running, progress_total=10, progress_done=3)
    db_session.add(job)
    db_session.commit()

    with TestClient(app) as client:
        response = client.get(f"/jobs/{job.id}/fragment")
        assert response.status_code == 200
        assert "3 / 10" in response.text
        assert "hx-trigger" in response.text  # still polling


def test_progress_fragment_terminal_stops_polling(db_session):
    account = _account(db_session)
    job = Job(account_id=account.id, type=JobType.scan,
              status=JobStatus.success, progress_total=10, progress_done=10)
    db_session.add(job)
    db_session.commit()

    with TestClient(app) as client:
        response = client.get(f"/jobs/{job.id}/fragment")
        assert response.status_code == 200
        assert "hx-trigger" not in response.text  # polling stopped


def test_start_scan_creates_job_and_returns_progress_fragment(db_session):
    account = _account(db_session)

    # Avoid running the actual job — we only assert the row was created.
    with TestClient(app) as client, \
         patch("app.routes.jobs._dispatch_scan_job") as dispatch:
        dispatch.return_value = None
        response = client.post(f"/accounts/{account.id}/scan")

    assert response.status_code == 200
    job = db_session.query(Job).filter_by(account_id=account.id).one()
    assert job.type == JobType.scan
    assert dispatch.called
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/routes/test_jobs_routes.py -v
```

- [ ] **Step 3: Create `app/templates/fragments/job_progress.html`**

```jinja
{% from "_macros.html" import progress_bar %}
{% set terminal = job.status.value in ("success", "failed", "cancelled") %}

<div id="job-{{ job.id }}"
     {% if not terminal %}hx-get="/jobs/{{ job.id }}/fragment"
       hx-trigger="every 2s"
       hx-swap="outerHTML"{% endif %}>
  <div class="muted">Job #{{ job.id }} — {{ job.type.value }} — {{ job.status.value }}</div>
  {{ progress_bar(job.progress_done, job.progress_total) }}
  {% if job.status.value == "failed" %}
  <div style="color: var(--danger);">Error: {{ job.error or "unknown" }}</div>
  {% endif %}
</div>
```

- [ ] **Step 4: Create `app/routes/jobs.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.jobs.runner import JobRunner
from app.jobs.scan import build_scan_work
from app.models.account import Account, ProviderType
from app.models.job import Job, JobType
from app.providers.imap import IMAPProvider
from app.providers.jmap import JMAPProvider
from app.services.crypto import CredentialCipher

router = APIRouter(tags=["jobs"])


def _templates(request: Request):
    from app.main import templates
    return templates


def _provider_for(account: Account):
    cipher = CredentialCipher.from_settings()
    if account.provider == ProviderType.imap:
        password = cipher.decrypt(account.credential_encrypted)
        return IMAPProvider(
            account.imap_host or "", account.imap_port or 993,
            account.imap_username or "", password,
        )
    if account.provider == ProviderType.jmap:
        token = cipher.decrypt(account.credential_encrypted)
        return JMAPProvider(api_token=token)
    raise HTTPException(status_code=400, detail="Unknown provider")


_runner: JobRunner | None = None


def _get_runner() -> JobRunner:
    global _runner
    if _runner is None:
        _runner = JobRunner()
    return _runner


def _dispatch_scan_job(job_id: int, account: Account) -> None:
    """Schedule the scan job on the runner. Separate function so tests can patch."""
    provider = _provider_for(account)
    work = build_scan_work(account_id=account.id, provider=provider, max_messages=500)
    _get_runner().schedule(job_id, work)


@router.post("/accounts/{account_id}/scan", response_class=HTMLResponse)
def start_scan(account_id: int, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404)

    job_id = JobRunner.create_job(
        db, type=JobType.scan, account_id=account_id, params={"max_messages": 500},
    )
    _dispatch_scan_job(job_id, account)

    job = db.get(Job, job_id)
    return _templates(request).TemplateResponse(
        request, "fragments/job_progress.html", {"job": job}
    )


@router.get("/jobs/{job_id}/fragment", response_class=HTMLResponse)
def job_fragment(job_id: int, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404)
    return _templates(request).TemplateResponse(
        request, "fragments/job_progress.html", {"job": job}
    )
```

- [ ] **Step 5: Wire the router** — append in `app/main.py` after the accounts router include:

```python
from app.routes import jobs as jobs_routes
...
app.include_router(jobs_routes.router)
```

- [ ] **Step 6: Add the scan button to `app/templates/fragments/account_card.html`**

Replace the existing card with:

```jinja
<div class="card" id="account-{{ account.id }}">
  <div class="flex between">
    <div>
      <strong>{{ account.name }}</strong>
      <div class="muted">{{ account.email }} · {{ account.provider.value }}</div>
      {% if account.last_full_scan_at %}
      <div class="muted">Last scan: {{ account.last_full_scan_at.strftime("%Y-%m-%d %H:%M") }}</div>
      {% else %}
      <div class="muted">Never scanned</div>
      {% endif %}
    </div>
    <div class="flex">
      <button hx-post="/accounts/{{ account.id }}/scan"
              hx-target="#scan-status-{{ account.id }}"
              hx-swap="innerHTML">Scan</button>
      <form method="post" action="/accounts/{{ account.id }}/delete">
        <button type="submit" class="secondary"
                onclick="return confirm('Delete account {{ account.email }}?')">Delete</button>
      </form>
    </div>
  </div>
  <div id="scan-status-{{ account.id }}"></div>
</div>
```

- [ ] **Step 7: Run tests**

```bash
uv run pytest tests/routes/test_jobs_routes.py -v
```

Expected: 3 passed.

- [ ] **Step 8: Run full suite**

```bash
uv run pytest -v
```

- [ ] **Step 9: Commit**

```bash
git add app/routes/jobs.py app/templates/fragments/ app/main.py tests/routes/test_jobs_routes.py
git commit -m "feat(ui/jobs): scan trigger button + 2s-polling progress fragment"
```

---

## Task 23: Sender list view (period filter + sender/domain grouping)

**Files:**
- Create: `app/routes/senders.py`, `app/templates/pages/senders.html`, `app/templates/fragments/sender_row.html`, `tests/routes/test_senders_routes.py`
- Modify: `app/main.py`, `app/templates/pages/index.html`

- [ ] **Step 1: Write the failing test**

```python
# tests/routes/test_senders_routes.py
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.models.account import Account, ProviderType
from app.models.message import Message
from app.models.sender import Sender


def _seed(db) -> Account:
    account = Account(name="A", email="a@x.com",
                      provider=ProviderType.jmap, credential_encrypted="x")
    db.add(account)
    db.commit()

    now = datetime.now(timezone.utc)
    senders = [
        Sender(account_id=account.id, group_key="g.news",
               from_email="news@example.com", from_domain="example.com",
               display_name="News"),
        Sender(account_id=account.id, group_key="g.shop",
               from_email="shop@vendor.com", from_domain="vendor.com",
               display_name="Shop"),
    ]
    db.add_all(senders)
    db.commit()

    # 5 fresh news messages, 1 ancient shop message
    for i in range(5):
        db.add(Message(
            account_id=account.id, sender_id=senders[0].id,
            provider_uid=f"n{i}", mailbox="INBOX", subject=f"News {i}",
            received_at=now - timedelta(days=i),
        ))
    db.add(Message(
        account_id=account.id, sender_id=senders[1].id,
        provider_uid="s1", mailbox="INBOX", subject="Old shop",
        received_at=now - timedelta(days=400),
    ))
    db.commit()
    return account


def test_sender_list_default_30d_orders_by_count(db_session):
    account = _seed(db_session)
    with TestClient(app) as client:
        response = client.get(f"/?account_id={account.id}")
        assert response.status_code == 200
        assert "News" in response.text
        # Shop is older than 30d, should not show
        assert "Shop" not in response.text


def test_sender_list_alltime_includes_old(db_session):
    account = _seed(db_session)
    with TestClient(app) as client:
        response = client.get(f"/?account_id={account.id}&period=all")
        assert "Shop" in response.text


def test_sender_list_domain_grouping(db_session):
    account = _seed(db_session)
    with TestClient(app) as client:
        response = client.get(f"/?account_id={account.id}&group=domain&period=all")
    # In domain mode: rows show domains, not display names
    assert "example.com" in response.text
    assert "vendor.com" in response.text
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/routes/test_senders_routes.py -v
```

- [ ] **Step 3: Create `app/routes/senders.py`**

```python
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.account import Account
from app.models.message import Message
from app.models.sender import Sender, SenderStatus

router = APIRouter(tags=["senders"])

Period = Literal["7d", "30d", "90d", "all"]
Grouping = Literal["sender", "domain"]


def _period_floor(period: Period) -> datetime | None:
    now = datetime.now(timezone.utc)
    if period == "7d":
        return now - timedelta(days=7)
    if period == "30d":
        return now - timedelta(days=30)
    if period == "90d":
        return now - timedelta(days=90)
    return None  # "all"


def _templates(request: Request):
    from app.main import templates
    return templates


@router.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    account_id: int | None = Query(default=None),
    period: Period = Query(default="30d"),
    group: Grouping = Query(default="sender"),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    accounts = db.execute(select(Account).order_by(Account.created_at)).scalars().all()
    if account_id is None and accounts:
        account_id = accounts[0].id
    selected_account = db.get(Account, account_id) if account_id else None

    rows: list[dict] = []
    if selected_account is not None:
        floor = _period_floor(period)
        rows = _query_rows(db, selected_account.id, floor, group)

    context = {
        "accounts": accounts,
        "selected_account": selected_account,
        "rows": rows,
        "period": period,
        "group": group,
    }
    return _templates(request).TemplateResponse(request, "pages/senders.html", context)


def _query_rows(
    db: Session, account_id: int, floor: datetime | None, group: Grouping
) -> list[dict]:
    msg_filter = [Message.account_id == account_id]
    if floor is not None:
        msg_filter.append(Message.received_at >= floor)

    if group == "sender":
        stmt = (
            select(
                Sender.id.label("sender_id"),
                Sender.display_name,
                Sender.from_email,
                Sender.from_domain,
                Sender.unsubscribe_one_click_post,
                func.count(Message.id).label("count"),
                func.max(Message.received_at).label("last_seen"),
            )
            .join(Message, Message.sender_id == Sender.id)
            .where(Sender.account_id == account_id)
            .where(Sender.status == SenderStatus.active)
            .where(*msg_filter)
            .group_by(Sender.id)
            .order_by(func.count(Message.id).desc())
            .limit(50)
        )
        return [dict(row._mapping) for row in db.execute(stmt).all()]

    # group == "domain"
    stmt = (
        select(
            Sender.from_domain.label("from_domain"),
            func.count(Message.id).label("count"),
            func.max(Message.received_at).label("last_seen"),
        )
        .join(Message, Message.sender_id == Sender.id)
        .where(Sender.account_id == account_id)
        .where(Sender.status == SenderStatus.active)
        .where(*msg_filter)
        .group_by(Sender.from_domain)
        .order_by(func.count(Message.id).desc())
        .limit(50)
    )
    return [dict(row._mapping) for row in db.execute(stmt).all()]
```

- [ ] **Step 4: Create `app/templates/pages/senders.html`**

```jinja
{% extends "base.html" %}
{% block title %}Senders — Bulk Unsubscribe{% endblock %}

{% block content %}
<form method="get" action="/" class="card">
  <div class="flex" style="flex-wrap: wrap; gap: 0.5rem;">
    <select name="account_id">
      {% for a in accounts %}
      <option value="{{ a.id }}"
              {% if selected_account and selected_account.id == a.id %}selected{% endif %}>
        {{ a.name }} ({{ a.email }})
      </option>
      {% endfor %}
    </select>
    <select name="period">
      {% for p in ["7d", "30d", "90d", "all"] %}
      <option value="{{ p }}" {% if period == p %}selected{% endif %}>{{ p }}</option>
      {% endfor %}
    </select>
    <select name="group">
      <option value="sender" {% if group == "sender" %}selected{% endif %}>Per sender</option>
      <option value="domain" {% if group == "domain" %}selected{% endif %}>Per domain</option>
    </select>
    <button type="submit">Apply</button>
  </div>
</form>

{% if not accounts %}
<p class="muted">No accounts yet. <a href="/accounts">Add one</a> to get started.</p>
{% elif not rows %}
<p class="muted">Nothing to show. Run a scan from the <a href="/accounts">Accounts</a> page.</p>
{% else %}
{% for row in rows %}
  {% include "fragments/sender_row.html" %}
{% endfor %}
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Create `app/templates/fragments/sender_row.html`**

```jinja
<div class="card flex between">
  <div>
    {% if group == "sender" %}
      <strong>{{ row.display_name or row.from_email }}</strong>
      <div class="muted">{{ row.from_email }} · {{ row.from_domain }}</div>
    {% else %}
      <strong>{{ row.from_domain }}</strong>
      <div class="muted">domain</div>
    {% endif %}
    <div class="muted">
      {{ row.count }} message{{ "s" if row.count != 1 else "" }}
      {% if row.last_seen %} · last on {{ row.last_seen.strftime("%Y-%m-%d") }}{% endif %}
    </div>
  </div>
  {% if group == "sender" %}
  <a class="btn secondary" href="/senders/{{ row.sender_id }}">Open</a>
  {% endif %}
</div>
```

- [ ] **Step 6: Replace `app/templates/pages/index.html`** so that `/` is the senders view

Delete `app/templates/pages/index.html`. Remove the `index` route from `app/main.py` (the senders router now owns `/`).

In `app/main.py`, remove:
```python
@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "pages/index.html", {})
```

Add the senders router include:
```python
from app.routes import senders as senders_routes
...
app.include_router(senders_routes.router)
```

- [ ] **Step 7: Run tests**

```bash
uv run pytest tests/routes/test_senders_routes.py -v
```

Expected: 3 passed.

- [ ] **Step 8: Run full suite**

```bash
uv run pytest -v
```

- [ ] **Step 9: Commit**

```bash
git add app/routes/senders.py app/templates/ app/main.py tests/routes/test_senders_routes.py
git rm app/templates/pages/index.html
git commit -m "feat(ui/senders): top-senders view with period + grouping toggle"
```

---

## Task 24: Sender detail page with lazy preview

**Files:**
- Modify: `app/routes/senders.py`, `app/providers/jmap.py`, `app/providers/imap.py`
- Create: `app/templates/pages/sender_detail.html`, `app/templates/fragments/message_preview.html`, `tests/routes/test_sender_detail.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/routes/test_sender_detail.py
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.account import Account, ProviderType
from app.models.message import Message
from app.models.sender import Sender


def _seed(db):
    account = Account(name="A", email="a@x.com",
                      provider=ProviderType.jmap, credential_encrypted="x")
    db.add(account)
    db.commit()
    sender = Sender(
        account_id=account.id, group_key="g",
        from_email="news@example.com", from_domain="example.com",
        display_name="News",
        unsubscribe_http="https://example.com/u",
        unsubscribe_one_click_post=True,
    )
    db.add(sender)
    db.commit()
    for i in range(3):
        db.add(Message(
            account_id=account.id, sender_id=sender.id,
            provider_uid=f"u{i}", mailbox="INBOX",
            subject=f"News {i}", received_at=datetime(2026, 4, i + 1, tzinfo=timezone.utc),
        ))
    db.commit()
    return account, sender


def test_sender_detail_lists_messages(db_session):
    _, sender = _seed(db_session)
    with TestClient(app) as client:
        response = client.get(f"/senders/{sender.id}")
    assert response.status_code == 200
    assert "News 0" in response.text
    assert "News 2" in response.text
    # Preview should not be inlined yet — lazy
    assert "lazy preview" in response.text.lower() or "hx-get" in response.text


def test_message_preview_fragment_returns_snippet(db_session):
    account, sender = _seed(db_session)

    async def fake_snippet(self, ref):
        return "Hello world preview"

    with TestClient(app) as client, \
         patch("app.providers.jmap.JMAPProvider.fetch_snippet", new=fake_snippet):
        response = client.get(
            f"/senders/{sender.id}/messages/u0/preview"
        )
    assert response.status_code == 200
    assert "Hello world preview" in response.text
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/routes/test_sender_detail.py -v
```

- [ ] **Step 3: Add `fetch_snippet` to JMAP provider** — replace its stub in `app/providers/jmap.py`

```python
async def fetch_snippet(self, ref: MessageRef) -> str:
    async with aiohttp.ClientSession() as http:
        if self._api_url is None:
            await self._get_session(http)
        payload = {
            "using": _CAPS,
            "methodCalls": [[
                "Email/get",
                {
                    "accountId": self._account_id,
                    "ids": [ref.provider_uid],
                    "properties": ["preview", "subject"],
                },
                "0",
            ]],
        }
        async with http.post(self._api_url, json=payload, headers=self._headers) as r:
            r.raise_for_status()
            data = await r.json()
    items = data["methodResponses"][0][1].get("list", [])
    if not items:
        return ""
    return (items[0].get("preview") or "").strip()
```

- [ ] **Step 4: Add `fetch_snippet` to IMAP provider** — replace its stub in `app/providers/imap.py`

```python
def _fetch_snippet_sync(self, ref: MessageRef) -> str:
    conn = self._connect()
    try:
        conn.select(ref.mailbox, readonly=True)
        status, data = conn.uid("FETCH", ref.provider_uid, "(BODY.PEEK[TEXT]<0.2048>)")
        if status != "OK" or not data:
            return ""
        for entry in data:
            if isinstance(entry, tuple) and len(entry) >= 2:
                raw = entry[1]
                if isinstance(raw, (bytes, bytearray)):
                    text = bytes(raw).decode("utf-8", errors="replace")
                    # Strip MIME-ish whitespace; keep first 200 chars.
                    return " ".join(text.split())[:200]
        return ""
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass


async def fetch_snippet(self, ref: MessageRef) -> str:
    return await asyncio.to_thread(self._fetch_snippet_sync, ref)
```

- [ ] **Step 5: Add the routes to `app/routes/senders.py`** — append:

```python
from fastapi import HTTPException

from app.providers.base import MessageRef
from app.providers.imap import IMAPProvider
from app.providers.jmap import JMAPProvider
from app.services.crypto import CredentialCipher
from app.models.account import ProviderType


def _provider_for_account(account: Account):
    cipher = CredentialCipher.from_settings()
    secret = cipher.decrypt(account.credential_encrypted)
    if account.provider == ProviderType.imap:
        return IMAPProvider(
            account.imap_host or "", account.imap_port or 993,
            account.imap_username or "", secret,
        )
    return JMAPProvider(api_token=secret)


@router.get("/senders/{sender_id}", response_class=HTMLResponse)
def sender_detail(
    sender_id: int, request: Request, db: Session = Depends(get_db)
) -> HTMLResponse:
    sender = db.get(Sender, sender_id)
    if sender is None:
        raise HTTPException(status_code=404)
    messages = (
        db.execute(
            select(Message)
            .where(Message.sender_id == sender_id)
            .order_by(Message.received_at.desc())
            .limit(50)
        ).scalars().all()
    )
    return _templates(request).TemplateResponse(
        request,
        "pages/sender_detail.html",
        {"sender": sender, "messages": messages},
    )


@router.get(
    "/senders/{sender_id}/messages/{provider_uid}/preview",
    response_class=HTMLResponse,
)
async def message_preview(
    sender_id: int,
    provider_uid: str,
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    sender = db.get(Sender, sender_id)
    if sender is None:
        raise HTTPException(status_code=404)
    message = db.scalar(
        select(Message).where(
            Message.sender_id == sender_id,
            Message.provider_uid == provider_uid,
        )
    )
    if message is None:
        raise HTTPException(status_code=404)

    snippet = message.snippet
    if not snippet:
        account = db.get(Account, message.account_id)
        provider = _provider_for_account(account)
        snippet = await provider.fetch_snippet(
            MessageRef(provider_uid=provider_uid, mailbox=message.mailbox)
        )
        message.snippet = snippet
        db.commit()

    return _templates(request).TemplateResponse(
        request,
        "fragments/message_preview.html",
        {"message": message, "snippet": snippet},
    )
```

- [ ] **Step 6: Create `app/templates/pages/sender_detail.html`**

```jinja
{% extends "base.html" %}
{% block title %}{{ sender.display_name or sender.from_email }} — Bulk Unsubscribe{% endblock %}

{% block content %}
<a class="muted" href="/">← back</a>
<div class="card">
  <h2 style="margin-top:0">{{ sender.display_name or sender.from_email }}</h2>
  <div class="muted">{{ sender.from_email }} · {{ sender.from_domain }}</div>
  {% if sender.list_id %}<div class="muted">List-Id: {{ sender.list_id }}</div>{% endif %}
  <div class="muted">
    Status: {{ sender.status.value }}
    {% if sender.unsubscribe_one_click_post %} · 🟢 one-click supported{% endif %}
    {% if sender.unsubscribe_http %} · HTTP link available{% endif %}
    {% if sender.unsubscribe_mailto %} · mailto link available{% endif %}
  </div>
</div>

<h3>Recent messages ({{ messages|length }})</h3>
{% for m in messages %}
<div class="card" id="msg-{{ m.provider_uid }}">
  <div class="flex between">
    <div>
      <strong>{{ m.subject or "(no subject)" }}</strong>
      <div class="muted">{{ m.received_at.strftime("%Y-%m-%d %H:%M") }} · {{ m.mailbox }}</div>
    </div>
    <button class="secondary"
            hx-get="/senders/{{ sender.id }}/messages/{{ m.provider_uid }}/preview"
            hx-target="#preview-{{ m.provider_uid }}"
            hx-swap="innerHTML">Preview</button>
  </div>
  <div id="preview-{{ m.provider_uid }}" class="muted" style="margin-top:0.5rem;">
    <em>lazy preview — click "Preview" to load.</em>
  </div>
</div>
{% endfor %}
{% endblock %}
```

- [ ] **Step 7: Create `app/templates/fragments/message_preview.html`**

```jinja
{% if snippet %}
<div>{{ snippet }}</div>
{% else %}
<em>(no preview available)</em>
{% endif %}
```

- [ ] **Step 8: Run tests**

```bash
uv run pytest tests/routes/test_sender_detail.py -v
```

Expected: 2 passed.

- [ ] **Step 9: Run full suite**

```bash
uv run pytest -v
```

- [ ] **Step 10: Commit**

```bash
git add app/routes/senders.py app/providers/jmap.py app/providers/imap.py \
        app/templates/pages/sender_detail.html app/templates/fragments/message_preview.html \
        tests/routes/test_sender_detail.py
git commit -m "feat(ui/senders): detail page with lazy snippet preview via HTMX"
```

---

## Task 25: README rewrite for v0.2 foundations

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace `README.md`** with:

````markdown
# Bulk Unsubscribe (v0.2 — foundations)

Mobile-first webapp that connects to your mail provider, scans for newsletters, and helps you decide what to do about them. **This release** lets you connect accounts, scan, and browse top senders with previews. Unsubscribe execution and bulk inbox actions land in the next release.

## Features (v0.2)

- IMAP and Fastmail (JMAP) accounts.
- Header-only scan that detects messages with `List-Unsubscribe`.
- Top-senders view per account, filtered by 7d / 30d / 90d / all-time.
- Toggle between sender-grouping and domain-grouping.
- Sender detail with up to 50 recent messages and lazy snippet preview.
- Async scan jobs with live progress (polled by HTMX every 2s).

## Setup

```bash
# Generate a Fernet key first
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
export BU_FERNET_KEY=<paste-output>

# Optional overrides
export BU_DATA_DIR=./var
export BU_BIND_HOST=127.0.0.1
export BU_BIND_PORT=8000

uv sync --all-groups
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>.

## Tests

```bash
uv run pytest -v
```

## Configuration

| Env var | Required | Default | Notes |
|---------|----------|---------|-------|
| `BU_FERNET_KEY` | yes | — | Output of `Fernet.generate_key()` |
| `BU_DATA_DIR`   | no  | `./var` | SQLite DB + (future) body cache |
| `BU_DATABASE_URL` | no | `sqlite:///{data_dir}/bulk-unsubscribe.db` | |
| `BU_BIND_HOST`  | no  | `127.0.0.1` | |
| `BU_BIND_PORT`  | no  | `8000` | |

## Roadmap

The next plan ("Actions & deployment") covers RFC 8058 one-click unsubscribe with confirmation, bulk archive/trash, whitelist (sender + domain), single-password auth gate, Dockerfile, and a GitHub Actions workflow that publishes images to GHCR on every push to `main`.
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: rewrite README for v0.2 foundations"
```

---

## Final verification

- [ ] **Run the full suite**

```bash
uv run pytest -v
```

Expected: every test green.

- [ ] **Boot the server manually**

```bash
export BU_FERNET_KEY=$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then in a browser:
1. Visit <http://127.0.0.1:8000/accounts>; add a Fastmail or IMAP account.
2. Click "Scan"; watch the progress fragment update every 2s.
3. Visit <http://127.0.0.1:8000/>, switch period and grouping, open a sender, click "Preview" on a message.

- [ ] **Confirm scope**

This plan delivers the read-only foundation: connect, scan, browse, preview. The next plan (Plan 2 — actions & deployment) adds:
- Unsubscribe flow (one-click POST + HTTP/mailto with explicit user confirmation).
- Bulk archive / move-to-trash across all folders.
- Whitelist (sender + domain) and Whitelist view.
- Single-password auth gate.
- Dockerfile and GHCR GitHub Actions workflow.
- README rewrite for the full feature set.
