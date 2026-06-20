"""
Обработчики для управления сменами - интерфейсы для менеджеров
"""

from contextlib import contextmanager
from datetime import datetime, date, timedelta
from typing import Optional

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext

from uk_management_bot.database.session import session_scope
from uk_management_bot.database.models.user import User
from sqlalchemy.orm import Session
from uk_management_bot.services.shift_planning_service import ShiftPlanningService
from uk_management_bot.services.shift_management_service import ShiftManagementService
from uk_management_bot.services.template_manager import TemplateManager
from uk_management_bot.keyboards.shift_management import (
    get_main_shift_menu,
    get_planning_menu,
    get_template_selection_keyboard,
    get_date_selection_keyboard,
    get_analytics_menu,
    get_auto_planning_keyboard,
    get_schedule_view_keyboard,
    get_template_management_keyboard,
    get_executor_assignment_keyboard
)
from uk_management_bot.states.shift_management import ShiftManagementStates, TemplateManagementStates, ExecutorAssignmentStates
from uk_management_bot.middlewares.auth import require_role
from uk_management_bot.utils.helpers import get_user_language
from uk_management_bot.utils.helpers import get_text
import logging

logger = logging.getLogger(__name__)
router = Router()


@contextmanager
def _db_scope(db):
    """Сессия для хендлера: инъецированная (владелец — вызывающий, НЕ закрываем
    здесь) либо свежая через ``session_scope()`` (закроется на выходе).

    CODE-04: заменяет ``db = next(get_db())`` + ``finally: db.close()``. Сохраняет
    seam внедрения ``db`` в тестах (близкий к исходному: переданный db не трогаем,
    а если db нет — берём и гарантированно закрываем).
    """
    if db is not None:
        yield db
    else:
        with session_scope() as scoped:
            yield scoped


def _format_end_label(start_dt: Optional[datetime], end_dt: Optional[datetime]) -> str:
    """Время конца смены 'ЧЧ:ММ'; добавляет '+N', если смена переходит на
    следующий день(и) (например суточная 08:00→08:00 показывается как '08:00 +1').

    start_dt и end_dt должны быть в одной таймзоне (берутся из одной смены —
    start_time/end_time или planned_*), поэтому сравнение .date() согласовано.
    """
    if not end_dt:
        return "—"
    label = end_dt.strftime('%H:%M')
    if start_dt and end_dt.date() > start_dt.date():
        label += f" +{(end_dt.date() - start_dt.date()).days}"
    return label

# Словарь локализации специализаций
SPECIALIZATION_TRANSLATIONS = {
    "ru": {
        "electric": "Электрика",
        "plumbing": "Сантехника",
        "hvac": "Вентиляция",
        "security": "Охрана",
        "cleaning": "Уборка",
        "universal": "Универсальная",
        "carpentry": "Плотницкие работы",
        "painting": "Малярные работы",
        "landscaping": "Благоустройство",
        "maintenance": "Обслуживание",
        "it": "IT поддержка",
        "reception": "Ресепшн"
    },
    "uz": {
        "electric": "Elektr",
        "plumbing": "Santexnika",
        "hvac": "Ventilyatsiya",
        "security": "Xavfsizlik",
        "cleaning": "Tozalash",
        "universal": "Universal",
        "carpentry": "Duradgorlik",
        "painting": "Bo'yoqchilik",
        "landscaping": "Obodonlashtirish",
        "maintenance": "Texnik xizmat",
        "it": "IT qo'llab-quvvatlash",
        "reception": "Qabulxona"
    }
}

def translate_specializations(specializations: list, language: str = "ru") -> str:
    """Переводит список специализаций на указанный язык"""
    if not specializations:
        return get_text("shift_management.any_specialization", language=language)

    translations = SPECIALIZATION_TRANSLATIONS.get(language, SPECIALIZATION_TRANSLATIONS["ru"])
    translated = [translations.get(spec, spec) for spec in specializations]
    return ", ".join(translated)


@router.message(Command("shifts"))
@require_role(['admin', 'manager'])
async def cmd_shifts(message: Message, state: FSMContext, db=None):
    """Главное меню управления сменами"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(message.from_user.id, db)

            await message.answer(
                get_text("shift_management.main_menu_title", language=lang),
                reply_markup=get_main_shift_menu(lang),
                parse_mode="HTML"
            )

            await state.set_state(ShiftManagementStates.main_menu)

    except Exception as e:
        logger.error(f"Ошибка команды /shifts: {e}")
        await message.answer(get_text("shift_management.menu_load_error", language=lang))




@router.callback_query(F.data == "shift_planning")
@require_role(['admin', 'manager'])
async def handle_shift_planning(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Меню планирования смен"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
        
            await callback.message.edit_text(
                get_text("shift_management.planning_menu_title", language=lang),
                reply_markup=get_planning_menu(lang),
                parse_mode="HTML"
            )

            await state.set_state(ShiftManagementStates.planning_menu)
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка планирования смен: {e}")
        await callback.answer(get_text("shift_management.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data == "auto_planning")
@require_role(['admin', 'manager'])
async def handle_auto_planning(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Автоматическое планирование смен"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
        
            await callback.message.edit_text(
                get_text("shift_management.auto_planning_title", language=lang),
                reply_markup=get_auto_planning_keyboard(lang),
                parse_mode="HTML"
            )
        
            await state.set_state(ShiftManagementStates.auto_planning_settings)
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка автопланирования: {e}")
        await callback.answer(get_text("shift_management.error_generic", language=lang), show_alert=True)


def _get_confirm_keyboard(yes_callback: str, no_callback: str, lang: str) -> InlineKeyboardMarkup:
    """Inline keyboard with Yes/No buttons for destructive confirmation."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=get_text("shift_planning.confirm_yes", language=lang),
                callback_data=yes_callback,
            ),
            InlineKeyboardButton(
                text=get_text("shift_planning.confirm_no", language=lang),
                callback_data=no_callback,
            ),
        ]
    ])


@router.callback_query(F.data == "auto_plan_week")
@require_role(['admin', 'manager'])
async def handle_auto_plan_week(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Подтверждение автопланирования на неделю (без создания смен)."""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            today = date.today()
            days_until_monday = today.weekday()
            monday = today - timedelta(days=days_until_monday)
            sunday = monday + timedelta(days=6)
            period = f"{monday.strftime('%d.%m.%Y')} — {sunday.strftime('%d.%m.%Y')}"

            prompt = get_text(
                "shift_planning.confirm_prompt",
                language=lang,
                action=get_text("shift_management.keyboards.auto_plan_week", language=lang),
                period=period,
            )

            await callback.message.edit_text(
                prompt,
                reply_markup=_get_confirm_keyboard(
                    yes_callback="confirm_auto_plan_week",
                    no_callback="cancel_auto_plan_week",
                    lang=lang,
                ),
                parse_mode="HTML",
            )
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка подтверждения автопланирования недели: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data == "cancel_auto_plan_week")
@require_role(['admin', 'manager'])
async def handle_auto_plan_week_cancel(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Отмена автопланирования на неделю — возврат в меню автопланирования."""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
            await callback.message.edit_text(
                get_text("shift_planning.cancelled", language=lang),
                reply_markup=get_auto_planning_keyboard(lang),
                parse_mode="HTML",
            )
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка отмены автопланирования недели: {e}")
        await callback.answer()


@router.callback_query(F.data == "confirm_auto_plan_week")
@require_role(['admin', 'manager'])
async def handle_auto_plan_week_confirm(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Автопланирование на неделю (выполнение после подтверждения)."""
    try:
        with _db_scope(db) as db:

            lang = get_user_language(callback.from_user.id, db)
            planning_service = ShiftPlanningService(db)

            # Начинаем планирование с понедельника текущей недели
            today = date.today()
            days_until_monday = today.weekday()
            monday = today - timedelta(days=days_until_monday)

            await callback.answer(get_text("shift_management.planning_week_progress", language=lang))

            results = planning_service.plan_weekly_schedule(monday)

            # Формируем отчет
            stats = results['statistics']
            period = f"{results['week_start'].strftime('%d.%m.%Y')} - {(results['week_start'] + timedelta(days=6)).strftime('%d.%m.%Y')}"
            response = get_text("shift_management.auto_plan_week_complete", language=lang,
                               period=period, total_shifts=stats['total_shifts'])

            if stats['shifts_by_day']:
                response += get_text("shift_management.shifts_by_day_header", language=lang)
                for day, count in stats['shifts_by_day'].items():
                    response += get_text("shift_management.shifts_count", language=lang, name=day, count=count)

            if stats['shifts_by_template']:
                response += get_text("shift_management.shifts_by_template_header", language=lang)
                for template, count in stats['shifts_by_template'].items():
                    response += get_text("shift_management.shifts_count", language=lang, name=template, count=count)

            if results['errors']:
                response += get_text("shift_management.errors_header", language=lang)
                for error in results['errors'][:3]:  # Показываем только первые 3 ошибки
                    response += f"• {error}\n"

            await callback.message.edit_text(
                response,
                reply_markup=get_auto_planning_keyboard(lang),
                parse_mode="HTML"
            )

    except Exception as e:
        logger.error(f"Ошибка автопланирования недели: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.message.edit_text(
            get_text("shift_management.auto_plan_week_error", language=lang, error=str(e)[:200]),
            reply_markup=get_auto_planning_keyboard(lang),
            parse_mode="HTML"
        )


@router.callback_query(F.data == "auto_plan_month")
@require_role(['admin', 'manager'])
async def handle_auto_plan_month(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Подтверждение автопланирования на месяц (без создания смен)."""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            today = date.today()
            month_end = today + timedelta(weeks=4) - timedelta(days=1)
            period = f"{today.strftime('%d.%m.%Y')} — {month_end.strftime('%d.%m.%Y')}"

            prompt = get_text(
                "shift_planning.confirm_prompt",
                language=lang,
                action=get_text("shift_management.keyboards.auto_plan_month", language=lang),
                period=period,
            )

            await callback.message.edit_text(
                prompt,
                reply_markup=_get_confirm_keyboard(
                    yes_callback="confirm_auto_plan_month",
                    no_callback="cancel_auto_plan_month",
                    lang=lang,
                ),
                parse_mode="HTML",
            )
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка подтверждения автопланирования месяца: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data == "cancel_auto_plan_month")
@require_role(['admin', 'manager'])
async def handle_auto_plan_month_cancel(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Отмена автопланирования на месяц — возврат в меню автопланирования."""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
            await callback.message.edit_text(
                get_text("shift_planning.cancelled", language=lang),
                reply_markup=get_auto_planning_keyboard(lang),
                parse_mode="HTML",
            )
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка отмены автопланирования месяца: {e}")
        await callback.answer()


@router.callback_query(F.data == "confirm_auto_plan_month")
@require_role(['admin', 'manager'])
async def handle_auto_plan_month_confirm(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Автопланирование на месяц (выполнение после подтверждения)."""
    try:
        with _db_scope(db) as db:

            lang = get_user_language(callback.from_user.id, db)
            planning_service = ShiftPlanningService(db)

            await callback.answer(get_text("shift_management.planning_month_progress", language=lang))

            # Планируем по неделям на весь месяц
            today = date.today()
            total_shifts = 0
            weeks_planned = 0
            errors = []

            # Планируем 4 недели вперед
            for week_offset in range(4):
                week_start = today + timedelta(weeks=week_offset)
                try:
                    results = planning_service.plan_weekly_schedule(week_start)
                    total_shifts += results['statistics']['total_shifts']
                    weeks_planned += 1
                    if results['errors']:
                        errors.extend(results['errors'])
                except Exception as e:
                    errors.append(get_text("shift_management.week_error", language=lang,
                                          week=week_offset + 1, error=str(e)))

            response = get_text("shift_management.auto_plan_month_complete", language=lang,
                              weeks_planned=weeks_planned, total_shifts=total_shifts)

            if errors:
                response += get_text("shift_management.errors_count_header", language=lang, count=len(errors))
                for error in errors[:3]:  # Показываем только первые 3 ошибки
                    response += f"• {error}\n"
                if len(errors) > 3:
                    response += get_text("shift_management.more_errors", language=lang, count=len(errors) - 3)

            await callback.message.edit_text(
                response,
                reply_markup=get_auto_planning_keyboard(lang),
                parse_mode="HTML"
            )

    except Exception as e:
        logger.error(f"Ошибка автопланирования месяца: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.message.edit_text(
            get_text("shift_management.auto_plan_month_error", language=lang, error=str(e)[:200]),
            reply_markup=get_auto_planning_keyboard(lang),
            parse_mode="HTML"
        )


@router.callback_query(F.data == "auto_plan_tomorrow")
@require_role(['admin', 'manager'])
async def handle_auto_plan_tomorrow(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Подтверждение создания смен на завтра (без создания смен)."""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            tomorrow = date.today() + timedelta(days=1)
            period = tomorrow.strftime('%d.%m.%Y')

            prompt = get_text(
                "shift_planning.confirm_prompt",
                language=lang,
                action=get_text("shift_management.keyboards.create_shifts_tomorrow", language=lang),
                period=period,
            )

            await callback.message.edit_text(
                prompt,
                reply_markup=_get_confirm_keyboard(
                    yes_callback="confirm_auto_plan_tomorrow",
                    no_callback="cancel_auto_plan_tomorrow",
                    lang=lang,
                ),
                parse_mode="HTML",
            )
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка подтверждения создания смен на завтра: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data == "cancel_auto_plan_tomorrow")
@require_role(['admin', 'manager'])
async def handle_auto_plan_tomorrow_cancel(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Отмена создания смен на завтра — возврат в меню автопланирования."""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
            await callback.message.edit_text(
                get_text("shift_planning.cancelled", language=lang),
                reply_markup=get_auto_planning_keyboard(lang),
                parse_mode="HTML",
            )
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка отмены создания смен на завтра: {e}")
        await callback.answer()


@router.callback_query(F.data == "confirm_auto_plan_tomorrow")
@require_role(['admin', 'manager'])
async def handle_auto_plan_tomorrow_confirm(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Создание смен на завтра (выполнение после подтверждения)."""
    try:
        with _db_scope(db) as db:

            lang = get_user_language(callback.from_user.id, db)
            planning_service = ShiftPlanningService(db)

            tomorrow = date.today() + timedelta(days=1)

            await callback.answer(get_text("shift_management.planning_tomorrow_progress", language=lang))

            # Получаем активные шаблоны для автосоздания
            templates = ShiftManagementService(db).list_auto_create_templates()

            total_shifts = 0
            created_by_template = {}
            errors = []

            for template in templates:
                if template.is_date_included(tomorrow):
                    try:
                        shifts = planning_service.create_shift_from_template(template.id, tomorrow)
                        if shifts:
                            total_shifts += len(shifts)
                            created_by_template[template.name] = len(shifts)
                    except Exception as e:
                        errors.append(f"{template.name}: {str(e)}")

            response = get_text("shift_management.auto_plan_tomorrow_complete", language=lang,
                              date=tomorrow.strftime('%d.%m.%Y'), total_shifts=total_shifts)

            if created_by_template:
                response += get_text("shift_management.shifts_by_template_header", language=lang)
                for template, count in created_by_template.items():
                    response += get_text("shift_management.shifts_count", language=lang, name=template, count=count)

            if total_shifts == 0:
                response += get_text("shift_management.possible_reasons_header", language=lang)
                response += get_text("shift_management.reason_no_templates", language=lang)
                response += get_text("shift_management.reason_no_weekdays", language=lang)
                response += get_text("shift_management.reason_not_workday", language=lang)

            if errors:
                response += get_text("shift_management.errors_header", language=lang)
                for error in errors[:3]:
                    response += f"• {error}\n"

            await callback.message.edit_text(
                response,
                reply_markup=get_auto_planning_keyboard(lang),
                parse_mode="HTML"
            )

    except Exception as e:
        logger.error(f"Ошибка создания смен на завтра: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.message.edit_text(
            get_text("shift_management.auto_plan_tomorrow_error", language=lang, error=str(e)[:200]),
            reply_markup=get_auto_planning_keyboard(lang),
            parse_mode="HTML"
        )


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
            else:
                response += get_text("shift_management.no_shifts_on_date", language=lang)

            response += get_text("shift_management.select_another_date", language=lang)

            await callback.message.edit_text(
                response,
                reply_markup=get_schedule_view_keyboard(selected_date, lang),
                parse_mode="HTML"
            )

            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка выбора даты расписания: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.schedule_load_error", language=lang), show_alert=True)


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


@router.callback_query(F.data == "template_management")
@require_role(['admin', 'manager'])
async def handle_template_management(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Управление шаблонами смен"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
        
            await callback.message.edit_text(
                get_text("shift_management.template_management_title", language=lang),
                reply_markup=get_template_management_keyboard(lang),
                parse_mode="HTML"
            )

            await state.set_state(ShiftManagementStates.template_menu)
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка управления шаблонами: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.template_error", language=lang), show_alert=True)


@router.callback_query(F.data == "create_new_template")
@require_role(['admin', 'manager'])
async def handle_create_new_template(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Создание нового шаблона"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
        
            await callback.message.edit_text(
                get_text("shift_management.create_template_title", language=lang),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang),
                                        callback_data="template_management")]
                ]),
                parse_mode="HTML"
            )

            await state.set_state(ShiftManagementStates.template_name_input)
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка создания шаблона: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.template_error", language=lang), show_alert=True)


@router.callback_query(F.data == "templates_view_all")
@require_role(['admin', 'manager'])
async def handle_view_all_templates(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Просмотр всех шаблонов"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
            template_manager = TemplateManager(db)
        
            # Получаем все шаблоны
            templates = template_manager.get_templates(active_only=False)
        
            if not templates:
                await callback.message.edit_text(
                    get_text("shift_management.no_templates_found", language=lang),
                    reply_markup=get_template_management_keyboard(lang),
                    parse_mode="HTML"
                )
                await callback.answer(get_text("shift_management.no_templates_alert", language=lang))
                return
        
            # Формируем текст со списком шаблонов
            templates_text = get_text("shift_management.templates_list_title", language=lang)
        
            for i, template in enumerate(templates, 1):
                status_emoji = "✅" if template.is_active else "❌"
                time_info = f"{template.start_hour:02d}:{template.start_minute or 0:02d}"
                duration_info = f"{template.duration_hours}ч"
            
                specialization_info = ""
                if template.required_specializations:
                    from uk_management_bot.utils.constants import SPECIALIZATIONS
                    spec_names = [SPECIALIZATIONS.get(spec, spec) for spec in template.required_specializations[:2]]
                    specialization_info = f" • {', '.join(spec_names)}"
                    if len(template.required_specializations) > 2:
                        specialization_info += f" (+{len(template.required_specializations)-2})"
            
                description = template.description or get_text("shift_management.no_description", language=lang)
                templates_text += (
                    f"{i}. {status_emoji} <b>{template.name}</b>\n"
                    f"   🕒 {time_info} ({duration_info}){specialization_info}\n"
                    f"   📝 {description}\n\n"
                )
        
            await callback.message.edit_text(
                templates_text,
                reply_markup=get_template_management_keyboard(lang),
                parse_mode="HTML"
            )
        
            await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка просмотра шаблонов: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.template_error", language=lang), show_alert=True)


@router.message(StateFilter(ShiftManagementStates.template_name_input))
async def handle_template_name_input(message: Message, state: FSMContext, db=None, roles: list = None, user=None):
    """Обработка ввода названия шаблона"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(message.from_user.id, db)
        
            template_name = message.text.strip()
        
            # Проверяем длину названия
            if len(template_name) < 3:
                await message.answer(
                    get_text("shift_management.name_too_short", language=lang),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang),
                                            callback_data="template_management")]
                    ])
                )
                return
        
            if len(template_name) > 50:
                await message.answer(
                    get_text("shift_management.name_too_long", language=lang),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang),
                                            callback_data="template_management")]
                    ])
                )
                return
        
            # Сохраняем название в состоянии
            await state.update_data(template_name=template_name)
        
            # Переходим к вводу времени начала
            await message.answer(
                get_text("shift_management.name_saved_enter_time", language=lang, name=template_name),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang),
                                        callback_data="template_management")]
                ]),
                parse_mode="HTML"
            )
        
            await state.set_state(ShiftManagementStates.template_time_input)
        
    except Exception as e:
        logger.error(f"Ошибка ввода названия шаблона: {e}")
        lang = get_user_language(message.from_user.id, db) if db else "ru"
        await message.answer(get_text("shift_management.template_name_error", language=lang))


