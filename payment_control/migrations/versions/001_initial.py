"""Immutable imports, source operation uniqueness and audit trail."""
from alembic import op
import sqlalchemy as sa

revision = "payment_001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("payment_imports",
                    sa.Column("id", sa.Integer, primary_key=True),
                    sa.Column("fingerprint", sa.String(64), nullable=False, unique=True),
                    sa.Column("kind", sa.String(20), nullable=False),
                    sa.Column("source", sa.String(100), nullable=False),
                    sa.Column("filename", sa.String(200), nullable=False),
                    sa.Column("as_of", sa.Date, nullable=False),
                    sa.Column("status", sa.String(20), nullable=False),
                    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                              server_default=sa.text("CURRENT_TIMESTAMP")),
                    sa.Column("created_by", sa.String(64), nullable=False),
                    sa.Column("invalid", sa.Integer, nullable=False),
                    sa.Column("row_count", sa.Integer, nullable=False))
    op.create_table("payment_import_rows",
                    sa.Column("id", sa.Integer, primary_key=True),
                    sa.Column("batch_id", sa.Integer,
                              sa.ForeignKey("payment_imports.id", ondelete="RESTRICT"), nullable=False),
                    sa.Column("line", sa.Integer, nullable=False),
                    sa.Column("account_number", sa.String(64), nullable=False),
                    sa.Column("paid_at", sa.Date, nullable=True),
                    sa.Column("data", sa.JSON, nullable=False),
                    sa.Column("errors", sa.JSON, nullable=False))
    op.create_index("ix_payment_import_rows_batch_line", "payment_import_rows", ["batch_id", "line"])
    op.create_index("ix_payment_import_rows_account_number", "payment_import_rows", ["account_number"])
    op.create_table("payment_claims",
                    sa.Column("id", sa.Integer, primary_key=True),
                    sa.Column("batch_id", sa.Integer,
                              sa.ForeignKey("payment_imports.id", ondelete="RESTRICT"), nullable=False),
                    sa.Column("source", sa.String(100), nullable=False),
                    sa.Column("operation_id", sa.String(100), nullable=False),
                    sa.UniqueConstraint("source", "operation_id", name="uq_payment_source_operation"))
    op.create_index("ix_payment_claims_batch_id", "payment_claims", ["batch_id"])
    op.create_table("payment_audit",
                    sa.Column("id", sa.Integer, primary_key=True),
                    sa.Column("batch_id", sa.Integer,
                              sa.ForeignKey("payment_imports.id", ondelete="RESTRICT"), nullable=False),
                    sa.Column("action", sa.String(20), nullable=False),
                    sa.Column("actor_id", sa.String(64), nullable=False),
                    sa.Column("reason", sa.String(500), nullable=True),
                    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                              server_default=sa.text("CURRENT_TIMESTAMP")))
    op.create_index("ix_payment_audit_batch_id", "payment_audit", ["batch_id"])


def downgrade():
    for table in ("payment_audit", "payment_claims", "payment_import_rows", "payment_imports"):
        op.drop_table(table)
