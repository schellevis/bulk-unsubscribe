# Bulk Unsubscribe

Mobile-first, self-hosted webapp that connects to your mail provider, scans for newsletters, and helps you bulk-unsubscribe and clean up your inbox.

## Features

- **Connect IMAP or Fastmail (JMAP) accounts** — multiple per install.
- **Scan** the inbox for messages with `List-Unsubscribe` headers; group senders by `List-ID` (with fallback to From-address) and show top senders per period (7d / 30d / 90d / all-time).
- **Sender detail** with up to 50 recent messages and lazy snippet preview.
- **Unsubscribe** with explicit URL/method confirmation:
  - 🟢 **One-click POST** (RFC 8058) when supported.
  - HTTP link (opens in a new tab; you confirm in the browser).
  - mailto link.
- **Bulk inbox actions** per sender, across all folders:
  - Move to **Archive**.
  - Move to **Trash** (recoverable via your mail client).
- **Whitelist** rules per account, three scopes:
  - `sender` — exact From-address.
  - `domain` — every sender on that domain.
  - `mailbox` — every message in that folder/label (sub-folders match by prefix).
- Same-origin protection for browser-triggered POST requests.
- **Async jobs** with live HTMX-polled progress.
- **Docker image** published to GHCR on every push to `main`.

## Local setup

```bash
# 1. Generate a Fernet key
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
export BU_FERNET_KEY=<paste-output>

# Optional
export BU_BIND_HOST=127.0.0.1
export BU_BIND_PORT=8000
export BU_DATA_DIR=./var

# 2. Install + migrate + run
uv sync --all-groups
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>.

## Docker

```bash
docker run --rm -p 8000:8000 \
  -e BU_FERNET_KEY=<fernet-key> \
  -v bulk-unsubscribe-data:/data \
  ghcr.io/<owner>/bulk-unsubscribe:latest
```

The image runs as a non-root user, persists SQLite + caches in `/data`, and runs `alembic upgrade head` on startup.

### docker compose

A ready-to-use `docker-compose.yml` is included. Create a `.env` next to it
with your generated key, then start the stack:

```bash
echo "BU_FERNET_KEY=$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" > .env
docker compose up -d
```

By default it binds to `127.0.0.1:8000` only — drop the `127.0.0.1:` prefix in
the `ports:` mapping once you've put a reverse proxy with TLS in front.

## Tests

```bash
uv run pytest -v
```

## Configuration

| Env var | Required | Default | Notes |
|---------|----------|---------|-------|
| `BU_FERNET_KEY` | yes | — | Output of `Fernet.generate_key()`. App refuses to start without a valid key. |
| `BU_DATA_DIR` | no | `./var` (or `/data` in Docker) | SQLite DB lives here. |
| `BU_DATABASE_URL` | no | `sqlite:///{data_dir}/bulk-unsubscribe.db` | |
| `BU_BIND_HOST` | no | `127.0.0.1` | Bind to `0.0.0.0` only behind a reverse proxy. |
| `BU_BIND_PORT` | no | `8000` | |

## Security notes

- The app binds `127.0.0.1` by default. Run it on localhost or behind a reverse proxy with TLS.
- Authentication is intentionally out of scope for this app. It has no built-in login gate, users, or session cookies. Put it behind a reverse proxy if you expose it beyond localhost.
- Browser-origin protection rejects unsafe-method requests when `Origin` or `Referer` points to another origin. Non-browser clients without those headers are still allowed.
- Credentials (IMAP password / JMAP token) are stored Fernet-encrypted; the key only lives in the env var.
- One-click unsubscribe only posts to HTTPS URLs whose host resolves to public IP addresses, rejects credentials in URLs, and validates every redirect target before following it.

## CI / GHCR

`.github/workflows/docker.yml` builds and pushes a multi-arch (amd64 + arm64) image to `ghcr.io/<owner>/bulk-unsubscribe` on every push to `main`, tagged `latest` and `sha-<short>`.

## Architecture

- FastAPI + Jinja2 + HTMX + Alpine.js (no build step).
- SQLAlchemy 2.x + Alembic + SQLite.
- `MailProvider` Protocol with IMAP (`imaplib` wrapped in `asyncio.to_thread`) and JMAP (`aiohttp`) implementations.
- In-process async job runner with crash recovery — no external worker required.
