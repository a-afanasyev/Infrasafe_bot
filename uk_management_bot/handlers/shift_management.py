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
from sqlalchemy.orm import Session
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
    get_template_management_keyboard,
    get_executor_assignment_keyboard
)
from uk_management_bot.states.shift_management import ShiftManagementStates, TemplateManagementStates, ExecutorAssignmentStates
from uk_management_bot.middlewares.auth import require_role
from uk_management_bot.utils.helpers import get_user_language
import logging

logger = logging.getLogger(__name__)
router = Router()

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
        return "Любая" if language == "ru" else "Har qanday"

    translations = SPECIALIZATION_TRANSLATIONS.get(language, SPECIALIZATION_TRANSLATIONS["ru"])
    translated = [translations.get(spec, spec) for spec in specializations]
    return ", ".join(translated)


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
                from uk_management_bot.utils.constants import SPECIALIZATIONS
                spec_names = [SPECIALIZATIONS.get(spec, spec) for spec in template.required_specializations[:2]]
                specialization_info = f" • {', '.join(spec_names)}"
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
        
        # Сохраняем продолжительность в состоянии и переходим к выбору специализаций
        await state.update_data(duration=duration)
        
        from uk_management_bot.utils.constants import SPECIALIZATIONS
        keyboard = []
        
        for spec_key, spec_name in SPECIALIZATIONS.items():
            keyboard.append([InlineKeyboardButton(
                text=f"⭕ {spec_name}",
                callback_data=f"template_create_spec_{spec_key}"
            )])
        
        keyboard.append([InlineKeyboardButton(text="➡️ Далее (без специализаций)", callback_data="template_create_no_specs")])
        keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="template_management")])
        
        await message.answer(
            f"✅ Продолжительность смены: <b>{duration} ч.</b>\n\n"
            "🎯 <b>Выберите специализации для шаблона:</b>\n\n"
            "Нажимайте на специализации для их выбора.\n"
            "Можете выбрать несколько или пропустить этот шаг.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="HTML"
        )
        
        await state.set_state(ShiftManagementStates.template_specialization_selection)
        
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
            from uk_management_bot.utils.constants import SPECIALIZATIONS
            specialization_info = ", ".join([SPECIALIZATIONS.get(spec, spec) for spec in template.required_specializations])
        
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
            [InlineKeyboardButton(text="🎯 Изменить специализации", callback_data=f"template_edit_specializations_{template_id}")],
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


