"""Revocable dashboard sessions and shared authentication attempt windows."""
from alembic import op
import sqlalchemy as sa
revision = '0005_dashboard_auth'
down_revision = '0004_classification'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('dashboard_sessions',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('token_hash',sa.String(64),nullable=False),
        sa.Column('credential_version',sa.String(64),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('token_hash'))
    op.create_index('ix_dashboard_sessions_expires_at','dashboard_sessions',['expires_at'])
    op.create_table('dashboard_login_attempts',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('key_hash',sa.String(64),nullable=False),
        sa.Column('window_started_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('attempts',sa.Integer(),nullable=False),
        sa.UniqueConstraint('key_hash'))


def downgrade():
    op.drop_table('dashboard_login_attempts')
    op.drop_index('ix_dashboard_sessions_expires_at',table_name='dashboard_sessions')
    op.drop_table('dashboard_sessions')
