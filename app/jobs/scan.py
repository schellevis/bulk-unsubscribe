from datetime import datetime, timezone

from sqlalchemy import func, select, update

from app.db import get_session_factory
from app.jobs.runner import JobContext
from app.models.account import Account
from app.models.message import Message
from app.models.sender import Sender, SenderAlias
from app.providers.base import ScannedMessage
from app.services.grouping import compute_group_key, extract_domain
from app.services.unsubscribe import parse_unsubscribe_methods


async def _collect_scan(
    provider, since: datetime | None, max_messages: int
) -> list[ScannedMessage]:
    out: list[ScannedMessage] = []
    async for msg in provider.scan_headers(since=since, max_messages=max_messages):
        out.append(msg)
    return out


def build_scan_work(*, account_id: int, provider, max_messages: int):
    """Return a JobWork closure that runs a scan for the given account."""

    session_factory = get_session_factory()

    async def work(ctx: JobContext) -> dict:
        with session_factory() as s:
            account = s.get(Account, account_id)
            since = account.last_incremental_scan_at if account else None

        scanned = await _collect_scan(provider, since=since, max_messages=max_messages)
        ctx.set_total(len(scanned))

        by_group: dict[str, list[ScannedMessage]] = {}
        for sm in scanned:
            key = compute_group_key(sm.list_id or "", sm.from_email)
            by_group.setdefault(key, []).append(sm)

        for group_key, group_msgs in by_group.items():
            with session_factory() as s:
                _persist_group(s, account_id, group_key, group_msgs)
                s.commit()
            ctx.advance(len(group_msgs))

        with session_factory() as s:
            now = datetime.now(timezone.utc)
            s.execute(
                update(Account)
                .where(Account.id == account_id)
                .values(
                    last_full_scan_at=now,
                    last_incremental_scan_at=now,
                )
            )
            s.commit()

        return {"messages_seen": len(scanned), "groups": len(by_group)}

    return work


def _persist_group(
    session, account_id: int, group_key: str, msgs: list[ScannedMessage]
) -> None:
    representative = msgs[0]
    domain = representative.from_domain or extract_domain(representative.from_email)

    # Aggregate unsubscribe methods across all messages in the group.
    aggregated_http: str | None = None
    aggregated_mailto: str | None = None
    aggregated_one_click = False
    for sm in msgs:
        m = parse_unsubscribe_methods(sm.list_unsubscribe, sm.list_unsubscribe_post)
        aggregated_http = aggregated_http or m.http_url
        aggregated_mailto = aggregated_mailto or m.mailto_url
        aggregated_one_click = aggregated_one_click or m.one_click

    class _M:
        http_url = aggregated_http
        mailto_url = aggregated_mailto
        one_click = aggregated_one_click

    methods = _M

    sender = session.scalar(
        select(Sender).where(
            Sender.account_id == account_id, Sender.group_key == group_key
        )
    )
    if sender is None:
        sender = Sender(
            account_id=account_id,
            group_key=group_key,
            from_email=representative.from_email,
            from_domain=domain,
            list_id=representative.list_id,
            display_name=representative.display_name,
            unsubscribe_http=methods.http_url,
            unsubscribe_mailto=methods.mailto_url,
            unsubscribe_one_click_post=methods.one_click,
        )
        session.add(sender)
        session.flush()
    else:
        if methods.http_url:
            sender.unsubscribe_http = methods.http_url
        if methods.mailto_url:
            sender.unsubscribe_mailto = methods.mailto_url
        if methods.one_click:
            sender.unsubscribe_one_click_post = True
        if representative.display_name and not sender.display_name:
            sender.display_name = representative.display_name

    for sm in msgs:
        message_existing = session.scalar(
            select(Message).where(
                Message.account_id == account_id,
                Message.provider_uid == sm.ref.provider_uid,
                Message.mailbox == sm.ref.mailbox,
            )
        )
        if message_existing is None:
            session.add(
                Message(
                    account_id=account_id,
                    sender_id=sender.id,
                    provider_uid=sm.ref.provider_uid,
                    mailbox=sm.ref.mailbox,
                    subject=sm.subject,
                    received_at=sm.received_at,
                )
            )
        else:
            message_existing.subject = sm.subject
            message_existing.received_at = sm.received_at

        alias = session.scalar(
            select(SenderAlias).where(
                SenderAlias.sender_id == sender.id,
                SenderAlias.from_email == sm.from_email,
            )
        )
        if alias is None:
            session.add(
                SenderAlias(
                    sender_id=sender.id,
                    from_email=sm.from_email,
                    from_domain=sm.from_domain or extract_domain(sm.from_email),
                    email_count=1,
                )
            )

    session.flush()
    sender.email_count = (
        session.scalar(
            select(func.count(Message.id)).where(Message.sender_id == sender.id)
        )
        or 0
    )

    sender.first_seen_at = session.scalar(
        select(func.min(Message.received_at)).where(Message.sender_id == sender.id)
    )
    sender.last_seen_at = session.scalar(
        select(func.max(Message.received_at)).where(Message.sender_id == sender.id)
    )

    alias_counts: dict[str, int] = {}
    for sm in msgs:
        alias_counts[sm.from_email] = alias_counts.get(sm.from_email, 0) + 1
    for alias_email, count in alias_counts.items():
        alias_row = session.scalar(
            select(SenderAlias).where(
                SenderAlias.sender_id == sender.id,
                SenderAlias.from_email == alias_email,
            )
        )
        if alias_row is None:
            continue
        alias_row.email_count = max(alias_row.email_count, count)
