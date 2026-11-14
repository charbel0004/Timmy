"""Associate stored spreadsheets with conversations and parsed source rows."""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "document_imports",
        sa.Column("file_id", sa.String(36), sa.ForeignKey("stored_files.id"), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="SET NULL")),
        sa.Column("sheets", sa.JSON(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
    )
    op.create_index("ix_document_imports_conversation_id", "document_imports", ["conversation_id"])


def downgrade():
    raise RuntimeError("Document evidence migration is forward-only")
