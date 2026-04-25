import base64
import os

from cryptography.fernet import Fernet

# In production this key should come from a secure environment variable.
# For development we derive a stable key from a fixed secret.
_SECRET = os.environ.get("CREDENTIAL_SECRET", "dev-secret-do-not-use-in-production-00000")
# Fernet requires a 32-byte url-safe base64-encoded key
_KEY = base64.urlsafe_b64encode(_SECRET.encode()[:32].ljust(32, b"0"))
_fernet = Fernet(_KEY)


def encrypt(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet.decrypt(token.encode()).decode()
