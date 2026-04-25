import pytest
import sqlalchemy.exc

from app.models.account import Account, ProviderType
from app.models.sender import Sender, SenderAlias, SenderStatus, WhitelistScope


def _make_account(db) -> Account:
    a = Account(
        name="A",
        email="a@example.com",
        provider=ProviderType.jmap,
        credential_encrypted="x",
    )
    db.add(a)
    db.commit()
    return a


def test_sender_with_alias(db_session):
    account = _make_account(db_session)
    sender = Sender(
        account_id=account.id,
        group_key="<list.example.com>",
        from_email="news@example.com",
        from_domain="example.com",
        list_id="<list.example.com>",
        display_name="Example News",
        email_count=12,
    )
    db_session.add(sender)
    db_session.commit()

    alias = SenderAlias(
        sender_id=sender.id,
        from_email="news@example.com",
        from_domain="example.com",
        email_count=12,
    )
    db_session.add(alias)
    db_session.commit()
    db_session.refresh(sender)

    assert sender.status == SenderStatus.active
    assert sender.whitelist_scope == WhitelistScope.none
    assert sender.aliases[0].from_email == "news@example.com"


def test_sender_unique_per_account_and_key(db_session):
    account = _make_account(db_session)
    db_session.add(
        Sender(
            account_id=account.id,
            group_key="k1",
            from_email="a@x.com",
            from_domain="x.com",
            display_name="",
        )
    )
    db_session.commit()

    db_session.add(
        Sender(
            account_id=account.id,
            group_key="k1",
            from_email="b@x.com",
            from_domain="x.com",
            display_name="",
        )
    )
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db_session.commit()
