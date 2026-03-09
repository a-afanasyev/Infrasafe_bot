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
from uk_management_bot.utils.helpers import get_user_language, get_text
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
async def cmd_quarterly_planning(message: Message, state: FSMContext, db=None, language: str = "ru"):
    """Главное меню квартального планирования"""
    lang = language
    try:
        if not db:
            db = next(get_db())

        lang = get_user_language(message.from_user.id, db)
        
        await message.answer(
            get_text("quarterly.handlers.menu_title", language=lang),
            reply_markup=get_quarterly_planning_menu(lang)
        )

        logger.info(f"Пользователь {message.from_user.id} открыл меню квартального планирования")

    except Exception as e:
        logger.error(f"Ошибка отображения меню квартального планирования: {e}")
        await message.answer(get_text("quarterly.handlers.error_loading_menu", language=lang))


@router.callback_query(F.data == "quarterly_plan_create")
async def start_quarterly_planning(callback: CallbackQuery, state: FSMContext, db=None, language: str = "ru"):
    """Начало создания квартального плана"""
    lang = language
    try:
        if not db:
            db = next(get_db())

        lang = get_user_language(callback.from_user.id, db)

        # Переходим к выбору квартала
        await state.set_state(QuarterlyPlanningStates.selecting_quarter)

        await callback.message.edit_text(
            get_text("quarterly.handlers.select_quarter_title", language=lang),
            reply_markup=get_quarter_selection_keyboard(lang)
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка начала квартального планирования: {e}")
        await callback.answer(get_text("quarterly.handlers.error_init_planning", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("quarter_"), StateFilter(QuarterlyPlanningStates.selecting_quarter))
async def select_quarter(callback: CallbackQuery, state: FSMContext, db=None, language: str = "ru"):
    """Выбор квартала для планирования"""
    lang = language
    try:
        if not db:
            db = next(get_db())

        lang = get_user_language(callback.from_user.id, db)
        quarter_data = callback.data.replace("quarter_", "")

        # Парсим данные квартала
        if quarter_data == "current":
            start_date = _get_current_quarter_start()
            quarter_name = get_text("quarterly.handlers.current_quarter", language=lang)
        elif quarter_data == "next":
            start_date = _get_next_quarter_start()
            quarter_name = get_text("quarterly.handlers.next_quarter", language=lang)
        elif quarter_data.startswith("custom_"):
            # Для кастомного выбора даты
            start_date = _parse_custom_date(quarter_data)
            quarter_name = get_text("quarterly.handlers.custom_quarter", language=lang).format(date=start_date.strftime('%d.%m.%Y'))
        else:
            await callback.answer(get_text("quarterly.handlers.error_invalid_quarter", language=lang), show_alert=True)
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
            get_text("quarterly.handlers.select_specializations", language=lang).format(
                quarter_name=quarter_name,
                start_date=start_date.strftime('%d.%m.%Y'),
                count=len(configs)
            ),
            reply_markup=get_specialization_selection_keyboard(list(configs.keys()))
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка выбора квартала: {e}")
        await callback.answer(get_text("quarterly.handlers.error_select_quarter", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("spec_"), StateFilter(QuarterlyPlanningStates.selecting_specializations))
async def toggle_specialization(callback: CallbackQuery, state: FSMContext, db=None, language: str = "ru"):
    """Переключение выбора специализации"""
    lang = language
    try:
        if not db:
            db = next(get_db())

        lang = get_user_language(callback.from_user.id, db)
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

        status = get_text("quarterly.handlers.spec_selected", language=lang) if specialization in selected_specs else get_text("quarterly.handlers.spec_deselected", language=lang)
        await callback.answer(f"{specialization}: {status}")

    except Exception as e:
        logger.error(f"Ошибка переключения специализации: {e}")
        await callback.answer(get_text("quarterly.handlers.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data == "spec_confirm", StateFilter(QuarterlyPlanningStates.selecting_specializations))
async def confirm_specializations(callback: CallbackQuery, state: FSMContext, db=None, language: str = "ru"):
    """Подтверждение выбора специализаций"""
    lang = language
    try:
        if not db:
            db = next(get_db())

        lang = get_user_language(callback.from_user.id, db)
        data = await state.get_data()
        selected_specs = data.get("selected_specializations", [])

        if not selected_specs:
            await callback.answer(get_text("quarterly.handlers.error_no_specs", language=lang), show_alert=True)
            return

        start_date = date.fromisoformat(data["start_date"])
        quarter_name = data["quarter_name"]

        # Валидация планирования
        planning_service = SpecializationPlanningService(db)
        validation = planning_service.validate_quarterly_plan(start_date, selected_specs)

        # Формируем сводку для подтверждения
        end_date_str = (start_date + timedelta(days=91)).strftime('%d.%m.%Y')
        summary = get_text("quarterly.handlers.summary_header", language=lang).format(
            quarter_name=quarter_name,
            start_date=start_date.strftime('%d.%m.%Y'),
            end_date=end_date_str,
            spec_count=len(selected_specs)
        )

        # Список специализаций
        for spec in selected_specs:
            summary += f"• {spec}\n"

        # Предупреждения валидации
        if validation.get("warnings"):
            summary += "\n" + get_text("quarterly.handlers.warnings_header", language=lang)
            for warning in validation["warnings"]:
                summary += f"• {warning}\n"

        # Ошибки валидации
        if validation.get("errors"):
            summary += "\n" + get_text("quarterly.handlers.errors_header", language=lang)
            for error in validation["errors"]:
                summary += f"• {error}\n"

            summary += "\n" + get_text("quarterly.handlers.planning_impossible", language=lang)

            await callback.message.edit_text(
                summary,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=get_text("quarterly.handlers.btn_back_to_selection", language=lang), callback_data="spec_back")],
                    [InlineKeyboardButton(text=get_text("quarterly.handlers.btn_cancel", language=lang), callback_data="quarterly_cancel")]
                ])
            )
            await callback.answer()
            return

        # Переходим к подтверждению
        await state.set_state(QuarterlyPlanningStates.confirming_plan)

        await callback.message.edit_text(
            summary + "\n" + get_text("quarterly.handlers.all_checks_passed", language=lang),
            reply_markup=get_planning_confirmation_keyboard()
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка подтверждения специализаций: {e}")
        await callback.answer(get_text("quarterly.handlers.error_confirmation", language=lang), show_alert=True)


@router.callback_query(F.data == "plan_execute", StateFilter(QuarterlyPlanningStates.confirming_plan))
async def execute_quarterly_plan(callback: CallbackQuery, state: FSMContext, db=None, language: str = "ru"):
    """Выполнение квартального планирования"""
    lang = language
    try:
        if not db:
            db = next(get_db())

        lang = get_user_language(callback.from_user.id, db)
        data = await state.get_data()
        start_date = date.fromisoformat(data["start_date"])
        selected_specs = data["selected_specializations"]
        quarter_name = data["quarter_name"]

        # Показываем прогресс
        await callback.message.edit_text(
            get_text("quarterly.handlers.creating_plan_progress", language=lang).format(
                quarter_name=quarter_name,
                spec_count=len(selected_specs)
            )
        )

        # Выполняем планирование
        planning_service = SpecializationPlanningService(db)
        results = planning_service.create_quarterly_plan(start_date, selected_specs)

        # Сохраняем результаты
        await state.update_data(planning_results=results)
        await state.set_state(QuarterlyPlanningStates.viewing_results)

        # Формируем отчет о результатах
        report = get_text("quarterly.handlers.plan_completed_header", language=lang).format(
            start_date=start_date.strftime('%d.%m.%Y'),
            end_date=results['end_date'].strftime('%d.%m.%Y'),
            total_shifts=results['total_shifts_created']
        )

        # Детали по специализациям
        report += get_text("quarterly.handlers.spec_details_header", language=lang)
        for spec, info in results["specializations"].items():
            report += get_text("quarterly.handlers.spec_detail_item", language=lang).format(
                spec=spec,
                shifts=info['shifts_created'],
                schedule=info['schedule_type'],
                duration=info['duration_hours']
            )
            if info["coverage_24_7"]:
                report += get_text("quarterly.handlers.coverage_247", language=lang)
            report += "\n"

        # Ошибки если есть
        if results.get("errors"):
            report += get_text("quarterly.handlers.warnings_header", language=lang)
            for error in results["errors"]:
                report += f"• {error}\n"

        await callback.message.edit_text(
            report,
            reply_markup=get_planning_results_keyboard()
        )

        await callback.answer(get_text("quarterly.handlers.planning_completed_toast", language=lang))

        logger.info(f"Квартальное планирование выполнено: {results['total_shifts_created']} смен")

    except Exception as e:
        logger.error(f"Ошибка выполнения квартального планирования: {e}")
        await callback.message.edit_text(
            get_text("quarterly.handlers.error_creating_plan", language=lang).format(error=str(e)),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=get_text("quarterly.handlers.btn_back_to_menu", language=lang), callback_data="quarterly_menu")]
            ])
        )
        await callback.answer()


