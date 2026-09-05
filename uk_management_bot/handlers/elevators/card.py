"""Карточка лифта и общие async-хелперы бота лифтёра (Ф5, T10).

Карточка: подпись, статус и с какого времени, доступность 30 дней, ближайший
planned-пункт графика, число открытых заявок; кнопки — статус (только у
введённого лифта), ремонт, ТО (если planned-пункт в ближайшие ``DUE_SOON_DAYS``).

Хелперы ``run_unit``/``edit``/``deny``/``answer_card`` используют остальные
модули пакета. ``run_unit`` принимает ``run_db`` вызывающего модуля — тесты
подменяют его по-модульно (``patch.object(mod, "run_db", ...)``).
"""

from __future__ import annotations

import logging
import re
from typing import Awaitable, Callable, Optional, TypeVar

from aiogram import F
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.exc import SQLAlchemyError

from uk_management_bot.database.session import run_db

from ._keyboards import CARD_PREFIX, card_keyboard
from ._router import router
from ._texts import card_text, deny_text, t
from ._units import OK, CardView, load_card

logger = logging.getLogger(__name__)

T = TypeVar("T")
RunDb = Callable[..., Awaitable[T]]

CARD_PATTERN = rf"^{re.escape(CARD_PREFIX)}(?P<id>\d+)$"
_CARD_RE = re.compile(CARD_PATTERN)


def parse_int(raw: Optional[str]) -> Optional[int]:
    return int(raw) if raw is not None and raw.isdigit() else None


async def run_unit(run: RunDb, unit: Callable, what: str) -> Optional[object]:
    """``run_db`` с единой обработкой сбоя БД: лог и ``None`` (хендлер покажет ошибку)."""
    try:
        return await run(unit)
    except SQLAlchemyError as exc:
        logger.error("Бот лифтёра: %s не выполнен: %s", what, type(exc).__name__, exc_info=True)
        return None


async def answer_quietly(callback: CallbackQuery) -> None:
    try:
        await callback.answer()
    except TelegramAPIError as exc:
        logger.debug("callback.answer лифтёра: %s", type(exc).__name__)


async def edit(callback: CallbackQuery, text: str, markup: Optional[InlineKeyboardMarkup] = None) -> None:
    """Заменить сообщение с кнопками; сбой Telegram — не ошибка операции."""
    try:
        await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except TelegramAPIError as exc:
        # Текст исключения не логируем: рядом с Bot API он может нести URL с токеном.
        logger.warning("Сообщение лифтёра не отредактировано: %s", type(exc).__name__)
    await answer_quietly(callback)


async def deny(callback: CallbackQuery, verdict: str, language: str) -> None:
    """Всплывающий отказ по вердикту юнита (доступ, not_found, ошибка)."""
    await callback.answer(deny_text(verdict, language), show_alert=True)


async def load_card_view(run: RunDb, telegram_id: int, elevator_id: int, language: str) -> CardView:
    view = await run_unit(run, lambda s: load_card(s, telegram_id, elevator_id, language), "карточка лифта")
    return view if view is not None else CardView("error")


async def answer_card(run: RunDb, message: Message, telegram_id: int, elevator_id: int, language: str) -> None:
    """Карточка новым сообщением (после текстового шага FSM или итога операции)."""
    view = await load_card_view(run, telegram_id, elevator_id, language)
    if view.verdict != OK:
        await message.answer(deny_text(view.verdict, language))
        return
    await message.answer(card_text(view, language), reply_markup=card_keyboard(view, language),
                         parse_mode="HTML")


async def edit_card(run: RunDb, callback: CallbackQuery, elevator_id: int, language: str) -> None:
    """Карточка вместо текущего сообщения (навигация по inline-кнопкам)."""
    view = await load_card_view(run, callback.from_user.id, elevator_id, language)
    if view.verdict != OK:
        await deny(callback, view.verdict, language)
        return
    await edit(callback, card_text(view, language), card_keyboard(view, language))


async def cancelled(callback: CallbackQuery, language: str) -> None:
    await edit(callback, t("cancelled", language))


@router.callback_query(F.data.regexp(CARD_PATTERN))
async def handle_card(callback: CallbackQuery, state: FSMContext, language: str = "ru") -> None:
    """``elvm:card:{id}``: карточка лифта; текущий FSM-шаг лифтёра снимается."""
    match = _CARD_RE.match(callback.data or "")
    elevator_id = parse_int(match.group("id")) if match else None
    if elevator_id is None:
        await deny(callback, "error", language)
        return
    await state.clear()
    await edit_card(run_db, callback, elevator_id, language)
