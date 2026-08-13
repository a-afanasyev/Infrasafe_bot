"""Передача смен из меню «Мои смены»: меню, инициация, мои передачи.

AUD5-ARCH-3 (волна 7): перенос 1:1 из handlers/my_shifts.py.
"""

import logging

from aiogram import F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext

from uk_management_bot.database.session import run_db
from uk_management_bot.keyboards.shift_transfer import (
    shift_selection_keyboard,
    transfers_list_keyboard
)
from uk_management_bot.utils.helpers import get_text

from ._router import router
from ._units import _load_transfer_menu_counts, _load_transferable_shifts, _load_my_transfers

logger = logging.getLogger(__name__)


# ========== ИНТЕГРАЦИЯ С ПЕРЕДАЧЕЙ СМЕН ==========

@router.callback_query(F.data == "shift_transfer_menu")
async def handle_shift_transfer_menu(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработка меню передачи смен (BUG-BOT-006)."""
    try:
        user_lang = language

        counts = await run_db(
            lambda s: _load_transfer_menu_counts(s, callback.from_user.id), db=_db,
        )
        if counts is None:
            await callback.answer(get_text("my_shifts.handlers.user_not_found", language=user_lang), show_alert=True)
            return

        active_shifts_count, transfers_count = counts

        menu_text = get_text("my_shifts.handlers.transfer_menu", language=user_lang).format(
            active_shifts_count=active_shifts_count,
            transfers_count=transfers_count
        )

        # Создаем клавиатуру меню передач
        keyboard = []

        if active_shifts_count:
            keyboard.append([InlineKeyboardButton(
                text=get_text("my_shifts.handlers.btn_transfer_shift", language=user_lang),
                callback_data="initiate_transfer"
            )])

        if transfers_count:
            keyboard.append([InlineKeyboardButton(
                text=get_text("my_shifts.handlers.btn_my_transfers", language=user_lang),
                callback_data="view_my_transfers"
            )])

        # Кнопка назад (убрана по запросу пользователя)

        await callback.message.edit_text(
            menu_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="HTML"
        )

        # BUG-142: снять спиннер на кнопке (как в соседних хендлерах пакета).
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка меню передачи смен: {e}")
        await callback.answer(get_text("my_shifts.handlers.error_loading_menu", language=user_lang), show_alert=True)


@router.callback_query(F.data == "initiate_transfer")
async def handle_initiate_transfer(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Инициация передачи смены через меню 'Мои смены'"""
    try:
        user_lang = language

        active_shifts = await run_db(
            lambda s: _load_transferable_shifts(s, callback.from_user.id), db=_db,
        )
        if active_shifts is None:
            # Пользователь не найден — раньше это давало AttributeError и ту же
            # ветку с error_initiating_transfer; сообщение сохранено.
            await callback.answer(get_text("my_shifts.handlers.error_initiating_transfer", language=user_lang), show_alert=True)
            return

        if not active_shifts:
            await callback.answer(get_text("my_shifts.handlers.no_shifts_to_transfer", language=user_lang), show_alert=True)
            return

        # Показываем список смен для выбора
        select_text = get_text("my_shifts.handlers.select_shift_to_transfer", language=user_lang)

        await callback.message.edit_text(
            select_text,
            reply_markup=shift_selection_keyboard(active_shifts, user_lang)
        )

        # BUG-142: снять спиннер на кнопке (как в соседних хендлерах пакета).
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка инициации передачи: {e}")
        await callback.answer(get_text("my_shifts.handlers.error_initiating_transfer", language=user_lang), show_alert=True)


@router.callback_query(F.data == "view_my_transfers")
async def handle_view_my_transfers(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Просмотр передач пользователя"""
    try:
        user_lang = language

        my_transfers = await run_db(
            lambda s: _load_my_transfers(s, callback.from_user.id), db=_db,
        )
        if my_transfers is None:
            # Пользователь не найден — раньше AttributeError уводил в ту же
            # ветку с error_loading_transfers; сообщение сохранено.
            await callback.answer(get_text("my_shifts.handlers.error_loading_transfers", language=user_lang), show_alert=True)
            return

        if not my_transfers:
            await callback.answer(get_text("my_shifts.handlers.no_transfers", language=user_lang), show_alert=True)
            return

        view_text = get_text("my_shifts.handlers.your_transfers", language=user_lang)

        await callback.message.edit_text(
            view_text,
            reply_markup=transfers_list_keyboard(my_transfers, user_lang)
        )

        # BUG-142: снять спиннер на кнопке (как в соседних хендлерах пакета).
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка просмотра передач: {e}")
        await callback.answer(get_text("my_shifts.handlers.error_loading_transfers", language=user_lang), show_alert=True)