@router.message(StateFilter(ShiftManagementStates.template_time_input))
async def handle_template_time_input(message: Message, state: FSMContext, db=None, roles: list = None, user=None):
    """Обработка ввода времени начала шаблона"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(message.from_user.id, db)
        
            time_text = message.text.strip()
        
            # Парсим время
            try:
                if ":" not in time_text:
                    raise ValueError("Неверный формат")
            
                hour_str, minute_str = time_text.split(":")
                hour = int(hour_str)
                minute = int(minute_str)
            
                if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                    raise ValueError("Неверное время")
                
            except (ValueError, IndexError):
                await message.answer(
                    get_text("shift_management.invalid_time_format", language=lang),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang),
                                            callback_data="template_management")]
                    ])
                )
                return
        
            # Сохраняем время в состоянии
            await state.update_data(start_hour=hour, start_minute=minute)
        
            # Переходим к вводу продолжительности
            await message.answer(
                get_text("shift_management.time_saved_enter_duration", language=lang, hour=hour, minute=minute),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang),
                                        callback_data="template_management")]
                ]),
                parse_mode="HTML"
            )
        
            await state.set_state(ShiftManagementStates.template_duration_input)
        
    except Exception as e:
        logger.error(f"Ошибка ввода времени шаблона: {e}")
        lang = get_user_language(message.from_user.id, db) if db else "ru"
        await message.answer(get_text("shift_management.template_time_error", language=lang))


@router.message(StateFilter(ShiftManagementStates.template_duration_input))
async def handle_template_duration_input(message: Message, state: FSMContext, db=None, roles: list = None, user=None):
    """Обработка ввода продолжительности шаблона"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(message.from_user.id, db)

            duration_text = message.text.strip()
        
            # Парсим продолжительность
            try:
                duration = int(duration_text)
                if duration < 1 or duration > 24:
                    raise ValueError("Неверная продолжительность")
            except ValueError:
                await message.answer(
                    get_text("shift_management.invalid_duration", language=lang),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang),
                                            callback_data="template_management")]
                    ])
                )
                return
        
            # Сохраняем продолжительность в состоянии и переходим к выбору специализаций
            await state.update_data(duration=duration)
        
            from uk_management_bot.utils.constants import SPECIALIZATIONS
            keyboard = []
        
            for spec_key, spec_name in SPECIALIZATIONS.items():
                keyboard.append([InlineKeyboardButton(
                    text=f"⭕ {spec_name}",
                    callback_data=f"template_create_spec_{spec_key}"
                )])
        
            keyboard.append([InlineKeyboardButton(text=get_text("shift_management.next_no_specs", language=lang),
                                                callback_data="template_create_no_specs")])
            keyboard.append([InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang),
                                                callback_data="template_management")])

            await message.answer(
                get_text("shift_management.duration_saved_select_specs", language=lang, duration=duration),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="HTML"
            )
        
            await state.set_state(ShiftManagementStates.template_specialization_selection)
        
    except Exception as e:
        logger.error(f"Ошибка создания шаблона: {e}")
        lang = get_user_language(message.from_user.id, db) if db else "ru"
        await message.answer(
            get_text("shift_management.template_creation_error", language=lang),
            reply_markup=get_template_management_keyboard(lang)
        )


@router.callback_query(F.data == "templates_edit")
@require_role(['admin', 'manager'])
async def handle_edit_templates(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Редактирование шаблонов смен"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
            template_manager = TemplateManager(db)
        
            logger.debug(f"Начинаем редактирование шаблонов для пользователя {callback.from_user.id}")
        
            # Получаем все шаблоны для редактирования
            templates = template_manager.get_templates(active_only=False)
        
            logger.debug(f"Найдено шаблонов: {len(templates)}")
        
            if not templates:
                await callback.message.edit_text(
                    get_text("shift_management.edit_no_templates", language=lang),
                    reply_markup=get_template_management_keyboard(lang),
                    parse_mode="HTML"
                )
                await callback.answer(get_text("shift_management.no_templates_alert", language=lang))
                return
        
            # Формируем клавиатуру со списком шаблонов для редактирования
            keyboard = []
            for template in templates:
                status_emoji = "✅" if template.is_active else "❌"
                time_info = f"{template.start_hour:02d}:{template.start_minute or 0:02d}"
            
                button_text = f"{status_emoji} {template.name} ({time_info})"
                keyboard.append([
                    InlineKeyboardButton(
                        text=button_text,
                        callback_data=f"template_edit_{template.id}"
                    )
                ])
        
            # Добавляем кнопки управления
            keyboard.extend([
                [InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang),
                                    callback_data="template_management")]
            ])

            logger.debug("Отправляем сообщение со списком шаблонов")

            await callback.message.edit_text(
                get_text("shift_management.edit_templates_title", language=lang),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="HTML"
            )
        
            logger.debug("Устанавливаем состояние")
            await state.set_state(TemplateManagementStates.editing_template)
        
            logger.debug("Отвечаем на callback")
            await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка редактирования шаблонов: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.edit_templates_error", language=lang), show_alert=True)


