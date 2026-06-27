"""Ф2: регистрация пилотных моделей access_control на общем Base.metadata.

Проверяет, что импорт доменного пакета регистрирует ровно 18 пилотных таблиц
(§5.2, DATA_MODEL_PILOT «Scope таблиц») на том же declarative ``Base``, что
использует alembic env.py и тестовый ``create_all``. Таблица выезда
``vehicle_presence_sessions`` в пилот НЕ входит (§10.3, §14.2) и не должна
присутствовать в metadata.

Чисто метаданные — без подключения к БД.
"""
from __future__ import annotations

# Регистрируем родительские таблицы (users/yards/apartments/...) и пилотные.
import uk_management_bot.database.models  # noqa: F401  # parent tables
import access_control.domain  # noqa: F401  # pilot tables register on Base
from uk_management_bot.database.session import Base


# 18 пилотных таблиц (DATA_MODEL_PILOT «Scope таблиц»).
PILOT_TABLES = {
    "parking_zones",
    "parking_zone_yards",
    "access_gates",
    "access_cameras",
    "access_barriers",
    "edge_controllers",
    "vehicles",
    "vehicle_apartments",
    "access_rules",
    "access_passes",
    "resident_access_requests",
    "camera_events",
    "access_decisions",
    "barrier_commands",
    "access_events",
    "manual_openings",
    "access_audit_logs",
    "controller_sync_events",
}


def test_all_pilot_tables_registered() -> None:
    """Все 18 пилотных таблиц присутствуют в Base.metadata после импорта."""
    tables = set(Base.metadata.tables.keys())
    missing = PILOT_TABLES - tables
    assert not missing, f"не зарегистрированы пилотные таблицы: {sorted(missing)}"


def test_presence_sessions_not_in_pilot() -> None:
    """vehicle_presence_sessions вне пилота (§10.3) — не должно быть в metadata."""
    assert "vehicle_presence_sessions" not in Base.metadata.tables


def test_camera_events_idempotency_unique() -> None:
    """camera_events несёт UNIQUE(controller_id, event_id) — канонический ключ §10.1."""
    table = Base.metadata.tables["camera_events"]
    unique_cols = {
        tuple(c.name for c in uc.columns)
        for uc in table.constraints
        if uc.__class__.__name__ == "UniqueConstraint"
    }
    assert ("controller_id", "event_id") in unique_cols


def test_access_events_idempotency_unique() -> None:
    """access_events несёт UNIQUE(controller_id, event_id) — один проезд на event §10.1."""
    table = Base.metadata.tables["access_events"]
    unique_cols = {
        tuple(c.name for c in uc.columns)
        for uc in table.constraints
        if uc.__class__.__name__ == "UniqueConstraint"
    }
    assert ("controller_id", "event_id") in unique_cols


def test_controller_sync_events_idempotency_unique() -> None:
    """controller_sync_events несёт UNIQUE(controller_id, event_id) (§8.4)."""
    table = Base.metadata.tables["controller_sync_events"]
    unique_cols = {
        tuple(c.name for c in uc.columns)
        for uc in table.constraints
        if uc.__class__.__name__ == "UniqueConstraint"
    }
    assert ("controller_id", "event_id") in unique_cols


def test_dedup_window_index_present() -> None:
    """Окно дедупа: INDEX(gate_id, direction, plate_number_normalized, captured_at)."""
    table = Base.metadata.tables["camera_events"]
    index_cols = {tuple(c.name for c in ix.columns) for ix in table.indexes}
    assert ("gate_id", "direction", "plate_number_normalized", "captured_at") in index_cols


def test_append_only_tables_have_hash_chain_columns() -> None:
    """4 append-only таблицы (§9.7) несут колонки hash-chain prev_hash/row_hash."""
    for name in ("access_events", "access_decisions", "manual_openings", "access_audit_logs"):
        cols = set(Base.metadata.tables[name].columns.keys())
        assert {"prev_hash", "row_hash"} <= cols, f"{name} без hash-chain колонок"


def test_barrier_commands_uuid_pk() -> None:
    """barrier_commands.command_id — PK типа UUID (§9.2)."""
    table = Base.metadata.tables["barrier_commands"]
    pk_cols = [c.name for c in table.primary_key.columns]
    assert pk_cols == ["command_id"]


# Недостающие FK-индексы доревью Фазы 2 (миграция 029) — ORM-паритет.
# (index_name, table, column): имена совпадают с дефолтным ix_<table>_<col>,
# чтобы autogenerate не показывал ложный drift.
_REVIEW_FK_INDEXES = (
    ("ix_access_events_decision_id", "access_events", "decision_id"),
    ("ix_access_events_camera_event_id", "access_events", "camera_event_id"),
    (
        "ix_access_decisions_matched_vehicle_id",
        "access_decisions",
        "matched_vehicle_id",
    ),
    ("ix_access_decisions_matched_pass_id", "access_decisions", "matched_pass_id"),
    (
        "ix_access_decisions_supersedes_decision_id",
        "access_decisions",
        "supersedes_decision_id",
    ),
    ("ix_camera_events_camera_id", "camera_events", "camera_id"),
)


def test_review_fk_indexes_present_in_metadata() -> None:
    """6 FK-индексов доревью (миграция 029) объявлены в ORM с ожидаемым именем."""
    for index_name, table_name, column in _REVIEW_FK_INDEXES:
        table = Base.metadata.tables[table_name]
        by_name = {ix.name: ix for ix in table.indexes}
        assert index_name in by_name, (
            f"индекс {index_name} не объявлен на {table_name} "
            f"(ожидался index=True на {column})"
        )
        cols = [c.name for c in by_name[index_name].columns]
        assert cols == [column], f"{index_name} покрывает {cols}, ожидалось [{column}]"


def test_edge_controllers_status_check_in_metadata() -> None:
    """edge_controllers несёт CheckConstraint ck_edge_controllers_status (миграция 029)."""
    table = Base.metadata.tables["edge_controllers"]
    check_names = {
        c.name
        for c in table.constraints
        if c.__class__.__name__ == "CheckConstraint"
    }
    assert "ck_edge_controllers_status" in check_names
