"""access_control Ф2 (4/4): команды + аудит + append-only enforcement

Создаёт 3 пилотные таблицы (§9.2, §9.5, §9.7): barrier_commands, manual_openings,
access_audit_logs. Завершает домен пилота (18 таблиц).

Ключевые инварианты:
* barrier_commands: PK command_id (UUID); UNIQUE(decision_id) WHERE decision_id
  IS NOT NULL (§10.1, идемпотентная команда на решение).

Append-only enforcement (§9.7, решение CTO #10a): BEFORE UPDATE OR DELETE
PL/pgSQL триггер с RAISE EXCEPTION на 4 таблицах — access_events,
access_decisions, manual_openings, access_audit_logs. Гарантирует §15.12 при
ЛЮБОЙ роли, не только UI-запрет.

TODO (решение CTO #10b, devops/Ф7): провизионировать ОТДЕЛЬНУЮ прикладную
DB-роль с грантами только INSERT/SELECT на эти 4 таблицы (REVOKE UPDATE/DELETE).
Это инфраструктурная задача (роли/гранты вне миграции схемы); триггер выше
обеспечивает enforcement независимо от роли уже сейчас.

Идемпотентно (guard по inspector; CREATE OR REPLACE FUNCTION + DROP/CREATE
TRIGGER). Только PostgreSQL.

Revision ID: 028
Revises: 027
Create Date: 2026-06-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "028"
down_revision: Union[str, None] = "027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_COMMAND_STATUS = "('pending', 'leased', 'acked', 'dead')"
_COMMAND_TYPE = "('open_barrier')"

# 4 append-only таблицы (§9.7). manual_openings/access_audit_logs создаются ниже,
# access_events/access_decisions — в 027.
_APPEND_ONLY_TABLES = (
    "access_events",
    "access_decisions",
    "manual_openings",
    "access_audit_logs",
)

_APPEND_ONLY_FN = "access_control_append_only_guard"


def _existing(bind) -> set:
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    tables = _existing(bind)

    if "barrier_commands" not in tables:
        op.create_table(
            "barrier_commands",
            sa.Column(
                "command_id", postgresql.UUID(as_uuid=True), primary_key=True
            ),
            sa.Column(
                "decision_id",
                sa.BigInteger,
                sa.ForeignKey("access_decisions.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "controller_id",
                sa.BigInteger,
                sa.ForeignKey("edge_controllers.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "barrier_id",
                sa.BigInteger,
                sa.ForeignKey("access_barriers.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "command_type",
                sa.String(32),
                nullable=False,
                server_default="open_barrier",
            ),
            sa.Column(
                "status", sa.String(16), nullable=False, server_default="pending"
            ),
            sa.Column("lease_token", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
            sa.Column("max_attempts", sa.Integer, nullable=False, server_default="5"),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                f"status IN {_COMMAND_STATUS}", name="ck_barrier_commands_status"
            ),
            sa.CheckConstraint(
                f"command_type IN {_COMMAND_TYPE}",
                name="ck_barrier_commands_command_type",
            ),
        )
        op.create_index(
            "ix_barrier_commands_controller_id", "barrier_commands", ["controller_id"]
        )
        op.create_index(
            "ix_barrier_commands_barrier_id", "barrier_commands", ["barrier_id"]
        )
        op.create_index(
            "ix_barrier_commands_controller_status",
            "barrier_commands",
            ["controller_id", "status"],
        )
        # Идемпотентность §10.1: одна команда на решение (ручные — decision_id NULL).
        op.create_index(
            "uq_barrier_commands_decision",
            "barrier_commands",
            ["decision_id"],
            unique=True,
            postgresql_where=sa.text("decision_id IS NOT NULL"),
        )

    if "manual_openings" not in tables:
        op.create_table(
            "manual_openings",
            sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
            sa.Column(
                "barrier_id",
                sa.BigInteger,
                sa.ForeignKey("access_barriers.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "command_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("barrier_commands.command_id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "decision_id",
                sa.BigInteger,
                sa.ForeignKey("access_decisions.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "operator_user_id",
                sa.Integer,
                sa.ForeignKey("users.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("reason", sa.Text, nullable=False),
            sa.Column(
                "captured_event_id",
                sa.BigInteger,
                sa.ForeignKey("camera_events.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("prev_hash", sa.String(64), nullable=True),
            sa.Column("row_hash", sa.String(64), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )
        op.create_index(
            "ix_manual_openings_barrier_id", "manual_openings", ["barrier_id"]
        )
        op.create_index(
            "ix_manual_openings_operator_user_id",
            "manual_openings",
            ["operator_user_id"],
        )

    if "access_audit_logs" not in tables:
        op.create_table(
            "access_audit_logs",
            sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
            sa.Column(
                "actor_user_id",
                sa.Integer,
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("action", sa.String(128), nullable=False),
            sa.Column("entity_type", sa.String(64), nullable=True),
            sa.Column("entity_id", sa.String(64), nullable=True),
            sa.Column("details", postgresql.JSONB, nullable=True),
            sa.Column("ip_address", sa.String(64), nullable=True),
            sa.Column("prev_hash", sa.String(64), nullable=True),
            sa.Column("row_hash", sa.String(64), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )
        op.create_index(
            "ix_access_audit_logs_actor_user_id",
            "access_audit_logs",
            ["actor_user_id"],
        )

    # Append-only enforcement (§9.7, решение CTO #10a). Только PostgreSQL —
    # PL/pgSQL. На прочих диалектах пропускаем (домен и так гоняется на pg).
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_APPEND_ONLY_FN}() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'append-only violation: % on % is forbidden (TZ §9.7)',
                TG_OP, TG_TABLE_NAME
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in _APPEND_ONLY_TABLES:
        trigger = f"trg_append_only_{table}"
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
        op.execute(
            f"""
            CREATE TRIGGER {trigger}
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION {_APPEND_ONLY_FN}();
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in _APPEND_ONLY_TABLES:
            op.execute(f"DROP TRIGGER IF EXISTS trg_append_only_{table} ON {table}")
        op.execute(f"DROP FUNCTION IF EXISTS {_APPEND_ONLY_FN}()")

    for table in (
        "access_audit_logs",
        "manual_openings",
        "barrier_commands",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
