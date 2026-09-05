"""Immutable imports, source operation uniqueness and audit trail."""
from alembic import op
import sqlalchemy as sa

# Рантайм-роль: точные права выдаются здесь, а не в provision.sql, который
# выполняется при инициализации пустой БД, когда этих таблиц ещё нет.
# Импорты и журнал неизменяемы: UPDATE нужен только статусу импорта, DELETE —
# только claims (снимаются при деактивации).
RUNTIME_ROLE = "payment_app"
RUNTIME_GRANTS = (
    "GRANT SELECT, INSERT, UPDATE ON payment_imports TO payment_app",
    "GRANT SELECT, INSERT ON payment_import_rows TO payment_app",
    "GRANT SELECT, INSERT, DELETE ON payment_claims TO payment_app",
    "GRANT SELECT, INSERT ON payment_audit TO payment_app",
    "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO payment_app",
)


def _grant_runtime_privileges():
    """Выдать права рантайм-роли, если это PostgreSQL и роль существует.

    На sqlite (тесты, CI сервиса) и на БД без провижининга роли — no-op.
    """
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    exists = bind.execute(
        sa.text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": RUNTIME_ROLE}
    ).scalar()
    if not exists:
        return
    for statement in RUNTIME_GRANTS:
        op.execute(statement)

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
    _grant_runtime_privileges()


def downgrade():
    for table in ("payment_audit", "payment_claims", "payment_import_rows", "payment_imports"):
        op.drop_table(table)
