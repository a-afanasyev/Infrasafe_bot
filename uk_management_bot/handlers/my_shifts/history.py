"""История смен и возврат в главное меню.

AUD5-ARCH-3 (волна 7): перенос 1:1 из handlers/my_shifts.py.
"""

import logging

from aiogram import F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from uk_management_bot.database.session import run_db
from uk_management_bot.database.models.user import User
from uk_management_bot.keyboards.my_shifts import get_my_shifts_menu
from uk_management_bot.states.my_shifts import MyShiftsStates
from uk_management_bot.middlewares.auth import require_role
from uk_management_bot.utils.helpers import get_text
# ARCH-116: показ и дневные бакеты — в бизнес-зоне (БД остаётся UTC).
from uk_management_bot.utils.business_time import fmt_day_month, fmt_time

from ._router import router
from ._units import _load_shift_history

logger = logging.getLogger(__name__)


@router.callback_query(F.data == "shift_history")
@require_role(['admin', 'manager', 'executor'])
async def handle_shift_history(callback: CallbackQuery, state: FSMContext, language: str = "ru",
                               roles: list = None, user: User = None, *, _db=None):
    """История смен.

    BUG-BOT-005: разрешён доступ executor + manager + admin. Для executor query
    фильтруется по `Shift.user_id == user.id` (внутренний DB id, не telegram_id).
    Manager/admin — видит все смены.
    """
    try:
        lang = language
        user_db_id = user.id if user is not None else None
        is_privileged = bool(roles) and any(r in ('admin', 'manager') for r in roles)

        user_found, history_shifts = await run_db(
            lambda s: _load_shift_history(s, callback.from_user.id, user_db_id, is_privileged), db=_db,
        )
        if not user_found:
            await callback.answer(get_text("my_shifts.handlers.error_occurred", language=lang), show_alert=True)
            return

        if not history_shifts:
            await callback.message.edit_text(
                get_text("my_shifts.handlers.no_shift_history", language=lang),
                reply_markup=get_my_shifts_menu(lang),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        # Статистика
        completed_shifts = [s for s in history_shifts if s.status == 'completed']
        cancelled_shifts = [s for s in history_shifts if s.status == 'cancelled']

        total_hours = 0
        total_requests = 0

        for shift in completed_shifts:
            if shift.start_time and shift.end_time:
                hours = (shift.end_time - shift.start_time).total_seconds() / 3600
                total_hours += hours

            if shift.completed_requests:
                total_requests += shift.completed_requests

        # Формируем текст истории
        history_text = get_text("my_shifts.handlers.shift_history_header", language=lang).format(
            completed_count=len(completed_shifts),
            cancelled_count=len(cancelled_shifts),
            total_hours=f"{total_hours:.1f}",
            total_requests=total_requests
        ) + "\n"

        for shift in history_shifts[:10]:  # Показываем последние 10
            # FS-07: ad-hoc смена без planned_* → эффективное время.
            eff_start = shift.planned_start_time or shift.start_time
            shift_date = fmt_day_month(eff_start)
            start_time = fmt_time(eff_start)

            status_emoji = {
                'completed': '✅',
                'cancelled': '❌'
            }.get(shift.status, '⚪')

            duration = ""
            if shift.start_time and shift.end_time:
                hours = (shift.end_time - shift.start_time).total_seconds() / 3600
                duration = f" ({hours:.1f}ч)"

            requests = ""
            if shift.completed_requests:
                requests = f" • {shift.completed_requests} {get_text('my_shifts.handlers.requests_word', language=lang)}"

            history_text += f"{status_emoji} {shift_date} {start_time}{duration}{requests}\n"

        if len(history_shifts) > 10:
            history_text += f"\n... {get_text('my_shifts.handlers.and_more_shifts', language=lang).format(count=len(history_shifts) - 10)}"

        await callback.message.edit_text(
            history_text,
            reply_markup=get_my_shifts_menu(lang),
            parse_mode="HTML"
        )

        await state.set_state(MyShiftsStates.main_menu)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка просмотра истории смен: {e}")
        await callback.answer(get_text("my_shifts.handlers.error_occurred", language=language), show_alert=True)


@router.callback_query(F.data == "back_to_my_shifts")
async def handle_back_to_my_shifts(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Возврат к главному меню моих смен"""
    try:
        lang = language

        await callback.message.edit_text(
            get_text("my_shifts.handlers.main_menu", language=lang),
            reply_markup=get_my_shifts_menu(lang),
            parse_mode="HTML"
        )

        await state.set_state(MyShiftsStates.main_menu)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка возврата к моим сменам: {e}")
        await callback.answer(get_text("my_shifts.handlers.error_occurred", language=language), show_alert=True)
