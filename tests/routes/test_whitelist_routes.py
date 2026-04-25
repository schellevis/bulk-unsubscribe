from fastapi.testclient import TestClient

from app.main import app
from app.models.account import Account, ProviderType
from app.models.sender import Sender, SenderStatus
from app.models.whitelist_rule import WhitelistKind, WhitelistRule


def _account(db):
    a = Account(
        name="A",
        email="a@x.com",
        provider=ProviderType.jmap,
        credential_encrypted="x",
    )
    db.add(a)
    db.commit()
    return a


def test_list_whitelist_empty_renders(db_session):
    with TestClient(app) as c:
        a = _account(db_session)
        r = c.get(f"/whitelist?account_id={a.id}")
    assert r.status_code == 200
    assert "No whitelist rules" in r.text


def test_create_rule_marks_sender_whitelisted(db_session):
    with TestClient(app) as c:
        a = _account(db_session)
        s = Sender(
            account_id=a.id,
            group_key="g",
            from_email="x@y.com",
            from_domain="y.com",
            display_name="",
        )
        db_session.add(s)
        db_session.commit()
        r = c.post(
            "/whitelist",
            data={"account_id": a.id, "kind": "domain", "value": "Y.com"},
            follow_redirects=False,
        )
    assert r.status_code in (303, 200)
    db_session.expire_all()
    s = db_session.query(Sender).filter_by(id=s.id).one()
    assert s.status == SenderStatus.whitelisted


def test_delete_rule_unmarks(db_session):
    with TestClient(app) as c:
        a = _account(db_session)
        s = Sender(
            account_id=a.id,
            group_key="g",
            from_email="x@y.com",
            from_domain="y.com",
            display_name="",
            status=SenderStatus.whitelisted,
        )
        db_session.add(s)
        rule = WhitelistRule(
            account_id=a.id, kind=WhitelistKind.domain, value="y.com"
        )
        db_session.add(rule)
        db_session.commit()
        r = c.post(f"/whitelist/{rule.id}/delete", follow_redirects=False)
    assert r.status_code in (303, 200)
    db_session.expire_all()
    s = db_session.query(Sender).filter_by(id=s.id).one()
    assert s.status == SenderStatus.active
