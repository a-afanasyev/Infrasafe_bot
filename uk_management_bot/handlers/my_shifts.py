"""
Detailed shift interface ("📋 Мои смены") — schedule, stats, time tracking.

Uses: Shift.planned_start_time, Shift.planned_end_time (planned times)
Related: shifts.py handles the operational menu ("🔄 Смена")
"""

from datetime import datetime, date, timedelta

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from uk_management_bot.database.session import get_db
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_transfer import ShiftTransfer
from uk_management_bot.database.models.user import User
from uk_management_bot.keyboards.my_shifts import (
    get_my_shifts_menu,
    get_shift_list_keyboard,
    get_shift_actions_keyboard
)
from uk_management_bot.keyboards.shift_transfer import (
    shift_selection_keyboard,
    transfers_list_keyboard
)
from uk_management_bot.states.my_shifts import MyShiftsStates
from uk_management_bot.middlewares.auth import require_role
from uk_management_bot.utils.helpers import get_text
from sqlalchemy import and_, func, or_
# Single Source of Truth for button texts - TASK 17
from uk_management_bot.utils.button_texts import get_my_shifts_texts
import logging

logger = logging.getLogger(__name__)
router = Router()

# Константа для фильтрации сообщений "Мои смены"
MY_SHIFTS_TEXTS = get_my_shifts_texts()


@router.message(Command("my_shifts"))
async def cmd_my_shifts(message: Message, state: FSMContext, language: str = "ru", db=None):
    """Главное меню моих смен"""
    own_db = db is None  # ARCH-013: закрываем только свою сессию (не middleware)
    try:
        if not db:
            db = next(get_db())
        lang = language
        
        await message.answer(
            get_text("my_shifts.handlers.main_menu", language=lang),
            reply_markup=get_my_shifts_menu(lang),
            parse_mode="HTML"
        )
        
        await state.set_state(MyShiftsStates.main_menu)
        
    except Exception as e:
        logger.error(f"Ошибка команды /my_shifts: {e}")
        await message.answer(get_text("my_shifts.handlers.error_loading", language=language))
    finally:
        if own_db and db:
            db.close()


@router.message(F.text.in_(MY_SHIFTS_TEXTS))
async def handle_my_shifts_button(message: Message, state: FSMContext, language: str = "ru"):
    """Обработчик кнопки 'Мои смены'"""
    await cmd_my_shifts(message, state, language=language)


@router.callback_query(F.data == "view_current_shifts")
@require_role(['executor'])
async def handle_current_shifts(callback: CallbackQuery, state: FSMContext, language: str = "ru", db=None, user: User = None, roles: list = None):
    """Просмотр текущих смен.

    BUG-BOT-007: ранее filter использовал ``callback.from_user.id`` (telegram_id)
    напрямую как ``Shift.user_id`` — но ``Shift.user_id`` это FK на ``users.id``
    (внутренний DB id), а не telegram_id. Это давало пустую выборку и handler
    показывал "no_current_shifts". Дополнительно для пустой выборки текст был
    про "Заявка не найдена" в шапке — переключаем на корректный shift-контекст.
    """
    own_db = db is None  # ARCH-013: закрываем только свою сессию
    try:
        if not db:
            db = next(get_db())
        lang = language

        # BUG-BOT-007: получаем внутренний user.id (Shift.user_id — FK на users.id),
        # как в BUG-BOT-005. callback.from_user.id — это telegram_id.
        if user is None:
            user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if user is None:
            await callback.answer(get_text("my_shifts.handlers.error_occurred", language=lang), show_alert=True)
            return

        # Получаем смены на сегодня и завтра
        today = date.today()
        tomorrow = today + timedelta(days=1)

        current_shifts = db.query(Shift).filter(
            and_(
                Shift.user_id == user.id,
                func.date(Shift.planned_start_time).in_([today, tomorrow]),
                Shift.status.in_(['planned', 'active'])
            )
        ).order_by(Shift.planned_start_time).all()

        if not current_shifts:
            await callback.message.edit_text(
                get_text("my_shifts.handlers.no_current_shifts", language=lang),
                reply_markup=get_my_shifts_menu(lang),
                parse_mode="HTML"
            )
            await callback.answer()
            return
        
        # Формируем список смен
        shifts_text = f"📅 <b>{get_text('my_shifts.handlers.your_current_shifts', language=lang)}</b>\n\n"

        for shift in current_shifts:
            shift_date = shift.planned_start_time.date()
            is_today = shift_date == today
            date_prefix = f"🔥 {get_text('my_shifts.handlers.today', language=lang)}" if is_today else f"📅 {get_text('my_shifts.handlers.tomorrow', language=lang)}"
            
            start_time = shift.planned_start_time.strftime("%H:%M")
            end_time = shift.planned_end_time.strftime("%H:%M") if shift.planned_end_time else "?"
            
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
    finally:
        if own_db and db:
            db.close()


