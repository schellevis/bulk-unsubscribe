from aioresponses import aioresponses

from app.providers.jmap import JMAP_SESSION_URL, JMAPProvider


async def test_test_credentials_succeeds_with_valid_token():
    with aioresponses() as m:
        m.get(
            JMAP_SESSION_URL,
            payload={
                "apiUrl": "https://api.example.com/jmap/api",
                "primaryAccounts": {"urn:ietf:params:jmap:mail": "acct1"},
                "accounts": {"acct1": {}},
            },
        )
        provider = JMAPProvider(api_token="abc")
        assert await provider.test_credentials() is True


async def test_test_credentials_fails_on_401():
    with aioresponses() as m:
        m.get(JMAP_SESSION_URL, status=401)
        provider = JMAPProvider(api_token="bad")
        assert await provider.test_credentials() is False
