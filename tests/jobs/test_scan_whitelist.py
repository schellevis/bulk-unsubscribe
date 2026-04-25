from datetime import datetime, timezone

from app.jobs.runner import JobRunner
from app.jobs.scan import build_scan_work
from app.models.account import Account, ProviderType
from app.models.job import JobType
from app.models.message import Message
from app.models.sender import Sender, SenderStatus
from app.models.whitelist_rule import WhitelistKind, WhitelistRule
from tests.fakes.mail_provider import FakeMailProvider, FakeMessage


async def test_scan_skips_mailbox_whitelisted(db_session, tmp_path):
    db_url = f"sqlite:///{tmp_path}/bulk-unsubscribe.db"
    a = Account(
        name="A",
        email="a@x.com",
        provider=ProviderType.jmap,
        credential_encrypted="x",
    )
    db_session.add(a)
    db_session.commit()
    db_session.add(
        WhitelistRule(account_id=a.id, kind=WhitelistKind.mailbox, value="Promotions")
    )
    db_session.commit()

    provider = FakeMailProvider(
        messages=[
            FakeMessage(
                uid="1",
                mailbox="INBOX",
                from_email="news@example.com",
                display_name="N",
                subject="A",
                received_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
                list_id="<a>",
                list_unsubscribe="<https://x>",
                list_unsubscribe_post=None,
                body=b"",
                snippet="",
            ),
            FakeMessage(
                uid="2",
                mailbox="Promotions",
                from_email="promo@example.com",
                display_name="P",
                subject="B",
                received_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
                list_id="<b>",
                list_unsubscribe="<https://y>",
                list_unsubscribe_post=None,
                body=b"",
                snippet="",
            ),
        ]
    )
    job_id = JobRunner.create_job(
        db_session, type=JobType.scan, account_id=a.id, params=None
    )
    runner = JobRunner(database_url=db_url)
    await runner.run(
        job_id,
        build_scan_work(account_id=a.id, provider=provider, max_messages=50),
    )

    db_session.expire_all()
    msgs = db_session.query(Message).filter_by(account_id=a.id).all()
    assert {m.provider_uid for m in msgs} == {"1"}


async def test_scan_marks_domain_whitelisted_after_persist(db_session, tmp_path):
    db_url = f"sqlite:///{tmp_path}/bulk-unsubscribe.db"
    a = Account(
        name="A",
        email="a@x.com",
        provider=ProviderType.jmap,
        credential_encrypted="x",
    )
    db_session.add(a)
    db_session.commit()
    db_session.add(
        WhitelistRule(account_id=a.id, kind=WhitelistKind.domain, value="example.com")
    )
    db_session.commit()

    provider = FakeMailProvider(
        messages=[
            FakeMessage(
                uid="1",
                mailbox="INBOX",
                from_email="news@example.com",
                display_name="N",
                subject="A",
                received_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
                list_id="<a>",
                list_unsubscribe="<https://x>",
                list_unsubscribe_post=None,
                body=b"",
                snippet="",
            ),
        ]
    )
    job_id = JobRunner.create_job(
        db_session, type=JobType.scan, account_id=a.id, params=None
    )
    runner = JobRunner(database_url=db_url)
    await runner.run(
        job_id,
        build_scan_work(account_id=a.id, provider=provider, max_messages=50),
    )

    db_session.expire_all()
    sender = db_session.query(Sender).filter_by(account_id=a.id).one()
    assert sender.status == SenderStatus.whitelisted