@router.callback_query(lambda c: c.data.startswith("template_edit_") and c.data.replace("template_edit_", "").isdigit())
@require_role(['admin', 'manager'])
async def handle_edit_template_details(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Редактирование конкретного шаблона"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            # Извлекаем ID шаблона из callback_data
            template_id = int(callback.data.replace("template_edit_", ""))
        
            # Получаем шаблон из базы данных
            template = ShiftManagementService(db).get_template(template_id)

            if not template:
                await callback.answer(get_text("shift_management.template_not_found", language=lang), show_alert=True)
                return

            # Формируем информацию о шаблоне
            status_text = get_text("shift_management.template_status_active", language=lang) if template.is_active else get_text("shift_management.template_status_inactive", language=lang)
            time_info = f"{template.start_hour:02d}:{template.start_minute or 0:02d}"

            specialization_info = get_text("shift_management.specializations_not_specified", language=lang)
            if template.required_specializations:
                from uk_management_bot.utils.constants import SPECIALIZATIONS
                specialization_info = ", ".join([SPECIALIZATIONS.get(spec, spec) for spec in template.required_specializations])

            description = template.description or get_text("shift_management.description_not_specified", language=lang)

            template_info = get_text("shift_management.edit_template_details", language=lang,
                                    name=template.name,
                                    description=description,
                                    time=time_info,
                                    duration=template.duration_hours,
                                    specializations=specialization_info,
                                    status=status_text)
        
            # Клавиатура редактирования
            toggle_text = get_text("shift_management.activate_button", language=lang) if not template.is_active else get_text("shift_management.deactivate_button", language=lang)

            keyboard = [
                [InlineKeyboardButton(text=get_text("shift_management.edit_name_button", language=lang),
                                    callback_data=f"template_edit_name_{template_id}")],
                [InlineKeyboardButton(text=get_text("shift_management.edit_description_button", language=lang),
                                    callback_data=f"template_edit_description_{template_id}")],
                [InlineKeyboardButton(text=get_text("shift_management.edit_time_button", language=lang),
                                    callback_data=f"template_edit_time_{template_id}")],
                [InlineKeyboardButton(text=get_text("shift_management.edit_duration_button", language=lang),
                                    callback_data=f"template_edit_duration_{template_id}")],
                [InlineKeyboardButton(text=get_text("shift_management.edit_specializations_button", language=lang),
                                    callback_data=f"template_edit_specializations_{template_id}")],
                [InlineKeyboardButton(text=toggle_text,
                                    callback_data=f"template_toggle_active_{template_id}")],
                [InlineKeyboardButton(text=get_text("shift_management.delete_template_button", language=lang),
                                    callback_data=f"template_delete_{template_id}")],
                [InlineKeyboardButton(text=get_text("shift_management.back_to_list_button", language=lang),
                                    callback_data="templates_edit")]
            ]
        
            await callback.message.edit_text(
                template_info,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="HTML"
            )
        
            # Сохраняем ID шаблона в состоянии для дальнейшего использования
            await state.update_data(editing_template_id=template_id)
            await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка редактирования шаблона: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.edit_templates_error", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("template_toggle_active_"))
@require_role(['admin', 'manager'])
async def handle_toggle_template_active(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Переключение активности шаблона"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            # Извлекаем ID шаблона
            template_id = int(callback.data.replace("template_toggle_active_", ""))

            service = ShiftManagementService(db)
            # Получаем шаблон
            template = service.get_template(template_id)

            if not template:
                await callback.answer(get_text("shift_management.template_not_found", language=lang), show_alert=True)
                return

            # Переключаем активность
            new_status = not template.is_active
            success = service.set_template_active(template_id, new_status)

            if success:
                status_key = "shift_management.template_activated" if new_status else "shift_management.template_deactivated"
                await callback.answer(get_text(status_key, language=lang))

                # Обновляем отображение
                await handle_edit_template_details(callback, state, db, roles, user)
            else:
                await callback.answer(get_text("shift_management.template_status_change_failed", language=lang), show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка переключения активности шаблона: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.template_toggle_error", language=lang), show_alert=True)


# Обработчики редактирования полей шаблона
@router.callback_query(F.data.startswith("template_edit_name_"))
@require_role(['admin', 'manager'])
async def handle_edit_template_name(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Изменение названия шаблона"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            template_id = int(callback.data.replace("template_edit_name_", ""))
            template = ShiftManagementService(db).get_template(template_id)

            if not template:
                await callback.answer(get_text("shift_management.template_not_found", language=lang), show_alert=True)
                return

            await callback.message.edit_text(
                get_text("shift_management.edit_name_prompt", language=lang, current_name=template.name),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=get_text("shift_management.cancel_button", language=lang), callback_data=f"template_edit_{template_id}")]
                ]),
                parse_mode="HTML"
            )

            await state.update_data(editing_template_id=template_id, editing_field="name")
            await state.set_state(TemplateManagementStates.editing_field)
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка изменения названия шаблона: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.edit_name_error", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("template_edit_description_"))
@require_role(['admin', 'manager'])
async def handle_edit_template_description(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Изменение описания шаблона"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            template_id = int(callback.data.replace("template_edit_description_", ""))
            template = ShiftManagementService(db).get_template(template_id)

            if not template:
                await callback.answer(get_text("shift_management.template_not_found", language=lang), show_alert=True)
                return

            current_desc = template.description or get_text("shift_management.description_not_specified", language=lang)
            await callback.message.edit_text(
                get_text("shift_management.edit_description_prompt", language=lang, current_description=current_desc),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=get_text("shift_management.cancel_button", language=lang), callback_data=f"template_edit_{template_id}")]
                ]),
                parse_mode="HTML"
            )

            await state.update_data(editing_template_id=template_id, editing_field="description")
            await state.set_state(TemplateManagementStates.editing_field)
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка изменения описания шаблона: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.edit_description_error", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("template_edit_time_"))
@require_role(['admin', 'manager'])
async def handle_edit_template_time(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Изменение времени начала шаблона"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            template_id = int(callback.data.replace("template_edit_time_", ""))
            template = ShiftManagementService(db).get_template(template_id)

            if not template:
                await callback.answer(get_text("shift_management.template_not_found", language=lang), show_alert=True)
                return

            await callback.message.edit_text(
                get_text("shift_management.edit_time_prompt", language=lang, current_time=f"{template.start_hour:02d}:00"),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=get_text("shift_management.cancel_button", language=lang), callback_data=f"template_edit_{template_id}")]
                ]),
                parse_mode="HTML"
            )

            await state.update_data(editing_template_id=template_id, editing_field="start_hour")
            await state.set_state(TemplateManagementStates.editing_field)
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка изменения времени шаблона: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.edit_time_error", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("template_edit_duration_"))
@require_role(['admin', 'manager'])
async def handle_edit_template_duration(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Изменение продолжительности шаблона"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            template_id = int(callback.data.replace("template_edit_duration_", ""))
            template = ShiftManagementService(db).get_template(template_id)

            if not template:
                await callback.answer(get_text("shift_management.template_not_found", language=lang), show_alert=True)
                return

            await callback.message.edit_text(
                get_text("shift_management.edit_duration_prompt", language=lang, current_duration=template.duration_hours),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=get_text("shift_management.cancel_button", language=lang), callback_data=f"template_edit_{template_id}")]
                ]),
                parse_mode="HTML"
            )

            await state.update_data(editing_template_id=template_id, editing_field="duration_hours")
            await state.set_state(TemplateManagementStates.editing_field)
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка изменения продолжительности шаблона: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.edit_duration_error", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("template_create_spec_"))
async def handle_template_create_specialization_toggle(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Переключение специализации при создании шаблона"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            specialization = callback.data.replace("template_create_spec_", "")

            # Получаем текущие выбранные специализации из состояния
            data = await state.get_data()
            selected_specs = data.get('selected_specializations', [])

            # Переключаем специализацию
            if specialization in selected_specs:
                selected_specs.remove(specialization)
            else:
                selected_specs.append(specialization)

            # Сохраняем в состоянии
            await state.update_data(selected_specializations=selected_specs)

            # Обновляем клавиатуру
            from uk_management_bot.utils.constants import SPECIALIZATIONS
            keyboard = []

            for spec_key, spec_name in SPECIALIZATIONS.items():
                is_selected = spec_key in selected_specs
                text = f"{'✅' if is_selected else '⭕'} {spec_name}"
                keyboard.append([InlineKeyboardButton(
                    text=text,
                    callback_data=f"template_create_spec_{spec_key}"
                )])

            keyboard.append([InlineKeyboardButton(text=get_text("shift_management.create_finish_button", language=lang), callback_data="template_create_finish")])
            keyboard.append([InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang), callback_data="template_management")])

            selected_text = ", ".join([SPECIALIZATIONS.get(spec, spec) for spec in selected_specs]) if selected_specs else get_text("shift_management.specs_not_selected", language=lang)

            try:
                await callback.message.edit_text(
                    get_text("shift_management.select_specs_for_template", language=lang, selected=selected_text),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                    parse_mode="HTML"
                )
            except Exception as edit_error:
                if "message is not modified" not in str(edit_error):
                    raise edit_error

            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка переключения специализации при создании: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.spec_toggle_error", language=lang), show_alert=True)


@router.callback_query(F.data == "template_create_finish")
async def handle_template_create_finish(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Завершение создания шаблона с выбранными специализациями"""
    try:
        with _db_scope(db) as db:
        
            template_manager = TemplateManager(db)
            lang = get_user_language(callback.from_user.id, db)
        
            # Получаем все данные из состояния
            data = await state.get_data()
            template_name = data.get('template_name')
            start_hour = data.get('start_hour')
            start_minute = data.get('start_minute', 0)
            duration = data.get('duration')
            selected_specs = data.get('selected_specializations', [])
        
            logger.info(f"Создание шаблона: name={template_name}, start_hour={start_hour}, start_minute={start_minute}, duration={duration}, specs={selected_specs}")
        
            # Создаем шаблон в базе данных
            template = template_manager.create_template(
                name=template_name,
                start_hour=start_hour,
                start_minute=start_minute,
                duration_hours=duration,
                description=get_text("shift_management.template_default_description", language=lang).format(name=template_name),
                required_specializations=selected_specs if selected_specs else None,
                is_active=True,
                auto_create=True,
                days_of_week=[1, 2, 3, 4, 5, 6, 7],  # Все дни недели
                advance_days=1  # Создавать смены за 1 день
            )
        
            if template:
                from uk_management_bot.utils.constants import SPECIALIZATIONS
                selected_text = ", ".join([SPECIALIZATIONS.get(spec, spec) for spec in selected_specs]) if selected_specs else get_text("shift_management.specializations_not_specified", language=lang)
                status_text = get_text("shift_management.template_status_active", language=lang)

                await callback.message.edit_text(
                    get_text("shift_management.template_created_success", language=lang,
                            name=template.name,
                            time=f"{template.start_hour:02d}:{(template.start_minute or 0):02d}",
                            duration=template.duration_hours,
                            specializations=selected_text,
                            status=status_text),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=get_text("shift_management.back_to_templates_button", language=lang), callback_data="template_management")]
                    ]),
                    parse_mode="HTML"
                )
            else:
                await callback.message.edit_text(
                    get_text("shift_management.template_creation_failed", language=lang),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang), callback_data="template_management")]
                    ])
                )

            await state.clear()
            success_msg = get_text("shift_management.template_created_popup", language=lang) if template else get_text("shift_management.template_creation_failed_popup", language=lang)
            await callback.answer(success_msg)

    except Exception as e:
        logger.error(f"Ошибка завершения создания шаблона: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.template_finish_error", language=lang), show_alert=True)


@router.callback_query(F.data == "template_create_no_specs")
async def handle_template_create_no_specs(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Создание шаблона без специализаций (совместимость со старым кодом)"""
    await handle_template_create_finish(callback, state, db, roles, user)


@router.callback_query(F.data.startswith("template_edit_specializations_"))
@require_role(['admin', 'manager'])
async def handle_edit_template_specializations(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Изменение специализаций шаблона"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
        
            template_id = int(callback.data.replace("template_edit_specializations_", ""))
            template = ShiftManagementService(db).get_template(template_id)
        
            if not template:
                await callback.answer(get_text("shift_management.template_not_found", language=lang), show_alert=True)
                return

            current_specializations = template.required_specializations or []
            from uk_management_bot.utils.constants import SPECIALIZATIONS
            not_specified = get_text("shift_management.not_specified", language=lang)
            specializations_text = ", ".join([SPECIALIZATIONS.get(spec, spec) for spec in current_specializations]) if current_specializations else not_specified

            # Создаем клавиатуру с доступными специализациями
            from uk_management_bot.utils.constants import SPECIALIZATIONS
            keyboard = []

            for spec_key, spec_name in SPECIALIZATIONS.items():
                is_selected = spec_key in current_specializations
                text = f"{'✅' if is_selected else '⭕'} {spec_name}"
                keyboard.append([InlineKeyboardButton(
                    text=text,
                    callback_data=f"template_spec_toggle_{template_id}_{spec_key}"
                )])

            keyboard.append([InlineKeyboardButton(text=get_text("shift_management.save_button", language=lang), callback_data=f"template_spec_save_{template_id}")])
            keyboard.append([InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang), callback_data=f"template_edit_{template_id}")])

            await callback.message.edit_text(
                get_text("shift_management.edit_specializations_title", language=lang,
                        template_name=template.name,
                        current_specs=specializations_text),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="HTML"
            )

            await state.update_data(editing_template_id=template_id)
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка редактирования специализаций шаблона: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("template_spec_toggle_"))
@require_role(['admin', 'manager'])
async def handle_toggle_template_specialization(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Переключение специализации шаблона"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            # Парсим callback data: template_spec_toggle_{template_id}_{specialization}
            parts = callback.data.replace("template_spec_toggle_", "").split("_", 1)
            template_id = int(parts[0])
            specialization = parts[1]

            template = ShiftManagementService(db).get_template(template_id)

            if not template:
                await callback.answer(get_text("shift_management.template_not_found", language=lang), show_alert=True)
                return

            current_specs = template.required_specializations or []

            # Переключаем специализацию
            if specialization in current_specs:
                current_specs.remove(specialization)
            else:
                current_specs.append(specialization)

            # Принудительно устанавливаем новое значение и помечаем поле как измененное
            ShiftManagementService(db).set_template_specializations(template_id, current_specs)

            # Обновляем клавиатуру
            from uk_management_bot.utils.constants import SPECIALIZATIONS
            keyboard = []

            for spec_key, spec_name in SPECIALIZATIONS.items():
                is_selected = spec_key in current_specs
                text = f"{'✅' if is_selected else '⭕'} {spec_name}"
                keyboard.append([InlineKeyboardButton(
                    text=text,
                    callback_data=f"template_spec_toggle_{template_id}_{spec_key}"
                )])

            keyboard.append([InlineKeyboardButton(text=get_text("shift_management.save_button", language=lang), callback_data=f"template_spec_save_{template_id}")])
            keyboard.append([InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang), callback_data=f"template_edit_{template_id}")])

            not_specified = get_text("shift_management.not_specified", language=lang)
            specializations_text = ", ".join([SPECIALIZATIONS.get(spec, spec) for spec in current_specs]) if current_specs else not_specified

            try:
                await callback.message.edit_text(
                    get_text("shift_management.edit_specializations_title", language=lang,
                            template_name=template.name,
                            current_specs=specializations_text),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                    parse_mode="HTML"
                )
            except Exception as edit_error:
                # Если сообщение не изменилось, просто игнорируем ошибку
                if "message is not modified" not in str(edit_error):
                    raise edit_error

            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка переключения специализации: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("template_spec_save_"))
