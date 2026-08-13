"""Просмотр смен: текущие, недельное расписание, детали смены.

AUD5-ARCH-3 (волна 7): перенос 1:1 из handlers/my_shifts.py.
"""

import logging

from datetime import timedelta

from aiogram import F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from uk_management_bot.database.session import run_db
from uk_management_bot.database.models.user import User
from uk_management_bot.keyboards.my_shifts import (
    get_my_shifts_menu,
    get_shift_list_keyboard,
    get_shift_actions_keyboard
)
from uk_management_bot.states.my_shifts import MyShiftsStates
from uk_management_bot.middlewares.auth import require_role
from uk_management_bot.utils.helpers import get_text
# ARCH-116: показ и дневные бакеты — в бизнес-зоне (БД остаётся UTC).
from uk_management_bot.utils.business_time import (
    business_date_of,
    business_today,
    fmt_date,
    fmt_day_month,
    fmt_time,
)

from ._router import router
from ._units import _load_current_shifts, _load_week_shifts, _load_shift_details

logger = logging.getLogger(__name__)


@router.callback_query(F.data == "view_current_shifts")
@require_role(['executor'])
async def handle_current_shifts(callback: CallbackQuery, state: FSMContext, language: str = "ru",
                                user: User = None, roles: list = None, *, _db=None):
    """Просмотр текущих смен."""
    try:
        lang = language
        user_db_id = user.id if user is not None else None

        user_found, today, current_shifts = await run_db(
            lambda s: _load_current_shifts(s, callback.from_user.id, user_db_id), db=_db,
        )
        if not user_found:
            await callback.answer(get_text("my_shifts.handlers.error_occurred", language=lang), show_alert=True)
            return

        if not current_shifts:
            await callback.message.edit_text(
                get_text("my_shifts.handlers.no_current_shifts", language=lang),
                reply_markup=get_my_shifts_menu(lang),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        # Формируем список смен (today — из юнита, тот же день, что окно запроса)
        shifts_text = f"📅 <b>{get_text('my_shifts.handlers.your_current_shifts', language=lang)}</b>\n\n"

        for shift in current_shifts:
            # FS-06: ad-hoc смена не имеет planned_*; берём эффективное время.
            eff_start = shift.planned_start_time or shift.start_time
            eff_end = shift.planned_end_time or shift.end_time
            shift_date = business_date_of(eff_start)
            # BUG-142: метка — от фактической даты смены, а не от позиции в окне
            # (образец — handle_shift_details ниже).
            is_today = shift_date == today
            is_tomorrow = shift_date == today + timedelta(days=1)
            date_prefix = f"🔥 {get_text('my_shifts.handlers.today', language=lang)}" if is_today else f"📅 {get_text('my_shifts.handlers.tomorrow', language=lang)}" if is_tomorrow else f"📅 {fmt_date(shift_date)}"

            start_time = fmt_time(eff_start)
            end_time = fmt_time(eff_end) if eff_end else "?"

            status_emoji = {
                'planned': '⏱️',
                'active': '🔴',
                'completed': '✅'
            }.get(shift.status, '⚪')

            specializations = ""
            if shift.specialization_focus:
                specializations = f"🔧 {', '.join(shift.specialization_focus[:2])}"
                if len(shift.specialization_focus) > 2:
                    specializations += f" (+{len(shift.specialization_focus)-2})"

            geographic_zone = ""
            if shift.geographic_zone:
                geographic_zone = f"🗺️ {shift.geographic_zone}"

            shifts_text += (
                f"{status_emoji} <b>{date_prefix}</b>\n"
                f"⏰ {start_time} - {end_time}\n"
            )

            if specializations:
                shifts_text += f"{specializations}\n"
            if geographic_zone:
                shifts_text += f"{geographic_zone}\n"

            # Информация о заявках
            if shift.max_requests:
                current_requests = shift.current_request_count or 0
                shifts_text += f"📋 {get_text('my_shifts.handlers.requests_label', language=lang)}: {current_requests}/{shift.max_requests}\n"

            shifts_text += "\n"

        await callback.message.edit_text(
            shifts_text,
            reply_markup=get_shift_list_keyboard(current_shifts, lang),
            parse_mode="HTML"
        )

        await state.set_state(MyShiftsStates.viewing_shifts)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка просмотра текущих смен: {e}")
        await callback.answer(get_text("my_shifts.handlers.error_occurred", language=language), show_alert=True)


@router.callback_query(F.data == "view_week_schedule")
@require_role(['admin', 'manager', 'executor'])
async def handle_week_schedule(callback: CallbackQuery, state: FSMContext, language: str = "ru",
                               roles: list = None, user: User = None, *, _db=None):
    """Просмотр расписания на неделю.

    BUG-BOT-005: разрешён доступ executor + manager + admin. Для executor query
    фильтруется по его собственному `Shift.user_id`. Manager/admin — видит все смены.
    """
    try:
        lang = language
        user_db_id = user.id if user is not None else None
        is_privileged = bool(roles) and any(r in ('admin', 'manager') for r in roles)

        user_found, today, week_shifts = await run_db(
            lambda s: _load_week_shifts(s, callback.from_user.id, user_db_id, is_privileged), db=_db,
        )
        if not user_found:
            await callback.answer(get_text("my_shifts.handlers.error_occurred", language=lang), show_alert=True)
            return

        # today — из юнита: заголовок периода совпадает с окном запроса.
        start_of_week = today - timedelta(days=today.weekday())  # Понедельник
        end_of_week = start_of_week + timedelta(days=6)  # Воскресенье

        # Группируем по дням недели
        days_of_week = [
            get_text("my_shifts.handlers.monday", language=lang),
            get_text("my_shifts.handlers.tuesday", language=lang),
            get_text("my_shifts.handlers.wednesday", language=lang),
            get_text("my_shifts.handlers.thursday", language=lang),
            get_text("my_shifts.handlers.friday", language=lang),
            get_text("my_shifts.handlers.saturday", language=lang),
            get_text("my_shifts.handlers.sunday", language=lang),
        ]
        week_schedule = {day: [] for day in days_of_week}

        for shift in week_shifts:
            # ARCH-116: день недели — по бизнес-дате, иначе смена после местной
            # полуночи попадала в предыдущий день.
            day_name = days_of_week[business_date_of(shift.planned_start_time).weekday()]
            week_schedule[day_name].append(shift)

        # Формируем текст расписания
        schedule_text = (
            f"📆 <b>{get_text('my_shifts.handlers.week_schedule', language=lang)}</b>\n"
            f"<b>{get_text('my_shifts.handlers.period', language=lang)}:</b> {fmt_day_month(start_of_week)} - {fmt_date(end_of_week)}\n\n"
        )

        total_shifts = len(week_shifts)
        total_hours = 0

        for day_name, day_shifts in week_schedule.items():
            day_date = start_of_week + timedelta(days=days_of_week.index(day_name))
            is_today = day_date == today
            day_prefix = "🔥" if is_today else "📅"

            if day_shifts:
                schedule_text += f"{day_prefix} <b>{day_name}</b> ({fmt_day_month(day_date)})\n"

                for shift in day_shifts:
                    start_time = fmt_time(shift.planned_start_time)
                    end_time = fmt_time(shift.planned_end_time) if shift.planned_end_time else "?"

                    status_emoji = {
                        'planned': '⏱️',
                        'active': '🔴',
                        'completed': '✅'
                    }.get(shift.status, '⚪')

                    duration = ""
                    if shift.planned_start_time and shift.planned_end_time:
                        hours = (shift.planned_end_time - shift.planned_start_time).total_seconds() / 3600
                        total_hours += hours
                        duration = f" ({hours:.0f}ч)"

                    schedule_text += f"  {status_emoji} {start_time}-{end_time}{duration}\n"

                schedule_text += "\n"
            else:
                schedule_text += f"📅 <b>{day_name}</b> ({fmt_day_month(day_date)}): {get_text('my_shifts.handlers.day_off', language=lang)}\n\n"

        # Итоговая статистика
        schedule_text += (
            f"📊 <b>{get_text('my_shifts.handlers.total', language=lang)}:</b>\n"
            f"• {get_text('my_shifts.handlers.shifts_count', language=lang)}: {total_shifts}\n"
            f"• {get_text('my_shifts.handlers.hours_count', language=lang)}: {total_hours:.1f}\n"
        )

        await callback.message.edit_text(
            schedule_text,
            reply_markup=get_my_shifts_menu(lang),
            parse_mode="HTML"
        )

        await state.set_state(MyShiftsStates.main_menu)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка просмотра недельного расписания: {e}")
        await callback.answer(get_text("my_shifts.handlers.error_occurred", language=language), show_alert=True)


@router.callback_query(F.data.startswith("shift_details:"))
@require_role(['executor'])
async def handle_shift_details(callback: CallbackQuery, state: FSMContext, language: str = "ru",
                               user: User = None, roles: list = None, *, _db=None):
    """Подробная информация о смене.

    BUG-BOT-007: Shift.user_id — FK на users.id (внутренний DB id), а не
    telegram_id. Без user/roles в сигнатуре aiogram DI не передавал roles, и
    require_role отклонял исполнителя на ЕГО ЖЕ смене («нет прав доступа»).
    """
    try:
        shift_id = int(callback.data.split(':')[1])
        lang = language
        user_db_id = user.id if user is not None else None

        user_found, shift = await run_db(
            lambda s: _load_shift_details(s, callback.from_user.id, user_db_id, shift_id), db=_db,
        )
        if not user_found:
            await callback.answer(get_text("my_shifts.handlers.error_occurred", language=lang), show_alert=True)
            return
        if not shift:
            await callback.answer(get_text("my_shifts.handlers.shift_not_found", language=language), show_alert=True)
            return

        # Формируем подробную информацию
        # FS-06: ad-hoc смена без planned_* (достижима из «Текущие смены» →
        # shift_details) → эффективное время, иначе planned_start_time.date() крах.
        eff_start = shift.planned_start_time or shift.start_time
        eff_end = shift.planned_end_time or shift.end_time
        shift_date = business_date_of(eff_start)
        today = business_today()
        is_today = shift_date == today
        is_tomorrow = shift_date == today + timedelta(days=1)

        date_text = f"🔥 {get_text('my_shifts.handlers.today', language=lang)}" if is_today else f"📅 {get_text('my_shifts.handlers.tomorrow', language=lang)}" if is_tomorrow else fmt_date(shift_date)

        start_time = fmt_time(eff_start)
        end_time = fmt_time(eff_end) if eff_end else "?"

        status_text = {
            'planned': f"⏱️ {get_text('my_shifts.handlers.status_planned', language=lang)}",
            'active': f"🔴 {get_text('my_shifts.handlers.status_active', language=lang)}",
            'completed': f"✅ {get_text('my_shifts.handlers.status_completed', language=lang)}",
            'cancelled': f"❌ {get_text('my_shifts.handlers.status_cancelled', language=lang)}"
        }.get(shift.status, f"⚪ {get_text('my_shifts.handlers.status_unknown', language=lang)}")

        details_text = (
            f"📋 <b>{get_text('my_shifts.handlers.shift_details', language=lang)}</b>\n\n"
            f"<b>{get_text('my_shifts.handlers.date_label', language=lang)}:</b> {date_text}\n"
            f"<b>{get_text('my_shifts.handlers.time_label', language=lang)}:</b> {start_time} - {end_time}\n"
            f"<b>{get_text('my_shifts.handlers.status_label', language=lang)}:</b> {status_text}\n\n"
        )

        # Длительность
        if shift.planned_start_time and shift.planned_end_time:
            duration = (shift.planned_end_time - shift.planned_start_time).total_seconds() / 3600
            details_text += f"<b>{get_text('my_shifts.handlers.duration_label', language=lang)}:</b> {duration:.1f} {get_text('my_shifts.handlers.hours_word', language=lang)}\n"

        # Специализации
        if shift.specialization_focus:
            specializations = ', '.join(shift.specialization_focus)
            details_text += f"<b>{get_text('my_shifts.handlers.specializations_label', language=lang)}:</b> {specializations}\n"

        # Географическая зона
        if shift.geographic_zone:
            details_text += f"<b>{get_text('my_shifts.handlers.zone_label', language=lang)}:</b> {shift.geographic_zone}\n"

        # Области покрытия
        if shift.coverage_areas:
            coverage = ', '.join(shift.coverage_areas)
            details_text += f"<b>{get_text('my_shifts.handlers.areas_label', language=lang)}:</b> {coverage}\n"

        details_text += "\n"

        # Заявки
        current_requests = shift.current_request_count or 0
        max_requests = shift.max_requests or 0

        if max_requests > 0:
            details_text += f"<b>📋 {get_text('my_shifts.handlers.requests_label', language=lang)}:</b> {current_requests}/{max_requests}\n"

            if current_requests > 0:
                progress = (current_requests / max_requests) * 100
                progress_bar = "🟩" * int(progress // 20) + "⬜" * (5 - int(progress // 20))
                details_text += f"{get_text('my_shifts.handlers.workload', language=lang)}: {progress_bar} {progress:.0f}%\n"

        # Статистика (если есть)
        if shift.completed_requests:
            details_text += f"<b>{get_text('my_shifts.handlers.completed_requests', language=lang)}:</b> {shift.completed_requests}\n"

        if shift.average_completion_time:
            avg_time = shift.average_completion_time
            details_text += f"<b>{get_text('my_shifts.handlers.average_time', language=lang)}:</b> {avg_time:.1f} {get_text('my_shifts.handlers.minutes_word', language=lang)}\n"

        if shift.efficiency_score:
            score = shift.efficiency_score
            details_text += f"<b>{get_text('my_shifts.handlers.efficiency', language=lang)}:</b> {score:.1f}%\n"

        # Заметки
        if shift.notes:
            details_text += f"\n<b>{get_text('my_shifts.handlers.notes_label', language=lang)}:</b>\n{shift.notes}"

        await callback.message.edit_text(
            details_text,
            reply_markup=get_shift_actions_keyboard(shift, lang),
            parse_mode="HTML"
        )

        await state.update_data(current_shift_id=shift_id)
        await state.set_state(MyShiftsStates.viewing_shift_details)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка просмотра деталей смены: {e}")
        await callback.answer(get_text("my_shifts.handlers.error_occurred", language=language), show_alert=True)
