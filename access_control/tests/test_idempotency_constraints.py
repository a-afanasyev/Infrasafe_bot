"""Ф2: идемпотентные UNIQUE-ключи приёма событий (§10.1) на доступной БД.

Гоняется на sqlite in-memory (независимо от settings.DATABASE_URL): создаём
схему через ``Base.metadata.create_all`` и проверяем, что повторная вставка с тем
же каноническим ключом ``(controller_id, event_id)`` падает с IntegrityError.

sqlite по умолчанию НЕ форсит FK (PRAGMA foreign_keys=off), поэтому вставляем
сырые строки с синтетическими controller_id без родительских записей — проверяем
именно UNIQUE-ограничение, а не FK.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

# Регистрируем родительские + пилотные таблицы на Base.
import uk_management_bot.database.models  # noqa: F401
import access_control.domain  # noqa: F401
from uk_management_bot.database.session import Base


@pytest.fixture()
def sqlite_engine():
    """Свежая sqlite in-memory БД со всей схемой (родители + пилот)."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


def test_camera_events_unique_controller_event(sqlite_engine) -> None:
    """UNIQUE(controller_id, event_id) на camera_events не даёт вставить дубль."""
    captured = dt.datetime(2026, 6, 26, 12, 0, 0)
    insert = text(
        "INSERT INTO camera_events "
        "(controller_id, event_id, direction, captured_at) "
        "VALUES (:cid, :eid, 'entry', :cap)"
    )
    with sqlite_engine.begin() as conn:
        conn.execute(insert, {"cid": 1, "eid": "evt-1", "cap": captured})

    with sqlite_engine.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(insert, {"cid": 1, "eid": "evt-1", "cap": captured})


def test_camera_events_distinct_controller_allowed(sqlite_engine) -> None:
    """Тот же event_id с другим controller_id — разные ключи, вставка проходит."""
    captured = dt.datetime(2026, 6, 26, 12, 0, 0)
    insert = text(
        "INSERT INTO camera_events "
        "(controller_id, event_id, direction, captured_at) "
        "VALUES (:cid, :eid, 'entry', :cap)"
    )
    with sqlite_engine.begin() as conn:
        conn.execute(insert, {"cid": 1, "eid": "evt-1", "cap": captured})
        conn.execute(insert, {"cid": 2, "eid": "evt-1", "cap": captured})
        count = conn.execute(text("SELECT COUNT(*) FROM camera_events")).scalar()
    assert count == 2


def test_access_events_unique_controller_event(sqlite_engine) -> None:
    """UNIQUE(controller_id, event_id) на access_events — один проезд на event."""
    occurred = dt.datetime(2026, 6, 26, 12, 0, 0)
    insert = text(
        "INSERT INTO access_events "
        "(controller_id, event_id, direction, occurred_at) "
        "VALUES (:cid, :eid, 'entry', :occ)"
    )
    with sqlite_engine.begin() as conn:
        conn.execute(insert, {"cid": 5, "eid": "evt-9", "occ": occurred})

    with sqlite_engine.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(insert, {"cid": 5, "eid": "evt-9", "occ": occurred})


def test_controller_sync_events_unique_controller_event(sqlite_engine) -> None:
    """UNIQUE(controller_id, event_id) на controller_sync_events (§8.4)."""
    insert = text(
        "INSERT INTO controller_sync_events (controller_id, event_id) "
        "VALUES (:cid, :eid)"
    )
    with sqlite_engine.begin() as conn:
        conn.execute(insert, {"cid": 7, "eid": "sync-1"})

    with sqlite_engine.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(insert, {"cid": 7, "eid": "sync-1"})


def _insert_controller(conn, *, uid: str, status: str) -> None:
    conn.execute(
        text(
            "INSERT INTO edge_controllers "
            "(controller_uid, api_key_hash, offline_mode, status) "
            "VALUES (:uid, 'h', 'fail_closed', :status)"
        ),
        {"uid": uid, "status": status},
    )


def test_edge_controllers_status_check_accepts_canonical(sqlite_engine) -> None:
    """CHECK ck_edge_controllers_status пропускает канонические значения (миграция 029)."""
    with sqlite_engine.begin() as conn:
        for i, status in enumerate(("active", "inactive", "decommissioned")):
            _insert_controller(conn, uid=f"ctrl-{i}", status=status)
        count = conn.execute(
            text("SELECT COUNT(*) FROM edge_controllers")
        ).scalar()
    assert count == 3


def test_edge_controllers_status_check_rejects_unknown(sqlite_engine) -> None:
    """Неканоническое значение status отклоняется CheckConstraint (миграция 029)."""
    with sqlite_engine.begin() as conn:
        with pytest.raises(IntegrityError):
            _insert_controller(conn, uid="ctrl-bad", status="enabled")


def test_review_fk_indexes_created_in_schema(sqlite_engine) -> None:
    """6 FK-индексов доревью присутствуют в схеме после create_all (миграция 029)."""
    from sqlalchemy import inspect as sa_inspect

    expected = {
        "access_events": {
            "ix_access_events_decision_id",
            "ix_access_events_camera_event_id",
        },
        "access_decisions": {
            "ix_access_decisions_matched_vehicle_id",
            "ix_access_decisions_matched_pass_id",
            "ix_access_decisions_supersedes_decision_id",
        },
        "camera_events": {"ix_camera_events_camera_id"},
    }
    inspector = sa_inspect(sqlite_engine)
    for table, names in expected.items():
        present = {ix["name"] for ix in inspector.get_indexes(table)}
        assert names <= present, f"{table}: отсутствуют индексы {names - present}"
