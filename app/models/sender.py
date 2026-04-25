from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class SenderStatus(StrEnum):
    active = "active"
    unsubscribed = "unsubscribed"
    whitelisted = "whitelisted"
    trashed = "trashed"
    archived = "archived"


class WhitelistScope(StrEnum):
    none = "none"
    sender = "sender"
    domain = "domain"


class Sender(Base):
    __tablename__ = "senders"
    __table_args__ = (
        UniqueConstraint("account_id", "group_key", name="uq_sender_account_group"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    group_key: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    from_email: Mapped[str] = mapped_column(String(320), nullable=False)
    from_domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    list_id: Mapped[str | None] = mapped_column(String(512))
    display_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    email_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unsubscribe_http: Mapped[str | None] = mapped_column(Text)
    unsubscribe_mailto: Mapped[str | None] = mapped_column(Text)
    unsubscribe_one_click_post: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    status: Mapped[SenderStatus] = mapped_column(
        SAEnum(SenderStatus, name="sender_status"),
        default=SenderStatus.active,
        nullable=False,
        index=True,
    )
    whitelist_scope: Mapped[WhitelistScope] = mapped_column(
        SAEnum(WhitelistScope, name="whitelist_scope"),
        default=WhitelistScope.none,
        nullable=False,
    )
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    aliases: Mapped[list["SenderAlias"]] = relationship(
        "SenderAlias", back_populates="sender", cascade="all, delete-orphan"
    )


class SenderAlias(Base):
    __tablename__ = "sender_aliases"
    __table_args__ = (
        UniqueConstraint("sender_id", "from_email", name="uq_alias_sender_email"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sender_id: Mapped[int] = mapped_column(
        ForeignKey("senders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    from_domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    email_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    sender: Mapped[Sender] = relationship("Sender", back_populates="aliases")
