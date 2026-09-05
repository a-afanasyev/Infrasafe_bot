"""Модуль «Лифты» (Ф1): схема — три доменные таблицы, singleton-конфиг, колонки requests.

1. ``elevators`` — реестр лифтов: идентификация ``(building_id, entrance_number,
   elevator_number)``, паспорт, текущий статус (NULL до ввода в эксплуатацию),
   договор обслуживания и освидетельствование (поля), ступени напоминаний,
   публичный код, архивация. Уникальность места лифта — частичный индекс
   ``WHERE archived_at IS NULL`` (архив не мешает завести лифт на его место).
2. ``elevator_status_events`` — append-only журнал событий. ``request_number``
   БЕЗ FK: журнал переживает удаление заявки (образец material_issues).
3. ``elevator_maintenance_occurrences`` — плановые ТО / освидетельствования;
   среди неотменённых не более одной записи на ``(elevator_id, kind, due_on)``.
   Обе дочерние таблицы — FK на лифт ON DELETE RESTRICT: лифт архивируется
   (``archived_at``), жёсткое удаление при наличии истории БД запрещает.
4. ``elevators_config`` — singleton id=1, клон auto_manager_config (0005);
   строка-seed не создаётся, дефолты несёт сервисный слой.
5. ``requests.elevator_id`` (FK SET NULL, индекс) + ``requests.elevator_operational``
   — привязка заявки к лифту и отметка «лифт работает?» со слов заявителя.
   CHECK на категорию не навешивается.

Пользовательского поведения в этой фазе нет. Идемпотентность управляется
alembic-версией; отдельных guard'ов не требуется.

Revision ID: 016
Revises: 015
Create Date: 2026-09-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Канон-наборы дублируют константы models/elevator.py (миграция не импортирует
# модели по правилам alembic); паритет закреплён test_elevator_models.py.
STATUSES = ("working", "not_working", "under_repair", "maintenance")
EVENT_KINDS = (
    "status_changed",
    "commissioned",
    "archived",
    "contract_changed",
    "cert_changed",
    "passport_changed",
)
EVENT_SOURCES = ("manual", "request_hint", "infrasafe", "system")
OCCURRENCE_KINDS = ("maintenance", "certification")
OCCURRENCE_STATES = ("planned", "done", "cancelled")


def _in_clause(column: str, values: tuple) -> str:
    return "{} IN ({})".format(column, ", ".join(f"'{v}'" for v in values))


def _create_elevators() -> None:
    op.create_table(
        "elevators",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("building_id", sa.Integer(), nullable=False),
        sa.Column("entrance_number", sa.Integer(), nullable=False),
        sa.Column("elevator_number", sa.Integer(), nullable=False),
        sa.Column("passport_number", sa.String(length=100), nullable=False),
        sa.Column("manufacturer", sa.String(length=200), nullable=False),
        sa.Column("serial_number", sa.String(length=100), nullable=False),
        sa.Column("factory_number", sa.String(length=100), nullable=True),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("production_year", sa.Integer(), nullable=True),
        sa.Column("capacity_kg", sa.Integer(), nullable=True),
        sa.Column("floors_served", sa.String(length=100), nullable=True),
        sa.Column("commissioned_at", sa.Date(), nullable=True),
        sa.Column("current_status", sa.String(length=20), nullable=True),
        sa.Column("status_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("downtime_reason", sa.Text(), nullable=True),
        sa.Column("spare_part_expected_on", sa.Date(), nullable=True),
        sa.Column(
            "publish_downtime_details",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("service_org_name", sa.String(length=200), nullable=True),
        sa.Column("service_org_phone", sa.String(length=50), nullable=True),
        sa.Column("contract_number", sa.String(length=100), nullable=True),
        sa.Column("contract_until", sa.Date(), nullable=True),
        sa.Column("cert_number", sa.String(length=100), nullable=True),
        sa.Column("cert_valid_until", sa.Date(), nullable=True),
        sa.Column("cert_act_url", sa.String(length=500), nullable=True),
        sa.Column(
            "contract_reminder_stage",
            sa.SmallInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "cert_reminder_stage",
            sa.SmallInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("downtime_reminded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("public_code", sa.String(length=32), nullable=False),
        sa.Column("is_public", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "is_commissioned", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint(
            "current_status IS NULL OR " + _in_clause("current_status", STATUSES),
            name="ck_elevators_current_status",
        ),
        sa.ForeignKeyConstraint(["building_id"], ["buildings.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_code"),
    )
    op.create_index(
        "uq_elevators_building_entrance_number_active",
        "elevators",
        ["building_id", "entrance_number", "elevator_number"],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
        sqlite_where=sa.text("archived_at IS NULL"),
    )


def _create_status_events() -> None:
    op.create_table(
        "elevator_status_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("elevator_id", sa.Integer(), nullable=False),
        sa.Column("event_kind", sa.String(length=30), nullable=False),
        sa.Column("old_status", sa.String(length=20), nullable=True),
        sa.Column("new_status", sa.String(length=20), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("request_number", sa.String(length=15), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.CheckConstraint(
            _in_clause("event_kind", EVENT_KINDS), name="ck_elevator_status_events_event_kind"
        ),
        sa.CheckConstraint(
            _in_clause("source", EVENT_SOURCES), name="ck_elevator_status_events_source"
        ),
        sa.ForeignKeyConstraint(["elevator_id"], ["elevators.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_elevator_status_events_elevator_id"),
        "elevator_status_events",
        ["elevator_id"],
        unique=False,
    )


def _create_maintenance_occurrences() -> None:
    op.create_table(
        "elevator_maintenance_occurrences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("elevator_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("state", sa.String(length=20), server_default="planned", nullable=False),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("done_by_user_id", sa.Integer(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("request_number", sa.String(length=15), nullable=True),
        sa.Column(
            "reminder_stage", sa.SmallInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("overdue_reminded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            _in_clause("kind", OCCURRENCE_KINDS),
            name="ck_elevator_maintenance_occurrences_kind",
        ),
        sa.CheckConstraint(
            _in_clause("state", OCCURRENCE_STATES),
            name="ck_elevator_maintenance_occurrences_state",
        ),
        sa.ForeignKeyConstraint(["elevator_id"], ["elevators.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["done_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_elevator_maintenance_occurrences_elevator_id"),
        "elevator_maintenance_occurrences",
        ["elevator_id"],
        unique=False,
    )
    op.create_index(
        "uq_elevator_maintenance_occurrences_active",
        "elevator_maintenance_occurrences",
        ["elevator_id", "kind", "due_on"],
        unique=True,
        postgresql_where=sa.text("state <> 'cancelled'"),
        sqlite_where=sa.text("state <> 'cancelled'"),
    )


def _create_elevators_config() -> None:
    op.create_table(
        "elevators_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "data",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_elevators_config_updated_by"),
        "elevators_config",
        ["updated_by"],
        unique=False,
    )


def _add_request_columns() -> None:
    op.add_column(
        "requests",
        sa.Column(
            "elevator_id",
            sa.Integer(),
            sa.ForeignKey(
                "elevators.id",
                ondelete="SET NULL",
                name="fk_requests_elevator_id_elevators",
            ),
            nullable=True,
        ),
    )
    op.add_column("requests", sa.Column("elevator_operational", sa.Boolean(), nullable=True))
    op.create_index(op.f("ix_requests_elevator_id"), "requests", ["elevator_id"], unique=False)


def upgrade() -> None:
    _create_elevators()
    _create_status_events()
    _create_maintenance_occurrences()
    _create_elevators_config()
    _add_request_columns()


def downgrade() -> None:
    op.drop_index(op.f("ix_requests_elevator_id"), table_name="requests")
    op.drop_column("requests", "elevator_operational")
    op.drop_column("requests", "elevator_id")

    op.drop_index(op.f("ix_elevators_config_updated_by"), table_name="elevators_config")
    op.drop_table("elevators_config")

    op.drop_index(
        "uq_elevator_maintenance_occurrences_active",
        table_name="elevator_maintenance_occurrences",
        postgresql_where=sa.text("state <> 'cancelled'"),
        sqlite_where=sa.text("state <> 'cancelled'"),
    )
    op.drop_index(
        op.f("ix_elevator_maintenance_occurrences_elevator_id"),
        table_name="elevator_maintenance_occurrences",
    )
    op.drop_table("elevator_maintenance_occurrences")

    op.drop_index(
        op.f("ix_elevator_status_events_elevator_id"), table_name="elevator_status_events"
    )
    op.drop_table("elevator_status_events")

    op.drop_index(
        "uq_elevators_building_entrance_number_active",
        table_name="elevators",
        postgresql_where=sa.text("archived_at IS NULL"),
        sqlite_where=sa.text("archived_at IS NULL"),
    )
    op.drop_table("elevators")
