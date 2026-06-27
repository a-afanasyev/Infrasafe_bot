"""access_control Ф2 (доревью): недостающие FK-индексы + CHECK на статус контроллера

Код-ревью Фазы 2 (принято CTO): добавляет индексы на «горячие» FK событий/решений,
не покрытые миграциями 027/028, и канонический CheckConstraint на
``edge_controllers.status`` (active|inactive|decommissioned), не заданный в 025.

Индексы (HIGH — частые join/lookup в Decision Engine и журнале проездов):
* ix_access_events_decision_id              на access_events(decision_id)
* ix_access_events_camera_event_id          на access_events(camera_event_id)
* ix_access_decisions_matched_vehicle_id    на access_decisions(matched_vehicle_id)
* ix_access_decisions_matched_pass_id       на access_decisions(matched_pass_id)
* ix_access_decisions_supersedes_decision_id на access_decisions(supersedes_decision_id)
* ix_camera_events_camera_id                на camera_events(camera_id)

Имена индексов совпадают с дефолтным неймингом ORM (``index=True`` →
``ix_<table>_<column>``), поэтому autogenerate не показывает ложный drift.

Идемпотентно (контракт миграций 025–028): индекс создаётся только если его ещё
нет (guard по inspector.get_indexes); CHECK — только если constraint отсутствует
(guard по inspector.get_check_constraints). downgrade дропает добавленное.
Только PostgreSQL (домен гоняется на pg; CI = create_all + upgrade head).

Revision ID: 029
Revises: 028
Create Date: 2026-06-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "029"
down_revision: Union[str, None] = "028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (index_name, table_name, [columns]) — недостающие FK-индексы.
_INDEXES = (
    ("ix_access_events_decision_id", "access_events", ["decision_id"]),
    ("ix_access_events_camera_event_id", "access_events", ["camera_event_id"]),
    (
        "ix_access_decisions_matched_vehicle_id",
        "access_decisions",
        ["matched_vehicle_id"],
    ),
    (
        "ix_access_decisions_matched_pass_id",
        "access_decisions",
        ["matched_pass_id"],
    ),
    (
        "ix_access_decisions_supersedes_decision_id",
        "access_decisions",
        ["supersedes_decision_id"],
    ),
    ("ix_camera_events_camera_id", "camera_events", ["camera_id"]),
)

_STATUS_CHECK_NAME = "ck_edge_controllers_status"
_EDGE_STATUSES = "('active', 'inactive', 'decommissioned')"


def _index_names(inspector, table: str) -> set:
    return {ix["name"] for ix in inspector.get_indexes(table)}


def _check_names(inspector, table: str) -> set:
    return {ck["name"] for ck in inspector.get_check_constraints(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    for name, table, columns in _INDEXES:
        if table not in tables:
            continue
        if name not in _index_names(inspector, table):
            op.create_index(name, table, columns)

    if "edge_controllers" in tables:
        if _STATUS_CHECK_NAME not in _check_names(inspector, "edge_controllers"):
            op.create_check_constraint(
                _STATUS_CHECK_NAME,
                "edge_controllers",
                f"status IN {_EDGE_STATUSES}",
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "edge_controllers" in tables:
        if _STATUS_CHECK_NAME in _check_names(inspector, "edge_controllers"):
            op.drop_constraint(
                _STATUS_CHECK_NAME, "edge_controllers", type_="check"
            )

    for name, table, _columns in _INDEXES:
        if table not in tables:
            continue
        if name in _index_names(inspector, table):
            op.drop_index(name, table_name=table)