@require_role(['admin', 'manager'])
async def handle_save_template_specializations(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Сохранение специализаций шаблона"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            template_id = int(callback.data.replace("template_spec_save_", ""))

            await callback.answer(get_text("shift_management.specializations_saved", language=lang))

            # Создаем новый callback объект для возврата к редактированию
            from aiogram.types import CallbackQuery
            new_callback = CallbackQuery(
                id=callback.id,
                from_user=callback.from_user,
                message=callback.message,
                data=f"template_edit_{template_id}",
                chat_instance=callback.chat_instance
            )

            # Возвращаемся к редактированию шаблона
            await handle_edit_template_details(new_callback, state, db, roles, user)

    except Exception as e:
        logger.error(f"Ошибка сохранения специализаций: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.error_generic", language=lang), show_alert=True)


@router.callback_query(lambda c: c.data.startswith("template_delete_") and not c.data.startswith("template_delete_confirm_") and c.data.replace("template_delete_", "").isdigit())
@require_role(['admin', 'manager'])
async def handle_delete_template(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Удаление шаблона"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
        
            template_id = int(callback.data.replace("template_delete_", ""))
            template = ShiftManagementService(db).get_template(template_id)
        
            if not template:
                await callback.answer(get_text("shift_management.template_not_found", language=lang), show_alert=True)
                return

            # Показываем подтверждение удаления
            await callback.message.edit_text(
                get_text("shift_management.delete_template_confirm", language=lang, name=template.name),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text=get_text("shift_management.delete_yes_button", language=lang),
                                           callback_data=f"template_delete_confirm_{template_id}"),
                        InlineKeyboardButton(text=get_text("shift_management.delete_cancel_button", language=lang),
                                           callback_data=f"template_edit_{template_id}")
                    ]
                ]),
                parse_mode="HTML"
            )
        
            await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка удаления шаблона: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.template_delete_error", language=lang), show_alert=True)


@router.callback_query(lambda c: c.data.startswith("template_delete_confirm_") and c.data.replace("template_delete_confirm_", "").isdigit())
@require_role(['admin', 'manager'])
async def handle_delete_template_confirm(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Подтверждение удаления шаблона"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
            template_manager = TemplateManager(db)
        
            template_id = int(callback.data.replace("template_delete_confirm_", ""))
            template = ShiftManagementService(db).get_template(template_id)
        
            if not template:
                await callback.answer(get_text("shift_management.template_not_found", language=lang), show_alert=True)
                return

            template_name = template.name

            # Попробуем удалить шаблон через менеджер (с проверками)
            success = template_manager.delete_template(template_id, force=False)

            if success:
                await callback.answer(get_text("shift_management.template_deleted", language=lang, name=template_name))
                # Возвращаемся к списку шаблонов
                await handle_edit_templates(callback, state, db, roles, user)
            else:
                # Показываем опцию принудительного удаления
                await callback.message.edit_text(
                    get_text("shift_management.template_delete_failed", language=lang, name=template_name),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=get_text("shift_management.force_delete_button", language=lang),
                                            callback_data=f"template_force_delete_{template_id}")],
                        [InlineKeyboardButton(text=get_text("shift_management.delete_cancel_button", language=lang),
                                            callback_data=f"template_edit_{template_id}")]
                    ]),
                    parse_mode="HTML"
                )
        
    except Exception as e:
        logger.error(f"Ошибка подтверждения удаления шаблона: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.template_delete_error", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("template_force_delete_"))
@require_role(['admin', 'manager'])
async def handle_force_delete_template(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Принудительное удаление шаблона"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
            template_manager = TemplateManager(db)
        
            template_id = int(callback.data.replace("template_force_delete_", ""))
            template = ShiftManagementService(db).get_template(template_id)
        
            if not template:
                await callback.answer(get_text("shift_management.template_not_found", language=lang), show_alert=True)
                return

            template_name = template.name

            # Принудительно удаляем шаблон
            success = template_manager.delete_template(template_id, force=True)

            if success:
                await callback.answer(get_text("shift_management.template_force_deleted", language=lang, name=template_name))
                # Возвращаемся к списку шаблонов
                await handle_edit_templates(callback, state, db, roles, user)
            else:
                await callback.answer(get_text("shift_management.template_delete_failed", language=lang), show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка принудительного удаления шаблона: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.error_generic", language=lang), show_alert=True)


# Обработчик ввода новых значений полей
@router.message(StateFilter(TemplateManagementStates.editing_field))
async def handle_template_field_input(message: Message, state: FSMContext, db=None, roles: list = None, user=None):
    """Обработка ввода нового значения поля шаблона"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(message.from_user.id, db)
        
            data = await state.get_data()
            template_id = data.get('editing_template_id')
            field = data.get('editing_field')
        
            if not template_id or not field:
                await message.answer(get_text("shift_management.editing_data_not_found", language=lang))
                return

            service = ShiftManagementService(db)
            template = service.get_template(template_id)

            if not template:
                await message.answer(get_text("shift_management.template_not_found", language=lang))
                return

            new_value = message.text.strip()

            # Валидация и обновление поля
            if field == "name":
                if len(new_value) < 3:
                    await message.answer(get_text("shift_management.name_min_length", language=lang))
                    return
                template.name = new_value

            elif field == "description":
                template.description = new_value if new_value else None

            elif field == "start_hour":
                try:
                    start_hour = int(new_value)
                    if not (0 <= start_hour <= 23):
                        await message.answer(get_text("shift_management.hour_range_error", language=lang))
                        return
                    template.start_hour = start_hour
                except ValueError:
                    await message.answer(get_text("shift_management.hour_number_error", language=lang))
                    return

            elif field == "duration_hours":
                try:
                    duration = int(new_value)
                    if not (1 <= duration <= 24):
                        await message.answer(get_text("shift_management.duration_range_error", language=lang))
                        return
                    template.duration_hours = duration
                except ValueError:
                    await message.answer(get_text("shift_management.duration_number_error", language=lang))
                    return
            else:
                await message.answer(get_text("shift_management.unknown_field_error", language=lang))
                return

            # Сохраняем изменения
            service.commit()

            # Отображаем успешное сообщение с правильным текстом
            field_names = {
                "name": get_text("shift_management.field_name_label", language=lang),
                "description": get_text("shift_management.field_description_label", language=lang),
                "start_hour": get_text("shift_management.field_start_hour_label", language=lang),
                "duration_hours": get_text("shift_management.field_duration_label", language=lang)
            }

            field_display = field_names.get(field, field.capitalize())

            await message.answer(
                get_text("shift_management.field_updated_success", language=lang, field=field_display),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=get_text("shift_management.back_to_template_button", language=lang), callback_data=f"template_edit_{template_id}")]
                ])
            )

            await state.clear()

    except Exception as e:
        logger.error(f"Ошибка обновления поля шаблона: {e}")
        lang = get_user_language(message.from_user.id, db) if db else "ru"
        await message.answer(get_text("shift_management.save_error", language=lang))


@router.callback_query(F.data == "create_shift_from_template")
@require_role(['admin', 'manager'])
async def handle_create_shift_template(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Создание смены из шаблона"""
    try:
        with _db_scope(db) as db:
            template_manager = TemplateManager(db)
            lang = get_user_language(callback.from_user.id, db)
        
            # Получаем активные шаблоны
            templates = template_manager.get_templates(active_only=True)

            if not templates:
                await callback.message.edit_text(
                    get_text("shift_management.no_templates_available", language=lang),
                    reply_markup=get_planning_menu(lang),
                    parse_mode="HTML"
                )
                await callback.answer(get_text("shift_management.no_templates_alert", language=lang), show_alert=True)
                return

            await callback.message.edit_text(
                get_text("shift_management.select_template_title", language=lang),
                reply_markup=get_template_selection_keyboard(templates, lang),
                parse_mode="HTML"
            )

            await state.set_state(ShiftManagementStates.selecting_template)
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка выбора шаблона: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("select_template:"))
@require_role(['admin', 'manager'])
async def handle_template_selection(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Выбор шаблона и даты"""
    try:
        template_id = int(callback.data.split(':')[1])
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
        
            # Сохраняем ID шаблона в состояние
            await state.update_data(template_id=template_id)

            # Получаем информацию о шаблоне
            template = ShiftManagementService(db).get_template(template_id)

            if not template:
                await callback.answer(get_text("shift_management.template_not_found", language=lang), show_alert=True)
                return

            any_spec = get_text("shift_management.any_specialization", language=lang)
            specializations = ', '.join(template.required_specializations) if template.required_specializations else any_spec

            await callback.message.edit_text(
                get_text("shift_management.select_date_for_shift", language=lang,
                        template_name=template.name,
                        start_time=f"{template.start_hour:02d}:{template.start_minute or 0:02d}",
                        end_time=f"{(template.start_hour + template.duration_hours) % 24:02d}:00",
                        specializations=specializations),
                reply_markup=get_date_selection_keyboard(lang),
                parse_mode="HTML"
            )

            await state.set_state(ShiftManagementStates.selecting_date)
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка выбора шаблона: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("select_date:"))
@require_role(['admin', 'manager'])
async def handle_date_selection(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Создание смены на выбранную дату"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            date_offset = int(callback.data.split(':')[1])
            target_date = date.today() + timedelta(days=date_offset)

            data = await state.get_data()
            template_id = data.get('template_id')

            if not template_id:
                await callback.answer(get_text("shift_management.template_not_found", language=lang), show_alert=True)
                return

            planning_service = ShiftPlanningService(db)

            # Создаем смены из шаблона
            created_shifts = planning_service.create_shift_from_template(
                template_id=template_id,
                target_date=target_date
            )

            if created_shifts:
                await callback.message.edit_text(
                    get_text("shift_management.shifts_created_success", language=lang,
                            date=target_date.strftime('%d.%m.%Y'),
                            count=len(created_shifts)),
                    reply_markup=get_planning_menu(lang),
                    parse_mode="HTML"
                )
            else:
                await callback.message.edit_text(
                    get_text("shift_management.shifts_not_created", language=lang,
                            date=target_date.strftime('%d.%m.%Y')),
                    reply_markup=get_planning_menu(lang),
                    parse_mode="HTML"
                )

            await state.set_state(ShiftManagementStates.planning_menu)
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка создания смены: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data == "plan_weekly_schedule")
@require_role(['admin', 'manager'])
async def handle_weekly_planning(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Подтверждение недельного планирования (без создания смен)."""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            start_date = date.today() + timedelta(days=1)
            days_until_monday = start_date.weekday()
            week_start = start_date - timedelta(days=days_until_monday)
            week_end = week_start + timedelta(days=6)
            period = f"{week_start.strftime('%d.%m.%Y')} — {week_end.strftime('%d.%m.%Y')}"

            prompt = get_text(
                "shift_planning.confirm_prompt",
                language=lang,
                action=get_text("shift_management.keyboards.plan_week", language=lang),
                period=period,
            )

            await callback.message.edit_text(
                prompt,
                reply_markup=_get_confirm_keyboard(
                    yes_callback="confirm_plan_weekly_schedule",
                    no_callback="cancel_plan_weekly_schedule",
                    lang=lang,
                ),
                parse_mode="HTML",
            )
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка подтверждения недельного планирования: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data == "cancel_plan_weekly_schedule")
@require_role(['admin', 'manager'])
async def handle_weekly_planning_cancel(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Отмена недельного планирования — возврат в меню планирования."""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
            await callback.message.edit_text(
                get_text("shift_planning.cancelled", language=lang),
                reply_markup=get_planning_menu(lang),
                parse_mode="HTML",
            )
            await state.set_state(ShiftManagementStates.planning_menu)
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка отмены недельного планирования: {e}")
        await callback.answer()


@router.callback_query(F.data == "confirm_plan_weekly_schedule")
@require_role(['admin', 'manager'])
async def handle_weekly_planning_confirm(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Планирование недельного расписания (выполнение после подтверждения)."""
    try:
        with _db_scope(db) as db:
            planning_service = ShiftPlanningService(db)
            lang = get_user_language(callback.from_user.id, db)

            # Планируем смены на следующую неделю
            start_date = date.today() + timedelta(days=1)
            results = planning_service.plan_weekly_schedule(start_date)
        
            stats = results['statistics']

            # Добавляем временную метку для обеспечения уникальности сообщения
            from datetime import datetime
            timestamp = datetime.now().strftime('%H:%M:%S')

            shifts_label = get_text("shift_management.shifts_label", language=lang)

            all_planned = ""
            if stats['total_shifts'] == 0:
                all_planned = get_text("shift_management.all_shifts_already_planned", language=lang)

            by_day = ""
            if stats['shifts_by_day'] and stats['total_shifts'] > 0:
                by_day_label = get_text("shift_management.by_day_label", language=lang)
                by_day = f"\n<b>{by_day_label}:</b>\n"
                for day_name, count in stats['shifts_by_day'].items():
                    by_day += f"• {day_name}: {count} {shifts_label}\n"

            by_template = ""
            if stats['shifts_by_template']:
                by_template_label = get_text("shift_management.by_template_label", language=lang)
                by_template = f"\n<b>{by_template_label}:</b>\n"
                for template_name, count in stats['shifts_by_template'].items():
                    by_template += f"• {template_name}: {count} {shifts_label}\n"

            errors_text = ""
            if results['errors']:
                errors_label = get_text("shift_management.errors_label", language=lang)
                errors_text = f"\n⚠️ <b>{errors_label}:</b>\n"
                for error in results['errors'][:3]:  # Показываем только первые 3 ошибки
                    errors_text += f"• {error}\n"

            week_info = get_text("shift_management.weekly_planning_complete", language=lang,
                                timestamp=timestamp,
                                week_start=results['week_start'].strftime('%d.%m.%Y'),
                                week_end=(results['week_start'] + timedelta(days=6)).strftime('%d.%m.%Y'),
                                total_shifts=stats['total_shifts'],
                                all_planned=all_planned,
                                by_day=by_day,
                                by_template=by_template,
                                errors=errors_text)

            await callback.message.edit_text(
                week_info,
                reply_markup=get_planning_menu(lang),
                parse_mode="HTML"
            )

            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка недельного планирования: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data == "shift_analytics")
@require_role(['admin', 'manager'])
async def handle_shift_analytics(callback: CallbackQuery, state: FSMContext, db=None):
    """Меню аналитики смен"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            await callback.message.edit_text(
                get_text("shift_management.analytics_menu_title", language=lang),
                reply_markup=get_analytics_menu(lang),
                parse_mode="HTML"
            )

            await state.set_state(ShiftManagementStates.analytics_menu)
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка аналитики: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data == "shift_executor_assignment")
@require_role(['admin', 'manager'])
async def handle_shift_executor_assignment(callback: CallbackQuery, state: FSMContext, db: Session = None, user: User = None, roles: list = None):
    """Назначение исполнителей для смен"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            # Получаем смены без назначенных исполнителей
            from datetime import datetime, timedelta
            now = datetime.now()
            week_ahead = now + timedelta(days=7)

            unassigned_shifts = ShiftManagementService(db).list_unassigned_planned_shifts_between(now, week_ahead)

            # BUG-BOT-014: используем клавиатуру с кнопкой "Назад" для возврата к меню смен
            from uk_management_bot.keyboards.shift_management import get_executor_assignment_keyboard

            if not unassigned_shifts:
                await callback.message.edit_text(
                    get_text("shift_management.no_unassigned_shifts", language=lang),
                    parse_mode="HTML",
                    reply_markup=get_executor_assignment_keyboard(lang)
                )
                await callback.answer()
                return

            # Показываем список смен для назначения

            shift_list = ""
            for shift in unassigned_shifts:
                start_time = shift.start_time.strftime('%d.%m.%Y %H:%M')
                # Переводим специализации на язык пользователя
                specialization_text = translate_specializations(shift.specialization_focus, lang)
                shift_list += f"🔹 <b>{start_time}</b> - {specialization_text}\n"

            text = get_text("shift_management.executor_assignment_list", language=lang,
                           count=len(unassigned_shifts),
                           shifts=shift_list)

            await callback.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=get_executor_assignment_keyboard(lang)
            )

            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка назначения исполнителей: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.executor_assignment_error", language=lang), show_alert=True)


