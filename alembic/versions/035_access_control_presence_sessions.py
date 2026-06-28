"""access_control: presence-сессии выезда + тумблер лимита мест (§8.3, §10.3)

Добавляет функционал ВЫЕЗДА и учёта присутствия:

* ``vehicle_presence_sessions`` — сессия присутствия авто в зоне. Въезд открывает
  (``status='open'``), выезд/ручное освобождение закрывает (``status='closed'``).
  «Занятость» места assigned-зоны = число открытых сессий квартиры в зоне.
  Мутабельна (open→closed UPDATE) — НЕ append-only (без триггера §9.7, в отличие
  от журналов). Частичный ``UNIQUE(vehicle_id, zone_id) WHERE status='open'`` —
  ровно одна открытая сессия авто в зоне.
* ``parking_spot_assignments.enforce_limit BOOLEAN NOT NULL DEFAULT TRUE`` —
  отключаемый тумблер лимита мест. TRUE — авто квартиры сверх числа её активных
  мест не пускается (manual_review ``parking_spot_occupied``); FALSE — житель/
  менеджер временно снял лимит.

Прикладная роль (§9.7, решение CTO #10b): presence МУТАБЕЛЬНА (close=UPDATE) →
полный CRUD для ``access_app_rw`` (если роль провизионирована).

Только PostgreSQL (как и весь домен). Полностью идемпотентна.

Revision ID: 035
Revises: 034
Create Date: 2026-06-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "035"
down_revision: Union[str, None] = "034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Полный текущий перечень reason'ов решения (DATA_MODEL_PILOT «Enum»). Колоночный
# CHECK ``ck_access_decisions_reason`` создан в 027 и не пересоздавался при добавлении
# зоно-типных reason'ов (033) — assigned_spot_allowed/… фактически не проходили запись
# через ingestion. Здесь пересоздаём с полным списком + новым parking_spot_occupied.
_DECISION_REASONS = (
    "permanent_vehicle_allowed",
    "temporary_pass_allowed",
    "assigned_spot_allowed",
    "spot_not_assigned",
    "spot_rental_expired",
    "shared_access_allowed",
    "per_apartment_limit_exceeded",
    "parking_spot_occupied",
    "vehicle_not_found",
    "vehicle_blocked",
    "zone_not_allowed",
    "pass_expired",
    "pass_already_used",
    "low_confidence",
    "possible_plate_clone",
    "anti_passback_violation",
    "manual_review_required",
)


def _tables(bind) -> set:
    return set(sa.inspect(bind).get_table_names())


def _columns(bind, table: str) -> set:
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # Домен access_control — только PostgreSQL (BIGINT IDENTITY/FK).
        return

    # 0) Пересоздать CHECK reason'а решения с полным актуальным списком
    #    (включая parking_spot_occupied и зоно-типные reason'ы из 033). Идемпотентно.
    if "access_decisions" in _tables(bind):
        reasons = ", ".join(f"'{r}'" for r in _DECISION_REASONS)
        op.execute(
            "ALTER TABLE access_decisions "
            "DROP CONSTRAINT IF EXISTS ck_access_decisions_reason"
        )
        op.execute(
            "ALTER TABLE access_decisions ADD CONSTRAINT ck_access_decisions_reason "
            f"CHECK (reason IS NULL OR reason IN ({reasons}))"
        )

    # 1) Тумблер лимита мест на закреплении (идемпотентно).
    if "parking_spot_assignments" in _tables(bind):
        if "enforce_limit" not in _columns(bind, "parking_spot_assignments"):
            op.add_column(
                "parking_spot_assignments",
                sa.Column(
                    "enforce_limit",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("true"),
                ),
            )

    # 2) Таблица presence-сессий (идемпотентно).
    if "vehicle_presence_sessions" not in _tables(bind):
        op.create_table(
            "vehicle_presence_sessions",
            sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
            sa.Column(
                "vehicle_id",
                sa.BigInteger,
                sa.ForeignKey("vehicles.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "apartment_id",
                sa.Integer,
                sa.ForeignKey("apartments.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "zone_id",
                sa.BigInteger,
                sa.ForeignKey("parking_zones.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("entered_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("exited_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "status",
                sa.String(8),
                nullable=False,
                server_default="open",
            ),
            sa.Column(
                "entry_camera_event_id",
                sa.BigInteger,
                sa.ForeignKey("camera_events.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "exit_camera_event_id",
                sa.BigInteger,
                sa.ForeignKey("camera_events.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "closed_by_user_id",
                sa.Integer,
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("close_reason", sa.String(32), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.CheckConstraint(
                "status IN ('open','closed')",
                name="ck_vehicle_presence_sessions_status",
            ),
        )
        op.create_index(
            "ix_vehicle_presence_sessions_vehicle_id",
            "vehicle_presence_sessions",
            ["vehicle_id"],
        )
        op.create_index(
            "ix_vehicle_presence_sessions_apartment_id",
            "vehicle_presence_sessions",
            ["apartment_id"],
        )
        op.create_index(
            "ix_vehicle_presence_sessions_zone_id",
            "vehicle_presence_sessions",
            ["zone_id"],
        )
        op.create_index(
            "ix_vehicle_presence_sessions_zone_status",
            "vehicle_presence_sessions",
            ["zone_id", "status"],
        )
        op.create_index(
            "ix_vehicle_presence_sessions_apartment_zone_status",
            "vehicle_presence_sessions",
            ["apartment_id", "zone_id", "status"],
        )
        # Ровно одна открытая сессия авто в зоне (§10.3).
        op.create_index(
            "uq_vehicle_presence_open_vehicle_zone",
            "vehicle_presence_sessions",
            ["vehicle_id", "zone_id"],
            unique=True,
            postgresql_where=sa.text("status = 'open'"),
        )

    # Прикладная роль: presence мутабельна (close=UPDATE) → полный CRUD.
    # Идемпотентно; пропускается, если роль не провизионирована.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'access_app_rw')
               AND to_regclass('public.vehicle_presence_sessions') IS NOT NULL THEN
                GRANT SELECT, INSERT, UPDATE, DELETE
                    ON vehicle_presence_sessions TO access_app_rw;
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
               AND to_regclass('public.vehicle_presence_sessions') IS NOT NULL THEN
                REVOKE ALL ON vehicle_presence_sessions FROM access_app_rw;
            END IF;
        END
        $$;
        """
    )
    op.execute("DROP TABLE IF EXISTS vehicle_presence_sessions")
    if "enforce_limit" in _columns(bind, "parking_spot_assignments"):
        op.drop_column("parking_spot_assignments", "enforce_limit")
    # Вернуть CHECK reason'а к списку миграции 027 (без зоно-типных/presence reason'ов).
    if "access_decisions" in _tables(bind):
        legacy = (
            "permanent_vehicle_allowed",
            "temporary_pass_allowed",
            "vehicle_not_found",
            "vehicle_blocked",
            "zone_not_allowed",
            "pass_expired",
            "pass_already_used",
            "low_confidence",
            "possible_plate_clone",
            "anti_passback_violation",
            "manual_review_required",
        )
        reasons = ", ".join(f"'{r}'" for r in legacy)
        op.execute(
            "ALTER TABLE access_decisions "
            "DROP CONSTRAINT IF EXISTS ck_access_decisions_reason"
        )
        op.execute(
            "ALTER TABLE access_decisions ADD CONSTRAINT ck_access_decisions_reason "
            f"CHECK (reason IS NULL OR reason IN ({reasons}))"
        )
