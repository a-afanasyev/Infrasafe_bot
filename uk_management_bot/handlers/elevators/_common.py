"""Инфраструктура хендлеров лифтёра (Ф5, T10): юниты, ответы, отказы, карточка.

``run_unit`` принимает ``run_db`` модуля-вызывающего — тесты подменяют его
по-модульно (``patch.object(mod, "run_db", ...)``). Здесь же два сквозных
message-хендлера текстовых шагов FSM (``states.elevators.ALL_STATES``):

* ``handle_exit_button`` — ПЕРВЫЙ хендлер пакета: reply-кнопки отмены/меню
  («❌ Отмена», «🔙 Назад», кнопки главного меню executor) во время текстового
  шага снимают состояние, иначе роутер (он стоит до ``base_router``) записал бы
  «❌ Отменить» причиной или описанием;
* ``handle_non_text`` — ПОСЛЕДНИЙ (регистрируется в ``__init__`` после всех
  модулей): не текст / текст не по кнопке на шаге — подсказка, состояние
  сохраняется.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Optional, TypeVar

from aiogram import F
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from uk_management_bot.database.session import run_db
from uk_management_bot.states.elevators import ALL_STATES, ElevatorStates
from uk_management_bot.utils import button_texts as bt

from ._keyboards import card_keyboard
from ._router import router
from ._texts import card_text, deny_text, t
from ._units import OK, CardView, load_card

logger = logging.getLogger(__name__)

T = TypeVar("T")
# ``run_db`` вызывающего модуля: (unit) -> awaitable результата юнита.
RunDb = Callable[[Callable[[Session], T]], Awaitable[T]]

# Reply-кнопки, которые на текстовом шаге означают «выйти», а не «это мой текст»:
# отмена/назад всех клавиатур бота + кнопки главного меню executor.
EXIT_TEXTS: frozenset[str] = frozenset(
    bt.get_cancel_texts() + bt.get_back_texts() + bt.get_onboarding_cancel_texts()
    + bt.get_admin_back_to_menu_texts() + bt.get_profile_texts() + bt.get_help_texts()
    + bt.get_feedback_texts() + bt.get_shift_texts() + bt.get_my_shifts_texts()
    + bt.get_active_requests_texts() + bt.get_archive_texts() + bt.get_group_pool_texts()
    + bt.get_switch_role_texts() + bt.get_admin_panel_texts() + bt.get_acceptance_texts()
    + bt.get_my_requests_texts() + bt.get_access_control_texts()
)


def parse_int(raw: Optional[str]) -> Optional[int]:
    return int(raw) if raw is not None and raw.isdigit() else None


async def run_unit(run: RunDb, unit: Callable[[Session], T], what: str) -> Optional[T]:
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


async def cancelled(callback: CallbackQuery, language: str) -> None:
    await edit(callback, t("cancelled", language))


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


@router.message(StateFilter(*ALL_STATES), F.text.in_(EXIT_TEXTS))
async def handle_exit_button(message: Message, state: FSMContext, language: str = "ru") -> None:
    """Reply-кнопка отмены/меню на текстовом шаге: снять состояние, вернуть карточку."""
    data = await state.get_data()
    await state.clear()
    await message.answer(t("cancelled", language))
    elevator_id = data.get("elvm_elevator_id")
    if elevator_id is not None:
        await answer_card(run_db, message, message.from_user.id, int(elevator_id), language)


async def handle_non_text(message: Message, state: FSMContext, language: str = "ru") -> None:
    """Не по кнопке / не текст на шаге лифтёра — подсказка, состояние сохраняется.

    Регистрируется ПОСЛЕДНИМ в ``__init__`` (после текстовых хендлеров шагов).
    """
    if await state.get_state() == ElevatorStates.repair_urgency.state:
        await message.answer(t("pick_urgency", language))
        return
    await message.answer(t("text_only", language))
