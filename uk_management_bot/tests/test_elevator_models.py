"""Схема модуля «Лифты» (Ф1, T1): модели строятся в Base.metadata как в спеке.

Только интроспекция SQLAlchemy-метадаты, БД не нужна. Проверяем канон-константы,
набор/nullable колонок, частичные уникальные индексы, FK-политики и две новые
колонки на ``requests``. Поведения в этой фазе нет — тестировать больше нечего.
"""
from sqlalchemy import Boolean, Date, DateTime, Integer, SmallInteger, String, Text
from sqlalchemy.dialects import postgresql, sqlite

from uk_management_bot.database.models import (  # noqa: F401 — регистрация в Base
    Elevator,
    ElevatorMaintenanceOccurrence,
    ElevatorStatusEvent,
    ElevatorsConfig,
    Request,
)
from uk_management_bot.database.models.elevator import (
    ELEVATOR_EVENT_KINDS,
    ELEVATOR_EVENT_SOURCES,
    ELEVATOR_STATUSES,
    OCCURRENCE_KINDS,
    OCCURRENCE_STATES,
)
from uk_management_bot.database.session import Base


def _fk_targets(column):
    return {(fk.column.table.name, fk.column.name, fk.ondelete) for fk in column.foreign_keys}


def _partial_unique_index(table, name):
    idx = next(i for i in table.indexes if i.name == name)
    assert idx.unique is True
    return idx


def test_canonical_constants():
    assert ELEVATOR_STATUSES == ("working", "not_working", "under_repair", "maintenance")
    assert ELEVATOR_EVENT_KINDS == (
        "status_changed",
        "commissioned",
        "archived",
        "contract_changed",
        "cert_changed",
        "passport_changed",
    )
    assert ELEVATOR_EVENT_SOURCES == ("manual", "request_hint", "infrasafe", "system")
    assert OCCURRENCE_KINDS == ("maintenance", "certification")
    assert OCCURRENCE_STATES == ("planned", "done", "cancelled")


def test_all_four_tables_registered_in_base_metadata():
    for name in (
        "elevators",
        "elevator_status_events",
        "elevator_maintenance_occurrences",
        "elevators_config",
    ):
        assert name in Base.metadata.tables, name
    assert Elevator.__tablename__ == "elevators"
    assert ElevatorStatusEvent.__tablename__ == "elevator_status_events"
    assert ElevatorMaintenanceOccurrence.__tablename__ == "elevator_maintenance_occurrences"
    assert ElevatorsConfig.__tablename__ == "elevators_config"


def test_elevators_columns_and_nullability():
    t = Base.metadata.tables["elevators"]
    c = t.c
    # Идентификация
    assert _fk_targets(c.building_id) == {("buildings", "id", None)}
    assert c.building_id.nullable is False
    assert c.entrance_number.nullable is False and isinstance(c.entrance_number.type, Integer)
    assert c.elevator_number.nullable is False and isinstance(c.elevator_number.type, Integer)
    # Паспорт: обязательные / опциональные
    for name in ("passport_number", "manufacturer", "serial_number"):
        assert c[name].nullable is False, name
        assert isinstance(c[name].type, String), name
    for name in ("factory_number", "model", "floors_served"):
        assert c[name].nullable is True, name
    assert isinstance(c.production_year.type, Integer) and c.production_year.nullable
    assert isinstance(c.capacity_kg.type, Integer) and c.capacity_kg.nullable
    assert isinstance(c.commissioned_at.type, Date) and c.commissioned_at.nullable
    # Статус: NULL до ввода в эксплуатацию
    assert c.current_status.nullable is True
    assert isinstance(c.status_since.type, DateTime) and c.status_since.type.timezone
    assert isinstance(c.downtime_reason.type, Text)
    assert isinstance(c.spare_part_expected_on.type, Date)
    assert isinstance(c.publish_downtime_details.type, Boolean)
    assert c.publish_downtime_details.nullable is False
    assert c.publish_downtime_details.server_default is not None
    # Договор и освидетельствование
    for name in ("service_org_name", "service_org_phone", "contract_number", "cert_number", "cert_act_url"):
        assert isinstance(c[name].type, String) and c[name].nullable, name
    assert isinstance(c.contract_until.type, Date)
    assert isinstance(c.cert_valid_until.type, Date)
    # Напоминания
    for name in ("contract_reminder_stage", "cert_reminder_stage"):
        assert isinstance(c[name].type, SmallInteger), name
        assert c[name].nullable is False and c[name].server_default is not None, name
    assert isinstance(c.downtime_reminded_at.type, DateTime) and c.downtime_reminded_at.nullable
    # Публичность
    assert isinstance(c.public_code.type, String) and c.public_code.type.length == 32
    assert c.public_code.nullable is False and c.public_code.unique is True
    assert isinstance(c.is_public.type, Boolean) and c.is_public.nullable is False
    # Жизненный цикл
    assert isinstance(c.is_commissioned.type, Boolean) and c.is_commissioned.nullable is False
    assert isinstance(c.archived_at.type, DateTime) and c.archived_at.nullable
    assert isinstance(c.archived_reason.type, Text)
    assert c.created_at.nullable is False and c.created_at.server_default is not None
    assert c.updated_at.server_default is not None and c.updated_at.onupdate is not None
    assert isinstance(c.version.type, Integer) and c.version.nullable is False
    assert c.version.server_default is not None


