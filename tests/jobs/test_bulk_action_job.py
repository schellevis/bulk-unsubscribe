from datetime import UTC, datetime

from app.jobs.bulk_action import build_bulk_move_work
from app.jobs.runner import JobRunner
from app.models.account import Account, ProviderType
from app.models.action import Action, ActionStatus
from app.models.job import JobType
from app.models.sender import Sender, SenderAlias, SenderStatus
from app.providers.base import SpecialFolder
from tests.fakes.mail_provider import FakeMailProvider, FakeMessage


async def test_bulk_trash_moves_all_aliases_across_mailboxes(db_session, tmp_path):
    db_url = f"sqlite:///{tmp_path}/bulk-unsubscribe.db"
    a = Account(
        name="A",
        email="a@x.com",
        provider=ProviderType.jmap,
        credential_encrypted="x",
    )
    db_session.add(a)
    db_session.commit()
    sender = Sender(
        account_id=a.id,
        group_key="news.example.com",
        from_email="news@example.com",
        from_domain="example.com",
        display_name="News",
    )
    db_session.add(sender)
    db_session.commit()
    db_session.add_all(
        [
            SenderAlias(
                sender_id=sender.id,
                from_email="news@example.com",
                from_domain="example.com",
            ),
            SenderAlias(
                sender_id=sender.id,
                from_email="news2@example.com",
                from_domain="example.com",
            ),
        ]
    )
    db_session.commit()

    msgs = [
        FakeMessage(
            uid="1",
            mailbox="INBOX",
            from_email="news@example.com",
            display_name="News",
            subject="A",
            received_at=datetime(2026, 4, 1, tzinfo=UTC),
            list_id=None,
            list_unsubscribe="<https://x>",
            list_unsubscribe_post=None,
            body=b"",
            snippet="",
        ),
        FakeMessage(
            uid="2",
            mailbox="Promotions",
            from_email="news2@example.com",
            display_name="News",
            subject="B",
            received_at=datetime(2026, 4, 2, tzinfo=UTC),
            list_id=None,
            list_unsubscribe="<https://x>",
            list_unsubscribe_post=None,
            body=b"",
            snippet="",
        ),
        FakeMessage(
            uid="3",
            mailbox="INBOX",
            from_email="other@example.org",
            display_name="Other",
            subject="C",
            received_at=datetime(2026, 4, 3, tzinfo=UTC),
            list_id=None,
            list_unsubscribe="<https://x>",
            list_unsubscribe_post=None,
            body=b"",
            snippet="",
        ),
    ]
    provider = FakeMailProvider(messages=msgs)

    job_id = JobRunner.create_job(
        db_session,
        type=JobType.bulk_trash,
        account_id=a.id,
        params={"sender_id": sender.id},
    )
    runner = JobRunner(database_url=db_url)
    await runner.run(
        job_id,
        build_bulk_move_work(
            account_id=a.id,
            sender_id=sender.id,
            provider=provider,
            destination=SpecialFolder.trash,
            job_id=job_id,
        ),
    )

    db_session.expire_all()
    sender = db_session.get(Sender, sender.id)
    assert sender.status == SenderStatus.trashed
    actions = db_session.query(Action).filter_by(sender_id=sender.id).all()
    assert len(actions) == 1
    assert actions[0].status == ActionStatus.success
    assert actions[0].affected_count == 2
    # The "other@example.org" message should remain untouched.
    assert msgs[2].mailbox == "INBOX"


async def test_bulk_archive_marks_sender_archived(db_session, tmp_path):
    db_url = f"sqlite:///{tmp_path}/bulk-unsubscribe.db"
    a = Account(
        name="A",
        email="a@x.com",
        provider=ProviderType.jmap,
        credential_encrypted="x",
    )
    db_session.add(a)
    db_session.commit()
    sender = Sender(
        account_id=a.id,
        group_key="news.example.com",
        from_email="news@example.com",
        from_domain="example.com",
        display_name="News",
    )
    db_session.add(sender)
    db_session.commit()
    db_session.add(
        SenderAlias(
            sender_id=sender.id,
            from_email="news@example.com",
            from_domain="example.com",
        )
    )
    db_session.commit()

    msgs = [
        FakeMessage(
            uid="1",
            mailbox="INBOX",
            from_email="news@example.com",
            display_name="News",
            subject="A",
            received_at=datetime(2026, 4, 1, tzinfo=UTC),
            list_id=None,
            list_unsubscribe="<https://x>",
            list_unsubscribe_post=None,
            body=b"",
            snippet="",
        ),
    ]
    provider = FakeMailProvider(messages=msgs)

    job_id = JobRunner.create_job(
        db_session,
        type=JobType.bulk_archive,
        account_id=a.id,
        params={"sender_id": sender.id},
    )
    runner = JobRunner(database_url=db_url)
    await runner.run(
        job_id,
        build_bulk_move_work(
            account_id=a.id,
            sender_id=sender.id,
            provider=provider,
            destination=SpecialFolder.archive,
            job_id=job_id,
        ),
    )

    db_session.expire_all()
    sender = db_session.get(Sender, sender.id)
    # Archiving should set the sender to 'archived', not 'unsubscribed'.
    assert sender.status == SenderStatus.archived
    actions = db_session.query(Action).filter_by(sender_id=sender.id).all()
    assert len(actions) == 1
    assert actions[0].status == ActionStatus.success
    assert actions[0].affected_count == 1
