# Bulk Unsubscribe — Actions & Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the action features on top of Plan 1's foundations: rule-based whitelist (sender / domain / mailbox-label), unsubscribe flow with RFC 8058 one-click confirmation, bulk archive/trash jobs across all folders, single-password auth, Dockerfile, and a GitHub Actions workflow that publishes images to GHCR on push to main.

**Architecture:** Re-use the v0.2 stack (FastAPI + SQLAlchemy + HTMX + Jinja). Add one new model (`WhitelistRule`) and one new service module (`whitelist.py`). The unsubscribe and bulk-action features are new routes that dispatch to either a small async service (one-click POST) or a `Job` running on the existing in-process runner (bulk move-messages). Auth is a thin middleware gate using `itsdangerous` session cookies; no User table.

**Tech Stack:** unchanged from Plan 1 (`itsdangerous` was already in `pyproject.toml`).

**Layout additions:**
```
app/
├── models/whitelist_rule.py        # new
├── services/whitelist.py           # new
├── services/unsubscribe_exec.py    # new (HTTP execution; parser stays in unsubscribe.py)
├── jobs/bulk_action.py             # new
├── routes/whitelist.py             # new
├── routes/unsubscribe.py           # new
├── routes/bulk_action.py           # new
├── auth.py                         # new — session gate
└── templates/
    ├── pages/whitelist.html
    ├── pages/login.html
    ├── fragments/unsubscribe_modal.html
    └── fragments/bulk_action_modal.html
Dockerfile
.github/workflows/docker.yml
docker-entrypoint.sh
```

---

## Task 26: WhitelistRule model + migration

**Files:** `app/models/whitelist_rule.py` (new), `app/models/__init__.py` (modify), `tests/models/test_whitelist_rule.py` (new), `alembic/versions/<new>.py` (autogen).

- [ ] **Step 1: Create `app/models/whitelist_rule.py`**

```python
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    DateTime, Enum as SAEnum, ForeignKey, Integer, String,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class WhitelistKind(str, Enum):
    sender = "sender"
    domain = "domain"
    mailbox = "mailbox"


class WhitelistRule(Base):
    __tablename__ = "whitelist_rules"
    __table_args__ = (
        UniqueConstraint("account_id", "kind", "value", name="uq_whitelist_rule"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[WhitelistKind] = mapped_column(
        SAEnum(WhitelistKind, name="whitelist_kind"), nullable=False
    )
    value: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 2: Re-export from `app/models/__init__.py`** — add `WhitelistRule, WhitelistKind`.

- [ ] **Step 3: Create `tests/models/test_whitelist_rule.py`**

```python
import pytest
import sqlalchemy.exc

from app.models.account import Account, ProviderType
from app.models.whitelist_rule import WhitelistKind, WhitelistRule


def _account(db):
    a = Account(name="A", email="a@x.com", provider=ProviderType.jmap, credential_encrypted="x")
    db.add(a); db.commit(); return a


def test_create_rules(db_session):
    a = _account(db_session)
    db_session.add_all([
        WhitelistRule(account_id=a.id, kind=WhitelistKind.sender, value="x@y.com"),
        WhitelistRule(account_id=a.id, kind=WhitelistKind.domain, value="example.com"),
        WhitelistRule(account_id=a.id, kind=WhitelistKind.mailbox, value="Promotions"),
    ])
    db_session.commit()
    rows = db_session.query(WhitelistRule).all()
    assert len(rows) == 3


def test_unique_constraint(db_session):
    a = _account(db_session)
    db_session.add(WhitelistRule(account_id=a.id, kind=WhitelistKind.domain, value="x.com"))
    db_session.commit()
    db_session.add(WhitelistRule(account_id=a.id, kind=WhitelistKind.domain, value="x.com"))
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db_session.commit()
```

- [ ] **Step 4: Generate migration + apply + commit.**

```bash
uv run alembic revision --autogenerate -m "create whitelist_rules"
uv run alembic upgrade head
uv run pytest tests/models/test_whitelist_rule.py -v
git add -A && git commit -m "feat(model): WhitelistRule with kind enum + migration"
```

---

## Task 27: Whitelist service

**Files:** `app/services/whitelist.py`, `tests/services/test_whitelist.py`.

The service answers two questions:
- *During scan:* should this `ScannedMessage` be persisted? (mailbox-rules can skip messages outright).
- *On rule change:* recompute `Sender.status` for senders matching sender/domain rules.

- [ ] **Step 1: Create `app/services/whitelist.py`**

```python
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.sender import Sender, SenderStatus, WhitelistScope
from app.models.whitelist_rule import WhitelistKind, WhitelistRule
from app.providers.base import ScannedMessage


def load_rules(session: Session, account_id: int) -> list[WhitelistRule]:
    return list(session.scalars(
        select(WhitelistRule).where(WhitelistRule.account_id == account_id)
    ))


def _mailbox_match(rule_value: str, mailbox: str) -> bool:
    """Case-sensitive prefix match. Exact-equal or starts-with rule_value+separator."""
    if mailbox == rule_value:
        return True
    # Both '/' and '.' are common IMAP hierarchy delimiters; accept either.
    return mailbox.startswith(f"{rule_value}/") or mailbox.startswith(f"{rule_value}.")


def is_mailbox_whitelisted(rules: list[WhitelistRule], mailbox: str) -> bool:
    return any(
        r.kind == WhitelistKind.mailbox and _mailbox_match(r.value, mailbox)
        for r in rules
    )


def should_skip_during_scan(rules: list[WhitelistRule], msg: ScannedMessage) -> bool:
    """True iff a mailbox-rule excludes this message (skip persistence entirely)."""
    return is_mailbox_whitelisted(rules, msg.ref.mailbox)


def sender_or_domain_whitelisted(
    rules: list[WhitelistRule], from_email: str, from_domain: str
) -> bool:
    fe = from_email.lower()
    fd = from_domain.lower()
    for r in rules:
        if r.kind == WhitelistKind.sender and r.value.lower() == fe:
            return True
        if r.kind == WhitelistKind.domain and r.value.lower() == fd:
            return True
    return False


def recompute_sender_statuses(session: Session, account_id: int) -> int:
    """Apply current rules to all of an account's senders.

    Returns the number of `Sender` rows that changed status. Senders that
    were `unsubscribed` or `trashed` are left alone — those statuses are
    final and not affected by whitelist changes.
    """
    rules = load_rules(session, account_id)
    senders = list(session.scalars(
        select(Sender).where(
            Sender.account_id == account_id,
            Sender.status.in_([SenderStatus.active, SenderStatus.whitelisted]),
        )
    ))
    changed = 0
    for s in senders:
        whitelisted = sender_or_domain_whitelisted(rules, s.from_email, s.from_domain)
        new_status = SenderStatus.whitelisted if whitelisted else SenderStatus.active
        new_scope = (
            WhitelistScope.domain
            if whitelisted and any(
                r.kind == WhitelistKind.domain and r.value.lower() == s.from_domain.lower()
                for r in rules
            )
            else (WhitelistScope.sender if whitelisted else WhitelistScope.none)
        )
        if s.status != new_status or s.whitelist_scope != new_scope:
            s.status = new_status
            s.whitelist_scope = new_scope
            changed += 1
    session.commit()
    return changed
