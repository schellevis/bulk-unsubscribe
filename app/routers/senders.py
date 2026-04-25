"""Sender routes: list senders and manage unsubscribe actions."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Sender, SenderStatus, UnsubscribeAttempt, UnsubscribeStatus

router = APIRouter(prefix="/api/senders", tags=["senders"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class SenderResponse(BaseModel):
    id: int
    account_id: int
    email: str
    display_name: str | None
    email_count: int
    unsubscribe_link: str | None
    unsubscribe_mailto: str | None
    status: SenderStatus
    first_seen: datetime | None
    last_seen: datetime | None

    model_config = {"from_attributes": True}


class UnsubscribeAttemptResponse(BaseModel):
    id: int
    sender_id: int
    attempted_at: datetime
    method: str
    status: UnsubscribeStatus
    response_code: int | None
    response_detail: str | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[SenderResponse])
def list_senders(
    account_id: int | None = None,
    status: SenderStatus | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Sender)
    if account_id is not None:
        query = query.filter(Sender.account_id == account_id)
    if status is not None:
        query = query.filter(Sender.status == status)
    return query.order_by(Sender.email_count.desc()).all()


@router.get("/{sender_id}", response_model=SenderResponse)
def get_sender(sender_id: int, db: Session = Depends(get_db)):
    sender = db.get(Sender, sender_id)
    if not sender:
        raise HTTPException(status_code=404, detail="Sender not found")
    return sender


@router.post("/{sender_id}/unsubscribe", response_model=UnsubscribeAttemptResponse)
async def unsubscribe(sender_id: int, db: Session = Depends(get_db)):
    """
    Attempt to unsubscribe from a sender via its HTTP unsubscribe link.
    Records the attempt and updates the sender status accordingly.
    """
    import aiohttp

    sender = db.get(Sender, sender_id)
    if not sender:
        raise HTTPException(status_code=404, detail="Sender not found")

    if not sender.unsubscribe_link and not sender.unsubscribe_mailto:
        raise HTTPException(
            status_code=422,
            detail="No unsubscribe link available for this sender.",
        )

    method = "http" if sender.unsubscribe_link else "mailto"
    response_code: int | None = None
    response_detail: str | None = None
    attempt_status = UnsubscribeStatus.pending

    if method == "http":
        try:
            async with aiohttp.ClientSession() as http:
                async with http.get(
                    sender.unsubscribe_link,
                    allow_redirects=True,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    response_code = resp.status
                    response_detail = f"HTTP {resp.status} {resp.reason}"
                    attempt_status = (
                        UnsubscribeStatus.success if resp.status < 400 else UnsubscribeStatus.failed
                    )
        except Exception as exc:
            response_detail = str(exc)
            attempt_status = UnsubscribeStatus.failed
    else:
        # mailto: we surface the link so the client can open a mail client
        response_detail = f"mailto unsubscribe: {sender.unsubscribe_mailto}"
        attempt_status = UnsubscribeStatus.success

    attempt = UnsubscribeAttempt(
        sender_id=sender_id,
        method=method,
        status=attempt_status,
        response_code=response_code,
        response_detail=response_detail,
    )
    db.add(attempt)

    if attempt_status == UnsubscribeStatus.success:
        sender.status = SenderStatus.unsubscribed

    db.commit()
    db.refresh(attempt)
    return attempt


@router.patch("/{sender_id}/status", response_model=SenderResponse)
def update_status(sender_id: int, new_status: SenderStatus, db: Session = Depends(get_db)):
    sender = db.get(Sender, sender_id)
    if not sender:
        raise HTTPException(status_code=404, detail="Sender not found")
    sender.status = new_status
    db.commit()
    db.refresh(sender)
    return sender
