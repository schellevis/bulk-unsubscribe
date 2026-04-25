"""Fastmail JMAP service: authenticate via API token and scan for newsletter senders."""

from dataclasses import dataclass
from datetime import datetime, timezone

import aiohttp

JMAP_SESSION_URL = "https://api.fastmail.com/jmap/session"


@dataclass
class SenderInfo:
    email: str
    display_name: str
    email_count: int = 0
    unsubscribe_link: str | None = None
    unsubscribe_mailto: str | None = None
    first_seen: datetime | None = None
    last_seen: datetime | None = None


def _parse_unsubscribe_header(header_value: str) -> tuple[str | None, str | None]:
    """Parse List-Unsubscribe header value, return (http_url, mailto_url)."""
    import re

    http_url: str | None = None
    mailto_url: str | None = None
    for part in re.findall(r"<([^>]+)>", header_value):
        part = part.strip()
        if part.lower().startswith("http"):
            http_url = part
        elif part.lower().startswith("mailto"):
            mailto_url = part
    return http_url, mailto_url


class FastmailService:
    """
    Interact with Fastmail via the JMAP protocol.
    See https://jmap.io and https://www.fastmail.com/dev/
    """

    def __init__(self, api_token: str) -> None:
        self.api_token = api_token
        self._session_url: str | None = None
        self._account_id: str | None = None

    @property
    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_token}"}

    async def _get_session(self, http: aiohttp.ClientSession) -> None:
        """Fetch the JMAP session to obtain the API URL and accountId."""
        async with http.get(JMAP_SESSION_URL, headers=self._auth_headers) as resp:
            resp.raise_for_status()
            data = await resp.json()
        self._session_url = data["apiUrl"]
        # primaryAccounts maps capability -> accountId
        self._account_id = data["primaryAccounts"].get(
            "urn:ietf:params:jmap:mail"
        ) or next(iter(data["accounts"]))

    async def test_connection(self) -> bool:
        """Return True if the token is valid and the JMAP session can be established."""
        try:
            async with aiohttp.ClientSession() as http:
                await self._get_session(http)
            return True
        except Exception:
            return False

    async def scan_senders(self, max_messages: int = 500) -> list[SenderInfo]:
        """
        Scan inbox for newsletters via JMAP Email/query + Email/get.
        Only messages that contain a List-Unsubscribe header are considered.
        """
        async with aiohttp.ClientSession() as http:
            await self._get_session(http)
            assert self._session_url and self._account_id

            # Step 1: Get the inbox mailbox id
            inbox_id = await self._get_inbox_id(http)

            # Step 2: Query email IDs in the inbox (most recent first)
            email_ids = await self._query_emails(http, inbox_id, max_messages)
            if not email_ids:
                return []

            # Step 3: Fetch header fields for those emails
            return await self._fetch_senders(http, email_ids)

    async def _get_inbox_id(self, http: aiohttp.ClientSession) -> str:
        payload = {
            "using": ["urn:ietf:params:jmap:core", "urn:ietf:params:jmap:mail"],
            "methodCalls": [
                [
                    "Mailbox/query",
                    {
                        "accountId": self._account_id,
                        "filter": {"role": "inbox"},
                    },
                    "0",
                ]
            ],
        }
        async with http.post(
            self._session_url, json=payload, headers=self._auth_headers
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
        ids = data["methodResponses"][0][1].get("ids", [])
        return ids[0] if ids else ""

    async def _query_emails(
        self, http: aiohttp.ClientSession, mailbox_id: str, limit: int
    ) -> list[str]:
        payload = {
            "using": ["urn:ietf:params:jmap:core", "urn:ietf:params:jmap:mail"],
            "methodCalls": [
                [
                    "Email/query",
                    {
                        "accountId": self._account_id,
                        "filter": {"inMailbox": mailbox_id},
                        "sort": [{"property": "receivedAt", "isAscending": False}],
                        "limit": limit,
                    },
                    "0",
                ]
            ],
        }
        async with http.post(
            self._session_url, json=payload, headers=self._auth_headers
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
        return data["methodResponses"][0][1].get("ids", [])

    async def _fetch_senders(
        self, http: aiohttp.ClientSession, email_ids: list[str]
    ) -> list[SenderInfo]:
        # JMAP allows fetching specific header fields
        payload = {
            "using": ["urn:ietf:params:jmap:core", "urn:ietf:params:jmap:mail"],
            "methodCalls": [
                [
                    "Email/get",
                    {
                        "accountId": self._account_id,
                        "ids": email_ids,
                        "properties": [
                            "from",
                            "receivedAt",
                            "header:List-Unsubscribe:asText",
                        ],
                    },
                    "0",
                ]
            ],
        }
        async with http.post(
            self._session_url, json=payload, headers=self._auth_headers
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()

        emails = data["methodResponses"][0][1].get("list", [])
        senders: dict[str, SenderInfo] = {}

        for em in emails:
            unsub_header = em.get("header:List-Unsubscribe:asText") or ""
            if not unsub_header:
                continue

            from_list: list[dict] = em.get("from") or []
            if not from_list:
                continue
            from_obj = from_list[0]
            sender_email = (from_obj.get("email") or "").lower().strip()
            display_name = (from_obj.get("name") or "").strip()
            if not sender_email:
                continue

            received_at_str: str = em.get("receivedAt") or ""
            msg_date: datetime | None = None
            if received_at_str:
                try:
                    msg_date = datetime.fromisoformat(
                        received_at_str.replace("Z", "+00:00")
                    ).astimezone(timezone.utc)
                except Exception:
                    pass

            http_url, mailto_url = _parse_unsubscribe_header(unsub_header)

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
