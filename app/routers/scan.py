"""Scan routes: trigger a mailbox scan to discover newsletter senders."""

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.crypto import decrypt
from app.database import get_db
from app.models import Account, ProviderType, Sender, SenderStatus
from app.services.fastmail_service import FastmailService
from app.services.imap_service import IMAPService
from app.services.imap_service import SenderInfo as IMAPSenderInfo

router = APIRouter(prefix="/api/scan", tags=["scan"])


class ScanResponse(BaseModel):
    account_id: int
    senders_found: int
    message: str


def _upsert_senders(db: Session, account_id: int, sender_infos) -> int:
    """Insert or update Sender rows for the given account. Returns the count."""
    count = 0
    for info in sender_infos:
        existing = (
            db.query(Sender)
            .filter(Sender.account_id == account_id, Sender.email == info.email)
            .first()
        )
        if existing:
            existing.email_count = max(existing.email_count, info.email_count)
            if info.unsubscribe_link:
                existing.unsubscribe_link = info.unsubscribe_link
            if info.unsubscribe_mailto:
                existing.unsubscribe_mailto = info.unsubscribe_mailto
            if info.last_seen and (
                existing.last_seen is None or info.last_seen > existing.last_seen
            ):
                existing.last_seen = info.last_seen
            if info.first_seen and (
                existing.first_seen is None or info.first_seen < existing.first_seen
            ):
                existing.first_seen = info.first_seen
        else:
            sender = Sender(
                account_id=account_id,
                email=info.email,
                display_name=info.display_name,
                email_count=info.email_count,
                unsubscribe_link=info.unsubscribe_link,
                unsubscribe_mailto=info.unsubscribe_mailto,
                status=SenderStatus.active,
                first_seen=info.first_seen,
                last_seen=info.last_seen,
            )
            db.add(sender)
            count += 1
    db.commit()
    return count


@router.post("/{account_id}", response_model=ScanResponse)
async def scan_account(account_id: int, db: Session = Depends(get_db)):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    credential = decrypt(account.credential) if account.credential else ""

    if account.provider == ProviderType.imap:
        svc = IMAPService(
            account.imap_host,
            account.imap_port,
            account.imap_username,
            credential,
        )
        try:
            svc.connect()
            sender_infos = svc.scan_senders()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"IMAP error: {exc}") from exc
        finally:
            svc.disconnect()

    elif account.provider == ProviderType.fastmail:
        svc_fm = FastmailService(credential)
        try:
            sender_infos = await svc_fm.scan_senders()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Fastmail error: {exc}") from exc
    else:
        raise HTTPException(status_code=400, detail="Unknown provider")

    new_count = _upsert_senders(db, account_id, sender_infos)

    # Update last_scan timestamp
    account.last_scan = datetime.now(timezone.utc)
    db.commit()

    return ScanResponse(
        account_id=account_id,
        senders_found=len(sender_infos),
        message=f"Scan complete. Found {len(sender_infos)} newsletter sender(s), {new_count} new.",
    )
