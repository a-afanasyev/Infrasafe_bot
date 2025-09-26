"""
Обработчики для квартального планирования смен
Интерфейсы для менеджеров и администраторов
"""

from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from uk_management_bot.database.session import get_db
from uk_management_bot.database.models.user import User
from uk_management_bot.services.specialization_planning_service import SpecializationPlanningService
from uk_management_bot.services.shift_transfer_service import ShiftTransferService
from uk_management_bot.keyboards.quarterly_planning import (
    get_quarterly_planning_menu,
    get_specialization_selection_keyboard,
    get_quarter_selection_keyboard,
    get_planning_confirmation_keyboard,
    get_planning_results_keyboard
)
from uk_management_bot.middlewares.auth import require_role
from uk_management_bot.utils.helpers import get_user_language
import logging

logger = logging.getLogger(__name__)
router = Router()


class QuarterlyPlanningStates(StatesGroup):
    """Состояния FSM для квартального планирования"""
    selecting_quarter = State()
    selecting_specializations = State()
    confirming_plan = State()
    viewing_results = State()


@router.message(Command("quarterly_planning"))
@require_role(['admin', 'manager'])
async def cmd_quarterly_planning(message: Message, state: FSMContext, db=None):
    """Главное меню квартального планирования"""
    try:
        if not db:
            db = next(get_db())
        
        lang = get_user_language(message.from_user.id, db)
        
        await message.answer(
            "🗓️ **Квартальное планирование смен**\n\n"
            "Выберите действие:",
            reply_markup=get_quarterly_planning_menu(lang),
            parse_mode="Markdown"
        )
        
        logger.info(f"Пользователь {message.from_user.id} открыл меню квартального планирования")
        
    except Exception as e:
        logger.error(f"Ошибка отображения меню квартального планирования: {e}")
        await message.answer("❌ Ошибка при загрузке меню планирования")


