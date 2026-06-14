"""
Обработчики для управления отчетами о выполнении заявок
Обеспечивает функциональность просмотра и принятия отчетов
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.states.request_reports import RequestReportStates
from uk_management_bot.services.comment_service import CommentService
from uk_management_bot.keyboards.request_reports import (
    get_report_confirmation_keyboard,
    get_report_actions_keyboard
)
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.auth_helpers import check_user_role
from uk_management_bot.utils.workflow_predicates import is_awaiting_applicant
from uk_management_bot.utils.constants import (
    ROLE_MANAGER, ROLE_APPLICANT
)

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data.startswith("view_report_"))
async def handle_view_report(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru"):
    """Просмотр отчета о выполнении заявки"""
    try:
        # Получаем номер заявки
        request_number = callback.data.split("_")[-1]
        
        # Проверяем существование заявки
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            from uk_management_bot.utils.safe_localization import safe_get_text
            await callback.answer(safe_get_text("errors.request_not_found", language=language), show_alert=True)
            return

        # Проверяем права доступа
        user_id = callback.from_user.id
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            from uk_management_bot.utils.safe_localization import safe_get_text
            await callback.answer(safe_get_text("errors.user_not_found", language=language), show_alert=True)
            return

        # Проверяем, что пользователь имеет отношение к заявке
        user_roles = user.roles if user.roles else []
        has_access = (
            request.user_id == user_id or  # Заявитель
            request.executor_id == user_id or  # Исполнитель
            ROLE_MANAGER in user_roles  # Менеджер
        )

        if not has_access:
            await callback.answer(get_text("request_reports.handlers.no_access_view_report", language=language), show_alert=True)
            return

        # Проверяем, есть ли отчет
        if not request.completion_report:
            await callback.answer(get_text("request_reports.handlers.no_report_yet", language=language), show_alert=True)
            return

        # Получаем комментарии с отчетами
        comment_service = CommentService(db)
        report_comments = comment_service.get_comments_by_type(request.request_number, "report")

        # Формируем текст отчета
        lang = language
        report_text = format_report_for_display(request, report_comments, lang)
        
        # Показываем отчет
        keyboard = get_report_actions_keyboard(request.request_number, request.status, lang)
        
        await callback.message.edit_text(
            report_text,
            reply_markup=keyboard
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка просмотра отчета: {e}")
        await callback.answer(get_text("request_reports.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)

@router.callback_query(F.data.startswith("approve_request_"))
async def handle_approve_request(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru"):
    """Принятие заявки заявителем"""
    try:
        # Проверяем права доступа (только заявитель)
        if not await check_user_role(callback.from_user.id, ROLE_APPLICANT, db):
            await callback.answer(get_text("request_reports.handlers.no_access_approve", language=language), show_alert=True)
            return
        
        request_number = callback.data.split("_")[-1]
        
        # Проверяем существование заявки
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer(get_text("request_reports.handlers.request_not_found", language=language), show_alert=True)
            return

        # Проверяем, что заявка принадлежит этому пользователю
        if request.user_id != callback.from_user.id:
            await callback.answer(get_text("request_reports.handlers.only_own_requests", language=language), show_alert=True)
            return

        # PR2a-6: заявка ожидает решения заявителя (Исполнено, не возвращена) —
        # канон-предикат вместо сырого status==Исполнено (возвращённые ждут
        # менеджера и в отчёт/доработку заявителем не идут).
        if not is_awaiting_applicant(request):
            await callback.answer(get_text("request_reports.handlers.only_completed_requests", language=language), show_alert=True)
            return
        
        # Сохраняем данные в состоянии
        await state.update_data(
            request_number=request_number,
            current_status=request.status
        )
        
        # Показываем подтверждение принятия
        lang = language
        keyboard = get_report_confirmation_keyboard(lang)
        
        confirmation_text = get_text("reports.approval_confirmation", language=lang).format(
            request_id=request_number,
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
        await callback.answer(get_text("request_reports.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)

@router.callback_query(F.data == "confirm_approval")
async def handle_approval_confirmation(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru"):
    """Подтверждение принятия заявки"""
    try:
        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")

        if not request_number:
            await callback.answer(get_text("request_reports.handlers.request_data_not_found", language=language), show_alert=True)
            return

        # SSOT-кластер #1, PR2d: приёмка заявителем = канонический rated-accept
        # (APPLICANT_ACCEPT с оценкой). Прежний прямой перевод в «Принято» без
        # рейтинга через update_request_status снят. Редирект на канон:
        # показываем клавиатуру оценки 1–5★, приёмку выполнит
        # request_acceptance.save_rating → run_command(APPLICANT_ACCEPT).
        from uk_management_bot.keyboards.admin import get_rating_keyboard
        await state.clear()
        await callback.message.edit_text(
            get_text("request_acceptance.handlers.rate_request", language=language),
            reply_markup=get_rating_keyboard(request_number),
            parse_mode="HTML",
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка подтверждения принятия: {e}")
        await callback.answer(get_text("request_reports.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)

@router.callback_query(F.data == "cancel_approval")
async def handle_approval_cancellation(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru"):
    """Отмена принятия заявки"""
    try:
        # Очищаем состояние
        await state.clear()
        
        lang = language
        await callback.message.edit_text(get_text("request_reports.handlers.approval_cancelled", language=lang))
        await callback.answer(get_text("request_reports.handlers.approval_cancelled", language=lang))

    except Exception as e:
        logger.error(f"Ошибка отмены принятия: {e}")
        await callback.answer(get_text("request_reports.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)

@router.callback_query(F.data.startswith("request_revision_"))
async def handle_request_revision(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru"):
    """Запрос доработки заявки"""
    try:
        # Проверяем права доступа (только заявитель)
        if not await check_user_role(callback.from_user.id, ROLE_APPLICANT, db):
            await callback.answer(get_text("request_reports.handlers.no_access_revision", language=language), show_alert=True)
            return

        request_number = callback.data.split("_")[-1]

        # Проверяем существование заявки
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer(get_text("request_reports.handlers.request_not_found", language=language), show_alert=True)
            return

        # Проверяем, что заявка принадлежит этому пользователю
        if request.user_id != callback.from_user.id:
            await callback.answer(get_text("request_reports.handlers.only_own_revision", language=language), show_alert=True)
            return

        # PR2a-6: заявка ожидает решения заявителя (Исполнено, не возвращена) —
        # канон-предикат вместо сырого status==Исполнено (возвращённые ждут
        # менеджера и в отчёт/доработку заявителем не идут).
        if not is_awaiting_applicant(request):
            await callback.answer(get_text("request_reports.handlers.only_completed_revision", language=language), show_alert=True)
            return
        
        # Сохраняем данные в состоянии
        await state.update_data(
            request_number=request_number,
            action="revision"
        )
        
        # Запрашиваем причину доработки
        lang = language
        await callback.message.edit_text(
            get_text("reports.enter_revision_reason", language=lang)
        )
        
        # Переходим в состояние ввода причины
        await state.set_state(RequestReportStates.waiting_for_revision_reason)
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка запроса доработки: {e}")
        await callback.answer(get_text("request_reports.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)

@router.message(RequestReportStates.waiting_for_revision_reason)
async def handle_revision_reason_input(message: Message, state: FSMContext, db: Session, language: str = "ru"):
    """Обработка ввода причины доработки"""
    try:
        # Получаем причину доработки
        revision_reason = message.text.strip()
        
        if not revision_reason:
            await message.answer(get_text("request_reports.handlers.enter_revision_reason_prompt", language=language))
            return

        if len(revision_reason) < 10:
            await message.answer(get_text("request_reports.handlers.revision_reason_too_short", language=language))
            return
        
        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")
        
        comment_service = CommentService(db)

        # Получаем текущую заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await message.answer(get_text("request_reports.handlers.request_not_found", language=language))
            return

        # SSOT-кластер #1, PR2d: доработка заявителем = канонический возврат
        # (APPLICANT_RETURN, Исполнено→Возвращена; дальше разбирает менеджер).
        # Прежний прямой перевод в «В работе» через update_request_status снят
        # (у заявителя нет канон-ребра Исполнено→В работе).
        from uk_management_bot.database.session import SessionLocal
        from uk_management_bot.services.workflow_runner import (
            run_command_sync, RequestNotFound)
        from uk_management_bot.utils.request_workflow import (
            Action, ActionCommand, PrincipalRef, WorkflowError)
        actor = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not actor:
            await message.answer(get_text("request_reports.handlers.request_not_found", language=language))
            return
        try:
            run_command_sync(
                SessionLocal, request_number,
                PrincipalRef(kind="user", user_id=actor.id, source="telegram"),
                ActionCommand(f"revision:{request_number}", Action.APPLICANT_RETURN,
                              {"return_reason": revision_reason}),
            )
        except RequestNotFound:
            await message.answer(get_text("request_reports.handlers.request_not_found", language=language))
            return
        except WorkflowError as e:
            logger.error(f"APPLICANT_RETURN (доработка) отклонён для {request_number}: {e}")
            await message.answer(get_text("request_reports.handlers.error_occurred", language=language).format(error=str(e)))
            return

        # Добавляем комментарий о доработке
        comment_service.add_clarification_comment(
            request_id=request_number,
            user_id=message.from_user.id,
            clarification=f"Запрошена доработка. Причина: {revision_reason}"
        )
        
        # Показываем подтверждение
        lang = language
        success_text = get_text("reports.revision_requested", language=lang).format(
            request_id=request_number,
            reason=revision_reason
        )
        
        await message.answer(success_text)
        
        # Очищаем состояние
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка сохранения причины доработки: {e}")
        await message.answer(get_text("request_reports.handlers.error_occurred", language=language).format(error=str(e)))

@router.callback_query(F.data.startswith("back_to_report_"))
async def handle_back_to_report(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru"):
    """Возврат к отчету"""
    try:
        # Получаем ID заявки
        request_number = callback.data.split("_")[-1]
        
        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer(get_text("request_reports.handlers.request_not_found", language=language), show_alert=True)
            return

        # Получаем комментарии с отчетами
        comment_service = CommentService(db)
        report_comments = comment_service.get_comments_by_type(request.request_number, "report")

        # Формируем текст отчета
        lang = language
        report_text = format_report_for_display(request, report_comments, lang)
        
        # Показываем отчет
        keyboard = get_report_actions_keyboard(request.request_number, request.status, lang)
        
        await callback.message.edit_text(
            report_text,
            reply_markup=keyboard
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка возврата к отчету: {e}")
        await callback.answer(get_text("request_reports.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)

# Вспомогательные функции

def format_report_for_display(request: Request, report_comments: list, language: str = "ru") -> str:
    """Форматирование отчета для отображения"""
    try:
        # Основная информация о заявке
        report_text = f"📋 **{get_text('request_reports.handlers.report_title', language=language)} #{request.request_number}**\n\n"
        report_text += f"🏷️ **{get_text('request_reports.handlers.category', language=language)}**: {request.category}\n"
        report_text += f"📍 **{get_text('request_reports.handlers.address', language=language)}**: {request.address}\n"
        report_text += f"📝 **{get_text('request_reports.handlers.description', language=language)}**: {request.description}\n"
        report_text += f"📊 **{get_text('request_reports.handlers.status', language=language)}**: {request.status}\n"

        # Информация о выполнении
        if request.completed_at:
            report_text += f"✅ **{get_text('request_reports.handlers.completed_at', language=language)}**: {request.completed_at.strftime('%d.%m.%Y %H:%M')}\n"

        # Отчет о выполнении
        if request.completion_report:
            report_text += f"\n📋 **{get_text('request_reports.handlers.completion_report', language=language)}**:\n{request.completion_report}\n"

        # Материалы для закупки (если были)
        if request.purchase_materials:
            report_text += f"\n🛒 **{get_text('request_reports.handlers.purchase_materials', language=language)}**:\n{request.purchase_materials}\n"

        # Комментарии с отчетами
        if report_comments:
            report_text += f"\n📝 **{get_text('request_reports.handlers.additional_reports', language=language)}**:\n"
            for comment in report_comments[:3]:  # Показываем только последние 3
                user = comment.user.full_name if comment.user else get_text("request_reports.handlers.user_label", language=language).format(user_id=comment.user_id)
                date_str = comment.created_at.strftime('%d.%m.%Y %H:%M') if comment.created_at else get_text("request_reports.handlers.unknown_date", language=language)
                report_text += f"👤 **{user}** ({date_str}):\n{comment.comment_text}\n\n"

        return report_text

    except Exception as e:
        logger.error(f"Ошибка форматирования отчета: {e}")
        return get_text("request_reports.handlers.report_format_error", language=language)
