"""Add immutable per-run ordered step receipts; preserve prior workflow history."""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "workflow_step_receipts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("workflow_runs.id"), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("step_id", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("attempted", sa.Boolean(), nullable=False),
        sa.Column("executed", sa.Boolean(), nullable=False),
        sa.Column("blocked_by", sa.String(80)),
        sa.Column("issue_codes", sa.JSON(), nullable=False),
        sa.Column("recorded_at", sa.Integer(), nullable=False),
        sa.UniqueConstraint("run_id", "step_index"),
        sa.CheckConstraint("step_index >= 0", name="ck_workflow_step_index"),
        sa.CheckConstraint("status IN ('completed','needs_review','blocked','failed')",
                           name="ck_workflow_step_status"),
    )
    op.create_index("ix_workflow_step_receipts_run_id",
                    "workflow_step_receipts", ["run_id"])


def downgrade():
    raise RuntimeError("Workflow receipt journal is forward-only; use a verified backup")
