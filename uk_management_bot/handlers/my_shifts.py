"""
Обработчики для исполнителей - интерфейс "Мои смены"
"""

from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext

from uk_management_bot.database.session import get_db
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_transfer import ShiftTransfer
from uk_management_bot.database.models.user import User
from uk_management_bot.keyboards.my_shifts import (
    get_my_shifts_menu,
    get_shift_list_keyboard,
    get_shift_actions_keyboard,
    get_shift_filter_keyboard
)
from uk_management_bot.keyboards.shift_transfer import (
    shift_selection_keyboard,
    transfers_list_keyboard
)
from uk_management_bot.states.my_shifts import MyShiftsStates
from uk_management_bot.middlewares.auth import require_role
from uk_management_bot.utils.helpers import get_user_language, format_datetime
from sqlalchemy import and_, func, or_
import logging

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("my_shifts"))
@require_role(['executor'])
async def cmd_my_shifts(message: Message, state: FSMContext, db=None):
    """Главное меню моих смен"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(message.from_user.id, db)
        
        await message.answer(
            "👤 <b>Мои смены</b>\n\n"
            "Здесь вы можете просматривать и управлять своими сменами:",
            reply_markup=get_my_shifts_menu(lang),
            parse_mode="HTML"
        )
        
        await state.set_state(MyShiftsStates.main_menu)
        
    except Exception as e:
        logger.error(f"Ошибка команды /my_shifts: {e}")
        await message.answer("❌ Произошла ошибка при загрузке моих смен")
    finally:
        if db:
            db.close()


@router.message(F.text == "📋 Мои смены")
@require_role(['executor'])
async def handle_my_shifts_button(message: Message, state: FSMContext):
    """Обработчик кнопки 'Мои смены'"""
    await cmd_my_shifts(message, state)


@router.callback_query(F.data == "view_current_shifts")
@require_role(['executor'])
async def handle_current_shifts(callback: CallbackQuery, state: FSMContext):
    """Просмотр текущих смен"""
    try:
        db = next(get_db())
        user_id = callback.from_user.id
        lang = await get_user_language(user_id)
        
        # Получаем смены на сегодня и завтра
        today = date.today()
        tomorrow = today + timedelta(days=1)
        
        current_shifts = db.query(Shift).filter(
            and_(
                Shift.user_id == user_id,
                func.date(Shift.planned_start_time).in_([today, tomorrow]),
                Shift.status.in_(['planned', 'active'])
            )
        ).order_by(Shift.planned_start_time).all()
        
        if not current_shifts:
            await callback.message.edit_text(
                "📅 <b>Текущие смены</b>\n\n"
                "У вас нет запланированных смен на сегодня и завтра.\n\n"
                "Обратитесь к менеджеру для назначения смен.",
                reply_markup=get_my_shifts_menu(lang),
                parse_mode="HTML"
            )
            await callback.answer()
            return
        
        # Формируем список смен
        shifts_text = "📅 <b>Ваши текущие смены</b>\n\n"
        
        for shift in current_shifts:
            shift_date = shift.planned_start_time.date()
            is_today = shift_date == today
            date_prefix = "🔥 Сегодня" if is_today else "📅 Завтра"
            
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
                shifts_text += f"📋 Заявки: {current_requests}/{shift.max_requests}\n"
            
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
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "view_week_schedule")
@require_role(['executor'])
async def handle_week_schedule(callback: CallbackQuery, state: FSMContext):
    """Просмотр расписания на неделю"""
    try:
        db = next(get_db())
        user_id = callback.from_user.id
        lang = await get_user_language(user_id)
        
        # Получаем смены на текущую неделю
        today = date.today()
        start_of_week = today - timedelta(days=today.weekday())  # Понедельник
        end_of_week = start_of_week + timedelta(days=6)  # Воскресенье
        
        week_shifts = db.query(Shift).filter(
            and_(
                Shift.user_id == user_id,
                func.date(Shift.planned_start_time) >= start_of_week,
                func.date(Shift.planned_start_time) <= end_of_week,
                Shift.status.in_(['planned', 'active', 'completed'])
            )
        ).order_by(Shift.planned_start_time).all()
        
        # Группируем по дням недели
        days_of_week = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
        week_schedule = {day: [] for day in days_of_week}
        
        for shift in week_shifts:
            day_name = days_of_week[shift.planned_start_time.weekday()]
            week_schedule[day_name].append(shift)
        
        # Формируем текст расписания
        schedule_text = (
            f"📆 <b>Расписание на неделю</b>\n"
            f"<b>Период:</b> {start_of_week.strftime('%d.%m')} - {end_of_week.strftime('%d.%m.%Y')}\n\n"
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
                schedule_text += f"📅 <b>{day_name}</b> ({day_date.strftime('%d.%m')}): Выходной\n\n"
        
        # Итоговая статистика
        schedule_text += (
            f"📊 <b>Итого:</b>\n"
            f"• Смен: {total_shifts}\n"
            f"• Часов: {total_hours:.1f}\n"
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
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("shift_details:"))
@require_role(['executor'])
async def handle_shift_details(callback: CallbackQuery, state: FSMContext):
    """Подробная информация о смене"""
    try:
        shift_id = int(callback.data.split(':')[1])
        db = next(get_db())
        user_id = callback.from_user.id
        lang = await get_user_language(user_id)
        
        # Получаем смену
        shift = db.query(Shift).filter(
            and_(
                Shift.id == shift_id,
                Shift.user_id == user_id
            )
        ).first()
        
        if not shift:
            await callback.answer("❌ Смена не найдена", show_alert=True)
            return
        
        # Формируем подробную информацию
        shift_date = shift.planned_start_time.date()
        is_today = shift_date == date.today()
        is_tomorrow = shift_date == date.today() + timedelta(days=1)
        
        date_text = "🔥 Сегодня" if is_today else "📅 Завтра" if is_tomorrow else shift_date.strftime('%d.%m.%Y')
        
        start_time = shift.planned_start_time.strftime("%H:%M")
        end_time = shift.planned_end_time.strftime("%H:%M") if shift.planned_end_time else "?"
        
        status_text = {
            'planned': '⏱️ Запланирована',
            'active': '🔴 Активна',
            'completed': '✅ Завершена',
            'cancelled': '❌ Отменена'
        }.get(shift.status, '⚪ Неизвестно')
        
        details_text = (
            f"📋 <b>Детали смены</b>\n\n"
            f"<b>Дата:</b> {date_text}\n"
            f"<b>Время:</b> {start_time} - {end_time}\n"
            f"<b>Статус:</b> {status_text}\n\n"
        )
        
        # Длительность
        if shift.planned_start_time and shift.planned_end_time:
            duration = (shift.planned_end_time - shift.planned_start_time).total_seconds() / 3600
            details_text += f"<b>Длительность:</b> {duration:.1f} часов\n"
        
        # Специализации
        if shift.specialization_focus:
            specializations = ', '.join(shift.specialization_focus)
            details_text += f"<b>Специализации:</b> {specializations}\n"
        
        # Географическая зона
        if shift.geographic_zone:
            details_text += f"<b>Зона:</b> {shift.geographic_zone}\n"
        
        # Области покрытия
        if shift.coverage_areas:
            coverage = ', '.join(shift.coverage_areas)
            details_text += f"<b>Области:</b> {coverage}\n"
        
        details_text += "\n"
        
        # Заявки
        current_requests = shift.current_request_count or 0
        max_requests = shift.max_requests or 0
        
        if max_requests > 0:
            details_text += f"<b>📋 Заявки:</b> {current_requests}/{max_requests}\n"
            
            if current_requests > 0:
                progress = (current_requests / max_requests) * 100
                progress_bar = "🟩" * int(progress // 20) + "⬜" * (5 - int(progress // 20))
                details_text += f"Загрузка: {progress_bar} {progress:.0f}%\n"
        
        # Статистика (если есть)
        if shift.completed_requests:
            details_text += f"<b>Выполнено заявок:</b> {shift.completed_requests}\n"
        
        if shift.average_completion_time:
            avg_time = shift.average_completion_time
            details_text += f"<b>Среднее время:</b> {avg_time:.1f} мин\n"
        
        if shift.efficiency_score:
            score = shift.efficiency_score
            details_text += f"<b>Эффективность:</b> {score:.1f}%\n"
        
        # Заметки
        if shift.notes:
            details_text += f"\n<b>Заметки:</b>\n{shift.notes}"
        
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
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "start_shift")
@require_role(['executor'])
async def handle_start_shift(callback: CallbackQuery, state: FSMContext):
    """Начать смену"""
    try:
        data = await state.get_data()
        shift_id = data.get('current_shift_id')
        
        if not shift_id:
            await callback.answer("❌ Смена не выбрана", show_alert=True)
            return
        
        db = next(get_db())
        user_id = callback.from_user.id
        lang = await get_user_language(user_id)
        
        # Получаем и обновляем смену
        shift = db.query(Shift).filter(
            and_(
                Shift.id == shift_id,
                Shift.user_id == user_id,
                Shift.status == 'planned'
            )
        ).first()
        
        if not shift:
            await callback.answer("❌ Смена не найдена или уже запущена", show_alert=True)
            return
        
        # Начинаем смену
        shift.status = 'active'
        shift.start_time = datetime.now()
        db.commit()
        
        await callback.message.edit_text(
            "✅ <b>Смена начата!</b>\n\n"
            f"⏰ Время начала: {shift.start_time.strftime('%H:%M')}\n\n"
            "Теперь вы можете принимать заявки.\n"
            "Не забудьте завершить смену в конце рабочего времени.",
            reply_markup=get_shift_actions_keyboard(shift, lang),
            parse_mode="HTML"
        )
        
        await callback.answer("Смена начата!")
        
    except Exception as e:
        logger.error(f"Ошибка начала смены: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "end_shift")
@require_role(['executor'])
async def handle_end_shift(callback: CallbackQuery, state: FSMContext):
    """Завершить смену"""
    try:
        data = await state.get_data()
        shift_id = data.get('current_shift_id')
        
        if not shift_id:
            await callback.answer("❌ Смена не выбрана", show_alert=True)
            return
        
        db = next(get_db())
        user_id = callback.from_user.id
        lang = await get_user_language(user_id)
        
        # Получаем и обновляем смену
        shift = db.query(Shift).filter(
            and_(
                Shift.id == shift_id,
                Shift.user_id == user_id,
                Shift.status == 'active'
            )
        ).first()
        
        if not shift:
            await callback.answer("❌ Смена не найдена или не активна", show_alert=True)
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
        summary_text = (
            "✅ <b>Смена завершена!</b>\n\n"
            f"⏰ Время завершения: {end_time.strftime('%H:%M')}\n"
        )
        
        if shift.start_time:
            summary_text += f"⏱️ Фактическая длительность: {actual_duration:.1f} ч\n"
        
        if shift.current_request_count:
            summary_text += f"📋 Обработано заявок: {shift.current_request_count}\n"
        
        summary_text += (
            f"\nСпасибо за работу! 👍\n"
            f"Информация о смене сохранена в системе."
        )
        
        await callback.message.edit_text(
            summary_text,
            reply_markup=get_my_shifts_menu(lang),
            parse_mode="HTML"
        )
        
        await state.set_state(MyShiftsStates.main_menu)
        await callback.answer("Смена завершена!")
        
    except Exception as e:
        logger.error(f"Ошибка завершения смены: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "shift_history")
@require_role(['executor'])
async def handle_shift_history(callback: CallbackQuery, state: FSMContext):
    """История смен"""
    try:
        db = next(get_db())
        user_id = callback.from_user.id
        lang = await get_user_language(user_id)
        
        # Получаем историю смен за последние 30 дней
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        
        history_shifts = db.query(Shift).filter(
            and_(
                Shift.user_id == user_id,
                func.date(Shift.planned_start_time) >= start_date,
                func.date(Shift.planned_start_time) <= end_date,
                Shift.status.in_(['completed', 'cancelled'])
            )
        ).order_by(Shift.planned_start_time.desc()).limit(20).all()
        
        if not history_shifts:
            await callback.message.edit_text(
                "📊 <b>История смен</b>\n\n"
                "За последние 30 дней у вас не было завершенных смен.",
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
        history_text = (
            f"📊 <b>История смен</b> (30 дней)\n\n"
            f"<b>📈 Статистика:</b>\n"
            f"• Завершено смен: {len(completed_shifts)}\n"
            f"• Отменено смен: {len(cancelled_shifts)}\n"
            f"• Отработано часов: {total_hours:.1f}\n"
            f"• Обработано заявок: {total_requests}\n\n"
            f"<b>🗓️ Последние смены:</b>\n"
        )
        
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
                requests = f" • {shift.completed_requests} заявок"
            
            history_text += f"{status_emoji} {shift_date} {start_time}{duration}{requests}\n"
        
        if len(history_shifts) > 10:
            history_text += f"\n... и еще {len(history_shifts) - 10} смен"
        
        await callback.message.edit_text(
            history_text,
            reply_markup=get_my_shifts_menu(lang),
            parse_mode="HTML"
        )
        
        await state.set_state(MyShiftsStates.main_menu)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка просмотра истории смен: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "back_to_my_shifts")
async def handle_back_to_my_shifts(callback: CallbackQuery, state: FSMContext):
    """Возврат к главному меню моих смен"""
    try:
        lang = await get_user_language(callback.from_user.id)
        
        await callback.message.edit_text(
            "👤 <b>Мои смены</b>\n\n"
            "Здесь вы можете просматривать и управлять своими сменами:",
            reply_markup=get_my_shifts_menu(lang),
            parse_mode="HTML"
        )
        
        await state.set_state(MyShiftsStates.main_menu)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка возврата к моим сменам: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


# ========== ИНТЕГРАЦИЯ С ПЕРЕДАЧЕЙ СМЕН ==========

@router.callback_query(F.data == "shift_transfer_menu")
async def handle_shift_transfer_menu(callback: CallbackQuery, state: FSMContext):
    """Обработка меню передачи смен"""
    try:
        user_lang = await get_user_language(callback.from_user.id)

        with get_db() as db:
            # Получаем активные смены пользователя для передачи
            user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
            if not user:
                error_text = "Пользователь не найден" if user_lang == "ru" else "Foydalanuvchi topilmadi"
                await callback.answer(error_text, show_alert=True)
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

            if user_lang == "ru":
                menu_text = f"""