@router.callback_query(F.data == "weekly_analytics")
@require_role(['admin', 'manager'])
async def handle_weekly_analytics(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Аналитика за неделю"""
    try:
        with _db_scope(db) as db:
            planning_service = ShiftPlanningService(db)
            lang = get_user_language(callback.from_user.id, db)
        
            # Анализируем последние 7 дней
            end_date = date.today()
            start_date = end_date - timedelta(days=6)
        
            # Получаем комплексную аналитику
            analytics = await planning_service.get_comprehensive_analytics(
                start_date=start_date,
                end_date=end_date,
                include_recommendations=True
            )
        
            if 'error' in analytics:
                await callback.message.edit_text(
                    get_text("shift_management.analytics_error_msg", language=lang, error=analytics['error']),
                    reply_markup=get_analytics_menu(lang),
                    parse_mode="HTML"
                )
                await callback.answer()
                return
        
            # Build shift statistics section
            shift_stats = ""
            if analytics.get('shift_analytics'):
                sa = analytics['shift_analytics']
                shift_stats = get_text("shift_management.shift_stats_section", language=lang,
                                       total=sa.get('total_shifts', 0),
                                       avg_efficiency=sa.get('average_efficiency', 0),
                                       completion_rate=sa.get('completion_rate', 0),
                                       on_time_rate=sa.get('on_time_rate', 0))

            # Build planning efficiency section
            planning_stats = ""
            if analytics.get('planning_efficiency') and 'error' not in analytics['planning_efficiency']:
                pe = analytics['planning_efficiency']
                planning_stats = get_text("shift_management.planning_efficiency_section", language=lang,
                                          assignment_rate=pe.get('assignment_rate', 0),
                                          avg_duration=pe.get('avg_actual_duration', 0),
                                          unassigned=pe.get('unassigned_shifts', 0))

            # Build recommendations section
            recommendations_text = ""
            if analytics.get('recommendations'):
                recommendations = analytics['recommendations'][:3]
                no_description = get_text("shift_management.no_description", language=lang)
                rec_list = ""
                for i, rec in enumerate(recommendations, 1):
                    rec_text = rec.get('description', rec.get('recommendation', no_description))
                    rec_list += f"{i}. {rec_text[:100]}...\n"
                recommendations_text = get_text("shift_management.recommendations_section", language=lang,
                                              recommendations=rec_list)

            report = get_text("shift_management.weekly_analytics_report", language=lang,
                             start_date=start_date.strftime('%d.%m.%Y'),
                             end_date=end_date.strftime('%d.%m.%Y'),
                             total_days=analytics['period']['total_days'],
                             shift_stats=shift_stats,
                             planning_stats=planning_stats,
                             recommendations=recommendations_text)
        
            await callback.message.edit_text(
                report,
                reply_markup=get_analytics_menu(lang),
                parse_mode="HTML"
            )
        
            await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка недельной аналитики: {e}", exc_info=True)
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.weekly_analytics_error", language=lang), show_alert=True)


@router.callback_query(F.data == "workload_forecast")
@require_role(['admin', 'manager'])
async def handle_workload_forecast(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Прогноз рабочей нагрузки"""
    try:
        with _db_scope(db) as db:
            planning_service = ShiftPlanningService(db)
            lang = get_user_language(callback.from_user.id, db)
        
            # Прогноз на следующие 5 дней
            target_date = date.today() + timedelta(days=1)
            prediction = await planning_service.predict_workload(
                target_date=target_date,
                days_ahead=5
            )
        
            if 'error' in prediction:
                await callback.message.edit_text(
                    get_text("shift_management.forecast_error_msg", language=lang, error=prediction['error']),
                    reply_markup=get_analytics_menu(lang),
                    parse_mode="HTML"
                )
                await callback.answer()
                return
        
            # Формируем отчет прогноза
            forecast_period = prediction['forecast_period']
            summary = prediction['summary']

            # Build daily predictions list
            daily_list = ""
            requests_label = get_text("shift_management.requests_label", language=lang)
            confidence_label = get_text("shift_management.confidence_label", language=lang)
            for daily_pred in prediction['daily_predictions'][:5]:
                date_str = daily_pred['date'].strftime('%d.%m')
                requests = daily_pred['predicted_requests']
                load_level = daily_pred['load_level']
                confidence = daily_pred['confidence']

                load_emoji = {
                    'low': '🟢',
                    'medium': '🟡',
                    'high': '🔴'
                }.get(load_level, '⚪')

                daily_list += f"• {date_str}: {requests} {requests_label} {load_emoji} ({confidence_label}: {confidence:.0%})\n"

            # Build resource recommendations section
            resources_text = ""
            if summary.get('resource_requirements'):
                req = summary['resource_requirements']
                resources_text = get_text("shift_management.resource_recommendations_section", language=lang,
                                         daily_shifts=req['recommended_daily_shifts'],
                                         peak_shifts=req['peak_day_shifts'],
                                         min_executors=req['min_executors_needed'])

            # Build peak/low load days
            peak_days_text = ""
            if summary.get('peak_load_days'):
                peak_dates = [d.strftime('%d.%m') for d in summary['peak_load_days'][:3]]
                peak_days_text = f"\n{get_text('shift_management.peak_load_days', language=lang, dates=', '.join(peak_dates))}\n"

            low_days_text = ""
            if summary.get('low_load_days'):
                low_dates = [d.strftime('%d.%m') for d in summary['low_load_days'][:3]]
                low_days_text = f"{get_text('shift_management.low_load_days', language=lang, dates=', '.join(low_dates))}\n"

            report = get_text("shift_management.workload_forecast_report", language=lang,
                             start_date=forecast_period['start_date'].strftime('%d.%m.%Y'),
                             end_date=forecast_period['end_date'].strftime('%d.%m.%Y'),
                             avg_requests=summary['avg_predicted_requests'],
                             daily_list=daily_list,
                             resources=resources_text,
                             peak_days=peak_days_text,
                             low_days=low_days_text)
        
            await callback.message.edit_text(
                report,
                reply_markup=get_analytics_menu(lang),
                parse_mode="HTML"
            )
        
            await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка прогноза нагрузки: {e}", exc_info=True)
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.workload_forecast_error", language=lang), show_alert=True)


@router.callback_query(F.data == "optimization_recommendations")
@require_role(['admin', 'manager'])
async def handle_optimization_recommendations(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Рекомендации по оптимизации"""
    try:
        with _db_scope(db) as db:
            planning_service = ShiftPlanningService(db)
            lang = get_user_language(callback.from_user.id, db)
        
            # Получаем рекомендации на сегодня
            recommendations = await planning_service.get_optimization_recommendations(
                target_date=date.today()
            )
        
            if 'error' in recommendations:
                await callback.message.edit_text(
                    get_text("shift_management.recommendations_error_msg", language=lang, error=recommendations['error']),
                    reply_markup=get_analytics_menu(lang),
                    parse_mode="HTML"
                )
                await callback.answer()
                return
        
            # Формируем отчет рекомендаций
            current_state = recommendations['current_state']
            target_date_str = recommendations['date'].strftime('%d.%m.%Y')

            # Build priority actions list
            priority_list = ""
            priority_actions = recommendations.get('priority_actions', [])
            if priority_actions:
                for action in priority_actions:
                    urgency_emoji = {
                        'high': '🔴',
                        'medium': '🟡',
                        'low': '🟢'
                    }.get(action.get('urgency', 'medium'), '⚪')

                    priority_list += f"{urgency_emoji} {action['description']}\n"
                    priority_list += f"   → {action['action']}\n\n"

            # Build optimization suggestions list
            optimization_list = ""
            optimization_suggestions = recommendations.get('optimization_suggestions', [])
            if optimization_suggestions:
                action_label = get_text("shift_management.action_label", language=lang)
                for suggestion in optimization_suggestions:
                    optimization_list += f"• {suggestion['description']}\n"
                    optimization_list += f"  {action_label}: {suggestion['action']}\n\n"

            # Build AI recommendations list
            ai_recs_list = ""
            if recommendations.get('ai_recommendations'):
                ai_recs = recommendations['ai_recommendations']
                if isinstance(ai_recs, dict) and ai_recs.get('recommendations'):
                    no_description = get_text("shift_management.no_description", language=lang)
                    for rec in ai_recs['recommendations'][:2]:
                        rec_text = rec.get('description', rec.get('recommendation', no_description))
                        ai_recs_list += f"• {rec_text[:80]}...\n"

            # All good message if no actions
            all_good_text = ""
            if not priority_actions and not optimization_suggestions:
                all_good_text = get_text("shift_management.optimization_all_good", language=lang)

            report = get_text("shift_management.optimization_recommendations_report", language=lang,
                             date=target_date_str,
                             total_shifts=current_state['shifts_count'],
                             assigned=current_state['assigned_shifts'],
                             unassigned=current_state['unassigned_shifts'],
                             priority_list=priority_list,
                             optimization_list=optimization_list,
                             ai_recs=ai_recs_list,
                             all_good=all_good_text)
        
            await callback.message.edit_text(
                report,
                reply_markup=get_analytics_menu(lang),
                parse_mode="HTML"
            )
        
            await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка рекомендаций по оптимизации: {e}", exc_info=True)
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.optimization_recommendations_error", language=lang), show_alert=True)


@router.callback_query(F.data == "monthly_analytics")
@require_role(['admin', 'manager'])
async def handle_monthly_analytics(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Месячный отчёт — заглушка (функция в разработке).

    Без этого handler-а кнопка `monthly_analytics` возвращала silent callback
    (no answer, no edit). См. BUG-BOT-003.
    """
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            await callback.message.edit_text(
                get_text("shift_management.monthly_analytics_under_development", language=lang),
                reply_markup=get_analytics_menu(lang),
                parse_mode="HTML",
            )
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка месячного отчёта: {e}", exc_info=True)
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data == "efficiency_analysis")
@require_role(['admin', 'manager'])
async def handle_efficiency_analysis(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Анализ эффективности — заглушка (функция в разработке).

    Без этого handler-а кнопка `efficiency_analysis` возвращала silent callback
    (no answer, no edit). См. BUG-BOT-003.
    """
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            await callback.message.edit_text(
                get_text("shift_management.efficiency_analysis_under_development", language=lang),
                reply_markup=get_analytics_menu(lang),
                parse_mode="HTML",
            )
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка анализа эффективности: {e}", exc_info=True)
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.error_generic", language=lang), show_alert=True)


# NOTE: a second `handle_back_to_shifts` (F.data == "back_to_shifts") previously
# lived here — a shadowed duplicate of the handler defined earlier (~L815), so it
# never ran (aiogram dispatches to the first registered match). It also carried an
# undefined-`db` bug (F821) that the F811 redefinition masked. Removed in the
# F821/F601 cleanup; the earlier handler is the single source of truth.


@router.callback_query(F.data == "back_to_planning")
async def handle_back_to_planning(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Возврат к меню планирования"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
        
            await callback.message.edit_text(
                get_text("shift_management.planning_menu_title", language=lang),
                reply_markup=get_planning_menu(lang),
                parse_mode="HTML"
            )

            await state.set_state(ShiftManagementStates.planning_menu)
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка возврата к планированию: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.back_to_planning_error", language=lang), show_alert=True)


@router.callback_query(F.data == "back_to_analytics")
async def handle_back_to_analytics(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Возврат к меню аналитики"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            await callback.message.edit_text(
                get_text("shift_management.analytics_menu_title", language=lang),
                reply_markup=get_analytics_menu(lang),
                parse_mode="HTML"
            )

            await state.set_state(ShiftManagementStates.analytics_menu)
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка возврата к аналитике: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.back_to_analytics_error", language=lang), show_alert=True)


# Handlers for Executor Assignment

@router.callback_query(F.data == "assign_to_shift")
@require_role(['admin', 'manager'])
async def handle_assign_to_shift(callback: CallbackQuery, state: FSMContext, db: Session = None, user: User = None, roles: list = None):
    """Назначить исполнителя на конкретную смену"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            # Получаем неназначенные смены
            from datetime import datetime, timedelta
            now = datetime.now()
            week_ahead = now + timedelta(days=7)

            unassigned_shifts = ShiftManagementService(db).list_unassigned_planned_shifts_range(now, week_ahead)

            if not unassigned_shifts:
                await callback.message.edit_text(
                    get_text("shift_management.all_shifts_assigned", language=lang),
                    reply_markup=get_executor_assignment_keyboard(lang),
                    parse_mode="HTML"
                )
                await callback.answer()
                return

            # Формируем список смен для выбора
            shift_details = ""
            for i, shift in enumerate(unassigned_shifts, 1):
                # Переводим специализации на язык пользователя
                specialization_text = translate_specializations(shift.specialization_focus, lang)

                # Форматируем время
                start_date = shift.start_time.strftime('%d.%m.%Y')
                start_time = shift.start_time.strftime('%H:%M')
                end_time = _format_end_label(shift.start_time, shift.end_time)
                zone = shift.geographic_zone or get_text("shift_management.zone_not_specified", language=lang)

                shift_details += (f"{i}. <b>{start_date}</b> "
                                f"{start_time}-{end_time}\n"
                                f"   🔧 {specialization_text}\n"
                                f"   📍 {zone}\n\n")

            text = get_text("shift_management.assign_to_specific_shift", language=lang, shifts=shift_details)

            # Создаем клавиатуру для выбора смены
            keyboard = []
            for shift in unassigned_shifts:
                # Переводим специализации (показываем первые 2)
                if shift.specialization_focus and isinstance(shift.specialization_focus, list):
                    first_two = shift.specialization_focus[:2]
                    spec_text = translate_specializations(first_two, lang)
                else:
                    spec_text = get_text("shift_management.any_spec", language=lang)

                button_text = f"{shift.start_time.strftime('%d.%m %H:%M')} - {spec_text}"
                keyboard.append([InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"select_shift_for_assignment:{shift.id}"
                )])

            keyboard.append([InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang), callback_data="executor_assignment")])

            await callback.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="HTML"
            )

            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка назначения на смену: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.assign_to_shift_error", language=lang), show_alert=True)


