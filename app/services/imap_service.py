"""IMAP service: connect to any IMAP server and scan for newsletter senders."""

import email
import email.header
import imaplib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class SenderInfo:
    email: str
    display_name: str
    email_count: int = 0
    unsubscribe_link: str | None = None
    unsubscribe_mailto: str | None = None
    first_seen: datetime | None = None
    last_seen: datetime | None = None


def _decode_header_value(value: str | bytes | None) -> str:
    """Decode RFC 2047 encoded header value to a plain string."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    parts = email.header.decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded).strip()


def _parse_address(raw: str) -> tuple[str, str]:
    """Return (display_name, email_address) from a From header value."""
    raw = _decode_header_value(raw)
    match = re.match(r"^(.*?)<([^>]+)>$", raw.strip())
    if match:
        name = match.group(1).strip().strip('"')
        addr = match.group(2).strip().lower()
        return name, addr
    # plain address without display name
    return "", raw.strip().lower()


def _parse_unsubscribe_header(header_value: str) -> tuple[str | None, str | None]:
    """
    Parse a List-Unsubscribe header.
    Returns (http_url, mailto_url) where each may be None.
    """
    http_url: str | None = None
    mailto_url: str | None = None
    for part in re.findall(r"<([^>]+)>", header_value):
        part = part.strip()
        if part.lower().startswith("http"):
            http_url = part
        elif part.lower().startswith("mailto"):
            mailto_url = part
    return http_url, mailto_url


class IMAPService:
    def __init__(self, host: str, port: int, username: str, password: str) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self._conn: imaplib.IMAP4_SSL | None = None

    def connect(self) -> None:
        """Open and authenticate an IMAP connection."""
        self._conn = imaplib.IMAP4_SSL(self.host, self.port)
        self._conn.login(self.username, self.password)

    def disconnect(self) -> None:
        if self._conn:
            try:
                self._conn.logout()
            except Exception:
                pass
            self._conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()

    def test_connection(self) -> bool:
        """Return True if credentials are valid."""
        try:
            self.connect()
            return True
        except imaplib.IMAP4.error:
            return False
        finally:
            self.disconnect()

    def scan_senders(self, mailbox: str = "INBOX", max_messages: int = 500) -> list[SenderInfo]:
        """
        Scan the mailbox for newsletter-style senders by looking for messages
        with a List-Unsubscribe header.  Returns aggregated SenderInfo records.
        """
        assert self._conn is not None, "Call connect() first"

        self._conn.select(mailbox, readonly=True)

        # Search for messages that have a List-Unsubscribe header (newsletters)
        status, data = self._conn.search(None, "ALL")
        if status != "OK" or not data or not data[0]:
            return []

        message_ids: list[bytes] = data[0].split()
        # Process the most recent messages first
        message_ids = message_ids[-max_messages:]

        senders: dict[str, SenderInfo] = {}

        for msg_id in message_ids:
            status, msg_data = self._conn.fetch(msg_id, "(BODY.PEEK[HEADER])")
            if status != "OK" or not msg_data or not msg_data[0]:
                continue

            raw_header = msg_data[0][1]  # type: ignore[index]
            msg = email.message_from_bytes(raw_header)

            list_unsub = msg.get("List-Unsubscribe", "")
            if not list_unsub:
                # Skip messages without a List-Unsubscribe header
                continue

            from_raw = msg.get("From", "")
            display_name, sender_email = _parse_address(from_raw)
            if not sender_email:
                continue

            date_str = msg.get("Date", "")
            msg_date: datetime | None = None
            try:
                parsed = email.utils.parsedate_to_datetime(date_str)
                msg_date = parsed.astimezone(timezone.utc)
            except Exception:
                pass

            http_url, mailto_url = _parse_unsubscribe_header(list_unsub)

            if sender_email not in senders:
                senders[sender_email] = SenderInfo(
                    email=sender_email,
                    display_name=display_name,
                    email_count=0,
                    unsubscribe_link=http_url,
                    unsubscribe_mailto=mailto_url,
                    first_seen=msg_date,
                    last_seen=msg_date,
                )
            info = senders[sender_email]
            info.email_count += 1
            if http_url and not info.unsubscribe_link:
                info.unsubscribe_link = http_url
            if mailto_url and not info.unsubscribe_mailto:
                info.unsubscribe_mailto = mailto_url
            if msg_date:
                if info.first_seen is None or msg_date < info.first_seen:
                    info.first_seen = msg_date
                if info.last_seen is None or msg_date > info.last_seen:
                    info.last_seen = msg_date

        return list(senders.values())
