import asyncio

from app.jobs.runner import JobContext, JobRunner
from app.models.account import Account, ProviderType
from app.models.job import Job, JobStatus, JobType


def _make_account(db) -> Account:
    a = Account(
        name="A",
        email="a@x.com",
        provider=ProviderType.jmap,
        credential_encrypted="x",
    )
    db.add(a)
    db.commit()
    return a


async def test_runner_runs_job_to_success(db_session, tmp_path):
    account = _make_account(db_session)
    db_url = f"sqlite:///{tmp_path}/test.db"
    job_id = JobRunner.create_job(
        db_session,
        type=JobType.scan,
        account_id=account.id,
        params={"hello": "world"},
    )

    async def work(ctx: JobContext) -> dict:
        ctx.set_total(3)
        for _ in range(3):
            await asyncio.sleep(0)
            ctx.advance(1)
        return {"done": True}

    runner = JobRunner(database_url=db_url)
    await runner.run(job_id, work)

    db_session.expire_all()
    job = db_session.get(Job, job_id)
    assert job.status == JobStatus.success
    assert job.progress_done == 3
    assert job.progress_total == 3
    assert job.result_json == '{"done": true}'


async def test_runner_marks_job_failed_on_exception(db_session, tmp_path):
    account = _make_account(db_session)
    db_url = f"sqlite:///{tmp_path}/test.db"
    job_id = JobRunner.create_job(
        db_session, type=JobType.scan, account_id=account.id, params=None
    )

    async def boom(ctx: JobContext) -> dict:
        raise RuntimeError("explode")

    runner = JobRunner(database_url=db_url)
    await runner.run(job_id, boom)

    db_session.expire_all()
    job = db_session.get(Job, job_id)
    assert job.status == JobStatus.failed
    assert "explode" in (job.error or "")


def test_recover_running_jobs_marks_them_failed(db_session, tmp_path):
    account = _make_account(db_session)
    db_url = f"sqlite:///{tmp_path}/test.db"
    job = Job(account_id=account.id, type=JobType.scan, status=JobStatus.running)
    db_session.add(job)
    db_session.commit()

    JobRunner.recover_orphans(database_url=db_url)

    db_session.expire_all()
    refreshed = db_session.get(Job, job.id)
    assert refreshed.status == JobStatus.failed
    assert "interrupted by restart" in (refreshed.error or "")
