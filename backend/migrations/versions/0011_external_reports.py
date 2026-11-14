"""Persist authoritative external report versions and first cutoff."""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "external_report_versions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        *(sa.Column(name, sa.Text, nullable=False) for name in (
            "activity_code", "source", "report_id", "version", "submitted_at", "local_date", "evidence_ref",
        )),
        sa.Column("validated_at", sa.Text),
        sa.Column("cutoff", sa.Text),
        sa.UniqueConstraint("project_id", "activity_code", "version"),
    )


def downgrade():
    raise RuntimeError("External report evidence is forward-only")
