"""Stop invented activity identity; preserve historical rows on review hold."""
import sqlalchemy as sa
from alembic import op

revision='0016'
down_revision='0015'
branch_labels=depends_on=None


def upgrade():
    collisions=op.get_bind().execute(sa.text('SELECT activity_code FROM activities WHERE activity_code IS NOT NULL GROUP BY activity_code HAVING count(*) > 1')).first()
    if collisions:
        raise RuntimeError('Global activity-code collisions require human reconciliation before migration; no codes were rewritten')
    op.add_column('activities',sa.Column('code_authority',sa.String(30),nullable=False,server_default='legacy_review_required'))
    op.add_column('activities',sa.Column('planning_contract_version',sa.String(80)))
    op.create_index('uq_activities_global_code','activities',['activity_code'],unique=True)
    op.create_table('planning_code_contracts',
        sa.Column('project_id',sa.Integer,sa.ForeignKey('projects.id'),primary_key=True),
        sa.Column('version',sa.String(80),nullable=False),
        sa.Column('code_pattern',sa.String(128),nullable=False),
        sa.Column('source_ref',sa.Text,nullable=False),
        sa.Column('approved_by',sa.Integer,sa.ForeignKey('users.id'),nullable=False),
        sa.Column('approved_at',sa.Integer,nullable=False))


def downgrade():
    raise RuntimeError('Authority migration is forward-only; recover from a verified backup')
