import logging
from datetime import date, timedelta

from aiogram import F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session

from uk_management_bot.database.models.user import User
from uk_management_bot.services.shift_management_service import ShiftManagementService
from uk_management_bot.keyboards.shift_management import (
    get_executor_assignment_keyboard,
)
from uk_management_bot.middlewares.auth import require_role
from uk_management_bot.utils.helpers import get_user_language, get_text
from uk_management_bot.utils.datetime_utils import utc_now

from ._router import router
from .shared import _db_scope, _format_end_label, translate_specializations

logger = logging.getLogger(__name__)


@router.callback_query(F.data == "assign_to_shift")
@require_role(['admin', 'manager'])
async def handle_assign_to_shift(callback: CallbackQuery, state: FSMContext, db: Session = None, user: User = None, roles: list = None):
    """Назначить исполнителя на конкретную смену"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            # Получаем неназначенные смены
            now = utc_now()
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
            end_dt = utc_now() + timedelta(days=7)
            unassigned_shifts = ShiftManagementService(db).list_unassigned_shifts_window(
                utc_now(), end_dt
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
            today = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)

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
            executor_stats = service.get_executor_workload_stats(utc_now(), end_date)

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

            shifts = ShiftManagementService(db).list_assigned_shifts_between(utc_now(), end_date)

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
