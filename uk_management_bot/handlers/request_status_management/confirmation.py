"""Показ подтверждения изменения статуса (show_status_confirmation).

AUD5-ARCH-3 (волна 12): перенос 1:1 из handlers/request_status_management.py.
"""

import logging

from aiogram.fsm.context import FSMContext

from uk_management_bot.database.session import run_db
from uk_management_bot.states.request_status import RequestStatusStates
from uk_management_bot.keyboards.request_status import get_status_confirmation_keyboard
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.status_display import get_status_display

from ._units import _load_confirmation_context

logger = logging.getLogger(__name__)


async def show_status_confirmation(callback_or_message, state: FSMContext, new_status: str, comment: str = None, language: str = "ru", *, _db=None):
    """Показ подтверждения изменения статуса"""
    try:
        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")
        current_status = data.get("current_status")

        # Язык: как исторический get_language_from_event — сперва
        # language_code из Telegram, иначе fallback на БД внутри юнита.
        tg_lang = None
        from_user_id = None
        if hasattr(callback_or_message, 'from_user') and callback_or_message.from_user:
            tg_lang = getattr(callback_or_message.from_user, 'language_code', None)
            from_user_id = callback_or_message.from_user.id

        # `not tg_lang` (не `is None`): исторический get_language_from_event
        # уходил в БД-fallback и на пустой строке language_code (LOW ревью).
        found, category, address, db_lang = await run_db(
            lambda s: _load_confirmation_context(
                s, request_number, from_user_id, need_db_lang=(not tg_lang and from_user_id is not None)
            ),
            db=_db,
        )
        if not found:
            lang_fallback = language
            not_found_text = get_text("request_status_mgmt.handlers.request_not_found", language=lang_fallback)
            if hasattr(callback_or_message, 'edit_text'):
                await callback_or_message.answer(not_found_text, show_alert=True)
            else:
                await callback_or_message.answer(not_found_text)
            return

        # Формируем текст подтверждения
        lang = tg_lang or db_lang or "ru"
        confirmation_text = get_text("request_status_mgmt.handlers.confirmation", language=lang).format(
            request_number=request_number,
            current_status=get_status_display(current_status, language=lang),
            new_status=get_status_display(new_status, language=lang),
            category=category,
            address=address
        )

        if comment:
            confirmation_text += get_text("request_status_mgmt.handlers.confirmation_comment", language=lang).format(comment=comment)

        # Показываем клавиатуру подтверждения
        keyboard = get_status_confirmation_keyboard(lang)

        if hasattr(callback_or_message, 'edit_text'):
            await callback_or_message.edit_text(confirmation_text, reply_markup=keyboard)
        else:
            await callback_or_message.answer(confirmation_text, reply_markup=keyboard)

        # Переходим в состояние подтверждения
        await state.set_state(RequestStatusStates.waiting_for_confirmation)

    except Exception as e:
        logger.error(f"Ошибка показа подтверждения: {e}")
        lang_err = language
        err_text = get_text("request_status_mgmt.handlers.error_occurred", language=lang_err).format(error=str(e))
        if hasattr(callback_or_message, 'edit_text'):
            await callback_or_message.answer(err_text, show_alert=True)
        else:
            await callback_or_message.answer(err_text)
