import asyncio
import email
import email.header
import email.utils
import imaplib
import re
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from app.providers.base import (
    Mailbox,
    MessageRef,
    MoveResult,
    ScannedMessage,
    SenderQuery,
    SpecialFolder,
)

_LIST_RE = re.compile(rb'\((?P<flags>[^)]*)\) "(?P<sep>[^"]*)" "?(?P<name>[^"\r\n]+)"?')

_FLAG_TO_ROLE = {
    b"\\inbox": SpecialFolder.inbox,
    b"\\archive": SpecialFolder.archive,
    b"\\trash": SpecialFolder.trash,
    b"\\sent": SpecialFolder.sent,
    b"\\drafts": SpecialFolder.drafts,
    b"\\junk": SpecialFolder.junk,
}

_HEADER_FIELDS = (
    "FROM DATE SUBJECT MESSAGE-ID LIST-ID LIST-UNSUBSCRIBE LIST-UNSUBSCRIBE-POST"
)


def _decode_role(flags: bytes, name: str) -> SpecialFolder | None:
    flags_lc = flags.lower()
    for tag, role in _FLAG_TO_ROLE.items():
        if tag in flags_lc:
            return role
    if name.upper() == "INBOX":
        return SpecialFolder.inbox
    return None


def _decode_header(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    parts = email.header.decode_header(value)
    out = []
    for chunk, charset in parts:
        if isinstance(chunk, bytes):
            out.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(chunk)
    return " ".join(out).strip()


def _parse_from(raw: str) -> tuple[str, str]:
    decoded = _decode_header(raw)
    name, addr = email.utils.parseaddr(decoded)
    return name.strip().strip('"'), addr.strip().lower()


class IMAPProvider:
    def __init__(self, host: str, port: int, username: str, password: str) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password

    # -- sync helpers run via asyncio.to_thread --------------------------------

    def _connect(self) -> imaplib.IMAP4_SSL:
        conn = imaplib.IMAP4_SSL(self.host, self.port)
        conn.login(self.username, self.password)
        return conn

    def _login_only_sync(self) -> bool:
        try:
            conn = self._connect()
        except Exception:  # noqa: BLE001
            return False
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass
        return True

    def _list_mailboxes_sync(self) -> list[Mailbox]:
        conn = self._connect()
        try:
            status, lines = conn.list()
            if status != "OK" or lines is None:
                return []
            result: list[Mailbox] = []
            for raw in lines:
                if raw is None:
                    continue
                m = _LIST_RE.match(raw)
                if not m:
                    continue
                name = m.group("name").decode("utf-8", errors="replace")
                flags = m.group("flags")
                result.append(Mailbox(id=name, name=name, role=_decode_role(flags, name)))
            return result
        finally:
            try:
                conn.logout()
            except Exception:  # noqa: BLE001
                pass

    def _scan_sync(
        self, since: datetime | None, max_messages: int
    ) -> list[ScannedMessage]:
        conn = self._connect()
        try:
            conn.select("INBOX", readonly=True)
            criteria = "ALL"
            if since is not None:
                since_str = since.strftime("%d-%b-%Y")
                criteria = f"SINCE {since_str}"
            status, data = conn.uid("SEARCH", None, criteria)
            if status != "OK" or not data or not data[0]:
                return []
            uids = data[0].split()
            if not uids:
                return []
            uids = uids[-max_messages:]

            results: list[ScannedMessage] = []
            for chunk_start in range(0, len(uids), 200):
                chunk = uids[chunk_start : chunk_start + 200]
                uid_set = b",".join(chunk).decode()
                status, fetch_data = conn.uid(
                    "FETCH",
                    uid_set,
                    f"(BODY.PEEK[HEADER.FIELDS ({_HEADER_FIELDS})])",
                )
                if status != "OK" or not fetch_data:
                    continue
                for entry in fetch_data:
                    if not isinstance(entry, tuple) or len(entry) < 2:
                        continue
                    meta, raw_headers = entry[0], entry[1]
                    if not isinstance(raw_headers, (bytes, bytearray)):
                        continue
                    msg = email.message_from_bytes(bytes(raw_headers))
                    list_unsub = msg.get("List-Unsubscribe")
                    if not list_unsub:
                        continue
                    _, sender_email = _parse_from(msg.get("From", ""))
                    if not sender_email or "@" not in sender_email:
                        continue
                    domain = sender_email.rsplit("@", 1)[1]

                    date_raw = msg.get("Date", "")
                    try:
                        received = email.utils.parsedate_to_datetime(
                            date_raw
                        ).astimezone(timezone.utc)
                    except (TypeError, ValueError):
                        continue

                    uid_match = re.match(
                        rb"\s*(\d+)\s+\(",
                        meta if isinstance(meta, (bytes, bytearray)) else b"",
                    )
                    provider_uid = (
                        uid_match.group(1).decode() if uid_match else ""
                    )

                    display_name, _ = _parse_from(msg.get("From", ""))

                    results.append(
                        ScannedMessage(
                            ref=MessageRef(
                                provider_uid=provider_uid, mailbox="INBOX"
                            ),
                            from_email=sender_email,
                            from_domain=domain,
                            display_name=display_name,
                            subject=_decode_header(msg.get("Subject", "")),
                            received_at=received,
                            list_id=_decode_header(msg.get("List-Id")) or None,
                            list_unsubscribe=_decode_header(list_unsub) or None,
                            list_unsubscribe_post=(
                                _decode_header(msg.get("List-Unsubscribe-Post")) or None
                            ),
                        )
                    )
            return results
        finally:
            try:
                conn.logout()
            except Exception:  # noqa: BLE001
                pass

    def _fetch_snippet_sync(self, ref: MessageRef) -> str:
        conn = self._connect()
        try:
            conn.select(ref.mailbox, readonly=True)
            status, data = conn.uid(
                "FETCH", ref.provider_uid, "(BODY.PEEK[TEXT]<0.2048>)"
            )
            if status != "OK" or not data:
                return ""
            for entry in data:
                if isinstance(entry, tuple) and len(entry) >= 2:
                    raw = entry[1]
                    if isinstance(raw, (bytes, bytearray)):
                        text = bytes(raw).decode("utf-8", errors="replace")
                        return " ".join(text.split())[:200]
            return ""
        finally:
            try:
                conn.logout()
            except Exception:  # noqa: BLE001
                pass

    # -- Protocol API ----------------------------------------------------------

    async def test_credentials(self) -> bool:
        return await asyncio.to_thread(self._login_only_sync)

    async def list_mailboxes(self) -> list[Mailbox]:
        return await asyncio.to_thread(self._list_mailboxes_sync)

    async def scan_headers(  # type: ignore[override]
        self, since: datetime | None, max_messages: int
    ) -> AsyncIterator[ScannedMessage]:
        results = await asyncio.to_thread(self._scan_sync, since, max_messages)
        for r in results:
            yield r

    async def fetch_snippet(self, ref: MessageRef) -> str:
        return await asyncio.to_thread(self._fetch_snippet_sync, ref)

    async def fetch_body(self, ref: MessageRef) -> bytes:
        raise NotImplementedError

    async def search_by_sender(  # type: ignore[override]
        self, query: SenderQuery, mailboxes: list[str] | None = None
    ) -> AsyncIterator[MessageRef]:
        raise NotImplementedError
        yield  # pragma: no cover

    async def move_messages(
        self, refs: list[MessageRef], destination: SpecialFolder
    ) -> MoveResult:
        raise NotImplementedError
