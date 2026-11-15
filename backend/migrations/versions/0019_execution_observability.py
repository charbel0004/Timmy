"""Add isolated execution metadata without changing business records."""
from alembic import op
import sqlalchemy as sa
revision = '0019'
down_revision = '0018'
branch_labels = depends_on = None

def upgrade():
    op.create_table('execution_runs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('trace_id', sa.String(32), nullable=False, unique=True),
        sa.Column('actor_id', sa.Integer, sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('conversation_id', sa.String(36)),
        sa.Column('project_ids', sa.JSON, nullable=False),
        sa.Column('heartbeat_at', sa.String(40), nullable=False),
        sa.Column('access_grants', sa.JSON, nullable=False),
        sa.Column('operation', sa.String(100), nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('started_at', sa.String(40), nullable=False),
        sa.Column('ended_at', sa.String(40)))
    for name in ('actor_id', 'conversation_id', 'started_at'):
        op.create_index('ix_execution_runs_' + name, 'execution_runs', [name])
    op.create_index('ix_execution_runs_status_heartbeat', 'execution_runs', ['status', 'heartbeat_at'])
    op.create_index('ix_execution_runs_actor_started', 'execution_runs', ['actor_id', 'started_at'])
    op.create_table('execution_events',
        sa.Column('event_id', sa.String(36), primary_key=True),
        sa.Column('run_id', sa.String(36), sa.ForeignKey('execution_runs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sequence_number', sa.Integer, nullable=False),
        sa.Column('payload', sa.JSON, nullable=False),
        sa.UniqueConstraint('run_id', 'sequence_number'))
    op.create_index('ix_execution_events_run_id', 'execution_events', ['run_id'])

def downgrade():
    op.drop_table('execution_events')
    op.drop_table('execution_runs')
