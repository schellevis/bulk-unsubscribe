"""Build a MailProvider from a stored Account row."""

from app.models.account import Account, ProviderType
from app.providers.imap import IMAPProvider
from app.providers.jmap import JMAPProvider
from app.services.crypto import CredentialCipher


def build_provider(account: Account):
    cipher = CredentialCipher.from_settings()
    secret = cipher.decrypt(account.credential_encrypted)
    if account.provider == ProviderType.imap:
        return IMAPProvider(
            account.imap_host or "",
            account.imap_port or 993,
            account.imap_username or "",
            secret,
        )
    if account.provider == ProviderType.jmap:
        return JMAPProvider(api_token=secret)
    raise ValueError(f"Unknown provider: {account.provider}")
