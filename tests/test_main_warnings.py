import logging

from app.main import _warn_on_removed_env_vars


def test_warns_when_legacy_auth_password_is_set(monkeypatch, caplog):
    monkeypatch.setenv("BU_AUTH_PASSWORD", "anything")
    caplog.set_level(logging.WARNING, logger="app.main")
    _warn_on_removed_env_vars()
    assert any(
        "BU_AUTH_PASSWORD" in r.getMessage() and "no longer used" in r.getMessage()
        for r in caplog.records
    )


def test_no_warning_when_legacy_auth_password_unset(monkeypatch, caplog):
    monkeypatch.delenv("BU_AUTH_PASSWORD", raising=False)
    caplog.set_level(logging.WARNING, logger="app.main")
    _warn_on_removed_env_vars()
    assert caplog.records == []
