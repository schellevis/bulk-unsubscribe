"""Importing this module ensures every model is registered on Base.metadata."""

from app.db import Base
from app.models.account import Account, ProviderType


def register_all() -> type[Base]:
    return Base


__all__ = ["Account", "ProviderType", "register_all"]
