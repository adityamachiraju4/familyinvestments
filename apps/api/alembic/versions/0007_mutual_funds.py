"""Household mutual-fund planning; no seed data."""
from alembic import op
from sqlalchemy import Column, Integer, String, Date, DateTime, Boolean, Numeric, Enum, ForeignKey, UniqueConstraint, CheckConstraint, text
revision = "0007_mutual_funds"
down_revision = "0006_zerodha_login_state"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('mutual_fund_accounts',
        Column('id', Integer(), primary_key=True, nullable=False),
        Column('display_name', String(length=255), primary_key=False, nullable=False),
        Column('updated_at', DateTime(timezone=True), primary_key=False, nullable=False, server_default=text('now()')),
        Column('created_at', DateTime(timezone=True), primary_key=False, nullable=False, server_default=text('now()')),
    )
    op.create_table('mutual_fund_schemes',
        Column('id', Integer(), primary_key=True, nullable=False),
        Column('account_id', Integer(), ForeignKey('mutual_fund_accounts.id'), primary_key=False, nullable=False),
        Column('scheme_key', String(length=255), primary_key=False, nullable=False),
        Column('scheme_name', String(length=255), primary_key=False, nullable=False),
        Column('isin', String(length=32), primary_key=False, nullable=True),
        Column('folio_number', String(length=128), primary_key=False, nullable=True),
        Column('plan_type', String(length=64), primary_key=False, nullable=True),
        Column('option_type', String(length=64), primary_key=False, nullable=True),
        Column('category', Enum('NIFTY_50', 'LARGE_CAP', 'MID_CAP', 'SMALL_CAP', 'FLEXI_CAP', 'MULTI_CAP', 'HYBRID', 'DEBT', 'GOLD', 'INTERNATIONAL', 'OTHER', 'UNCLASSIFIED', name='mf_category', native_enum=False, create_constraint=True), primary_key=False, nullable=False),
        Column('currency', String(length=3), primary_key=False, nullable=False),
        Column('history_complete', Boolean(), primary_key=False, nullable=False),
        Column('updated_at', DateTime(timezone=True), primary_key=False, nullable=False, server_default=text('now()')),
        Column('created_at', DateTime(timezone=True), primary_key=False, nullable=False, server_default=text('now()')),
        UniqueConstraint('account_id','scheme_key'),
    )
    op.create_table('sips',
        Column('id', Integer(), primary_key=True, nullable=False),
        Column('scheme_id', Integer(), ForeignKey('mutual_fund_schemes.id'), primary_key=False, nullable=False),
        Column('source', Enum('GROWW', 'CAS', 'MANUAL', name='sip_source', native_enum=False, create_constraint=True), primary_key=False, nullable=False),
        Column('monthly_amount', Numeric(precision=20, scale=4), primary_key=False, nullable=False),
        Column('sip_day', Integer(), primary_key=False, nullable=True),
        Column('start_date', Date(), primary_key=False, nullable=False),
        Column('end_date', Date(), primary_key=False, nullable=True),
        Column('status', String(length=16), primary_key=False, nullable=False),
        Column('updated_at', DateTime(timezone=True), primary_key=False, nullable=False, server_default=text('now()')),
        Column('created_at', DateTime(timezone=True), primary_key=False, nullable=False, server_default=text('now()')),
        CheckConstraint('monthly_amount > 0', name='positive_amount'),
        CheckConstraint('end_date IS NULL OR end_date >= start_date', name='valid_dates'),
        CheckConstraint('sip_day IS NULL OR (sip_day >= 1 AND sip_day <= 31)', name='valid_day'),
        CheckConstraint("status IN ('ACTIVE','PAUSED','STOPPED')", name='valid_status'),
    )
    op.create_table('mutual_fund_transactions',
        Column('id', Integer(), primary_key=True, nullable=False),
        Column('scheme_id', Integer(), ForeignKey('mutual_fund_schemes.id'), primary_key=False, nullable=False),
        Column('sip_id', Integer(), ForeignKey('sips.id'), primary_key=False, nullable=True),
        Column('source', Enum('GROWW', 'CAS', 'MANUAL', name='mf_transaction_source', native_enum=False, create_constraint=True), primary_key=False, nullable=False),
        Column('import_key', String(length=255), primary_key=False, nullable=False),
        Column('transaction_date', Date(), primary_key=False, nullable=False),
        Column('transaction_type', String(length=32), primary_key=False, nullable=False),
        Column('amount', Numeric(precision=20, scale=4), primary_key=False, nullable=False),
        Column('units', Numeric(precision=24, scale=8), primary_key=False, nullable=True),
        Column('nav', Numeric(precision=24, scale=8), primary_key=False, nullable=True),
        Column('status', String(length=16), primary_key=False, nullable=False),
        Column('created_at', DateTime(timezone=True), primary_key=False, nullable=False, server_default=text('now()')),
        CheckConstraint('amount > 0', name='positive_amount'),
        CheckConstraint("status IN ('CONFIRMED','PENDING','CANCELLED')", name='valid_status'),
        CheckConstraint("transaction_type IN ('PURCHASE','SIP','REDEMPTION','SWITCH_IN','SWITCH_OUT','DIVIDEND')", name='valid_type'),
        UniqueConstraint('scheme_id','source','import_key'),
    )
    op.create_table('mutual_fund_holdings',
        Column('scheme_id', Integer(), ForeignKey('mutual_fund_schemes.id'), primary_key=True, nullable=False),
        Column('source', Enum('GROWW', 'CAS', 'MANUAL', name='mf_holding_source', native_enum=False, create_constraint=True), primary_key=False, nullable=False),
        Column('units', Numeric(precision=24, scale=8), primary_key=False, nullable=True),
        Column('invested_amount', Numeric(precision=20, scale=4), primary_key=False, nullable=True),
        Column('latest_nav', Numeric(precision=24, scale=8), primary_key=False, nullable=True),
        Column('current_value', Numeric(precision=20, scale=4), primary_key=False, nullable=False),
        Column('valuation_date', Date(), primary_key=False, nullable=False),
        Column('updated_at', DateTime(timezone=True), primary_key=False, nullable=False, server_default=text('now()')),
        Column('created_at', DateTime(timezone=True), primary_key=False, nullable=False, server_default=text('now()')),
        CheckConstraint('current_value >= 0', name='nonnegative_value'),
    )

def downgrade():
    op.drop_table('mutual_fund_holdings')
    op.drop_table('mutual_fund_transactions')
    op.drop_table('sips')
    op.drop_table('mutual_fund_schemes')
    op.drop_table('mutual_fund_accounts')
