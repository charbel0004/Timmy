"""Approved Excel reporting designation, provenance declarations and decisions."""
from alembic import op
import sqlalchemy as sa
revision = '0020'
down_revision = '0019'
branch_labels = depends_on = None


def upgrade():
    op.create_table('reporting_register_sources',
        sa.Column('id', sa.String(36), primary_key=True), sa.Column('name', sa.String(160), nullable=False),
        sa.Column('project_ids', sa.JSON, nullable=False),
        sa.Column('approved_by', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('approved_at', sa.Integer, nullable=False))
    op.create_table('reporting_register_imports',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('source_id', sa.String(36), sa.ForeignKey('reporting_register_sources.id'), nullable=False),
        sa.Column('file_id', sa.String(36), sa.ForeignKey('stored_files.id'), nullable=False),
        sa.Column('actor_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('sha256', sa.String(64), nullable=False), sa.Column('mapping_digest', sa.String(64), nullable=False),
        sa.Column('mappings', sa.JSON, nullable=False), sa.Column('rows', sa.JSON, nullable=False),
        sa.Column('confirmed_at', sa.String(40), nullable=False), sa.Column('assurance', sa.String(60), nullable=False),
        sa.UniqueConstraint('source_id','actor_id','sha256'))
    op.create_table('reporting_register_decisions',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('import_id', sa.String(36), sa.ForeignKey('reporting_register_imports.id'), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False), sa.Column('snapshot', sa.JSON, nullable=False),
        sa.Column('evaluated_at', sa.Integer, nullable=False), sa.UniqueConstraint('import_id','fingerprint'))
    op.create_index('ix_reporting_register_decisions_import_id','reporting_register_decisions',['import_id'])

    op.create_table('workflow_payment_drafts',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('actor_id',sa.Integer,sa.ForeignKey('users.id'),nullable=False),
        sa.Column('conversation_id',sa.String(36),sa.ForeignKey('conversations.id'),nullable=False),
        sa.Column('project_id',sa.Integer,sa.ForeignKey('projects.id'),nullable=False),
        sa.Column('digest',sa.String(64),nullable=False),sa.Column('snapshot',sa.JSON,nullable=False),
        sa.Column('created_at',sa.String(40),nullable=False),sa.UniqueConstraint('actor_id','digest'))
    op.create_table('workflow_payment_approvals',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('draft_id',sa.String(36),sa.ForeignKey('workflow_payment_drafts.id'),unique=True,nullable=False),
        sa.Column('digest',sa.String(64),nullable=False),sa.Column('actor_id',sa.Integer,sa.ForeignKey('users.id'),nullable=False),
        sa.Column('approved_at',sa.Integer,nullable=False))
    op.create_table('workflow_credit_reservations',
        sa.Column('credit_key',sa.String(64),primary_key=True),
        sa.Column('draft_id',sa.String(36),sa.ForeignKey('workflow_payment_drafts.id'),nullable=False))
    op.create_table('workflow_payment_exports',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('draft_id',sa.String(36),sa.ForeignKey('workflow_payment_drafts.id'),unique=True,nullable=False),
        sa.Column('approval_id',sa.String(36),sa.ForeignKey('workflow_payment_approvals.id'),nullable=False),
        sa.Column('sha256',sa.String(64),nullable=False),sa.Column('created_at',sa.Integer,nullable=False))


def downgrade():
    op.drop_table('workflow_payment_exports')
    op.drop_table('workflow_credit_reservations')
    op.drop_table('workflow_payment_approvals')
    op.drop_table('workflow_payment_drafts')
    op.drop_table('reporting_register_decisions')
    op.drop_table('reporting_register_imports')
    op.drop_table('reporting_register_sources')
