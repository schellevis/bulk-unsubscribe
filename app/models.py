from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ProviderType(str, PyEnum):
    imap = "imap"
    fastmail = "fastmail"


class SenderStatus(str, PyEnum):
    active = "active"
    unsubscribed = "unsubscribed"
    pending = "pending"


class UnsubscribeStatus(str, PyEnum):
    success = "success"
    failed = "failed"
    pending = "pending"


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    provider: Mapped[ProviderType] = mapped_column(
        Enum(ProviderType), nullable=False, default=ProviderType.imap
    )
    # IMAP settings
    imap_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    imap_port: Mapped[int | None] = mapped_column(Integer, nullable=True, default=993)
    imap_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Encrypted credential storage (password for IMAP, token for Fastmail)
    credential: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_scan: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    senders: Mapped[list["Sender"]] = relationship("Sender", back_populates="account")


class Sender(Base):
    __tablename__ = "senders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_count: Mapped[int] = mapped_column(Integer, default=0)
    unsubscribe_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    unsubscribe_mailto: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[SenderStatus] = mapped_column(
        Enum(SenderStatus), nullable=False, default=SenderStatus.active
    )
    first_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    account: Mapped["Account"] = relationship("Account", back_populates="senders")
    unsubscribe_attempts: Mapped[list["UnsubscribeAttempt"]] = relationship(
        "UnsubscribeAttempt", back_populates="sender"
    )


class UnsubscribeAttempt(Base):
    __tablename__ = "unsubscribe_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sender_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("senders.id", ondelete="CASCADE"), nullable=False
    )
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    method: Mapped[str] = mapped_column(String(50), nullable=False)  # "http" or "mailto"
    status: Mapped[UnsubscribeStatus] = mapped_column(
        Enum(UnsubscribeStatus), nullable=False, default=UnsubscribeStatus.pending
    )
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    sender: Mapped["Sender"] = relationship("Sender", back_populates="unsubscribe_attempts")