🔄 <b>Меню передачи смен</b>

📊 <b>Статус:</b>
• Активных смен: {len(active_shifts)}
• Ваших передач: {len(my_transfers)}

Выберите действие:
"""
            else:
                menu_text = f"""
🔄 <b>Smena o'tkazish menyusi</b>

📊 <b>Holat:</b>
• Faol smenalar: {len(active_shifts)}
• Sizning o'tkazishlaringiz: {len(my_transfers)}

Amalni tanlang:
"""

            # Создаем клавиатуру меню передач
            keyboard = []

            if active_shifts:
                transfer_text = "📤 Передать смену" if user_lang == "ru" else "📤 Smenani o'tkazish"
                keyboard.append([InlineKeyboardButton(
                    text=transfer_text,
                    callback_data="initiate_transfer"
                )])

            if my_transfers:
                view_text = "📋 Мои передачи" if user_lang == "ru" else "📋 Mening o'tkazishlarim"
                keyboard.append([InlineKeyboardButton(
                    text=view_text,
                    callback_data="view_my_transfers"
                )])

            # Кнопка назад
            back_text = "🔙 Назад в меню" if user_lang == "ru" else "🔙 Menyuga qaytish"
            keyboard.append([InlineKeyboardButton(
                text=back_text,
                callback_data="back_to_my_shifts"
            )])

            await callback.message.edit_text(
                menu_text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="HTML"
            )

    except Exception as e:
        logger.error(f"Ошибка меню передачи смен: {e}")
        error_text = "Ошибка загрузки меню" if user_lang == "ru" else "Menyuni yuklashda xatolik"
        await callback.answer(error_text, show_alert=True)


@router.callback_query(F.data == "initiate_transfer")
async def handle_initiate_transfer(callback: CallbackQuery, state: FSMContext):
    """Инициация передачи смены через меню 'Мои смены'"""
    try:
        user_lang = await get_user_language(callback.from_user.id)

        with get_db() as db:
            user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()

            # Получаем активные смены пользователя
            active_shifts = db.query(Shift).filter(
                Shift.user_id == user.telegram_id,
                Shift.status.in_(['planned', 'active']),
                Shift.start_time >= datetime.now()
            ).order_by(Shift.start_time).limit(10).all()

            if not active_shifts:
                no_shifts_text = (
                    "У вас нет активных смен для передачи" if user_lang == "ru"
                    else "Sizda o'tkazish uchun faol smenalar yo'q"
                )
                await callback.answer(no_shifts_text, show_alert=True)
                return

            # Показываем список смен для выбора
            select_text = (
                "Выберите смену для передачи:" if user_lang == "ru"
                else "O'tkazish uchun smenani tanlang:"
            )

            await callback.message.edit_text(
                select_text,
                reply_markup=shift_selection_keyboard(active_shifts, user_lang)
            )

    except Exception as e:
        logger.error(f"Ошибка инициации передачи: {e}")
        error_text = "Ошибка инициации передачи" if user_lang == "ru" else "O'tkazishni boshlashda xatolik"
        await callback.answer(error_text, show_alert=True)


@router.callback_query(F.data == "view_my_transfers")
async def handle_view_my_transfers(callback: CallbackQuery, state: FSMContext):
    """Просмотр передач пользователя"""
    try:
        user_lang = await get_user_language(callback.from_user.id)

        with get_db() as db:
            user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()

            # Получаем передачи пользователя
            my_transfers = db.query(ShiftTransfer).filter(
                or_(
                    ShiftTransfer.from_executor_id == user.telegram_id,
                    ShiftTransfer.to_executor_id == user.telegram_id
                )
            ).order_by(ShiftTransfer.created_at.desc()).limit(10).all()

            if not my_transfers:
                no_transfers_text = (
                    "У вас нет передач" if user_lang == "ru"
                    else "Sizda o'tkazishlar yo'q"
                )
                await callback.answer(no_transfers_text, show_alert=True)
                return

            view_text = "Ваши передачи:" if user_lang == "ru" else "Sizning o'tkazishlaringiz:"

            await callback.message.edit_text(
                view_text,
                reply_markup=transfers_list_keyboard(my_transfers, user_lang)
            )

    except Exception as e:
        logger.error(f"Ошибка просмотра передач: {e}")
        error_text = "Ошибка загрузки передач" if user_lang == "ru" else "O'tkazishlarni yuklashda xatolik"
        await callback.answer(error_text, show_alert=True)