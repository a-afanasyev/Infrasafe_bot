"""Главное меню «Мои смены»: /my_shifts и reply-кнопка.

AUD5-ARCH-3 (волна 7): перенос 1:1 из handlers/my_shifts.py.
"""

import logging

from aiogram import F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from uk_management_bot.keyboards.my_shifts import get_my_shifts_menu
from uk_management_bot.states.my_shifts import MyShiftsStates
from uk_management_bot.utils.helpers import get_text

from ._router import router
from ._units import MY_SHIFTS_TEXTS

logger = logging.getLogger(__name__)


# ==========================================================================
# Handlers: только Telegram-IO и рендеринг по DTO.
# ==========================================================================

@router.message(Command("my_shifts"))
async def cmd_my_shifts(message: Message, state: FSMContext, language: str = "ru"):
    """Главное меню моих смен (БД не нужна — раньше сессия открывалась зря)."""
    try:
        lang = language

        await message.answer(
            get_text("my_shifts.handlers.main_menu", language=lang),
            reply_markup=get_my_shifts_menu(lang),
            parse_mode="HTML"
        )

        await state.set_state(MyShiftsStates.main_menu)

    except Exception as e:
        logger.error(f"Ошибка команды /my_shifts: {e}")
        await message.answer(get_text("my_shifts.handlers.error_loading", language=language))


@router.message(F.text.in_(MY_SHIFTS_TEXTS))
async def handle_my_shifts_button(message: Message, state: FSMContext, language: str = "ru"):
    """Обработчик кнопки 'Мои смены'"""
    await cmd_my_shifts(message, state, language=language)
