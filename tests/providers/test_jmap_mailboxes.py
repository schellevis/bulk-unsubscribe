from aioresponses import aioresponses

from app.providers.base import SpecialFolder
from app.providers.jmap import JMAP_SESSION_URL, JMAPProvider


async def test_list_mailboxes_maps_roles():
    with aioresponses() as m:
        m.get(
            JMAP_SESSION_URL,
            payload={
                "apiUrl": "https://api.example.com/jmap/api",
                "primaryAccounts": {"urn:ietf:params:jmap:mail": "acct1"},
                "accounts": {"acct1": {}},
            },
        )
        m.post(
            "https://api.example.com/jmap/api",
            payload={
                "methodResponses": [
                    [
                        "Mailbox/get",
                        {
                            "list": [
                                {"id": "mb1", "name": "INBOX", "role": "inbox"},
                                {"id": "mb2", "name": "Archive", "role": "archive"},
                                {"id": "mb3", "name": "Trash", "role": "trash"},
                                {"id": "mb4", "name": "Custom", "role": None},
                            ]
                        },
                        "0",
                    ]
                ]
            },
        )

        provider = JMAPProvider(api_token="abc")
        boxes = await provider.list_mailboxes()
        roles = {b.name: b.role for b in boxes}
        assert roles["INBOX"] == SpecialFolder.inbox
        assert roles["Archive"] == SpecialFolder.archive
        assert roles["Trash"] == SpecialFolder.trash
        assert roles["Custom"] is None
