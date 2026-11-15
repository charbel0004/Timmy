"""Record project-selected fixed policy family without rewriting legacy policies.

Historical project rows have no inferred policy family; a human must choose.
Do not migrate historical configurable policy JSON into authoritative fixed rules.
"""
import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = depends_on = None


def upgrade():
    op.add_column("projects", sa.Column("policy_family", sa.String(12), nullable=True))
    # No backfill: old rates and drafts are not evidence of the newly approved choice.
    # Project creation API now requires one of the two fixed families.


def downgrade():
    raise RuntimeError("Project policy family migration is forward-only; restore a verified backup")
