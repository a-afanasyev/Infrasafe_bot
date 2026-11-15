"""Отключения в боте: только напоминание автору и кнопка «✅ Включили».

Объявляют отключение в TWA; правила покрыты tests/services/test_notices_outages.py.
Здесь — что клиентскому callback_data не доверяют и что кнопки объявления в меню нет.
"""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import uk_management_bot.database.models  # noqa: F401
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.notice import Notice
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.database.session import Base
from uk_management_bot.handlers import outages as bot
from uk_management_bot.keyboards.base import get_main_keyboard_for_role
from uk_management_bot.services.notices import outage_reminders, outages
from uk_management_bot.services.notices.outages import OpenOutage
from uk_management_bot.utils.datetime_utils import utc_now

PLUMBER_TG, OFF_TG = 7001, 7002


@pytest_asyncio.fixture
async def factory(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as db:
        db.add(Yard(id=1, name="Северный"))
        db.add(Building(id=12, address="Садовая, 14", yard_id=1))
        db.add_all([User(id=1, telegram_id=PLUMBER_TG, roles='["executor"]', status="approved", specialization="plumber"),
                    User(id=2, telegram_id=OFF_TG, roles='["executor"]', status="approved", specialization="plumber")])
        db.add(Shift(user_id=1, status="active", start_time=utc_now() - timedelta(hours=1)))
        await db.commit()
        await outages.announce(db, await db.get(User, 1), resource="water", building_ids=[12], duration="2h")
    monkeypatch.setattr(bot, "_session", maker)
    yield maker
    await engine.dispose()


def _cb(data: str, tg: int = PLUMBER_TG):
    return SimpleNamespace(data=data, from_user=SimpleNamespace(id=tg), answer=AsyncMock(),
                           message=SimpleNamespace(edit_text=AsyncMock()))


async def _notices(factory) -> list[Notice]:
    async with factory() as db:
        return list((await db.execute(select(Notice).order_by(Notice.id))).scalars().all())


@pytest.mark.asyncio
async def test_close_button_closes_only_for_author_or_plumber_on_shift(factory):
    [notice] = await _notices(factory)

    foreign = _cb(f"outg:close:{notice.id}", OFF_TG)  # сантехник без смены, не автор
    await bot.handle_close(foreign)
    assert foreign.answer.call_args.kwargs.get("show_alert") and not foreign.message.edit_text.called
    assert (await _notices(factory))[0].status == "published"

    missing = _cb("outg:close:999")  # id из callback_data шлёт клиент
    await bot.handle_close(missing)
    assert missing.answer.call_args.kwargs.get("show_alert")

    cb = _cb(f"outg:close:{notice.id}")
    await bot.handle_close(cb)
    closed, restored = await _notices(factory)
    assert closed.status == "closed" and restored.title_ru == "Воду включили — Садовая, 14"
    assert cb.message.edit_text.called

    again = _cb(f"outg:close:{notice.id}")  # повторное нажатие второго сообщения жителям не даёт
    await bot.handle_close(again)
    assert again.answer.call_args.kwargs.get("show_alert") and len(await _notices(factory)) == 2


@pytest.mark.asyncio
async def test_reminder_carries_close_button_and_never_raises():
    sent = AsyncMock(side_effect=[None, RuntimeError("bot token in url")])
    items = [OpenOutage(5, 111, "ru", "Отключена вода — <Садовая>", ""), OpenOutage(6, 222, "uz", "ru", "Suv o'chirildi")]
    assert await outage_reminders.send_reminders(SimpleNamespace(send_message=sent), items, "remind_overdue") == 1
    first = sent.call_args_list[0]
    assert "&lt;Садовая&gt;" in first.args[1]
    assert [b.callback_data for row in first.kwargs["reply_markup"].inline_keyboard for b in row] == ["outg:close:5"]
    assert "Suv o'chirildi" in sent.call_args_list[1].args[1]


def test_bot_menu_has_no_outage_button():
    """Объявление — только в TWA (решение владельца 2026-11-15)."""
    menu = get_main_keyboard_for_role("executor", ["executor"], "approved")
    assert not [b.text for row in menu.keyboard for b in row if "🚰" in b.text]
