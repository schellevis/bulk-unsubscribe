from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.account import Account, ProviderType
from app.models.job import Job, JobStatus, JobType


def _account(db) -> Account:
    a = Account(
        name="A",
        email="a@x.com",
        provider=ProviderType.jmap,
        credential_encrypted="x",
    )
    db.add(a)
    db.commit()
    return a


def test_progress_fragment_renders_running_job(db_session):
    account = _account(db_session)

    with TestClient(app) as client:
        # Lifespan's recover_orphans() ran on startup; create the running job *after* that
        # so the fragment sees it as still running.
        job = Job(
            account_id=account.id,
            type=JobType.scan,
            status=JobStatus.running,
            progress_total=10,
            progress_done=3,
        )
        db_session.add(job)
        db_session.commit()

        response = client.get(f"/jobs/{job.id}/fragment")
        assert response.status_code == 200
        assert "3 / 10" in response.text
        assert "hx-trigger" in response.text


def test_progress_fragment_terminal_stops_polling(db_session):
    account = _account(db_session)
    job = Job(
        account_id=account.id,
        type=JobType.scan,
        status=JobStatus.success,
        progress_total=10,
        progress_done=10,
    )
    db_session.add(job)
    db_session.commit()

    with TestClient(app) as client:
        response = client.get(f"/jobs/{job.id}/fragment")
        assert response.status_code == 200
        assert "hx-trigger" not in response.text


def test_start_scan_creates_job_and_returns_progress_fragment(db_session):
    account = _account(db_session)

    with TestClient(app) as client, patch(
        "app.routes.jobs._dispatch_scan_job"
    ) as dispatch:
        dispatch.return_value = None
        response = client.post(f"/accounts/{account.id}/scan")

    assert response.status_code == 200
    db_session.expire_all()
    job = db_session.query(Job).filter_by(account_id=account.id).one()
    assert job.type == JobType.scan
    assert dispatch.called
