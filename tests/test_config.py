import pytest

from app.config import Settings, get_settings


def test_settings_loads_from_env(monkeypatch, tmp_path):
    get_settings.cache_clear()
    monkeypatch.setenv("BU_FERNET_KEY", "x" * 44 + "=")
    monkeypatch.setenv("BU_DATA_DIR", str(tmp_path))
    settings = Settings()
    assert settings.fernet_key == "x" * 44 + "="
    assert settings.data_dir == tmp_path
    assert settings.database_url == f"sqlite:///{tmp_path}/bulk-unsubscribe.db"


def test_settings_requires_fernet_key(monkeypatch, tmp_path):
    get_settings.cache_clear()
    monkeypatch.delenv("BU_FERNET_KEY", raising=False)
    monkeypatch.setenv("BU_DATA_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="fernet_key"):
        Settings()


def test_settings_creates_data_dir(monkeypatch, tmp_path):
    get_settings.cache_clear()
    target = tmp_path / "missing"
    monkeypatch.setenv("BU_FERNET_KEY", "x" * 44 + "=")
    monkeypatch.setenv("BU_DATA_DIR", str(target))
    Settings()
    assert target.exists()
