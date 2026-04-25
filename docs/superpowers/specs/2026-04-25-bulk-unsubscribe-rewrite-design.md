# Bulk Unsubscribe — Rewrite Design

**Date:** 2026-04-25
**Status:** Approved (brainstorming complete, ready for implementation plan)
**Supersedes:** v0.1 prototype on `main`

## 1. Goal & scope

A single-user, self-hosted webapp (mobile-first) that helps the owner work
through their newsletter inbox: see who sends the most, preview what they
send, decide per sender whether to unsubscribe, archive/trash existing
messages, or whitelist for the future.

Single-user, runs on localhost or behind a reverse proxy. Deployable as a
Docker image published to GHCR on every push to `main`.

In scope:
- IMAP and Fastmail (JMAP) accounts, multiple per install.
- Server-side scan and aggregation by `List-ID` with fallback to `From`-address.
- Manual unsubscribe with smart suggestion (RFC 8058 one-click POST when
  available), explicit URL/method confirmation before executing.
- Per-sender preview (lazy-loaded subjects/snippets/full body in sandbox iframe).
- Bulk actions on **all** mail from a sender across all folders: move to
  Trash (recoverable), or move to Archive/mark read.
- Whitelist per account, per sender or per domain, with a separate view to
  manage them.
- Top-senders main view filtered by selectable time period.

Out of scope (YAGNI for v1):
- Multi-user / authentication beyond single shared password.
- Truly destructive deletion (expunge); user does that in their mail client.
- Manual sender-merge UI; rely on `List-ID` accuracy + domain rollup view.
- External worker / queue (Redis, RQ, Celery).
- npm / build pipeline; HTMX + Alpine ship as static files.

## 2. Architecture

```
bulk-unsubscribe/
├── app/
│   ├── main.py                  # FastAPI + Jinja2 + statics
│   ├── config.py                # pydantic-settings
│   ├── db.py                    # SQLAlchemy engine/session
│   ├── models/                  # one file per aggregate
│   │   ├── account.py
│   │   ├── sender.py
│   │   ├── message.py
│   │   ├── job.py
│   │   └── action.py
│   ├── providers/               # mail-provider abstraction
│   │   ├── base.py              # MailProvider Protocol
│   │   ├── imap.py              # sync, runs via asyncio.to_thread
│   │   └── jmap.py              # async, aiohttp
│   ├── jobs/
│   │   ├── runner.py            # in-process scheduler
│   │   ├── scan.py
│   │   └── bulk_action.py
│   ├── routes/
│   │   ├── pages.py             # full-page Jinja renders
│   │   ├── senders.py
│   │   ├── unsubscribe.py
│   │   ├── inbox_actions.py
│   │   ├── jobs.py              # progress fragments for HTMX polling
│   │   └── accounts.py
│   ├── services/
│   │   ├── unsubscribe.py       # parse List-Unsubscribe + RFC 8058 logic
│   │   ├── grouping.py          # group_key, domain rollup
│   │   └── crypto.py            # Fernet, key from env or generated
│   └── templates/               # Jinja2 (HTMX fragments + base.html)
├── tests/                       # pytest with provider fakes
├── alembic/                     # migrations
├── static/                      # css, htmx.min.js, alpine.min.js
├── Dockerfile
├── .github/workflows/docker.yml
├── pyproject.toml
└── README.md
```

**Layer discipline:**
- `routes/` parses requests and orchestrates services/jobs; no IMAP/JMAP code.
- `services/` is pure logic, testable without DB/HTTP.
- `providers/` is the only place with provider-specific code; the rest of the
  app talks to the `MailProvider` Protocol.
- `jobs/` owns long-running operations; routes start a job and return a `job_id`.

## 3. Data model

