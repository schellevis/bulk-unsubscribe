"""Importing this module ensures every model is registered on Base.metadata."""

from app.db import Base


def register_all() -> type[Base]:
    return Base