@router.callback_query(F.data == "ai_assignment")
@require_role(['admin', 'manager'])
async def handle_ai_assignment(callback: CallbackQuery, state: FSMContext, db: Session = None, user: User = None, roles: list = None):
    """ИИ-назначение исполнителей"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            from uk_management_bot.services.shift_assignment_service import ShiftAssignmentService
            assignment_service = ShiftAssignmentService(db)

            # FS-03: auto_assign_executors_to_shifts — синхронный и принимает
            # СПИСОК смен (не target_date/days_ahead), и не должен await'иться.
            # Сами неназначенные смены тянем из ShiftManagementService.
            end_dt = datetime.now() + timedelta(days=7)
            unassigned_shifts = ShiftManagementService(db).list_unassigned_shifts_window(
                datetime.now(), end_dt
            )
            result = assignment_service.auto_assign_executors_to_shifts(
                unassigned_shifts, force_reassign=False
            )

            if result.get('error'):
                await callback.message.edit_text(
                    get_text("shift_management.ai_assignment_error_msg", language=lang, error=result['error']),
                    reply_markup=get_executor_assignment_keyboard(lang),
                    parse_mode="HTML"
                )
                await callback.answer()
                return

            # Реальная форма результата: successful_assignments / failed_assignments /
            # conflicts_found + assignments[{executor_name, assignment_score, shift_id}]
            # + conflicts[{shift_id, description}].
            assignments = result.get('assignments', [])
            conflicts = result.get('conflicts', [])
            assigned_count = result.get('successful_assignments', len(assignments))
            failed_count = result.get('failed_assignments', 0)

            assignments_list = ""
            if assignments:
                for a in assignments[:5]:
                    name = a.get('executor_name') or f"#{a.get('executor_id')}"
                    score = a.get('assignment_score') or 0
                    assignments_list += f"• №{a.get('shift_id')} → {name} ({score:.0%})\n"
                if len(assignments) > 5:
                    more_text = get_text("shift_management.and_more_assignments", language=lang, count=len(assignments) - 5)
                    assignments_list += more_text + "\n"

            conflicts_list = ""
            if conflicts:
                for c in conflicts[:3]:
                    reason = c.get('description') or get_text("shift_management.unknown_reason", language=lang)
                    conflicts_list += f"• #{c.get('shift_id')} - {reason}\n"
                if len(conflicts) > 3:
                    more_text = get_text("shift_management.and_more_conflicts", language=lang, count=len(conflicts) - 3)
                    conflicts_list += more_text + "\n"

            text = get_text("shift_management.ai_assignment_result", language=lang,
                           assigned=assigned_count,
                           conflicts=result.get('conflicts_found', len(conflicts)),
                           unassigned=failed_count,
                           assignments_list=assignments_list,
                           conflicts_list=conflicts_list)

            await callback.message.edit_text(
                text,
                reply_markup=get_executor_assignment_keyboard(lang),
                parse_mode="HTML"
            )

            await callback.answer(get_text("shift_management.ai_assignment_completed", language=lang))

    except Exception as e:
        logger.error(f"Ошибка ИИ-назначения: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.ai_assignment_error", language=lang), show_alert=True)


@router.callback_query(F.data == "bulk_assignment")
@require_role(['admin', 'manager'])
async def handle_bulk_assignment(callback: CallbackQuery, state: FSMContext, db: Session = None, user: User = None, roles: list = None):
    """Массовое назначение исполнителей"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            # Получаем статистику для массового назначения
            from datetime import datetime
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

            service = ShiftManagementService(db)
            total_unassigned = service.count_unassigned_shifts_from(today)
            available_executors = service.count_available_executors()

            text = get_text("shift_management.bulk_assignment_menu", language=lang,
                           unassigned=total_unassigned,
                           executors=available_executors)

            keyboard = [
                [InlineKeyboardButton(text=get_text("shift_management.bulk_auto_assign_button", language=lang),
                                    callback_data="bulk_auto_assign")],
                [InlineKeyboardButton(text=get_text("shift_management.bulk_by_spec_button", language=lang),
                                    callback_data="bulk_by_specialization")],
                [InlineKeyboardButton(text=get_text("shift_management.bulk_by_period_button", language=lang),
                                    callback_data="bulk_by_period")],
                [InlineKeyboardButton(text=get_text("shift_management.bulk_by_priority_button", language=lang),
                                    callback_data="bulk_by_priority")],
                [InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang),
                                    callback_data="executor_assignment")]
            ]

            await callback.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="HTML"
            )

            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка массового назначения: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.bulk_assignment_error", language=lang), show_alert=True)


@router.callback_query(F.data == "workload_analysis")
@require_role(['admin', 'manager'])
async def handle_workload_analysis(callback: CallbackQuery, state: FSMContext, db: Session = None, user: User = None, roles: list = None):
    """Анализ загруженности исполнителей"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            # Анализируем загруженность на ближайшие 7 дней
            end_date = date.today() + timedelta(days=7)

            service = ShiftManagementService(db)
            # Получаем статистику по исполнителям
            executor_stats = service.get_executor_workload_stats(datetime.now(), end_date)

            # Получаем исполнителей без смен
            assigned_executor_ids = [stat.id for stat in executor_stats]
            unassigned_executors = service.list_executors_without_shifts(assigned_executor_ids)

            # Build executor workload list
            workload_list = ""
            if executor_stats:
                for stat in executor_stats[:10]:  # Показываем топ-10
                    hours = stat.total_hours or 0
                    load_level = "🔴" if hours > 40 else "🟡" if hours > 20 else "🟢"
                    shifts_label = get_text("shift_management.shifts_count_label", language=lang)
                    hours_label = get_text("shift_management.hours_label", language=lang)
                    workload_list += (f"{load_level} <b>{stat.first_name} {stat.last_name}</b>\n"
                                     f"   {shifts_label}: {stat.shift_count}, {hours_label}: {hours:.1f}ч\n")

            # Build free executors list
            free_list = ""
            if unassigned_executors:
                for executor in unassigned_executors[:5]:  # Показываем первых 5
                    free_list += f"• {executor.first_name} {executor.last_name}\n"

                if len(unassigned_executors) > 5:
                    more_text = get_text("shift_management.and_more_executors", language=lang, count=len(unassigned_executors) - 5)
                    free_list += more_text + "\n"

            # Recommendation
            recommendation = ""
            if executor_stats:
                max_hours = max([stat.total_hours or 0 for stat in executor_stats])
                min_hours = min([stat.total_hours or 0 for stat in executor_stats])

                if max_hours - min_hours > 20:
                    recommendation = f"\n{get_text('shift_management.workload_imbalance_warning', language=lang)}"

            text = get_text("shift_management.workload_analysis_result", language=lang,
                           period_start=date.today().strftime('%d.%m.%Y'),
                           period_end=end_date.strftime('%d.%m.%Y'),
                           workload_list=workload_list,
                           free_count=len(unassigned_executors),
                           free_list=free_list,
                           recommendation=recommendation)

            await callback.message.edit_text(
                text,
                reply_markup=get_executor_assignment_keyboard(lang),
                parse_mode="HTML"
            )

            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка анализа загруженности: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.workload_analysis_error", language=lang), show_alert=True)


@router.callback_query(F.data == "redistribute_load")
@require_role(['admin', 'manager'])
async def handle_redistribute_load(callback: CallbackQuery, state: FSMContext, db: Session = None, user: User = None, roles: list = None):
    """Перераспределение нагрузки между исполнителями"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            from uk_management_bot.services.shift_assignment_service import ShiftAssignmentService
            assignment_service = ShiftAssignmentService(db)

            # FS-03: метод redistribute_workload на ShiftAssignmentService не
            # существует — балансировка выполняется синхронным
            # balance_executor_workload(). Прежний await на несуществующий метод
            # → AttributeError → кнопка падала. target_date по умолчанию = завтра
            # (балансируем planned-смены на следующий день, как задумано сервисом;
            # date.today() давал почти всегда пустой план → no-op).
            result = assignment_service.balance_executor_workload()

            if result.get('error'):
                await callback.message.edit_text(
                    get_text("shift_management.redistribute_error", language=lang, error=result['error']),
                    reply_markup=get_executor_assignment_keyboard(lang),
                    parse_mode="HTML"
                )
                await callback.answer()
                return

            # Нечего перераспределять (нет смен / уже сбалансировано / некуда) —
            # сервис возвращает {'message': ...} без rebalance_result.
            if result.get('message') and not result.get('rebalancing_performed'):
                await callback.message.edit_text(
                    f"🔄 {result['message']}",
                    reply_markup=get_executor_assignment_keyboard(lang),
                    parse_mode="HTML"
                )
                await callback.answer()
                return

            # Реальная форма: rebalance_result.redistributions[{shift_id,
            # from_executor, to_executor}] + initial_distribution.load_variance.
            rebalance = result.get('rebalance_result', {})
            redistributions = rebalance.get('redistributions', [])
            initial = result.get('initial_distribution', {})
            not_assigned = get_text("shift_management.not_assigned", language=lang)

            changes_list = ""
            for change in redistributions[:5]:
                old_id = change.get('from_executor') or not_assigned
                new_id = change.get('to_executor')
                changes_list += f"• №{change.get('shift_id')}: {old_id} → {new_id}\n"
            if len(redistributions) > 5:
                more_text = get_text("shift_management.and_more_changes", language=lang, count=len(redistributions) - 5)
                changes_list += f"{more_text}\n"

            text = get_text("shift_management.redistribute_result", language=lang,
                           redistributed=rebalance.get('redistributions_performed', len(redistributions)),
                           balance_improvement=0.0,
                           load_variance=float(initial.get('load_variance', 0) or 0),
                           changes_list=changes_list)

            await callback.message.edit_text(
                text,
                reply_markup=get_executor_assignment_keyboard(lang),
                parse_mode="HTML"
            )

            await callback.answer(get_text("shift_management.redistribute_completed", language=lang))

    except Exception as e:
        logger.error(f"Ошибка перераспределения нагрузки: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data == "schedule_conflicts")
@require_role(['admin', 'manager'])
async def handle_schedule_conflicts(callback: CallbackQuery, state: FSMContext, db: Session = None, user: User = None, roles: list = None):
    """Анализ конфликтов расписания"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            # Ищем конфликты в расписании на ближайшие 7 дней
            end_date = date.today() + timedelta(days=7)

            # Находим пересекающиеся смены у одного исполнителя
            conflicts = []

            shifts = ShiftManagementService(db).list_assigned_shifts_between(datetime.now(), end_date)

            # FS-03: модель Shift хранит start_time/end_time как полные DateTime
            # и не имеет полей `date`/`executor`/`executor_id` (исполнитель —
            # `user_id`/`user`). Прежний код читал s.executor_id и shift.date →
            # AttributeError → кнопка падала. Группируем по user_id (смены уже
            # упорядочены сервисом по user_id, start_time) и сравниваем datetime
            # напрямую: пересечение (end1 > start2) и короткий перерыв (<1ч).
            from itertools import groupby
            for _executor_id, executor_shifts in groupby(shifts, key=lambda s: s.user_id):
                executor_shifts = list(executor_shifts)
                for i in range(len(executor_shifts) - 1):
                    shift1 = executor_shifts[i]
                    shift2 = executor_shifts[i + 1]

                    if not shift1.end_time:
                        continue

                    if shift1.end_time > shift2.start_time:
                        conflicts.append({
                            'executor': shift1.user,
                            'shift1': shift1,
                            'shift2': shift2,
                            'type': 'time_overlap'
                        })
                    else:
                        break_hours = (shift2.start_time - shift1.end_time).total_seconds() / 3600
                        if 0 < break_hours < 1:  # Менее часа перерыва
                            conflicts.append({
                                'executor': shift1.user,
                                'shift1': shift1,
                                'shift2': shift2,
                                'type': 'short_break',
                                'break_hours': break_hours
                            })

            conflicts_list = ""
            no_conflicts_msg = ""

            if not conflicts:
                no_conflicts_msg = get_text("shift_management.no_conflicts_found", language=lang)
            else:
                # Заголовок секции теперь в conflicts_list (а не хардкодом в шаблоне),
                # иначе при 0 конфликтов он висел пустым.
                conflicts_list = get_text("shift_management.conflicts_found_header", language=lang) + "\n\n"

                def _hm(dt):
                    return dt.strftime('%H:%M') if dt else "—"

                for i, conflict in enumerate(conflicts[:5], 1):  # Показываем первые 5
                    executor = conflict['executor']
                    shift1 = conflict['shift1']
                    shift2 = conflict['shift2']
                    conflict_type = conflict['type']

                    name = f"{executor.first_name} {executor.last_name}" if executor else "—"
                    conflicts_list += f"<b>{i}. {name}</b>\n"
                    conflicts_list += f"📅 {shift1.start_time.strftime('%d.%m.%Y')}\n"

                    if conflict_type == 'time_overlap':
                        conflicts_list += f"❌ {get_text('shift_management.time_overlap_label', language=lang)}:\n"
                        conflicts_list += f"   {_hm(shift1.start_time)}-{_hm(shift1.end_time)}\n"
                        conflicts_list += f"   {_hm(shift2.start_time)}-{_hm(shift2.end_time)}\n"
                    elif conflict_type == 'short_break':
                        break_hours = conflict['break_hours']
                        conflicts_list += f"⚡ {get_text('shift_management.short_break_label', language=lang, hours=break_hours)}:\n"
                        conflicts_list += f"   {_hm(shift1.start_time)}-{_hm(shift1.end_time)}\n"
                        conflicts_list += f"   {_hm(shift2.start_time)}-{_hm(shift2.end_time)}\n"

                    conflicts_list += "\n"

                if len(conflicts) > 5:
                    more_text = get_text("shift_management.and_more_conflicts", language=lang, count=len(conflicts) - 5)
                    conflicts_list += f"{more_text}\n\n"

                conflicts_list += get_text("shift_management.redistribute_recommendation", language=lang)

            text = get_text("shift_management.conflicts_analysis_result", language=lang,
                           period_start=date.today().strftime('%d.%m.%Y'),
                           period_end=end_date.strftime('%d.%m.%Y'),
                           conflicts_count=len(conflicts),
                           conflicts_list=conflicts_list,
                           no_conflicts=no_conflicts_msg)

            await callback.message.edit_text(
                text,
                reply_markup=get_executor_assignment_keyboard(lang),
                parse_mode="HTML"
            )

            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка анализа конфликтов: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.error_generic", language=lang), show_alert=True)


# Additional handlers for bulk assignment and shift selection

@router.callback_query(F.data == "bulk_auto_assign")
@require_role(['admin', 'manager'])
async def handle_bulk_auto_assign(callback: CallbackQuery, state: FSMContext, db: Session = None, user: User = None, roles: list = None):
    """Автоматическое назначение всех смен"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            from uk_management_bot.services.shift_assignment_service import ShiftAssignmentService
            assignment_service = ShiftAssignmentService(db)

            # Получаем все неназначенные смены на месяц вперед
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            month_end = today + timedelta(days=30)

            unassigned_shifts = ShiftManagementService(db).list_unassigned_shifts_window(today, month_end)

            if not unassigned_shifts:
                await callback.message.edit_text(
                    get_text("shift_management.all_shifts_assigned_30days", language=lang),
                    reply_markup=get_executor_assignment_keyboard(lang),
                    parse_mode="HTML"
                )
                await callback.answer()
                return

            # Запускаем автоматическое назначение на все неназначенные смены
            result = assignment_service.auto_assign_executors_to_shifts(
                shifts=unassigned_shifts,
                force_reassign=False
            )

            if result.get('error'):
                await callback.message.edit_text(
                    get_text("shift_management.bulk_auto_assign_error_msg", language=lang, error=result['error']),
                    reply_markup=get_executor_assignment_keyboard(lang),
                    parse_mode="HTML"
                )
                await callback.answer()
                return

            assignments = result.get('assignments', [])
            unassigned = result.get('unassigned_shifts', [])

            efficiency = (len(assignments) / (len(assignments) + len(unassigned)) * 100) if assignments else 0
            efficiency_text = f"📊 <b>{get_text('shift_management.efficiency_label', language=lang)}:</b> {efficiency:.1f}%\n\n" if assignments else ""
            warning_text = get_text("shift_management.unassigned_need_manual", language=lang) if unassigned else ""

            text = get_text("shift_management.bulk_auto_assign_result", language=lang,
                           assigned=len(assignments),
                           unassigned=len(unassigned),
                           efficiency=efficiency_text,
                           warning=warning_text)

            await callback.message.edit_text(
                text,
                reply_markup=get_executor_assignment_keyboard(lang),
                parse_mode="HTML"
            )

            await callback.answer(get_text("shift_management.bulk_auto_assign_completed", language=lang))

    except Exception as e:
        logger.error(f"Ошибка автоматического назначения: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.bulk_auto_assign_error", language=lang), show_alert=True)