```python
Account
  id, name, email (unique), provider: imap|jmap
  imap_host, imap_port, imap_username  # nullable
  credential_encrypted                  # Fernet
  last_full_scan_at, last_incremental_scan_at
  created_at

Sender
  id, account_id (FK)
  group_key            # normalized List-ID, or from_email as fallback
  from_email           # representative address
  from_domain          # derived; used for domain-grouping & whitelist
  list_id              # nullable
  display_name
  email_count          # within current scan window
  unsubscribe_http
  unsubscribe_mailto
  unsubscribe_one_click_post  # bool: RFC 8058 supported
  status: active | unsubscribed | whitelisted | trashed
  whitelist_scope: none | sender | domain
  first_seen_at, last_seen_at
  UNIQUE(account_id, group_key)

SenderAlias                     # all From-addresses observed in this group
  id, sender_id, from_email, from_domain, email_count

Message                         # lightweight metadata cache, for preview
  id, sender_id, account_id
  provider_uid                  # IMAP UID or JMAP id
  mailbox                       # "INBOX", "Archive", ...
  subject, received_at
  snippet                       # nullable, lazy-filled
  has_full_body_cached          # bool
  UNIQUE(account_id, provider_uid, mailbox)

Job
  id, account_id (FK, nullable for global jobs)
  type: scan | bulk_archive | bulk_trash | unsubscribe
  status: queued | running | success | failed | cancelled
  progress_total, progress_done
  params_json                   # e.g. {"sender_id": 42, "destination": "trash"}
  result_json                   # summary
  error
  started_at, finished_at, created_at

Action                          # append-only audit log of mutations
  id, sender_id, job_id (nullable), account_id
  kind: unsubscribe_http | unsubscribe_one_click | unsubscribe_mailto
      | archive | trash | mark_read | whitelist | unwhitelist
  status: success | failed | partial
  affected_count               # for bulk
  detail                       # response codes, errors
  created_at
```

**Notes:**
- `group_key` is the identity of a sender group: lowercased & stripped
  `list_id` if present, else `from_email`. Domain rollup is a query-time
  `GROUP BY from_domain`, not a separate row.
- `Message` is a lightweight cache; bodies are not stored in the DB. Snippets
  and full bodies are fetched lazily on preview and cached on disk at
  `./var/body-cache/{account_id}/{provider_uid}.html`.
- `Job` is the single source of truth for in-flight ops. On app start, any
  `running` job becomes `failed` with `error="interrupted by restart"`.
- `Action` is append-only; no status mutations after the fact.
- Indexes: `Sender(account_id, status)`, `Sender(account_id, last_seen_at)`,
  `Message(sender_id, received_at DESC)`, `Job(status, created_at)`.

## 4. Provider abstraction & scan strategy

```python
class MailProvider(Protocol):
    async def test_credentials(self) -> bool: ...
    async def list_mailboxes(self) -> list[Mailbox]: ...
    async def scan_headers(
        self, since: datetime | None, max_messages: int
    ) -> AsyncIterator[ScannedMessage]: ...
    async def fetch_snippet(self, msg: MessageRef) -> str: ...
    async def fetch_body(self, msg: MessageRef) -> bytes: ...
    async def search_by_sender(
        self, sender: SenderQuery, mailboxes: list[str] | None = None
    ) -> AsyncIterator[MessageRef]: ...
    async def move_messages(
        self, refs: list[MessageRef], destination: SpecialFolder
    ) -> MoveResult: ...
```

`SpecialFolder` is an enum (`TRASH`, `ARCHIVE`) resolved per provider:
- IMAP: discover via `XLIST`/`LIST (SPECIAL-USE)`, fall back to common names.
- JMAP: read `role` from the Mailbox objects (`trash`, `archive`).

**IMAP implementation notes (`providers/imap.py`):**
- `imaplib` is sync → wrap every call in `asyncio.to_thread`.
- Header scan uses one bulk `FETCH` per batch of UIDs with
  `BODY.PEEK[HEADER.FIELDS (FROM DATE LIST-ID LIST-UNSUBSCRIBE LIST-UNSUBSCRIBE-POST SUBJECT MESSAGE-ID)]`.
- `search_by_sender` uses `SEARCH FROM "<addr>"` per mailbox; for List-ID
  groups, OR all aliases of the group.

**JMAP implementation notes (`providers/jmap.py`):**
- One JMAP request can chain multiple method calls; combine
  `Mailbox/get` + `Email/query` + `Email/get` to keep round-trips low.
- Use `header:List-Unsubscribe-Post:asText` to detect RFC 8058 support.
- `move_messages` is `Email/set` with `mailboxIds` patch.

**Scan strategy:**
- First scan per account: walk INBOX from newest, batches of 200, until
  `since` or 5000-message hard ceiling.
- Subsequent scans: incremental from `last_incremental_scan_at - 1 day`.
- Scan fills `Sender`, `SenderAlias`, and `Message` rows; never mutates
  the mailbox. When a message is added to an existing group, its
  `from_email`/`from_domain` is upserted into `SenderAlias` and the
  alias-level `email_count` is incremented.
