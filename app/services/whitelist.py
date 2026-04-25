from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.sender import Sender, SenderStatus, WhitelistScope
from app.models.whitelist_rule import WhitelistKind, WhitelistRule
from app.providers.base import ScannedMessage


def load_rules(session: Session, account_id: int) -> list[WhitelistRule]:
    return list(
        session.scalars(
            select(WhitelistRule).where(WhitelistRule.account_id == account_id)
        )
    )


def _mailbox_match(rule_value: str, mailbox: str) -> bool:
    if mailbox == rule_value:
        return True
    return mailbox.startswith(f"{rule_value}/") or mailbox.startswith(f"{rule_value}.")


def is_mailbox_whitelisted(rules: list[WhitelistRule], mailbox: str) -> bool:
    return any(
        r.kind == WhitelistKind.mailbox and _mailbox_match(r.value, mailbox)
        for r in rules
    )


def should_skip_during_scan(
    rules: list[WhitelistRule], msg: ScannedMessage
) -> bool:
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
    were `unsubscribed` or `trashed` are left alone — those are final.
    """
    rules = load_rules(session, account_id)
    senders = list(
        session.scalars(
            select(Sender).where(
                Sender.account_id == account_id,
                Sender.status.in_(
                    [SenderStatus.active, SenderStatus.whitelisted]
                ),
            )
        )
    )
    changed = 0
    for s in senders:
        whitelisted = sender_or_domain_whitelisted(rules, s.from_email, s.from_domain)
        new_status = (
            SenderStatus.whitelisted if whitelisted else SenderStatus.active
        )
        if whitelisted:
            new_scope = (
                WhitelistScope.domain
                if any(
                    r.kind == WhitelistKind.domain
                    and r.value.lower() == s.from_domain.lower()
                    for r in rules
                )
                else WhitelistScope.sender
            )
        else:
            new_scope = WhitelistScope.none
        if s.status != new_status or s.whitelist_scope != new_scope:
            s.status = new_status
            s.whitelist_scope = new_scope
            changed += 1
    session.commit()
    return changed
