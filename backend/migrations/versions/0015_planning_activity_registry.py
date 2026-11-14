"""Link sidebar, planning evidence and external reports through activity codes."""
import sqlalchemy as sa
from alembic import op

revision='0015'
down_revision='0014'
branch_labels = depends_on = None


def upgrade():
    op.add_column('activities', sa.Column('activity_code', sa.String(88)))
    op.add_column('activities', sa.Column('planned_start', sa.String(10)))
    op.add_column('activities', sa.Column('planned_end', sa.String(10)))
    op.create_index('uq_activities_project_activity_code','activities',['project_id','activity_code'],unique=True)
    # Legacy sidebar activities remain uncoded; never guess a source identity.
    op.create_table('activity_planning_sources',
        sa.Column('id',sa.Integer,primary_key=True),
        sa.Column('activity_id',sa.Integer,sa.ForeignKey('activities.id'),nullable=False),
        sa.Column('project_id',sa.Integer,sa.ForeignKey('projects.id'),nullable=False),
        sa.Column('file_id',sa.String(36),sa.ForeignKey('stored_files.id'),nullable=False),
        sa.Column('source_sha256',sa.String(64),nullable=False),
        sa.Column('sheet_index',sa.Integer,nullable=False),
        sa.Column('source_row',sa.Integer,nullable=False),
        sa.Column('mapping_id',sa.String(36),sa.ForeignKey('mapping_proposals.id'),nullable=False),
        sa.UniqueConstraint('project_id','source_sha256','sheet_index','source_row'))
    for column in ('activity_id','project_id'):
        op.create_index(f'ix_activity_planning_sources_{column}','activity_planning_sources',[column])
    op.execute('ALTER TABLE external_report_versions ADD COLUMN activity_id INTEGER REFERENCES activities(id)')


def downgrade():
    raise RuntimeError('Planning provenance is forward-only')
