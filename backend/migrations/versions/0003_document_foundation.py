"""Add project codes, private-file metadata and structured audit context."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("projects", sa.Column("project_code", sa.String(80)))
    op.create_index("ix_projects_project_code", "projects", ["project_code"], unique=True)
    op.create_table(
        "stored_files",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("purpose", sa.String(80), nullable=False),
        sa.Column("original_filename", sa.Text, nullable=False),
        sa.Column("relative_storage_key", sa.Text, nullable=False, unique=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=False),
        sa.Column("uploaded_at", sa.String(32), nullable=False),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id")),
        sa.Column("uploaded_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.CheckConstraint("size_bytes > 0", name="ck_stored_files_positive_size"),
        sa.CheckConstraint("length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'", name="ck_stored_files_sha256"),
    )
    for name in ("project_id", "uploaded_by"):
        op.create_index(f"ix_stored_files_{name}", "stored_files", [name])

    for name, length in (("trigger", 80), ("resource_type", 80), ("resource_id", 128), ("outcome", 40)):
        op.add_column("audit_events", sa.Column(name, sa.String(length)))
    op.execute(
        "ALTER TABLE audit_events ADD COLUMN evidence_file_id VARCHAR(36) REFERENCES stored_files(id)"
    )
    op.create_index("ix_audit_events_evidence_file_id", "audit_events", ["evidence_file_id"])


def downgrade():
    op.drop_index("ix_audit_events_evidence_file_id", table_name="audit_events")
    with op.batch_alter_table("audit_events") as batch:
        for name in ("evidence_file_id", "outcome", "resource_id", "resource_type", "trigger"):
            batch.drop_column(name)
    op.drop_table("stored_files")
    op.drop_index("ix_projects_project_code", table_name="projects")
    op.drop_column("projects", "project_code")