```

- [ ] **Step 2: Create `tests/services/test_whitelist.py`** — unit tests for each pure function plus a recompute-roundtrip.

```python
from app.models.account import Account, ProviderType
from app.models.sender import Sender, SenderStatus, WhitelistScope
from app.models.whitelist_rule import WhitelistKind, WhitelistRule
from app.providers.base import MessageRef, ScannedMessage
from app.services.whitelist import (
    is_mailbox_whitelisted,
    recompute_sender_statuses,
    sender_or_domain_whitelisted,
    should_skip_during_scan,
)
from datetime import datetime, timezone


def _msg(mailbox: str = "INBOX", from_email: str = "x@y.com") -> ScannedMessage:
    return ScannedMessage(
        ref=MessageRef(provider_uid="1", mailbox=mailbox),
        from_email=from_email, from_domain=from_email.split("@", 1)[1],
        display_name="", subject="", received_at=datetime.now(timezone.utc),
        list_id=None, list_unsubscribe="<https://x>", list_unsubscribe_post=None,
    )


def test_mailbox_match_exact_and_prefix():
    assert is_mailbox_whitelisted(
        [WhitelistRule(kind=WhitelistKind.mailbox, value="Promotions")],
        "Promotions",
    ) is True
    assert is_mailbox_whitelisted(
        [WhitelistRule(kind=WhitelistKind.mailbox, value="Newsletters")],
        "Newsletters/Subscribed",
    ) is True
    assert is_mailbox_whitelisted(
        [WhitelistRule(kind=WhitelistKind.mailbox, value="Foo")],
        "Foobar",
    ) is False


def test_should_skip_during_scan():
    rules = [WhitelistRule(kind=WhitelistKind.mailbox, value="Promotions")]
    assert should_skip_during_scan(rules, _msg(mailbox="Promotions")) is True
    assert should_skip_during_scan(rules, _msg(mailbox="INBOX")) is False


def test_sender_and_domain_match_case_insensitive():
    rules = [
        WhitelistRule(kind=WhitelistKind.sender, value="News@Example.com"),
        WhitelistRule(kind=WhitelistKind.domain, value="VENDOR.com"),
    ]
    assert sender_or_domain_whitelisted(rules, "news@example.com", "example.com") is True
    assert sender_or_domain_whitelisted(rules, "shop@vendor.com", "vendor.com") is True
    assert sender_or_domain_whitelisted(rules, "joe@friend.com", "friend.com") is False


def test_recompute_marks_active_senders_whitelisted_and_unmarks(db_session):
    a = Account(name="A", email="a@x.com", provider=ProviderType.jmap, credential_encrypted="x")
    db_session.add(a); db_session.commit()
    s_match = Sender(account_id=a.id, group_key="g1", from_email="news@example.com",
                     from_domain="example.com", display_name="")
    s_other = Sender(account_id=a.id, group_key="g2", from_email="other@friend.com",
                     from_domain="friend.com", display_name="")
    db_session.add_all([s_match, s_other]); db_session.commit()

    db_session.add(WhitelistRule(account_id=a.id, kind=WhitelistKind.domain, value="example.com"))
    db_session.commit()
    assert recompute_sender_statuses(db_session, a.id) == 1
    db_session.refresh(s_match); db_session.refresh(s_other)
    assert s_match.status == SenderStatus.whitelisted
    assert s_match.whitelist_scope == WhitelistScope.domain
    assert s_other.status == SenderStatus.active

    # Remove the rule and recompute → s_match goes back to active.
    db_session.query(WhitelistRule).delete()
    db_session.commit()
    assert recompute_sender_statuses(db_session, a.id) == 1
    db_session.refresh(s_match)
    assert s_match.status == SenderStatus.active
    assert s_match.whitelist_scope == WhitelistScope.none
```

- [ ] **Step 3: Run + commit.**

```bash
uv run pytest tests/services/test_whitelist.py -v
git add -A && git commit -m "feat(services): whitelist rules engine + recompute"
```

---

## Task 28: Wire whitelist into scan job

**Files:** `app/jobs/scan.py` (modify), `tests/jobs/test_scan_whitelist.py` (new).

Update `build_scan_work` so it loads rules once at the start and skips messages caught by mailbox rules. After persisting, call `recompute_sender_statuses` so newly-created senders get the correct status if a sender/domain rule applies.

- [ ] **Step 1: Modify `app/jobs/scan.py`**

In the `work` closure:

```python
from app.services.whitelist import (
    load_rules, recompute_sender_statuses, should_skip_during_scan,
)

# inside work():
with session_factory() as s:
    rules = load_rules(s, account_id)
scanned = await _collect_scan(provider, since=since, max_messages=max_messages)
scanned = [m for m in scanned if not should_skip_during_scan(rules, m)]
ctx.set_total(len(scanned))
# ... persist groups as before ...
with session_factory() as s:
    recompute_sender_statuses(s, account_id)
```

- [ ] **Step 2: Create `tests/jobs/test_scan_whitelist.py`** — re-use the `FakeMailProvider` from `tests/fakes`. Seed two mailbox-tagged messages and assert the Promotions one is not stored.

```python
from datetime import datetime, timezone

from app.jobs.runner import JobRunner
from app.jobs.scan import build_scan_work
from app.models.account import Account, ProviderType
from app.models.job import JobType
from app.models.message import Message
from app.models.whitelist_rule import WhitelistKind, WhitelistRule
from tests.fakes.mail_provider import FakeMailProvider, FakeMessage


async def test_scan_skips_mailbox_whitelisted(db_session, tmp_path):
    db_url = f"sqlite:///{tmp_path}/bulk-unsubscribe.db"
    a = Account(name="A", email="a@x.com", provider=ProviderType.jmap, credential_encrypted="x")
    db_session.add(a); db_session.commit()
    db_session.add(WhitelistRule(account_id=a.id, kind=WhitelistKind.mailbox, value="Promotions"))
    db_session.commit()

    provider = FakeMailProvider(messages=[
        FakeMessage(uid="1", mailbox="INBOX", from_email="news@example.com",
                    display_name="N", subject="A",
                    received_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
                    list_id="<a>", list_unsubscribe="<https://x>",
                    list_unsubscribe_post=None, body=b"", snippet=""),
        FakeMessage(uid="2", mailbox="Promotions", from_email="promo@example.com",
                    display_name="P", subject="B",
                    received_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
                    list_id="<b>", list_unsubscribe="<https://y>",
                    list_unsubscribe_post=None, body=b"", snippet=""),
    ])
    job_id = JobRunner.create_job(db_session, type=JobType.scan, account_id=a.id, params=None)
    runner = JobRunner(database_url=db_url)
    await runner.run(job_id, build_scan_work(account_id=a.id, provider=provider, max_messages=50))

    db_session.expire_all()
    msgs = db_session.query(Message).filter_by(account_id=a.id).all()
    assert {m.provider_uid for m in msgs} == {"1"}
