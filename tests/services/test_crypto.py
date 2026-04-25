import pytest
from cryptography.fernet import Fernet

from app.config import get_settings
from app.services.crypto import CredentialCipher


def test_roundtrip_encryption(monkeypatch, tmp_path):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("BU_FERNET_KEY", key)
    monkeypatch.setenv("BU_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()

    cipher = CredentialCipher.from_settings()
    token = cipher.encrypt("hunter2")
    assert token != "hunter2"
    assert cipher.decrypt(token) == "hunter2"


def test_invalid_key_raises_at_construction(monkeypatch, tmp_path):
    monkeypatch.setenv("BU_FERNET_KEY", "not-a-real-fernet-key")
    monkeypatch.setenv("BU_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="Fernet"):
        CredentialCipher.from_settings()
