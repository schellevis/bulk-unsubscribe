from aioresponses import aioresponses

from app.providers.base import MessageRef, SenderQuery, SpecialFolder
from app.providers.jmap import JMAP_SESSION_URL, JMAPProvider


def _session_payload():
    return {
        "apiUrl": "https://api.example.com/jmap/api",
        "primaryAccounts": {"urn:ietf:params:jmap:mail": "acct1"},
        "accounts": {"acct1": {}},
    }


async def test_search_by_sender_yields_refs():
    with aioresponses() as m:
        m.get(JMAP_SESSION_URL, payload=_session_payload())
        m.post(
            "https://api.example.com/jmap/api",
            payload={
                "methodResponses": [
                    ["Email/query", {"ids": ["e1", "e2"]}, "0"],
                    [
                        "Email/get",
                        {
                            "list": [
                                {
                                    "id": "e1",
                                    "mailboxIds": {"mb_inbox": True},
                                },
                                {
                                    "id": "e2",
                                    "mailboxIds": {"mb_inbox": True, "mb_promo": True},
                                },
                            ]
                        },
                        "1",
                    ],
                ]
            },
        )
        provider = JMAPProvider(api_token="abc")
        refs = [
            r
            async for r in provider.search_by_sender(
                SenderQuery(from_emails=["news@example.com"])
            )
        ]
    assert {(r.provider_uid, r.mailbox) for r in refs} == {
        ("e1", "mb_inbox"),
        ("e2", "mb_inbox"),
        ("e2", "mb_promo"),
    }


async def test_move_messages_uses_email_set_with_destination_role():
    with aioresponses() as m:
        m.get(JMAP_SESSION_URL, payload=_session_payload())
        # First POST: Mailbox/query for trash role
        m.post(
            "https://api.example.com/jmap/api",
            payload={
                "methodResponses": [
                    ["Mailbox/query", {"ids": ["mb_trash"]}, "0"]
                ]
            },
        )
        # Second POST: Email/set
        m.post(
            "https://api.example.com/jmap/api",
            payload={
                "methodResponses": [
                    [
                        "Email/set",
                        {
                            "updated": {"e1": None, "e2": None},
                            "notUpdated": {},
                        },
                        "0",
                    ]
                ]
            },
        )
        provider = JMAPProvider(api_token="abc")
        result = await provider.move_messages(
            [
                MessageRef(provider_uid="e1", mailbox="mb_inbox"),
                MessageRef(provider_uid="e2", mailbox="mb_inbox"),
            ],
            SpecialFolder.trash,
        )
    assert result.moved == 2
    assert result.failed == 0
    assert result.errors == []
