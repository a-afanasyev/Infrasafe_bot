"""Сообщения бота по уборке: утро, напоминание перед концом дня, итог дня, фото в чате."""
from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.cleaning import (
    CleaningAssignment,
    CleaningPlanVersion,
    CleaningRules,
    CleaningTask,
)
from uk_management_bot.services.cleaning import days, notify
from uk_management_bot.utils.business_time import business_wall_clock

TUE = date(2026, 11, 17)
MANAGER, CLEANER, CLEANER2 = 1, 11, 12


def _at(hour: int, minute: int = 0, day: date = TUE):
    return business_wall_clock(day, hour, minute)


@pytest.fixture
async def db(el_async_factory, el_seed):
    async with el_async_factory() as session:
        staff = dict(roles='["executor"]', specialization="cleaning")
        session.add_all([
            el_seed.yard(), el_seed.building(1, entrance_count=2), el_seed.user(MANAGER, roles='["manager"]'),
            el_seed.user(CLEANER, language="uz", **staff), el_seed.user(CLEANER2, **staff),
            CleaningRules(id=1, data={"day_end_time": "20:00"}, created_at=_at(10, day=TUE - timedelta(days=2))),
            CleaningPlanVersion(building_id=1, valid_from=date(2026, 11, 1), extra_points=[], floor_count=9,
                                entrance_count=2, items=[{"work_kind": "wet", "weekdays": [1]}]),
            CleaningAssignment(building_id=1, entrance=1, user_id=CLEANER, valid_from=date(2026, 11, 1)),
            CleaningAssignment(building_id=1, entrance=2, user_id=CLEANER2, valid_from=date(2026, 11, 1)),
        ])
        await session.flush()
        await days.ensure_tasks(session, TUE, now=_at(0, 10))
        await session.commit()
        yield session


async def _collect(db, now):
    messages = await notify.collect(db, now=now)
    await db.commit()
    return messages


async def test_morning_message_goes_once_to_each_cleaner_in_her_language(db):
    assert await _collect(db, _at(7, 30)) == []           # до 08:00 молчим
    first = await _collect(db, _at(8, 5))
    assert sorted(m.telegram_id for m in first) == [1011, 1012]
    uz = next(m for m in first if m.telegram_id == 1011)
    assert "1" in uz.text and uz.webapp is True and uz.text != next(m for m in first if m.telegram_id == 1012).text
    assert await _collect(db, _at(8, 15)) == []           # повторно не шлём


async def test_reminder_before_day_end_only_for_unfinished(db):
    await _collect(db, _at(8, 5))
    done = (await db.execute(select(CleaningTask).where(CleaningTask.entrance == 2))).scalar_one()
    done.status = "accepted"
    await db.flush()
    assert await _collect(db, _at(16, 50)) == []          # конец дня 20:00, напоминание за 3 часа
    (reminder,) = await _collect(db, _at(17, 5))
    assert reminder.telegram_id == 1011 and "20:00" in reminder.text
    assert await _collect(db, _at(17, 20)) == []


async def test_day_summary_goes_to_managers_once_after_closing(db):
    await _collect(db, _at(8, 5))
    await _collect(db, _at(17, 5))
    await days.close_days(db, now=_at(20, 6))
    (summary,) = await _collect(db, _at(20, 7))
    assert summary.telegram_id == 1001 and summary.webapp is False
    assert "17.11.2026" in summary.text and "2" in summary.text
    assert await _collect(db, _at(20, 30)) == []


async def test_send_is_best_effort(db):
    bot = AsyncMock()
    bot.send_message.side_effect = [RuntimeError("blocked"), None]
    sent = await notify.send(bot, await _collect(db, _at(8, 5)))
    assert sent == 1 and bot.send_message.await_count == 2


# ── фото, присланное в чат ──────────────────────────────────────────────────

async def _stray(user, monkeypatch, enabled=True):
    from uk_management_bot.handlers import onboarding

    monkeypatch.setattr(settings, "CLEANING_ENABLED", enabled)
    message = AsyncMock()
    await onboarding.catch_stray_document(message, language="ru", user=user)
    return message.answer.await_args


async def test_photo_in_chat_from_cleaner_gets_cleaning_hint(db, el_seed, monkeypatch):
    cleaner = el_seed.user(11, roles='["executor"]', specialization="cleaning")
    resident = el_seed.user(21)
    hint = (await _stray(cleaner, monkeypatch)).args[0]
    assert hint == notify.photo_in_chat_text("ru")
    assert (await _stray(resident, monkeypatch)).args[0] != hint          # жителю — прежняя подсказка
    assert (await _stray(cleaner, monkeypatch, enabled=False)).args[0] != hint  # модуль выключен — как раньше
    assert (await _stray(None, monkeypatch)).args[0] != hint