- Whitelisted senders are still scanned and counted (so the user has
  accurate stats), they just don't appear in the default view.

## 5. Unsubscribe flow

The "smart suggestion" presents the user with the best available method
and lets them confirm before anything is executed.

**On the sender detail page:**
1. Show parsed methods, ranked:
   - **Recommended:** RFC 8058 one-click POST, if `List-Unsubscribe-Post` header
     was seen and an HTTPS URL is present.
   - HTTP link (regular GET).
   - mailto link.
2. Click → confirmation modal showing exact URL & method:
   > "POST to `https://list.example.com/u/abc123`. Continue?"
3. On confirm:
   - **One-click:** server sends `POST` with body
     `List-Unsubscribe=One-Click`, content-type
     `application/x-www-form-urlencoded`, 15-second timeout. 2xx →
     `Sender.status = unsubscribed`, write `Action(kind=unsubscribe_one_click,
     status=success)`. Non-2xx → status `failed`, the user sees the response
     code & body excerpt and can retry as a regular HTTP link.
   - **HTTP link:** open in a new browser tab via `target="_blank"`. Sender
     status becomes `unsubscribed` only after the user explicitly confirms
     "Yes, that worked" (button in the modal). Default = no status change.
   - **Mailto:** generate `mailto:` URL with subject `Unsubscribe` and body
     from the parsed mailto, open via `target="_blank"`. Same explicit
     "I sent it" confirmation rule.
4. Whichever path: an `Action` row records the attempt with full detail.

The one confirmation gate handles "double-check we have the right link";
the URL/method shown in the modal is exactly what gets executed (no
hidden redirects from our end — the remote server can still redirect).

## 6. Bulk inbox actions

Per sender (or domain group), user can:
- **Archive existing** — move to the provider's Archive folder, all
  mailboxes scanned. (For IMAP without a clear Archive: fall back to
  marking read in place; surface this in the confirmation step.)
- **Move to Trash** — move to the provider's Trash folder.
- **Mark as read** — flag-only mutation, no move.

**Flow:**
1. User picks action on sender detail.
2. Server runs a quick `count_by_sender(group)` query against the provider
   (no mutation yet) and shows a confirmation:
   > "This will move 142 messages from `*@example.com` across INBOX, Promotions,
   > and Updates to Trash. Continue?"
3. On confirm, a `Job` is created with status `queued` and the user is
   redirected to the sender page with a live progress fragment (HTMX poll).
4. The `bulk_action` job iterates batches of 50 messages, calls
   `move_messages`, updates `progress_done` after each batch.
5. On completion, an `Action` row records the result; the sender status
   becomes `trashed` (if all messages moved successfully) and the sender
   leaves the default view.

**Safety:**
- Trash is the destination, not expunge. User can recover via their mail
  client for the provider-defined retention window.
- A single in-process lock per `(account_id, sender_id)` prevents two
  concurrent bulk actions on the same target.
- All bulk actions are paginated and resumable: the job stores
  `last_processed_uid` per mailbox so a restart picks up where it left off
  on next manual retry (status moves from `failed` back to `queued`).

## 7. Whitelist

- A sender is whitelisted by setting `Sender.status = whitelisted` and
  `Sender.whitelist_scope = sender | domain`.
- Domain whitelist (`scope = domain`) suppresses every sender whose
  `from_domain` matches, including future ones.
- Default view filters out `whitelisted` and `unsubscribed`/`trashed`.
- A separate "Whitelist" tab lists everything that is whitelisted, with
  an "unwhitelist" button.
- Whitelist is per account: each `Sender` row is per account, so domain
  whitelisting also stays scoped to the account that owns the rule.

## 8. Top-senders view

Default landing page after picking an account:
- Sort by message count within selected period, computed at query time
  from `Message.received_at` (not from the cached `Sender.email_count`,
  which reflects the scan window rather than the user-selected period).
- Period selector: 7d / 30d / 90d / all-time. Default 30d.
- Group toggle: by sender (`group_key`) [default] or by domain (`from_domain`).
- Page size: 50 senders, infinite scroll via HTMX.
- Filters: `status = active`, hides whitelisted and unsubscribed/trashed.
- Card per sender: display name, address(es), count, last-seen, badges
  (one-click supported, mailto-only, etc.), quick "Open" button to detail.

## 9. Jobs & progress

