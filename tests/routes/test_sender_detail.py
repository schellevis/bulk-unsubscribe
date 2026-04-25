from datetime import UTC, datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.account import Account, ProviderType
from app.models.message import Message
from app.models.sender import Sender


def _seed(db):
    account = Account(
        name="A",
        email="a@x.com",
        provider=ProviderType.jmap,
        credential_encrypted="x",
    )
    db.add(account)
    db.commit()
    sender = Sender(
        account_id=account.id,
        group_key="g",
        from_email="news@example.com",
        from_domain="example.com",
        display_name="News",
        unsubscribe_http="https://example.com/u",
        unsubscribe_one_click_post=True,
    )
    db.add(sender)
    db.commit()
    for i in range(3):
        db.add(
            Message(
                account_id=account.id,
                sender_id=sender.id,
                provider_uid=f"u{i}",
                mailbox="INBOX",
                subject=f"News {i}",
                received_at=datetime(2026, 4, i + 1, tzinfo=UTC),
            )
        )
    db.commit()
    return account, sender


def test_sender_detail_lists_messages(db_session):
    with TestClient(app) as client:
        _, sender = _seed(db_session)
        response = client.get(f"/senders/{sender.id}")
    assert response.status_code == 200
    assert "News 0" in response.text
    assert "News 2" in response.text
    assert "lazy preview" in response.text.lower() or "hx-get" in response.text


def test_message_preview_fragment_returns_snippet(db_session):
    async def fake_snippet(self, ref):
        return "Hello world preview"

    # Patch the provider factory to bypass credential decryption.
    with TestClient(app) as client, patch(
        "app.providers.jmap.JMAPProvider.fetch_snippet", new=fake_snippet
    ), patch(
        "app.services.provider_factory.CredentialCipher.from_settings"
    ) as cipher_factory:
        cipher_factory.return_value.decrypt.return_value = "fake-token"
        _, sender = _seed(db_session)
        response = client.get(
            f"/senders/{sender.id}/messages/u0/preview"
        )
    assert response.status_code == 200
    assert "Hello world preview" in response.text