@router.callback_query(F.data == "bulk_by_specialization")
@require_role(['admin', 'manager'])
async def handle_bulk_by_specialization(callback: CallbackQuery, state: FSMContext, db: Session = None, user: User = None, roles: list = None):
    """Массовое назначение по специализациям"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            from uk_management_bot.services.shift_assignment_service import ShiftAssignmentService
            assignment_service = ShiftAssignmentService(db)

            # Получаем все неназначенные смены
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            unassigned_shifts = ShiftManagementService(db).list_unassigned_shifts_from(today)

            if not unassigned_shifts:
                await callback.message.edit_text(
                    get_text("shift_management.all_shifts_assigned_now", language=lang),
                    reply_markup=get_executor_assignment_keyboard(lang),
                    parse_mode="HTML"
                )
                await callback.answer()
                return

            # Группируем смены по специализациям
            specialization_groups = {}
            for shift in unassigned_shifts:
                if shift.specialization_focus:
                    if isinstance(shift.specialization_focus, list):
                        specs = tuple(sorted(shift.specialization_focus))
                    else:
                        specs = ("universal",)
                else:
                    specs = ("universal",)

                if specs not in specialization_groups:
                    specialization_groups[specs] = []
                specialization_groups[specs].append(shift)

            # Назначаем по группам специализаций
            total_assigned = 0
            total_failed = 0

            for specs, shifts_group in specialization_groups.items():
                result = assignment_service.auto_assign_executors_to_shifts(
                    shifts=shifts_group,
                    force_reassign=False
                )
                if result.get('assignments'):
                    total_assigned += len(result['assignments'])
                if result.get('unassigned_shifts'):
                    total_failed += len(result['unassigned_shifts'])

            efficiency = (total_assigned / (total_assigned + total_failed) * 100) if total_assigned > 0 else 0
            efficiency_text = f"📊 <b>{get_text('shift_management.efficiency_label', language=lang)}:</b> {efficiency:.1f}%\n" if total_assigned > 0 else ""

            text = get_text("shift_management.bulk_by_spec_result", language=lang,
                           assigned=total_assigned,
                           failed=total_failed,
                           groups=len(specialization_groups),
                           efficiency=efficiency_text)

            await callback.message.edit_text(
                text,
                reply_markup=get_executor_assignment_keyboard(lang),
                parse_mode="HTML"
            )

            await callback.answer(get_text("shift_management.bulk_by_spec_completed", language=lang))

    except Exception as e:
        logger.error(f"Ошибка назначения по специализациям: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.bulk_by_spec_error", language=lang), show_alert=True)


@router.callback_query(F.data == "bulk_by_period")
@require_role(['admin', 'manager'])
async def handle_bulk_by_period(callback: CallbackQuery, state: FSMContext, db: Session = None, user: User = None, roles: list = None):
    """Массовое назначение на период"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            from uk_management_bot.services.shift_assignment_service import ShiftAssignmentService
            assignment_service = ShiftAssignmentService(db)

            # Получаем смены на следующие 7 дней
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            week_end = today + timedelta(days=7)

            unassigned_shifts = ShiftManagementService(db).list_unassigned_shifts_window(today, week_end)

            if not unassigned_shifts:
                await callback.message.edit_text(
                    get_text("shift_management.all_shifts_assigned_7days", language=lang),
                    reply_markup=get_executor_assignment_keyboard(lang),
                    parse_mode="HTML"
                )
                await callback.answer()
                return

            # Назначаем все смены разом
            result = assignment_service.auto_assign_executors_to_shifts(
                shifts=unassigned_shifts,
                force_reassign=False
            )

            if result.get('error'):
                await callback.message.edit_text(
                    get_text("shift_management.bulk_by_period_error_msg", language=lang, error=result['error']),
                    reply_markup=get_executor_assignment_keyboard(lang),
                    parse_mode="HTML"
                )
                await callback.answer()
                return

            assignments = result.get('assignments', [])
            unassigned = result.get('unassigned_shifts', [])

            efficiency = (len(assignments) / (len(assignments) + len(unassigned)) * 100) if assignments else 0
            efficiency_text = f"📊 <b>{get_text('shift_management.efficiency_label', language=lang)}:</b> {efficiency:.1f}%\n\n" if assignments else ""
            warning_text = get_text("shift_management.unassigned_need_manual", language=lang) if unassigned else ""

            text = get_text("shift_management.bulk_by_period_result", language=lang,
                           assigned=len(assignments),
                           unassigned=len(unassigned),
                           efficiency=efficiency_text,
                           warning=warning_text)

            await callback.message.edit_text(
                text,
                reply_markup=get_executor_assignment_keyboard(lang),
                parse_mode="HTML"
            )

            await callback.answer(get_text("shift_management.bulk_by_period_completed", language=lang))

    except Exception as e:
        logger.error(f"Ошибка назначения на период: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.bulk_by_period_error", language=lang), show_alert=True)


