from collections.abc import AsyncIterator
from datetime import datetime, timezone

import aiohttp

from app.providers.base import (
    Mailbox,
    MessageRef,
    MoveResult,
    ScannedMessage,
    SenderQuery,
    SpecialFolder,
)

JMAP_SESSION_URL = "https://api.fastmail.com/jmap/session"
_CAPS = ["urn:ietf:params:jmap:core", "urn:ietf:params:jmap:mail"]

_ROLE_MAP = {
    "inbox": SpecialFolder.inbox,
    "archive": SpecialFolder.archive,
    "trash": SpecialFolder.trash,
    "sent": SpecialFolder.sent,
    "drafts": SpecialFolder.drafts,
    "junk": SpecialFolder.junk,
}


class JMAPProvider:
    def __init__(self, api_token: str, session_url: str = JMAP_SESSION_URL) -> None:
        self.api_token = api_token
        self._session_discovery_url = session_url
        self._api_url: str | None = None
        self._account_id: str | None = None

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_token}"}

    async def _get_session(self, http: aiohttp.ClientSession) -> None:
        async with http.get(self._session_discovery_url, headers=self._headers) as r:
            r.raise_for_status()
            data = await r.json()
        self._api_url = data["apiUrl"]
        primary = data.get("primaryAccounts", {}).get("urn:ietf:params:jmap:mail")
        self._account_id = primary or next(iter(data.get("accounts", {})), None)
        if self._account_id is None:
            raise RuntimeError("JMAP session has no mail account")

    async def test_credentials(self) -> bool:
        try:
            async with aiohttp.ClientSession() as http:
                await self._get_session(http)
            return True
        except Exception:  # noqa: BLE001
            return False

    async def list_mailboxes(self) -> list[Mailbox]:
        async with aiohttp.ClientSession() as http:
            if self._api_url is None:
                await self._get_session(http)
            payload = {
                "using": _CAPS,
                "methodCalls": [
                    [
                        "Mailbox/get",
                        {"accountId": self._account_id},
                        "0",
                    ]
                ],
            }
            async with http.post(
                self._api_url, json=payload, headers=self._headers
            ) as r:
                r.raise_for_status()
                data = await r.json()

        raw = data["methodResponses"][0][1].get("list", [])
        return [
            Mailbox(
                id=m["id"],
                name=m.get("name", ""),
                role=_ROLE_MAP.get((m.get("role") or "").lower()),
            )
            for m in raw
        ]

    async def scan_headers(  # type: ignore[override]
        self, since: datetime | None, max_messages: int
    ) -> AsyncIterator[ScannedMessage]:
        raise NotImplementedError
        yield  # pragma: no cover

    async def fetch_snippet(self, ref: MessageRef) -> str:
        raise NotImplementedError

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
