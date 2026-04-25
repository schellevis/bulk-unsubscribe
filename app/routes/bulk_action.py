from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.jobs.bulk_action import build_bulk_move_work
from app.jobs.runner import JobRunner
from app.models.account import Account
from app.models.job import Job, JobType
from app.models.sender import Sender, SenderAlias
from app.providers.base import SenderQuery, SpecialFolder
from app.services.provider_factory import build_provider

router = APIRouter(tags=["bulk_action"])
DbSession = Annotated[Session, Depends(get_db)]

Destination = Literal["archive", "trash"]


def _templates():
    from app.main import templates

    return templates


def _resolve_destination(value: Destination) -> SpecialFolder:
    return SpecialFolder.archive if value == "archive" else SpecialFolder.trash


def _job_type(value: Destination) -> JobType:
    return JobType.bulk_archive if value == "archive" else JobType.bulk_trash


_runner: JobRunner | None = None


def _get_runner() -> JobRunner:
    global _runner
    if _runner is None:
        _runner = JobRunner()
    return _runner


def _dispatch_bulk_job(
    job_id: int, account: Account, sender_id: int, destination: SpecialFolder
) -> None:
    provider = build_provider(account)
    work = build_bulk_move_work(
        account_id=account.id,
        sender_id=sender_id,
        provider=provider,
        destination=destination,
        job_id=job_id,
    )
    _get_runner().schedule(job_id, work)


async def _count_messages(provider, sender: Sender, aliases: list[SenderAlias]) -> int:
    from_emails = sorted({a.from_email for a in aliases} | {sender.from_email})
    count = 0
    async for _ in provider.search_by_sender(SenderQuery(from_emails=from_emails)):
        count += 1
    return count


@router.get("/senders/{sender_id}/bulk", response_class=HTMLResponse)
async def show_bulk_modal(
    sender_id: int,
    destination: Annotated[Destination, Query()],
    request: Request,
    db: DbSession,
) -> HTMLResponse:
    sender = db.get(Sender, sender_id)
    if sender is None:
        raise HTTPException(status_code=404)
    account = db.get(Account, sender.account_id)
    aliases = list(
        db.scalars(select(SenderAlias).where(SenderAlias.sender_id == sender_id))
    )
    provider = build_provider(account)
    count: int | None
    count_error: str | None
    try:
        count = await _count_messages(provider, sender, aliases)
        count_error = None
    except Exception as exc:
        count = None
        count_error = str(exc) or exc.__class__.__name__
    return _templates().TemplateResponse(
        request,
        "fragments/bulk_action_modal.html",
        {
            "sender": sender,
            "destination": _resolve_destination(destination),
            "count": count,
            "count_error": count_error,
        },
    )


@router.post("/senders/{sender_id}/bulk", response_class=HTMLResponse)
def start_bulk_action(
    sender_id: int,
    destination: Annotated[Destination, Query()],
    request: Request,
    db: DbSession,
) -> HTMLResponse:
    sender = db.get(Sender, sender_id)
    if sender is None:
        raise HTTPException(status_code=404)
    account = db.get(Account, sender.account_id)

    job_id = JobRunner.create_job(
        db,
        type=_job_type(destination),
        account_id=account.id,
        params={"sender_id": sender_id, "destination": destination},
    )
    _dispatch_bulk_job(job_id, account, sender_id, _resolve_destination(destination))
    job = db.get(Job, job_id)
    return _templates().TemplateResponse(
        request, "fragments/job_progress.html", {"job": job}
    )
