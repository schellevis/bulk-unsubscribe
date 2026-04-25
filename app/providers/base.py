from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol


class SpecialFolder(str, Enum):
    inbox = "inbox"
    archive = "archive"
    trash = "trash"
    sent = "sent"
    drafts = "drafts"
    junk = "junk"


@dataclass(frozen=True)
class Mailbox:
    id: str
    name: str
    role: SpecialFolder | None


@dataclass(frozen=True)
class MessageRef:
    """Pointer to one message at the provider."""

    provider_uid: str
    mailbox: str


@dataclass(frozen=True)
class ScannedMessage:
    """Result of a header-only scan."""

    ref: MessageRef
    from_email: str
    from_domain: str
    display_name: str
    subject: str
    received_at: datetime
    list_id: str | None
    list_unsubscribe: str | None
    list_unsubscribe_post: str | None


@dataclass(frozen=True)
class SenderQuery:
    """Selector for "all messages from this sender" operations.

    Provider implementations OR all `from_emails` together when querying.
    """

    from_emails: list[str]


@dataclass(frozen=True)
class MoveResult:
    moved: int
    failed: int
    errors: list[str]


class MailProvider(Protocol):
    async def test_credentials(self) -> bool: ...

    async def list_mailboxes(self) -> list[Mailbox]: ...

    def scan_headers(
        self, since: datetime | None, max_messages: int
    ) -> AsyncIterator[ScannedMessage]: ...

    async def fetch_snippet(self, ref: MessageRef) -> str: ...

    async def fetch_body(self, ref: MessageRef) -> bytes: ...

    def search_by_sender(
        self, query: SenderQuery, mailboxes: list[str] | None = None
    ) -> AsyncIterator[MessageRef]: ...

    async def move_messages(
        self, refs: list[MessageRef], destination: SpecialFolder
    ) -> MoveResult: ...
