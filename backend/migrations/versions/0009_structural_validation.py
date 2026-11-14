"""Persist structural validation snapshots."""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "structural_validations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("actor_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.Integer, nullable=False),
        sa.Column("snapshot", sa.JSON, nullable=False),
        sa.UniqueConstraint("project_id", "fingerprint"),
    )
    op.create_index("ix_structural_validations_project_id", "structural_validations", ["project_id"])


def downgrade():
    raise RuntimeError("Validation evidence migration is forward-only")
