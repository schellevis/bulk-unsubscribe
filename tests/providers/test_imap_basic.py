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
