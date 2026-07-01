import logging
from datetime import date, timedelta

from aiogram import F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from uk_management_bot.services.shift_planning_service import ShiftPlanningService
from uk_management_bot.services.shift_management_service import ShiftManagementService
from uk_management_bot.keyboards.shift_management import (
    get_main_shift_menu,
    get_planning_menu,
    get_auto_planning_keyboard,
)
from uk_management_bot.states.shift_management import ShiftManagementStates
from uk_management_bot.middlewares.auth import require_role
from uk_management_bot.utils.helpers import get_user_language, get_text

from ._router import router
from .shared import _db_scope, _get_confirm_keyboard

logger = logging.getLogger(__name__)


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
