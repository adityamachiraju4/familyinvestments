"""One-time session-bound Zerodha callback correlations, independent of cookies."""
from alembic import op
import sqlalchemy as sa
revision = '0006_zerodha_login_state'
down_revision = '0005_dashboard_auth'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('zerodha_login_states',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('account_id',sa.Integer(),sa.ForeignKey('zerodha_accounts.id'),nullable=False),
        sa.Column('dashboard_session_id',sa.Integer(),sa.ForeignKey('dashboard_sessions.id',ondelete='CASCADE'),nullable=False),
        sa.Column('state_hash',sa.String(64),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('consumed_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.UniqueConstraint('state_hash'))
    op.create_index('ix_zerodha_login_states_expires_at','zerodha_login_states',['expires_at'])


def downgrade():
    op.drop_index('ix_zerodha_login_states_expires_at',table_name='zerodha_login_states')
    op.drop_table('zerodha_login_states')
