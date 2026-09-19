"""AUD8-CODE-01: сбои уведомлений о старте/завершении смены не глушатся молча.

Три `except Exception: pass` в handlers/shifts.py прятали и падение билдера
сообщения (db-фаза), и падение отправки (async-фаза): исполнитель и канал не
получали уведомления, в логах — пусто (в отличие от симметричного end-пути,
который логировал). Пользовательский ответ при этом остаётся штатным.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message, User as TgUser

LOGGER = "uk_management_bot.handlers.shifts"


def _make_message(user_id: int = 555) -> MagicMock:
    u = MagicMock(spec=TgUser)
    u.id = user_id
    msg = MagicMock(spec=Message)
    msg.from_user = u
    msg.text = ""
    msg.answer = AsyncMock()
    msg.bot = MagicMock()
    return msg


def _make_shift() -> MagicMock:
    shift = MagicMock()
    shift.id = 1
    shift.user_id = 10
    shift.status = "active"
    shift.start_time = datetime(2026, 9, 19, 9, 0, tzinfo=timezone.utc)
    shift.end_time = None
    shift.specialization_focus = []
    return shift


def _make_db_user() -> MagicMock:
    user = MagicMock()
    user.id = 10
    user.telegram_id = 555
    user.status = "approved"
    user.roles = '["executor"]'
    user.active_role = "executor"
    return user


def _patches(**extra):
    base = {
        "get_user_language": patch(f"{LOGGER}.get_user_language", return_value="ru"),
        "keyboard": patch(f"{LOGGER}.get_shifts_main_keyboard", return_value=MagicMock()),
        "send_to_user": patch(f"{LOGGER}.send_to_user", new_callable=AsyncMock),
        "send_to_channel": patch(f"{LOGGER}.send_to_channel", new_callable=AsyncMock),
    }
    base.update(extra)
    return base


@pytest.mark.asyncio
async def test_builder_failure_is_logged_and_user_still_confirmed(caplog) -> None:
    from uk_management_bot.handlers.shifts import start_shift

    msg = _make_message()
    with patch(f"{LOGGER}.ShiftService") as MockService, patch(
        f"{LOGGER}.build_shift_started_message", side_effect=RuntimeError("builder boom")
    ), _patches()["get_user_language"], _patches()["keyboard"], _patches()["send_to_user"] as stu, _patches()["send_to_channel"]:
        svc = MockService.return_value
        svc.start_shift.return_value = {"success": True, "shift": _make_shift()}
        svc._get_user_by_tg.return_value = _make_db_user()
        with caplog.at_level(logging.WARNING, logger=LOGGER):
            await start_shift(msg, _db=MagicMock())

    msg.answer.assert_called()  # пользователь получил подтверждение
    stu.assert_not_called()  # отправлять нечего
    records = [r for r in caplog.records if r.name == LOGGER and r.levelno >= logging.WARNING]
    assert records, "падение билдера уведомления не залогировано"
    assert any("builder boom" in (r.exc_text or "") or "builder boom" in r.getMessage() for r in records)


@pytest.mark.asyncio
async def test_send_failure_is_logged(caplog) -> None:
    from uk_management_bot.handlers.shifts import start_shift

    msg = _make_message()
    with patch(f"{LOGGER}.ShiftService") as MockService, patch(
        f"{LOGGER}.build_shift_started_message", return_value="text"
    ), _patches()["get_user_language"], _patches()["keyboard"], patch(
        f"{LOGGER}.send_to_user", new_callable=AsyncMock, side_effect=RuntimeError("net down")
    ), _patches()["send_to_channel"]:
        svc = MockService.return_value
        svc.start_shift.return_value = {"success": True, "shift": _make_shift()}
        svc._get_user_by_tg.return_value = _make_db_user()
        with caplog.at_level(logging.WARNING, logger=LOGGER):
            await start_shift(msg, _db=MagicMock())

    msg.answer.assert_called()
    records = [r for r in caplog.records if r.name == LOGGER and r.levelno >= logging.ERROR]
    assert records and any("net down" in (r.exc_text or "") or "net down" in r.getMessage() for r in records)


def test_no_bare_except_pass_around_shift_notifications() -> None:
    """Ратчет: в handlers/shifts.py не осталось `except Exception:\\n pass`."""
    import inspect

    from uk_management_bot.handlers import shifts

    src = inspect.getsource(shifts)
    assert "except Exception:\n        pass" not in src and "except Exception:\n            pass" not in src
