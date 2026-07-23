import logging
from datetime import date, timedelta, timezone

from aiogram import F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session

from uk_management_bot.database.models.user import User
from uk_management_bot.services.shift_management_service import ShiftManagementService
from uk_management_bot.keyboards.shift_management import (
    get_executor_assignment_keyboard,
)
from uk_management_bot.states.shift_management import ExecutorAssignmentStates
from uk_management_bot.middlewares.auth import require_role
from uk_management_bot.utils.helpers import get_user_language, get_text
from uk_management_bot.utils.auth_helpers import parse_roles_safe
from uk_management_bot.utils.datetime_utils import utc_now

from ._router import router
from .shared import _db_scope, translate_specializations

logger = logging.getLogger(__name__)


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
            today = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
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
            today = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
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
            today = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
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
            today = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
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
                # COD-01: канонический парсер ролей (JSON+CSV)
                if 'executor' in parse_roles_safe(user.roles) or user.active_role == 'executor':
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
                    from datetime import datetime
                    shift_date = shift.start_time.date()
                    # AUD5-CODE-3: naive combine() уходил в запрос по Shift.start_time
                    # (timestamptz) через count_shifts_for_user_on_day — aware UTC.
                    day_start = datetime.combine(shift_date, datetime.min.time(), tzinfo=timezone.utc)
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
