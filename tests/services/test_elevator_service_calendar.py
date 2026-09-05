"""График ТО/освидетельствований: генерация, пункты, перенос, отмена, закрытие (sqlite)."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone

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
    cancel_occurrence_async,
    complete_occurrence_async,
    complete_occurrence_sync,
    create_occurrence_async,
    create_occurrence_sync,
    generate_occurrences_async,
    generate_occurrences_sync,
    reschedule_occurrence_async,
)

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
ACTOR = 50
START = date(2026, 10, 31)


def _seed(db, seed, *extra):
    db.add_all([seed.yard(), seed.building(), seed.user(ACTOR), seed.elevator(1), *extra])
    db.commit()


def _occ(id, due_on, *, kind="maintenance", state="planned", elevator_id=1, **extra):
    return ElevatorMaintenanceOccurrence(id=id, elevator_id=elevator_id, kind=kind, due_on=due_on,
                                         state=state, **extra)


def _rows(db):
    return db.execute(
        select(ElevatorMaintenanceOccurrence.due_on, ElevatorMaintenanceOccurrence.kind,
               ElevatorMaintenanceOccurrence.state)
        .order_by(ElevatorMaintenanceOccurrence.due_on)
    ).all()


class TestGenerate:
    def test_generates_and_is_idempotent(self, el_db, el_seed):
        _seed(el_db, el_seed, _occ(1, date(2026, 12, 31)), _occ(2, date(2027, 1, 31), state="cancelled"))

        created = generate_occurrences_sync(el_db, 1, kind="maintenance", start=START, every_months=1,
                                            count=4, actor_user_id=ACTOR)
        el_db.commit()

        # 31.10, 30.11, [31.12 уже есть], 31.01 (отменённая не мешает)
        assert [o.due_on for o in created] == [START, date(2026, 11, 30), date(2027, 1, 31)]
        assert all(o.state == "planned" and o.created_by_user_id == ACTOR for o in created)
        again = generate_occurrences_sync(el_db, 1, kind="maintenance", start=START, every_months=1,
                                          count=4, actor_user_id=ACTOR)
        assert again == []
        assert len(_rows(el_db)) == 5

    def test_invalid_kind_and_missing_elevator(self, el_db, el_seed):
        _seed(el_db, el_seed)
        with pytest.raises(ElevatorValidationError):
            generate_occurrences_sync(el_db, 1, kind="repair", start=START, every_months=1, count=1, actor_user_id=ACTOR)
        with pytest.raises(ElevatorNotFoundError):
            generate_occurrences_sync(el_db, 9, kind="maintenance", start=START, every_months=1, count=1, actor_user_id=ACTOR)
        with pytest.raises(ElevatorValidationError):
            generate_occurrences_sync(el_db, 1, kind="maintenance", start=START, every_months=0, count=1, actor_user_id=ACTOR)


class TestCreate:
    def test_create_and_duplicate(self, el_db, el_seed):
        _seed(el_db, el_seed)
        occurrence = create_occurrence_sync(el_db, 1, kind="certification", due_on=START, actor_user_id=ACTOR)
        assert (occurrence.kind, occurrence.state, occurrence.due_on) == ("certification", "planned", START)
        with pytest.raises(ElevatorConflictError):
            create_occurrence_sync(el_db, 1, kind="certification", due_on=START, actor_user_id=ACTOR)
        # другой вид на ту же дату — не дубль
        create_occurrence_sync(el_db, 1, kind="maintenance", due_on=START, actor_user_id=ACTOR)


class TestComplete:
    def test_complete_maintenance_without_event(self, el_db, el_seed):
        _seed(el_db, el_seed, _occ(1, START))
        occurrence = complete_occurrence_sync(el_db, 1, actor_user_id=ACTOR, comment="ок",
                                              request_number="260905-001", now=NOW)
        el_db.commit()

        assert (occurrence.state, occurrence.done_by_user_id, occurrence.comment, occurrence.request_number) == (
            "done", ACTOR, "ок", "260905-001")
        assert occurrence.done_at.replace(tzinfo=timezone.utc) == NOW
        assert el_db.execute(select(ElevatorStatusEvent)).scalars().all() == []
        assert el_db.get(Elevator, 1).version == 1

    def test_done_is_frozen(self, el_db, el_seed):
        _seed(el_db, el_seed, _occ(1, START, state="done"))
        with pytest.raises(ElevatorStateError):
            complete_occurrence_sync(el_db, 1, actor_user_id=ACTOR, comment=None, now=NOW)

    def test_cert_fields_forbidden_for_maintenance(self, el_db, el_seed):
        _seed(el_db, el_seed, _occ(1, START))
        with pytest.raises(ElevatorValidationError):
            complete_occurrence_sync(el_db, 1, actor_user_id=ACTOR, comment=None, now=NOW,
                                     cert_fields={"cert_number": "C-1", "cert_valid_until": date(2027, 1, 1)})

    def test_certification_requires_fields(self, el_db, el_seed):
        _seed(el_db, el_seed, _occ(1, START, kind="certification"))
        with pytest.raises(ElevatorValidationError):
            complete_occurrence_sync(el_db, 1, actor_user_id=ACTOR, comment=None, now=NOW)
        with pytest.raises(ElevatorValidationError):
            complete_occurrence_sync(el_db, 1, actor_user_id=ACTOR, comment=None, now=NOW,
                                     cert_fields={"cert_number": "C-1"})
        assert el_db.get(ElevatorMaintenanceOccurrence, 1).state == "planned"

    def test_certification_updates_passport(self, el_db, el_seed):
        _seed(el_db, el_seed, _occ(1, START, kind="certification"))
        el_db.get(Elevator, 1).cert_reminder_stage = 7
        el_db.commit()
        cert = {"cert_number": "C-2", "cert_valid_until": date(2027, 9, 1), "cert_act_url": "https://x/act.pdf"}

        complete_occurrence_sync(el_db, 1, actor_user_id=ACTOR, comment="акт", now=NOW, cert_fields=cert,
                                 done_at=NOW)
        el_db.commit()

        elevator = el_db.get(Elevator, 1)
        assert (elevator.cert_number, elevator.cert_valid_until, elevator.cert_act_url) == (
            "C-2", date(2027, 9, 1), "https://x/act.pdf")
        assert (elevator.cert_reminder_stage, elevator.version) == (0, 2)
        [event] = el_db.execute(select(ElevatorStatusEvent)).scalars().all()
        assert event.event_kind == "cert_changed"
        assert event.payload["changed"]["cert_valid_until"] == [None, "2027-09-01"]

    def test_naive_done_at_rejected(self, el_db, el_seed):
        _seed(el_db, el_seed, _occ(1, START))
        with pytest.raises(ValueError):
            complete_occurrence_sync(el_db, 1, actor_user_id=ACTOR, comment=None, now=NOW,
                                     done_at=datetime(2026, 9, 1))


class TestAsync:
    def test_generate_reschedule_cancel_complete(self, el_async_factory, el_seed):
        async def run():
            async with el_async_factory() as s:
                s.add_all([el_seed.yard(), el_seed.building(), el_seed.user(ACTOR), el_seed.elevator(1),
                           _occ(1, START), _occ(2, date(2026, 12, 1), state="done")])
                await s.commit()
            async with el_async_factory() as s:
                created = await generate_occurrences_async(
                    s, 1, kind="maintenance", start=START, every_months=1, count=2, actor_user_id=ACTOR)
                assert [o.due_on for o in created] == [date(2026, 11, 30)]
                with pytest.raises(ElevatorConflictError):
                    await create_occurrence_async(s, 1, kind="maintenance", due_on=START, actor_user_id=ACTOR)

                moved = await reschedule_occurrence_async(s, 1, due_on=date(2026, 11, 15), actor_user_id=ACTOR)
                assert (moved.due_on, moved.reminder_stage, moved.overdue_reminded_at) == (
                    date(2026, 11, 15), 0, None)
                with pytest.raises(ElevatorConflictError):
                    await reschedule_occurrence_async(s, 1, due_on=date(2026, 11, 30), actor_user_id=ACTOR)
                with pytest.raises(ElevatorStateError):
                    await reschedule_occurrence_async(s, 2, due_on=date(2026, 11, 1), actor_user_id=ACTOR)
                with pytest.raises(ElevatorNotFoundError):
                    await cancel_occurrence_async(s, 99, actor_user_id=ACTOR)

                cancelled = await cancel_occurrence_async(s, created[0].id, actor_user_id=ACTOR)
                assert cancelled.state == "cancelled"
                with pytest.raises(ElevatorStateError):
                    await cancel_occurrence_async(s, created[0].id, actor_user_id=ACTOR)

                done = await complete_occurrence_async(s, 1, actor_user_id=ACTOR, comment="ок", now=NOW)
                await s.commit()
                return done.state, done.done_by_user_id

        assert asyncio.run(run()) == ("done", ACTOR)

    def test_complete_certification_parity(self, el_db, el_seed, el_async_factory):
        cert = {"cert_number": "C-2", "cert_valid_until": date(2027, 9, 1)}
        _seed(el_db, el_seed, _occ(1, START, kind="certification"))
        complete_occurrence_sync(el_db, 1, actor_user_id=ACTOR, comment="акт", now=NOW, cert_fields=cert)
        el_db.commit()
        sync_elevator = el_db.get(Elevator, 1)
        sync_state = (sync_elevator.cert_number, sync_elevator.cert_valid_until, sync_elevator.version)

        async def run():
            async with el_async_factory() as s:
                s.add_all([el_seed.yard(), el_seed.building(), el_seed.user(ACTOR), el_seed.elevator(1),
                           _occ(1, START, kind="certification")])
                await s.commit()
            async with el_async_factory() as s:
                await complete_occurrence_async(s, 1, actor_user_id=ACTOR, comment="акт", now=NOW, cert_fields=cert)
                await s.commit()
                elevator = await s.get(Elevator, 1)
                events = (await s.execute(select(ElevatorStatusEvent.event_kind))).scalars().all()
                return (elevator.cert_number, elevator.cert_valid_until, elevator.version), events

        async_state, events = asyncio.run(run())
        assert async_state == sync_state == ("C-2", date(2027, 9, 1), 2)
        assert events == ["cert_changed"]
