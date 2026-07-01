import logging
from datetime import date, timedelta

from aiogram import F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from uk_management_bot.services.shift_management_service import ShiftManagementService
from uk_management_bot.keyboards.shift_management import (
    get_main_shift_menu,
    get_schedule_view_keyboard,
)
from uk_management_bot.states.shift_management import ShiftManagementStates
from uk_management_bot.middlewares.auth import require_role
from uk_management_bot.utils.helpers import get_user_language, get_text

from ._router import router
from .shared import _db_scope, _format_end_label

logger = logging.getLogger(__name__)


@router.callback_query(F.data == "view_schedule")
@require_role(['admin', 'manager'])
async def handle_view_schedule(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Просмотр расписания смен"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
        
            # Показываем расписание на сегодня
            today = date.today()

            await callback.message.edit_text(
                get_text("shift_management.schedule_view_title", language=lang,
                        date=today.strftime('%d.%m.%Y')),
                reply_markup=get_schedule_view_keyboard(today, lang),
                parse_mode="HTML"
            )

            await state.set_state(ShiftManagementStates.viewing_schedule)
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка просмотра расписания: {e}")
        await callback.answer(get_text("shift_management.schedule_error", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("schedule_date:"))
@require_role(['admin', 'manager'])
async def handle_schedule_date(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Обработка выбора даты в расписании"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
        
            # Извлекаем дату из callback_data
            date_str = callback.data.split(":", 1)[1]
            selected_date = date.fromisoformat(date_str)
        
            service = ShiftManagementService(db)
            # Получаем смены на выбранную дату
            shifts = service.get_shifts_for_date(selected_date)
        
            # Формируем сообщение
            response = get_text("shift_management.schedule_date_title", language=lang,
                              date=selected_date.strftime('%d.%m.%Y'))

            # REG-02: кнопки прямого менеджерского переназначения смен.
            reassign_rows = []
            if shifts:
                response += get_text("shift_management.shifts_found", language=lang, count=len(shifts))
                for shift in shifts:
                    # Получаем имя исполнителя
                    executor_name = get_text("shift_management.not_assigned", language=lang)
                    if shift.user_id:
                        user = service.get_user(shift.user_id)
                        if user:
                            executor_name = f"{user.first_name} {user.last_name or ''}".strip()

                    # Получаем название шаблона
                    template_name = get_text("shift_management.no_template", language=lang)
                    if shift.shift_template_id:
                        template = service.get_template(shift.shift_template_id)
                        if template:
                            template_name = template.name

                    start_time = shift.planned_start_time.strftime('%H:%M') if shift.planned_start_time else "??:??"
                    end_time = _format_end_label(shift.planned_start_time, shift.planned_end_time) if shift.planned_end_time else "??:??"

                    status_emoji = "🟢" if shift.status == "active" else "🟡" if shift.status == "planned" else "🔴"

                    response += (
                        f"{status_emoji} <b>{start_time}-{end_time}</b>\n"
                        f"   👤 {executor_name}\n"
                        f"   📋 {template_name}\n"
                        f"   📊 {shift.status.title()}\n\n"
                    )

                    if shift.user_id and shift.status in ("active", "planned"):
                        reassign_rows.append([InlineKeyboardButton(
                            text=get_text("shift_management.keyboards.reassign_shift", language=lang, time=start_time),
                            callback_data=f"reassign_shift_pick:{shift.id}"
                        )])
            else:
                response += get_text("shift_management.no_shifts_on_date", language=lang)

            response += get_text("shift_management.select_another_date", language=lang)

            base_kb = get_schedule_view_keyboard(selected_date, lang)
            markup = InlineKeyboardMarkup(inline_keyboard=reassign_rows + base_kb.inline_keyboard)
            await callback.message.edit_text(
                response,
                reply_markup=markup,
                parse_mode="HTML"
            )

            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка выбора даты расписания: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.schedule_load_error", language=lang), show_alert=True)


def _reassign_error_text(error: str, lang: str) -> str:
    """Локализованный текст ошибки reassign (ключи в shift_transfer.errors.*)."""
    full_key = f"shift_transfer.errors.{error}"
    text = get_text(full_key, language=lang)
    if text == full_key:
        return get_text("shift_transfer.handlers.error_generic", language=lang)
    return text


@router.callback_query(F.data.startswith("reassign_shift_pick:"))
@require_role(['admin', 'manager'])
async def handle_reassign_shift_pick(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """REG-02: менеджер выбирает нового исполнителя для прямого переназначения смены.

    Тонкий слой: весь data-access — в ShiftTransferService (ARCH-01 — без прямого
    ORM в handlers/shift_management.py).
    """
    lang = "ru"
    try:
        shift_id = int(callback.data.split(":")[1])
        from uk_management_bot.keyboards.shift_transfer import executor_selection_keyboard
        from uk_management_bot.services.shift_transfer_service import ShiftTransferService

        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
            service = ShiftTransferService(db)
            shift = service.get_shift(shift_id)
            if not shift:
                await callback.answer(_reassign_error_text("shift_not_found", lang), show_alert=True)
                return

            eligible = service.list_eligible_executors(exclude_user_id=shift.user_id, shift=shift)
            if not eligible:
                await callback.answer(get_text("shift_management.reassign_no_executors", language=lang), show_alert=True)
                return

            start_time = shift.planned_start_time.strftime('%H:%M') if shift.planned_start_time else "??:??"
            await callback.message.edit_text(
                get_text("shift_management.reassign_pick_title", language=lang, time=start_time),
                reply_markup=executor_selection_keyboard(
                    shift_id, eligible, lang, mode="reassign", back_callback="back_to_planning"
                )
            )

    except Exception as e:
        logger.error(f"Ошибка выбора исполнителя для reassign: {e}")
        await callback.answer(get_text("shift_management.schedule_error", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("reassign_executor:"))
@require_role(['admin', 'manager'])
async def handle_reassign_executor(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """REG-02: прямой менеджерский reassign смены (без согласия получателя).

    Commit + рассылка — в сервисном слое/после него (ARCH-01 — без прямого ORM
    в хендлере: `manager_direct_reassign` коммитит, хендлер шлёт jobs).
    """
    lang = "ru"
    try:
        _, shift_id_s, new_user_id_s = callback.data.split(":")
        shift_id, new_user_id = int(shift_id_s), int(new_user_id_s)
        from uk_management_bot.services.shift_transfer_service import ShiftTransferService

        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
            service = ShiftTransferService(db)
            res = service.manager_direct_reassign(shift_id, new_user_id, callback.from_user.id)
            if not res["success"]:
                await callback.answer(_reassign_error_text(res["error"], lang), show_alert=True)
                return

            service.dispatch_jobs(res["notification_jobs"])  # ПОСЛЕ commit (в сервисе)

            await callback.message.edit_text(
                get_text("shift_management.reassign_success", language=lang, moved=res.get("moved_requests", 0))
            )

    except Exception as e:
        logger.error(f"Ошибка прямого reassign смены: {e}")
        await callback.answer(get_text("shift_management.schedule_error", language=lang), show_alert=True)


@router.callback_query(F.data == "schedule_week_view")
@require_role(['admin', 'manager'])
async def handle_schedule_week_view(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Недельное расписание"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
            service = ShiftManagementService(db)

            # Определяем начало текущей недели (понедельник)
            today = date.today()
            monday = today - timedelta(days=today.weekday())

            period = f"{monday.strftime('%d.%m')} - {(monday + timedelta(days=6)).strftime('%d.%m.%Y')}"
            response = get_text("shift_management.week_schedule_title", language=lang, period=period)

            # Проходим по каждому дню недели
            days_keys = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

            for i in range(7):
                current_day = monday + timedelta(days=i)
                day_name = get_text(f"shift_management.{days_keys[i]}", language=lang)
            
                # Получаем смены на этот день
                shifts = service.get_shifts_for_date(current_day)
            
                response += f"<b>{day_name} {current_day.strftime('%d.%m')}</b>\n"
            
                if shifts:
                    for shift in shifts:
                        start_time = shift.planned_start_time.strftime('%H:%M') if shift.planned_start_time else "??:??"
                        end_time = _format_end_label(shift.planned_start_time, shift.planned_end_time) if shift.planned_end_time else "?"

                        # Цвет зависит от наличия исполнителя, а не от статуса
                        status_emoji = "🟢" if shift.user_id else "🟡"

                        # Получаем название смены
                        shift_name = ""
                        if shift.template:
                            shift_name = shift.template.name
                        elif shift.shift_type:
                            shift_type_key = f"shift_type_{shift.shift_type}"
                            shift_name = get_text(f"shift_management.{shift_type_key}", language=lang) if shift_type_key in ["shift_type_regular", "shift_type_emergency", "shift_type_overtime", "shift_type_maintenance"] else shift.shift_type
                        else:
                            shift_name = get_text("shift_management.shift_generic", language=lang)

                        # Получаем имя исполнителя
                        executor_name = get_text("shift_management.not_assigned", language=lang)
                        if shift.user_id:
                            user = service.get_user(shift.user_id)
                            if user:
                                executor_name = f"{user.first_name}"

                        response += f"  {status_emoji} <b>{start_time}-{end_time}</b> {shift_name} | {executor_name}\n"
                else:
                    response += get_text("shift_management.no_shifts", language=lang)
            
                response += "\n"
        
            await callback.message.edit_text(
                response,
                reply_markup=get_schedule_view_keyboard(today, lang),
                parse_mode="HTML"
            )
        
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка недельного расписания: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data == "schedule_month_view")
@require_role(['admin', 'manager'])
async def handle_schedule_month_view(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Месячный обзор расписания"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
        
            # Определяем текущий месяц
            today = date.today()
            month_start = today.replace(day=1)
        
            # Получаем смены за месяц
            shifts = ShiftManagementService(db).get_shifts_in_month(month_start)
        
            # Группируем по датам
            shifts_by_date = {}
            for shift in shifts:
                if shift.planned_start_time:
                    shift_date = shift.planned_start_time.date()
                    if shift_date not in shifts_by_date:
                        shifts_by_date[shift_date] = 0
                    shifts_by_date[shift_date] += 1
        
            # BUG-BOT-026: используем локализованное имя месяца вместо системного %B
            from uk_management_bot.utils.date_helpers import localized_month_year
            response = get_text("shift_management.month_overview_title", language=lang,
                              month=localized_month_year(today, language=lang), total=len(shifts))

            # Показываем дни с наибольшим количеством смен
            if shifts_by_date:
                sorted_dates = sorted(shifts_by_date.items(), key=lambda x: x[1], reverse=True)[:10]
                response += get_text("shift_management.busiest_days_header", language=lang)
                for shift_date, count in sorted_dates:
                    response += f"• {shift_date.strftime('%d.%m')}: {count} смен\n"
            else:
                response += get_text("shift_management.no_shifts_month", language=lang)

            await callback.message.edit_text(
                response,
                reply_markup=get_schedule_view_keyboard(today, lang),
                parse_mode="HTML"
            )

            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка месячного обзора: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data == "back_to_shifts")
async def handle_back_to_shifts(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Возврат к главному меню смен"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
        
            await callback.message.edit_text(
                get_text("shift_management.back_menu_title", language=lang),
                reply_markup=get_main_shift_menu(lang),
                parse_mode="HTML"
            )

            await state.clear()
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка возврата к меню смен: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.error_generic", language=lang), show_alert=True)
