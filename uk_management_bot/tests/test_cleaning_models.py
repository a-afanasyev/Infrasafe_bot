"""Схема модуля «Уборка» (этап 1): только интроспекция метаданных, БД не нужна."""
from sqlalchemy.dialects import postgresql, sqlite

from uk_management_bot.database.models import (  # noqa: F401 — регистрация в Base
    CleaningAssignment,
    CleaningBuildingSettings,
    CleaningComplaint,
    CleaningDay,
    CleaningPhoto,
    CleaningPlanVersion,
    CleaningRules,
    CleaningTask,
    CleaningTaskEvent,
)
from uk_management_bot.database.models.cleaning import (
    PHOTO_OUTCOMES,
    PHOTO_STATES,
    TASK_STATUSES,
    TRUST_LEVELS,
)
from uk_management_bot.database.session import Base

TABLES = (
    "cleaning_plan_versions", "cleaning_assignments", "cleaning_building_settings",
    "cleaning_days", "cleaning_rules", "cleaning_tasks", "cleaning_photos",
    "cleaning_task_events", "cleaning_complaints",
)


def _unique_sets(table) -> set[frozenset[str]]:
    from sqlalchemy import UniqueConstraint
    return {frozenset(c.name for c in u.columns) for u in table.constraints if isinstance(u, UniqueConstraint)}


def test_constants():
    assert TASK_STATUSES == ("planned", "in_progress", "accepted", "review", "rejected", "missed", "expired")
    assert PHOTO_STATES == ("pending", "done")
    assert PHOTO_OUTCOMES == ("activated", "superseded", "evidence", "refused")
    assert TRUST_LEVELS == ("live", "deferred", "offline", "late")


def test_tables_registered():
    for name in TABLES:
        assert name in Base.metadata.tables, name


def test_task_is_unique_per_entrance_and_day():
    assert frozenset({"building_id", "entrance", "work_date"}) in _unique_sets(Base.metadata.tables["cleaning_tasks"])


def test_photo_op_key_unique_and_slot_not_null():
    t = Base.metadata.tables["cleaning_photos"]
    assert t.c.op_key.unique is True
    assert t.c.slot.nullable is False
    assert t.c.received_at.nullable is False


def test_current_photo_partial_unique_index_on_both_dialects():
    t = Base.metadata.tables["cleaning_photos"]
    idx = next(i for i in t.indexes if i.name == "uq_cleaning_photos_current_slot")
    assert idx.unique is True
    assert [c.name for c in idx.columns] == ["task_id", "slot"]
    for dialect, key in ((postgresql.dialect(), "postgresql"), (sqlite.dialect(), "sqlite")):
        where = idx.dialect_options[key]["where"]
        assert "is_current" in str(where.compile(dialect=dialect))


def test_complaint_request_number_optional_and_unique_per_author_day():
    t = Base.metadata.tables["cleaning_complaints"]
    assert t.c.request_number.nullable is True
    assert t.c.request_number.unique is True
    assert frozenset({"author_id", "building_id", "entrance", "work_date"}) in _unique_sets(t)


def test_plan_version_is_unique_per_building_start():
    assert frozenset({"building_id", "valid_from"}) in _unique_sets(Base.metadata.tables["cleaning_plan_versions"])