@router.callback_query(F.data == "quarterly_plan_create")
async def start_quarterly_planning(callback: CallbackQuery, state: FSMContext, db=None):
    """Начало создания квартального плана"""
    try:
        if not db:
            db = next(get_db())
        
        lang = get_user_language(callback.from_user.id, db)
        
        # Переходим к выбору квартала
        await state.set_state(QuarterlyPlanningStates.selecting_quarter)
        
        await callback.message.edit_text(
            "📅 **Выбор квартала для планирования**\n\n"
            "Выберите период планирования:",
            reply_markup=get_quarter_selection_keyboard(lang),
            parse_mode="Markdown"
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка начала квартального планирования: {e}")
        await callback.answer("❌ Ошибка при инициации планирования", show_alert=True)


@router.callback_query(F.data.startswith("quarter_"), StateFilter(QuarterlyPlanningStates.selecting_quarter))
async def select_quarter(callback: CallbackQuery, state: FSMContext, db=None):
    """Выбор квартала для планирования"""
    try:
        if not db:
            db = next(get_db())
        
        quarter_data = callback.data.replace("quarter_", "")
        
        # Парсим данные квартала
        if quarter_data == "current":
            start_date = self._get_current_quarter_start()
            quarter_name = "Текущий квартал"
        elif quarter_data == "next":
            start_date = self._get_next_quarter_start()
            quarter_name = "Следующий квартал"
        elif quarter_data.startswith("custom_"):
            # Для кастомного выбора даты
            start_date = self._parse_custom_date(quarter_data)
            quarter_name = f"Квартал с {start_date.strftime('%d.%m.%Y')}"
        else:
            await callback.answer("❌ Неверный выбор квартала", show_alert=True)
            return
        
        # Сохраняем выбранный период
        await state.update_data(
            start_date=start_date.isoformat(),
            quarter_name=quarter_name
        )
        
        # Переходим к выбору специализаций
        await state.set_state(QuarterlyPlanningStates.selecting_specializations)
        
        # Получаем доступные специализации
        planning_service = SpecializationPlanningService(db)
        configs = planning_service.get_specialization_configs()
        
        await callback.message.edit_text(
            f"👥 **Выбор специализаций**\n\n"
            f"Период: {quarter_name}\n"
            f"Дата начала: {start_date.strftime('%d.%m.%Y')}\n\n"
            f"Выберите специализации для планирования:\n"
            f"(Доступно {len(configs)} специализаций)",
            reply_markup=get_specialization_selection_keyboard(list(configs.keys())),
            parse_mode="Markdown"
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка выбора квартала: {e}")
        await callback.answer("❌ Ошибка при выборе квартала", show_alert=True)


@router.callback_query(F.data.startswith("spec_"), StateFilter(QuarterlyPlanningStates.selecting_specializations))
async def toggle_specialization(callback: CallbackQuery, state: FSMContext, db=None):
    """Переключение выбора специализации"""
    try:
        if not db:
            db = next(get_db())
        
        specialization = callback.data.replace("spec_", "")
        
        # Получаем текущий выбор
        data = await state.get_data()
        selected_specs = data.get("selected_specializations", [])
        
        # Переключаем выбор
        if specialization in selected_specs:
            selected_specs.remove(specialization)
        else:
            selected_specs.append(specialization)
        
        await state.update_data(selected_specializations=selected_specs)
        
        # Обновляем клавиатуру
        planning_service = SpecializationPlanningService(db)
        configs = planning_service.get_specialization_configs()
        
        await callback.message.edit_reply_markup(
            reply_markup=get_specialization_selection_keyboard(
                list(configs.keys()), 
                selected=selected_specs
            )
        )
        
        await callback.answer(f"✅ {specialization}: {'выбрано' if specialization in selected_specs else 'отменено'}")
        
    except Exception as e:
        logger.error(f"Ошибка переключения специализации: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "spec_confirm", StateFilter(QuarterlyPlanningStates.selecting_specializations))
async def confirm_specializations(callback: CallbackQuery, state: FSMContext, db=None):
    """Подтверждение выбора специализаций"""
    try:
        if not db:
            db = next(get_db())
        
        data = await state.get_data()
        selected_specs = data.get("selected_specializations", [])
        
        if not selected_specs:
            await callback.answer("❌ Выберите хотя бы одну специализацию", show_alert=True)
            return
        
        start_date = date.fromisoformat(data["start_date"])
        quarter_name = data["quarter_name"]
        
        # Валидация планирования
        planning_service = SpecializationPlanningService(db)
        validation = planning_service.validate_quarterly_plan(start_date, selected_specs)
        
        # Формируем сводку для подтверждения
        summary = f"📋 **Сводка квартального планирования**\n\n"
        summary += f"**Период:** {quarter_name}\n"
        summary += f"**Дата начала:** {start_date.strftime('%d.%m.%Y')}\n"
        summary += f"**Дата окончания:** {(start_date + timedelta(days=91)).strftime('%d.%m.%Y')}\n"
        summary += f"**Специализации:** {len(selected_specs)}\n\n"
        
        # Список специализаций
        for spec in selected_specs:
            summary += f"• {spec}\n"
        
        # Предупреждения валидации
        if validation.get("warnings"):
            summary += f"\n⚠️ **Предупреждения:**\n"
            for warning in validation["warnings"]:
                summary += f"• {warning}\n"
        
        # Ошибки валидации
        if validation.get("errors"):
            summary += f"\n❌ **Ошибки:**\n"
            for error in validation["errors"]:
                summary += f"• {error}\n"
            
            summary += f"\n❌ Планирование невозможно из-за ошибок"
            
            await callback.message.edit_text(
                summary,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Назад к выбору", callback_data="spec_back")],
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="quarterly_cancel")]
                ]),
                parse_mode="Markdown"
            )
            await callback.answer()
            return
        
        # Переходим к подтверждению
        await state.set_state(QuarterlyPlanningStates.confirming_plan)
        
        await callback.message.edit_text(
            summary + "\n✅ Все проверки пройдены. Продолжить создание плана?",
            reply_markup=get_planning_confirmation_keyboard(),
            parse_mode="Markdown"
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка подтверждения специализаций: {e}")
        await callback.answer("❌ Ошибка при подтверждении", show_alert=True)


@router.callback_query(F.data == "plan_execute", StateFilter(QuarterlyPlanningStates.confirming_plan))
async def execute_quarterly_plan(callback: CallbackQuery, state: FSMContext, db=None):
    """Выполнение квартального планирования"""
    try:
        if not db:
            db = next(get_db())
        
        data = await state.get_data()
        start_date = date.fromisoformat(data["start_date"])
        selected_specs = data["selected_specializations"]
        quarter_name = data["quarter_name"]
        
        # Показываем прогресс
        await callback.message.edit_text(
            f"⏳ **Создание квартального плана...**\n\n"
            f"Период: {quarter_name}\n"
            f"Специализации: {len(selected_specs)}\n\n"
            f"⚡ Процесс может занять несколько минут...",
            parse_mode="Markdown"
        )
        
        # Выполняем планирование
        planning_service = SpecializationPlanningService(db)
        results = planning_service.create_quarterly_plan(start_date, selected_specs)
        
        # Сохраняем результаты
        await state.update_data(planning_results=results)
        await state.set_state(QuarterlyPlanningStates.viewing_results)
        
        # Формируем отчет о результатах
        report = f"✅ **Квартальное планирование завершено**\n\n"
        report += f"**Период:** {start_date.strftime('%d.%m.%Y')} - {results['end_date'].strftime('%d.%m.%Y')}\n"
        report += f"**Всего создано смен:** {results['total_shifts_created']}\n\n"
        
        # Детали по специализациям
        report += f"**Детали по специализациям:**\n"
        for spec, info in results["specializations"].items():
            report += f"• **{spec}**: {info['shifts_created']} смен\n"
            report += f"  График: {info['schedule_type']}\n"
            report += f"  Длительность: {info['duration_hours']}ч\n"
            if info["coverage_24_7"]:
                report += f"  🔄 24/7 покрытие\n"
            report += f"\n"
        
        # Ошибки если есть
        if results.get("errors"):
            report += f"⚠️ **Предупреждения:**\n"
            for error in results["errors"]:
                report += f"• {error}\n"
        
        await callback.message.edit_text(
            report,
            reply_markup=get_planning_results_keyboard(),
            parse_mode="Markdown"
        )
        
        await callback.answer("✅ Планирование завершено!")
        
        logger.info(f"Квартальное планирование выполнено: {results['total_shifts_created']} смен")
        
    except Exception as e:
        logger.error(f"Ошибка выполнения квартального планирования: {e}")
        await callback.message.edit_text(
            f"❌ **Ошибка при создании плана**\n\n"
            f"Произошла ошибка: {str(e)}\n\n"
            f"Обратитесь к администратору или попробуйте позже.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Вернуться в меню", callback_data="quarterly_menu")]
            ]),
            parse_mode="Markdown"
        )
        await callback.answer()


