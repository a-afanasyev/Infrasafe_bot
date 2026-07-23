import logging
from datetime import date, timedelta

from aiogram import F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from uk_management_bot.services.shift_planning_service import ShiftPlanningService
from uk_management_bot.services.shift_management_service import ShiftManagementService
from uk_management_bot.services.template_manager import TemplateManager
from uk_management_bot.keyboards.shift_management import (
    get_planning_menu,
    get_template_selection_keyboard,
    get_date_selection_keyboard,
)
from uk_management_bot.states.shift_management import ShiftManagementStates
from uk_management_bot.middlewares.auth import require_role
from uk_management_bot.utils.helpers import get_user_language, get_text
from uk_management_bot.utils.datetime_utils import utc_now

from ._router import router
from .shared import _db_scope, _get_confirm_keyboard

logger = logging.getLogger(__name__)


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
            timestamp = utc_now().strftime('%H:%M:%S')

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
