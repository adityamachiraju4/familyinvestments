"""Persist day-scoped order books and deduplicated execution fills.

Revision ID: 0003_execution_activity
Revises: 0002_holding_lifecycle
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_execution_activity"
down_revision = "0002_holding_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("zerodha_accounts", sa.Column("last_refresh_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("book_date", sa.Date(), nullable=True))
    for name, kind in (
        ("zerodha_trade_id", sa.String(64)), ("zerodha_order_id", sa.String(64)),
        ("instrument_token", sa.BigInteger()), ("product", sa.String(32)),
        ("transaction_type", sa.String(16)), ("fill_timestamp", sa.DateTime(timezone=True)),
        ("synced_at", sa.DateTime(timezone=True)),
    ):
        op.add_column("investment_transactions", sa.Column(name, kind, nullable=True))
    for name in ("charges", "net_amount"):
        op.alter_column("investment_transactions", name, existing_type=sa.Numeric(20, 4), nullable=True)
    op.create_unique_constraint("uq_investment_transactions_provider_fill", "investment_transactions",
                                ["account_id", "trade_date", "exchange", "zerodha_order_id", "zerodha_trade_id"])


def downgrade():
    # PostgreSQL rejects this downgrade if unknown amounts exist. Transactional
    # DDL leaves the schema/data intact; never invent charges to force downgrade.
    for name in ("charges", "net_amount"):
        op.alter_column("investment_transactions", name, existing_type=sa.Numeric(20, 4), nullable=False)
    op.drop_constraint("uq_investment_transactions_provider_fill", "investment_transactions", type_="unique")
    for name in ("synced_at", "fill_timestamp", "transaction_type", "product", "instrument_token", "zerodha_order_id", "zerodha_trade_id"):
        op.drop_column("investment_transactions", name)
    op.drop_column("orders", "book_date")
    op.drop_column("zerodha_accounts", "last_refresh_at")
