from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.account import Account
from app.models.message import Message
from app.models.sender import Sender, SenderStatus
from app.providers.base import MessageRef
from app.services.provider_factory import build_provider as _provider_for_account

router = APIRouter(tags=["senders"])
DbSession = Annotated[Session, Depends(get_db)]

Period = Literal["7d", "30d", "90d", "all"]
Grouping = Literal["sender", "domain"]
ShowMode = Literal["active", "whitelisted"]


def _period_floor(period: Period) -> datetime | None:
    now = datetime.now(UTC)
    if period == "7d":
        return now - timedelta(days=7)
    if period == "30d":
        return now - timedelta(days=30)
    if period == "90d":
        return now - timedelta(days=90)
    return None


def _templates():
    from app.main import templates

    return templates


@router.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    db: DbSession,
    account_id: Annotated[int | None, Query()] = None,
    period: Annotated[Period, Query()] = "30d",
    group: Annotated[Grouping, Query()] = "sender",
    show: Annotated[ShowMode, Query()] = "active",
) -> HTMLResponse:
    accounts = db.execute(select(Account).order_by(Account.created_at)).scalars().all()
    if account_id is None and accounts:
        account_id = accounts[0].id
    selected_account = db.get(Account, account_id) if account_id else None

    rows: list[dict] = []
    if selected_account is not None:
        floor = _period_floor(period)
        rows = _query_rows(db, selected_account.id, floor, group, show)

    context = {
        "accounts": accounts,
        "selected_account": selected_account,
        "rows": rows,
        "period": period,
        "group": group,
        "show": show,
    }
    return _templates().TemplateResponse(request, "pages/senders.html", context)


def _query_rows(
    db: Session,
    account_id: int,
    floor: datetime | None,
    group: Grouping,
    show: ShowMode = "active",
) -> list[dict]:
    msg_filter = [Message.account_id == account_id]
    if floor is not None:
        msg_filter.append(Message.received_at >= floor)

    status_filter = (
        SenderStatus.whitelisted if show == "whitelisted" else SenderStatus.active
    )

    if group == "sender":
        stmt = (
            select(
                Sender.id.label("sender_id"),
                Sender.display_name,
                Sender.from_email,
                Sender.from_domain,
                Sender.unsubscribe_one_click_post,
                func.count(Message.id).label("count"),
                func.max(Message.received_at).label("last_seen"),
            )
            .join(Message, Message.sender_id == Sender.id)
            .where(Sender.account_id == account_id)
            .where(Sender.status == status_filter)
            .where(*msg_filter)
            .group_by(Sender.id)
            .order_by(func.count(Message.id).desc())
            .limit(50)
        )
        return [dict(row._mapping) for row in db.execute(stmt).all()]

    stmt = (
        select(
            Sender.from_domain.label("from_domain"),
            func.count(Message.id).label("count"),
            func.max(Message.received_at).label("last_seen"),
        )
        .join(Message, Message.sender_id == Sender.id)
        .where(Sender.account_id == account_id)
        .where(Sender.status == status_filter)
        .where(*msg_filter)
        .group_by(Sender.from_domain)
        .order_by(func.count(Message.id).desc())
        .limit(50)
    )
    return [dict(row._mapping) for row in db.execute(stmt).all()]


@router.get("/senders/{sender_id}", response_class=HTMLResponse)
def sender_detail(
    sender_id: int, request: Request, db: DbSession
) -> HTMLResponse:
    sender = db.get(Sender, sender_id)
    if sender is None:
        raise HTTPException(status_code=404)
    messages = (
        db.execute(
            select(Message)
            .where(Message.sender_id == sender_id)
            .order_by(Message.received_at.desc())
            .limit(50)
        )
        .scalars()
        .all()
    )
    return _templates().TemplateResponse(
        request,
        "pages/sender_detail.html",
        {"sender": sender, "messages": messages},
    )


@router.get(
    "/senders/{sender_id}/messages/{provider_uid}/preview",
    response_class=HTMLResponse,
)
async def message_preview(
    sender_id: int,
    provider_uid: str,
    request: Request,
    db: DbSession,
) -> HTMLResponse:
    sender = db.get(Sender, sender_id)
    if sender is None:
        raise HTTPException(status_code=404)
    message = db.scalar(
        select(Message).where(
            Message.sender_id == sender_id,
            Message.provider_uid == provider_uid,
        )
    )
    if message is None:
        raise HTTPException(status_code=404)

    snippet = message.snippet
    if not snippet:
        account = db.get(Account, message.account_id)
        provider = _provider_for_account(account)
        snippet = await provider.fetch_snippet(
            MessageRef(provider_uid=provider_uid, mailbox=message.mailbox)
        )
        message.snippet = snippet
        db.commit()

    return _templates().TemplateResponse(
        request,
        "fragments/message_preview.html",
        {"message": message, "snippet": snippet},
    )
