# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Tooling

This project uses **uv** (not pip). uv lives in `~/.local/bin/uv`; that path may not be on `PATH` by default — prefix commands with `export PATH="$HOME/.local/bin:$PATH" && ...` if `uv` is not found.

```bash
uv sync --all-groups                      # install (incl. dev deps)
uv run pytest -v                          # full test suite
uv run pytest tests/path/test_x.py -v     # one file
uv run pytest tests/x.py::test_name -v    # one test
uv run ruff check .                       # lint
uv run alembic revision --autogenerate -m "message"
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
docker build -t bulk-unsubscribe:dev .
```

`BU_FERNET_KEY` (a real `Fernet.generate_key()` output) is **required** for the app to boot, run alembic, or import `app.main`. The pytest `conftest.py` sets one at module-load time; if you write code that imports `app.main` outside pytest, set the env var first.

## Architecture

**Layering (strict — don't break it):**
- `app/routes/` — request parsing, redirect/render only. No IMAP/JMAP code, no SQL beyond simple queries.
- `app/services/` — pure business logic, testable without DB or HTTP. Houses the unsubscribe parser, grouping rules, whitelist engine, crypto, provider factory.
- `app/providers/` — only place that touches IMAP (`imaplib`) or JMAP (`aiohttp`). All consumers talk to the `MailProvider` Protocol in `app/providers/base.py`.
- `app/jobs/` — long operations (scan, bulk archive/trash). Routes start a `Job` and dispatch via `JobRunner.schedule()`; the UI polls `/jobs/{id}/fragment` every 2s.
- `app/models/` — SQLAlchemy 2.x mapped classes; `__init__.py` re-exports everything so alembic's autogenerate sees all tables.

**Provider Protocol.** New mailbox-touching code goes through `MailProvider` (`test_credentials`, `list_mailboxes`, `scan_headers`, `fetch_snippet`, `search_by_sender`, `move_messages`). IMAP is sync wrapped in `asyncio.to_thread`; JMAP is async with chained method calls in one HTTP request. Tests use `tests/fakes/mail_provider.py` — never hit a real server in CI.

**Data model identity.** `Sender.group_key` is `normalized List-ID` if present, else `from_email` (lowercased). `SenderAlias` records every From-address seen in the group. The senders view aggregates by `group_key` (default) or `from_domain` (toggle).

**Whitelist semantics.** Rules in `whitelist_rules` table; three kinds:
- `mailbox` rules are applied **during scan** (`should_skip_during_scan`) — those messages are never persisted.
- `sender` / `domain` rules are applied **after scan** (`recompute_sender_statuses`) and flip `Sender.status` to `whitelisted`. The default senders view filters those out.
Sub-folder match for `mailbox` is prefix-based on `/` or `.`.

**Job runner gotcha.** `JobRunner.recover_orphans()` runs in the FastAPI lifespan and flips any `running` job to `failed`. Tests that need to assert against a `running` job must create that row **inside the `with TestClient(app) as client:` block** (i.e. after lifespan startup). See `tests/routes/test_jobs_routes.py`.

**Provider factory.** Routes that need a `MailProvider` from a stored `Account` use `app.services.provider_factory.build_provider`. To avoid real credential decryption in tests, patch `app.services.provider_factory.CredentialCipher.from_settings` (see `tests/routes/test_sender_detail.py`).

**Test DB convention.** `conftest.py`'s `db_session` fixture creates `sqlite:///{tmp_path}/bulk-unsubscribe.db` — the **same path the default settings would resolve to**. This means jobs/routes that call `get_session_factory()` with no URL hit the same SQLite file the test inspects. Don't change that path without also changing every job that uses it.

**No built-in auth.** The login gate (`app/auth.py`, `BU_AUTH_PASSWORD`, `SessionMiddleware`) was removed in `da6ae03`. Auth is delegated to a reverse proxy. `app/main.py` logs a startup warning if `BU_AUTH_PASSWORD` is still set so legacy users notice. Browser CSRF is mitigated by `app/security.py`'s `OriginProtectionMiddleware`, which 403s any unsafe-method request whose `Origin` (or, as fallback, `Referer`) doesn't match the request host. Requests with neither header are allowed (non-browser clients).

**Frontend.** Server-rendered Jinja2 with HTMX 2.x for fragments and Alpine.js for tiny in-page state. Vendor JS lives in `static/vendor/` — no build step, no npm. Pages are in `app/templates/pages/`, HTMX-swappable fragments in `app/templates/fragments/`.

## Migrations

Alembic autogenerate works against `app.models.register_all()`. After changing a model: `uv run alembic revision --autogenerate -m "..."`, inspect the generated file (SQLite stores enums as VARCHAR — that's expected), then `uv run alembic upgrade head`. The Docker entrypoint runs `alembic upgrade head` on every container start.

## Things that look weird but are intentional

- `import` statements after `app = FastAPI(...)` in `app/main.py` — middleware must be added before routers, and routers must be added after `app.mount("/static", ...)`.
- `SenderAlias.email_count` is approximated per-batch in the scan (we don't persist alias→message links). Idempotent on rerun. Total count on `Sender` is recomputed via SQL `COUNT` and is exact.

## Internal docs (gitignored)

`docs/superpowers/` is in `.gitignore`. Specs and plans there are local-only — don't restore them to tracking.
