"""access_control: подтверждение спорного въезда жителем (§6.4, §9.4, §16.2)

Создаёт таблицу ``access_entry_confirmations`` — СОВЕЩАТЕЛЬНЫЙ ответ жителя на
спорный въезд (manual_review). Ответ фиксируется и показывается оператору, но НЕ
открывает шлагбаум и НЕ меняет ``access_decisions`` (решение остаётся за
оператором, §9.5).

Не append-only (в отличие от журналов/аудита §9.7): допускается upsert
«последнего ответа» по ``UNIQUE(decision_id, user_id)``. Поэтому прикладная роль
``access_app_rw`` получает на неё полный CRUD (если роль провизионирована).

Только PostgreSQL (как и весь домен). Полностью идемпотентна.

Revision ID: 034
Revises: 033
Create Date: 2026-06-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "034"
down_revision: Union[str, None] = "033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables(bind) -> set:
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # Домен access_control — только PostgreSQL (BIGINT IDENTITY/FK).
        return

    if "access_entry_confirmations" not in _tables(bind):
        op.create_table(
            "access_entry_confirmations",
            sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
            sa.Column(
                "decision_id",
                sa.BigInteger,
                sa.ForeignKey("access_decisions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "camera_event_id",
                sa.BigInteger,
                sa.ForeignKey("camera_events.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "user_id",
                sa.Integer,
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "apartment_id",
                sa.Integer,
                sa.ForeignKey("apartments.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("response", sa.String(8), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.CheckConstraint(
                "response IN ('confirm','deny')",
                name="ck_access_entry_confirmations_response",
            ),
            sa.UniqueConstraint(
                "decision_id",
                "user_id",
                name="uq_access_entry_confirmations_decision_user",
            ),
        )
        op.create_index(
            "ix_access_entry_confirmations_decision_id",
            "access_entry_confirmations",
            ["decision_id"],
        )
        op.create_index(
            "ix_access_entry_confirmations_camera_event_id",
            "access_entry_confirmations",
            ["camera_event_id"],
        )

    # Прикладная роль (§9.7, решение CTO #10b): таблица мутабельна (upsert) →
    # полный CRUD. Идемпотентно; пропускается, если роль не провизионирована.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'access_app_rw')
               AND to_regclass('public.access_entry_confirmations') IS NOT NULL THEN
                GRANT SELECT, INSERT, UPDATE, DELETE
                    ON access_entry_confirmations TO access_app_rw;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'access_app_rw')
               AND to_regclass('public.access_entry_confirmations') IS NOT NULL THEN
                REVOKE ALL ON access_entry_confirmations FROM access_app_rw;
            END IF;
        END
        $$;
        """
    )
    op.execute("DROP TABLE IF EXISTS access_entry_confirmations")
