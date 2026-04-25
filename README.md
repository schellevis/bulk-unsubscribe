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

The next plan ("Actions & deployment") covers RFC 8058 one-click unsubscribe with confirmation, bulk archive/trash across all folders, whitelist (sender + domain + mailbox/label), single-password auth gate, Dockerfile, and a GitHub Actions workflow that publishes images to GHCR on every push to `main`.
