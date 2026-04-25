from datetime import datetime
from enum import Enum

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ActionKind(str, Enum):
    unsubscribe_http = "unsubscribe_http"
    unsubscribe_one_click = "unsubscribe_one_click"
    unsubscribe_mailto = "unsubscribe_mailto"
    archive = "archive"
    trash = "trash"
    mark_read = "mark_read"
    whitelist = "whitelist"
    unwhitelist = "unwhitelist"


class ActionStatus(str, Enum):
    success = "success"
    failed = "failed"
    partial = "partial"


class Action(Base):
    __tablename__ = "actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender_id: Mapped[int] = mapped_column(
        ForeignKey("senders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL")
    )
    kind: Mapped[ActionKind] = mapped_column(
        SAEnum(ActionKind, name="action_kind"), nullable=False
    )
    status: Mapped[ActionStatus] = mapped_column(
        SAEnum(ActionStatus, name="action_status"), nullable=False
    )
    affected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
