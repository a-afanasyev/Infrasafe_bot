"""`residents_of_entrance_*`: адресаты жительских уведомлений по подъезду (sqlite)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from uk_management_bot.services.elevator_service import (
    Recipient,
    residents_of_entrance_async,
    residents_of_entrance_sync,
)

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)


def _objects(seed):
    """Дом 1: кв.1/2 в подъезде 1, кв.3 в подъезде 2, кв.4 без подъезда, кв.5 неактивна."""
    return [
        seed.yard(),
        seed.building(),
        seed.apartment(1, entrance=1),
        seed.apartment(2, entrance=1),
        seed.apartment(3, entrance=2),
        seed.apartment(4, entrance=None),
        seed.apartment(5, entrance=1, is_active=False),
        # 10 — одобрен в двух квартирах подъезда 1 (DISTINCT)
        seed.user(10, language="uz"),
        seed.belonging(10, 1),
        seed.belonging(10, 2),
        # 11 — только pending
        seed.user(11),
        seed.belonging(11, 1, status="pending"),
        # 12 — подъезд 2
        seed.user(12),
        seed.belonging(12, 3),
        # 13 — квартира без подъезда
        seed.user(13),
        seed.belonging(13, 4),
        # 14 — заблокировал бота
        seed.user(14, bot_blocked_at=NOW),
        seed.belonging(14, 1),
        # 15 — удалён
        seed.user(15, deleted_at=NOW),
        seed.belonging(15, 1),
        # 16 — заблокирован УК
        seed.user(16, status="blocked"),
        seed.belonging(16, 1),
        # 17 — неактивная квартира
        seed.user(17),
        seed.belonging(17, 5),
        # 18 — одобрен в подъезде 1, обычный житель
        seed.user(18, telegram_id=555),
        seed.belonging(18, 2),
    ]


def test_sync_filters_and_distinct(el_db, el_seed):
    el_db.add_all(_objects(el_seed))
    el_db.commit()

    result = residents_of_entrance_sync(el_db, 1, 1)

    assert result == [
        Recipient(user_id=10, telegram_id=1010, language="uz"),
        Recipient(user_id=18, telegram_id=555, language="ru"),
    ]


def test_sync_other_entrance(el_db, el_seed):
    el_db.add_all(_objects(el_seed))
    el_db.commit()

    assert [r.user_id for r in residents_of_entrance_sync(el_db, 1, 2)] == [12]
    assert residents_of_entrance_sync(el_db, 1, 3) == []
    assert residents_of_entrance_sync(el_db, 99, 1) == []


async def test_async_parity(el_async_factory, el_seed):
    async with el_async_factory() as s:
        s.add_all(_objects(el_seed))
        await s.commit()
    async with el_async_factory() as s:
        result = await residents_of_entrance_async(s, 1, 1)
    assert [r.user_id for r in result] == [10, 18]
