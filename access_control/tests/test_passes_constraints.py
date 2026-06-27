"""Schema-CHECK инварианты access_passes (порт из B, §9.3/§9.5). PostgreSQL-only.

Расходуемый лимит въездов пропуска должен быть согласован на уровне БД
(defense-in-depth, как у B): ``max_entries > 0`` и ``0 <= used_entries <=
max_entries``. Это закрывает невозможные состояния (отрицательный/нулевой лимит,
перерасход) на уровне схемы, а не только в логике ingestion.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from access_control.tests.conftest import PilotFixture


def _insert_pass(pg_db, apartment_id: int, *, max_entries: int, used_entries: int) -> None:
    pg_db.execute(
        text(
            "INSERT INTO access_passes "
            "(apartment_id, pass_type, max_entries, used_entries, status) "
            "VALUES (:a, 'taxi', :m, :u, 'active')"
        ),
        {"a": apartment_id, "m": max_entries, "u": used_entries},
    )
    pg_db.commit()


def test_max_entries_must_be_positive(pg_db, pilot: PilotFixture) -> None:
    with pytest.raises(IntegrityError):
        _insert_pass(pg_db, pilot.apartment_id, max_entries=0, used_entries=0)
    pg_db.rollback()


def test_used_entries_cannot_exceed_max(pg_db, pilot: PilotFixture) -> None:
    with pytest.raises(IntegrityError):
        _insert_pass(pg_db, pilot.apartment_id, max_entries=1, used_entries=2)
    pg_db.rollback()


def test_used_entries_cannot_be_negative(pg_db, pilot: PilotFixture) -> None:
    with pytest.raises(IntegrityError):
        _insert_pass(pg_db, pilot.apartment_id, max_entries=1, used_entries=-1)
    pg_db.rollback()


def test_valid_bounds_accepted(pg_db, pilot: PilotFixture) -> None:
    """used_entries == max_entries (исчерпанный taxi) допустим."""
    _insert_pass(pg_db, pilot.apartment_id, max_entries=1, used_entries=1)
    cnt = pg_db.execute(
        text("SELECT count(*) FROM access_passes WHERE apartment_id = :a"),
        {"a": pilot.apartment_id},
    ).scalar()
    assert cnt == 1
