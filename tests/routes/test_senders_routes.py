from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.account import Account, ProviderType
from app.models.message import Message
from app.models.sender import Sender


def _seed(db) -> Account:
    account = Account(
        name="A",
        email="a@x.com",
        provider=ProviderType.jmap,
        credential_encrypted="x",
    )
    db.add(account)
    db.commit()

    now = datetime.now(UTC)
    senders = [
        Sender(
            account_id=account.id,
            group_key="g.news",
            from_email="news@example.com",
            from_domain="example.com",
            display_name="News",
        ),
        Sender(
            account_id=account.id,
            group_key="g.shop",
            from_email="shop@vendor.com",
            from_domain="vendor.com",
            display_name="Shop",
        ),
    ]
    db.add_all(senders)
    db.commit()

    for i in range(5):
        db.add(
            Message(
                account_id=account.id,
                sender_id=senders[0].id,
                provider_uid=f"n{i}",
                mailbox="INBOX",
                subject=f"News {i}",
                received_at=now - timedelta(days=i),
            )
        )
    db.add(
        Message(
            account_id=account.id,
            sender_id=senders[1].id,
            provider_uid="s1",
            mailbox="INBOX",
            subject="Old shop",
            received_at=now - timedelta(days=400),
        )
    )
    db.commit()
    return account


def test_sender_list_default_30d_orders_by_count(db_session):
    with TestClient(app) as client:
        account = _seed(db_session)
        response = client.get(f"/?account_id={account.id}")
        assert response.status_code == 200
        assert "News" in response.text
        assert "Shop" not in response.text


def test_sender_list_alltime_includes_old(db_session):
    with TestClient(app) as client:
        account = _seed(db_session)
        response = client.get(f"/?account_id={account.id}&period=all")
        assert "Shop" in response.text


def test_sender_list_domain_grouping(db_session):
    with TestClient(app) as client:
        account = _seed(db_session)
        response = client.get(f"/?account_id={account.id}&group=domain&period=all")
    assert "example.com" in response.text
    assert "vendor.com" in response.text
