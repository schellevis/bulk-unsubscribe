"""Importing this module ensures every model is registered on Base.metadata."""

from app.db import Base
from app.models.account import Account, ProviderType
from app.models.action import Action, ActionKind, ActionStatus
from app.models.job import Job, JobStatus, JobType
from app.models.message import Message
from app.models.sender import Sender, SenderAlias, SenderStatus, WhitelistScope


def register_all() -> type[Base]:
    return Base


__all__ = [
    "Account",
    "ProviderType",
    "Sender",
    "SenderAlias",
    "SenderStatus",
    "WhitelistScope",
    "Message",
    "Job",
    "JobStatus",
    "JobType",
    "Action",
    "ActionKind",
    "ActionStatus",
    "register_all",
]
