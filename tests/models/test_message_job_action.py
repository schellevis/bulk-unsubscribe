import json
from datetime import datetime, timezone

from app.models.account import Account, ProviderType
from app.models.action import Action, ActionKind, ActionStatus
from app.models.job import Job, JobStatus, JobType
from app.models.message import Message
from app.models.sender import Sender


def _seed(db):
    account = Account(
        name="A",
        email="a@x.com",
        provider=ProviderType.jmap,
        credential_encrypted="x",
    )
    db.add(account)
    db.commit()
    sender = Sender(
        account_id=account.id,
        group_key="g",
        from_email="a@x.com",
        from_domain="x.com",
    )
    db.add(sender)
    db.commit()
    return account, sender


def test_message_roundtrip(db_session):
    account, sender = _seed(db_session)
    msg = Message(
        account_id=account.id,
        sender_id=sender.id,
        provider_uid="123",
        mailbox="INBOX",
        subject="Hello",
        received_at=datetime.now(timezone.utc),
    )
    db_session.add(msg)
    db_session.commit()
    db_session.refresh(msg)
    assert msg.has_full_body_cached is False


def test_job_with_params_json(db_session):
    account, _ = _seed(db_session)
    job = Job(
        account_id=account.id,
        type=JobType.scan,
        status=JobStatus.queued,
        params_json=json.dumps({"max_messages": 500}),
    )
    db_session.add(job)
    db_session.commit()
    assert job.progress_total == 0
    assert job.progress_done == 0


def test_action_audit(db_session):
    account, sender = _seed(db_session)
    action = Action(
        account_id=account.id,
        sender_id=sender.id,
        kind=ActionKind.unsubscribe_one_click,
        status=ActionStatus.success,
        affected_count=1,
        detail="HTTP 200",
    )
    db_session.add(action)
    db_session.commit()
    assert action.created_at is not None