@router.callback_query(F.data == "view_statistics")
async def view_planning_statistics(callback: CallbackQuery, state: FSMContext, db=None, language: str = "ru"):
    """Просмотр статистики планирования"""
    lang = language
    try:
        if not db:
            db = next(get_db())

        lang = get_user_language(callback.from_user.id, db)

        # Получаем статистику за следующие 3 месяца
        start_date = date.today()
        planning_service = SpecializationPlanningService(db)
        stats = planning_service.get_planning_statistics(start_date, days=91)

        # Формируем отчет
        end_date_str = (start_date + timedelta(days=91)).strftime('%d.%m.%Y')
        report = get_text("quarterly.handlers.stats_header", language=lang).format(
            start_date=start_date.strftime('%d.%m.%Y'),
            end_date=end_date_str,
            total_shifts=stats['total_shifts']
        )

        if stats.get("by_specialization"):
            report += get_text("quarterly.handlers.stats_by_spec_header", language=lang)
            for spec, count in sorted(stats["by_specialization"].items()):
                report += get_text("quarterly.handlers.stats_spec_item", language=lang).format(spec=spec, count=count)
            report += "\n"

        if stats.get("coverage_analysis"):
            report += get_text("quarterly.handlers.stats_coverage_header", language=lang)
            for spec, coverage in stats["coverage_analysis"].items():
                report += get_text("quarterly.handlers.stats_coverage_item", language=lang).format(
                    spec=spec, percentage=f"{coverage['coverage_percentage']:.1f}"
                )
                if coverage.get("gaps"):
                    report += get_text("quarterly.handlers.stats_gaps", language=lang).format(count=len(coverage['gaps']))
                report += "\n"

        if not stats["total_shifts"]:
            report += get_text("quarterly.handlers.stats_no_shifts", language=lang)

        await callback.message.edit_text(
            report,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=get_text("quarterly.handlers.btn_back_to_menu", language=lang), callback_data="quarterly_menu")],
                [InlineKeyboardButton(text=get_text("quarterly.handlers.btn_create_plan", language=lang), callback_data="quarterly_plan_create")]
            ])
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        await callback.answer(get_text("quarterly.handlers.error_stats", language=lang), show_alert=True)


