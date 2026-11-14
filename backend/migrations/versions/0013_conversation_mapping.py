"""Persist conversation progression and exact human-confirmed column mappings."""
import sqlalchemy as sa
from alembic import op

revision = '0013'
down_revision = '0012'
branch_labels = depends_on = None


def upgrade():
    op.add_column('conversations', sa.Column('workflow_state', sa.JSON))
    op.create_table(
        'mapping_proposals',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('conversation_id', sa.String(36), sa.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('actor_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('project_id', sa.Integer, sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('version', sa.Integer, nullable=False),
        sa.Column('sheets', sa.JSON, nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('created_at', sa.Integer, nullable=False),
        sa.Column('confirmed_at', sa.Integer),
        sa.Column('confirmed_by', sa.Integer, sa.ForeignKey('users.id')),
    )
    op.create_index('ix_mapping_proposals_conversation_id', 'mapping_proposals', ['conversation_id'])


def downgrade():
    raise RuntimeError('Mapping decisions are forward-only evidence')