def test_elevators_partial_unique_index_on_active_rows():
    t = Base.metadata.tables["elevators"]
    idx = _partial_unique_index(t, "uq_elevators_building_entrance_number_active")
    assert [col.name for col in idx.columns] == ["building_id", "entrance_number", "elevator_number"]
    assert str(idx.dialect_options["postgresql"]["where"]) == "archived_at IS NULL"
    assert str(idx.dialect_options["sqlite"]["where"]) == "archived_at IS NULL"


def test_elevators_status_check_allows_null():
    t = Base.metadata.tables["elevators"]
    ck = next(x for x in t.constraints if getattr(x, "name", None) == "ck_elevators_current_status")
    sql = str(ck.sqltext)
    assert "current_status IS NULL" in sql
    for status in ELEVATOR_STATUSES:
        assert f"'{status}'" in sql


def test_status_events_columns():
    t = Base.metadata.tables["elevator_status_events"]
    c = t.c
    assert _fk_targets(c.elevator_id) == {("elevators", "id", "CASCADE")}
    assert c.elevator_id.nullable is False
    assert any([col.name for col in i.columns] == ["elevator_id"] for i in t.indexes)
    assert c.event_kind.nullable is False
    assert c.old_status.nullable and c.new_status.nullable
    assert isinstance(c.occurred_at.type, DateTime) and c.occurred_at.nullable is False
    assert _fk_targets(c.actor_user_id) == {("users", "id", "SET NULL")}
    assert c.source.nullable is False
    # Журнал переживает удаление заявки: номер без FK (образец material_issues)
    assert isinstance(c.request_number.type, String) and c.request_number.type.length == 15
    assert c.request_number.foreign_keys == set()
    assert isinstance(c.reason.type, Text)
    assert isinstance(c.payload.type.dialect_impl(postgresql.dialect()), postgresql.JSONB)
    assert not isinstance(c.payload.type.dialect_impl(sqlite.dialect()), postgresql.JSONB)
    names = {getattr(x, "name", None) for x in t.constraints}
    assert {"ck_elevator_status_events_event_kind", "ck_elevator_status_events_source"} <= names


def test_maintenance_occurrences_columns_and_partial_unique():
    t = Base.metadata.tables["elevator_maintenance_occurrences"]
    c = t.c
    assert _fk_targets(c.elevator_id) == {("elevators", "id", "CASCADE")}
    assert c.elevator_id.nullable is False
    assert c.kind.nullable is False
    assert isinstance(c.due_on.type, Date) and c.due_on.nullable is False
    assert c.state.nullable is False and c.state.server_default is not None
    assert isinstance(c.done_at.type, DateTime) and c.done_at.nullable
    assert _fk_targets(c.done_by_user_id) == {("users", "id", "SET NULL")}
    assert _fk_targets(c.created_by_user_id) == {("users", "id", "SET NULL")}
    assert isinstance(c.comment.type, Text)
    assert c.request_number.type.length == 15 and c.request_number.foreign_keys == set()
    assert isinstance(c.reminder_stage.type, SmallInteger) and c.reminder_stage.nullable is False
    assert isinstance(c.overdue_reminded_at.type, DateTime) and c.overdue_reminded_at.nullable
    assert c.created_at.server_default is not None
    names = {getattr(x, "name", None) for x in t.constraints}
    assert {
        "ck_elevator_maintenance_occurrences_kind",
        "ck_elevator_maintenance_occurrences_state",
    } <= names
    idx = _partial_unique_index(t, "uq_elevator_maintenance_occurrences_active")
    assert [col.name for col in idx.columns] == ["elevator_id", "kind", "due_on"]
    assert str(idx.dialect_options["postgresql"]["where"]) == "state <> 'cancelled'"
    assert str(idx.dialect_options["sqlite"]["where"]) == "state <> 'cancelled'"


def test_elevators_config_is_singleton_clone_of_auto_manager_config():
    t = Base.metadata.tables["elevators_config"]
    ref = Base.metadata.tables["auto_manager_config"]
    assert set(t.c.keys()) == set(ref.c.keys()) == {"id", "data", "updated_at", "updated_by"}
    assert t.c.data.nullable is False
    assert isinstance(t.c.data.type.dialect_impl(postgresql.dialect()), postgresql.JSONB)
    assert _fk_targets(t.c.updated_by) == {("users", "id", "SET NULL")}
    assert t.c.updated_by.index is True


def test_requests_has_elevator_columns():
    t = Base.metadata.tables["requests"]
    c = t.c
    assert _fk_targets(c.elevator_id) == {("elevators", "id", "SET NULL")}
    assert c.elevator_id.nullable is True and c.elevator_id.index is True
    assert "ix_requests_elevator_id" in {i.name for i in t.indexes}
    assert isinstance(c.elevator_operational.type, Boolean)
    assert c.elevator_operational.nullable is True
    # Существующий инвариант адреса не тронут
    assert "ck_requests_address_type_fk" in {getattr(x, "name", None) for x in t.constraints}
