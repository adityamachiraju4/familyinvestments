"""Preserve holding identities while tracking active current membership.

Revision ID: 0002_holding_lifecycle
Revises: 0001_initial_schema
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_holding_lifecycle"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Preserve existing visibility until a successful complete sync reconciles it.
    op.add_column("holdings", sa.Column(
        "is_active", sa.Boolean(), nullable=False, server_default=sa.true(),
    ))


def downgrade() -> None:
    op.drop_column("holdings", "is_active")
