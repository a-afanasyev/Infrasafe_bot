"""Сортировка списка жителей — по всей выборке, а не по загруженной странице.

Раздел постраничный (25 строк), поэтому упорядочивать в браузере нельзя:
«первый по алфавиту» на второй странице начинался бы с «А» заново.
"""
import pytest

from uk_management_bot.database.models.user import User
from uk_management_bot.services.residents import queries


async def _resident(db, tg, *, last_name, verification="verified", status="approved"):
    db.add(User(
        telegram_id=tg, username=f"r{tg}", first_name="И", last_name=last_name,
        roles='["applicant"]', active_role="applicant", status=status,
        verification_status=verification,
    ))
    await db.commit()


async def _names(db, **kw) -> list[str]:
    users, _ = await queries.list_residents(db, **kw)
    return [u.last_name for u in users]


@pytest.mark.asyncio
async def test_default_order_keeps_newest_first(db_session):
    await _resident(db_session, 5001, last_name="Первый")
    await _resident(db_session, 5002, last_name="Второй")

    # Порядок раздела не менялся: created_at DESC, id DESC.
    assert await _names(db_session) == ["Второй", "Первый"]


@pytest.mark.asyncio
async def test_sort_by_surname_both_ways(db_session):
    await _resident(db_session, 5011, last_name="Волков")
    await _resident(db_session, 5012, last_name="Алиев")

    assert await _names(db_session, sort="name") == ["Алиев", "Волков"]
    assert await _names(db_session, sort="name", order="desc") == ["Волков", "Алиев"]


@pytest.mark.asyncio
async def test_sort_by_verification_puts_requested_first(db_session):
    await _resident(db_session, 5021, last_name="Проверен", verification="verified")
    await _resident(db_session, 5022, last_name="Запрошен", verification="requested")

    assert await _names(db_session, sort="verification") == ["Запрошен", "Проверен"]


@pytest.mark.asyncio
async def test_sort_applies_before_paging(db_session):
    for i, name in enumerate(["Волков", "Алиев", "Баров"]):
        await _resident(db_session, 5030 + i, last_name=name)

    # Страница — срез уже отсортированной выборки, а не отсортированный срез.
    assert await _names(db_session, sort="name", limit=1) == ["Алиев"]
    assert await _names(db_session, sort="name", limit=1, offset=2) == ["Волков"]


@pytest.mark.asyncio
async def test_unknown_sort_falls_back_to_default_order(db_session):
    """Домен не падает от чужого значения — его отбивает Literal в роутере."""
    await _resident(db_session, 5041, last_name="Первый")
    await _resident(db_session, 5042, last_name="Второй")

    assert await _names(db_session, sort="выдумка") == ["Второй", "Первый"]
