"""Record human reviews against immutable validation snapshots."""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "evidence_reviews",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("validation_id", sa.Integer, sa.ForeignKey("structural_validations.id"), nullable=False),
        sa.Column("actor_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_code", sa.Text, nullable=False),
        sa.Column("activity_code", sa.Text, nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("evidence_ref", sa.Text, nullable=False),
        sa.Column("created_at", sa.Integer, nullable=False),
    )
    op.create_index("ix_evidence_reviews_validation_id", "evidence_reviews", ["validation_id"])


def downgrade():
    raise RuntimeError("Review evidence is forward-only")
