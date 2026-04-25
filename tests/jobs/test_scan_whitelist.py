from datetime import UTC, datetime

from aioresponses import aioresponses

from app.jobs.runner import JobRunner
from app.jobs.scan import build_scan_work
from app.models.account import Account, ProviderType
from app.models.job import JobType
from app.models.message import Message
from app.models.sender import Sender, SenderStatus
from app.models.whitelist_rule import WhitelistKind, WhitelistRule
from app.providers.jmap import JMAP_SESSION_URL, JMAPProvider
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
                received_at=datetime(2026, 4, 1, tzinfo=UTC),
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
                received_at=datetime(2026, 4, 2, tzinfo=UTC),
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
                received_at=datetime(2026, 4, 1, tzinfo=UTC),
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


async def test_jmap_scan_skips_messages_in_name_whitelisted_mailbox(db_session, tmp_path):
    """Regression: JMAP whitelist rules must match on human-readable mailbox
    names, not on opaque provider IDs."""
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

    with aioresponses() as mock_http:
        mock_http.get(
            JMAP_SESSION_URL,
            payload={
                "apiUrl": "https://api.example.com/jmap/api",
                "primaryAccounts": {"urn:ietf:params:jmap:mail": "acct1"},
                "accounts": {"acct1": {}},
            },
        )
        mock_http.post(
            "https://api.example.com/jmap/api",
            payload={
                "methodResponses": [
                    [
                        "Mailbox/get",
                        {
                            "list": [
                                {"id": "opaque-inbox-id", "name": "Inbox", "role": "inbox"},
                                {"id": "opaque-promo-id", "name": "Promotions", "role": None},
                            ]
                        },
                        "0",
                    ],
                    ["Mailbox/query", {"ids": ["opaque-inbox-id"]}, "1"],
                    ["Email/query", {"ids": ["e1", "e2"]}, "2"],
                    [
                        "Email/get",
                        {
                            "list": [
                                {
                                    "id": "e1",
                                    "mailboxIds": {"opaque-inbox-id": True},
                                    "from": [{"email": "news@example.com", "name": "News"}],
                                    "subject": "Newsletter",
                                    "receivedAt": "2026-04-01T10:00:00Z",
                                    "header:List-Id:asText": "<news.example.com>",
                                    "header:List-Unsubscribe:asText": "<https://example.com/u/1>",
                                    "header:List-Unsubscribe-Post:asText": None,
                                },
                                {
                                    "id": "e2",
                                    "mailboxIds": {"opaque-promo-id": True},
                                    "from": [{"email": "promo@example.com", "name": "Promo"}],
                                    "subject": "Deal",
                                    "receivedAt": "2026-04-02T10:00:00Z",
                                    "header:List-Id:asText": "<promo.example.com>",
                                    "header:List-Unsubscribe:asText": "<https://example.com/u/2>",
                                    "header:List-Unsubscribe-Post:asText": None,
                                },
                            ]
                        },
                        "3",
                    ],
                ]
            },
        )

        provider = JMAPProvider(api_token="tok")
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
    # e2 (Promotions) must be skipped; only e1 (Inbox) must be stored
    assert len(msgs) == 1
    assert {m.provider_uid for m in msgs} == {"e1"}
