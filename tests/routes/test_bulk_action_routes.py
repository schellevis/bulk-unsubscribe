from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.account import Account, ProviderType
from app.models.job import Job, JobType
from app.models.sender import Sender


def _seed(db):
    a = Account(
        name="A",
        email="a@x.com",
        provider=ProviderType.jmap,
        credential_encrypted="x",
    )
    db.add(a)
    db.commit()
    s = Sender(
        account_id=a.id,
        group_key="g",
        from_email="news@example.com",
        from_domain="example.com",
        display_name="N",
    )
    db.add(s)
    db.commit()
    return a, s


def test_show_bulk_modal_renders_count(db_session):
    async def fake_search(self, query, mailboxes=None):
        for uid in ["1", "2", "3"]:
            yield type(
                "R", (), {"provider_uid": uid, "mailbox": "INBOX"}
            )()

    with TestClient(app) as c, patch(
        "app.routes.bulk_action.build_provider"
    ) as mk:
        mk.return_value.search_by_sender = lambda query: fake_search(None, query)
        _, sender = _seed(db_session)
        r = c.get(f"/senders/{sender.id}/bulk?destination=trash")
    assert r.status_code == 200
    assert "3" in r.text
    assert "trash" in r.text


def test_show_bulk_modal_renders_when_provider_unreachable(db_session):
    async def failing_search(self, query, mailboxes=None):
        raise OSError("No address associated with hostname")
        yield  # pragma: no cover - make this an async generator

    with TestClient(app) as c, patch(
        "app.routes.bulk_action.build_provider"
    ) as mk:
        mk.return_value.search_by_sender = lambda query: failing_search(None, query)
        _, sender = _seed(db_session)
        r = c.get(f"/senders/{sender.id}/bulk?destination=archive")

    assert r.status_code == 200
    assert "Could not contact mail provider" in r.text
    assert "No address associated with hostname" in r.text
    assert "archive" in r.text


def test_start_bulk_action_creates_job_and_dispatches(db_session):
    with TestClient(app) as c, patch(
        "app.routes.bulk_action._dispatch_bulk_job"
    ) as dispatch:
        dispatch.return_value = None
        _, sender = _seed(db_session)
        r = c.post(f"/senders/{sender.id}/bulk?destination=trash")
    assert r.status_code == 200
    db_session.expire_all()
    job = db_session.query(Job).filter_by(account_id=sender.account_id).one()
    assert job.type == JobType.bulk_trash
    assert dispatch.called
