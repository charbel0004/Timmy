"""Persist scoped workflow receipts and chat request context."""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = depends_on = None


def upgrade():
    op.add_column("chat_turns", sa.Column("context", sa.JSON))
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("actor_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("request_key", sa.String(160), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("workflow_id", sa.String(80), nullable=False),
        sa.Column("knowledge_version", sa.String(40), nullable=False),
        sa.Column("created_at", sa.Integer, nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("snapshot", sa.JSON, nullable=False),
        sa.UniqueConstraint("actor_id", "request_key"),
    )
    op.create_index("ix_workflow_runs_actor_id", "workflow_runs", ["actor_id"])
    op.create_index("ix_workflow_runs_project_id", "workflow_runs", ["project_id"])


def downgrade():
    raise RuntimeError("Workflow receipts are forward-only")
