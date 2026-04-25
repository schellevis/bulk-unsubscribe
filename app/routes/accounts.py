from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.account import Account, ProviderType
from app.providers.imap import IMAPProvider
from app.providers.jmap import JMAPProvider
from app.services.crypto import CredentialCipher

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _templates():
    from app.main import templates

    return templates


@router.get("", response_class=HTMLResponse)
def list_accounts(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    accounts = db.execute(
        select(Account).order_by(Account.created_at.desc())
    ).scalars().all()
    return _templates().TemplateResponse(
        request, "pages/accounts.html", {"accounts": accounts}
    )


@router.post("/imap")
async def create_imap_account(
    name: str = Form(...),
    email: EmailStr = Form(...),
    imap_host: str = Form(...),
    imap_port: int = Form(993),
    imap_username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    provider = IMAPProvider(imap_host, imap_port, imap_username, password)
    if not await provider.test_credentials():
        raise HTTPException(status_code=400, detail="IMAP credentials rejected")
    if db.scalar(select(Account).where(Account.email == email)):
        raise HTTPException(status_code=409, detail="Account with this email exists")
    account = Account(
        name=name,
        email=email,
        provider=ProviderType.imap,
        imap_host=imap_host,
        imap_port=imap_port,
        imap_username=imap_username,
        credential_encrypted=CredentialCipher.from_settings().encrypt(password),
    )
    db.add(account)
    db.commit()
    return RedirectResponse(url="/accounts", status_code=303)


@router.post("/jmap")
async def create_jmap_account(
    name: str = Form(...),
    email: EmailStr = Form(...),
    api_token: str = Form(...),
    db: Session = Depends(get_db),
):
    provider = JMAPProvider(api_token=api_token)
    if not await provider.test_credentials():
        raise HTTPException(status_code=400, detail="JMAP token rejected")
    if db.scalar(select(Account).where(Account.email == email)):
        raise HTTPException(status_code=409, detail="Account with this email exists")
    account = Account(
        name=name,
        email=email,
        provider=ProviderType.jmap,
        credential_encrypted=CredentialCipher.from_settings().encrypt(api_token),
    )
    db.add(account)
    db.commit()
    return RedirectResponse(url="/accounts", status_code=303)


@router.post("/{account_id}/delete")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404)
    db.delete(account)
    db.commit()
    return RedirectResponse(url="/accounts", status_code=303)
