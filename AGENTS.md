# Repository Guidelines

## Project Structure & Module Organization

This is a Python 3.12 FastAPI app for a self-hosted bulk unsubscribe workflow. Application code lives in `app/`: `routes/` handles HTTP and rendering, `services/` contains business logic, `providers/` contains IMAP/JMAP integrations, `jobs/` runs scans and bulk actions, and `models/` defines SQLAlchemy tables. Templates are in `app/templates/`, static CSS and vendored HTMX/Alpine assets are in `static/`, migrations are in `alembic/versions/`, and tests mirror the app layout under `tests/`.

## Build, Test, and Development Commands

Use `uv` for dependency and command execution.

- `uv sync --all-groups` installs runtime and dev dependencies.
- `uv run pytest -v` runs the full test suite.
- `uv run pytest tests/routes/test_accounts_routes.py -v` runs one test file.
- `uv run ruff check .` runs lint checks.
- `uv run alembic upgrade head` applies database migrations.
- `uv run uvicorn app.main:app --host 127.0.0.1 --port 8000` starts the app locally.
- `docker build -t bulk-unsubscribe:dev .` builds a local image.

Set `BU_FERNET_KEY` before importing or running the app outside pytest. Generate one with `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`.

## Coding Style & Naming Conventions

Ruff is configured for Python 3.12, 100-character lines, import sorting, pyupgrade, bugbear, simplify, and Ruff rules. Follow the existing layered architecture: routes should stay thin, provider-specific network code belongs in `app/providers/`, and reusable business rules belong in `app/services/`. Use `snake_case` for modules, functions, fixtures, and test names; use `PascalCase` for ORM models and protocol/classes.

## Testing Guidelines

Tests use `pytest`, `pytest-asyncio`, `httpx`, and local fakes. Add focused tests near the code being changed, using paths such as `tests/services/test_grouping.py` or `tests/providers/test_jmap_scan.py`. Test names should describe behavior, for example `test_scan_skips_whitelisted_mailbox`. Do not contact real mail servers in tests; use `tests/fakes/mail_provider.py` or patch provider construction.

## Commit & Pull Request Guidelines

Git history uses conventional-style commits such as `feat(ui/senders): ...`, `fix(...)`, `docs: ...`, `ci: ...`, and `chore: ...`. Keep commits scoped and imperative. Pull requests should include a short summary, linked issue when applicable, test results (`uv run pytest -v`, `uv run ruff check .`), migration notes for model changes, and screenshots or screen recordings for UI changes.

## Security & Configuration Tips

Keep credentials and `BU_FERNET_KEY` out of git. The app stores mail credentials encrypted and is intended as a single-user tool. Bind to `127.0.0.1` locally; use TLS and a reverse proxy for remote access.
