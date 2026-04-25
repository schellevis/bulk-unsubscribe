from aioresponses import aioresponses
from fastapi.testclient import TestClient

from app.main import app
from app.models.account import Account, ProviderType
from app.models.action import Action, ActionStatus
from app.models.sender import Sender, SenderStatus


async def _public_resolver(_host: str) -> set[str]:
    return {"93.184.216.34"}


def _seed(db, *, http=None, mailto=None, one_click=False):
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
        unsubscribe_http=http,
        unsubscribe_mailto=mailto,
        unsubscribe_one_click_post=one_click,
    )
    db.add(s)
    db.commit()
    return a, s


def test_modal_shows_only_available_methods(db_session):
    with TestClient(app) as c:
        _, sender = _seed(db_session, http="https://example.com/u", one_click=True)
        r = c.get(f"/senders/{sender.id}/unsubscribe")
    assert r.status_code == 200
    assert "One-click POST" in r.text
    assert "Open HTTP link" in r.text
    assert "Use mailto" not in r.text


def test_modal_uses_json_escaped_confirm_text(db_session):
    url = "https://example.com/u?next=');alert(1);//"
    with TestClient(app) as c:
        _, sender = _seed(db_session, http=url, one_click=True)
        r = c.get(f"/senders/{sender.id}/unsubscribe")

    assert r.status_code == 200
    assert "return confirm(&#34;POST one-click to " in r.text
    assert "return confirm(&#34;Open " in r.text
    assert "confirm('POST one-click" not in r.text
    assert "confirm('Open " not in r.text


def test_one_click_success_marks_sender_unsubscribed(db_session, monkeypatch):
    url = "https://example.com/u/abc"
    monkeypatch.setattr(
        "app.services.unsubscribe_exec._resolve_host_ips", _public_resolver
    )
    with TestClient(app) as c, aioresponses() as m:
        m.post(url, status=200)
        _, sender = _seed(db_session, http=url, one_click=True)
        r = c.post(f"/senders/{sender.id}/unsubscribe?method=one_click")
    assert r.status_code == 200
    assert "Unsubscribed" in r.text

    db_session.expire_all()
    sender = db_session.get(Sender, sender.id)
    assert sender.status == SenderStatus.unsubscribed
    actions = db_session.query(Action).filter_by(sender_id=sender.id).all()
    assert len(actions) == 1
    assert actions[0].status == ActionStatus.success


def test_one_click_failure_keeps_sender_active(db_session, monkeypatch):
    url = "https://example.com/u/abc"
    monkeypatch.setattr(
        "app.services.unsubscribe_exec._resolve_host_ips", _public_resolver
    )
    with TestClient(app) as c, aioresponses() as m:
        m.post(url, status=500)
        _, sender = _seed(db_session, http=url, one_click=True)
        r = c.post(f"/senders/{sender.id}/unsubscribe?method=one_click")
    assert r.status_code == 200
    assert "Failed" in r.text

    db_session.expire_all()
    sender = db_session.get(Sender, sender.id)
    assert sender.status == SenderStatus.active
