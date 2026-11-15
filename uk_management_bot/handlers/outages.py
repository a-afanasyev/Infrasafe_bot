"""«✅ Включили» в боте — кнопка под напоминанием автору незакрытого отключения.

Объявляет отключение сантехник только в TWA (обычный и простой режим — решение
владельца 2026-11-15); в боте кнопки объявления нет. Бот лишь напоминает
автору (конец смены, истёкший срок — ``services/notices/outage_reminders``) и
принимает ответ. Правила — в общем сервисе ``services/notices/outages``.

Данные callback шлёт клиент: id отключения и право закрыть сверяет сервис.
"""
from __future__ import annotations

import logging
import re

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery
from sqlalchemy import select

from uk_management_bot.database.models.user import User
from uk_management_bot.handlers._role_gate import ActionGate
from uk_management_bot.services.notices import outages
from uk_management_bot.services.notices.outage_reminders import CLOSE_PREFIX
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)

_CLOSE_RE = re.compile(r"^" + re.escape(CLOSE_PREFIX) + r"(?P<id>\d{1,9})$")
_REFUSAL_KEYS = {"not_open": "err_not_open", "not_found": "err_not_open", "not_yours": "err_not_yours"}

router = Router(name="outages")
router.callback_query.filter(ActionGate("outages.announce"), F.data.startswith(CLOSE_PREFIX))


def _session():
    """Async-сессия бота; тесты подменяют функцию своей фабрикой."""
    from uk_management_bot.database.session import AsyncSessionLocal

    return AsyncSessionLocal()


def t(key: str, language: str) -> str:
    return get_text(f"outages.{key}", language=language)


@router.callback_query(F.data.regexp(_CLOSE_RE))
async def handle_close(callback: CallbackQuery, language: str = "ru") -> None:
    notice_id = int(_CLOSE_RE.match(callback.data).group("id"))
    try:
        async with _session() as db:
            user = (await db.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalar_one()
            await outages.close(db, user, notice_id)
    except outages.OutageRefused as e:
        await callback.answer(t(_REFUSAL_KEYS.get(e.code, "err_generic"), language), show_alert=True)
        return
    except Exception:
        logger.exception("outages: не удалось закрыть отключение %s", notice_id)
        await callback.answer(t("err_generic", language), show_alert=True)
        return
    try:
        await callback.message.edit_text(t("closed", language))
    except TelegramBadRequest:  # сообщение устарело — отключение всё равно закрыто
        pass
    await callback.answer()