@router.callback_query(F.data == "view_week_schedule")
@require_role(['admin', 'manager', 'executor'])
async def handle_week_schedule(callback: CallbackQuery, state: FSMContext, language: str = "ru", db=None, roles: list = None, user: User = None):
    """Просмотр расписания на неделю.

    BUG-BOT-005: разрешён доступ executor + manager + admin. Для executor query
    фильтруется по его собственному `Shift.user_id`. Manager/admin — видит все смены.
    """
    own_db = db is None  # ARCH-013: закрываем только свою сессию
    try:
        if not db:
            db = next(get_db())
        lang = language

        # BUG-BOT-005: Получаем внутренний user.id (Shift.user_id — FK на users.id,
        # а не telegram_id). Раньше сравнивалось с callback.from_user.id (telegram_id),
        # что давало пустую выборку даже для существующих смен.
        if user is None:
            user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if user is None:
            await callback.answer(get_text("my_shifts.handlers.error_occurred", language=lang), show_alert=True)
            return

        is_privileged = bool(roles) and any(r in ('admin', 'manager') for r in roles)

        # Получаем смены на текущую неделю
        today = date.today()
        start_of_week = today - timedelta(days=today.weekday())  # Понедельник
        end_of_week = start_of_week + timedelta(days=6)  # Воскресенье

        filters = [
            func.date(Shift.planned_start_time) >= start_of_week,
            func.date(Shift.planned_start_time) <= end_of_week,
            Shift.status.in_(['planned', 'active', 'completed']),
        ]
        # Executor видит только свои смены; manager/admin — все.
        if not is_privileged:
            filters.append(Shift.user_id == user.id)

        week_shifts = db.query(Shift).filter(and_(*filters)).order_by(Shift.planned_start_time).all()
        
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
            day_name = days_of_week[shift.planned_start_time.weekday()]
            week_schedule[day_name].append(shift)
        
        # Формируем текст расписания
        schedule_text = (
            f"📆 <b>{get_text('my_shifts.handlers.week_schedule', language=lang)}</b>\n"
            f"<b>{get_text('my_shifts.handlers.period', language=lang)}:</b> {start_of_week.strftime('%d.%m')} - {end_of_week.strftime('%d.%m.%Y')}\n\n"
        )
        
        total_shifts = len(week_shifts)
        total_hours = 0
        
        for day_name, day_shifts in week_schedule.items():
            day_date = start_of_week + timedelta(days=days_of_week.index(day_name))
            is_today = day_date == today
            day_prefix = "🔥" if is_today else "📅"
            
            if day_shifts:
                schedule_text += f"{day_prefix} <b>{day_name}</b> ({day_date.strftime('%d.%m')})\n"
                
                for shift in day_shifts:
                    start_time = shift.planned_start_time.strftime("%H:%M")
                    end_time = shift.planned_end_time.strftime("%H:%M") if shift.planned_end_time else "?"
                    
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
                schedule_text += f"📅 <b>{day_name}</b> ({day_date.strftime('%d.%m')}): {get_text('my_shifts.handlers.day_off', language=lang)}\n\n"
        
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
    finally:
        if own_db and db:
            db.close()


