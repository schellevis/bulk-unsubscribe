from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.jobs.runner import JobRunner
from app.jobs.scan import build_scan_work
from app.models.account import Account, ProviderType
from app.models.job import Job, JobType
from app.providers.imap import IMAPProvider
from app.providers.jmap import JMAPProvider
from app.services.crypto import CredentialCipher

router = APIRouter(tags=["jobs"])
DbSession = Annotated[Session, Depends(get_db)]


def _templates():
    from app.main import templates

    return templates


def _provider_for(account: Account):
    cipher = CredentialCipher.from_settings()
    if account.provider == ProviderType.imap:
        password = cipher.decrypt(account.credential_encrypted)
        return IMAPProvider(
            account.imap_host or "",
            account.imap_port or 993,
            account.imap_username or "",
            password,
        )
    if account.provider == ProviderType.jmap:
        token = cipher.decrypt(account.credential_encrypted)
        return JMAPProvider(api_token=token)
    raise HTTPException(status_code=400, detail="Unknown provider")


_runner: JobRunner | None = None


def _get_runner() -> JobRunner:
    global _runner
    if _runner is None:
        _runner = JobRunner()
    return _runner


def _dispatch_scan_job(job_id: int, account: Account) -> None:
    """Schedule the scan job on the runner. Separate function so tests can patch."""
    provider = _provider_for(account)
    work = build_scan_work(
        account_id=account.id, provider=provider, max_messages=500
    )
    _get_runner().schedule(job_id, work)


@router.post("/accounts/{account_id}/scan", response_class=HTMLResponse)
def start_scan(
    account_id: int, request: Request, db: DbSession
) -> HTMLResponse:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404)

    job_id = JobRunner.create_job(
        db,
        type=JobType.scan,
        account_id=account_id,
        params={"max_messages": 500},
    )
    _dispatch_scan_job(job_id, account)

    job = db.get(Job, job_id)
    return _templates().TemplateResponse(
        request, "fragments/job_progress.html", {"job": job}
    )


@router.get("/jobs/{job_id}/fragment", response_class=HTMLResponse)
def job_fragment(
    job_id: int, request: Request, db: DbSession
) -> HTMLResponse:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404)
    return _templates().TemplateResponse(
        request, "fragments/job_progress.html", {"job": job}
    )
