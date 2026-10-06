"""Create initial family investment schema.

Revision ID: 0001_initial_schema
Revises:
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('zerodha_accounts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.String(length=64), nullable=False),
    sa.Column('display_name', sa.String(length=255), nullable=False),
    sa.Column('connection_status', sa.String(length=32), server_default='disconnected', nullable=False),
    sa.Column('last_authenticated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_zerodha_accounts')),
    sa.UniqueConstraint('client_id', name=op.f('uq_zerodha_accounts_client_id'))
    )
    op.create_table('holding_snapshots',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('snapshot_date', sa.Date(), nullable=False),
    sa.Column('exchange', sa.String(length=16), nullable=False),
    sa.Column('tradingsymbol', sa.String(length=128), nullable=False),
    sa.Column('bucket', sa.String(length=9), server_default='OTHER', nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('average_price', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('last_price', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('invested_value', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('market_value', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('pnl', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('pnl_percent', sa.Numeric(precision=12, scale=6), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("bucket IN ('NIFTY_50', 'MID_CAP', 'SMALL_CAP', 'LARGE_CAP', 'OTHER')", name=op.f('ck_holding_snapshots_bucket')),
    sa.ForeignKeyConstraint(['account_id'], ['zerodha_accounts.id'], name=op.f('fk_holding_snapshots_account_id_zerodha_accounts')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_holding_snapshots')),
    sa.UniqueConstraint('account_id', 'snapshot_date', 'exchange', 'tradingsymbol', name=op.f('uq_holding_snapshots_account_id'))
    )
    op.create_index('ix_holding_snapshots_account_date', 'holding_snapshots', ['account_id', 'snapshot_date'], unique=False)
    op.create_table('holdings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('exchange', sa.String(length=16), nullable=False),
    sa.Column('tradingsymbol', sa.String(length=128), nullable=False),
    sa.Column('instrument_token', sa.BigInteger(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('t1_quantity', sa.Integer(), nullable=False),
    sa.Column('average_price', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('last_price', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('invested_value', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('current_value', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('unrealised_pnl', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('unrealised_pnl_percent', sa.Numeric(precision=12, scale=6), nullable=False),
    sa.Column('bucket', sa.String(length=9), server_default='OTHER', nullable=False),
    sa.Column('synced_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("bucket IN ('NIFTY_50', 'MID_CAP', 'SMALL_CAP', 'LARGE_CAP', 'OTHER')", name=op.f('ck_holdings_bucket')),
    sa.ForeignKeyConstraint(['account_id'], ['zerodha_accounts.id'], name=op.f('fk_holdings_account_id_zerodha_accounts')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_holdings')),
    sa.UniqueConstraint('account_id', 'exchange', 'tradingsymbol', name=op.f('uq_holdings_account_id'))
    )
    op.create_table('monthly_targets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('month', sa.Date(), nullable=False),
    sa.Column('total_target', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('nifty_target', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('midcap_target', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('smallcap_target', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('EXTRACT(DAY FROM month) = 1', name=op.f('ck_monthly_targets_month_first_day')),
    sa.ForeignKeyConstraint(['account_id'], ['zerodha_accounts.id'], name=op.f('fk_monthly_targets_account_id_zerodha_accounts')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_monthly_targets')),
    sa.UniqueConstraint('account_id', 'month', name=op.f('uq_monthly_targets_account_id'))
    )
    op.create_table('orders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('zerodha_order_id', sa.String(length=64), nullable=False),
    sa.Column('tradingsymbol', sa.String(length=128), nullable=False),
    sa.Column('exchange', sa.String(length=16), nullable=False),
    sa.Column('transaction_type', sa.String(length=16), nullable=False),
    sa.Column('product', sa.String(length=32), nullable=False),
    sa.Column('order_type', sa.String(length=32), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('filled_quantity', sa.Integer(), nullable=False),
    sa.Column('price', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('average_price', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('order_timestamp', sa.DateTime(timezone=True), nullable=False),
    sa.Column('exchange_timestamp', sa.DateTime(timezone=True), nullable=True),
    sa.Column('synced_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['zerodha_accounts.id'], name=op.f('fk_orders_account_id_zerodha_accounts')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_orders')),
    sa.UniqueConstraint('account_id', 'zerodha_order_id', name=op.f('uq_orders_account_id'))
    )
    op.create_table('portfolio_snapshots',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('snapshot_date', sa.Date(), nullable=False),
    sa.Column('available_cash', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('holdings_invested_value', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('holdings_market_value', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('portfolio_value', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('total_account_value', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('day_pnl', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('total_pnl', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('total_pnl_percent', sa.Numeric(precision=12, scale=6), nullable=False),
    sa.Column('nifty_value', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('midcap_value', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('smallcap_value', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('other_value', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['zerodha_accounts.id'], name=op.f('fk_portfolio_snapshots_account_id_zerodha_accounts')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_portfolio_snapshots')),
    sa.UniqueConstraint('account_id', 'snapshot_date', name=op.f('uq_portfolio_snapshots_account_id'))
    )
    op.create_table('zerodha_credentials',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('encrypted_access_token', sa.Text(), nullable=False),
    sa.Column('token_created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['zerodha_accounts.id'], name=op.f('fk_zerodha_credentials_account_id_zerodha_accounts')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_zerodha_credentials')),
    sa.UniqueConstraint('account_id', name=op.f('uq_zerodha_credentials_account_id'))
    )
    op.create_table('investment_transactions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=True),
    sa.Column('trade_date', sa.Date(), nullable=False),
    sa.Column('tradingsymbol', sa.String(length=128), nullable=False),
    sa.Column('exchange', sa.String(length=16), nullable=False),
    sa.Column('bucket', sa.String(length=9), server_default='OTHER', nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('price', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('gross_amount', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('charges', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('net_amount', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("bucket IN ('NIFTY_50', 'MID_CAP', 'SMALL_CAP', 'LARGE_CAP', 'OTHER')", name=op.f('ck_investment_transactions_bucket')),
    sa.ForeignKeyConstraint(['account_id'], ['zerodha_accounts.id'], name=op.f('fk_investment_transactions_account_id_zerodha_accounts')),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_investment_transactions_order_id_orders')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_investment_transactions'))
    )


def downgrade() -> None:
    op.drop_table('investment_transactions')
    op.drop_table('zerodha_credentials')
    op.drop_table('portfolio_snapshots')
    op.drop_table('orders')
    op.drop_table('monthly_targets')
    op.drop_table('holdings')
    op.drop_index('ix_holding_snapshots_account_date', table_name='holding_snapshots')
    op.drop_table('holding_snapshots')
    op.drop_table('zerodha_accounts')