@router.callback_query(F.data == "transfer_management")
async def transfer_management_menu(callback: CallbackQuery, state: FSMContext, db=None, language: str = "ru"):
    """Меню управления передачами смен"""
    lang = language
    try:
        if not db:
            db = next(get_db())

        lang = get_user_language(callback.from_user.id, db)
        transfer_service = ShiftTransferService(db)

        # Получаем статистику передач
        stats = transfer_service.get_transfer_statistics()
        active_transfers = transfer_service.get_active_transfers()

        report = get_text("quarterly.handlers.transfer_menu_header", language=lang).format(
            total=stats.get('total_transfers', 0),
            successful=stats.get('successful_transfers', 0),
            failed=stats.get('failed_transfers', 0),
            rate=f"{stats.get('transfer_success_rate', 0):.1f}"
        )

        if active_transfers:
            report += get_text("quarterly.handlers.active_transfers_count", language=lang).format(count=len(active_transfers))
        else:
            report += get_text("quarterly.handlers.no_active_transfers", language=lang)

        # Автообнаружение необходимых передач
        required_transfers = transfer_service.auto_detect_required_transfers()
        if required_transfers:
            report += get_text("quarterly.handlers.required_transfers", language=lang).format(count=len(required_transfers))

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_text("quarterly.handlers.btn_auto_initiate", language=lang), callback_data="auto_initiate_transfers")],
            [InlineKeyboardButton(text=get_text("quarterly.handlers.btn_active_transfers", language=lang), callback_data="view_active_transfers")],
            [InlineKeyboardButton(text=get_text("quarterly.handlers.btn_detailed_stats", language=lang), callback_data="transfer_detailed_stats")],
            [InlineKeyboardButton(text=get_text("quarterly.handlers.btn_back_to_menu", language=lang), callback_data="quarterly_menu")]
        ])

        await callback.message.edit_text(
            report,
            reply_markup=keyboard
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка меню управления передачами: {e}")
        await callback.answer(get_text("quarterly.handlers.error_loading_menu", language=lang), show_alert=True)


@router.callback_query(F.data == "auto_initiate_transfers")
async def auto_initiate_transfers(callback: CallbackQuery, state: FSMContext, db=None, language: str = "ru"):
    """Автоматическая инициация передач"""
    lang = language
    try:
        if not db:
            db = next(get_db())

        lang = get_user_language(callback.from_user.id, db)
        transfer_service = ShiftTransferService(db)

        await callback.message.edit_text(
            get_text("quarterly.handlers.auto_initiate_progress", language=lang)
        )

        # Выполняем автоинициацию
        initiated_transfers = transfer_service.auto_initiate_transfers()

        result = get_text("quarterly.handlers.auto_initiate_completed", language=lang).format(
            count=len(initiated_transfers)
        )

        if initiated_transfers:
            result += get_text("quarterly.handlers.auto_initiate_details_header", language=lang)
            for transfer in initiated_transfers:
                result += get_text("quarterly.handlers.auto_initiate_detail_item", language=lang).format(
                    outgoing=transfer.outgoing_shift_id,
                    incoming=transfer.incoming_shift_id,
                    requests=transfer.total_requests
                )
        else:
            result += get_text("quarterly.handlers.auto_initiate_no_transfers", language=lang)

        await callback.message.edit_text(
            result,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=get_text("quarterly.handlers.btn_back_to_transfers", language=lang), callback_data="transfer_management")]
            ])
        )

        await callback.answer(get_text("quarterly.handlers.auto_initiate_toast", language=lang).format(count=len(initiated_transfers)))

    except Exception as e:
        logger.error(f"Ошибка автоинициации передач: {e}")
        await callback.answer(get_text("quarterly.handlers.error_auto_initiate", language=lang), show_alert=True)


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
async def back_to_quarterly_menu(callback: CallbackQuery, state: FSMContext, db=None, language: str = "ru"):
    """Возврат в главное меню квартального планирования"""
    lang = language
    try:
        await state.clear()
        await cmd_quarterly_planning(callback.message, state, db)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка возврата в меню: {e}")
        await callback.answer(get_text("quarterly.handlers.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data == "quarterly_cancel")
async def cancel_quarterly_planning(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Отмена квартального планирования"""
    lang = language
    try:
        await state.clear()

        await callback.message.edit_text(
            get_text("quarterly.handlers.planning_cancelled", language=lang),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=get_text("quarterly.handlers.btn_start_over", language=lang), callback_data="quarterly_plan_create")],
                [InlineKeyboardButton(text=get_text("quarterly.handlers.btn_main_menu", language=lang), callback_data="quarterly_menu")]
            ])
        )

        await callback.answer(get_text("quarterly.handlers.cancelled_toast", language=lang))

    except Exception as e:
        logger.error(f"Ошибка отмены планирования: {e}")
        await callback.answer(get_text("quarterly.handlers.error_generic", language=lang), show_alert=True)