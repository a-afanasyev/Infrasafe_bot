"""FSM-флоу смены статуса заявки: выбор, комментарий, подтверждение, отмена.

AUD5-ARCH-3 (волна 12): перенос 1:1 из handlers/request_status_management.py.
"""

import logging

from aiogram import F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from uk_management_bot.database.session import run_db
from uk_management_bot.database.models.user import User
from uk_management_bot.states.request_status import RequestStatusStates
from uk_management_bot.keyboards.request_status import get_status_selection_keyboard
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.status_display import get_status_display
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_PURCHASE, REQUEST_STATUS_CLARIFICATION, REQUEST_STATUS_EXECUTED
)

from ._router import router
from ._units import _load_status_change_context, _request_exists, _apply_status_change
from .availability import get_comment_prompt
from .confirmation import show_status_confirmation

logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("change_status_"))
async def handle_status_change_start(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Начало процесса изменения статуса заявки"""
    try:
        lang = language
        # Получаем номер заявки
        request_number = callback.data.split("_")[-1]

        user_id = callback.from_user.id
        outcome, current_status, user_roles, available_statuses = await run_db(
            lambda s: _load_status_change_context(s, request_number, user_id), db=_db
        )

        if outcome == "no_request":
            from uk_management_bot.utils.safe_localization import safe_get_text
            await callback.answer(safe_get_text("errors.request_not_found", language=lang), show_alert=True)
            return

        if outcome == "no_user":
            await callback.answer(get_text("request_status_mgmt.handlers.user_not_found", language=lang), show_alert=True)
            return

        if not available_statuses:
            await callback.answer(get_text("request_status_mgmt.handlers.no_available_statuses", language=lang), show_alert=True)
            return

        # Сохраняем данные в состоянии
        await state.update_data(
            request_number=request_number,
            current_status=current_status,
            user_roles=user_roles
        )

        # Показываем выбор нового статуса
        keyboard = get_status_selection_keyboard(available_statuses, lang)

        await callback.message.edit_text(
            get_text("request_status_mgmt.handlers.select_status", language=lang).format(
                current_status=get_status_display(current_status, language=lang)
            ),
            reply_markup=keyboard
        )

        # Переходим в состояние выбора статуса
        await state.set_state(RequestStatusStates.waiting_for_status)

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка начала изменения статуса: {e}")
        await callback.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)

@router.callback_query(F.data.startswith("status_"))
async def handle_status_selection(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработка выбора нового статуса"""
    try:
        lang = language
        # Получаем новый статус из callback data
        new_status = callback.data.split("_", 1)[1]

        # Сохраняем новый статус в состоянии
        await state.update_data(new_status=new_status)

        # Получаем данные заявки
        data = await state.get_data()
        request_number = data.get("request_number")

        # Проверяем существование заявки
        exists = await run_db(lambda s: _request_exists(s, request_number), db=_db)
        if not exists:
            await callback.answer(get_text("request_status_mgmt.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Проверяем, нужен ли комментарий для этого статуса
        requires_comment = new_status in [REQUEST_STATUS_PURCHASE, REQUEST_STATUS_CLARIFICATION, REQUEST_STATUS_EXECUTED]

        if requires_comment:
            # Запрашиваем комментарий
            comment_prompt = get_comment_prompt(new_status, lang)

            await callback.message.edit_text(comment_prompt)

            # Переходим в состояние ввода комментария
            await state.set_state(RequestStatusStates.waiting_for_comment)
        else:
            # Показываем подтверждение без комментария
            await show_status_confirmation(callback, state, new_status, _db=_db)

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка выбора статуса: {e}")
        await callback.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)

@router.message(RequestStatusStates.waiting_for_comment)
async def handle_comment_input(message: Message, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработка ввода комментария для изменения статуса"""
    try:
        lang = language
        # Получаем комментарий
        comment = message.text.strip()

        if not comment:
            await message.answer(get_text("request_status_mgmt.handlers.please_enter_comment", language=lang))
            return

        # Сохраняем комментарий в состоянии
        await state.update_data(comment=comment)

        # Получаем данные из состояния
        data = await state.get_data()
        new_status = data.get("new_status")

        # Показываем подтверждение с комментарием
        await show_status_confirmation(message, state, new_status, comment, _db=_db)

    except Exception as e:
        logger.error(f"Ошибка ввода комментария: {e}")
        await message.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)))

@router.callback_query(F.data == "confirm_status_change")
async def handle_status_confirmation(callback: CallbackQuery, state: FSMContext, language: str = "ru", user: User = None, *, _db=None):
    """Подтверждение изменения статуса"""
    try:
        lang = language
        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")
        current_status = data.get("current_status")
        new_status = data.get("new_status")
        comment = data.get("comment")

        if not request_number or not new_status:
            await callback.answer(get_text("request_status_mgmt.handlers.data_not_found", language=lang), show_alert=True)
            return

        actor_tg = callback.from_user.id
        commenter_id = user.id if user else None
        result = await run_db(
            lambda s: _apply_status_change(
                s, request_number, new_status, actor_tg, current_status, comment, commenter_id
            ),
            db=_db,
        )
        if not result["success"]:
            await callback.message.edit_text(f"❌ {result['message']}")
            await state.clear()
            return

        # Показываем сообщение об успехе
        success_text = get_text("request_status_mgmt.handlers.success", language=lang).format(
            request_number=request_number,
            old_status=get_status_display(current_status, language=lang),
            new_status=get_status_display(new_status, language=lang)
        )

        await callback.message.edit_text(success_text)

        # Очищаем состояние
        await state.clear()

        await callback.answer(get_text("request_status_mgmt.handlers.status_changed_success", language=lang))

    except Exception as e:
        logger.error(f"Ошибка подтверждения изменения статуса: {e}")
        await callback.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)

@router.callback_query(F.data == "cancel_status_change")
async def handle_status_cancellation(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Отмена изменения статуса"""
    try:
        lang = language
        # Очищаем состояние
        await state.clear()

        await callback.message.edit_text(get_text("request_status_mgmt.handlers.status_change_cancelled", language=lang))
        await callback.answer(get_text("request_status_mgmt.handlers.status_change_cancelled", language=lang))

    except Exception as e:
        logger.error(f"Ошибка отмены изменения статуса: {e}")
        await callback.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)
