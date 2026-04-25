from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SAEnum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ProviderType(str, Enum):
    imap = "imap"
    jmap = "jmap"


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    provider: Mapped[ProviderType] = mapped_column(
        SAEnum(ProviderType, name="provider_type"), nullable=False
    )
    imap_host: Mapped[str | None] = mapped_column(String(255))
    imap_port: Mapped[int | None] = mapped_column(Integer)
    imap_username: Mapped[str | None] = mapped_column(String(255))
    credential_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    last_full_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_incremental_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
