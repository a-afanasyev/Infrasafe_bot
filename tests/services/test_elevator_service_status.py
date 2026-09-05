"""`set_status_sync/async`: смена статуса лифта, журнал, сообщения жителям (sqlite)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from uk_management_bot.database.models.elevator import Elevator, ElevatorStatusEvent
from uk_management_bot.services.elevator_service import (
    DEFAULT_ELEVATORS_CONFIG,
    ElevatorNotFoundError,
    ElevatorStateError,
    ElevatorValidationError,
    StatusChange,
    set_status_async,
    set_status_sync,
)

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
SINCE = NOW - timedelta(days=3)
ACTOR = 50


def _seed(db, seed, **elevator_kwargs):
    db.add_all([
        seed.yard(),
        seed.building(address="ул. Мира, д. 5"),
        seed.apartment(1, entrance=1),
        seed.apartment(2, entrance=2),
        seed.user(10, language="ru"),
        seed.belonging(10, 1),
        seed.user(11, language="uz"),
        seed.belonging(11, 1),
        seed.user(12),
        seed.belonging(12, 2),
        seed.user(ACTOR, roles='["manager"]'),
        seed.elevator(1, entrance=1, number=1, status_since=SINCE, downtime_reminded_at=SINCE,
                      **{"status": "working", **elevator_kwargs}),
    ])
    db.commit()


def _events(db, elevator_id=1):
    return db.execute(
        select(ElevatorStatusEvent).where(ElevatorStatusEvent.elevator_id == elevator_id)
    ).scalars().all()


class TestNoOp:
    def test_same_status_writes_nothing(self, el_db, el_seed):
        _seed(el_db, el_seed)

        result = set_status_sync(el_db, 1, "working", actor_user_id=ACTOR, source="manual", now=NOW)
        el_db.commit()

        assert result == StatusChange(
            changed=False, elevator_id=1, old_status="working", new_status="working",
            status_since=result.status_since,
        )
        assert result.resident_messages == ()
        assert _events(el_db) == []
        row = el_db.get(Elevator, 1)
        assert row.status_since.replace(tzinfo=timezone.utc) == SINCE
        assert row.version == 1


class TestChange:
    def test_change_writes_one_event_and_resets_downtime(self, el_db, el_seed):
        _seed(el_db, el_seed)

        result = set_status_sync(
            el_db, 1, "not_working", actor_user_id=ACTOR, source="request_hint",
            reason="стоит", request_number="260905-001", now=NOW,
        )
        el_db.commit()

        assert (result.changed, result.old_status, result.new_status) == (True, "working", "not_working")
        assert result.status_since == NOW
        assert result.resident_messages == ()  # not_working жителям не шлём
        row = el_db.get(Elevator, 1)
        assert row.current_status == "not_working"
        assert row.status_since.replace(tzinfo=timezone.utc) == NOW
        assert row.downtime_reminded_at is None
        assert row.version == 2
        [event] = _events(el_db)
        assert (event.event_kind, event.old_status, event.new_status) == ("status_changed", "working", "not_working")
        assert (event.actor_user_id, event.source, event.request_number, event.reason) == (
            ACTOR, "request_hint", "260905-001", "стоит")
        assert event.occurred_at.replace(tzinfo=timezone.utc) == NOW

    def test_status_is_normalized(self, el_db, el_seed):
        _seed(el_db, el_seed)
        result = set_status_sync(el_db, 1, " Under_Repair ", actor_user_id=ACTOR, source="manual", now=NOW)
        assert result.new_status == "under_repair"

    def test_default_now_is_utc_aware(self, el_db, el_seed):
        _seed(el_db, el_seed)
        result = set_status_sync(el_db, 1, "maintenance", actor_user_id=ACTOR, source="manual")
        assert result.status_since.tzinfo is not None


class TestGuards:
    def test_unknown_status(self, el_db, el_seed):
        _seed(el_db, el_seed)
        with pytest.raises(ElevatorValidationError):
            set_status_sync(el_db, 1, "broken", actor_user_id=ACTOR, source="manual", now=NOW)

    def test_unknown_source(self, el_db, el_seed):
        _seed(el_db, el_seed)
        with pytest.raises(ElevatorValidationError):
            set_status_sync(el_db, 1, "working", actor_user_id=ACTOR, source="telepathy", now=NOW)

    def test_not_commissioned(self, el_db, el_seed):
        _seed(el_db, el_seed, commissioned=False)
        with pytest.raises(ElevatorStateError):
            set_status_sync(el_db, 1, "working", actor_user_id=ACTOR, source="manual", now=NOW)
        assert _events(el_db) == []

    def test_archived_is_not_found(self, el_db, el_seed):
        _seed(el_db, el_seed, archived_at=NOW)
        with pytest.raises(ElevatorNotFoundError):
            set_status_sync(el_db, 1, "working", actor_user_id=ACTOR, source="manual", now=NOW)

    def test_missing_is_not_found(self, el_db, el_seed):
        _seed(el_db, el_seed)
        with pytest.raises(ElevatorNotFoundError):
            set_status_sync(el_db, 77, "working", actor_user_id=ACTOR, source="manual", now=NOW)

    def test_naive_now_rejected(self, el_db, el_seed):
        _seed(el_db, el_seed)
        with pytest.raises(ValueError):
            set_status_sync(el_db, 1, "working", actor_user_id=ACTOR, source="manual",
                            now=datetime(2026, 9, 5, 12, 0))


class TestResidentMessages:
    def test_under_repair_notifies_entrance_in_user_language(self, el_db, el_seed):
        _seed(el_db, el_seed)

        result = set_status_sync(el_db, 1, "under_repair", actor_user_id=ACTOR, source="manual", now=NOW)

        by_tg = {m.telegram_id: m.text for m in result.resident_messages}
        assert set(by_tg) == {1010, 1011}  # подъезд 1; житель подъезда 2 не получает
        assert "ул. Мира, д. 5" in by_tg[1010]
        assert by_tg[1010] != by_tg[1011]  # ru vs uz
        assert "elevators.notify" not in by_tg[1010]  # ключ локали найден
        assert result.staff_messages == ()

    @pytest.mark.parametrize("target", ["maintenance", "working"])
    def test_maintenance_and_back_in_service_notify(self, el_db, el_seed, target):
        _seed(el_db, el_seed, status="not_working")
        result = set_status_sync(el_db, 1, target, actor_user_id=ACTOR, source="manual", now=NOW)
        assert len(result.resident_messages) == 2

    def test_config_can_disable(self, el_db, el_seed):
        _seed(el_db, el_seed)
        config = {
            **DEFAULT_ELEVATORS_CONFIG,
            "resident_notifications": {"repair_started": False, "maintenance_started": True,
                                       "back_in_service": True},
        }
        result = set_status_sync(el_db, 1, "under_repair", actor_user_id=ACTOR, source="manual",
                                 now=NOW, config=config)
        assert result.resident_messages == ()

    def test_address_is_html_escaped(self, el_db, el_seed):
        el_db.add_all([
            el_seed.yard(), el_seed.building(address="ул. <Мира> & Труда, д. 5"),
            el_seed.apartment(1, entrance=1), el_seed.user(10), el_seed.belonging(10, 1),
            el_seed.elevator(1, status="working"),
        ])
        el_db.commit()
        result = set_status_sync(el_db, 1, "under_repair", actor_user_id=ACTOR, source="manual", now=NOW)
        [message] = result.resident_messages
        assert "&lt;Мира&gt; &amp; Труда" in message.text
        assert "<Мира>" not in message.text


class TestAsyncParity:
    def test_async_mirrors_sync(self, el_db, el_seed, el_async_factory):
        _seed(el_db, el_seed)
        sync_result = set_status_sync(
            el_db, 1, "under_repair", actor_user_id=ACTOR, source="manual", now=NOW, reason="r")
        el_db.commit()

        async def run():
            async with el_async_factory() as s:
                s.add_all([
                    el_seed.yard(), el_seed.building(address="ул. Мира, д. 5"),
                    el_seed.apartment(1, entrance=1), el_seed.apartment(2, entrance=2),
                    el_seed.user(10, language="ru"), el_seed.belonging(10, 1),
                    el_seed.user(11, language="uz"), el_seed.belonging(11, 1),
                    el_seed.user(12), el_seed.belonging(12, 2),
                    el_seed.user(ACTOR, roles='["manager"]'),
                    el_seed.elevator(1, status="working", status_since=SINCE, downtime_reminded_at=SINCE),
                ])
                await s.commit()
            async with el_async_factory() as s:
                result = await set_status_async(
                    s, 1, "under_repair", actor_user_id=ACTOR, source="manual", now=NOW, reason="r")
                await s.commit()
                events = (await s.execute(select(ElevatorStatusEvent))).scalars().all()
                row = await s.get(Elevator, 1)
                return result, events, (row.current_status, row.version, row.downtime_reminded_at)

        async_result, events, row_state = asyncio.run(run())
        assert async_result == sync_result
        assert len(events) == 1 and events[0].new_status == "under_repair"
        assert row_state == ("under_repair", 2, None)

    def test_async_not_found(self, el_async_factory):
        async def run():
            async with el_async_factory() as s:
                with pytest.raises(ElevatorNotFoundError):
                    await set_status_async(s, 1, "working", actor_user_id=ACTOR, source="manual", now=NOW)

        asyncio.run(run())
