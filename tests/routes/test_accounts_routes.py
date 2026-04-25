from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.account import Account, ProviderType


def test_list_accounts_empty(db_session):
    with TestClient(app) as client:
        response = client.get("/accounts")
        assert response.status_code == 200
        assert "No accounts yet" in response.text


def test_create_jmap_account_with_valid_token(db_session):
    async def fake_test_credentials(self):
        return True

    with TestClient(app) as client, patch(
        "app.providers.jmap.JMAPProvider.test_credentials", new=fake_test_credentials
    ):
        response = client.post(
            "/accounts/jmap",
            data={
                "name": "Fastmail",
                "email": "me@fastmail.com",
                "api_token": "secret-token",
            },
            follow_redirects=False,
        )
    assert response.status_code in (303, 200)

    account = db_session.query(Account).filter_by(email="me@fastmail.com").one()
    assert account.provider == ProviderType.jmap
    assert account.credential_encrypted != "secret-token"


def test_create_jmap_account_rejects_bad_token(db_session):
    async def fake_test_credentials(self):
        return False

    with TestClient(app) as client, patch(
        "app.providers.jmap.JMAPProvider.test_credentials", new=fake_test_credentials
    ):
        response = client.post(
            "/accounts/jmap",
            data={
                "name": "Fastmail",
                "email": "me@fastmail.com",
                "api_token": "bad",
            },
        )
    assert response.status_code == 400


def test_delete_account(db_session):
    account = Account(
        name="X",
        email="x@y.com",
        provider=ProviderType.jmap,
        credential_encrypted="x",
    )
    db_session.add(account)
    db_session.commit()

    with TestClient(app) as client:
        response = client.post(
            f"/accounts/{account.id}/delete", follow_redirects=False
        )
    assert response.status_code in (303, 200)

    db_session.expire_all()
    from sqlalchemy.orm.exc import ObjectDeletedError
    try:
        result = db_session.get(Account, account.id)
    except ObjectDeletedError:
        result = None
    assert result is None
