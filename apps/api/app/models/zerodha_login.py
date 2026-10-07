"""Cookie-independent, short-lived brokerage login correlations."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.common import CreatedAt


class ZerodhaLoginState(CreatedAt, Base):
    __tablename__ = "zerodha_login_states"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("zerodha_accounts.id"))
    dashboard_session_id: Mapped[int] = mapped_column(ForeignKey("dashboard_sessions.id", ondelete="CASCADE"))
    state_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