```

- [ ] **Step 3: Run + commit.**

---

## Task 29: Whitelist routes + UI

**Files:** `app/routes/whitelist.py`, `app/templates/pages/whitelist.html`, `tests/routes/test_whitelist_routes.py`. Add nav link in `base.html`.

Routes:
- `GET /whitelist?account_id=N` — list rules grouped by kind, plus a small "potentially affected" sender count per rule.
- `POST /whitelist?account_id=N` — form posts a `kind` and `value`; create rule then `recompute_sender_statuses`. Redirect back.
- `POST /whitelist/{rule_id}/delete` — delete + recompute. Redirect back.

Re-use `_provider_for_account` only for the optional "Suggest mailboxes" feature (out of v0.2.x scope; pre-fill with INBOX/Promotions/Updates as text).

- [ ] **Step 1: Create `app/routes/whitelist.py`**

```python
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.account import Account
from app.models.sender import Sender
from app.models.whitelist_rule import WhitelistKind, WhitelistRule
from app.services.whitelist import recompute_sender_statuses

router = APIRouter(prefix="/whitelist", tags=["whitelist"])


def _templates():
    from app.main import templates
    return templates


@router.get("", response_class=HTMLResponse)
def list_rules(
    request: Request,
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    accounts = db.execute(select(Account).order_by(Account.created_at)).scalars().all()
    if account_id is None and accounts:
        account_id = accounts[0].id
    selected = db.get(Account, account_id) if account_id else None
    rules: list[WhitelistRule] = []
    affected: dict[int, int] = {}
    if selected:
        rules = list(db.scalars(
            select(WhitelistRule).where(WhitelistRule.account_id == selected.id)
            .order_by(WhitelistRule.kind, WhitelistRule.value)
        ))
        for r in rules:
            if r.kind == WhitelistKind.sender:
                cnt = db.scalar(
                    select(func.count(Sender.id)).where(
                        Sender.account_id == selected.id,
                        func.lower(Sender.from_email) == r.value.lower(),
                    )
                ) or 0
            elif r.kind == WhitelistKind.domain:
                cnt = db.scalar(
                    select(func.count(Sender.id)).where(
                        Sender.account_id == selected.id,
                        func.lower(Sender.from_domain) == r.value.lower(),
                    )
                ) or 0
            else:
                cnt = 0  # mailbox rules don't map to senders
            affected[r.id] = cnt

    return _templates().TemplateResponse(
        request, "pages/whitelist.html",
        {"accounts": accounts, "selected_account": selected,
         "rules": rules, "affected": affected, "kinds": list(WhitelistKind)},
    )


@router.post("")
def create_rule(
    account_id: int = Form(...),
    kind: WhitelistKind = Form(...),
    value: str = Form(...),
    db: Session = Depends(get_db),
):
    if not db.get(Account, account_id):
        raise HTTPException(status_code=404)
    value = value.strip()
    if not value:
        raise HTTPException(status_code=400, detail="value required")
    existing = db.scalar(
        select(WhitelistRule).where(
            WhitelistRule.account_id == account_id,
            WhitelistRule.kind == kind,
            WhitelistRule.value == value,
        )
    )
    if not existing:
        db.add(WhitelistRule(account_id=account_id, kind=kind, value=value))
        db.commit()
        recompute_sender_statuses(db, account_id)
    return RedirectResponse(url=f"/whitelist?account_id={account_id}", status_code=303)


@router.post("/{rule_id}/delete")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.get(WhitelistRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404)
    account_id = rule.account_id
    db.delete(rule)
    db.commit()
    recompute_sender_statuses(db, account_id)
    return RedirectResponse(url=f"/whitelist?account_id={account_id}", status_code=303)
```

- [ ] **Step 2: Create `app/templates/pages/whitelist.html`**

```jinja
{% extends "base.html" %}
{% block title %}Whitelist — Bulk Unsubscribe{% endblock %}
{% block content %}
<form method="get" action="/whitelist" class="card">
  <select name="account_id">
    {% for a in accounts %}
    <option value="{{ a.id }}" {% if selected_account and selected_account.id == a.id %}selected{% endif %}>{{ a.name }} ({{ a.email }})</option>
    {% endfor %}
  </select>
  <button type="submit">Switch</button>
</form>

{% if selected_account %}
<h2>Whitelist for {{ selected_account.email }}</h2>
{% if rules %}
{% for r in rules %}
<div class="card flex between">
  <div>
    <strong>{{ r.kind.value }}</strong>: {{ r.value }}
    <div class="muted">{{ affected.get(r.id, 0) }} matching sender(s)</div>
  </div>
  <form method="post" action="/whitelist/{{ r.id }}/delete">
    <button class="secondary" type="submit"
            onclick="return confirm('Remove this whitelist rule?')">Remove</button>
  </form>
</div>
{% endfor %}
{% else %}
<p class="muted">No whitelist rules yet.</p>
{% endif %}

<h3>Add rule</h3>
<form method="post" action="/whitelist" class="card">
  <input type="hidden" name="account_id" value="{{ selected_account.id }}">
  <div class="field">
    <label>Kind</label>
    <select name="kind">
      {% for k in kinds %}
      <option value="{{ k.value }}">{{ k.value }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="field">
    <label>Value (email, domain, or mailbox/label name — sub-folders match by prefix)</label>
    <input name="value" required>
  </div>
  <button type="submit">Add rule</button>
</form>
{% endif %}
{% endblock %}
```

- [ ] **Step 3: Add nav link** to `app/templates/base.html`:
```html
<a href="/whitelist">Whitelist</a>
```

- [ ] **Step 4: Wire router** in `app/main.py`:
```python
from app.routes import whitelist as whitelist_routes
app.include_router(whitelist_routes.router)
```

- [ ] **Step 5: Tests** — `tests/routes/test_whitelist_routes.py` covering: list page renders, POST creates a rule and recomputes statuses, DELETE removes and recomputes.

```python
from fastapi.testclient import TestClient

from app.main import app
from app.models.account import Account, ProviderType
from app.models.sender import Sender, SenderStatus
from app.models.whitelist_rule import WhitelistKind, WhitelistRule


def _account(db):
    a = Account(name="A", email="a@x.com", provider=ProviderType.jmap, credential_encrypted="x")
    db.add(a); db.commit(); return a


def test_list_whitelist_empty_renders(db_session):
    a = _account(db_session)
    with TestClient(app) as c:
        r = c.get(f"/whitelist?account_id={a.id}")
    assert r.status_code == 200
    assert "No whitelist rules" in r.text


def test_create_rule_marks_sender_whitelisted(db_session):
    a = _account(db_session)
    s = Sender(account_id=a.id, group_key="g", from_email="x@y.com",
               from_domain="y.com", display_name="")
    db_session.add(s); db_session.commit()
    with TestClient(app) as c:
        r = c.post("/whitelist", data={
            "account_id": a.id, "kind": "domain", "value": "Y.com",
        }, follow_redirects=False)
    assert r.status_code in (303, 200)
    db_session.expire_all()
    s = db_session.query(Sender).filter_by(id=s.id).one()
    assert s.status == SenderStatus.whitelisted


def test_delete_rule_unmarks(db_session):
    a = _account(db_session)
    s = Sender(account_id=a.id, group_key="g", from_email="x@y.com",
               from_domain="y.com", display_name="", status=SenderStatus.whitelisted)
    db_session.add(s)
    rule = WhitelistRule(account_id=a.id, kind=WhitelistKind.domain, value="y.com")
    db_session.add(rule); db_session.commit()
    with TestClient(app) as c:
        r = c.post(f"/whitelist/{rule.id}/delete", follow_redirects=False)
    assert r.status_code in (303, 200)
    db_session.expire_all()
    s = db_session.query(Sender).filter_by(id=s.id).one()
    assert s.status == SenderStatus.active
```

- [ ] **Step 6: Run + commit.**

---

## Task 30: IMAP search_by_sender + move_messages

**Files:** `app/providers/imap.py` (modify), `tests/providers/test_imap_search_move.py` (new).

`search_by_sender` does an IMAP `SEARCH FROM "<addr>"` per (mailbox, address) pair. `move_messages` resolves the destination via `list_mailboxes()`'s special-use roles and uses `UID MOVE` (RFC 6851) when available, falling back to `UID COPY` + flag `\Deleted`.

- [ ] **Step 1: Modify `app/providers/imap.py`** — replace the two `NotImplementedError` stubs:

```python
def _search_by_sender_sync(
    self, query: SenderQuery, mailboxes: list[str] | None
) -> list[MessageRef]:
    conn = self._connect()
    try:
        boxes_to_check: list[str]
        if mailboxes is not None:
            boxes_to_check = mailboxes
        else:
            status, lines = conn.list()
            boxes_to_check = []
            if status == "OK" and lines:
                for raw in lines:
                    if raw is None:
                        continue
                    m = _LIST_RE.match(raw)
                    if m:
                        boxes_to_check.append(
                            m.group("name").decode("utf-8", errors="replace")
                        )

        results: list[MessageRef] = []
        for mb in boxes_to_check:
            try:
                conn.select(mb, readonly=True)
            except Exception:  # noqa: BLE001
                continue
            for addr in query.from_emails:
                status, data = conn.uid("SEARCH", None, "FROM", f'"{addr}"')
                if status != "OK" or not data or not data[0]:
                    continue
                for uid in data[0].split():
                    results.append(
                        MessageRef(provider_uid=uid.decode(), mailbox=mb)
                    )
        return results
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass


def _move_messages_sync(
    self, refs: list[MessageRef], destination: SpecialFolder
) -> MoveResult:
    if not refs:
        return MoveResult(moved=0, failed=0, errors=[])

    conn = self._connect()
    try:
        # Discover destination mailbox name from special-use flags.
        target_name: str | None = None
        status, lines = conn.list()
        if status == "OK" and lines:
            for raw in lines:
                if raw is None:
                    continue
                m = _LIST_RE.match(raw)
                if not m:
                    continue
                name = m.group("name").decode("utf-8", errors="replace")
                role = _decode_role(m.group("flags"), name)
                if role == destination:
                    target_name = name
                    break
        if target_name is None:
            target_name = {
                SpecialFolder.archive: "Archive",
                SpecialFolder.trash: "Trash",
            }.get(destination)
        if target_name is None:
            return MoveResult(moved=0, failed=len(refs),
                              errors=["No destination folder discovered"])

        # Group refs by source mailbox.
        by_mb: dict[str, list[str]] = {}
        for r in refs:
            by_mb.setdefault(r.mailbox, []).append(r.provider_uid)

        moved = 0
        errors: list[str] = []
        for mb, uids in by_mb.items():
            try:
                conn.select(mb)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"select {mb!r}: {exc}")
                continue
            uid_set = ",".join(uids).encode()
            # Try MOVE first (RFC 6851). Fall back to COPY+STORE+EXPUNGE.
            move_status, _ = conn.uid("MOVE", uid_set, target_name)
            if move_status == "OK":
                moved += len(uids)
                continue
            copy_status, _ = conn.uid("COPY", uid_set, target_name)
            if copy_status == "OK":
                conn.uid("STORE", uid_set, "+FLAGS", r"(\Deleted)")
                conn.expunge()
                moved += len(uids)
            else:
                errors.append(f"copy {mb!r} failed")
        return MoveResult(moved=moved, failed=len(refs) - moved, errors=errors)
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass


async def search_by_sender(  # type: ignore[override]
    self, query: SenderQuery, mailboxes: list[str] | None = None
) -> AsyncIterator[MessageRef]:
    refs = await asyncio.to_thread(self._search_by_sender_sync, query, mailboxes)
    for r in refs:
        yield r


async def move_messages(
    self, refs: list[MessageRef], destination: SpecialFolder
) -> MoveResult:
    return await asyncio.to_thread(self._move_messages_sync, refs, destination)
```

- [ ] **Step 2: Tests** — `tests/providers/test_imap_search_move.py` mocks `imaplib.IMAP4_SSL` and verifies that `MOVE` was called with the right UIDs + target name.

```python
from unittest.mock import MagicMock, patch

from app.providers.base import MessageRef, SenderQuery, SpecialFolder
from app.providers.imap import IMAPProvider


def _conn():
    c = MagicMock()
    c.login.return_value = ("OK", [b"ok"])
    c.list.return_value = (
        "OK",
        [
            b'(\\HasNoChildren) "/" "INBOX"',
            b'(\\HasNoChildren \\Trash) "/" "Trash"',
        ],
    )
    c.select.return_value = ("OK", [b"42"])
    return c


async def test_search_by_sender_collects_uids():
    c = _conn()
    def uid(*args):
        if args[0] == "SEARCH":
            return ("OK", [b"1 2 3"])
        return ("BAD", [])
    c.uid.side_effect = uid
    with patch("app.providers.imap.imaplib.IMAP4_SSL", return_value=c):
        provider = IMAPProvider("h", 993, "u", "p")
        refs = [r async for r in provider.search_by_sender(
            SenderQuery(from_emails=["news@example.com"]), mailboxes=["INBOX"]
        )]
    assert {r.provider_uid for r in refs} == {"1", "2", "3"}
    assert all(r.mailbox == "INBOX" for r in refs)


async def test_move_messages_uses_move_when_supported():
    c = _conn()
    def uid(*args):
        if args[0] == "MOVE":
            return ("OK", [b"ok"])
        return ("BAD", [])
    c.uid.side_effect = uid
    with patch("app.providers.imap.imaplib.IMAP4_SSL", return_value=c):
        provider = IMAPProvider("h", 993, "u", "p")
        result = await provider.move_messages(
            [MessageRef(provider_uid="1", mailbox="INBOX"),
             MessageRef(provider_uid="2", mailbox="INBOX")],
            SpecialFolder.trash,
        )
    assert result.moved == 2
    assert result.failed == 0
```

- [ ] **Step 3: Run + commit.**

---

## Task 31: JMAP search_by_sender + move_messages

**Files:** `app/providers/jmap.py` (modify), `tests/providers/test_jmap_search_move.py` (new).

`search_by_sender` chains `Email/query` per address with `from` filter; we OR the address list and walk all mailboxes (no `inMailbox` constraint when `mailboxes is None`). `move_messages` uses `Email/set` with `mailboxIds` patch — set destination to `{dst_id: True}` and remove the source mailbox by setting `mailboxIds/<src_id>` to `null` (JMAP property patch syntax).

- [ ] **Step 1: Modify `app/providers/jmap.py`** — replace the two stubs:

```python
async def search_by_sender(  # type: ignore[override]
    self, query: SenderQuery, mailboxes: list[str] | None = None
) -> AsyncIterator[MessageRef]:
    async with aiohttp.ClientSession() as http:
        if self._api_url is None:
            await self._get_session(http)

        # OR all from-addresses; optionally constrain by mailbox.
        from_filters = [{"from": a} for a in query.from_emails]
        if not from_filters:
            return
        flt: dict = {"operator": "OR", "conditions": from_filters} if len(from_filters) > 1 else from_filters[0]
        if mailboxes:
            flt = {"operator": "AND", "conditions": [
                flt,
                {"operator": "OR", "conditions": [{"inMailbox": mb} for mb in mailboxes]},
            ]}

        payload = {
            "using": _CAPS,
            "methodCalls": [
                ["Email/query",
                 {"accountId": self._account_id, "filter": flt, "limit": 5000},
                 "0"],
                ["Email/get",
                 {"accountId": self._account_id,
                  "#ids": {"resultOf": "0", "name": "Email/query", "path": "/ids"},
                  "properties": ["id", "mailboxIds"]},
                 "1"],
            ],
        }
        async with http.post(self._api_url, json=payload, headers=self._headers) as r:
            r.raise_for_status()
            data = await r.json()

    for em in data["methodResponses"][-1][1].get("list", []):
        for mb_id in (em.get("mailboxIds") or {}).keys():
            yield MessageRef(provider_uid=em["id"], mailbox=mb_id)


async def move_messages(
    self, refs: list[MessageRef], destination: SpecialFolder
) -> MoveResult:
    if not refs:
        return MoveResult(moved=0, failed=0, errors=[])

    async with aiohttp.ClientSession() as http:
        if self._api_url is None:
            await self._get_session(http)

        # Resolve destination mailbox id from role.
        get_payload = {
            "using": _CAPS,
            "methodCalls": [["Mailbox/query",
                             {"accountId": self._account_id,
                              "filter": {"role": destination.value}}, "0"]],
        }
        async with http.post(self._api_url, json=get_payload, headers=self._headers) as r:
            r.raise_for_status()
            data = await r.json()
        ids = data["methodResponses"][0][1].get("ids", [])
        if not ids:
            return MoveResult(moved=0, failed=len(refs),
                              errors=[f"No mailbox with role={destination.value}"])
        dst_id = ids[0]

        # Group refs by JMAP id (provider_uid). The mailbox in MessageRef is the
        # *current* source mailbox id; we patch each one to null.
        by_id: dict[str, set[str]] = {}
        for r in refs:
            by_id.setdefault(r.provider_uid, set()).add(r.mailbox)

        update_obj = {}
        for email_id, src_ids in by_id.items():
            patch = {f"mailboxIds/{dst_id}": True}
            for src in src_ids:
                if src and src != dst_id:
                    patch[f"mailboxIds/{src}"] = None
            update_obj[email_id] = patch

        set_payload = {
            "using": _CAPS,
            "methodCalls": [["Email/set",
                             {"accountId": self._account_id, "update": update_obj}, "0"]],
        }
        async with http.post(self._api_url, json=set_payload, headers=self._headers) as r:
            r.raise_for_status()
            result = await r.json()

    set_resp = result["methodResponses"][0][1]
    updated = set_resp.get("updated") or {}
    not_updated = set_resp.get("notUpdated") or {}
    errors = [f"{eid}: {err.get('description', err)}" for eid, err in not_updated.items()]
    moved = sum(len(by_id[eid]) for eid in updated.keys())
    return MoveResult(moved=moved, failed=len(refs) - moved, errors=errors)
```

- [ ] **Step 2: Tests** — `tests/providers/test_jmap_search_move.py` with `aioresponses` covering both calls and the role→id resolution.

(Boilerplate; mirror the structure of `test_jmap_scan.py`. Assert `moved == len(refs)` on success.)

- [ ] **Step 3: Run + commit.**

---

## Task 32: Bulk action job

**Files:** `app/jobs/bulk_action.py`, `tests/jobs/test_bulk_action_job.py`.

The job receives `account_id`, `sender_id`, and `destination` (`SpecialFolder.archive` or `.trash`). Loads sender + aliases → builds `SenderQuery` → runs `provider.search_by_sender` (no mailbox filter — we want everything from this sender) → calls `provider.move_messages` in batches of 50, advancing progress per batch. On completion, writes an `Action` row and updates `Sender.status` to `unsubscribed` for archive, `trashed` for trash (keeping the existing semantics).

- [ ] **Step 1: Create `app/jobs/bulk_action.py`**

```python
from datetime import datetime, timezone

from sqlalchemy import select

from app.db import get_session_factory
from app.jobs.runner import JobContext
from app.models.action import Action, ActionKind, ActionStatus
from app.models.sender import Sender, SenderAlias, SenderStatus
from app.providers.base import MessageRef, MoveResult, SenderQuery, SpecialFolder

_BATCH = 50


def build_bulk_move_work(*, account_id: int, sender_id: int, provider, destination: SpecialFolder, job_id: int):
    session_factory = get_session_factory()

    async def work(ctx: JobContext) -> dict:
        with session_factory() as s:
            sender = s.get(Sender, sender_id)
            if sender is None:
                raise ValueError(f"Sender {sender_id} not found")
            aliases = list(s.scalars(
                select(SenderAlias).where(SenderAlias.sender_id == sender_id)
            ))
            from_emails = sorted({a.from_email for a in aliases} | {sender.from_email})

        # Stream refs.
        refs: list[MessageRef] = []
        async for ref in provider.search_by_sender(SenderQuery(from_emails=from_emails)):
            refs.append(ref)
        ctx.set_total(len(refs))

        moved_total = 0
        errors: list[str] = []
        for i in range(0, len(refs), _BATCH):
            batch = refs[i : i + _BATCH]
            result: MoveResult = await provider.move_messages(batch, destination)
            moved_total += result.moved
            errors.extend(result.errors)
            ctx.advance(len(batch))

        # Audit + sender state.
        with session_factory() as s:
            kind = ActionKind.archive if destination == SpecialFolder.archive else ActionKind.trash
            status = (
                ActionStatus.success if not errors and moved_total == len(refs)
                else (ActionStatus.partial if moved_total else ActionStatus.failed)
            )
            s.add(Action(
                account_id=account_id, sender_id=sender_id, job_id=job_id,
                kind=kind, status=status, affected_count=moved_total,
                detail="; ".join(errors[:5]) if errors else None,
            ))
            sender = s.get(Sender, sender_id)
            if sender is not None and status in (ActionStatus.success, ActionStatus.partial):
                sender.status = (
                    SenderStatus.trashed if destination == SpecialFolder.trash
                    else SenderStatus.unsubscribed
                )
            s.commit()

        return {"requested": len(refs), "moved": moved_total, "errors": len(errors)}

    return work
```

- [ ] **Step 2: Test** — `tests/jobs/test_bulk_action_job.py` with `FakeMailProvider`. Seed sender + aliases + 3 messages across 2 mailboxes; run trash; assert moved=3 and `Sender.status == trashed`.

- [ ] **Step 3: Run + commit.**

---

## Task 33: Bulk action routes + UI

**Files:** `app/routes/bulk_action.py`, `app/templates/fragments/bulk_action_modal.html`, `app/templates/pages/sender_detail.html` (modify).

Routes:
- `GET /senders/{id}/bulk?destination=trash` — return a modal fragment showing "this will move N messages to Trash" with a confirm button. Server runs a quick `search_by_sender` count to populate N (with a soft cap at e.g. 5000 — JMAP limit is in the search).
- `POST /senders/{id}/bulk?destination=trash` — create job + dispatch + return job-progress fragment.

- [ ] **Step 1: Create `app/routes/bulk_action.py`** following `app/routes/jobs.py` patterns. Use `_provider_for_account` (extract to `app/services/provider_factory.py` to share between modules — see Step 4).

- [ ] **Step 2: Create `app/templates/fragments/bulk_action_modal.html`**:

```jinja
<div class="card">
  <strong>{{ count }}</strong> messages from <strong>{{ sender.display_name or sender.from_email }}</strong>
  will be moved to <strong>{{ destination.value }}</strong>.
  <form method="post" action="/senders/{{ sender.id }}/bulk?destination={{ destination.value }}"
        hx-post="/senders/{{ sender.id }}/bulk?destination={{ destination.value }}"
        hx-target="#bulk-status-{{ sender.id }}" hx-swap="innerHTML">
    <button type="submit" style="margin-top:0.5rem;">Yes, move them</button>
    <button type="button" class="secondary"
            hx-get="" onclick="this.closest('.card').remove()">Cancel</button>
  </form>
</div>
```

- [ ] **Step 3: Add buttons** to `sender_detail.html` above "Recent messages":

```html
<div class="flex" style="margin: 0.5rem 0;">
  <button class="secondary"
          hx-get="/senders/{{ sender.id }}/bulk?destination=archive"
          hx-target="#bulk-status-{{ sender.id }}">Archive all</button>
  <button class="secondary"
          hx-get="/senders/{{ sender.id }}/bulk?destination=trash"
          hx-target="#bulk-status-{{ sender.id }}">Move all to Trash</button>
</div>
<div id="bulk-status-{{ sender.id }}"></div>
```

- [ ] **Step 4: Extract** `_provider_for_account` from `app/routes/senders.py` and `app/routes/jobs.py` into a shared `app/services/provider_factory.py`. Update both call-sites.

- [ ] **Step 5: Test** route happy paths — modal renders count, POST creates a `Job` and the dispatch is called.

- [ ] **Step 6: Run + commit.**

---

## Task 34: Unsubscribe execution service

**Files:** `app/services/unsubscribe_exec.py`, `tests/services/test_unsubscribe_exec.py`.

Performs the actual one-click POST and HTTP GET fallback. Returns a structured result; routes turn it into an `Action` row.

- [ ] **Step 1: Create `app/services/unsubscribe_exec.py`**

```python
from dataclasses import dataclass

import aiohttp


@dataclass
class UnsubscribeResult:
    method: str  # "one_click" | "http" | "mailto"
    success: bool
    status_code: int | None
    detail: str


async def execute_one_click(http_url: str, timeout_s: int = 15) -> UnsubscribeResult:
    """RFC 8058 one-click POST.

    Body: `List-Unsubscribe=One-Click`. Content-Type: form.
    """
    timeout = aiohttp.ClientTimeout(total=timeout_s)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                http_url,
                data={"List-Unsubscribe": "One-Click"},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                allow_redirects=True,
            ) as resp:
                ok = 200 <= resp.status < 400
                return UnsubscribeResult(
                    method="one_click", success=ok, status_code=resp.status,
                    detail=f"HTTP {resp.status} {resp.reason or ''}".strip(),
                )
    except Exception as exc:  # noqa: BLE001
        return UnsubscribeResult(method="one_click", success=False,
                                 status_code=None, detail=f"network error: {exc}")
