import textwrap
from unittest.mock import MagicMock, patch

from app.providers.base import SpecialFolder
from app.providers.imap import IMAPProvider


def _fake_imap(login_ok: bool = True, list_lines: list[bytes] | None = None) -> MagicMock:
    conn = MagicMock()
    if login_ok:
        conn.login.return_value = ("OK", [b"Logged in"])
    else:
        conn.login.side_effect = Exception("auth failed")
    conn.list.return_value = (
        "OK",
        list_lines
        or [
            b'(\\HasNoChildren) "/" "INBOX"',
            b'(\\HasNoChildren \\Archive) "/" "Archive"',
            b'(\\HasNoChildren \\Trash) "/" "Trash"',
        ],
    )
    return conn


async def test_test_credentials_returns_true_on_login():
    conn = _fake_imap(login_ok=True)
    with patch("app.providers.imap.imaplib.IMAP4_SSL", return_value=conn):
        provider = IMAPProvider("imap.example.com", 993, "u", "p")
        assert await provider.test_credentials() is True


async def test_test_credentials_returns_false_on_failure():
    conn = _fake_imap(login_ok=False)
    with patch("app.providers.imap.imaplib.IMAP4_SSL", return_value=conn):
        provider = IMAPProvider("imap.example.com", 993, "u", "p")
        assert await provider.test_credentials() is False


async def test_list_mailboxes_maps_special_use_flags():
    conn = _fake_imap()
    with patch("app.providers.imap.imaplib.IMAP4_SSL", return_value=conn):
        provider = IMAPProvider("imap.example.com", 993, "u", "p")
        boxes = await provider.list_mailboxes()
    by_name = {b.name: b.role for b in boxes}
    assert by_name["INBOX"] == SpecialFolder.inbox
    assert by_name["Archive"] == SpecialFolder.archive
    assert by_name["Trash"] == SpecialFolder.trash


async def test_scan_uses_uid_not_sequence_number():
    """provider_uid must be the UID from the FETCH response, not the sequence number."""
    raw_headers = textwrap.dedent("""\
        From: Newsletter <news@example.com>
        Subject: Weekly digest
        Date: Tue, 01 Apr 2025 12:00:00 +0000
        List-Unsubscribe: <https://example.com/unsub>
    """).encode()

    # IMAP FETCH response: sequence number is 1, UID is 123
    meta = (
        b"1 (UID 123 BODY[HEADER.FIELDS (FROM DATE SUBJECT MESSAGE-ID"
        b" LIST-ID LIST-UNSUBSCRIBE LIST-UNSUBSCRIBE-POST)] {"
        + str(len(raw_headers)).encode()
        + b"}"
    )

    conn = _fake_imap()
    conn.select.return_value = ("OK", [b"1"])
    conn.uid.side_effect = [
        ("OK", [b"123"]),                     # UID SEARCH
        ("OK", [(meta, raw_headers), b")"]),  # UID FETCH
    ]

    with patch("app.providers.imap.imaplib.IMAP4_SSL", return_value=conn):
        provider = IMAPProvider("imap.example.com", 993, "u", "p")
        messages = [m async for m in provider.scan_headers(since=None, max_messages=100)]

    assert len(messages) == 1
    assert messages[0].ref.provider_uid == "123"
