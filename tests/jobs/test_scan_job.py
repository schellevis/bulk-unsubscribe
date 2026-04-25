from datetime import UTC, datetime

from app.jobs.runner import JobRunner
from app.jobs.scan import build_scan_work
from app.models.account import Account, ProviderType
from app.models.job import Job, JobStatus, JobType
from app.models.message import Message
from app.models.sender import Sender, SenderAlias
from tests.fakes.mail_provider import FakeMailProvider, FakeMessage


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


async def test_scan_job_creates_senders_and_messages(db_session, tmp_path):
    db_url = f"sqlite:///{tmp_path}/bulk-unsubscribe.db"
    account = _account(db_session)
    provider = FakeMailProvider(
        messages=[
            FakeMessage(
                uid="1",
                mailbox="INBOX",
                from_email="news@example.com",
                display_name="News",
                subject="Hi",
                received_at=datetime(2026, 4, 1, tzinfo=UTC),
                list_id="<news.example.com>",
                list_unsubscribe="<https://example.com/u/1>",
                list_unsubscribe_post="List-Unsubscribe=One-Click",
                body=b"x",
                snippet="x",
            ),
            FakeMessage(
                uid="2",
                mailbox="INBOX",
                from_email="news2@example.com",
                display_name="News2",
                subject="Hi2",
                received_at=datetime(2026, 4, 2, tzinfo=UTC),
                list_id="<news.example.com>",
                list_unsubscribe="<https://example.com/u/2>",
                list_unsubscribe_post=None,
                body=b"x",
                snippet="x",
            ),
        ]
    )

    job_id = JobRunner.create_job(
        db_session,
        type=JobType.scan,
        account_id=account.id,
        params={"max_messages": 50},
    )

    runner = JobRunner(database_url=db_url)
    work = build_scan_work(
        account_id=account.id, provider=provider, max_messages=50
    )
    await runner.run(job_id, work)

    db_session.expire_all()
    job = db_session.get(Job, job_id)
    assert job.status == JobStatus.success
    assert job.progress_done == 2

    senders = db_session.query(Sender).filter_by(account_id=account.id).all()
    assert len(senders) == 1
    sender = senders[0]
    assert sender.group_key == "news.example.com"
    assert sender.unsubscribe_one_click_post is True
    assert sender.email_count == 2

    aliases = db_session.query(SenderAlias).filter_by(sender_id=sender.id).all()
    assert {a.from_email for a in aliases} == {
        "news@example.com",
        "news2@example.com",
    }

    messages = db_session.query(Message).filter_by(account_id=account.id).all()
    assert {m.provider_uid for m in messages} == {"1", "2"}


async def test_scan_job_is_idempotent_on_rerun(db_session, tmp_path):
    db_url = f"sqlite:///{tmp_path}/bulk-unsubscribe.db"
    account = _account(db_session)
    msg = FakeMessage(
        uid="1",
        mailbox="INBOX",
        from_email="news@example.com",
        display_name="News",
        subject="Hi",
        received_at=datetime(2026, 4, 1, tzinfo=UTC),
        list_id="<news.example.com>",
        list_unsubscribe="<https://example.com/u/1>",
        list_unsubscribe_post=None,
        body=b"x",
        snippet="x",
    )
    provider = FakeMailProvider(messages=[msg])
    runner = JobRunner(database_url=db_url)

    for _ in range(2):
        job_id = JobRunner.create_job(
            db_session, type=JobType.scan, account_id=account.id, params=None
        )
        await runner.run(
            job_id,
            build_scan_work(
                account_id=account.id, provider=provider, max_messages=50
            ),
        )

    db_session.expire_all()
    senders = db_session.query(Sender).filter_by(account_id=account.id).all()
    assert len(senders) == 1
    assert senders[0].email_count == 1
    messages = db_session.query(Message).filter_by(account_id=account.id).all()
    assert len(messages) == 1
