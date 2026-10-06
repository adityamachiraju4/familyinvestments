"""Brokerage account and encrypted credential storage schema."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.common import Timestamps


class ZerodhaAccount(Timestamps, Base):
    __tablename__ = "zerodha_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(255))
    connection_status: Mapped[str] = mapped_column(String(32), default="disconnected", server_default="disconnected")
    last_authenticated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ZerodhaCredential(Timestamps, Base):
    __tablename__ = "zerodha_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("zerodha_accounts.id"), unique=True)
    encrypted_access_token: Mapped[str] = mapped_column(Text)
    token_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
