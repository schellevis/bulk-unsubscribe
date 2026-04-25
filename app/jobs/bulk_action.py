from sqlalchemy import select

from app.db import get_session_factory
from app.jobs.runner import JobContext
from app.models.action import Action, ActionKind, ActionStatus
from app.models.sender import Sender, SenderAlias, SenderStatus
from app.providers.base import MessageRef, MoveResult, SenderQuery, SpecialFolder

_BATCH = 50


def build_bulk_move_work(
    *,
    account_id: int,
    sender_id: int,
    provider,
    destination: SpecialFolder,
    job_id: int,
):
    session_factory = get_session_factory()

    async def work(ctx: JobContext) -> dict:
        with session_factory() as s:
            sender = s.get(Sender, sender_id)
            if sender is None:
                raise ValueError(f"Sender {sender_id} not found")
            aliases = list(
                s.scalars(
                    select(SenderAlias).where(SenderAlias.sender_id == sender_id)
                )
            )
            from_emails = sorted(
                {a.from_email for a in aliases} | {sender.from_email}
            )

        refs: list[MessageRef] = []
        async for ref in provider.search_by_sender(
            SenderQuery(from_emails=from_emails)
        ):
            refs.append(ref)
        ctx.set_total(len(refs))

        moved_total = 0
        errors: list[str] = []
        for i in range(0, len(refs), _BATCH):
            batch = refs[i : i + _BATCH]
            result: MoveResult = await provider.move_messages(batch, destination)
            moved_total += result.moved
            errors.extend(result.errors)
            ctx.advance(len(batch))

        with session_factory() as s:
            kind = (
                ActionKind.archive
                if destination == SpecialFolder.archive
                else ActionKind.trash
            )
            if not errors and moved_total == len(refs):
                status = ActionStatus.success
            elif moved_total > 0:
                status = ActionStatus.partial
            else:
                status = ActionStatus.failed
            s.add(
                Action(
                    account_id=account_id,
                    sender_id=sender_id,
                    job_id=job_id,
                    kind=kind,
                    status=status,
                    affected_count=moved_total,
                    detail="; ".join(errors[:5]) if errors else None,
                )
            )
            sender = s.get(Sender, sender_id)
            if sender is not None and status in (
                ActionStatus.success,
                ActionStatus.partial,
            ):
                sender.status = (
                    SenderStatus.trashed
                    if destination == SpecialFolder.trash
                    else SenderStatus.archived
                )
            s.commit()

        return {
            "requested": len(refs),
            "moved": moved_total,
            "errors": len(errors),
        }

    return work