In-process runner (`jobs/runner.py`):
- Uses `asyncio.create_task` to start jobs; keeps a registry of running
  tasks for cancellation.
- Each job function takes a `JobContext` with `update_progress(done,
  total)` and `set_result(...)` helpers; these write through to the `Job`
  row in a separate session.
- One global `asyncio.Semaphore` caps concurrent jobs at 2 (configurable).
- On app startup: `UPDATE jobs SET status='failed', error='interrupted by
  restart' WHERE status='running'`.

Frontend polls `/jobs/{id}/fragment` every 2s via HTMX `hx-trigger="every 2s"`
until `status` is terminal; the fragment then swaps itself for a
final-state card.

## 10. Security

- **Single-user, single-password gate.** A `BU_PASSWORD` env var enables
  a session cookie login (signed via `itsdangerous` or `starlette-session`).
  No registration, no users table.
- **Bind 127.0.0.1 by default**; override with env var for reverse-proxy
  setups. README documents this clearly.
- **Credential encryption.** `services/crypto.py` uses Fernet; key comes
  from `BU_FERNET_KEY` env var (must be a real Fernet key,
  `Fernet.generate_key()` output). On boot, refuse to start if the env
  var is missing or invalid — no silent dev-default key.
- **Outbound HTTP for one-click unsubscribe** is allowed to any host the
  user's mail server told us about; we don't sanitize there. Reasoning:
  the link is in the user's own mail, the user explicitly confirms the
  URL before we POST, and this is a single-user tool.
- **Body preview iframe:** `sandbox` (no `allow-scripts`),
  `referrerpolicy="no-referrer"`, `Content-Security-Policy` blocks
  external requests by default; a "Load remote images" toggle relaxes the
  CSP per-message.
- **CSRF:** all mutating routes require an HTMX request header
  (`HX-Request: true`) plus a session cookie; same-origin-only.

## 11. Deployment

**Dockerfile** (multi-stage, slim):
- Stage 1: install Python deps with `uv` or `pip` into a venv.
- Stage 2: `python:3.12-slim`, copy venv + app code, run as non-root user
  `app`. Expose 8000. Default command:
  `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- Persist data via a volume at `/data` (SQLite DB + body-cache). The app
  reads `BU_DATA_DIR=/data`.

**GitHub Actions** (`.github/workflows/docker.yml`):
- Trigger: `push` to `main`, plus `workflow_dispatch`.
- Steps: checkout → setup buildx → login to GHCR via `GITHUB_TOKEN` →
  `docker/build-push-action` with tags `ghcr.io/<owner>/bulk-unsubscribe:latest`
  and `:sha-<short>`. Build for `linux/amd64` + `linux/arm64`.
- Image manifest signed via `cosign` (optional, nice-to-have).

**Migrations.** Alembic with autogenerate; migrations run on container
startup via a small entrypoint shim before `uvicorn` starts.

## 12. Testing

- `pytest` with two layers:
  - **Unit:** `services/unsubscribe.py`, `services/grouping.py`, header
    parsers — pure-function tests with fixture inputs.
  - **Integration:** `routes/` against an in-memory SQLite + a fake
    `MailProvider` that records calls and returns canned data.
- No live IMAP/JMAP in CI. A separate `tests/manual/` folder has scripts
  for ad-hoc real-account smoke tests.

## 13. Open items / future work

- Sender-merge UI (manual override when `List-ID` grouping fails).
- "Re-scan since last action" CLI for nightly cron.
- Export of unsubscribe history as CSV.
- Multi-user mode (would require a real `User` model and per-user encryption keys).

## 14. Build sequence (high level — feeds into the implementation plan)

1. Project skeleton: `pyproject.toml`, FastAPI app, config, Alembic init.
2. Data model + migrations.
3. `MailProvider` Protocol + IMAP impl with header scan + tests using a fake provider.
4. JMAP impl (chain method calls, RFC 8058 detection).
5. Job runner + scan job + progress fragment.
6. Sender list view + period/grouping toggles.
7. Sender detail + lazy preview (snippet + sandboxed body).
8. Unsubscribe flow with confirmation modal + one-click POST.
9. Bulk archive/trash job + confirmation flow.
10. Whitelist (sender + domain) and Whitelist view.
11. Account management UI.
12. Auth gate + binding defaults + Fernet key enforcement.
13. Dockerfile + GitHub Actions to GHCR.
14. README rewrite.
