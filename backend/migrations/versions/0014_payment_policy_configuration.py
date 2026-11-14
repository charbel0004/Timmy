"""Add versioned payment configuration without changing legacy policy references."""
import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = depends_on = None


def upgrade():
    op.add_column("payment_policies", sa.Column("configuration", sa.JSON))
    op.add_column("payment_policies", sa.Column("status", sa.String(16), nullable=False, server_default="draft"))
    op.execute("ALTER TABLE payment_policies ADD COLUMN created_by INTEGER REFERENCES users(id)")
    op.add_column("payment_policies", sa.Column("created_at", sa.Integer))
    op.execute("ALTER TABLE payment_policies ADD COLUMN activated_by INTEGER REFERENCES users(id)")
    op.add_column("payment_policies", sa.Column("activated_at", sa.Integer))


def downgrade():
    raise RuntimeError("Policy authorization history is forward-only")
