"""Auth gate behavior."""

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


def test_no_password_means_open_access(monkeypatch, db_session):
    monkeypatch.delenv("BU_AUTH_PASSWORD", raising=False)
    get_settings.cache_clear()
    with TestClient(app) as client:
        r = client.get("/healthz")
        assert r.status_code == 200
        r2 = client.get("/accounts")
        assert r2.status_code == 200


def test_with_password_redirects_anonymous(monkeypatch, db_session):
    monkeypatch.setenv("BU_AUTH_PASSWORD", "secret")
    get_settings.cache_clear()
    with TestClient(app) as client:
        r = client.get("/", follow_redirects=False)
        assert r.status_code == 303
        assert "/login" in r.headers["location"]


def test_login_with_correct_password_grants_access(monkeypatch, db_session):
    monkeypatch.setenv("BU_AUTH_PASSWORD", "secret")
    get_settings.cache_clear()
    with TestClient(app) as client:
        r = client.post(
            "/login",
            data={"password": "secret", "next": "/accounts"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        r2 = client.get("/accounts")
        assert r2.status_code == 200


def test_login_with_wrong_password_returns_401(monkeypatch, db_session):
    monkeypatch.setenv("BU_AUTH_PASSWORD", "secret")
    get_settings.cache_clear()
    with TestClient(app) as client:
        r = client.post(
            "/login",
            data={"password": "wrong", "next": "/"},
        )
        assert r.status_code == 401
        assert "Wrong password" in r.text


def test_static_and_healthz_remain_public(monkeypatch, db_session):
    monkeypatch.setenv("BU_AUTH_PASSWORD", "secret")
    get_settings.cache_clear()
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/static/css/app.css").status_code == 200


def test_login_next_external_url_falls_back_to_root(monkeypatch, db_session):
    """Open redirect: absolute URL in next must be rejected."""
    monkeypatch.setenv("BU_AUTH_PASSWORD", "secret")
    get_settings.cache_clear()
    with TestClient(app) as client:
        r = client.post(
            "/login",
            data={"password": "secret", "next": "https://example.com/phish"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/"


def test_login_next_protocol_relative_url_falls_back_to_root(monkeypatch, db_session):
    """Open redirect: protocol-relative URL in next must be rejected."""
    monkeypatch.setenv("BU_AUTH_PASSWORD", "secret")
    get_settings.cache_clear()
    with TestClient(app) as client:
        r = client.post(
            "/login",
            data={"password": "secret", "next": "//evil.example.com"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/"


def test_login_next_valid_local_path_is_preserved(monkeypatch, db_session):
    """A normal relative path must be kept as-is."""
    monkeypatch.setenv("BU_AUTH_PASSWORD", "secret")
    get_settings.cache_clear()
    with TestClient(app) as client:
        r = client.post(
            "/login",
            data={"password": "secret", "next": "/accounts"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/accounts"
