from datetime import datetime, timezone

from aioresponses import aioresponses

from app.providers.jmap import JMAP_SESSION_URL, JMAPProvider

_SESSION_PAYLOAD = {
    "apiUrl": "https://api.example.com/jmap/api",
    "primaryAccounts": {"urn:ietf:params:jmap:mail": "acct1"},
    "accounts": {"acct1": {}},
}

_MAILBOX_GET_RESPONSE = [
    "Mailbox/get",
    {
        "list": [
            {"id": "mb_inbox", "name": "Inbox", "role": "inbox"},
            {"id": "mb_promo", "name": "Promotions", "role": None},
        ]
    },
    "0",
]


async def test_scan_headers_yields_only_messages_with_list_unsubscribe():
    with aioresponses() as m:
        m.get(JMAP_SESSION_URL, payload=_SESSION_PAYLOAD)
        m.post(
            "https://api.example.com/jmap/api",
            payload={
                "methodResponses": [
                    _MAILBOX_GET_RESPONSE,
                    ["Mailbox/query", {"ids": ["mb_inbox"]}, "1"],
                    ["Email/query", {"ids": ["e1", "e2"]}, "2"],
                    [
                        "Email/get",
                        {
                            "list": [
                                {
                                    "id": "e1",
                                    "mailboxIds": {"mb_inbox": True},
                                    "from": [
                                        {"email": "News@Example.com", "name": "News"}
                                    ],
                                    "subject": "Hi",
                                    "receivedAt": "2026-04-01T10:00:00Z",
                                    "header:List-Id:asText": "<news.example.com>",
                                    "header:List-Unsubscribe:asText": "<https://example.com/u/1>",
                                    "header:List-Unsubscribe-Post:asText": "List-Unsubscribe=One-Click",
                                },
                                {
                                    "id": "e2",
                                    "mailboxIds": {"mb_inbox": True},
                                    "from": [
                                        {"email": "joe@friend.com", "name": "Joe"}
                                    ],
                                    "subject": "Lunch",
                                    "receivedAt": "2026-04-02T11:00:00Z",
                                    "header:List-Id:asText": None,
                                    "header:List-Unsubscribe:asText": None,
                                    "header:List-Unsubscribe-Post:asText": None,
                                },
                            ]
                        },
                        "3",
                    ],
                ]
            },
        )

        provider = JMAPProvider(api_token="abc")
        results = [r async for r in provider.scan_headers(since=None, max_messages=10)]

    assert len(results) == 1
    only = results[0]
    assert only.from_email == "news@example.com"
    assert only.from_domain == "example.com"
    assert only.list_unsubscribe == "<https://example.com/u/1>"
    assert only.list_unsubscribe_post == "List-Unsubscribe=One-Click"
    assert only.received_at == datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc)
    assert only.ref.mailbox == "Inbox"


async def test_scan_headers_resolves_mailbox_id_to_name():
    """Mailbox IDs are resolved to human-readable names so that whitelist rules
    based on visible folder names work correctly for JMAP accounts."""
    with aioresponses() as m:
        m.get(JMAP_SESSION_URL, payload=_SESSION_PAYLOAD)
        m.post(
            "https://api.example.com/jmap/api",
            payload={
                "methodResponses": [
                    _MAILBOX_GET_RESPONSE,
                    ["Mailbox/query", {"ids": ["mb_inbox"]}, "1"],
                    ["Email/query", {"ids": ["e1", "e2"]}, "2"],
                    [
                        "Email/get",
                        {
                            "list": [
                                {
                                    "id": "e1",
                                    "mailboxIds": {"mb_inbox": True},
                                    "from": [{"email": "news@example.com", "name": "News"}],
                                    "subject": "Hi",
                                    "receivedAt": "2026-04-01T10:00:00Z",
                                    "header:List-Id:asText": "<a.example.com>",
                                    "header:List-Unsubscribe:asText": "<https://example.com/u/1>",
                                    "header:List-Unsubscribe-Post:asText": None,
                                },
                                {
                                    "id": "e2",
                                    "mailboxIds": {"mb_promo": True},
                                    "from": [{"email": "promo@example.com", "name": "Promo"}],
                                    "subject": "Deal",
                                    "receivedAt": "2026-04-02T10:00:00Z",
                                    "header:List-Id:asText": "<b.example.com>",
                                    "header:List-Unsubscribe:asText": "<https://example.com/u/2>",
                                    "header:List-Unsubscribe-Post:asText": None,
                                },
                            ]
                        },
                        "3",
                    ],
                ]
            },
        )

        provider = JMAPProvider(api_token="abc")
        results = [r async for r in provider.scan_headers(since=None, max_messages=10)]

    assert len(results) == 2
    by_uid = {r.ref.provider_uid: r for r in results}
    assert by_uid["e1"].ref.mailbox == "Inbox"
    assert by_uid["e2"].ref.mailbox == "Promotions"
