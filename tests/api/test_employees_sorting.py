"""Сортировка и честный размер выборки в списке сотрудников.

До этой работы у списка не было ``ORDER BY`` вовсе — база вправе вернуть
строки в любом порядке, и постраничная выдача могла терять и дублировать
сотрудников. Плюс ``total`` не считался, и плитка «Всего» на странице
показывала длину среза вместо числа сотрудников.
"""
import pytest

from uk_management_bot.api.shifts import service
from uk_management_bot.database.models.user import User


async def _user(db, tg, *, last_name, verification="verified"):
    user = User(
        telegram_id=tg, username=f"u{tg}", first_name="И", last_name=last_name,
        roles='["executor"]', active_role="executor", status="approved",
        verification_status=verification,
    )
    db.add(user)
    await db.commit()
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
    return [u.last_name for u in users]


@pytest.mark.asyncio
async def test_default_order_is_by_surname(db_session):
    await _user(db_session, 4003, last_name="Волков")
    await _user(db_session, 4001, last_name="Алиев")
    await _user(db_session, 4002, last_name="Баров")

    assert await _names(db_session) == ["Алиев", "Баров", "Волков"]


@pytest.mark.asyncio
async def test_sort_by_name_reverses(db_session):
    await _user(db_session, 4011, last_name="Алиев")
    await _user(db_session, 4012, last_name="Волков")

    assert await _names(db_session, sort="name", order="desc") == ["Волков", "Алиев"]


@pytest.mark.asyncio
async def test_sort_by_verification_puts_unchecked_first(db_session):
    await _user(db_session, 4021, last_name="Проверенный", verification="verified")
    await _user(db_session, 4022, last_name="Ждёт", verification="pending")

    assert await _names(db_session, sort="verification") == ["Ждёт", "Проверенный"]


@pytest.mark.asyncio
async def test_total_counts_whole_selection_not_the_page(db_session):
    for i in range(5):
        await _user(db_session, 4030 + i, last_name=f"Сотрудник{i}")

    users, _, total = await _list(db_session, limit=2)
    assert len(users) == 2 and total == 5


@pytest.mark.asyncio
async def test_pages_do_not_overlap_or_lose_rows(db_session):
    for i in range(5):
        await _user(db_session, 4040 + i, last_name=f"Фамилия{i}")

    first = await _names(db_session, limit=2, offset=0)
    second = await _names(db_session, limit=2, offset=2)
    third = await _names(db_session, limit=2, offset=4)
    assert first + second + third == [f"Фамилия{i}" for i in range(5)]
