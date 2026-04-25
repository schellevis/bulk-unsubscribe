from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class WhitelistKind(StrEnum):
    sender = "sender"
    domain = "domain"
    mailbox = "mailbox"


class WhitelistRule(Base):
    __tablename__ = "whitelist_rules"
    __table_args__ = (
        UniqueConstraint("account_id", "kind", "value", name="uq_whitelist_rule"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[WhitelistKind] = mapped_column(
        SAEnum(WhitelistKind, name="whitelist_kind"), nullable=False
    )
    value: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
