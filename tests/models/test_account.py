from datetime import datetime

from app.models.account import Account, ProviderType


def test_create_imap_account(db_session):
    account = Account(
        name="Privé",
        email="me@example.com",
        provider=ProviderType.imap,
        imap_host="imap.example.com",
        imap_port=993,
        imap_username="me",
        credential_encrypted="ciphertext",
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)

    assert account.id is not None
    assert account.provider == ProviderType.imap
    assert isinstance(account.created_at, datetime)


def test_create_jmap_account(db_session):
    account = Account(
        name="Fastmail",
        email="me@fastmail.com",
        provider=ProviderType.jmap,
        credential_encrypted="ciphertext",
    )
    db_session.add(account)
    db_session.commit()

    assert account.imap_host is None
    assert account.last_full_scan_at is None