@router.callback_query(F.data.startswith("shift_details:"))
@require_role(['executor'])
async def handle_shift_details(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Подробная информация о смене"""
    db = None  # ARCH-013: гарантируем close в finally
    try:
        shift_id = int(callback.data.split(':')[1])
        db = next(get_db())
        user_id = callback.from_user.id
        lang = language
        
        # Получаем смену
        shift = db.query(Shift).filter(
            and_(
                Shift.id == shift_id,
                Shift.user_id == user_id
            )
        ).first()
        
        if not shift:
            await callback.answer(get_text("my_shifts.handlers.shift_not_found", language=language), show_alert=True)
            return

        # Формируем подробную информацию
        shift_date = shift.planned_start_time.date()
        is_today = shift_date == date.today()
        is_tomorrow = shift_date == date.today() + timedelta(days=1)

        date_text = f"🔥 {get_text('my_shifts.handlers.today', language=lang)}" if is_today else f"📅 {get_text('my_shifts.handlers.tomorrow', language=lang)}" if is_tomorrow else shift_date.strftime('%d.%m.%Y')
        
        start_time = shift.planned_start_time.strftime("%H:%M")
        end_time = shift.planned_end_time.strftime("%H:%M") if shift.planned_end_time else "?"
        
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
    finally:
        if db:
            db.close()


@router.callback_query(F.data == "start_shift")
@require_role(['executor'])
async def handle_start_shift(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Начать смену"""
    db = None  # ARCH-013: гарантируем close в finally
    try:
        lang = language
        data = await state.get_data()
        shift_id = data.get('current_shift_id')

        if not shift_id:
            await callback.answer(get_text("my_shifts.handlers.shift_not_selected", language=lang), show_alert=True)
            return

        db = next(get_db())
        user_id = callback.from_user.id
        
        # Получаем и обновляем смену
        shift = db.query(Shift).filter(
            and_(
                Shift.id == shift_id,
                Shift.user_id == user_id,
                Shift.status == 'planned'
            )
        ).first()
        
        if not shift:
            await callback.answer(get_text("my_shifts.handlers.shift_not_found_or_started", language=lang), show_alert=True)
            return
        
        # Начинаем смену
        shift.status = 'active'
        shift.start_time = datetime.now()
        db.commit()
        
        await callback.message.edit_text(
            get_text("my_shifts.handlers.shift_started", language=lang).format(
                start_time=shift.start_time.strftime('%H:%M')
            ),
            reply_markup=get_shift_actions_keyboard(shift, lang),
            parse_mode="HTML"
        )

        await callback.answer(get_text("my_shifts.handlers.shift_started_toast", language=lang))
        
    except Exception as e:
        logger.error(f"Ошибка начала смены: {e}")
        await callback.answer(get_text("my_shifts.handlers.error_occurred", language=language), show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data == "end_shift")
@require_role(['executor'])
async def handle_end_shift(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Завершить смену"""
    db = None  # ARCH-013: гарантируем close в finally
    try:
        lang = language
        data = await state.get_data()
        shift_id = data.get('current_shift_id')

        if not shift_id:
            await callback.answer(get_text("my_shifts.handlers.shift_not_selected", language=lang), show_alert=True)
            return

        db = next(get_db())
        user_id = callback.from_user.id
        
        # Получаем и обновляем смену
        shift = db.query(Shift).filter(
            and_(
                Shift.id == shift_id,
                Shift.user_id == user_id,
                Shift.status == 'active'
            )
        ).first()
        
        if not shift:
            await callback.answer(get_text("my_shifts.handlers.shift_not_found_or_inactive", language=lang), show_alert=True)
            return
        
        # Завершаем смену
        end_time = datetime.now()
        shift.status = 'completed'
        shift.end_time = end_time
        
        # Рассчитываем фактическую длительность
        if shift.start_time:
            actual_duration = (end_time - shift.start_time).total_seconds() / 3600
        else:
            actual_duration = 0
        
        db.commit()
        
        # Формируем итоги смены
        summary_text = get_text("my_shifts.handlers.shift_ended_summary", language=lang).format(
            end_time=end_time.strftime('%H:%M'),
            actual_duration=f"{actual_duration:.1f}",
            request_count=shift.current_request_count or 0
        )
        
        await callback.message.edit_text(
            summary_text,
            reply_markup=get_my_shifts_menu(lang),
            parse_mode="HTML"
        )
        
        await state.set_state(MyShiftsStates.main_menu)
        await callback.answer(get_text("my_shifts.handlers.shift_ended_toast", language=lang))

    except Exception as e:
        logger.error(f"Ошибка завершения смены: {e}")
        await callback.answer(get_text("my_shifts.handlers.error_occurred", language=language), show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data == "shift_history")
@require_role(['admin', 'manager', 'executor'])
async def handle_shift_history(callback: CallbackQuery, state: FSMContext, language: str = "ru", db=None, roles: list = None, user: User = None):
    """История смен.

    BUG-BOT-005: разрешён доступ executor + manager + admin. Для executor query
    фильтруется по `Shift.user_id == user.id` (внутренний DB id, не telegram_id).
    Manager/admin — видит все смены.
    """
    own_db = db is None  # ARCH-013: закрываем только свою сессию
    try:
        if not db:
            db = next(get_db())
        lang = language

        # BUG-BOT-005: Используем внутренний user.id (Shift.user_id — FK на users.id).
        if user is None:
            user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if user is None:
            await callback.answer(get_text("my_shifts.handlers.error_occurred", language=lang), show_alert=True)
            return

        is_privileged = bool(roles) and any(r in ('admin', 'manager') for r in roles)

        # Получаем историю смен за последние 30 дней
        end_date = date.today()
        start_date = end_date - timedelta(days=30)

        filters = [
            func.date(Shift.planned_start_time) >= start_date,
            func.date(Shift.planned_start_time) <= end_date,
            Shift.status.in_(['completed', 'cancelled']),
        ]
        if not is_privileged:
            filters.append(Shift.user_id == user.id)

        history_shifts = db.query(Shift).filter(and_(*filters)).order_by(Shift.planned_start_time.desc()).limit(20).all()
        
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
            shift_date = shift.planned_start_time.strftime('%d.%m')
            start_time = shift.planned_start_time.strftime('%H:%M')
            
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
    finally:
        if own_db and db:
            db.close()


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


# ========== ИНТЕГРАЦИЯ С ПЕРЕДАЧЕЙ СМЕН ==========

@router.callback_query(F.data == "shift_transfer_menu")
async def handle_shift_transfer_menu(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Обработка меню передачи смен"""
    try:
        user_lang = language

        db = next(get_db())
        try:
            # Получаем активные смены пользователя для передачи
            user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
            if not user:
                await callback.answer(get_text("my_shifts.handlers.user_not_found", language=user_lang), show_alert=True)
                return

            active_shifts = db.query(Shift).filter(
                Shift.user_id == user.telegram_id,
                Shift.status.in_(['planned', 'active']),
                Shift.start_time >= datetime.now()
            ).order_by(Shift.start_time).limit(10).all()

            # Получаем мои передачи
            my_transfers = db.query(ShiftTransfer).filter(
                or_(
                    ShiftTransfer.from_executor_id == user.telegram_id,
                    ShiftTransfer.to_executor_id == user.telegram_id
                )
            ).order_by(ShiftTransfer.created_at.desc()).limit(5).all()

            menu_text = get_text("my_shifts.handlers.transfer_menu", language=user_lang).format(
                active_shifts_count=len(active_shifts),
                transfers_count=len(my_transfers)
            )

            # Создаем клавиатуру меню передач
            keyboard = []

            if active_shifts:
                keyboard.append([InlineKeyboardButton(
                    text=get_text("my_shifts.handlers.btn_transfer_shift", language=user_lang),
                    callback_data="initiate_transfer"
                )])

            if my_transfers:
                keyboard.append([InlineKeyboardButton(
                    text=get_text("my_shifts.handlers.btn_my_transfers", language=user_lang),
                    callback_data="view_my_transfers"
                )])

            # Кнопка назад (убрана по запросу пользователя)

            await callback.message.edit_text(
                menu_text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="HTML"
            )
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Ошибка меню передачи смен: {e}")
        await callback.answer(get_text("my_shifts.handlers.error_loading_menu", language=user_lang), show_alert=True)


@router.callback_query(F.data == "initiate_transfer")
async def handle_initiate_transfer(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Инициация передачи смены через меню 'Мои смены'"""
    try:
        user_lang = language

        db = next(get_db())
        try:
            user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()

            # Получаем активные смены пользователя
            active_shifts = db.query(Shift).filter(
                Shift.user_id == user.telegram_id,
                Shift.status.in_(['planned', 'active']),
                Shift.start_time >= datetime.now()
            ).order_by(Shift.start_time).limit(10).all()

            if not active_shifts:
                await callback.answer(get_text("my_shifts.handlers.no_shifts_to_transfer", language=user_lang), show_alert=True)
                return

            # Показываем список смен для выбора
            select_text = get_text("my_shifts.handlers.select_shift_to_transfer", language=user_lang)

            await callback.message.edit_text(
                select_text,
                reply_markup=shift_selection_keyboard(active_shifts, user_lang)
            )
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Ошибка инициации передачи: {e}")
        await callback.answer(get_text("my_shifts.handlers.error_initiating_transfer", language=user_lang), show_alert=True)


@router.callback_query(F.data == "view_my_transfers")
async def handle_view_my_transfers(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Просмотр передач пользователя"""
    try:
        user_lang = language

        db = next(get_db())
        try:
            user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()

            # Получаем передачи пользователя
            my_transfers = db.query(ShiftTransfer).filter(
                or_(
                    ShiftTransfer.from_executor_id == user.telegram_id,
                    ShiftTransfer.to_executor_id == user.telegram_id
                )
            ).order_by(ShiftTransfer.created_at.desc()).limit(10).all()

            if not my_transfers:
                await callback.answer(get_text("my_shifts.handlers.no_transfers", language=user_lang), show_alert=True)
                return

            view_text = get_text("my_shifts.handlers.your_transfers", language=user_lang)

            await callback.message.edit_text(
                view_text,
                reply_markup=transfers_list_keyboard(my_transfers, user_lang)
            )
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Ошибка просмотра передач: {e}")
        await callback.answer(get_text("my_shifts.handlers.error_loading_transfers", language=user_lang), show_alert=True)