@router.callback_query(F.data == "bulk_by_priority")
@require_role(['admin', 'manager'])
async def handle_bulk_by_priority(callback: CallbackQuery, state: FSMContext, db: Session = None, user: User = None, roles: list = None):
    """Массовое назначение по приоритету"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            from uk_management_bot.services.shift_assignment_service import ShiftAssignmentService
            assignment_service = ShiftAssignmentService(db)

            # Получаем все неназначенные смены
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            unassigned_shifts = ShiftManagementService(db).list_unassigned_shifts_from_ordered(today)  # Сортируем по времени (раньше = важнее)

            if not unassigned_shifts:
                await callback.message.edit_text(
                    get_text("shift_management.all_shifts_assigned_now", language=lang),
                    reply_markup=get_executor_assignment_keyboard(lang),
                    parse_mode="HTML"
                )
                await callback.answer()
                return

            # Обрабатываем первые 20 смен по приоритету
            priority_shifts = unassigned_shifts[:20]

            # Назначаем в порядке приоритета
            result = assignment_service.auto_assign_executors_to_shifts(
                shifts=priority_shifts,
                force_reassign=False
            )

            assignments = result.get('assignments', [])
            unassigned = result.get('unassigned_shifts', [])

            efficiency = (len(assignments) / (len(assignments) + len(unassigned)) * 100) if assignments else 0
            efficiency_text = f"📊 <b>{get_text('shift_management.efficiency_label', language=lang)}:</b> {efficiency:.1f}%\n" if assignments else ""

            remaining_text = ""
            if len(unassigned_shifts) > 20:
                remaining_text = f"\n<b>{get_text('shift_management.remaining_unassigned_label', language=lang)}:</b> {len(unassigned_shifts) - 20} {get_text('shift_management.shifts_count_label', language=lang)}"

            text = get_text("shift_management.bulk_by_priority_result", language=lang,
                           processed=len(priority_shifts),
                           assigned=len(assignments),
                           unassigned=len(unassigned),
                           efficiency=efficiency_text,
                           remaining=remaining_text)

            await callback.message.edit_text(
                text,
                reply_markup=get_executor_assignment_keyboard(lang),
                parse_mode="HTML"
            )

            await callback.answer(get_text("shift_management.bulk_by_priority_completed", language=lang))

    except Exception as e:
        logger.error(f"Ошибка назначения по приоритету: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.bulk_by_priority_error", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("select_shift_for_assignment:"))
@require_role(['admin', 'manager'])
async def handle_select_shift_for_assignment(callback: CallbackQuery, state: FSMContext, db: Session = None, user: User = None, roles: list = None):
    """Выбор конкретной смены для назначения исполнителя"""
    try:
        shift_id = int(callback.data.split(":")[1])
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
            service = ShiftManagementService(db)

            # Получаем смену
            shift = service.get_shift(shift_id)
            if not shift:
                await callback.answer(get_text("shift_management.shift_not_found", language=lang), show_alert=True)
                return

            # Получаем доступных исполнителей для этой смены
            # Ищем пользователей, у которых есть роль 'executor' в JSON-поле roles
            all_users = service.list_approved_users()

            available_executors = []
            for user in all_users:
                try:
                    import json
                    if user.roles:
                        parsed_roles = json.loads(user.roles)
                        if isinstance(parsed_roles, list) and 'executor' in parsed_roles:
                            available_executors.append(user)
                    elif user.active_role == 'executor':
                        available_executors.append(user)
                except Exception:
                    # Если не удалось распарсить JSON, проверяем active_role
                    if user.active_role == 'executor':
                        available_executors.append(user)

            # Фильтруем по специализации если указана в specialization_focus
            if shift.specialization_focus and isinstance(shift.specialization_focus, list):
                import json
                filtered_executors = []
                for executor in available_executors:
                    # Парсим специализации исполнителя из JSON
                    try:
                        if executor.specialization:
                            if isinstance(executor.specialization, str):
                                executor_specs = json.loads(executor.specialization)
                            else:
                                executor_specs = executor.specialization

                            # Проверяем пересечение специализаций
                            if isinstance(executor_specs, list):
                                # Если хотя бы одна специализация совпадает - подходит
                                if any(spec in executor_specs for spec in shift.specialization_focus):
                                    filtered_executors.append(executor)
                            else:
                                # Если не список - пропускаем исполнителя
                                continue
                        # Если специализация не указана - не добавляем в фильтрованный список
                    except (json.JSONDecodeError, TypeError):
                        # Если не удалось распарсить - пропускаем исполнителя
                        continue

                available_executors = filtered_executors

            end_time_str = shift.end_time.strftime('%H:%M') if shift.end_time else "—"
            shift_time = f"{shift.start_time.strftime('%d.%m.%Y')} {shift.start_time.strftime('%H:%M')}-{end_time_str}"

            # Переводим специализации
            spec_text = translate_specializations(shift.specialization_focus, lang)
            zone_text = shift.geographic_zone or get_text("shift_management.zone_not_specified", language=lang)

            if not available_executors:
                text = get_text("shift_management.no_available_executors", language=lang,
                              shift_time=shift_time,
                              specialization=spec_text,
                              zone=zone_text)

                keyboard = [[InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang), callback_data="assign_to_shift")]]
            else:
                keyboard = []
                for executor in available_executors[:10]:  # Показываем первых 10
                    # Проверяем загруженность исполнителя в этот день
                    from datetime import datetime, timedelta
                    shift_date = shift.start_time.date()
                    day_start = datetime.combine(shift_date, datetime.min.time())
                    day_end = day_start + timedelta(days=1)

                    day_shifts = service.count_shifts_for_user_on_day(executor.id, day_start, day_end)

                    load_indicator = "🔴" if day_shifts >= 3 else "🟡" if day_shifts >= 1 else "🟢"
                    shifts_label = get_text("shift_management.shifts_count_label", language=lang)

                    keyboard.append([InlineKeyboardButton(
                        text=f"{load_indicator} {executor.first_name} {executor.last_name} ({day_shifts} {shifts_label})",
                        callback_data=f"assign_executor_to_shift:{shift_id}:{executor.id}"
                    )])

                keyboard.append([InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang), callback_data="assign_to_shift")])

                text = get_text("shift_management.select_executor_for_shift", language=lang,
                              shift_time=shift_time,
                              specialization=spec_text,
                              zone=zone_text,
                              count=len(available_executors))

            await callback.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="HTML"
            )

            await state.set_state(ExecutorAssignmentStates.viewing_available_executors)
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка выбора смены для назначения: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.select_shift_error", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("assign_executor_to_shift:"))
@require_role(['admin', 'manager'])
async def handle_assign_executor_to_shift(callback: CallbackQuery, state: FSMContext, db: Session = None, user: User = None, roles: list = None):
    """Назначение исполнителя на смену"""
    try:
        parts = callback.data.split(":")
        shift_id = int(parts[1])
        executor_id = int(parts[2])

        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
            service = ShiftManagementService(db)

            # Получаем смену и исполнителя
            shift = service.get_shift(shift_id)
            executor = service.get_user(executor_id)

            if not shift or not executor:
                await callback.answer(get_text("shift_management.shift_or_executor_not_found", language=lang), show_alert=True)
                return

            from datetime import timedelta
            import json

            # ========== КРИТИЧЕСКАЯ ПРОВЕРКА: СООТВЕТСТВИЕ СПЕЦИАЛИЗАЦИЙ ==========
            # Проверяем, что у исполнителя есть ВСЕ требуемые для смены специализации
            shift_specs = shift.specialization_focus if shift.specialization_focus else []
            if isinstance(shift_specs, str):
                try:
                    shift_specs = json.loads(shift_specs)
                except Exception:
                    shift_specs = [shift_specs] if shift_specs else []

            # Получаем специализации исполнителя
            executor_specs = []
            if executor.specialization:
                if isinstance(executor.specialization, list):
                    executor_specs = executor.specialization
                elif isinstance(executor.specialization, str):
                    try:
                        executor_specs = json.loads(executor.specialization)
                    except (json.JSONDecodeError, TypeError):
                        executor_specs = [executor.specialization]

            # Проверяем наличие всех требуемых специализаций
            if shift_specs:  # Если у смены указаны специализации
                missing_specs = set(shift_specs) - set(executor_specs)
                if missing_specs:
                    from uk_management_bot.utils.specializations import translate_specializations
                    missing_text = translate_specializations(list(missing_specs), lang)
                    available_text = translate_specializations(executor_specs, lang) if executor_specs else get_text("shift_management.no_specs", language=lang)
                    required_text = translate_specializations(shift_specs, lang)

                    await callback.message.edit_text(
                        get_text("shift_management.spec_mismatch", language=lang,
                                executor_name=f"{executor.first_name} {executor.last_name}",
                                required=required_text,
                                available=available_text,
                                missing=missing_text),
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text=get_text("shift_management.select_another_button", language=lang), callback_data=f"select_shift_for_assignment:{shift_id}")],
                            [InlineKeyboardButton(text=get_text("shift_management.cancel_button", language=lang), callback_data="back_to_planning")]
                        ]),
                        parse_mode="HTML"
                    )
                    await callback.answer(get_text("shift_management.spec_mismatch_popup", language=lang), show_alert=True)
                    return

            # ========== ПРОВЕРКА КОНФЛИКТОВ ВРЕМЕНИ И СПЕЦИАЛИЗАЦИЙ ==========
            # ИЗМЕНЕНО: Проверяем конфликты специализаций, а не просто времени
            # Разрешаем перекрывающиеся смены с разными специализациями

            # Определяем конец смены (если не указан, считаем 8 часов)
            shift_end = shift.end_time if shift.end_time else shift.start_time + timedelta(hours=8)

            # Получаем все перекрывающиеся смены
            overlapping_shifts = service.list_overlapping_shifts(
                executor_id, shift_id, shift.start_time, shift_end
            )

            # Проверяем пересечение специализаций
            has_real_conflict = False
            if overlapping_shifts:
                # Получаем специализации текущей смены
                current_specs = shift.specialization_focus if shift.specialization_focus else []
                if isinstance(current_specs, str):
                    try:
                        current_specs = json.loads(current_specs)
                    except Exception:
                        current_specs = [current_specs]

                # Проверяем каждую перекрывающуюся смену
                for overlapping_shift in overlapping_shifts:
                    overlap_specs = overlapping_shift.specialization_focus if overlapping_shift.specialization_focus else []
                    if isinstance(overlap_specs, str):
                        try:
                            overlap_specs = json.loads(overlap_specs)
                        except Exception:
                            overlap_specs = [overlap_specs]

                    # Если есть пересечение специализаций - это настоящий конфликт
                    common_specs = set(current_specs) & set(overlap_specs)
                    if common_specs:
                        has_real_conflict = True
                        break

            if has_real_conflict:
                shift_date_str = shift.start_time.strftime('%d.%m.%Y')
                await callback.message.edit_text(
                    get_text("shift_management.spec_conflict", language=lang,
                            executor_name=f"{executor.first_name} {executor.last_name}",
                            date=shift_date_str),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=get_text("shift_management.force_assign_button", language=lang), callback_data=f"force_assign:{shift_id}:{executor_id}")],
                        [InlineKeyboardButton(text=get_text("shift_management.cancel_button", language=lang), callback_data=f"select_shift_for_assignment:{shift_id}")]
                    ]),
                    parse_mode="HTML"
                )
                await callback.answer()
                return

            # Назначаем исполнителя
            service.assign_executor(shift, executor_id)

            # Отправляем уведомление исполнителю
            try:
                from uk_management_bot.services.notification_service import NotificationService
                notification_service = NotificationService(db)
                await notification_service.send_shift_assignment_notification(
                    executor_id=executor_id,
                    shift_id=shift_id
                )
            except Exception as e:
                logger.warning(f"Не удалось отправить уведомление: {e}")

            # Переводим специализацию
            spec_text = translate_specializations(shift.specialization_focus, lang)

            shift_date_str = shift.start_time.strftime('%d.%m.%Y')
            start_time_str = shift.start_time.strftime('%H:%M')
            end_time_str = shift.end_time.strftime('%H:%M') if shift.end_time else "—"

            await callback.message.edit_text(
                get_text("shift_management.executor_assigned_success", language=lang,
                        date=shift_date_str,
                        start_time=start_time_str,
                        end_time=end_time_str,
                        executor_name=f"{executor.first_name} {executor.last_name}",
                        specialization=spec_text),
                reply_markup=get_executor_assignment_keyboard(lang),
                parse_mode="HTML"
            )

            await callback.answer(get_text("shift_management.assignment_completed_popup", language=lang))

    except Exception as e:
        logger.error(f"Ошибка назначения исполнителя: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.assignment_error", language=lang), show_alert=True)
        if db:
            ShiftManagementService(db).rollback()


@router.callback_query(F.data.startswith("force_assign:"))
@require_role(['admin', 'manager'])
async def handle_force_assign(callback: CallbackQuery, state: FSMContext, db: Session = None, user: User = None, roles: list = None):
    """Принудительное назначение с конфликтом расписания"""
    try:
        parts = callback.data.split(":")
        shift_id = int(parts[1])
        executor_id = int(parts[2])

        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
            service = ShiftManagementService(db)

            # Получаем смену и исполнителя
            shift = service.get_shift(shift_id)
            executor = service.get_user(executor_id)

            if not shift or not executor:
                await callback.answer(get_text("shift_management.shift_or_executor_not_found", language=lang), show_alert=True)
                return

            # КРИТИЧЕСКАЯ ПРОВЕРКА: даже при принудительном назначении проверяем специализации
            import json
            shift_specs = shift.specialization_focus if shift.specialization_focus else []
            if isinstance(shift_specs, str):
                try:
                    shift_specs = json.loads(shift_specs)
                except Exception:
                    shift_specs = [shift_specs] if shift_specs else []

            # Получаем специализации исполнителя
            executor_specs = []
            if executor.specialization:
                if isinstance(executor.specialization, list):
                    executor_specs = executor.specialization
                elif isinstance(executor.specialization, str):
                    try:
                        executor_specs = json.loads(executor.specialization)
                    except (json.JSONDecodeError, TypeError):
                        executor_specs = [executor.specialization]

            # Даже при принудительном назначении НЕЛЬЗЯ назначить исполнителя без нужной специализации
            if shift_specs:
                missing_specs = set(shift_specs) - set(executor_specs)
                if missing_specs:
                    from uk_management_bot.utils.specializations import translate_specializations
                    required_text = translate_specializations(shift_specs, lang)
                    missing_text = translate_specializations(list(missing_specs), lang)

                    await callback.message.edit_text(
                        get_text("shift_management.force_assign_impossible", language=lang,
                                executor_name=f"{executor.first_name} {executor.last_name}",
                                required=required_text,
                                missing=missing_text),
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text=get_text("shift_management.back_button", language=lang), callback_data=f"select_shift_for_assignment:{shift_id}")]
                        ]),
                        parse_mode="HTML"
                    )
                    await callback.answer(get_text("shift_management.missing_specs_popup", language=lang), show_alert=True)
                    return

            # Назначаем исполнителя принудительно
            service.force_assign_executor(
                shift,
                executor_id,
                f"\n[КОНФЛИКТ РАСПИСАНИЯ] Назначено принудительно {date.today().strftime('%d.%m.%Y')}",
            )

            shift_date = shift.start_time.date().strftime('%d.%m.%Y')
            start_time = shift.start_time.strftime('%H:%M')
            end_time = shift.end_time.strftime('%H:%M')

            await callback.message.edit_text(
                get_text("shift_management.force_assigned_success", language=lang,
                        date=shift_date,
                        start_time=start_time,
                        end_time=end_time,
                        executor_name=f"{executor.first_name} {executor.last_name}"),
                reply_markup=get_executor_assignment_keyboard(lang),
                parse_mode="HTML"
            )

            await callback.answer(get_text("shift_management.force_assigned_popup", language=lang))

    except Exception as e:
        logger.error(f"Ошибка принудительного назначения: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.force_assign_error", language=lang), show_alert=True)
        if db:
            ShiftManagementService(db).rollback()


@router.callback_query(F.data == "executor_assignment")
@require_role(['admin', 'manager'])
async def handle_executor_assignment_back(callback: CallbackQuery, state: FSMContext, db: Session = None, user: User = None, roles: list = None):
    """Возврат к меню назначения исполнителей"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            await callback.message.edit_text(
                get_text("shift_management.executor_assignment_menu_title", language=lang),
                reply_markup=get_executor_assignment_keyboard(lang),
                parse_mode="HTML"
            )

            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка возврата к назначению исполнителей: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.executor_assignment_back_error", language=lang), show_alert=True)