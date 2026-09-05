"""Чтение: лифт/журнал/график/заявки (`reads`), реестр и сводка (`registry`),
доступность поверх журнала (`metrics`) — sqlite."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from uk_management_bot.database.models.elevator import (
    ElevatorMaintenanceOccurrence,
    ElevatorStatusEvent,
)
from uk_management_bot.database.models.request import Request
from uk_management_bot.services.elevator_service import (
    ElevatorNotFoundError,
    ElevatorValidationError,
    availability_30d_for_page_async,
    count_building_apartments_without_entrance_async,
    count_elevators_async,
    get_elevator_async,
    get_elevator_including_archived_sync,
    get_elevator_sync,
    list_active_for_building_async,
    list_active_for_building_sync,
    list_all_occurrences_async,
    list_elevators_async,
    list_events_async,
    list_occurrences_async,
    list_requests_for_elevator_async,
    status_intervals_async,
    summary_async,
)
from uk_management_bot.utils.business_time import business_today
import uk_management_bot.utils.constants as C

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
TODAY = business_today(NOW)
D = timedelta(days=1)


def _base(seed):
    """Два двора, три дома; лифты: 1,2 (дом 1), 3 (дом 2), 4 (дом 3, двор 2), 5 архивный."""
    return [
        seed.yard(1, "Альфа"), seed.yard(2, "Бета"),
        seed.building(1, yard_id=1, address="ул. А, д. 1"),
        seed.building(2, yard_id=1, address="ул. Б, д. 2"),
        seed.building(3, yard_id=2, address="ул. В, д. 3"),
        seed.user(1, roles='["manager"]'),
        seed.elevator(1, building_id=1, entrance=2, number=1, status="working",
                      contract_until=TODAY + 10 * D, cert_valid_until=TODAY + 10 * D),
        seed.elevator(2, building_id=1, entrance=1, number=1, status="not_working",
                      status_since=NOW - 10 * D, contract_until=TODAY - D, cert_valid_until=TODAY),
        seed.elevator(3, building_id=2, entrance=1, number=1, status="under_repair",
                      status_since=NOW - 40 * D),
        seed.elevator(4, building_id=3, entrance=1, number=1, commissioned=False),
        seed.elevator(5, building_id=1, entrance=3, number=1, status="working", archived_at=NOW),
    ]


def _occ(id, elevator_id, due_on, *, kind="maintenance", state="planned", **extra):
    return ElevatorMaintenanceOccurrence(
        id=id, elevator_id=elevator_id, kind=kind, due_on=due_on, state=state, **extra)


def _event(id, elevator_id, new_status, at, old_status=None):
    return ElevatorStatusEvent(
        id=id, elevator_id=elevator_id, event_kind="status_changed", old_status=old_status,
        new_status=new_status, occurred_at=at, source="manual",
    )


def _request(number, *, category="elevator", elevator_id=None, status=C.REQUEST_STATUS_NEW):
    return Request(request_number=number, user_id=1, category=category, description="d",
                   urgency="low", status=status, elevator_id=elevator_id)


async def _seeded(factory, objects):
    """Залить объекты и вернуть свежую сессию для чтения."""
    async with factory() as s:
        s.add_all(objects)
        await s.commit()
    return factory()


# ---------------------------------------------------------------------------
# reads (sync)
# ---------------------------------------------------------------------------

class TestReadsSync:
    def test_get_elevator_loads_building(self, el_db, el_seed):
        el_db.add_all(_base(el_seed))
        el_db.commit()
        el_db.expire_all()
        elevator = get_elevator_sync(el_db, 1)
        assert elevator.building.address == "ул. А, д. 1"

    def test_get_elevator_archived_or_missing_not_found(self, el_db, el_seed):
        el_db.add_all(_base(el_seed))
        el_db.commit()
        with pytest.raises(ElevatorNotFoundError):
            get_elevator_sync(el_db, 5)
        with pytest.raises(ElevatorNotFoundError):
            get_elevator_sync(el_db, 99)
        assert get_elevator_including_archived_sync(el_db, 5).id == 5
        with pytest.raises(ElevatorNotFoundError):
            get_elevator_including_archived_sync(el_db, 99)

    def test_list_active_for_building_sorted_without_archived(self, el_db, el_seed):
        el_db.add_all(_base(el_seed))
        el_db.commit()
        assert [e.id for e in list_active_for_building_sync(el_db, 1)] == [2, 1]


# ---------------------------------------------------------------------------
# reads (async)
# ---------------------------------------------------------------------------

class TestReadsAsync:
    async def test_get_and_list_parity(self, el_async_factory, el_seed):
        async with await _seeded(el_async_factory, _base(el_seed)) as s:
            elevator = await get_elevator_async(s, 1)
            active = await list_active_for_building_async(s, 1)
            with pytest.raises(ElevatorNotFoundError):
                await get_elevator_async(s, 5)
        assert (elevator.building.address, [e.id for e in active]) == ("ул. А, д. 1", [2, 1])

    async def test_events_cursor_pagination(self, el_async_factory, el_seed):
        objects = _base(el_seed) + [
            _event(i, 1, "working", NOW - (10 - i) * D) for i in range(1, 6)
        ] + [_event(9, 2, "not_working", NOW)]
        async with await _seeded(el_async_factory, objects) as s:
            first = await list_events_async(s, 1, limit=2)
            second = await list_events_async(s, 1, limit=2, before_id=first[-1].id)
            with pytest.raises(ElevatorValidationError):
                await list_events_async(s, 1, limit=0)
        assert ([e.id for e in first], [e.id for e in second]) == ([5, 4], [3, 2])

    async def test_occurrences_filters(self, el_async_factory, el_seed):
        objects = _base(el_seed) + [
            _occ(1, 1, TODAY - 30 * D, state="done"),
            _occ(2, 1, TODAY + 5 * D),
            _occ(3, 1, TODAY + 40 * D, kind="certification"),
            _occ(4, 2, TODAY + 5 * D),
        ]
        async with await _seeded(el_async_factory, objects) as s:
            all_for_1 = await list_occurrences_async(s, 1)
            planned = await list_occurrences_async(s, 1, state="planned")
            cert = await list_occurrences_async(s, 1, kind="certification")
            window = await list_occurrences_async(s, 1, from_date=TODAY, to_date=TODAY + 10 * D)
            calendar = await list_all_occurrences_async(s, from_date=TODAY, to_date=TODAY + 10 * D)
            with pytest.raises(ElevatorValidationError):
                await list_occurrences_async(s, 1, kind="repair")
            with pytest.raises(ElevatorValidationError):
                await list_all_occurrences_async(s, from_date=TODAY, to_date=TODAY - D)
            calendar_view = [(o.id, o.elevator.building.address) for o in calendar]

        assert [o.id for o in all_for_1] == [1, 2, 3]
        assert [o.id for o in planned] == [2, 3]
        assert [o.id for o in cert] == [3]
        assert [o.id for o in window] == [2]
        assert calendar_view == [(2, "ул. А, д. 1"), (4, "ул. А, д. 1")]

    async def test_requests_for_elevator_and_orphans(self, el_async_factory, el_seed):
        objects = _base(el_seed) + [
            _request("260901-001", elevator_id=1),
            _request("260901-002", elevator_id=1, status=C.REQUEST_STATUS_APPROVED),
            _request("260901-003", elevator_id=1, status=C.REQUEST_STATUS_CANCELLED),
            _request("260901-004"),  # лифтовая без лифта — открытая
            _request("260901-005", status=C.REQUEST_STATUS_CANCELLED),  # закрытая — не считается
            _request("260901-006", category="plumbing"),
        ]
        async with await _seeded(el_async_factory, objects) as s:
            open_only = await list_requests_for_elevator_async(s, 1)
            with_closed = await list_requests_for_elevator_async(s, 1, include_closed=True)
            summary = await summary_async(s, now=NOW)

        assert sorted(r.request_number for r in open_only) == ["260901-001"]
        assert sorted(r.request_number for r in with_closed) == ["260901-001", "260901-002", "260901-003"]
        assert summary.requests_without_elevator == 1

    async def test_count_apartments_without_entrance(self, el_async_factory, el_seed):
        objects = _base(el_seed) + [
            el_seed.apartment(1, building_id=1, entrance=None),
            el_seed.apartment(2, building_id=1, entrance=None, is_active=False),
            el_seed.apartment(3, building_id=1, entrance=1),
            el_seed.apartment(4, building_id=2, entrance=None),
        ]
        async with await _seeded(el_async_factory, objects) as s:
            assert await count_building_apartments_without_entrance_async(s, 1) == 1


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------

class TestRegistry:
    async def test_default_list_excludes_archived_and_sorts(self, el_async_factory, el_seed):
        async with await _seeded(el_async_factory, _base(el_seed)) as s:
            rows = await list_elevators_async(s, now=NOW)
            total = await count_elevators_async(s, now=NOW)
        assert [e.id for e in rows] == [2, 1, 3, 4]
        assert total == 4

    async def test_filters(self, el_async_factory, el_seed):
        objects = _base(el_seed) + [
            _occ(1, 3, TODAY - 8 * D),  # просрочено (с 8-го дня)
            _occ(2, 1, TODAY - 7 * D),  # ещё в grace
            _occ(3, 2, TODAY - 20 * D, state="done"),  # done не считается
        ]

        async def ids(s, **kw):
            return [e.id for e in await list_elevators_async(s, now=NOW, **kw)]

        async with await _seeded(el_async_factory, objects) as s:
            result = {
                "yard": await ids(s, yard_id=2),
                "building": await ids(s, building_id=1),
                "status": await ids(s, status="not_working"),
                "uncommissioned": await ids(s, only_commissioned=False),
                "commissioned": await ids(s, only_commissioned=True),
                "archived": await ids(s, include_archived=True),
                "archived_no_contract": await ids(s, include_archived=True, flags={"no_contract"}),
                "no_contract": await ids(s, flags={"no_contract"}),
                "cert_expired": await ids(s, flags={"cert_expired"}),
                "overdue": await ids(s, flags={"maintenance_overdue"}),
                "combo": await ids(s, flags={"no_contract", "cert_expired"}, yard_id=1),
                "page": await ids(s, limit=2, offset=1),
                "count_no_contract": await count_elevators_async(s, flags={"no_contract"}, now=NOW),
            }

        assert result == {
            "yard": [4],
            "building": [2, 1],
            "status": [2],
            "uncommissioned": [4],
            "commissioned": [2, 1, 3],
            "archived": [2, 1, 5, 3, 4],
            "archived_no_contract": [2, 5, 3, 4],  # архивный 5 без договора попадает
            "no_contract": [2, 3, 4],
            "cert_expired": [3, 4],  # у лифта 2 срок = сегодня, ещё действует
            "overdue": [3],
            "combo": [3],  # во дворе 1 оба флага только у лифта 3
            "page": [1, 3],
            "count_no_contract": 3,
        }

    async def test_invalid_inputs(self, el_async_factory, el_seed):
        async with await _seeded(el_async_factory, _base(el_seed)) as s:
            with pytest.raises(ElevatorValidationError):
                await list_elevators_async(s, flags={"broken"})
            with pytest.raises(ElevatorValidationError):
                await list_elevators_async(s, status="broken")
            with pytest.raises(ElevatorValidationError):
                await list_elevators_async(s, limit=0)

    async def test_summary_by_yard(self, el_async_factory, el_seed):
        objects = _base(el_seed) + [_occ(1, 3, TODAY - 8 * D)]
        async with await _seeded(el_async_factory, objects) as s:
            summary = await summary_async(s, now=NOW)

        assert summary.today == TODAY
        totals = summary.totals
        assert totals.total == 4
        assert dict(totals.by_status) == {"not_working": 1, "under_repair": 1, "working": 1}
        assert (totals.no_contract, totals.cert_expired, totals.maintenance_overdue) == (3, 2, 1)
        # not_working 10 дней при пороге 7 → да; under_repair — порог None → нет
        assert totals.downtime_over_threshold == 1
        assert [(y.yard_name, y.counters.total) for y in summary.yards] == [("Альфа", 3), ("Бета", 1)]
        assert summary.yards[1].counters.by_status == {}

    async def test_summary_thresholds_param(self, el_async_factory, el_seed):
        async with await _seeded(el_async_factory, _base(el_seed)) as s:
            summary = await summary_async(
                s, now=NOW, downtime_thresholds={"not_working": 30, "under_repair": 30})
        assert summary.totals.downtime_over_threshold == 1  # только under_repair 40 дней


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------

class TestMetrics:
    async def test_intervals_and_availability(self, el_async_factory, el_seed):
        objects = _base(el_seed) + [
            _event(1, 1, "working", NOW - 60 * D),
            _event(2, 1, "not_working", NOW - 15 * D, old_status="working"),
            _event(3, 1, "working", NOW - 12 * D, old_status="not_working"),
            _event(4, 2, "working", NOW - 5 * D),
        ]
        async with await _seeded(el_async_factory, objects) as s:
            intervals = await status_intervals_async(s, [1, 2, 3])
            elevators = await list_elevators_async(s, now=NOW)
            availability = await availability_30d_for_page_async(s, elevators, now=NOW)

        assert [i.status for i in intervals[1]] == ["working", "not_working", "working"]
        assert intervals[1][0].started_at.tzinfo is not None
        assert 2 in intervals and 3 not in intervals
        assert availability[1] == 0.9  # 3 дня простоя из 30
        assert availability[2] == 1.0
        assert availability[3] is None  # журнал пуст
        assert availability[4] is None  # не введён в эксплуатацию

    async def test_empty_ids(self, el_async_factory, el_seed):
        async with await _seeded(el_async_factory, _base(el_seed)) as s:
            assert await status_intervals_async(s, []) == {}
