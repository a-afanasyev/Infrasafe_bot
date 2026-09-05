"""Паспорт лифта: создание, правка, ввод в эксплуатацию, архивация (sqlite)."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from uk_management_bot.database.models.elevator import (
    Elevator,
    ElevatorMaintenanceOccurrence,
    ElevatorStatusEvent,
)
from uk_management_bot.services.elevator_service import (
    ElevatorConflictError,
    ElevatorNotFoundError,
    ElevatorStateError,
    ElevatorValidationError,
    archive_sync,
    commission_async,
    commission_sync,
    create_elevator_async,
    create_elevator_sync,
    get_elevator_sync,
    is_valid_public_code,
    update_passport_sync,
)
from uk_management_bot.services.elevator_service import passport as passport_module
from uk_management_bot.utils.business_time import business_today

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
ACTOR = 50
DATA = {
    "building_id": 1, "entrance_number": 2, "elevator_number": 1,
    "passport_number": "P-1", "manufacturer": "OTIS", "serial_number": "S-1",
    "model": "Gen2", "contract_until": date(2027, 1, 1),
}


def _seed(db, seed, *extra):
    db.add_all([
        seed.yard(), seed.building(1, entrance_count=4),
        seed.building(2, entrance_count=2, is_active=False),
        seed.user(ACTOR, roles='["manager"]'), *extra,
    ])
    db.commit()


def _events(db, elevator_id):
    rows = db.execute(
        select(ElevatorStatusEvent).where(ElevatorStatusEvent.elevator_id == elevator_id)
        .order_by(ElevatorStatusEvent.id)
    ).scalars().all()
    return [(e.event_kind, e.old_status, e.new_status, e.payload) for e in rows]


class TestCreate:
    def test_creates_with_random_code_and_no_status(self, el_db, el_seed):
        _seed(el_db, el_seed)
        elevator = create_elevator_sync(el_db, DATA, actor_user_id=ACTOR)
        el_db.commit()

        assert elevator.id is not None
        assert is_valid_public_code(elevator.public_code)
        assert elevator.public_code != str(elevator.id)
        assert (elevator.current_status, elevator.is_commissioned, elevator.version) == (None, False, 1)
        assert elevator.model == "Gen2" and elevator.contract_until == date(2027, 1, 1)
        assert _events(el_db, elevator.id) == []

    def test_two_elevators_get_different_codes(self, el_db, el_seed):
        _seed(el_db, el_seed)
        first = create_elevator_sync(el_db, DATA, actor_user_id=ACTOR)
        second = create_elevator_sync(el_db, {**DATA, "elevator_number": 2}, actor_user_id=ACTOR)
        assert first.public_code != second.public_code

    def test_missing_required(self, el_db, el_seed):
        _seed(el_db, el_seed)
        with pytest.raises(ElevatorValidationError):
            create_elevator_sync(el_db, {**DATA, "manufacturer": " "}, actor_user_id=ACTOR)

    def test_unknown_field(self, el_db, el_seed):
        _seed(el_db, el_seed)
        with pytest.raises(ElevatorValidationError):
            create_elevator_sync(el_db, {**DATA, "commissioned_at": date(2026, 1, 1)}, actor_user_id=ACTOR)

    @pytest.mark.parametrize("building_id", [2, 99])
    def test_inactive_or_missing_building(self, el_db, el_seed, building_id):
        _seed(el_db, el_seed)
        with pytest.raises(ElevatorValidationError):
            create_elevator_sync(el_db, {**DATA, "building_id": building_id}, actor_user_id=ACTOR)

    def test_entrance_beyond_building(self, el_db, el_seed):
        _seed(el_db, el_seed)
        with pytest.raises(ElevatorValidationError, match="4 подъезд"):
            create_elevator_sync(el_db, {**DATA, "entrance_number": 5}, actor_user_id=ACTOR)

    def test_duplicate_place_conflict(self, el_db, el_seed):
        _seed(el_db, el_seed)
        create_elevator_sync(el_db, DATA, actor_user_id=ACTOR)
        with pytest.raises(ElevatorConflictError):
            create_elevator_sync(el_db, DATA, actor_user_id=ACTOR)

    def test_archived_place_is_free(self, el_db, el_seed):
        _seed(el_db, el_seed, el_seed.elevator(1, entrance=2, number=1, archived_at=NOW))
        elevator = create_elevator_sync(el_db, DATA, actor_user_id=ACTOR)
        assert elevator.id != 1

    def test_public_code_collision_retried(self, el_db, el_seed, monkeypatch):
        _seed(el_db, el_seed, el_seed.elevator(1, entrance=1, number=1, public_code="taken-code-0123456789"))
        codes = iter(["taken-code-0123456789", "fresh-code-0123456789"])
        monkeypatch.setattr(passport_module, "generate_public_code", lambda: next(codes))

        elevator = create_elevator_sync(el_db, DATA, actor_user_id=ACTOR)
        el_db.commit()

        assert elevator.public_code == "fresh-code-0123456789"
        assert sorted(el_db.execute(select(Elevator.id)).scalars().all()) == sorted([1, elevator.id])

    def test_async_parity(self, el_async_factory, el_seed):
        async def run():
            async with el_async_factory() as s:
                s.add_all([el_seed.yard(), el_seed.building(1, entrance_count=4),
                           el_seed.user(ACTOR, roles='["manager"]')])
                await s.commit()
            async with el_async_factory() as s:
                elevator = await create_elevator_async(s, DATA, actor_user_id=ACTOR)
                await s.commit()
                with pytest.raises(ElevatorConflictError):
                    await create_elevator_async(s, DATA, actor_user_id=ACTOR)
                with pytest.raises(ElevatorValidationError):
                    await create_elevator_async(s, {**DATA, "entrance_number": 9}, actor_user_id=ACTOR)
                return elevator.public_code, elevator.is_commissioned

        code, commissioned = asyncio.run(run())
        assert is_valid_public_code(code) and commissioned is False


class TestUpdate:
    def _elevator(self, el_db, el_seed, **kw):
        _seed(el_db, el_seed, el_seed.elevator(1, entrance=1, number=1, **kw))

    def test_empty_patch_noop(self, el_db, el_seed):
        self._elevator(el_db, el_seed)
        elevator = update_passport_sync(el_db, 1, {}, actor_user_id=ACTOR, expected_version=1, now=NOW)
        assert elevator.version == 1 and _events(el_db, 1) == []

    def test_same_values_noop(self, el_db, el_seed):
        self._elevator(el_db, el_seed)
        elevator = update_passport_sync(el_db, 1, {"manufacturer": "OTIS"}, actor_user_id=ACTOR,
                                        expected_version=None, now=NOW)
        assert elevator.version == 1 and _events(el_db, 1) == []

    def test_version_conflict(self, el_db, el_seed):
        self._elevator(el_db, el_seed)
        with pytest.raises(ElevatorConflictError):
            update_passport_sync(el_db, 1, {"model": "X"}, actor_user_id=ACTOR, expected_version=7, now=NOW)

    def test_unknown_and_blank_required(self, el_db, el_seed):
        self._elevator(el_db, el_seed)
        with pytest.raises(ElevatorValidationError):
            update_passport_sync(el_db, 1, {"version": 5}, actor_user_id=ACTOR, expected_version=None, now=NOW)
        with pytest.raises(ElevatorValidationError):
            update_passport_sync(el_db, 1, {"serial_number": ""}, actor_user_id=ACTOR, expected_version=None, now=NOW)

    def test_changes_write_diff_and_reset_stages(self, el_db, el_seed):
        self._elevator(el_db, el_seed, contract_reminder_stage=14, cert_reminder_stage=7,
                       contract_until=date(2026, 10, 1))
        patch = {"model": "Gen2", "contract_until": date(2027, 1, 1),
                 "cert_valid_until": date(2027, 6, 1), "is_public": True}

        elevator = update_passport_sync(el_db, 1, patch, actor_user_id=ACTOR, expected_version=1, now=NOW)
        el_db.commit()

        assert (elevator.version, elevator.contract_reminder_stage, elevator.cert_reminder_stage) == (2, 0, 0)
        assert elevator.is_public is True
        events = _events(el_db, 1)
        assert [e[0] for e in events] == ["passport_changed", "contract_changed", "cert_changed"]
        assert events[0][3] == {"changed": {
            "model": [None, "Gen2"],
            "contract_until": ["2026-10-01", "2027-01-01"],
            "cert_valid_until": [None, "2027-06-01"],
            "is_public": [False, True],
        }}
        assert events[1][3] == {"contract_until": ["2026-10-01", "2027-01-01"]}
        assert events[2][3] == {"cert_valid_until": [None, "2027-06-01"]}

    def test_stage_not_reset_when_date_unchanged(self, el_db, el_seed):
        self._elevator(el_db, el_seed, contract_reminder_stage=14, contract_until=date(2026, 10, 1))
        elevator = update_passport_sync(el_db, 1, {"contract_number": "N-1"}, actor_user_id=ACTOR,
                                        expected_version=1, now=NOW)
        assert elevator.contract_reminder_stage == 14
        assert [e[0] for e in _events(el_db, 1)] == ["passport_changed"]

    def test_place_change_forbidden_after_commissioning(self, el_db, el_seed):
        self._elevator(el_db, el_seed)
        with pytest.raises(ElevatorStateError):
            update_passport_sync(el_db, 1, {"entrance_number": 2}, actor_user_id=ACTOR, expected_version=None, now=NOW)

    def test_place_change_before_commissioning(self, el_db, el_seed):
        _seed(el_db, el_seed,
              el_seed.elevator(1, entrance=1, number=1, commissioned=False),
              el_seed.elevator(2, entrance=2, number=1, commissioned=False))
        with pytest.raises(ElevatorConflictError):
            update_passport_sync(el_db, 1, {"entrance_number": 2}, actor_user_id=ACTOR, expected_version=None, now=NOW)
        with pytest.raises(ElevatorValidationError):
            update_passport_sync(el_db, 1, {"entrance_number": 9}, actor_user_id=ACTOR, expected_version=None, now=NOW)
        elevator = update_passport_sync(el_db, 1, {"entrance_number": 3}, actor_user_id=ACTOR,
                                        expected_version=None, now=NOW)
        assert elevator.entrance_number == 3

    def test_archived_not_found(self, el_db, el_seed):
        self._elevator(el_db, el_seed, archived_at=NOW)
        with pytest.raises(ElevatorNotFoundError):
            update_passport_sync(el_db, 1, {"model": "X"}, actor_user_id=ACTOR, expected_version=None, now=NOW)


class TestCommission:
    def test_commission_sets_working_and_two_events(self, el_db, el_seed):
        _seed(el_db, el_seed, el_seed.elevator(1, commissioned=False))
        elevator = commission_sync(el_db, 1, actor_user_id=ACTOR, commissioned_at=date(2026, 9, 1), now=NOW)
        el_db.commit()

        assert (elevator.is_commissioned, elevator.current_status, elevator.commissioned_at) == (
            True, "working", date(2026, 9, 1))
        assert elevator.status_since.replace(tzinfo=timezone.utc) == NOW
        assert elevator.version == 2
        assert _events(el_db, 1) == [
            ("commissioned", None, None, {"commissioned_at": "2026-09-01"}),
            ("status_changed", None, "working", None),
        ]

    def test_default_commissioned_at_is_business_today(self, el_db, el_seed):
        _seed(el_db, el_seed, el_seed.elevator(1, commissioned=False))
        elevator = commission_sync(el_db, 1, actor_user_id=ACTOR, now=NOW)
        assert elevator.commissioned_at == business_today(NOW)

    def test_repeat_is_state_error(self, el_db, el_seed):
        _seed(el_db, el_seed, el_seed.elevator(1))
        with pytest.raises(ElevatorStateError):
            commission_sync(el_db, 1, actor_user_id=ACTOR, now=NOW)

    def test_requires_passport(self, el_db, el_seed):
        _seed(el_db, el_seed, el_seed.elevator(1, commissioned=False, manufacturer=""))
        with pytest.raises(ElevatorValidationError):
            commission_sync(el_db, 1, actor_user_id=ACTOR, now=NOW)

    def test_async_parity(self, el_db, el_seed, el_async_factory):
        _seed(el_db, el_seed, el_seed.elevator(1, commissioned=False))
        sync_elevator = commission_sync(el_db, 1, actor_user_id=ACTOR, commissioned_at=date(2026, 9, 1), now=NOW)
        el_db.commit()
        sync_state = (sync_elevator.current_status, sync_elevator.commissioned_at, sync_elevator.version)
        sync_events = _events(el_db, 1)

        async def run():
            async with el_async_factory() as s:
                s.add_all([el_seed.yard(), el_seed.building(), el_seed.user(ACTOR),
                           el_seed.elevator(1, commissioned=False)])
                await s.commit()
            async with el_async_factory() as s:
                elevator = await commission_async(s, 1, actor_user_id=ACTOR, commissioned_at=date(2026, 9, 1), now=NOW)
                await s.commit()
                with pytest.raises(ElevatorStateError):
                    await commission_async(s, 1, actor_user_id=ACTOR, now=NOW)
                rows = (await s.execute(select(ElevatorStatusEvent).order_by(ElevatorStatusEvent.id))).scalars().all()
                return (elevator.current_status, elevator.commissioned_at, elevator.version), [
                    (e.event_kind, e.old_status, e.new_status, e.payload) for e in rows]

        async_state, async_events = asyncio.run(run())
        assert async_state == sync_state and async_events == sync_events


class TestArchive:
    def test_archive_cancels_planned_and_unpublishes(self, el_db, el_seed):
        _seed(el_db, el_seed, el_seed.elevator(1, status="not_working", is_public=True))
        el_db.add_all([
            ElevatorMaintenanceOccurrence(id=1, elevator_id=1, kind="maintenance", due_on=date(2026, 10, 1)),
            ElevatorMaintenanceOccurrence(id=2, elevator_id=1, kind="maintenance", due_on=date(2026, 8, 1), state="done"),
        ])
        el_db.commit()

        elevator = archive_sync(el_db, 1, actor_user_id=ACTOR, reason="демонтаж", now=NOW)
        el_db.commit()

        assert elevator.archived_at.replace(tzinfo=timezone.utc) == NOW
        assert (elevator.archived_reason, elevator.is_public, elevator.current_status) == ("демонтаж", False, "not_working")
        assert elevator.version == 2
        states = dict(el_db.execute(select(ElevatorMaintenanceOccurrence.id, ElevatorMaintenanceOccurrence.state)).all())
        assert states == {1: "cancelled", 2: "done"}
        assert _events(el_db, 1) == [("archived", None, None, None)]
        with pytest.raises(ElevatorNotFoundError):
            get_elevator_sync(el_db, 1)

    def test_repeat_is_state_error(self, el_db, el_seed):
        _seed(el_db, el_seed, el_seed.elevator(1, archived_at=NOW - timedelta(days=1)))
        with pytest.raises(ElevatorStateError):
            archive_sync(el_db, 1, actor_user_id=ACTOR, reason="x", now=NOW)

    def test_reason_required(self, el_db, el_seed):
        _seed(el_db, el_seed, el_seed.elevator(1))
        with pytest.raises(ElevatorValidationError):
            archive_sync(el_db, 1, actor_user_id=ACTOR, reason="  ", now=NOW)