@router.callback_query(F.data == "view_statistics")
async def view_planning_statistics(callback: CallbackQuery, state: FSMContext, db=None):
    """Просмотр статистики планирования"""
    try:
        if not db:
            db = next(get_db())
        
        # Получаем статистику за следующие 3 месяца
        start_date = date.today()
        planning_service = SpecializationPlanningService(db)
        stats = planning_service.get_planning_statistics(start_date, days=91)
        
        # Формируем отчет
        report = f"📊 **Статистика планирования смен**\n\n"
        report += f"**Период:** {start_date.strftime('%d.%m.%Y')} - {(start_date + timedelta(days=91)).strftime('%d.%m.%Y')}\n"
        report += f"**Всего смен:** {stats['total_shifts']}\n\n"
        
        if stats.get("by_specialization"):
            report += f"**По специализациям:**\n"
            for spec, count in sorted(stats["by_specialization"].items()):
                report += f"• {spec}: {count} смен\n"
            report += f"\n"
        
        if stats.get("coverage_analysis"):
            report += f"**Анализ покрытия 24/7:**\n"
            for spec, coverage in stats["coverage_analysis"].items():
                report += f"• **{spec}**: {coverage['coverage_percentage']:.1f}%\n"
                if coverage.get("gaps"):
                    report += f"  Пробелов: {len(coverage['gaps'])}\n"
                report += f"\n"
        
        if not stats["total_shifts"]:
            report += f"⚠️ Нет запланированных смен на выбранный период.\n"
            report += f"Создайте квартальный план для начала работы."
        
        await callback.message.edit_text(
            report,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="quarterly_menu")],
                [InlineKeyboardButton(text="📋 Создать план", callback_data="quarterly_plan_create")]
            ]),
            parse_mode="Markdown"
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        await callback.answer("❌ Ошибка получения статистики", show_alert=True)


