"""
Обработчики для управления сменами - интерфейсы для менеджеров
"""

from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext

from uk_management_bot.database.session import get_db
from uk_management_bot.database.models.shift_template import ShiftTemplate
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from sqlalchemy import func
from uk_management_bot.services.shift_planning_service import ShiftPlanningService
from uk_management_bot.services.shift_analytics import ShiftAnalytics
from uk_management_bot.services.template_manager import TemplateManager
from uk_management_bot.keyboards.shift_management import (
    get_main_shift_menu,
    get_planning_menu,
    get_template_selection_keyboard,
    get_date_selection_keyboard,
    get_analytics_menu,
    get_shift_details_keyboard,
    get_auto_planning_keyboard,
    get_schedule_view_keyboard,
    get_template_management_keyboard
)
from uk_management_bot.states.shift_management import ShiftManagementStates, TemplateManagementStates
from uk_management_bot.middlewares.auth import require_role
from uk_management_bot.utils.helpers import get_user_language
import logging

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("shifts"))
@require_role(['admin', 'manager'])
async def cmd_shifts(message: Message, state: FSMContext, db=None):
    """Главное меню управления сменами"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(message.from_user.id, db)
        
        await message.answer(
            "🔧 <b>Управление сменами</b>\n\n"
            "Выберите действие:",
            reply_markup=get_main_shift_menu(lang),
            parse_mode="HTML"
        )
        
        await state.set_state(ShiftManagementStates.main_menu)
        
    except Exception as e:
        logger.error(f"Ошибка команды /shifts: {e}")
        await message.answer("❌ Произошла ошибка при загрузке меню смен")
    finally:
        if db:
            db.close()




@router.callback_query(F.data == "shift_planning")
@require_role(['admin', 'manager'])
async def handle_shift_planning(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Меню планирования смен"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)
        
        await callback.message.edit_text(
            "📅 <b>Планирование смен</b>\n\n"
            "Выберите действие:",
            reply_markup=get_planning_menu(lang),
            parse_mode="HTML"
        )
        
        await state.set_state(ShiftManagementStates.planning_menu)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка планирования смен: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data == "auto_planning")
@require_role(['admin', 'manager'])
async def handle_auto_planning(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Автоматическое планирование смен"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)
        
        await callback.message.edit_text(
            "🤖 <b>Автоматическое планирование</b>\n\n"
            "Выберите режим автоматического планирования:",
            reply_markup=get_auto_planning_keyboard(lang),
            parse_mode="HTML"
        )
        
        await state.set_state(ShiftManagementStates.auto_planning_settings)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка автопланирования: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data == "auto_plan_week")
@require_role(['admin', 'manager'])
async def handle_auto_plan_week(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Автопланирование на неделю"""
    try:
        if not db:
            db = next(get_db())
        
        planning_service = ShiftPlanningService(db)
        
        # Начинаем планирование с понедельника текущей недели
        today = date.today()
        days_until_monday = today.weekday()
        monday = today - timedelta(days=days_until_monday)
        
        await callback.answer("⏳ Планирую смены на неделю...")
        
        results = planning_service.plan_weekly_schedule(monday)
        
        # Формируем отчет
        stats = results['statistics']
        response = (
            f"📅 <b>Недельное автопланирование завершено</b>\n\n"
            f"<b>Период:</b> {results['week_start'].strftime('%d.%m.%Y')} - "
            f"{(results['week_start'] + timedelta(days=6)).strftime('%d.%m.%Y')}\n"
            f"<b>Создано смен:</b> {stats['total_shifts']}\n\n"
        )
        
        if stats['shifts_by_day']:
            response += "<b>По дням недели:</b>\n"
            for day, count in stats['shifts_by_day'].items():
                response += f"• {day}: {count} смен\n"
        
        if stats['shifts_by_template']:
            response += "\n<b>По шаблонам:</b>\n"
            for template, count in stats['shifts_by_template'].items():
                response += f"• {template}: {count} смен\n"
        
        if results['errors']:
            response += f"\n❌ <b>Ошибки:</b>\n"
            for error in results['errors'][:3]:  # Показываем только первые 3 ошибки
                response += f"• {error}\n"
        
        await callback.message.edit_text(
            response,
            reply_markup=get_auto_planning_keyboard(),
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Ошибка автопланирования недели: {e}")
        await callback.message.edit_text(
            f"❌ Ошибка автопланирования недели:\n{str(e)[:200]}",
            reply_markup=get_auto_planning_keyboard(),
            parse_mode="HTML"
        )
    finally:
        if db:
            db.close()


@router.callback_query(F.data == "auto_plan_month")
@require_role(['admin', 'manager'])
async def handle_auto_plan_month(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Автопланирование на месяц"""
    try:
        if not db:
            db = next(get_db())
        
        planning_service = ShiftPlanningService(db)
        
        await callback.answer("⏳ Планирую смены на месяц...")
        
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
                errors.append(f"Неделя {week_offset + 1}: {str(e)}")
        
        response = (
            f"📅 <b>Месячное автопланирование завершено</b>\n\n"
            f"<b>Запланировано недель:</b> {weeks_planned}/4\n"
            f"<b>Создано смен:</b> {total_shifts}\n"
        )
        
        if errors:
            response += f"\n❌ <b>Ошибки ({len(errors)}):</b>\n"
            for error in errors[:3]:  # Показываем только первые 3 ошибки
                response += f"• {error}\n"
            if len(errors) > 3:
                response += f"• ... и еще {len(errors) - 3} ошибок\n"
        
        await callback.message.edit_text(
            response,
            reply_markup=get_auto_planning_keyboard(),
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Ошибка автопланирования месяца: {e}")
        await callback.message.edit_text(
            f"❌ Ошибка автопланирования месяца:\n{str(e)[:200]}",
            reply_markup=get_auto_planning_keyboard(),
            parse_mode="HTML"
        )
    finally:
        if db:
            db.close()


@router.callback_query(F.data == "auto_plan_tomorrow")
@require_role(['admin', 'manager'])
async def handle_auto_plan_tomorrow(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Создание смен на завтра"""
    try:
        if not db:
            db = next(get_db())
        
        planning_service = ShiftPlanningService(db)
        
        tomorrow = date.today() + timedelta(days=1)
        
        await callback.answer("⏳ Создаю смены на завтра...")
        
        # Получаем активные шаблоны для автосоздания
        templates = db.query(ShiftTemplate).filter(
            ShiftTemplate.is_active == True,
            ShiftTemplate.auto_create == True
        ).all()
        
        total_shifts = 0
        created_by_template = {}
        errors = []
        
        weekday = tomorrow.weekday() + 1  # 1=понедельник, 7=воскресенье
        
        for template in templates:
            if template.is_day_included(weekday):
                try:
                    shifts = planning_service.create_shift_from_template(template.id, tomorrow)
                    if shifts:
                        total_shifts += len(shifts)
                        created_by_template[template.name] = len(shifts)
                except Exception as e:
                    errors.append(f"{template.name}: {str(e)}")
        
        response = (
            f"📅 <b>Создание смен на завтра завершено</b>\n\n"
            f"<b>Дата:</b> {tomorrow.strftime('%d.%m.%Y')}\n"
            f"<b>Создано смен:</b> {total_shifts}\n"
        )
        
        if created_by_template:
            response += "\n<b>По шаблонам:</b>\n"
            for template, count in created_by_template.items():
                response += f"• {template}: {count} смен\n"
        
        if total_shifts == 0:
            response += "\n💡 <i>Возможные причины:</i>\n"
            response += "• Нет активных шаблонов с auto_create=true\n"
            response += "• У шаблонов не настроены дни недели\n"
            response += "• Завтра не входит в рабочие дни шаблонов"
        
        if errors:
            response += f"\n❌ <b>Ошибки:</b>\n"
            for error in errors[:3]:
                response += f"• {error}\n"
        
        await callback.message.edit_text(
            response,
            reply_markup=get_auto_planning_keyboard(),
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Ошибка создания смен на завтра: {e}")
        await callback.message.edit_text(
            f"❌ Ошибка создания смен на завтра:\n{str(e)[:200]}",
            reply_markup=get_auto_planning_keyboard(),
            parse_mode="HTML"
        )
    finally:
        if db:
            db.close()


@router.callback_query(F.data == "view_schedule")
@require_role(['admin', 'manager'])
async def handle_view_schedule(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Просмотр расписания смен"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)
        
        # Показываем расписание на сегодня
        today = date.today()
        
        await callback.message.edit_text(
            f"📋 <b>Расписание смен</b>\n\n"
            f"📅 {today.strftime('%d.%m.%Y')}\n\n"
            "Выберите дату для просмотра:",
            reply_markup=get_schedule_view_keyboard(today, lang),
            parse_mode="HTML"
        )
        
        await state.set_state(ShiftManagementStates.viewing_schedule)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка просмотра расписания: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data.startswith("schedule_date:"))
@require_role(['admin', 'manager'])
async def handle_schedule_date(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Обработка выбора даты в расписании"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)
        
        # Извлекаем дату из callback_data
        date_str = callback.data.split(":", 1)[1]
        selected_date = date.fromisoformat(date_str)
        
        # Получаем смены на выбранную дату
        shifts = db.query(Shift).filter(
            func.date(Shift.planned_start_time) == selected_date
        ).order_by(Shift.planned_start_time).all()
        
        # Формируем сообщение
        response = f"📋 <b>Расписание смен</b>\n\n📅 {selected_date.strftime('%d.%m.%Y')}\n\n"
        
        if shifts:
            response += f"<b>Найдено смен: {len(shifts)}</b>\n\n"
            for shift in shifts:
                # Получаем имя исполнителя
                executor_name = "Не назначен"
                if shift.user_id:
                    user = db.query(User).filter(User.id == shift.user_id).first()
                    if user:
                        executor_name = f"{user.first_name} {user.last_name or ''}".strip()
                
                # Получаем название шаблона
                template_name = "Без шаблона"
                if shift.shift_template_id:
                    template = db.query(ShiftTemplate).filter(ShiftTemplate.id == shift.shift_template_id).first()
                    if template:
                        template_name = template.name
                
                start_time = shift.planned_start_time.strftime('%H:%M') if shift.planned_start_time else "??:??"
                end_time = shift.planned_end_time.strftime('%H:%M') if shift.planned_end_time else "??:??"
                
                status_emoji = "🟢" if shift.status == "active" else "🟡" if shift.status == "planned" else "🔴"
                
                response += (
                    f"{status_emoji} <b>{start_time}-{end_time}</b>\n"
                    f"   👤 {executor_name}\n"
                    f"   📋 {template_name}\n"
                    f"   📊 {shift.status.title()}\n\n"
                )
        else:
            response += "📭 <i>На эту дату смен не запланировано</i>\n\n"
        
        response += "Выберите другую дату:"
        
        await callback.message.edit_text(
            response,
            reply_markup=get_schedule_view_keyboard(selected_date, lang),
            parse_mode="HTML"
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка выбора даты расписания: {e}")
        await callback.answer("❌ Произошла ошибка при загрузке расписания", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data == "schedule_week_view")
@require_role(['admin', 'manager'])
async def handle_schedule_week_view(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Недельное расписание"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)
        
        # Определяем начало текущей недели (понедельник)
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        
        response = f"📅 <b>Недельное расписание</b>\n\n"
        response += f"<b>Неделя {monday.strftime('%d.%m')} - {(monday + timedelta(days=6)).strftime('%d.%m.%Y')}</b>\n\n"
        
        # Проходим по каждому дню недели
        days_names = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        
        for i in range(7):
            current_day = monday + timedelta(days=i)
            day_name = days_names[i]
            
            # Получаем смены на этот день
            shifts = db.query(Shift).filter(
                func.date(Shift.planned_start_time) == current_day
            ).order_by(Shift.planned_start_time).all()
            
            response += f"<b>{day_name} {current_day.strftime('%d.%m')}</b>\n"
            
            if shifts:
                for shift in shifts:
                    start_time = shift.planned_start_time.strftime('%H:%M') if shift.planned_start_time else "??:??"
                    status_emoji = "🟢" if shift.status == "active" else "🟡" if shift.status == "planned" else "🔴"
                    
                    # Получаем имя исполнителя
                    executor_name = "Не назначен"
                    if shift.user_id:
                        user = db.query(User).filter(User.id == shift.user_id).first()
                        if user:
                            executor_name = f"{user.first_name}"
                    
                    response += f"  {status_emoji} {start_time} - {executor_name}\n"
            else:
                response += f"  📭 <i>Смен нет</i>\n"
            
            response += "\n"
        
        await callback.message.edit_text(
            response,
            reply_markup=get_schedule_view_keyboard(today, lang),
            parse_mode="HTML"
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка недельного расписания: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data == "schedule_month_view")
@require_role(['admin', 'manager'])
async def handle_schedule_month_view(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Месячный обзор расписания"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)
        
        # Определяем текущий месяц
        today = date.today()
        month_start = today.replace(day=1)
        
        # Получаем смены за месяц
        shifts = db.query(Shift).filter(
            func.date(Shift.planned_start_time) >= month_start,
            func.date(Shift.planned_start_time) < month_start.replace(month=month_start.month + 1) if month_start.month < 12 else month_start.replace(year=month_start.year + 1, month=1)
        ).all()
        
        # Группируем по датам
        shifts_by_date = {}
        for shift in shifts:
            if shift.planned_start_time:
                shift_date = shift.planned_start_time.date()
                if shift_date not in shifts_by_date:
                    shifts_by_date[shift_date] = 0
                shifts_by_date[shift_date] += 1
        
        response = f"📅 <b>Месячный обзор</b>\n\n"
        response += f"<b>{today.strftime('%B %Y')}</b>\n\n"
        response += f"<b>Всего смен в месяце: {len(shifts)}</b>\n\n"
        
        # Показываем дни с наибольшим количеством смен
        if shifts_by_date:
            sorted_dates = sorted(shifts_by_date.items(), key=lambda x: x[1], reverse=True)[:10]
            response += "<b>Самые загруженные дни:</b>\n"
            for shift_date, count in sorted_dates:
                response += f"• {shift_date.strftime('%d.%m')}: {count} смен\n"
        else:
            response += "📭 <i>В этом месяце нет запланированных смен</i>\n"
        
        await callback.message.edit_text(
            response,
            reply_markup=get_schedule_view_keyboard(today, lang),
            parse_mode="HTML"
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка месячного обзора: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data == "back_to_shifts")
async def handle_back_to_shifts(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Возврат к главному меню смен"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)
        
        await callback.message.edit_text(
            "👥 <b>Управление сменами</b>\n\n"
            "Выберите действие:",
            reply_markup=get_main_shift_menu(lang),
            parse_mode="HTML"
        )
        
        await state.clear()
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка возврата к меню смен: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data == "template_management")
@require_role(['admin', 'manager'])
async def handle_template_management(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Управление шаблонами смен"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)
        
        await callback.message.edit_text(
            "🗂️ <b>Управление шаблонами</b>\n\n"
            "Выберите действие с шаблонами:",
            reply_markup=get_template_management_keyboard(lang),
            parse_mode="HTML"
        )
        
        await state.set_state(ShiftManagementStates.template_menu)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка управления шаблонами: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data == "create_new_template")
@require_role(['admin', 'manager'])
async def handle_create_new_template(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Создание нового шаблона"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)
        
        await callback.message.edit_text(
            "➕ <b>Создание шаблона смены</b>\n\n"
            "Введите название шаблона:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="template_management")]
            ]),
            parse_mode="HTML"
        )
        
        await state.set_state(ShiftManagementStates.template_name_input)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка создания шаблона: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data == "templates_view_all")
@require_role(['admin', 'manager'])
async def handle_view_all_templates(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Просмотр всех шаблонов"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)
        template_manager = TemplateManager(db)
        
        # Получаем все шаблоны
        templates = template_manager.get_templates(active_only=False)
        
        if not templates:
            await callback.message.edit_text(
                "📋 <b>Шаблоны смен</b>\n\n"
                "❌ Шаблонов не найдено\n\n"
                "Создайте первый шаблон с помощью кнопки 'Создать новый шаблон'",
                reply_markup=get_template_management_keyboard(lang),
                parse_mode="HTML"
            )
            await callback.answer("Шаблонов не найдено")
            return
        
        # Формируем текст со списком шаблонов
        templates_text = "📋 <b>Все шаблоны смен</b>\n\n"
        
        for i, template in enumerate(templates, 1):
            status_emoji = "✅" if template.is_active else "❌"
            time_info = f"{template.start_hour:02d}:{template.start_minute or 0:02d}"
            duration_info = f"{template.duration_hours}ч"
            
            specialization_info = ""
            if template.required_specializations:
                specialization_info = f" • {', '.join(template.required_specializations[:2])}"
                if len(template.required_specializations) > 2:
                    specialization_info += f" (+{len(template.required_specializations)-2})"
            
            templates_text += (
                f"{i}. {status_emoji} <b>{template.name}</b>\n"
                f"   🕒 {time_info} ({duration_info}){specialization_info}\n"
                f"   📝 {template.description or 'Без описания'}\n\n"
            )
        
        await callback.message.edit_text(
            templates_text,
            reply_markup=get_template_management_keyboard(lang),
            parse_mode="HTML"
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка просмотра шаблонов: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.message(StateFilter(ShiftManagementStates.template_name_input))
async def handle_template_name_input(message: Message, state: FSMContext, db=None, roles: list = None, user=None):
    """Обработка ввода названия шаблона"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(message.from_user.id, db)
        
        template_name = message.text.strip()
        
        # Проверяем длину названия
        if len(template_name) < 3:
            await message.answer(
                "❌ Название шаблона должно содержать минимум 3 символа.\n"
                "Введите название шаблона еще раз:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Назад", callback_data="template_management")]
                ])
            )
            return
        
        if len(template_name) > 50:
            await message.answer(
                "❌ Название шаблона не должно превышать 50 символов.\n"
                "Введите название шаблона еще раз:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Назад", callback_data="template_management")]
                ])
            )
            return
        
        # Сохраняем название в состоянии
        await state.update_data(template_name=template_name)
        
        # Переходим к вводу времени начала
        await message.answer(
            f"✅ Название шаблона: <b>{template_name}</b>\n\n"
            "🕒 Теперь введите время начала смены в формате ЧЧ:ММ\n"
            "(например: 09:00, 14:30, 22:15):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="template_management")]
            ]),
            parse_mode="HTML"
        )
        
        await state.set_state(ShiftManagementStates.template_time_input)
        
    except Exception as e:
        logger.error(f"Ошибка ввода названия шаблона: {e}")
        await message.answer("❌ Произошла ошибка, попробуйте еще раз")
    finally:
        if db:
            db.close()


@router.message(StateFilter(ShiftManagementStates.template_time_input))
async def handle_template_time_input(message: Message, state: FSMContext, db=None, roles: list = None, user=None):
    """Обработка ввода времени начала шаблона"""
    try:
        if not db:
            db = next(get_db())
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
                "❌ Неверный формат времени!\n\n"
                "Введите время в формате ЧЧ:ММ (например: 09:00, 14:30):",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Назад", callback_data="template_management")]
                ])
            )
            return
        
        # Сохраняем время в состоянии
        await state.update_data(start_hour=hour, start_minute=minute)
        
        # Переходим к вводу продолжительности
        await message.answer(
            f"✅ Время начала: <b>{hour:02d}:{minute:02d}</b>\n\n"
            "⏱️ Введите продолжительность смены в часах\n"
            "(например: 8, 12, 4):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="template_management")]
            ]),
            parse_mode="HTML"
        )
        
        await state.set_state(ShiftManagementStates.template_duration_input)
        
    except Exception as e:
        logger.error(f"Ошибка ввода времени шаблона: {e}")
        await message.answer("❌ Произошла ошибка, попробуйте еще раз")
    finally:
        if db:
            db.close()


@router.message(StateFilter(ShiftManagementStates.template_duration_input))
async def handle_template_duration_input(message: Message, state: FSMContext, db=None, roles: list = None, user=None):
    """Обработка ввода продолжительности шаблона"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(message.from_user.id, db)
        template_manager = TemplateManager(db)
        
        duration_text = message.text.strip()
        
        # Парсим продолжительность
        try:
            duration = int(duration_text)
            if duration < 1 or duration > 24:
                raise ValueError("Неверная продолжительность")
        except ValueError:
            await message.answer(
                "❌ Неверная продолжительность!\n\n"
                "Введите продолжительность смены в часах (от 1 до 24):",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Назад", callback_data="template_management")]
                ])
            )
            return
        
        # Получаем данные из состояния
        data = await state.get_data()
        template_name = data.get('template_name')
        start_hour = data.get('start_hour')
        start_minute = data.get('start_minute', 0)
        
        # Создаем шаблон в базе данных
        template = template_manager.create_template(
            name=template_name,
            start_hour=start_hour,
            start_minute=start_minute,
            duration_hours=duration,
            description=f"Шаблон {template_name}",
            is_active=True
        )
        
        if template:
            await message.answer(
                f"✅ <b>Шаблон создан успешно!</b>\n\n"
                f"📋 Название: <b>{template_name}</b>\n"
                f"🕒 Время: <b>{start_hour:02d}:{start_minute:02d}</b>\n"
                f"⏱️ Продолжительность: <b>{duration}ч</b>\n\n"
                f"Шаблон добавлен в базу данных и готов к использованию.",
                reply_markup=get_template_management_keyboard(lang),
                parse_mode="HTML"
            )
        else:
            await message.answer(
                "❌ Не удалось создать шаблон. Возможно, шаблон с таким названием уже существует.",
                reply_markup=get_template_management_keyboard(lang)
            )
        
        await state.set_state(ShiftManagementStates.template_menu)
        
    except Exception as e:
        logger.error(f"Ошибка создания шаблона: {e}")
        await message.answer(
            "❌ Произошла ошибка при создании шаблона",
            reply_markup=get_template_management_keyboard(lang)
        )
    finally:
        if db:
            db.close()


@router.callback_query(F.data == "templates_edit")
@require_role(['admin', 'manager'])
async def handle_edit_templates(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Редактирование шаблонов смен"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)
        template_manager = TemplateManager(db)
        
        logger.debug(f"Начинаем редактирование шаблонов для пользователя {callback.from_user.id}")
        
        # Получаем все шаблоны для редактирования
        templates = template_manager.get_templates(active_only=False)
        
        logger.debug(f"Найдено шаблонов: {len(templates)}")
        
        if not templates:
            await callback.message.edit_text(
                "✏️ <b>Редактирование шаблонов</b>\n\n"
                "❌ Шаблонов для редактирования не найдено\n\n"
                "Сначала создайте шаблоны с помощью кнопки 'Создать новый шаблон'",
                reply_markup=get_template_management_keyboard(lang),
                parse_mode="HTML"
            )
            await callback.answer("Шаблонов не найдено")
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
            [InlineKeyboardButton(text="🔙 Назад", callback_data="template_management")]
        ])
        
        logger.debug("Отправляем сообщение со списком шаблонов")
        
        await callback.message.edit_text(
            "✏️ <b>Редактирование шаблонов</b>\n\n"
            "Выберите шаблон для редактирования:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="HTML"
        )
        
        logger.debug("Устанавливаем состояние")
        await state.set_state(TemplateManagementStates.editing_template)
        
        logger.debug("Отвечаем на callback")
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка редактирования шаблонов: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(lambda c: c.data.startswith("template_edit_") and c.data.replace("template_edit_", "").isdigit())
@require_role(['admin', 'manager'])
async def handle_edit_template_details(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Редактирование конкретного шаблона"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)
        template_manager = TemplateManager(db)
        
        # Извлекаем ID шаблона из callback_data
        template_id = int(callback.data.replace("template_edit_", ""))
        
        # Получаем шаблон из базы данных
        template = db.query(ShiftTemplate).filter(ShiftTemplate.id == template_id).first()
        
        if not template:
            await callback.answer("❌ Шаблон не найден", show_alert=True)
            return
        
        # Формируем информацию о шаблоне
        status_text = "Активен" if template.is_active else "Неактивен"
        time_info = f"{template.start_hour:02d}:{template.start_minute or 0:02d}"
        
        specialization_info = "Не указаны"
        if template.required_specializations:
            specialization_info = ", ".join(template.required_specializations)
        
        template_info = (
            f"✏️ <b>Редактирование шаблона</b>\n\n"
            f"📋 <b>Название:</b> {template.name}\n"
            f"📝 <b>Описание:</b> {template.description or 'Не указано'}\n"
            f"🕒 <b>Время начала:</b> {time_info}\n"
            f"⏱️ <b>Продолжительность:</b> {template.duration_hours}ч\n"
            f"🎯 <b>Специализации:</b> {specialization_info}\n"
            f"📊 <b>Статус:</b> {status_text}\n\n"
            f"Выберите что хотите изменить:"
        )
        
        # Клавиатура редактирования
        keyboard = [
            [InlineKeyboardButton(text="📝 Изменить название", callback_data=f"template_edit_name_{template_id}")],
            [InlineKeyboardButton(text="📄 Изменить описание", callback_data=f"template_edit_description_{template_id}")],
            [InlineKeyboardButton(text="🕒 Изменить время", callback_data=f"template_edit_time_{template_id}")],
            [InlineKeyboardButton(text="⏱️ Изменить продолжительность", callback_data=f"template_edit_duration_{template_id}")],
            [
                InlineKeyboardButton(
                    text="✅ Активировать" if not template.is_active else "❌ Деактивировать",
                    callback_data=f"template_toggle_active_{template_id}"
                )
            ],
            [InlineKeyboardButton(text="🗑️ Удалить шаблон", callback_data=f"template_delete_{template_id}")],
            [InlineKeyboardButton(text="🔙 Назад к списку", callback_data="templates_edit")]
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
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data.startswith("template_toggle_active_"))
@require_role(['admin', 'manager'])
async def handle_toggle_template_active(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Переключение активности шаблона"""
    try:
        if not db:
            db = next(get_db())
        template_manager = TemplateManager(db)
        
        # Извлекаем ID шаблона
        template_id = int(callback.data.replace("template_toggle_active_", ""))
        
        # Получаем шаблон
        template = db.query(ShiftTemplate).filter(ShiftTemplate.id == template_id).first()
        
        if not template:
            await callback.answer("❌ Шаблон не найден", show_alert=True)
            return
        
        # Переключаем активность
        new_status = not template.is_active
        template.is_active = new_status
        
        try:
            db.commit()
            success = True
        except Exception as e:
            db.rollback()
            logger.error(f"Ошибка обновления шаблона: {e}")
            success = False
        
        if success:
            status_text = "активирован" if new_status else "деактивирован"
            await callback.answer(f"✅ Шаблон {status_text}")
            
            # Обновляем отображение
            await handle_edit_template_details(callback, state, db, roles, user)
        else:
            await callback.answer("❌ Не удалось изменить статус", show_alert=True)
        
    except Exception as e:
        logger.error(f"Ошибка переключения активности шаблона: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


# Обработчики редактирования полей шаблона
@router.callback_query(F.data.startswith("template_edit_name_"))
@require_role(['admin', 'manager'])
async def handle_edit_template_name(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Изменение названия шаблона"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)
        
        template_id = int(callback.data.replace("template_edit_name_", ""))
        template = db.query(ShiftTemplate).filter(ShiftTemplate.id == template_id).first()
        
        if not template:
            await callback.answer("❌ Шаблон не найден", show_alert=True)
            return
        
        await callback.message.edit_text(
            f"📝 <b>Изменение названия шаблона</b>\n\n"
            f"Текущее название: <b>{template.name}</b>\n\n"
            f"Введите новое название:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Отмена", callback_data=f"template_edit_{template_id}")]
            ]),
            parse_mode="HTML"
        )
        
        await state.update_data(editing_template_id=template_id, editing_field="name")
        await state.set_state(TemplateManagementStates.editing_field)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка изменения названия шаблона: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data.startswith("template_edit_description_"))
@require_role(['admin', 'manager'])
async def handle_edit_template_description(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Изменение описания шаблона"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)
        
        template_id = int(callback.data.replace("template_edit_description_", ""))
        template = db.query(ShiftTemplate).filter(ShiftTemplate.id == template_id).first()
        
        if not template:
            await callback.answer("❌ Шаблон не найден", show_alert=True)
            return
        
        await callback.message.edit_text(
            f"📄 <b>Изменение описания шаблона</b>\n\n"
            f"Текущее описание: <b>{template.description or 'Не указано'}</b>\n\n"
            f"Введите новое описание:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Отмена", callback_data=f"template_edit_{template_id}")]
            ]),
            parse_mode="HTML"
        )
        
        await state.update_data(editing_template_id=template_id, editing_field="description")
        await state.set_state(TemplateManagementStates.editing_field)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка изменения описания шаблона: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data.startswith("template_edit_time_"))
@require_role(['admin', 'manager'])
async def handle_edit_template_time(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Изменение времени начала шаблона"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)
        
        template_id = int(callback.data.replace("template_edit_time_", ""))
        template = db.query(ShiftTemplate).filter(ShiftTemplate.id == template_id).first()
        
        if not template:
            await callback.answer("❌ Шаблон не найден", show_alert=True)
            return
        
        await callback.message.edit_text(
            f"🕒 <b>Изменение времени начала шаблона</b>\n\n"
            f"Текущее время начала: <b>{template.start_hour:02d}:00</b>\n\n"
            f"Введите новый час начала смены (от 0 до 23):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Отмена", callback_data=f"template_edit_{template_id}")]
            ]),
            parse_mode="HTML"
        )
        
        await state.update_data(editing_template_id=template_id, editing_field="start_hour")
        await state.set_state(TemplateManagementStates.editing_field)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка изменения времени шаблона: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data.startswith("template_edit_duration_"))
@require_role(['admin', 'manager'])
async def handle_edit_template_duration(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Изменение продолжительности шаблона"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)
        
        template_id = int(callback.data.replace("template_edit_duration_", ""))
        template = db.query(ShiftTemplate).filter(ShiftTemplate.id == template_id).first()
        
        if not template:
            await callback.answer("❌ Шаблон не найден", show_alert=True)
            return
        
        await callback.message.edit_text(
            f"⏱️ <b>Изменение продолжительности шаблона</b>\n\n"
            f"Текущая продолжительность: <b>{template.duration_hours} ч.</b>\n\n"
            f"Введите новую продолжительность в часах (от 1 до 24):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Отмена", callback_data=f"template_edit_{template_id}")]
            ]),
            parse_mode="HTML"
        )
        
        await state.update_data(editing_template_id=template_id, editing_field="duration_hours")
        await state.set_state(TemplateManagementStates.editing_field)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка изменения продолжительности шаблона: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(lambda c: c.data.startswith("template_delete_") and not c.data.startswith("template_delete_confirm_") and c.data.replace("template_delete_", "").isdigit())
@require_role(['admin', 'manager'])
async def handle_delete_template(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Удаление шаблона"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)
        
        template_id = int(callback.data.replace("template_delete_", ""))
        template = db.query(ShiftTemplate).filter(ShiftTemplate.id == template_id).first()
        
        if not template:
            await callback.answer("❌ Шаблон не найден", show_alert=True)
            return
        
        # Показываем подтверждение удаления
        await callback.message.edit_text(
            f"🗑️ <b>Удаление шаблона</b>\n\n"
            f"⚠️ Вы уверены, что хотите удалить шаблон <b>{template.name}</b>?\n\n"
            f"Это действие нельзя отменить!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"template_delete_confirm_{template_id}"),
                    InlineKeyboardButton(text="❌ Отмена", callback_data=f"template_edit_{template_id}")
                ]
            ]),
            parse_mode="HTML"
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка удаления шаблона: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(lambda c: c.data.startswith("template_delete_confirm_") and c.data.replace("template_delete_confirm_", "").isdigit())
@require_role(['admin', 'manager'])
async def handle_delete_template_confirm(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Подтверждение удаления шаблона"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)
        template_manager = TemplateManager(db)
        
        template_id = int(callback.data.replace("template_delete_confirm_", ""))
        template = db.query(ShiftTemplate).filter(ShiftTemplate.id == template_id).first()
        
        if not template:
            await callback.answer("❌ Шаблон не найден", show_alert=True)
            return
        
        template_name = template.name
        
        # Попробуем удалить шаблон через менеджер (с проверками)
        success = template_manager.delete_template(template_id, force=False)
        
        if success:
            await callback.answer(f"✅ Шаблон '{template_name}' удален")
            # Возвращаемся к списку шаблонов
            await handle_edit_templates(callback, state, db, roles, user)
        else:
            # Показываем опцию принудительного удаления
            await callback.message.edit_text(
                f"⚠️ <b>Невозможно удалить шаблон</b>\n\n"
                f"Шаблон <b>{template_name}</b> используется в существующих сменах.\n\n"
                f"Хотите удалить принудительно?",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⚠️ Принудительно удалить", callback_data=f"template_force_delete_{template_id}")],
                    [InlineKeyboardButton(text="❌ Отмена", callback_data=f"template_edit_{template_id}")]
                ]),
                parse_mode="HTML"
            )
        
    except Exception as e:
        logger.error(f"Ошибка подтверждения удаления шаблона: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data.startswith("template_force_delete_"))
@require_role(['admin', 'manager'])
async def handle_force_delete_template(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Принудительное удаление шаблона"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)
        template_manager = TemplateManager(db)
        
        template_id = int(callback.data.replace("template_force_delete_", ""))
        template = db.query(ShiftTemplate).filter(ShiftTemplate.id == template_id).first()
        
        if not template:
            await callback.answer("❌ Шаблон не найден", show_alert=True)
            return
        
        template_name = template.name
        
        # Принудительно удаляем шаблон
        success = template_manager.delete_template(template_id, force=True)
        
        if success:
            await callback.answer(f"✅ Шаблон '{template_name}' принудительно удален")
            # Возвращаемся к списку шаблонов
            await handle_edit_templates(callback, state, db, roles, user)
        else:
            await callback.answer("❌ Не удалось удалить шаблон", show_alert=True)
        
    except Exception as e:
        logger.error(f"Ошибка принудительного удаления шаблона: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


# Обработчик ввода новых значений полей
@router.message(StateFilter(TemplateManagementStates.editing_field))
async def handle_template_field_input(message: Message, state: FSMContext, db=None, roles: list = None, user=None):
    """Обработка ввода нового значения поля шаблона"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(message.from_user.id, db)
        
        data = await state.get_data()
        template_id = data.get('editing_template_id')
        field = data.get('editing_field')
        
        if not template_id or not field:
            await message.answer("❌ Ошибка: не найдены данные для редактирования")
            return
        
        template = db.query(ShiftTemplate).filter(ShiftTemplate.id == template_id).first()
        
        if not template:
            await message.answer("❌ Шаблон не найден")
            return
        
        new_value = message.text.strip()
        
        # Валидация и обновление поля
        if field == "name":
            if len(new_value) < 3:
                await message.answer("❌ Название должно содержать минимум 3 символа")
                return
            template.name = new_value
            
        elif field == "description":
            template.description = new_value if new_value else None
            
        elif field == "start_hour":
            try:
                start_hour = int(new_value)
                if not (0 <= start_hour <= 23):
                    await message.answer("❌ Час должен быть от 0 до 23")
                    return
                template.start_hour = start_hour
            except ValueError:
                await message.answer("❌ Введите корректное число от 0 до 23")
                return
                
        elif field == "duration_hours":
            try:
                duration = int(new_value)
                if not (1 <= duration <= 24):
                    await message.answer("❌ Продолжительность должна быть от 1 до 24 часов")
                    return
                template.duration_hours = duration
            except ValueError:
                await message.answer("❌ Введите корректное число от 1 до 24")
                return
        else:
            await message.answer("❌ Неизвестное поле для редактирования")
            return
        
        # Сохраняем изменения
        db.commit()
        
        # Отображаем успешное сообщение с правильным текстом
        field_names = {
            "name": "Название",
            "description": "Описание",
            "start_hour": "Время начала",
            "duration_hours": "Продолжительность"
        }
        
        field_display = field_names.get(field, field.capitalize())
        
        await message.answer(
            f"✅ {field_display} шаблона успешно изменено!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К шаблону", callback_data=f"template_edit_{template_id}")]
            ])
        )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка обновления поля шаблона: {e}")
        await message.answer("❌ Произошла ошибка при сохранении")
    finally:
        if db:
            db.close()


@router.callback_query(F.data == "create_shift_from_template")
@require_role(['admin', 'manager'])
async def handle_create_shift_template(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Создание смены из шаблона"""
    try:
        if not db:
            db = next(get_db())
        template_manager = TemplateManager(db)
        lang = get_user_language(callback.from_user.id, db)
        
        # Получаем активные шаблоны
        templates = template_manager.get_templates(active_only=True)
        
        if not templates:
            await callback.message.edit_text(
                "⚠️ <b>Нет доступных шаблонов</b>\n\n"
                "Сначала создайте шаблоны смен в разделе управления шаблонами.",
                reply_markup=get_planning_menu(lang),
                parse_mode="HTML"
            )
            await callback.answer("Нет доступных шаблонов", show_alert=True)
            return
        
        await callback.message.edit_text(
            "🗂️ <b>Выбор шаблона смены</b>\n\n"
            "Выберите шаблон для создания смены:",
            reply_markup=get_template_selection_keyboard(templates, lang),
            parse_mode="HTML"
        )
        
        await state.set_state(ShiftManagementStates.selecting_template)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка выбора шаблона: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("select_template:"))
@require_role(['admin', 'manager'])
async def handle_template_selection(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Выбор шаблона и даты"""
    try:
        template_id = int(callback.data.split(':')[1])
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)
        
        # Сохраняем ID шаблона в состояние
        await state.update_data(template_id=template_id)
        
        template_manager = TemplateManager(db)
        
        # Получаем информацию о шаблоне
        template = db.query(ShiftTemplate).filter(ShiftTemplate.id == template_id).first()
        
        if not template:
            await callback.answer("❌ Шаблон не найден", show_alert=True)
            return
        
        await callback.message.edit_text(
            f"📅 <b>Выбор даты для смены</b>\n\n"
            f"<b>Шаблон:</b> {template.name}\n"
            f"<b>Время:</b> {template.start_hour:02d}:{template.start_minute or 0:02d} - "
            f"{(template.start_hour + template.duration_hours) % 24:02d}:00\n"
            f"<b>Специализация:</b> {', '.join(template.required_specializations) if template.required_specializations else 'Любая'}\n\n"
            "Выберите дату:",
            reply_markup=get_date_selection_keyboard(lang),
            parse_mode="HTML"
        )
        
        await state.set_state(ShiftManagementStates.selecting_date)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка выбора шаблона: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data.startswith("select_date:"))
@require_role(['admin', 'manager'])
async def handle_date_selection(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Создание смены на выбранную дату"""
    try:
        date_offset = int(callback.data.split(':')[1])
        target_date = date.today() + timedelta(days=date_offset)
        
        data = await state.get_data()
        template_id = data.get('template_id')
        
        if not template_id:
            await callback.answer("❌ Шаблон не найден", show_alert=True)
            return
        
        if not db:
            db = next(get_db())
        planning_service = ShiftPlanningService(db)
        lang = get_user_language(callback.from_user.id, db)
        
        # Создаем смены из шаблона
        created_shifts = planning_service.create_shift_from_template(
            template_id=template_id,
            target_date=target_date
        )
        
        if created_shifts:
            await callback.message.edit_text(
                f"✅ <b>Смены созданы успешно</b>\n\n"
                f"<b>Дата:</b> {target_date.strftime('%d.%m.%Y')}\n"
                f"<b>Создано смен:</b> {len(created_shifts)}\n\n"
                f"Смены добавлены в расписание и готовы к назначению исполнителей.",
                reply_markup=get_planning_menu(lang),
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                f"⚠️ <b>Смены не созданы</b>\n\n"
                f"Возможные причины:\n"
                f"• Смены на {target_date.strftime('%d.%m.%Y')} уже существуют\n"
                f"• День недели не включен в шаблон\n"
                f"• Нет доступных исполнителей\n\n"
                f"Проверьте настройки шаблона и попробуйте снова.",
                reply_markup=get_planning_menu(lang),
                parse_mode="HTML"
            )
        
        await state.set_state(ShiftManagementStates.planning_menu)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка создания смены: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "plan_weekly_schedule")
@require_role(['admin', 'manager'])
async def handle_weekly_planning(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Планирование недельного расписания"""
    try:
        if not db:
            db = next(get_db())
        planning_service = ShiftPlanningService(db)
        lang = get_user_language(callback.from_user.id, db)
        
        # Планируем смены на следующую неделю
        start_date = date.today() + timedelta(days=1)
        results = planning_service.plan_weekly_schedule(start_date)
        
        stats = results['statistics']
        
        week_info = (
            f"📅 <b>Недельное планирование</b>\n\n"
            f"<b>Период:</b> {results['week_start'].strftime('%d.%m.%Y')} - "
            f"{(results['week_start'] + timedelta(days=6)).strftime('%d.%m.%Y')}\n"
            f"<b>Создано смен:</b> {stats['total_shifts']}\n\n"
            f"<b>По дням недели:</b>\n"
        )
        
        for day_name, count in stats['shifts_by_day'].items():
            week_info += f"• {day_name}: {count} смен\n"
        
        if stats['shifts_by_template']:
            week_info += f"\n<b>По шаблонам:</b>\n"
            for template_name, count in stats['shifts_by_template'].items():
                week_info += f"• {template_name}: {count} смен\n"
        
        if results['errors']:
            week_info += f"\n⚠️ <b>Ошибки:</b>\n"
            for error in results['errors'][:3]:  # Показываем только первые 3 ошибки
                week_info += f"• {error}\n"
        
        await callback.message.edit_text(
            week_info,
            reply_markup=get_planning_menu(lang),
            parse_mode="HTML"
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка недельного планирования: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "shift_analytics")
@require_role(['admin', 'manager'])
async def handle_shift_analytics(callback: CallbackQuery, state: FSMContext, db=None):
    """Меню аналитики смен"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)
        
        await callback.message.edit_text(
            "📊 <b>Аналитика смен</b>\n\n"
            "Выберите тип анализа:",
            reply_markup=get_analytics_menu(lang),
            parse_mode="HTML"
        )
        
        await state.set_state(ShiftManagementStates.analytics_menu)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка аналитики: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data == "template_management")
@require_role(['admin', 'manager'])
async def handle_template_management(callback: CallbackQuery, state: FSMContext, db=None):
    """Управление шаблонами смен"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)
        
        await callback.message.edit_text(
            "🗂️ <b>Управление шаблонами</b>\n\n"
            "Функция в разработке. Используйте команду /shifts для создания смен.",
            parse_mode="HTML"
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка управления шаблонами: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data == "shift_executor_assignment")  
@require_role(['admin', 'manager'])
async def handle_shift_executor_assignment(callback: CallbackQuery, state: FSMContext, db=None):
    """Назначение исполнителей для смен"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)
        
        await callback.message.edit_text(
            "👥 <b>Назначение исполнителей</b>\n\n"
            "Функция в разработке. Используйте интерфейс заявок для назначения исполнителей.",
            parse_mode="HTML"
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка назначения исполнителей: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data == "weekly_analytics")
@require_role(['admin', 'manager'])
async def handle_weekly_analytics(callback: CallbackQuery, state: FSMContext):
    """Аналитика за неделю"""
    try:
        db = next(get_db())
        planning_service = ShiftPlanningService(db)
        if not db:
            db = next(get_db())
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
                f"❌ <b>Ошибка аналитики</b>\n\n"
                f"{analytics['error']}",
                reply_markup=get_analytics_menu(lang),
                parse_mode="HTML"
            )
            await callback.answer()
            return
        
        # Формируем отчет
        report = (
            f"📊 <b>Недельная аналитика смен</b>\n\n"
            f"<b>Период:</b> {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}\n"
            f"<b>Дней анализа:</b> {analytics['period']['total_days']}\n\n"
        )
        
        # Статистика смен
        if analytics.get('shift_analytics'):
            sa = analytics['shift_analytics']
            report += (
                f"<b>📈 Статистика смен:</b>\n"
                f"• Всего смен: {sa.get('total_shifts', 0)}\n"
                f"• Средняя эффективность: {sa.get('average_efficiency', 0):.1f}%\n"
                f"• Процент завершенных: {sa.get('completion_rate', 0):.1f}%\n"
                f"• Процент вовремя: {sa.get('on_time_rate', 0):.1f}%\n\n"
            )
        
        # Эффективность планирования
        if analytics.get('planning_efficiency') and 'error' not in analytics['planning_efficiency']:
            pe = analytics['planning_efficiency']
            report += (
                f"<b>⚙️ Эффективность планирования:</b>\n"
                f"• Процент назначения: {pe.get('assignment_rate', 0):.1f}%\n"
                f"• Средняя длительность: {pe.get('avg_actual_duration', 0):.1f}ч\n"
                f"• Неназначенных смен: {pe.get('unassigned_shifts', 0)}\n\n"
            )
        
        # Рекомендации
        if analytics.get('recommendations'):
            recommendations = analytics['recommendations'][:3]  # Первые 3 рекомендации
            report += f"<b>💡 Рекомендации:</b>\n"
            for i, rec in enumerate(recommendations, 1):
                rec_text = rec.get('description', rec.get('recommendation', 'Нет описания'))
                report += f"{i}. {rec_text[:100]}...\n"
        
        await callback.message.edit_text(
            report,
            reply_markup=get_analytics_menu(lang),
            parse_mode="HTML"
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка недельной аналитики: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "workload_forecast")
@require_role(['admin', 'manager'])
async def handle_workload_forecast(callback: CallbackQuery, state: FSMContext):
    """Прогноз рабочей нагрузки"""
    try:
        db = next(get_db())
        planning_service = ShiftPlanningService(db)
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)
        
        # Прогноз на следующие 5 дней
        target_date = date.today() + timedelta(days=1)
        prediction = await planning_service.predict_workload(
            target_date=target_date,
            days_ahead=5
        )
        
        if 'error' in prediction:
            await callback.message.edit_text(
                f"❌ <b>Ошибка прогноза</b>\n\n"
                f"{prediction['error']}",
                reply_markup=get_analytics_menu(lang),
                parse_mode="HTML"
            )
            await callback.answer()
            return
        
        # Формируем отчет прогноза
        forecast_period = prediction['forecast_period']
        summary = prediction['summary']
        
        report = (
            f"🔮 <b>Прогноз рабочей нагрузки</b>\n\n"
            f"<b>Период:</b> {forecast_period['start_date'].strftime('%d.%m.%Y')} - "
            f"{forecast_period['end_date'].strftime('%d.%m.%Y')}\n"
            f"<b>Средний прогноз:</b> {summary['avg_predicted_requests']} заявок/день\n\n"
        )
        
        # Ежедневные прогнозы
        report += "<b>📅 По дням:</b>\n"
        for daily_pred in prediction['daily_predictions'][:5]:  # Первые 5 дней
            date_str = daily_pred['date'].strftime('%d.%m')
            requests = daily_pred['predicted_requests']
            load_level = daily_pred['load_level']
            confidence = daily_pred['confidence']
            
            load_emoji = {
                'low': '🟢',
                'medium': '🟡', 
                'high': '🔴'
            }.get(load_level, '⚪')
            
            report += f"• {date_str}: {requests} заявок {load_emoji} (уверенность: {confidence:.0%})\n"
        
        # Рекомендации по ресурсам
        if summary.get('resource_requirements'):
            req = summary['resource_requirements']
            report += (
                f"\n<b>💼 Рекомендации по ресурсам:</b>\n"
                f"• Смен в день: {req['recommended_daily_shifts']}\n"
                f"• Пик нагрузки: {req['peak_day_shifts']} смен\n"
                f"• Минимум исполнителей: {req['min_executors_needed']}\n"
            )
        
        # Дни с высокой/низкой нагрузкой
        if summary.get('peak_load_days'):
            peak_dates = [d.strftime('%d.%m') for d in summary['peak_load_days'][:3]]
            report += f"\n🔴 <b>Дни высокой нагрузки:</b> {', '.join(peak_dates)}\n"
        
        if summary.get('low_load_days'):
            low_dates = [d.strftime('%d.%m') for d in summary['low_load_days'][:3]]
            report += f"🟢 <b>Дни низкой нагрузки:</b> {', '.join(low_dates)}\n"
        
        await callback.message.edit_text(
            report,
            reply_markup=get_analytics_menu(lang),
            parse_mode="HTML"
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка прогноза нагрузки: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "optimization_recommendations")
@require_role(['admin', 'manager'])
async def handle_optimization_recommendations(callback: CallbackQuery, state: FSMContext):
    """Рекомендации по оптимизации"""
    try:
        db = next(get_db())
        planning_service = ShiftPlanningService(db)
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)
        
        # Получаем рекомендации на сегодня
        recommendations = await planning_service.get_optimization_recommendations(
            target_date=date.today()
        )
        
        if 'error' in recommendations:
            await callback.message.edit_text(
                f"❌ <b>Ошибка получения рекомендаций</b>\n\n"
                f"{recommendations['error']}",
                reply_markup=get_analytics_menu(lang),
                parse_mode="HTML"
            )
            await callback.answer()
            return
        
        # Формируем отчет рекомендаций
        current_state = recommendations['current_state']
        target_date_str = recommendations['date'].strftime('%d.%m.%Y')
        
        report = (
            f"💡 <b>Рекомендации по оптимизации</b>\n\n"
            f"<b>Дата:</b> {target_date_str}\n\n"
            f"<b>📊 Текущее состояние:</b>\n"
            f"• Всего смен: {current_state['shifts_count']}\n"
            f"• Назначено: {current_state['assigned_shifts']}\n"
            f"• Не назначено: {current_state['unassigned_shifts']}\n\n"
        )
        
        # Приоритетные действия
        priority_actions = recommendations.get('priority_actions', [])
        if priority_actions:
            report += "<b>🚨 Приоритетные действия:</b>\n"
            for action in priority_actions:
                urgency_emoji = {
                    'high': '🔴',
                    'medium': '🟡',
                    'low': '🟢'
                }.get(action.get('urgency', 'medium'), '⚪')
                
                report += f"{urgency_emoji} {action['description']}\n"
                report += f"   → {action['action']}\n\n"
        
        # Предложения по оптимизации
        optimization_suggestions = recommendations.get('optimization_suggestions', [])
        if optimization_suggestions:
            report += "<b>⚙️ Предложения по оптимизации:</b>\n"
            for suggestion in optimization_suggestions:
                report += f"• {suggestion['description']}\n"
                report += f"  Действие: {suggestion['action']}\n\n"
        
        # ИИ рекомендации (если есть)
        if recommendations.get('ai_recommendations'):
            ai_recs = recommendations['ai_recommendations']
            if isinstance(ai_recs, dict) and ai_recs.get('recommendations'):
                report += "<b>🤖 ИИ рекомендации:</b>\n"
                for rec in ai_recs['recommendations'][:2]:  # Первые 2
                    rec_text = rec.get('description', rec.get('recommendation', 'Нет описания'))
                    report += f"• {rec_text[:80]}...\n"
        
        if not priority_actions and not optimization_suggestions:
            report += "✅ <b>Все отлично!</b>\nТекущее планирование смен оптимально."
        
        await callback.message.edit_text(
            report,
            reply_markup=get_analytics_menu(lang),
            parse_mode="HTML"
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка рекомендаций по оптимизации: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "back_to_shifts")
async def handle_back_to_shifts(callback: CallbackQuery, state: FSMContext):
    """Возврат к главному меню смен"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)
        
        await callback.message.edit_text(
            "🔧 <b>Управление сменами</b>\n\n"
            "Выберите действие:",
            reply_markup=get_main_shift_menu(lang),
            parse_mode="HTML"
        )
        
        await state.set_state(ShiftManagementStates.main_menu)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка возврата к меню смен: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "back_to_planning")
async def handle_back_to_planning(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Возврат к меню планирования"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)
        
        await callback.message.edit_text(
            "📅 <b>Планирование смен</b>\n\n"
            "Выберите действие:",
            reply_markup=get_planning_menu(lang),
            parse_mode="HTML"
        )
        
        await state.set_state(ShiftManagementStates.planning_menu)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка возврата к планированию: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "back_to_analytics")
async def handle_back_to_analytics(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Возврат к меню аналитики"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)
        
        await callback.message.edit_text(
            "📊 <b>Аналитика смен</b>\n\n"
            "Выберите тип анализа:",
            reply_markup=get_analytics_menu(lang),
            parse_mode="HTML"
        )
        
        await state.set_state(ShiftManagementStates.analytics_menu)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка возврата к аналитике: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)