from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime

from app.providers.base import (
    Mailbox,
    MessageRef,
    MoveResult,
    ScannedMessage,
    SenderQuery,
    SpecialFolder,
)


@dataclass
class FakeMessage:
    uid: str
    mailbox: str
    from_email: str
    display_name: str
    subject: str
    received_at: datetime
    list_id: str | None
    list_unsubscribe: str | None
    list_unsubscribe_post: str | None
    body: bytes
    snippet: str


@dataclass
class FakeMailProvider:
    messages: list[FakeMessage] = field(default_factory=list)
    credentials_valid: bool = True
    moved_log: list[tuple[str, SpecialFolder]] = field(default_factory=list)

    async def test_credentials(self) -> bool:
        return self.credentials_valid

    async def list_mailboxes(self) -> list[Mailbox]:
        return [
            Mailbox(id="INBOX", name="INBOX", role=SpecialFolder.inbox),
            Mailbox(id="Archive", name="Archive", role=SpecialFolder.archive),
            Mailbox(id="Trash", name="Trash", role=SpecialFolder.trash),
        ]

    async def scan_headers(
        self, since: datetime | None, max_messages: int
    ) -> AsyncIterator[ScannedMessage]:
        count = 0
        for m in sorted(self.messages, key=lambda x: x.received_at, reverse=True):
            if count >= max_messages:
                return
            if since and m.received_at < since:
                continue
            if not m.list_unsubscribe:
                continue
            domain = m.from_email.rsplit("@", 1)[-1].lower() if "@" in m.from_email else ""
            yield ScannedMessage(
                ref=MessageRef(provider_uid=m.uid, mailbox=m.mailbox),
                from_email=m.from_email.lower(),
                from_domain=domain,
                display_name=m.display_name,
                subject=m.subject,
                received_at=m.received_at,
                list_id=m.list_id,
                list_unsubscribe=m.list_unsubscribe,
                list_unsubscribe_post=m.list_unsubscribe_post,
            )
            count += 1

    async def fetch_snippet(self, ref: MessageRef) -> str:
        return self._find(ref).snippet

    async def fetch_body(self, ref: MessageRef) -> bytes:
        return self._find(ref).body

    async def search_by_sender(
        self, query: SenderQuery, mailboxes: list[str] | None = None
    ) -> AsyncIterator[MessageRef]:
        wanted = {e.lower() for e in query.from_emails}
        for m in self.messages:
            if mailboxes and m.mailbox not in mailboxes:
                continue
            if m.from_email.lower() in wanted:
                yield MessageRef(provider_uid=m.uid, mailbox=m.mailbox)

    async def move_messages(
        self, refs: list[MessageRef], destination: SpecialFolder
    ) -> MoveResult:
        target = {
            SpecialFolder.archive: "Archive",
            SpecialFolder.trash: "Trash",
        }[destination]
        moved = 0
        for ref in refs:
            for m in self.messages:
                if m.uid == ref.provider_uid and m.mailbox == ref.mailbox:
                    m.mailbox = target
                    self.moved_log.append((m.uid, destination))
                    moved += 1
                    break
        return MoveResult(moved=moved, failed=len(refs) - moved, errors=[])

    def _find(self, ref: MessageRef) -> FakeMessage:
        for m in self.messages:
            if m.uid == ref.provider_uid:
                return m
        raise KeyError(ref)
