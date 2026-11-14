"""Add identity profile and normalized role assignments."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = depends_on = None


def upgrade():
    for name, length in (("first_name", 80), ("middle_name", 80), ("last_name", 80), ("email", 254)):
        op.add_column("users", sa.Column(name, sa.String(length)))
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.add_column("roles", sa.Column("description", sa.String(240)))
    op.create_table("user_roles",
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("role_id", sa.Integer, sa.ForeignKey("roles.id"), primary_key=True))
    op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"])
    op.create_table("role_permissions",
        sa.Column("role_id", sa.Integer, sa.ForeignKey("roles.id"), primary_key=True),
        sa.Column("permission", sa.String(80), primary_key=True))
    op.create_table("project_roles",
        sa.Column("user_id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, primary_key=True),
        sa.Column("role_id", sa.Integer, sa.ForeignKey("roles.id"), primary_key=True),
        sa.ForeignKeyConstraint(["project_id", "user_id"],
                                ["project_memberships.project_id", "project_memberships.user_id"], ondelete="CASCADE"))
    for name in ("role_id", "project_id"):
        op.create_index(f"ix_project_roles_{name}", "project_roles", [name])


def downgrade():
    for name in ("project_roles", "role_permissions", "user_roles"):
        op.drop_table(name)
    op.drop_column("roles", "description")
    op.drop_index("ix_users_email", table_name="users")
    for name in ("email", "last_name", "middle_name", "first_name"):
        op.drop_column("users", name)
