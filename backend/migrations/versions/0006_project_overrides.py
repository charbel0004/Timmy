"""Store explicit per-member project permissions."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "project_permission_overrides",
        sa.Column("project_id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, primary_key=True),
        sa.Column("permissions", sa.JSON, nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id", "user_id"], ["project_memberships.project_id", "project_memberships.user_id"],
            ondelete="CASCADE",
        ),
    )


def downgrade():
    op.drop_table("project_permission_overrides")
