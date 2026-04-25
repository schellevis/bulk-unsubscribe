from datetime import UTC, datetime

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


def _msg(mailbox: str = "INBOX", from_email: str = "x@y.com") -> ScannedMessage:
    return ScannedMessage(
        ref=MessageRef(provider_uid="1", mailbox=mailbox),
        from_email=from_email,
        from_domain=from_email.split("@", 1)[1],
        display_name="",
        subject="",
        received_at=datetime.now(UTC),
        list_id=None,
        list_unsubscribe="<https://x>",
        list_unsubscribe_post=None,
    )


def test_mailbox_match_exact_and_prefix():
    assert (
        is_mailbox_whitelisted(
            [WhitelistRule(kind=WhitelistKind.mailbox, value="Promotions")],
            "Promotions",
        )
        is True
    )
    assert (
        is_mailbox_whitelisted(
            [WhitelistRule(kind=WhitelistKind.mailbox, value="Newsletters")],
            "Newsletters/Subscribed",
        )
        is True
    )
    assert (
        is_mailbox_whitelisted(
            [WhitelistRule(kind=WhitelistKind.mailbox, value="Foo")], "Foobar"
        )
        is False
    )


def test_should_skip_during_scan():
    rules = [WhitelistRule(kind=WhitelistKind.mailbox, value="Promotions")]
    assert should_skip_during_scan(rules, _msg(mailbox="Promotions")) is True
    assert should_skip_during_scan(rules, _msg(mailbox="INBOX")) is False


def test_sender_and_domain_match_case_insensitive():
    rules = [
        WhitelistRule(kind=WhitelistKind.sender, value="News@Example.com"),
        WhitelistRule(kind=WhitelistKind.domain, value="VENDOR.com"),
    ]
    assert (
        sender_or_domain_whitelisted(rules, "news@example.com", "example.com")
        is True
    )
    assert (
        sender_or_domain_whitelisted(rules, "shop@vendor.com", "vendor.com")
        is True
    )
    assert (
        sender_or_domain_whitelisted(rules, "joe@friend.com", "friend.com")
        is False
    )


def test_recompute_marks_active_senders_whitelisted_and_unmarks(db_session):
    a = Account(
        name="A",
        email="a@x.com",
        provider=ProviderType.jmap,
        credential_encrypted="x",
    )
    db_session.add(a)
    db_session.commit()
    s_match = Sender(
        account_id=a.id,
        group_key="g1",
        from_email="news@example.com",
        from_domain="example.com",
        display_name="",
    )
    s_other = Sender(
        account_id=a.id,
        group_key="g2",
        from_email="other@friend.com",
        from_domain="friend.com",
        display_name="",
    )
    db_session.add_all([s_match, s_other])
    db_session.commit()

    db_session.add(
        WhitelistRule(account_id=a.id, kind=WhitelistKind.domain, value="example.com")
    )
    db_session.commit()
    assert recompute_sender_statuses(db_session, a.id) == 1
    db_session.refresh(s_match)
    db_session.refresh(s_other)
    assert s_match.status == SenderStatus.whitelisted
    assert s_match.whitelist_scope == WhitelistScope.domain
    assert s_other.status == SenderStatus.active

    db_session.query(WhitelistRule).delete()
    db_session.commit()
    assert recompute_sender_statuses(db_session, a.id) == 1
    db_session.refresh(s_match)
    assert s_match.status == SenderStatus.active
    assert s_match.whitelist_scope == WhitelistScope.none
