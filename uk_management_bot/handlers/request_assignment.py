"""
Обработчики для назначения заявок на исполнение
Обеспечивает функциональность назначения заявок группам и конкретным исполнителям
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session

from uk_management_bot.database.session import get_db
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.states.request_assignment import RequestAssignmentStates
from uk_management_bot.services.assignment_service import AssignmentService
from uk_management_bot.services.comment_service import CommentService
from uk_management_bot.keyboards.request_assignment import (
    get_request_assignment_keyboard,
    get_executor_selection_keyboard,
    get_specialization_selection_keyboard,
    get_assignment_confirmation_keyboard
)
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.auth_helpers import check_user_role
from uk_management_bot.utils.constants import ROLE_MANAGER, REQUEST_STATUS_IN_PROGRESS

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data.startswith("assign_request_"))
async def handle_request_assignment_start(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru"):
    """Начало процесса назначения заявки"""
    lang = language

    try:
        # Проверяем права доступа (только менеджеры)
        if not await check_user_role(callback.from_user.id, ROLE_MANAGER, db):
            await callback.answer(get_text("request_assignment.no_permission", language=lang), show_alert=True)
            return

        # Извлекаем номер заявки из callback data
        request_number = callback.data.split("_")[-1]

        # Проверяем существование заявки
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer(get_text("requests.request_not_found", language=lang), show_alert=True)
            return

        # Сохраняем номер заявки в состоянии
        await state.update_data(request_number=request_number)

        # Показываем меню выбора типа назначения
        keyboard = get_request_assignment_keyboard(request_number, lang)

        await callback.message.edit_text(
            get_text("request_assignment.select_type", language=lang),
            reply_markup=keyboard
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка начала назначения заявки: {e}")
        await callback.answer(get_text("common.error_occurred", language=lang).format(error=str(e)), show_alert=True)

@router.callback_query(F.data.startswith("assign_group_"))
async def handle_group_assignment(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru"):
    """Назначение заявки группе исполнителей"""
    lang = language

    try:
        # Проверяем права доступа
        if not await check_user_role(callback.from_user.id, ROLE_MANAGER, db):
            await callback.answer(get_text("request_assignment.no_permission", language=lang), show_alert=True)
            return

        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")

        if not request_number:
            await callback.answer(get_text("request_assignment.request_not_in_state", language=lang), show_alert=True)
            return

        # Показываем выбор специализации
        keyboard = get_specialization_selection_keyboard(lang)

        await callback.message.edit_text(
            get_text("request_assignment.select_specialization", language=lang),
            reply_markup=keyboard
        )

        # Переходим в состояние выбора специализации
        await state.set_state(RequestAssignmentStates.waiting_for_specialization)

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка назначения группе: {e}")
        await callback.answer(get_text("common.error_occurred", language=lang).format(error=str(e)), show_alert=True)

@router.callback_query(F.data.startswith("assign_individual_"))
async def handle_individual_assignment(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru"):
    """Назначение заявки конкретному исполнителю"""
    lang = language

    try:
        # Проверяем права доступа
        if not await check_user_role(callback.from_user.id, ROLE_MANAGER, db):
            await callback.answer(get_text("request_assignment.no_permission", language=lang), show_alert=True)
            return

        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")

        if not request_number:
            await callback.answer(get_text("request_assignment.request_not_in_state", language=lang), show_alert=True)
            return

        # Получаем заявку для определения категории
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer(get_text("requests.request_not_found", language=lang), show_alert=True)
            return
        
        # Определяем специализацию на основе категории заявки
        specialization_map = {
            "Сантехника": "сантехник",
            "Электрика": "электрик",
            "Отопление": "сантехник",
            "Вентиляция": "сантехник",
            "Лифт": "электрик",
            "Уборка": "уборщик",
            "Благоустройство": "дворник",
            "Безопасность": "охранник",
            "Интернет/ТВ": "электрик",
            "Другое": "специалист"
        }
        
        specialization = specialization_map.get(request.category, "специалист")
        
        # Получаем доступных исполнителей
        assignment_service = AssignmentService(db)
        available_executors = assignment_service.get_available_executors(specialization)

        if not available_executors:
            await callback.answer(get_text("request_assignment.no_executors_available", language=lang), show_alert=True)
            return

        # Показываем выбор исполнителя
        keyboard = get_executor_selection_keyboard(available_executors, lang)

        await callback.message.edit_text(
            get_text("request_assignment.select_executor", language=lang),
            reply_markup=keyboard
        )

        # Переходим в состояние выбора исполнителя
        await state.set_state(RequestAssignmentStates.waiting_for_executor)

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка назначения исполнителю: {e}")
        await callback.answer(get_text("common.error_occurred", language=lang).format(error=str(e)), show_alert=True)

@router.callback_query(F.data.startswith("specialization_"))
async def handle_specialization_selection(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru"):
    """Обработка выбора специализации для группового назначения"""
    lang = language

    try:
        # Получаем специализацию из callback data
        specialization = callback.data.split("_", 1)[1]

        # Сохраняем специализацию в состоянии
        await state.update_data(specialization=specialization)

        # Получаем данные заявки
        data = await state.get_data()
        request_number = data.get("request_number")

        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer(get_text("requests.request_not_found", language=lang), show_alert=True)
            return

        # Показываем подтверждение назначения
        keyboard = get_assignment_confirmation_keyboard("group", lang)

        confirmation_text = get_text("request_assignment.confirmation_group", language=lang).format(
            request_number=request_number,
            specialization=specialization,
            category=request.category,
            address=request.address
        )

        await callback.message.edit_text(confirmation_text, reply_markup=keyboard)

        # Переходим в состояние подтверждения
        await state.set_state(RequestAssignmentStates.waiting_for_confirmation)

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка выбора специализации: {e}")
        await callback.answer(get_text("common.error_occurred", language=lang).format(error=str(e)), show_alert=True)

@router.callback_query(F.data.startswith("executor_"))
async def handle_executor_selection(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru"):
    """Обработка выбора конкретного исполнителя"""
    lang = language

    try:
        # Получаем ID исполнителя из callback data
        executor_id = int(callback.data.split("_")[1])

        # Сохраняем ID исполнителя в состоянии
        await state.update_data(executor_id=executor_id)

        # Получаем данные заявки
        data = await state.get_data()
        request_number = data.get("request_number")

        # Получаем заявку и исполнителя
        request = db.query(Request).filter(Request.request_number == request_number).first()
        executor = db.query(User).filter(User.id == executor_id).first()

        if not request or not executor:
            await callback.answer(get_text("request_assignment.request_or_executor_not_found", language=lang), show_alert=True)
            return

        # Показываем подтверждение назначения
        keyboard = get_assignment_confirmation_keyboard("individual", lang)

        confirmation_text = get_text("request_assignment.confirmation_individual", language=lang).format(
            request_number=request_number,
            executor_name=executor.full_name,
            category=request.category,
            address=request.address
        )

        await callback.message.edit_text(confirmation_text, reply_markup=keyboard)

        # Переходим в состояние подтверждения
        await state.set_state(RequestAssignmentStates.waiting_for_confirmation)

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка выбора исполнителя: {e}")
        await callback.answer(get_text("common.error_occurred", language=lang).format(error=str(e)), show_alert=True)

@router.callback_query(F.data == "confirm_assignment")
async def handle_assignment_confirmation(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru"):
    """Подтверждение назначения заявки"""
    lang = language

    try:
        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")
        specialization = data.get("specialization")
        executor_id = data.get("executor_id")

        if not request_number:
            await callback.answer(get_text("request_assignment.request_not_in_state", language=lang), show_alert=True)
            return

        # Создаем сервис назначений
        assignment_service = AssignmentService(db)

        # Выполняем назначение
        if specialization:
            # Групповое назначение
            assignment = assignment_service.assign_to_group(
                request_number=request_number,
                specialization=specialization,
                assigned_by=callback.from_user.id
            )
        elif executor_id:
            # Индивидуальное назначение
            assignment = assignment_service.assign_to_executor(
                request_number=request_number,
                executor_id=executor_id,
                assigned_by=callback.from_user.id
            )
        else:
            await callback.answer(get_text("request_assignment.no_assignment_type", language=lang), show_alert=True)
            return

        # Показываем сообщение об успехе
        success_text = get_text("request_assignment.assignment_success", language=lang)

        await callback.message.edit_text(success_text)

        # Очищаем состояние
        await state.clear()

        await callback.answer(get_text("request_assignment.assignment_success_alert", language=lang))

    except Exception as e:
        logger.error(f"Ошибка подтверждения назначения: {e}")
        await callback.answer(get_text("common.error_occurred", language=lang).format(error=str(e)), show_alert=True)

@router.callback_query(F.data == "cancel_assignment")
async def handle_assignment_cancellation(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru"):
    """Отмена процесса назначения"""
    lang = language

    try:
        # Очищаем состояние
        await state.clear()

        await callback.message.edit_text(get_text("request_assignment.assignment_cancelled", language=lang))
        await callback.answer(get_text("request_assignment.assignment_cancelled_alert", language=lang))

    except Exception as e:
        logger.error(f"Ошибка отмены назначения: {e}")
        await callback.answer(get_text("common.error_occurred", language=lang).format(error=str(e)), show_alert=True)

@router.callback_query(F.data.startswith("view_assignments_"))
async def handle_view_assignments(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru"):
    """Просмотр назначений заявки"""
    lang = language

    try:
        # Получаем номер заявки
        request_number = callback.data.split("_")[-1]

        # Получаем назначения
        assignment_service = AssignmentService(db)
        assignments = assignment_service.get_request_assignments(request_number)

        if not assignments:
            await callback.answer(get_text("request_assignment.no_assignments_found", language=lang), show_alert=True)
            return

        # Формируем текст с назначениями
        text = get_text("request_assignment.assignments_list_header", language=lang).format(request_number=request_number)
        text += "\n\n"

        group_label = get_text("request_assignment.group_label", language=lang)
        executor_label = get_text("request_assignment.executor_label", language=lang)
        date_label = get_text("request_assignment.date_label", language=lang)
        status_label = get_text("request_assignment.status_label", language=lang)

        for assignment in assignments:
            if assignment.is_group_assignment:
                text += f"👥 {group_label}: {assignment.group_specialization}\n"
            elif assignment.is_individual_assignment:
                executor = db.query(User).filter(User.id == assignment.executor_id).first()
                executor_name = executor.full_name if executor else f"ID {assignment.executor_id}"
                text += f"👤 {executor_label}: {executor_name}\n"

            text += f"📅 {date_label}: {assignment.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            text += f"📊 {status_label}: {assignment.status}\n\n"

        await callback.message.edit_text(text)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка просмотра назначений: {e}")
        await callback.answer(get_text("common.error_occurred", language=lang).format(error=str(e)), show_alert=True)
