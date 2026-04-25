"""Account management routes."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.crypto import decrypt, encrypt
from app.database import get_db
from app.models import Account, ProviderType
from app.services.fastmail_service import FastmailService
from app.services.imap_service import IMAPService

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class IMAPAccountCreate(BaseModel):
    name: str
    email: EmailStr
    imap_host: str
    imap_port: int = 993
    imap_username: str
    password: str


class FastmailAccountCreate(BaseModel):
    name: str
    email: EmailStr
    api_token: str


class AccountResponse(BaseModel):
    id: int
    name: str
    email: str
    provider: ProviderType
    imap_host: str | None
    imap_port: int | None
    imap_username: str | None
    created_at: datetime
    last_scan: datetime | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[AccountResponse])
def list_accounts(db: Session = Depends(get_db)):
    return db.query(Account).all()


@router.get("/{account_id}", response_model=AccountResponse)
def get_account(account_id: int, db: Session = Depends(get_db)):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.post("/imap", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_imap_account(body: IMAPAccountCreate, db: Session = Depends(get_db)):
    # Verify credentials before saving
    svc = IMAPService(body.imap_host, body.imap_port, body.imap_username, body.password)
    if not svc.test_connection():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not connect to IMAP server. Please check your credentials.",
        )

    existing = db.query(Account).filter(Account.email == body.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )

    account = Account(
        name=body.name,
        email=body.email,
        provider=ProviderType.imap,
        imap_host=body.imap_host,
        imap_port=body.imap_port,
        imap_username=body.imap_username,
        credential=encrypt(body.password),
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.post("/fastmail", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_fastmail_account(body: FastmailAccountCreate, db: Session = Depends(get_db)):
    svc = FastmailService(body.api_token)
    if not await svc.test_connection():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not authenticate with Fastmail. Please check your API token.",
        )

    existing = db.query(Account).filter(Account.email == body.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )

    account = Account(
        name=body.name,
        email=body.email,
        provider=ProviderType.fastmail,
        credential=encrypt(body.api_token),
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(account_id: int, db: Session = Depends(get_db)):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    db.delete(account)
    db.commit()