@router.callback_query(F.data.startswith("template_create_spec_"))
async def handle_template_create_specialization_toggle(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Переключение специализации при создании шаблона"""
    try:
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
        
        keyboard.append([InlineKeyboardButton(text="➡️ Далее (создать шаблон)", callback_data="template_create_finish")])
        keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="template_management")])
        
        selected_text = ", ".join([SPECIALIZATIONS.get(spec, spec) for spec in selected_specs]) if selected_specs else "Не выбраны"
        
        try:
            await callback.message.edit_text(
                f"🎯 <b>Выберите специализации для шаблона:</b>\n\n"
                f"<b>Выбранные специализации:</b> {selected_text}\n\n"
                "Нажимайте на специализации для их выбора/отмены.\n"
                "Когда закончите, нажмите 'Далее'.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="HTML"
            )
        except Exception as edit_error:
            if "message is not modified" not in str(edit_error):
                raise edit_error
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка переключения специализации при создании: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "template_create_finish")
async def handle_template_create_finish(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Завершение создания шаблона с выбранными специализациями"""
    try:
        if not db:
            db = next(get_db())
        
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
            description=f"Шаблон {template_name}",
            required_specializations=selected_specs if selected_specs else None,
            is_active=True,
            auto_create=True,
            days_of_week=[1, 2, 3, 4, 5, 6, 7],  # Все дни недели
            advance_days=1  # Создавать смены за 1 день
        )
        
        if template:
            from uk_management_bot.utils.constants import SPECIALIZATIONS
            selected_text = ", ".join([SPECIALIZATIONS.get(spec, spec) for spec in selected_specs]) if selected_specs else "Не указаны"
            await callback.message.edit_text(
                f"✅ <b>Шаблон создан успешно!</b>\n\n"
                f"📋 <b>Название:</b> {template.name}\n"
                f"🕒 <b>Время начала:</b> {template.start_hour:02d}:{(template.start_minute or 0):02d}\n"
                f"⏱️ <b>Продолжительность:</b> {template.duration_hours}ч\n"
                f"🎯 <b>Специализации:</b> {selected_text}\n"
                f"📊 <b>Статус:</b> Активен\n\n"
                f"Шаблон готов к использованию для создания смен.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 К управлению шаблонами", callback_data="template_management")]
                ]),
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                "❌ Не удалось создать шаблон. Возможно, шаблон с таким названием уже существует.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Назад", callback_data="template_management")]
                ])
            )
        
        await state.clear()
        await callback.answer("✅ Шаблон создан!" if template else "❌ Ошибка создания")
        
    except Exception as e:
        logger.error(f"Ошибка завершения создания шаблона: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data == "template_create_no_specs")
async def handle_template_create_no_specs(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Создание шаблона без специализаций (совместимость со старым кодом)"""
    await handle_template_create_finish(callback, state, db, roles, user)


@router.callback_query(F.data.startswith("template_edit_specializations_"))
@require_role(['admin', 'manager'])
async def handle_edit_template_specializations(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Изменение специализаций шаблона"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)
        
        template_id = int(callback.data.replace("template_edit_specializations_", ""))
        template = db.query(ShiftTemplate).filter(ShiftTemplate.id == template_id).first()
        
        if not template:
            await callback.answer("❌ Шаблон не найден", show_alert=True)
            return
        
        current_specializations = template.required_specializations or []
        from uk_management_bot.utils.constants import SPECIALIZATIONS
        specializations_text = ", ".join([SPECIALIZATIONS.get(spec, spec) for spec in current_specializations]) if current_specializations else "Не указаны"
        
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
        
        keyboard.append([InlineKeyboardButton(text="💾 Сохранить", callback_data=f"template_spec_save_{template_id}")])
        keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"template_edit_{template_id}")])
        
        await callback.message.edit_text(
            f"🎯 <b>Изменение специализаций шаблона</b>\n\n"
            f"Шаблон: <b>{template.name}</b>\n"
            f"Текущие специализации: <b>{specializations_text}</b>\n\n"
            f"Выберите нужные специализации:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="HTML"
        )
        
        await state.update_data(editing_template_id=template_id)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка редактирования специализаций шаблона: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data.startswith("template_spec_toggle_"))
@require_role(['admin', 'manager'])
async def handle_toggle_template_specialization(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Переключение специализации шаблона"""
    try:
        if not db:
            db = next(get_db())
        
        # Парсим callback data: template_spec_toggle_{template_id}_{specialization}
        parts = callback.data.replace("template_spec_toggle_", "").split("_", 1)
        template_id = int(parts[0])
        specialization = parts[1]
        
        template = db.query(ShiftTemplate).filter(ShiftTemplate.id == template_id).first()
        
        if not template:
            await callback.answer("❌ Шаблон не найден", show_alert=True)
            return
        
        current_specs = template.required_specializations or []
        
        # Переключаем специализацию
        if specialization in current_specs:
            current_specs.remove(specialization)
        else:
            current_specs.append(specialization)
        
        # Принудительно устанавливаем новое значение и помечаем поле как измененное
        template.required_specializations = current_specs
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(template, 'required_specializations')
        
        db.commit()
        
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
        
        keyboard.append([InlineKeyboardButton(text="💾 Сохранить", callback_data=f"template_spec_save_{template_id}")])
        keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"template_edit_{template_id}")])
        
        specializations_text = ", ".join([SPECIALIZATIONS.get(spec, spec) for spec in current_specs]) if current_specs else "Не указаны"
        
        try:
            await callback.message.edit_text(
                f"🎯 <b>Изменение специализаций шаблона</b>\n\n"
                f"Шаблон: <b>{template.name}</b>\n"
                f"Текущие специализации: <b>{specializations_text}</b>\n\n"
                f"Выберите нужные специализации:",
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
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data.startswith("template_spec_save_"))
@require_role(['admin', 'manager'])
async def handle_save_template_specializations(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Сохранение специализаций шаблона"""
    try:
        if not db:
            db = next(get_db())
        
        template_id = int(callback.data.replace("template_spec_save_", ""))
        
        await callback.answer("✅ Специализации сохранены")
        
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
async def handle_shift_executor_assignment(callback: CallbackQuery, state: FSMContext, db: Session = None, user: User = None, roles: list = None):
    """Назначение исполнителей для смен"""
    try:
        if not db:
            db = next(get_db())
        lang = get_user_language(callback.from_user.id, db)

        # Получаем смены без назначенных исполнителей
        from datetime import datetime, timedelta
        now = datetime.now()
        week_ahead = now + timedelta(days=7)

        unassigned_shifts = db.query(Shift).filter(
            Shift.user_id.is_(None),
            Shift.status == 'planned',
            Shift.start_time.between(now, week_ahead)
        ).order_by(Shift.start_time).limit(10).all()

        if not unassigned_shifts:
            await callback.message.edit_text(
                "👥 <b>Назначение исполнителей</b>\n\n"
                "✅ Все смены на ближайшую неделю уже имеют назначенных исполнителей.\n\n"
                "📋 Для назначения заявок исполнителям используйте интерфейс заявок.",
                parse_mode="HTML",
                reply_markup=get_main_shift_menu()
            )
            await callback.answer()
            return

        # Показываем список смен для назначения
        from uk_management_bot.keyboards.shift_management import get_executor_assignment_keyboard

        text = "👥 <b>Назначение исполнителей</b>\n\n"
        text += f"📊 Найдено <b>{len(unassigned_shifts)}</b> смен без назначенных исполнителей:\n\n"

        for shift in unassigned_shifts:
            start_time = shift.start_time.strftime('%d.%m.%Y %H:%M')
            # Переводим специализации на язык пользователя
            specialization_text = translate_specializations(shift.specialization_focus, lang)
            text += f"🔹 <b>{start_time}</b> - {specialization_text}\n"

        text += "\n🎯 Выберите действие:"

        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_executor_assignment_keyboard()
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


# Handlers for Executor Assignment

@router.callback_query(F.data == "assign_to_shift")
@require_role(['admin', 'manager'])
async def handle_assign_to_shift(callback: CallbackQuery, state: FSMContext, db: Session = None, user: User = None, roles: list = None):
    """Назначить исполнителя на конкретную смену"""
    try:
        if not db:
            db = SessionLocal()
        lang = get_user_language(callback.from_user.id, db)

        # Получаем неназначенные смены
        from datetime import datetime, timedelta
        now = datetime.now()
        week_ahead = now + timedelta(days=7)

        unassigned_shifts = db.query(Shift).filter(
            Shift.user_id.is_(None),
            Shift.status == 'planned',
            Shift.start_time >= now,
            Shift.start_time <= week_ahead
        ).order_by(Shift.start_time).limit(10).all()

        if not unassigned_shifts:
            await callback.message.edit_text(
                "✅ <b>Все смены назначены</b>\n\n"
                "В настоящее время нет неназначенных смен.",
                reply_markup=get_executor_assignment_keyboard(lang),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        # Формируем список смен для выбора
        text = "👤 <b>Назначение на конкретную смену</b>\n\n"
        text += "📋 <b>Неназначенные смены:</b>\n\n"

        for i, shift in enumerate(unassigned_shifts, 1):
            # Переводим специализации на язык пользователя
            specialization_text = translate_specializations(shift.specialization_focus, lang)

            # Форматируем время
            start_date = shift.start_time.strftime('%d.%m.%Y')
            start_time = shift.start_time.strftime('%H:%M')
            end_time = shift.end_time.strftime('%H:%M') if shift.end_time else "—"

            text += (f"{i}. <b>{start_date}</b> "
                    f"{start_time}-{end_time}\n"
                    f"   🔧 {specialization_text}\n"
                    f"   📍 {shift.geographic_zone or 'Не указано'}\n\n")

        # Создаем клавиатуру для выбора смены
        keyboard = []
        for shift in unassigned_shifts:
            # Переводим специализации (показываем первые 2)
            if shift.specialization_focus and isinstance(shift.specialization_focus, list):
                first_two = shift.specialization_focus[:2]
                spec_text = translate_specializations(first_two, lang)
            else:
                spec_text = "Любая" if lang == "ru" else "Har qanday"

            button_text = f"{shift.start_time.strftime('%d.%m %H:%M')} - {spec_text}"
            keyboard.append([InlineKeyboardButton(
                text=button_text,
                callback_data=f"select_shift_for_assignment:{shift.id}"
            )])

        keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="executor_assignment")])

        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="HTML"
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка назначения на смену: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data == "ai_assignment")
@require_role(['admin', 'manager'])
async def handle_ai_assignment(callback: CallbackQuery, state: FSMContext, db: Session = None, user: User = None, roles: list = None):
    """ИИ-назначение исполнителей"""
    try:
        if not db:
            db = SessionLocal()
        lang = get_user_language(callback.from_user.id, db)

        from uk_management_bot.services.shift_assignment_service import ShiftAssignmentService
        assignment_service = ShiftAssignmentService(db)

        # Запускаем автоматическое назначение
        result = await assignment_service.auto_assign_executors_to_shifts(
            target_date=date.today(),
            days_ahead=7
        )

        if result.get('error'):
            await callback.message.edit_text(
                f"❌ <b>Ошибка ИИ-назначения</b>\n\n"
                f"{result['error']}",
                reply_markup=get_executor_assignment_keyboard(lang),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        # Формируем отчет о назначении
        assignments = result.get('assignments', [])
        conflicts = result.get('conflicts', [])
        unassigned = result.get('unassigned_shifts', [])

        text = "🤖 <b>Результат ИИ-назначения</b>\n\n"
        text += f"✅ <b>Назначено смен:</b> {len(assignments)}\n"
        text += f"⚠️ <b>Конфликтов:</b> {len(conflicts)}\n"
        text += f"❌ <b>Не назначено:</b> {len(unassigned)}\n\n"

        if assignments:
            text += "<b>📋 Успешные назначения:</b>\n"
            for assignment in assignments[:5]:  # Показываем первые 5
                shift = assignment.get('shift')
                executor = assignment.get('executor')
                confidence = assignment.get('confidence', 0)

                if shift and executor:
                    text += (f"• {shift.date.strftime('%d.%m')} {shift.start_time.strftime('%H:%M')} "
                            f"→ {executor.first_name} {executor.last_name} "
                            f"({confidence:.0%})\n")

            if len(assignments) > 5:
                text += f"... и ещё {len(assignments) - 5} назначений\n"
            text += "\n"

        if conflicts:
            text += "<b>⚠️ Конфликты (требуют ручного назначения):</b>\n"
            for conflict in conflicts[:3]:  # Показываем первые 3
                shift = conflict.get('shift')
                reason = conflict.get('reason', 'Неизвестная причина')
                if shift:
                    text += f"• {shift.date.strftime('%d.%m')} {shift.start_time.strftime('%H:%M')} - {reason}\n"

            if len(conflicts) > 3:
                text += f"... и ещё {len(conflicts) - 3} конфликтов\n"

        await callback.message.edit_text(
            text,
            reply_markup=get_executor_assignment_keyboard(lang),
            parse_mode="HTML"
        )

        await callback.answer("✅ ИИ-назначение завершено")

    except Exception as e:
        logger.error(f"Ошибка ИИ-назначения: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data == "bulk_assignment")
@require_role(['admin', 'manager'])
async def handle_bulk_assignment(callback: CallbackQuery, state: FSMContext, db: Session = None, user: User = None, roles: list = None):
    """Массовое назначение исполнителей"""
    try:
        if not db:
            db = SessionLocal()
        lang = get_user_language(callback.from_user.id, db)

        # Получаем статистику для массового назначения
        from datetime import datetime
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        total_unassigned = db.query(Shift).filter(
            Shift.user_id.is_(None),
            Shift.start_time >= today
        ).count()

        available_executors = db.query(User).filter(
            User.active_role == 'executor',
            User.status == 'approved'
        ).count()

        text = (f"📅 <b>Массовое назначение исполнителей</b>\n\n"
               f"📊 <b>Текущая ситуация:</b>\n"
               f"• Неназначенных смен: {total_unassigned}\n"
               f"• Доступно исполнителей: {available_executors}\n\n"
               f"<b>Выберите действие:</b>")

        keyboard = [
            [InlineKeyboardButton(text="🚀 Назначить все автоматически", callback_data="bulk_auto_assign")],
            [InlineKeyboardButton(text="📋 Назначить по специализации", callback_data="bulk_by_specialization")],
            [InlineKeyboardButton(text="📅 Назначить на период", callback_data="bulk_by_period")],
            [InlineKeyboardButton(text="⚡ Назначить по приоритету", callback_data="bulk_by_priority")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="executor_assignment")]
        ]

        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="HTML"
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка массового назначения: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data == "workload_analysis")
@require_role(['admin', 'manager'])
async def handle_workload_analysis(callback: CallbackQuery, state: FSMContext, db: Session = None, user: User = None, roles: list = None):
    """Анализ загруженности исполнителей"""
    try:
        if not db:
            db = SessionLocal()
        lang = get_user_language(callback.from_user.id, db)

        # Анализируем загруженность на ближайшие 7 дней
        end_date = date.today() + timedelta(days=7)

        # Получаем статистику по исполнителям
        from sqlalchemy import func
        executor_stats = db.query(
            User.id,
            User.first_name,
            User.last_name,
            func.count(Shift.id).label('shift_count'),
            func.sum(
                func.extract('epoch', Shift.end_time - Shift.start_time) / 3600
            ).label('total_hours')
        ).join(
            Shift, Shift.user_id == User.id
        ).filter(
            User.active_role == 'executor',
            Shift.start_time.between(datetime.now(), end_date)
        ).group_by(
            User.id, User.first_name, User.last_name
        ).order_by(
            func.count(Shift.id).desc()
        ).all()

        # Получаем исполнителей без смен
        assigned_executor_ids = [stat.id for stat in executor_stats]
        unassigned_executors = db.query(User).filter(
            User.role == 'executor',
            User.is_active == True,
            ~User.id.in_(assigned_executor_ids)
        ).all()

        text = "📊 <b>Анализ загруженности исполнителей</b>\n\n"
        text += f"<b>Период:</b> {date.today().strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}\n\n"

        if executor_stats:
            text += "<b>👥 Загруженность исполнителей:</b>\n"
            for stat in executor_stats[:10]:  # Показываем топ-10
                hours = stat.total_hours or 0
                load_level = "🔴" if hours > 40 else "🟡" if hours > 20 else "🟢"
                text += (f"{load_level} <b>{stat.first_name} {stat.last_name}</b>\n"
                        f"   Смен: {stat.shift_count}, Часов: {hours:.1f}ч\n")
            text += "\n"

        if unassigned_executors:
            text += f"<b>😴 Свободные исполнители ({len(unassigned_executors)}):</b>\n"
            for executor in unassigned_executors[:5]:  # Показываем первых 5
                text += f"• {executor.first_name} {executor.last_name}\n"

            if len(unassigned_executors) > 5:
                text += f"... и ещё {len(unassigned_executors) - 5} исполнителей\n"

        # Рекомендации по балансировке
        if executor_stats:
            max_hours = max([stat.total_hours or 0 for stat in executor_stats])
            min_hours = min([stat.total_hours or 0 for stat in executor_stats])

            if max_hours - min_hours > 20:
                text += "\n⚠️ <b>Рекомендация:</b> Большой разброс в загруженности. Рекомендуется перераспределение смен."

        await callback.message.edit_text(
            text,
            reply_markup=get_executor_assignment_keyboard(lang),
            parse_mode="HTML"
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка анализа загруженности: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data == "redistribute_load")
@require_role(['admin', 'manager'])
async def handle_redistribute_load(callback: CallbackQuery, state: FSMContext, db: Session = None, user: User = None, roles: list = None):
    """Перераспределение нагрузки между исполнителями"""
    try:
        if not db:
            db = SessionLocal()
        lang = get_user_language(callback.from_user.id, db)

        from uk_management_bot.services.shift_assignment_service import ShiftAssignmentService
        assignment_service = ShiftAssignmentService(db)

        # Выполняем перераспределение нагрузки
        result = await assignment_service.redistribute_workload(
            start_date=date.today(),
            days_ahead=7,
            max_hours_per_executor=40
        )

        if result.get('error'):
            await callback.message.edit_text(
                f"❌ <b>Ошибка перераспределения</b>\n\n"
                f"{result['error']}",
                reply_markup=get_executor_assignment_keyboard(lang),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        # Формируем отчет о перераспределении
        redistributed = result.get('redistributed_shifts', [])
        summary = result.get('summary', {})

        text = "🔄 <b>Результат перераспределения нагрузки</b>\n\n"
        text += f"✅ <b>Перераспределено смен:</b> {len(redistributed)}\n"
        text += f"📈 <b>Улучшение баланса:</b> {summary.get('balance_improvement', 0):.1f}%\n"
        text += f"⚖️ <b>Новый разброс нагрузки:</b> {summary.get('load_variance', 0):.1f}ч\n\n"

        if redistributed:
            text += "<b>📋 Изменения в назначениях:</b>\n"
            for change in redistributed[:5]:  # Показываем первые 5
                shift = change.get('shift')
                old_executor = change.get('old_executor')
                new_executor = change.get('new_executor')

                if shift and new_executor:
                    text += (f"• {shift.date.strftime('%d.%m')} {shift.start_time.strftime('%H:%M')}\n"
                            f"  {old_executor.first_name if old_executor else 'Не назначен'} "
                            f"→ {new_executor.first_name} {new_executor.last_name}\n")

            if len(redistributed) > 5:
                text += f"... и ещё {len(redistributed) - 5} изменений\n"

        await callback.message.edit_text(
            text,
            reply_markup=get_executor_assignment_keyboard(lang),
            parse_mode="HTML"
        )

        await callback.answer("✅ Перераспределение завершено")

    except Exception as e:
        logger.error(f"Ошибка перераспределения нагрузки: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data == "schedule_conflicts")
@require_role(['admin', 'manager'])
async def handle_schedule_conflicts(callback: CallbackQuery, state: FSMContext, db: Session = None, user: User = None, roles: list = None):
    """Анализ конфликтов расписания"""
    try:
        if not db:
            db = SessionLocal()
        lang = get_user_language(callback.from_user.id, db)

        # Ищем конфликты в расписании на ближайшие 7 дней
        end_date = date.today() + timedelta(days=7)

        # Находим пересекающиеся смены у одного исполнителя
        from sqlalchemy import and_
        conflicts = []

        shifts = db.query(Shift).filter(
            Shift.user_id.is_not(None),
            Shift.start_time.between(datetime.now(), end_date)
        ).order_by(Shift.user_id, Shift.start_time).all()

        # Группируем по исполнителям и ищем пересечения
        from itertools import groupby
        for executor_id, executor_shifts in groupby(shifts, key=lambda s: s.user_id):
            executor_shifts = list(executor_shifts)
            for i in range(len(executor_shifts) - 1):
                shift1 = executor_shifts[i]
                shift2 = executor_shifts[i + 1]

                # Проверяем пересечение по времени в тот же день
                if (shift1.date == shift2.date and
                    shift1.end_time > shift2.start_time):
                    conflicts.append({
                        'executor': shift1.executor,
                        'shift1': shift1,
                        'shift2': shift2,
                        'type': 'time_overlap'
                    })

        # Находим смены без достаточного перерыва (менее 1 часа)
        for executor_id, executor_shifts in groupby(shifts, key=lambda s: s.executor_id):
            executor_shifts = list(executor_shifts)
            for i in range(len(executor_shifts) - 1):
                shift1 = executor_shifts[i]
                shift2 = executor_shifts[i + 1]

                if shift1.date == shift2.date:
                    break_time = (datetime.combine(shift2.date, shift2.start_time) -
                                 datetime.combine(shift1.date, shift1.end_time)).total_seconds() / 3600

                    if 0 < break_time < 1:  # Менее часа перерыва
                        conflicts.append({
                            'executor': shift1.executor,
                            'shift1': shift1,
                            'shift2': shift2,
                            'type': 'short_break',
                            'break_hours': break_time
                        })

        text = "⚠️ <b>Анализ конфликтов расписания</b>\n\n"
        text += f"<b>Период:</b> {date.today().strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}\n"
        text += f"<b>Найдено конфликтов:</b> {len(conflicts)}\n\n"

        if not conflicts:
            text += "✅ <b>Конфликтов не найдено!</b>\n"
            text += "Все расписания исполнителей оптимальны."
        else:
            text += "<b>🚨 Обнаруженные конфликты:</b>\n\n"

            for i, conflict in enumerate(conflicts[:5], 1):  # Показываем первые 5
                executor = conflict['executor']
                shift1 = conflict['shift1']
                shift2 = conflict['shift2']
                conflict_type = conflict['type']

                text += f"<b>{i}. {executor.first_name} {executor.last_name}</b>\n"
                text += f"📅 {shift1.date.strftime('%d.%m.%Y')}\n"

                if conflict_type == 'time_overlap':
                    text += f"❌ Пересечение смен:\n"
                    text += f"   {shift1.start_time.strftime('%H:%M')}-{shift1.end_time.strftime('%H:%M')}\n"
                    text += f"   {shift2.start_time.strftime('%H:%M')}-{shift2.end_time.strftime('%H:%M')}\n"
                elif conflict_type == 'short_break':
                    break_hours = conflict['break_hours']
                    text += f"⚡ Короткий перерыв ({break_hours:.1f}ч):\n"
                    text += f"   {shift1.start_time.strftime('%H:%M')}-{shift1.end_time.strftime('%H:%M')}\n"
                    text += f"   {shift2.start_time.strftime('%H:%M')}-{shift2.end_time.strftime('%H:%M')}\n"

                text += "\n"

            if len(conflicts) > 5:
                text += f"... и ещё {len(conflicts) - 5} конфликтов\n\n"

            text += "💡 <b>Рекомендация:</b> Используйте функцию перераспределения нагрузки для устранения конфликтов."

        await callback.message.edit_text(
            text,
            reply_markup=get_executor_assignment_keyboard(lang),
            parse_mode="HTML"
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка анализа конфликтов: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


# Additional handlers for bulk assignment and shift selection

@router.callback_query(F.data == "bulk_auto_assign")
@require_role(['admin', 'manager'])
async def handle_bulk_auto_assign(callback: CallbackQuery, state: FSMContext, db: Session = None, user: User = None, roles: list = None):
    """Автоматическое назначение всех смен"""
    try:
        if not db:
            db = SessionLocal()
        lang = get_user_language(callback.from_user.id, db)

        from uk_management_bot.services.shift_assignment_service import ShiftAssignmentService
        assignment_service = ShiftAssignmentService(db)

        # Запускаем автоматическое назначение на все неназначенные смены
        result = await assignment_service.auto_assign_executors_to_shifts(
            target_date=date.today(),
            days_ahead=30  # Назначаем на месяц вперед
        )

        if result.get('error'):
            await callback.message.edit_text(
                f"❌ <b>Ошибка автоназначения</b>\n\n"
                f"{result['error']}",
                reply_markup=get_executor_assignment_keyboard(lang),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        assignments = result.get('assignments', [])
        unassigned = result.get('unassigned_shifts', [])

        text = "🚀 <b>Результат автоматического назначения</b>\n\n"
        text += f"✅ <b>Успешно назначено:</b> {len(assignments)} смен\n"
        text += f"❌ <b>Не удалось назначить:</b> {len(unassigned)} смен\n\n"

        if assignments:
            text += f"📊 <b>Эффективность:</b> {(len(assignments) / (len(assignments) + len(unassigned)) * 100):.1f}%\n\n"

        if unassigned:
            text += "<b>⚠️ Неназначенные смены требуют ручного назначения</b>"

        await callback.message.edit_text(
            text,
            reply_markup=get_executor_assignment_keyboard(lang),
            parse_mode="HTML"
        )

        await callback.answer("✅ Автоназначение завершено")

    except Exception as e:
        logger.error(f"Ошибка автоматического назначения: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data.startswith("select_shift_for_assignment:"))
@require_role(['admin', 'manager'])
async def handle_select_shift_for_assignment(callback: CallbackQuery, state: FSMContext, db: Session = None, user: User = None, roles: list = None):
    """Выбор конкретной смены для назначения исполнителя"""
    try:
        shift_id = int(callback.data.split(":")[1])
        if not db:
            db = SessionLocal()
        lang = get_user_language(callback.from_user.id, db)

        # Получаем смену
        shift = db.query(Shift).filter(Shift.id == shift_id).first()
        if not shift:
            await callback.answer("❌ Смена не найдена", show_alert=True)
            return

        # Получаем доступных исполнителей для этой смены
        # Ищем пользователей, у которых есть роль 'executor' в JSON-поле roles
        all_users = db.query(User).filter(User.status == 'approved').all()

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
            except:
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

        text = f"👤 <b>Назначение исполнителя на смену</b>\n\n"
        text += f"<b>📅 Смена:</b> {shift.start_time.strftime('%d.%m.%Y')} "

        end_time_str = shift.end_time.strftime('%H:%M') if shift.end_time else "—"
        text += f"{shift.start_time.strftime('%H:%M')}-{end_time_str}\n"

        # Переводим специализации
        spec_text = translate_specializations(shift.specialization_focus, lang)
        text += f"<b>🔧 Специализация:</b> {spec_text}\n"

        text += f"<b>📍 Зона:</b> {shift.geographic_zone or 'Не указано'}\n\n"

        if not available_executors:
            text += "❌ <b>Нет доступных исполнителей</b>\n"
            text += "Все исполнители заняты или не подходят по специализации."

            keyboard = [[InlineKeyboardButton(text="🔙 Назад", callback_data="assign_to_shift")]]
        else:
            text += f"<b>👥 Доступные исполнители ({len(available_executors)}):</b>\n\n"

            keyboard = []
            for executor in available_executors[:10]:  # Показываем первых 10
                # Проверяем загруженность исполнителя в этот день
                from datetime import datetime, timedelta
                shift_date = shift.start_time.date()
                day_start = datetime.combine(shift_date, datetime.min.time())
                day_end = day_start + timedelta(days=1)

                day_shifts = db.query(Shift).filter(
                    Shift.user_id == executor.id,
                    Shift.start_time >= day_start,
                    Shift.start_time < day_end
                ).count()

                load_indicator = "🔴" if day_shifts >= 3 else "🟡" if day_shifts >= 1 else "🟢"

                keyboard.append([InlineKeyboardButton(
                    text=f"{load_indicator} {executor.first_name} {executor.last_name} ({day_shifts} смен)",
                    callback_data=f"assign_executor_to_shift:{shift_id}:{executor.id}"
                )])

            keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="assign_to_shift")])

        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="HTML"
        )

        await state.set_state(ExecutorAssignmentStates.viewing_available_executors)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка выбора смены для назначения: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data.startswith("assign_executor_to_shift:"))
@require_role(['admin', 'manager'])
async def handle_assign_executor_to_shift(callback: CallbackQuery, state: FSMContext, db: Session = None, user: User = None, roles: list = None):
    """Назначение исполнителя на смену"""
    try:
        parts = callback.data.split(":")
        shift_id = int(parts[1])
        executor_id = int(parts[2])

        if not db:
            db = SessionLocal()
        lang = get_user_language(callback.from_user.id, db)

        # Получаем смену и исполнителя
        shift = db.query(Shift).filter(Shift.id == shift_id).first()
        executor = db.query(User).filter(User.id == executor_id).first()

        if not shift or not executor:
            await callback.answer("❌ Смена или исполнитель не найдены", show_alert=True)
            return

        # Проверяем конфликты расписания (проверяем пересечение времени смен у этого исполнителя)
        from datetime import datetime, timedelta

        # Определяем конец смены (если не указан, считаем 8 часов)
        shift_end = shift.end_time if shift.end_time else shift.start_time + timedelta(hours=8)

        conflicts = db.query(Shift).filter(
            Shift.user_id == executor_id,
            Shift.start_time < shift_end,
            Shift.end_time > shift.start_time
        ).count()

        if conflicts > 0:
            shift_date_str = shift.start_time.strftime('%d.%m.%Y')
            await callback.message.edit_text(
                f"⚠️ <b>Конфликт расписания!</b>\n\n"
                f"У исполнителя <b>{executor.first_name} {executor.last_name}</b> "
                f"уже есть пересекающиеся смены на {shift_date_str}.\n\n"
                f"Всё равно назначить?",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Да, назначить", callback_data=f"force_assign:{shift_id}:{executor_id}")],
                    [InlineKeyboardButton(text="❌ Отменить", callback_data=f"select_shift_for_assignment:{shift_id}")]
                ]),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        # Назначаем исполнителя
        shift.user_id = executor_id
        shift.status = 'active'  # Меняем статус на активную
        db.commit()

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
            f"✅ <b>Исполнитель назначен!</b>\n\n"
            f"<b>📅 Смена:</b> {shift_date_str} "
            f"{start_time_str}-{end_time_str}\n"
            f"<b>👤 Исполнитель:</b> {executor.first_name} {executor.last_name}\n"
            f"<b>🔧 Специализация:</b> {spec_text}\n\n"
            f"Уведомление отправлено исполнителю.",
            reply_markup=get_executor_assignment_keyboard(lang),
            parse_mode="HTML"
        )

        await callback.answer("✅ Назначение выполнено")

    except Exception as e:
        logger.error(f"Ошибка назначения исполнителя: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
        if db:
            db.rollback()
    finally:
        if db:
            db.close()


@router.callback_query(F.data.startswith("force_assign:"))
@require_role(['admin', 'manager'])
async def handle_force_assign(callback: CallbackQuery, state: FSMContext, db: Session = None, user: User = None, roles: list = None):
    """Принудительное назначение с конфликтом расписания"""
    try:
        parts = callback.data.split(":")
        shift_id = int(parts[1])
        executor_id = int(parts[2])

        if not db:
            db = SessionLocal()
        lang = get_user_language(callback.from_user.id, db)

        # Получаем смену и исполнителя
        shift = db.query(Shift).filter(Shift.id == shift_id).first()
        executor = db.query(User).filter(User.id == executor_id).first()

        if not shift or not executor:
            await callback.answer("❌ Смена или исполнитель не найдены", show_alert=True)
            return

        # Назначаем исполнителя принудительно
        shift.user_id = executor_id
        shift.notes = (shift.notes or "") + f"\n[КОНФЛИКТ РАСПИСАНИЯ] Назначено принудительно {date.today().strftime('%d.%m.%Y')}"
        db.commit()

        await callback.message.edit_text(
            f"⚠️ <b>Исполнитель назначен принудительно</b>\n\n"
            f"<b>📅 Смена:</b> {shift.start_time.date().strftime('%d.%m.%Y')} "
            f"{shift.start_time.strftime('%H:%M')}-{shift.end_time.strftime('%H:%M')}\n"
            f"<b>👤 Исполнитель:</b> {executor.first_name} {executor.last_name}\n\n"
            f"❗ <b>Внимание:</b> Есть конфликт с другими сменами!\n"
            f"Рекомендуется проверить расписание исполнителя.",
            reply_markup=get_executor_assignment_keyboard(lang),
            parse_mode="HTML"
        )

        await callback.answer("⚠️ Назначено с конфликтом")

    except Exception as e:
        logger.error(f"Ошибка принудительного назначения: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
        if db:
            db.rollback()
    finally:
        if db:
            db.close()


@router.callback_query(F.data == "executor_assignment")
@require_role(['admin', 'manager'])
async def handle_executor_assignment_back(callback: CallbackQuery, state: FSMContext, db: Session = None, user: User = None, roles: list = None):
    """Возврат к меню назначения исполнителей"""
    try:
        if not db:
            db = SessionLocal()
        lang = get_user_language(callback.from_user.id, db)

        await callback.message.edit_text(
            "👥 <b>Назначение исполнителей на смены</b>\n\n"
            "Выберите действие:",
            reply_markup=get_executor_assignment_keyboard(lang),
            parse_mode="HTML"
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка возврата к назначению исполнителей: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()