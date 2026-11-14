"""Persist owner-scoped chat turns."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "conversations", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
    )
    op.create_index("ix_conversations_owner_id", "conversations", ["owner_id"])
    op.create_table(
        "chat_turns", sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("reply", sa.Text, nullable=False),
        sa.Column("created_at", sa.Integer, nullable=False),
        sa.UniqueConstraint("conversation_id", "request_id"),
    )
    op.create_index("ix_chat_turns_conversation_id", "chat_turns", ["conversation_id"])


def downgrade():
    op.drop_table("chat_turns")
    op.drop_table("conversations")
