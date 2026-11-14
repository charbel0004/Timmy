"""Workspace administration and onboarding."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = depends_on = None


def upgrade():
    op.add_column("users", sa.Column("must_change_password", sa.Boolean, nullable=False, server_default="0"))
    op.add_column("users", sa.Column("activation_hash", sa.String(64)))
    op.add_column("users", sa.Column("activation_expires", sa.Integer))
    op.create_index("ix_users_activation_hash", "users", ["activation_hash"], unique=True)
    op.execute(
        "ALTER TABLE projects ADD COLUMN status VARCHAR(12) NOT NULL DEFAULT 'active' "
        "CONSTRAINT ck_project_status CHECK (status IN ('draft','active','completed','archived'))"
    )
    op.add_column("projects", sa.Column("archived_from", sa.String(12)))
    op.add_column("conversations", sa.Column("title", sa.String(120)))


def downgrade():
    op.drop_column("conversations", "title")
    op.drop_column("projects", "archived_from")
    op.drop_column("projects", "status")
    op.drop_index("ix_users_activation_hash", table_name="users")
    for name in ("activation_expires", "activation_hash", "must_change_password"):
        op.drop_column("users", name)
