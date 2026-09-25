"""Жизненный цикл смены: начать / завершить.

AUD5-ARCH-3 (волна 7): перенос 1:1 из handlers/my_shifts.py.
"""

import logging

from aiogram import F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from uk_management_bot.database.session import run_db
from uk_management_bot.database.models.user import User
from uk_management_bot.keyboards.my_shifts import (
    get_my_shifts_menu,
    get_shift_actions_keyboard
)
from uk_management_bot.states.my_shifts import MyShiftsStates
from uk_management_bot.middlewares.auth import require_role
from uk_management_bot.services.executor_done_prompt import remind_after_shift_end
from uk_management_bot.services.shift_lifecycle import send_shift_notify
from uk_management_bot.utils.helpers import get_text
# ARCH-116: показ и дневные бакеты — в бизнес-зоне (БД остаётся UTC).
from uk_management_bot.utils.business_time import fmt_time

from ._router import router
from ._units import _start_shift, _end_shift

logger = logging.getLogger(__name__)


async def _send_notify(callback: CallbackQuery, payload) -> None:
    """A9-P2-32: уведомление исполнителю и в ops-канал — как у кнопки «Смена»
    и TWA, после коммита, вне db-фазы. Сбой сети не превращает уже выполненный
    старт/стоп в «ошибку» для пользователя."""
    try:
        await send_shift_notify(callback.bot, payload)
    except Exception:
        logger.error("my_shifts: ошибка отправки уведомлений о смене", exc_info=True)


@router.callback_query(F.data == "start_shift")
@require_role(['executor'])
async def handle_start_shift(callback: CallbackQuery, state: FSMContext, language: str = "ru",
                             user: User = None, roles: list = None, *, _db=None):
    """Начать смену"""
    try:
        lang = language
        data = await state.get_data()
        shift_id = data.get('current_shift_id')

        if not shift_id:
            await callback.answer(get_text("my_shifts.handlers.shift_not_selected", language=lang), show_alert=True)
            return

        user_db_id = user.id if user is not None else None
        user_found, shift, notify = await run_db(
            lambda s: _start_shift(s, callback.from_user.id, user_db_id, shift_id), db=_db,
        )
        if not user_found:
            await callback.answer(get_text("my_shifts.handlers.error_occurred", language=lang), show_alert=True)
            return
        if not shift:
            await callback.answer(get_text("my_shifts.handlers.shift_not_found_or_started", language=lang), show_alert=True)
            return

        await callback.message.edit_text(
            get_text("my_shifts.handlers.shift_started", language=lang).format(
                start_time=fmt_time(shift.start_time)
            ),
            reply_markup=get_shift_actions_keyboard(shift, lang),
            parse_mode="HTML"
        )

        await callback.answer(get_text("my_shifts.handlers.shift_started_toast", language=lang))
        await _send_notify(callback, notify)

    except Exception as e:
        logger.error(f"Ошибка начала смены: {e}")
        await callback.answer(get_text("my_shifts.handlers.error_occurred", language=language), show_alert=True)


@router.callback_query(F.data == "end_shift")
@require_role(['executor'])
async def handle_end_shift(callback: CallbackQuery, state: FSMContext, language: str = "ru",
                           user: User = None, roles: list = None, *, _db=None):
    """Завершить смену"""
    try:
        lang = language
        data = await state.get_data()
        shift_id = data.get('current_shift_id')

        if not shift_id:
            await callback.answer(get_text("my_shifts.handlers.shift_not_selected", language=lang), show_alert=True)
            return

        user_db_id = user.id if user is not None else None
        user_found, summary = await run_db(
            lambda s: _end_shift(s, callback.from_user.id, user_db_id, shift_id), db=_db,
        )
        if not user_found:
            await callback.answer(get_text("my_shifts.handlers.error_occurred", language=lang), show_alert=True)
            return
        if summary is None:
            await callback.answer(get_text("my_shifts.handlers.shift_not_found_or_inactive", language=lang), show_alert=True)
            return

        # Формируем итоги смены
        summary_text = get_text("my_shifts.handlers.shift_ended_summary", language=lang).format(
            end_time=fmt_time(summary["end_time"]),
            actual_duration=f"{summary['actual_duration']:.1f}",
            request_count=summary["request_count"]
        )

        await callback.message.edit_text(
            summary_text,
            reply_markup=get_my_shifts_menu(lang),
            parse_mode="HTML"
        )

        await state.set_state(MyShiftsStates.main_menu)
        await callback.answer(get_text("my_shifts.handlers.shift_ended_toast", language=lang))
        await _send_notify(callback, summary.get("notify"))
        # Фаза 4: незакрытые заявки — напоминание в личку (best-effort, не бросает).
        await remind_after_shift_end(callback.bot, summary.get("user_id"), _db=_db)

    except Exception as e:
        logger.error(f"Ошибка завершения смены: {e}")
        await callback.answer(get_text("my_shifts.handlers.error_occurred", language=language), show_alert=True)
