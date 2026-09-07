"""Сортировка и честный размер выборки в списке сотрудников.

До этой работы у списка не было ``ORDER BY`` вовсе — база вправе вернуть
строки в любом порядке, и постраничная выдача могла терять и дублировать
сотрудников. Плюс ``total`` не считался, и плитка «Всего» на странице
показывала длину среза вместо числа сотрудников.

ФИО вводится одной строкой: первое слово → `first_name`, остаток →
`last_name` (`utils/person_name`). Различающее слово кладём в `first_name` —
сортировка идёт в порядке показанной строки.
"""
from datetime import datetime, timezone

import pytest

from uk_management_bot.api.shifts import service
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User


async def _user(db, tg, *, name, verification="verified"):
    user = User(
        telegram_id=tg, username=f"u{tg}", first_name=name, last_name="Пётр",
        roles='["executor"]', active_role="executor", status="approved",
        verification_status=verification,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _list(db, **kw):
    kw.setdefault("specialization", None)
    kw.setdefault("has_active_shift", None)
    kw.setdefault("search", None)
    kw.setdefault("role", None)
    kw.setdefault("verification_status", None)
    kw.setdefault("limit", 50)
    kw.setdefault("offset", 0)
    return await service.list_employees(db, **kw)


async def _names(db, **kw) -> list[str]:
    users, _, _ = await _list(db, **kw)
    return [u.first_name for u in users]


@pytest.mark.asyncio
async def test_default_order_follows_the_displayed_name(db_session):
    await _user(db_session, 4003, name="Волков")
    await _user(db_session, 4001, name="Алиев")
    await _user(db_session, 4002, name="Баров")

    assert await _names(db_session) == ["Алиев", "Баров", "Волков"]


@pytest.mark.asyncio
async def test_sort_by_name_reverses(db_session):
    await _user(db_session, 4011, name="Алиев")
    await _user(db_session, 4012, name="Волков")

    assert await _names(db_session, sort="name", order="desc") == ["Волков", "Алиев"]


@pytest.mark.asyncio
async def test_sort_by_verification_puts_unchecked_first(db_session):
    await _user(db_session, 4021, name="Проверенный", verification="verified")
    await _user(db_session, 4022, name="Ждёт", verification="requested")

    assert await _names(db_session, sort="verification") == ["Ждёт", "Проверенный"]


@pytest.mark.asyncio
async def test_sort_by_shift_puts_working_first(db_session):
    """Прямой сценарий менеджера: «кто сейчас на смене»."""
    on_shift = await _user(db_session, 4051, name="Насмене")
    await _user(db_session, 4052, name="Отдыхает")
    db_session.add(Shift(
        user_id=on_shift.id, status="active", shift_type="regular",
        start_time=datetime(2026, 9, 7, 8, 0, tzinfo=timezone.utc),
    ))
    await db_session.commit()

    assert await _names(db_session, sort="shift") == ["Насмене", "Отдыхает"]
    assert await _names(db_session, sort="shift", order="desc") == ["Отдыхает", "Насмене"]


@pytest.mark.asyncio
async def test_total_counts_whole_selection_not_the_page(db_session):
    for i in range(5):
        await _user(db_session, 4030 + i, name=f"Сотрудник{i}")

    users, _, total = await _list(db_session, limit=2)
    assert len(users) == 2 and total == 5


@pytest.mark.asyncio
async def test_total_is_honest_in_the_python_filtered_branch(db_session):
    """Фильтр по специализации режется в Python — счётчик обязан считать там же."""
    for i in range(3):
        user = await _user(db_session, 4060 + i, name=f"Лифтёр{i}")
        user.specialization = "elevator"
    await db_session.commit()

    users, _, total = await _list(db_session, for_category="elevator", limit=2)
    assert len(users) == 2 and total == 3


@pytest.mark.asyncio
async def test_pages_do_not_overlap_or_lose_rows(db_session):
    for i in range(5):
        await _user(db_session, 4040 + i, name=f"Фамилия{i}")

    first = await _names(db_session, limit=2, offset=0)
    second = await _names(db_session, limit=2, offset=2)
    third = await _names(db_session, limit=2, offset=4)
    assert first + second + third == [f"Фамилия{i}" for i in range(5)]
