"""Чистая выборка публичного списка лифтов (`public`, T16) — sqlite, sync + async."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from uk_management_bot.database.models.elevator import ElevatorMaintenanceOccurrence
from uk_management_bot.services.elevator_service.public import (
    last_maintenance_by_elevator_async,
    last_maintenance_by_elevator_sync,
    list_public_elevators_async,
    list_public_elevators_sync,
)

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)


def _rows(seed):
    """Дворы «Бета»(1) и «Альфа»(2); публичные: 1,2 (дом 1), 3 (дом 2), 4 (дом 3);
    отсеиваются: 5 непубличный, 6 архивный, 7 не введён, 8 без статуса."""
    return [
        seed.yard(1, "Бета"), seed.yard(2, "Альфа"),
        seed.building(1, yard_id=1, address="ул. Б, д. 2"),
        seed.building(2, yard_id=1, address="ул. А, д. 1"),
        seed.building(3, yard_id=2, address="ул. В, д. 3"),
        seed.elevator(1, building_id=1, entrance=2, number=1, is_public=True),
        seed.elevator(2, building_id=1, entrance=1, number=2, is_public=True),
        seed.elevator(3, building_id=2, entrance=1, number=1, is_public=True),
        seed.elevator(4, building_id=3, entrance=1, number=1, is_public=True),
        seed.elevator(5, building_id=1, entrance=3, number=1, is_public=False),
        seed.elevator(6, building_id=1, entrance=4, number=1, is_public=True, archived_at=NOW),
        seed.elevator(7, building_id=2, entrance=2, number=1, is_public=True, commissioned=False),
        seed.elevator(8, building_id=3, entrance=2, number=1, is_public=True, status=None),
        # Просроченное ТО закрыто 20.08 → бизнес-дата закрытия, а не due_on
        ElevatorMaintenanceOccurrence(elevator_id=1, kind="maintenance", due_on=date(2026, 8, 1),
                                      state="done",
                                      done_at=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)),
        # done без done_at (легаси) → fallback на due_on; здесь раньше, чем 20.08
        ElevatorMaintenanceOccurrence(elevator_id=1, kind="maintenance", due_on=date(2026, 6, 1),
                                      state="done", done_at=None),
        ElevatorMaintenanceOccurrence(elevator_id=1, kind="maintenance", due_on=date(2026, 10, 1),
                                      state="planned"),
        ElevatorMaintenanceOccurrence(elevator_id=2, kind="certification", due_on=date(2026, 8, 1),
                                      state="done", done_at=NOW),
        # Только fallback: done без done_at
        ElevatorMaintenanceOccurrence(elevator_id=2, kind="maintenance", due_on=date(2026, 5, 5),
                                      state="done", done_at=None),
        # Полночь Ташкента 21.08 = 19:00 UTC 20.08 — бизнес-дата, не UTC-дата
        ElevatorMaintenanceOccurrence(elevator_id=4, kind="maintenance", due_on=date(2026, 8, 1),
                                      state="done",
                                      done_at=datetime(2026, 8, 20, 19, 30, tzinfo=timezone.utc)),
        ElevatorMaintenanceOccurrence(elevator_id=3, kind="maintenance", due_on=date(2026, 8, 1),
                                      state="cancelled"),
    ]


EXPECTED_ORDER = [4, 3, 2, 1]  # Альфа(д.3) → Бета: ул. А д.1 → ул. Б д.2: подъезд 1 → 2


def test_sync_list_and_last_maintenance(el_db, el_seed):
    el_db.add_all(_rows(el_seed))
    el_db.commit()

    elevators = list_public_elevators_sync(el_db)
    assert [e.id for e in elevators] == EXPECTED_ORDER
    assert all(e.building.yard.name for e in elevators)

    assert last_maintenance_by_elevator_sync(el_db, [1, 2, 3, 4]) == {
        1: date(2026, 8, 20), 2: date(2026, 5, 5), 4: date(2026, 8, 21),
    }
    assert last_maintenance_by_elevator_sync(el_db, []) == {}


@pytest.mark.asyncio
async def test_async_mirrors(el_async_factory, el_seed):
    async with el_async_factory() as s:
        s.add_all(_rows(el_seed))
        await s.commit()

    async with el_async_factory() as s:
        elevators = await list_public_elevators_async(s)
        assert [e.id for e in elevators] == EXPECTED_ORDER
        assert elevators[0].building.yard.name == "Альфа"
        assert await last_maintenance_by_elevator_async(s, [e.id for e in elevators]) == {
            1: date(2026, 8, 20), 2: date(2026, 5, 5), 4: date(2026, 8, 21),
        }
