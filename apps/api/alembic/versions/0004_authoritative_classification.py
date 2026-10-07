"""Separate unknown classification and snapshot allocation without rewriting history."""
from alembic import op
import sqlalchemy as sa

revision = "0004_classification"
down_revision = "0003_execution_activity"
branch_labels = None
depends_on = None

TABLES = ("holdings", "holding_snapshots", "investment_transactions")
OLD = "'NIFTY_50', 'MID_CAP', 'SMALL_CAP', 'LARGE_CAP', 'OTHER'"


def upgrade():
    for table in TABLES:
        op.drop_constraint(op.f(f"ck_{table}_bucket"), table, type_="check")
        op.alter_column(table, "bucket", existing_type=sa.String(9), type_=sa.String(12), server_default="UNCLASSIFIED")
        op.create_check_constraint(op.f(f"ck_{table}_bucket"), table, f"bucket IN ({OLD}, 'UNCLASSIFIED')")
    # Null on historical rows means unknown/unrecorded, not fabricated zero.
    op.add_column("portfolio_snapshots", sa.Column("unclassified_value", sa.Numeric(20, 4), nullable=True))


def downgrade():
    # Refuse loss of classifications or recorded allocation rather than fold into OTHER.
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM portfolio_snapshots WHERE unclassified_value <> 0) THEN RAISE EXCEPTION 'Unclassified snapshot allocation prevents downgrade'; END IF; END $$")
    for table in TABLES:
        op.drop_constraint(op.f(f"ck_{table}_bucket"), table, type_="check")
        op.create_check_constraint(op.f(f"ck_{table}_bucket"), table, f"bucket IN ({OLD})")
        op.alter_column(table, "bucket", existing_type=sa.String(12), type_=sa.String(9), server_default="OTHER")
    op.drop_column("portfolio_snapshots", "unclassified_value")