```

- [ ] **Step 2: Test** `tests/services/test_unsubscribe_exec.py` using `aioresponses` — 200 → success, 500 → failed, ConnectionError → failed.

- [ ] **Step 3: Run + commit.**

---

## Task 35: Unsubscribe routes + UI

**Files:** `app/routes/unsubscribe.py`, `app/templates/fragments/unsubscribe_modal.html`, `app/templates/pages/sender_detail.html` (modify).

Flow:
- `GET /senders/{id}/unsubscribe` — show methods (one-click, http, mailto) with the recommended one highlighted. "Confirm" buttons per method open a confirmation showing the exact URL.
- `POST /senders/{id}/unsubscribe?method=one_click` — execute via `execute_one_click`; on 2xx flip `Sender.status = unsubscribed`, write `Action`, return result fragment.
- `POST /senders/{id}/unsubscribe?method=http` — record an `unsubscribe_http` Action with `status=pending`, return fragment with `target="_blank"` link plus "Yes that worked"/"Didn't work" buttons that PATCH the action status. (For v1 simplicity: just record the click and surface the link; manual confirm can be a follow-up enhancement.)
- `POST /senders/{id}/unsubscribe?method=mailto` — record a `unsubscribe_mailto` Action with `status=success` (we trust the user's mail client), return a `mailto:` link to open.

- [ ] **Step 1: Create `app/routes/unsubscribe.py`**

```python
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.action import Action, ActionKind, ActionStatus
from app.models.sender import Sender, SenderStatus
from app.services.unsubscribe import parse_unsubscribe_methods
from app.services.unsubscribe_exec import execute_one_click

