from datetime import datetime, timezone

import pytest

from app.providers.base import MessageRef, SenderQuery, SpecialFolder
from tests.fakes.mail_provider import FakeMailProvider, FakeMessage


@pytest.fixture()
def provider() -> FakeMailProvider:
    return FakeMailProvider(
        messages=[
            FakeMessage(
                uid="1",
                mailbox="INBOX",
                from_email="news@example.com",
                display_name="News",
                subject="Hello",
                received_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
                list_id="<news.example.com>",
                list_unsubscribe="<https://example.com/u/1>, <mailto:u@example.com>",
                list_unsubscribe_post="List-Unsubscribe=One-Click",
                body=b"<p>Hello</p>",
                snippet="Hello",
            ),
            FakeMessage(
                uid="2",
                mailbox="INBOX",
                from_email="other@example.org",
                display_name="Other",
                subject="Plain",
                received_at=datetime(2026, 3, 15, tzinfo=timezone.utc),
                list_id=None,
                list_unsubscribe=None,
                list_unsubscribe_post=None,
                body=b"plain",
                snippet="plain",
            ),
        ]
    )


async def test_test_credentials(provider):
    assert await provider.test_credentials() is True


async def test_scan_headers_returns_only_messages_with_unsubscribe(provider):
    seen = [m async for m in provider.scan_headers(since=None, max_messages=100)]
    assert len(seen) == 1
    assert seen[0].from_email == "news@example.com"
    assert seen[0].list_unsubscribe == "<https://example.com/u/1>, <mailto:u@example.com>"


async def test_fetch_snippet_and_body(provider):
    ref = MessageRef(provider_uid="1", mailbox="INBOX")
    assert await provider.fetch_snippet(ref) == "Hello"
    assert await provider.fetch_body(ref) == b"<p>Hello</p>"


async def test_search_by_sender(provider):
    refs = [
        r
        async for r in provider.search_by_sender(
            SenderQuery(from_emails=["news@example.com"]),
            mailboxes=None,
        )
    ]
    assert refs == [MessageRef(provider_uid="1", mailbox="INBOX")]


async def test_move_messages(provider):
    refs = [MessageRef(provider_uid="1", mailbox="INBOX")]
    result = await provider.move_messages(refs, SpecialFolder.trash)
    assert result.moved == 1
    assert provider.messages[0].mailbox == "Trash"
