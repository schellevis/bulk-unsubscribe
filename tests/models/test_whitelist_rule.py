import pytest
import sqlalchemy.exc

from app.models.account import Account, ProviderType
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


def test_create_rules(db_session):
    a = _account(db_session)
    db_session.add_all(
        [
            WhitelistRule(account_id=a.id, kind=WhitelistKind.sender, value="x@y.com"),
            WhitelistRule(account_id=a.id, kind=WhitelistKind.domain, value="example.com"),
            WhitelistRule(account_id=a.id, kind=WhitelistKind.mailbox, value="Promotions"),
        ]
    )
    db_session.commit()
    rows = db_session.query(WhitelistRule).all()
    assert len(rows) == 3


def test_unique_constraint(db_session):
    a = _account(db_session)
    db_session.add(
        WhitelistRule(account_id=a.id, kind=WhitelistKind.domain, value="x.com")
    )
    db_session.commit()
    db_session.add(
        WhitelistRule(account_id=a.id, kind=WhitelistKind.domain, value="x.com")
    )
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db_session.commit()
