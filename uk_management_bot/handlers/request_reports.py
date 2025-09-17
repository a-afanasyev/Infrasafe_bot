"""
Обработчики для управления отчетами о выполнении заявок
Обеспечивает функциональность просмотра и принятия отчетов
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session

from uk_management_bot.database.session import get_db
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.states.request_reports import RequestReportStates
from uk_management_bot.services.request_service import RequestService
from uk_management_bot.services.comment_service import CommentService
from uk_management_bot.keyboards.request_reports import (
    get_report_confirmation_keyboard,
    get_report_actions_keyboard
)
from uk_management_bot.utils.helpers import get_text, get_language_from_event
from uk_management_bot.utils.auth_helpers import check_user_role
from uk_management_bot.utils.constants import (
    ROLE_MANAGER, ROLE_EXECUTOR, ROLE_APPLICANT,
    REQUEST_STATUS_APPROVED
)

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data.startswith("view_report_"))
async def handle_view_report(callback: CallbackQuery, state: FSMContext, db: Session):
    """Просмотр отчета о выполнении заявки"""
    try:
        # Получаем ID заявки
        request_id = int(callback.data.split("_")[-1])
        
        # Проверяем существование заявки
        request = db.query(Request).filter(Request.id == request_id).first()
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        # Проверяем права доступа
        user_id = callback.from_user.id
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        
        # Проверяем, что пользователь имеет отношение к заявке
        user_roles = user.roles if user.roles else []
        has_access = (
            request.user_id == user_id or  # Заявитель
            request.executor_id == user_id or  # Исполнитель
            ROLE_MANAGER in user_roles  # Менеджер
        )
        
        if not has_access:
            await callback.answer("У вас нет прав для просмотра отчета по этой заявке", show_alert=True)
            return
        
        # Проверяем, есть ли отчет
        if not request.completion_report:
            await callback.answer("Отчет о выполнении еще не создан", show_alert=True)
            return
        
        # Получаем комментарии с отчетами
        comment_service = CommentService(db)
        report_comments = comment_service.get_comments_by_type(request_id, "report")
        
        # Формируем текст отчета
        lang = get_language_from_event(callback, db)
        report_text = format_report_for_display(request, report_comments, lang)
        
        # Показываем отчет
        keyboard = get_report_actions_keyboard(request_id, request.status, lang)
        
        await callback.message.edit_text(
            report_text,
            reply_markup=keyboard
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка просмотра отчета: {e}")
        await callback.answer(f"Произошла ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("approve_request_"))
async def handle_approve_request(callback: CallbackQuery, state: FSMContext, db: Session):
    """Принятие заявки заявителем"""
    try:
        # Проверяем права доступа (только заявитель)
        if not await check_user_role(callback.from_user.id, ROLE_APPLICANT, db):
            await callback.answer("У вас нет прав для принятия заявки", show_alert=True)
            return
        
        request_id = int(callback.data.split("_")[-1])
        
        # Проверяем существование заявки
        request = db.query(Request).filter(Request.id == request_id).first()
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        # Проверяем, что заявка принадлежит этому пользователю
        if request.user_id != callback.from_user.id:
            await callback.answer("Вы можете принимать только свои заявки", show_alert=True)
            return
        
        # Проверяем, что заявка выполнена
        if request.status != "Исполнено":
            await callback.answer("Можно принимать только выполненные заявки", show_alert=True)
            return
        
        # Сохраняем данные в состоянии
        await state.update_data(
            request_id=request_id,
            current_status=request.status
        )
        
        # Показываем подтверждение принятия
        lang = get_language_from_event(callback, db)
        keyboard = get_report_confirmation_keyboard(lang)
        
        confirmation_text = get_text("reports.approval_confirmation", language=lang).format(
            request_id=request_id,
            category=request.category,
            address=request.address
        )
        
        await callback.message.edit_text(
            confirmation_text,
            reply_markup=keyboard
        )
        
        # Переходим в состояние подтверждения
        await state.set_state(RequestReportStates.waiting_for_approval_confirmation)
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка принятия заявки: {e}")
        await callback.answer(f"Произошла ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data == "confirm_approval")
async def handle_approval_confirmation(callback: CallbackQuery, state: FSMContext, db: Session):
    """Подтверждение принятия заявки"""
    try:
        # Получаем данные из состояния
        data = await state.get_data()
        request_id = data.get("request_id")
        current_status = data.get("current_status")
        
        if not request_id:
            await callback.answer("Ошибка: данные заявки не найдены", show_alert=True)
            return
        
        # Создаем сервисы
        request_service = RequestService(db)
        comment_service = CommentService(db)
        
        # Изменяем статус на "Принято"
        updated_request = request_service.change_status(
            request_id=request_id,
            new_status=REQUEST_STATUS_APPROVED,
            user_id=callback.from_user.id
        )
        
        # Добавляем комментарий о принятии
        comment_service.add_status_change_comment(
            request_id=request_id,
            user_id=callback.from_user.id,
            previous_status=current_status,
            new_status=REQUEST_STATUS_APPROVED,
            additional_comment="Заявка принята заявителем"
        )
        
        # Показываем сообщение об успехе
        lang = get_language_from_event(callback, db)
        success_text = get_text("reports.approval_success", language=lang).format(
            request_id=request_id
        )
        
        await callback.message.edit_text(success_text)
        
        # Очищаем состояние
        await state.clear()
        
        await callback.answer("Заявка успешно принята!")
        
    except Exception as e:
        logger.error(f"Ошибка подтверждения принятия: {e}")
        await callback.answer(f"Произошла ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data == "cancel_approval")
async def handle_approval_cancellation(callback: CallbackQuery, state: FSMContext, db: Session):
    """Отмена принятия заявки"""
    try:
        # Очищаем состояние
        await state.clear()
        
        await callback.message.edit_text("Принятие заявки отменено")
        await callback.answer("Принятие заявки отменено")
        
    except Exception as e:
        logger.error(f"Ошибка отмены принятия: {e}")
        await callback.answer(f"Произошла ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("request_revision_"))
async def handle_request_revision(callback: CallbackQuery, state: FSMContext, db: Session):
    """Запрос доработки заявки"""
    try:
        # Проверяем права доступа (только заявитель)
        if not await check_user_role(callback.from_user.id, ROLE_APPLICANT, db):
            await callback.answer("У вас нет прав для запроса доработки", show_alert=True)
            return
        
        request_id = int(callback.data.split("_")[-1])
        
        # Проверяем существование заявки
        request = db.query(Request).filter(Request.id == request_id).first()
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        # Проверяем, что заявка принадлежит этому пользователю
        if request.user_id != callback.from_user.id:
            await callback.answer("Вы можете запрашивать доработку только своих заявок", show_alert=True)
            return
        
        # Проверяем, что заявка выполнена
        if request.status != "Исполнено":
            await callback.answer("Можно запрашивать доработку только выполненных заявок", show_alert=True)
            return
        
        # Сохраняем данные в состоянии
        await state.update_data(
            request_id=request_id,
            action="revision"
        )
        
        # Запрашиваем причину доработки
        lang = get_language_from_event(callback, db)
        await callback.message.edit_text(
            get_text("reports.enter_revision_reason", language=lang)
        )
        
        # Переходим в состояние ввода причины
        await state.set_state(RequestReportStates.waiting_for_revision_reason)
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка запроса доработки: {e}")
        await callback.answer(f"Произошла ошибка: {str(e)}", show_alert=True)

@router.message(RequestReportStates.waiting_for_revision_reason)
async def handle_revision_reason_input(message: Message, state: FSMContext, db: Session):
    """Обработка ввода причины доработки"""
    try:
        # Получаем причину доработки
        revision_reason = message.text.strip()
        
        if not revision_reason:
            await message.answer("Пожалуйста, введите причину доработки")
            return
        
        if len(revision_reason) < 10:
            await message.answer("Причина доработки должна содержать минимум 10 символов")
            return
        
        # Получаем данные из состояния
        data = await state.get_data()
        request_id = data.get("request_id")
        
        # Создаем сервисы
        request_service = RequestService(db)
        comment_service = CommentService(db)
        
        # Получаем текущую заявку
        request = db.query(Request).filter(Request.id == request_id).first()
        if not request:
            await message.answer("Заявка не найдена")
            return
        
        # Изменяем статус на "В работе" (возвращаем к доработке)
        updated_request = request_service.change_status(
            request_id=request_id,
            new_status="В работе",
            user_id=message.from_user.id
        )
        
        # Добавляем комментарий о доработке
        comment_service.add_clarification_comment(
            request_id=request_id,
            user_id=message.from_user.id,
            clarification=f"Запрошена доработка. Причина: {revision_reason}"
        )
        
        # Показываем подтверждение
        lang = get_language_from_event(callback, db)
        success_text = get_text("reports.revision_requested", language=lang).format(
            request_id=request_id,
            reason=revision_reason
        )
        
        await message.answer(success_text)
        
        # Очищаем состояние
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка сохранения причины доработки: {e}")
        await message.answer(f"Произошла ошибка: {str(e)}")

@router.callback_query(F.data.startswith("back_to_report_"))
async def handle_back_to_report(callback: CallbackQuery, state: FSMContext, db: Session):
    """Возврат к отчету"""
    try:
        # Получаем ID заявки
        request_id = int(callback.data.split("_")[-1])
        
        # Получаем заявку
        request = db.query(Request).filter(Request.id == request_id).first()
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        # Получаем комментарии с отчетами
        comment_service = CommentService(db)
        report_comments = comment_service.get_comments_by_type(request_id, "report")
        
        # Формируем текст отчета
        lang = get_language_from_event(callback, db)
        report_text = format_report_for_display(request, report_comments, lang)
        
        # Показываем отчет
        keyboard = get_report_actions_keyboard(request_id, request.status, lang)
        
        await callback.message.edit_text(
            report_text,
            reply_markup=keyboard
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка возврата к отчету: {e}")
        await callback.answer(f"Произошла ошибка: {str(e)}", show_alert=True)

# Вспомогательные функции

def format_report_for_display(request: Request, report_comments: list, language: str = "ru") -> str:
    """Форматирование отчета для отображения"""
    try:
        # Основная информация о заявке
        report_text = f"📋 **Отчет о выполнении заявки #{request.request_number}**\n\n"
        report_text += f"🏷️ **Категория**: {request.category}\n"
        report_text += f"📍 **Адрес**: {request.address}\n"
        report_text += f"📝 **Описание**: {request.description}\n"
        report_text += f"📊 **Статус**: {request.status}\n"
        
        # Информация о выполнении
        if request.completed_at:
            report_text += f"✅ **Завершена**: {request.completed_at.strftime('%d.%m.%Y %H:%M')}\n"
        
        # Отчет о выполнении
        if request.completion_report:
            report_text += f"\n📋 **Отчет о выполнении**:\n{request.completion_report}\n"
        
        # Материалы для закупки (если были)
        if request.purchase_materials:
            report_text += f"\n🛒 **Материалы для закупки**:\n{request.purchase_materials}\n"
        
        # Комментарии с отчетами
        if report_comments:
            report_text += f"\n📝 **Дополнительные отчеты**:\n"
            for comment in report_comments[:3]:  # Показываем только последние 3
                user = comment.user.full_name if comment.user else f"Пользователь {comment.user_id}"
                date_str = comment.created_at.strftime('%d.%m.%Y %H:%M') if comment.created_at else "Неизвестно"
                report_text += f"👤 **{user}** ({date_str}):\n{comment.comment_text}\n\n"
        
        return report_text
        
    except Exception as e:
        logger.error(f"Ошибка форматирования отчета: {e}")
        return "Ошибка при формировании отчета"
