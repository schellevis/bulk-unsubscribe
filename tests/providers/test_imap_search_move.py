from unittest.mock import MagicMock, patch

from app.providers.base import MessageRef, SenderQuery, SpecialFolder
from app.providers.imap import IMAPProvider


def _conn():
    c = MagicMock()
    c.login.return_value = ("OK", [b"ok"])
    c.list.return_value = (
        "OK",
        [
            b'(\\HasNoChildren) "/" "INBOX"',
            b'(\\HasNoChildren \\Trash) "/" "Trash"',
        ],
    )
    c.select.return_value = ("OK", [b"42"])
    return c


async def test_search_by_sender_collects_uids():
    c = _conn()

    def uid(*args):
        if args[0] == "SEARCH":
            return ("OK", [b"1 2 3"])
        return ("BAD", [])

    c.uid.side_effect = uid
    with patch("app.providers.imap.imaplib.IMAP4_SSL", return_value=c):
        provider = IMAPProvider("h", 993, "u", "p")
        refs = [
            r
            async for r in provider.search_by_sender(
                SenderQuery(from_emails=["news@example.com"]), mailboxes=["INBOX"]
            )
        ]
    assert {r.provider_uid for r in refs} == {"1", "2", "3"}
    assert all(r.mailbox == "INBOX" for r in refs)


async def test_move_messages_uses_move_when_supported():
    c = _conn()

    def uid(*args):
        if args[0] == "MOVE":
            return ("OK", [b"ok"])
        return ("BAD", [])

    c.uid.side_effect = uid
    with patch("app.providers.imap.imaplib.IMAP4_SSL", return_value=c):
        provider = IMAPProvider("h", 993, "u", "p")
        result = await provider.move_messages(
            [
                MessageRef(provider_uid="1", mailbox="INBOX"),
                MessageRef(provider_uid="2", mailbox="INBOX"),
            ],
            SpecialFolder.trash,
        )
    assert result.moved == 2
    assert result.failed == 0
