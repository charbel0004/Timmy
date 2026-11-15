"""Persisted end-of-run flag findings and explicit human dispositions."""
from alembic import op
import sqlalchemy as sa
revision = '0021'
down_revision = '0020'
branch_labels = depends_on = None


def upgrade():
    op.create_table('workflow_findings',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.Integer, sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('conversation_id', sa.String(36), sa.ForeignKey('conversations.id'), nullable=False),
        sa.Column('validation_id', sa.Integer, sa.ForeignKey('structural_validations.id'), nullable=False),
        sa.Column('scope', sa.String(16), nullable=False), sa.Column('subject', sa.String(120), nullable=False),
        sa.Column('code', sa.String(80), nullable=False),
        sa.Column('source_refs', sa.JSON, nullable=False), sa.Column('detail', sa.JSON, nullable=False),
        sa.Column('state', sa.String(32), nullable=False), sa.Column('decision', sa.String(24)),
        sa.Column('decided_by', sa.Integer, sa.ForeignKey('users.id')), sa.Column('decided_at', sa.Integer),
        sa.Column('evidence_ref', sa.Text), sa.Column('note', sa.Text), sa.Column('created_at', sa.Integer, nullable=False),
        sa.UniqueConstraint('validation_id', 'conversation_id', 'scope', 'subject', 'code'))
    op.create_index('ix_workflow_findings_validation_id', 'workflow_findings', ['validation_id'])
    op.create_index('ix_workflow_findings_project_id', 'workflow_findings', ['project_id'])


def downgrade():
    op.drop_index('ix_workflow_findings_project_id', table_name='workflow_findings')
    op.drop_index('ix_workflow_findings_validation_id', table_name='workflow_findings')
    op.drop_table('workflow_findings')