@router.callback_query(F.data == "transfer_management")
async def transfer_management_menu(callback: CallbackQuery, state: FSMContext, db=None):
    """Меню управления передачами смен"""
    try:
        if not db:
            db = next(get_db())
        
        transfer_service = ShiftTransferService(db)
        
        # Получаем статистику передач
        stats = transfer_service.get_transfer_statistics()
        active_transfers = transfer_service.get_active_transfers()
        
        report = f"🔄 **Управление передачами смен**\n\n"
        report += f"**Статистика за месяц:**\n"
        report += f"• Всего передач: {stats.get('total_transfers', 0)}\n"
        report += f"• Успешных: {stats.get('successful_transfers', 0)}\n"
        report += f"• С ошибками: {stats.get('failed_transfers', 0)}\n"
        report += f"• Успешность: {stats.get('transfer_success_rate', 0):.1f}%\n\n"
        
        if active_transfers:
            report += f"**Активные передачи:** {len(active_transfers)}\n"
        else:
            report += f"**Активных передач:** нет\n"
        
        # Автообнаружение необходимых передач
        required_transfers = transfer_service.auto_detect_required_transfers()
        if required_transfers:
            report += f"\n⚠️ **Требуется передача:** {len(required_transfers)} смен\n"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🤖 Автоинициация передач", callback_data="auto_initiate_transfers")],
            [InlineKeyboardButton(text="📋 Активные передачи", callback_data="view_active_transfers")],
            [InlineKeyboardButton(text="📊 Подробная статистика", callback_data="transfer_detailed_stats")],
            [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="quarterly_menu")]
        ])
        
        await callback.message.edit_text(
            report,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка меню управления передачами: {e}")
        await callback.answer("❌ Ошибка загрузки меню", show_alert=True)


@router.callback_query(F.data == "auto_initiate_transfers")
async def auto_initiate_transfers(callback: CallbackQuery, state: FSMContext, db=None):
    """Автоматическая инициация передач"""
    try:
        if not db:
            db = next(get_db())
        
        transfer_service = ShiftTransferService(db)
        
        await callback.message.edit_text(
            "⏳ Автоматическая инициация передач...\n\n"
            "🔍 Поиск смен, требующих передачи...",
            parse_mode="Markdown"
        )
        
        # Выполняем автоинициацию
        initiated_transfers = transfer_service.auto_initiate_transfers()
        
        result = f"✅ **Автоинициация завершена**\n\n"
        result += f"**Инициировано передач:** {len(initiated_transfers)}\n\n"
        
        if initiated_transfers:
            result += f"**Детали:**\n"
            for transfer in initiated_transfers:
                result += f"• Смена {transfer.outgoing_shift_id} → {transfer.incoming_shift_id}\n"
                result += f"  Заявок к передаче: {transfer.total_requests}\n"
        else:
            result += f"ℹ️ Смен, требующих передачи, не обнаружено.\n"
            result += f"Все активные смены работают в штатном режиме."
        
        await callback.message.edit_text(
            result,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад к передачам", callback_data="transfer_management")]
            ]),
            parse_mode="Markdown"
        )
        
        await callback.answer(f"✅ Инициировано {len(initiated_transfers)} передач")
        
    except Exception as e:
        logger.error(f"Ошибка автоинициации передач: {e}")
        await callback.answer("❌ Ошибка автоинициации", show_alert=True)


# ========== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ==========

def _get_current_quarter_start() -> date:
    """Получает дату начала текущего квартала"""
    today = date.today()
    month = today.month
    
    if month <= 3:
        return date(today.year, 1, 1)
    elif month <= 6:
        return date(today.year, 4, 1)
    elif month <= 9:
        return date(today.year, 7, 1)
    else:
        return date(today.year, 10, 1)


def _get_next_quarter_start() -> date:
    """Получает дату начала следующего квартала"""
    current_start = _get_current_quarter_start()
    
    # Добавляем 3 месяца
    if current_start.month == 1:
        return date(current_start.year, 4, 1)
    elif current_start.month == 4:
        return date(current_start.year, 7, 1)
    elif current_start.month == 7:
        return date(current_start.year, 10, 1)
    else:
        return date(current_start.year + 1, 1, 1)


def _parse_custom_date(quarter_data: str) -> date:
    """Парсит кастомную дату из callback данных"""
    # Здесь можно реализовать парсинг кастомных дат
    # Пока возвращаем начало следующего квартала
    return _get_next_quarter_start()


# ========== ОБРАБОТЧИКИ ОТМЕНЫ И ВОЗВРАТА ==========

@router.callback_query(F.data == "quarterly_menu")
async def back_to_quarterly_menu(callback: CallbackQuery, state: FSMContext, db=None):
    """Возврат в главное меню квартального планирования"""
    try:
        await state.clear()
        await cmd_quarterly_planning(callback.message, state, db)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка возврата в меню: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "quarterly_cancel")
async def cancel_quarterly_planning(callback: CallbackQuery, state: FSMContext):
    """Отмена квартального планирования"""
    try:
        await state.clear()
        
        await callback.message.edit_text(
            "❌ **Квартальное планирование отменено**\n\n"
            "Вы можете начать заново в любое время.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Начать заново", callback_data="quarterly_plan_create")],
                [InlineKeyboardButton(text="🔙 Главное меню", callback_data="quarterly_menu")]
            ]),
            parse_mode="Markdown"
        )
        
        await callback.answer("Планирование отменено")
        
    except Exception as e:
        logger.error(f"Ошибка отмены планирования: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)