router = APIRouter(tags=["unsubscribe"])

Method = Literal["one_click", "http", "mailto"]


def _templates():
    from app.main import templates
    return templates


@router.get("/senders/{sender_id}/unsubscribe", response_class=HTMLResponse)
def show_unsubscribe(sender_id: int, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    sender = db.get(Sender, sender_id)
    if sender is None:
        raise HTTPException(status_code=404)
    methods = parse_unsubscribe_methods(
        sender.unsubscribe_http and f"<{sender.unsubscribe_http}>",
        "List-Unsubscribe=One-Click" if sender.unsubscribe_one_click_post else None,
    )
    # Add mailto manually since our parser expects bracketed input
    if sender.unsubscribe_mailto and methods.mailto_url is None:
        methods = type(methods)(http_url=methods.http_url,
                                mailto_url=sender.unsubscribe_mailto,
                                one_click=methods.one_click)
    return _templates().TemplateResponse(
        request, "fragments/unsubscribe_modal.html",
        {"sender": sender, "methods": methods,
         "recommended": methods.recommended()},
    )


@router.post("/senders/{sender_id}/unsubscribe", response_class=HTMLResponse)
async def execute_unsubscribe(
    sender_id: int,
    method: Method = Query(...),
    request: Request = None,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    sender = db.get(Sender, sender_id)
    if sender is None:
        raise HTTPException(status_code=404)

    detail = ""
    success = False
    kind = {
        "one_click": ActionKind.unsubscribe_one_click,
        "http": ActionKind.unsubscribe_http,
        "mailto": ActionKind.unsubscribe_mailto,
    }[method]

    if method == "one_click":
        if not sender.unsubscribe_http or not sender.unsubscribe_one_click_post:
            raise HTTPException(status_code=400, detail="One-click not available")
        result = await execute_one_click(sender.unsubscribe_http)
        success = result.success
        detail = result.detail
        if success:
            sender.status = SenderStatus.unsubscribed
    elif method == "http":
        if not sender.unsubscribe_http:
            raise HTTPException(status_code=400)
        success = True  # link surfaced; user confirms in browser
        detail = f"Opened in browser: {sender.unsubscribe_http}"
    else:  # mailto
        if not sender.unsubscribe_mailto:
            raise HTTPException(status_code=400)
        success = True
        detail = f"mailto link: {sender.unsubscribe_mailto}"

    db.add(Action(
        account_id=sender.account_id, sender_id=sender_id, kind=kind,
        status=ActionStatus.success if success else ActionStatus.failed,
        affected_count=1, detail=detail,
    ))
    db.commit()
    db.refresh(sender)

    return _templates().TemplateResponse(
        request, "fragments/unsubscribe_result.html",
        {"sender": sender, "method": method, "success": success, "detail": detail},
    )
```

- [ ] **Step 2: Templates**

`app/templates/fragments/unsubscribe_modal.html`:

```jinja
<div class="card">
  <h3 style="margin-top:0">Unsubscribe options</h3>
  {% if methods.one_click %}
  <form hx-post="/senders/{{ sender.id }}/unsubscribe?method=one_click"
        hx-target="#unsub-status-{{ sender.id }}" hx-swap="innerHTML"
        onsubmit="return confirm('POST one-click to {{ sender.unsubscribe_http }}?');">
    <button type="submit">🟢 One-click POST (recommended)</button>
    <div class="muted">{{ sender.unsubscribe_http }}</div>
  </form>
  {% endif %}
  {% if methods.http_url %}
  <form hx-post="/senders/{{ sender.id }}/unsubscribe?method=http"
        hx-target="#unsub-status-{{ sender.id }}" hx-swap="innerHTML"
        onsubmit="return confirm('Open {{ methods.http_url }} in a new tab?');"
        style="margin-top:0.5rem;">
    <button type="submit" class="secondary">Open HTTP link</button>
    <div class="muted">{{ methods.http_url }}</div>
  </form>
  {% endif %}
  {% if methods.mailto_url %}
  <form hx-post="/senders/{{ sender.id }}/unsubscribe?method=mailto"
        hx-target="#unsub-status-{{ sender.id }}" hx-swap="innerHTML"
        style="margin-top:0.5rem;">
    <button type="submit" class="secondary">Use mailto: link</button>
    <div class="muted">{{ methods.mailto_url }}</div>
  </form>
  {% endif %}
  {% if not methods.http_url and not methods.mailto_url %}
  <em>No unsubscribe methods available for this sender.</em>
  {% endif %}
</div>
```

`app/templates/fragments/unsubscribe_result.html`:

```jinja
<div class="card" style="border-color: {{ 'var(--accent)' if success else 'var(--danger)' }};">
  <strong>{{ "✓ Unsubscribed" if success else "✗ Failed" }}</strong>
  <div class="muted">{{ detail }}</div>
  {% if method == "http" and sender.unsubscribe_http %}
  <a class="btn" href="{{ sender.unsubscribe_http }}" target="_blank" rel="noopener noreferrer">Open the page</a>
  {% endif %}
  {% if method == "mailto" and sender.unsubscribe_mailto %}
  <a class="btn" href="{{ sender.unsubscribe_mailto }}">Open mail client</a>
  {% endif %}
</div>
```

- [ ] **Step 3: Add Unsubscribe button** in `sender_detail.html` near the bulk-action buttons:

```html
<button class="secondary"
        hx-get="/senders/{{ sender.id }}/unsubscribe"
        hx-target="#unsub-status-{{ sender.id }}">Unsubscribe…</button>
...
<div id="unsub-status-{{ sender.id }}"></div>
```

- [ ] **Step 4: Wire router** `app.include_router(unsubscribe_routes.router)`.

- [ ] **Step 5: Tests** — happy path one-click with `aioresponses` mocking the POST; assert `Sender.status` flipped and an `Action` row exists.

- [ ] **Step 6: Run + commit.**

---

## Task 36: Sender list filters out whitelisted/unsubscribed/trashed

Already done structurally — `_query_rows` filters `Sender.status == SenderStatus.active`. Add a "Show whitelisted" toggle to the senders page that flips the filter to include `whitelisted` (read-only — no actions).

- [ ] **Step 1: Modify `app/routes/senders.py`** — accept `show: Literal["active", "whitelisted"] = "active"` and adjust the query filter.

- [ ] **Step 2: Modify `app/templates/pages/senders.html`** — add `<select name="show">` with the two options.

- [ ] **Step 3: Test** — seed an account with one active and one whitelisted sender; assert default view shows only the active one and `?show=whitelisted` shows only the other.

- [ ] **Step 4: Commit.**

---

## Task 37: Auth gate

**Files:** `app/auth.py`, `app/templates/pages/login.html`, `app/main.py` (modify), `app/config.py` (modify).

Add `BU_AUTH_PASSWORD` setting (optional). When set, every request except `/login`, `/healthz`, and `/static/*` requires a signed session cookie. Sessions are signed with `BU_FERNET_KEY` re-used as a Starlette `SessionMiddleware` secret (after a `hashlib.sha256` derivation to avoid leaking the Fernet key bytes directly).

- [ ] **Step 1: Add to `Settings`**

```python
auth_password: str | None = None
```

- [ ] **Step 2: Create `app/auth.py`**

```python
import hashlib
import hmac

from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings


def _session_secret() -> str:
    return hashlib.sha256(get_settings().fernet_key.encode()).hexdigest()


class AuthMiddleware(BaseHTTPMiddleware):
    PUBLIC = {"/login", "/healthz"}

    async def dispatch(self, request: Request, call_next):
        if get_settings().auth_password is None:
            return await call_next(request)
        path = request.url.path
        if path in self.PUBLIC or path.startswith("/static/"):
            return await call_next(request)
        if request.session.get("authed") is True:
            return await call_next(request)
        return RedirectResponse(url=f"/login?next={path}", status_code=303)


def check_password(submitted: str) -> bool:
    expected = get_settings().auth_password or ""
    if not expected:
        return False
    return hmac.compare_digest(submitted, expected)
```

- [ ] **Step 3: Wire** in `app/main.py`:

```python
from starlette.middleware.sessions import SessionMiddleware
from app.auth import AuthMiddleware, _session_secret, check_password
from fastapi import Form, Request
from fastapi.responses import RedirectResponse

app.add_middleware(SessionMiddleware, secret_key=_session_secret(), max_age=60*60*24*30)
app.add_middleware(AuthMiddleware)


@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request, "pages/login.html", {"error": None, "next": request.query_params.get("next", "/")})


@app.post("/login")
def login_submit(request: Request, password: str = Form(...), next: str = Form("/")):
    if check_password(password):
        request.session["authed"] = True
        return RedirectResponse(url=next or "/", status_code=303)
    return templates.TemplateResponse(request, "pages/login.html", {"error": "Wrong password", "next": next}, status_code=401)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
```

- [ ] **Step 4: Login template** `app/templates/pages/login.html`:

```jinja
{% extends "base.html" %}
{% block content %}
<h2>Sign in</h2>
{% if error %}<p style="color: var(--danger);">{{ error }}</p>{% endif %}
<form method="post" action="/login" class="card">
  <input type="hidden" name="next" value="{{ next }}">
  <div class="field"><label>Password</label><input name="password" type="password" required autofocus></div>
  <button type="submit">Sign in</button>
</form>
{% endblock %}
```

- [ ] **Step 5: Tests** — `tests/test_auth.py`:
  - With `BU_AUTH_PASSWORD` unset: all routes are accessible (existing tests still green).
  - With it set: anonymous request to `/` → 303 to `/login`; submitting wrong password → 401; correct → session cookie + redirect; subsequent request to `/` → 200.

- [ ] **Step 6: Commit.**

---

## Task 38: Dockerfile + entrypoint

**Files:** `Dockerfile`, `docker-entrypoint.sh`, `.dockerignore`.

- [ ] **Step 1: Create `Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS builder
ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && cp /root/.local/bin/uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev


FROM python:3.12-slim AS runtime
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /data \
    && chown -R app:app /data
ENV PATH="/opt/venv/bin:$PATH" \
    BU_DATA_DIR=/data
WORKDIR /app
COPY --from=builder --chown=app:app /opt/venv /opt/venv
COPY --from=builder --chown=app:app /app /app
COPY --chmod=0755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
USER app
EXPOSE 8000
VOLUME ["/data"]
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Create `docker-entrypoint.sh`**

```bash
#!/usr/bin/env sh
set -e
alembic upgrade head
exec "$@"
```

- [ ] **Step 3: Create `.dockerignore`**

```
.git
.venv
var
__pycache__
*.pyc
.pytest_cache
.ruff_cache
docs
tests
```

- [ ] **Step 4: Local sanity-build**

```bash
docker build -t bulk-unsubscribe:dev .
```

(Skip running the container in CI for this plan; we just verify it builds.)

- [ ] **Step 5: Commit.**

---

## Task 39: GitHub Actions → GHCR

**Files:** `.github/workflows/docker.yml`.

- [ ] **Step 1: Create the workflow**

```yaml
name: Build and publish image

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  packages: write

jobs:
  docker:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3

      - name: Set up Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}
          tags: |
            type=raw,value=latest,enable={{is_default_branch}}
            type=sha,format=short

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: .
          platforms: linux/amd64,linux/arm64
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

- [ ] **Step 2: Commit.**

The workflow runs only on the GitHub side; locally we just verify YAML syntax with `python -c 'import yaml; yaml.safe_load(open(".github/workflows/docker.yml"))'`.

---

## Task 40: README rewrite

**Files:** `README.md`.

Rewrite for the v1 feature set: connect, scan, browse, preview, unsubscribe (one-click + manual confirm), bulk archive/trash, whitelist (sender / domain / mailbox), single-password auth, Docker. Add a "Pulling the image" section pointing to GHCR.

- [ ] **Step 1: Replace README.** Cover: features, setup (local + Docker), env vars (now including `BU_AUTH_PASSWORD`), tests, deployment to GHCR, security notes.

- [ ] **Step 2: Commit.**

---

## Final verification

- [ ] `uv run pytest -v` — all green (Plan 1 tests + Plan 2 tests).
- [ ] Manual smoke: boot the server, log in, add a test account, scan, view a sender, click "Unsubscribe…" and confirm one-click flow against a mocked endpoint, archive a sender's messages with the FakeProvider via a unit test path.
- [ ] `docker build -t bulk-unsubscribe:dev .` succeeds.
- [ ] `python -c 'import yaml; yaml.safe_load(open(".github/workflows/docker.yml"))'` succeeds.
- [ ] `git push` triggers the workflow on GitHub (verified after-the-fact).
