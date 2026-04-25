from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings, get_settings


class CredentialCipher:
    def __init__(self, key: str) -> None:
        try:
            self._fernet = Fernet(key.encode())
        except (ValueError, TypeError) as exc:
            raise ValueError(
                "Invalid Fernet key. Generate one with "
                "`python -c 'from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())'`"
            ) from exc

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "CredentialCipher":
        return cls((settings or get_settings()).fernet_key)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Stored credential could not be decrypted") from exc
