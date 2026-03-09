"""
Обработчики для управления статусами заявок
Обеспечивает функциональность изменения статусов заявок с комментариями
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session

from uk_management_bot.database.session import get_db
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.states.request_status import RequestStatusStates
from uk_management_bot.services.request_service import RequestService
from uk_management_bot.services.comment_service import CommentService
from uk_management_bot.keyboards.request_status import (
    get_status_selection_keyboard,
    get_status_confirmation_keyboard,
    get_executor_status_actions_keyboard
)
from uk_management_bot.utils.helpers import get_text, get_language_from_event
from uk_management_bot.utils.status_display import get_status_display, get_status_with_emoji, STATUS_EMOJI
from uk_management_bot.utils.auth_helpers import check_user_role
from uk_management_bot.utils.constants import (
    ROLE_MANAGER, ROLE_EXECUTOR, ROLE_APPLICANT,
    REQUEST_STATUS_NEW, REQUEST_STATUS_IN_PROGRESS, REQUEST_STATUS_PURCHASE,
    REQUEST_STATUS_CLARIFICATION, REQUEST_STATUS_EXECUTED,
    REQUEST_STATUS_COMPLETED, REQUEST_STATUS_APPROVED
)

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data.startswith("change_status_"))
async def handle_status_change_start(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru"):
    """Начало процесса изменения статуса заявки"""
    try:
        lang = language
        # Получаем номер заявки
        request_number = callback.data.split("_")[-1]

        # Проверяем существование заявки
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            from uk_management_bot.utils.safe_localization import safe_get_text
            await callback.answer(safe_get_text("errors.request_not_found", language=lang), show_alert=True)
            return

        # Проверяем права доступа
        user_id = callback.from_user.id
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            await callback.answer(get_text("request_status_mgmt.handlers.user_not_found", language=lang), show_alert=True)
            return

        # Определяем доступные статусы в зависимости от роли и текущего статуса
        available_statuses = get_available_statuses(user, request)

        if not available_statuses:
            await callback.answer(get_text("request_status_mgmt.handlers.no_available_statuses", language=lang), show_alert=True)
            return

        # Сохраняем данные в состоянии
        await state.update_data(
            request_number=request_number,
            current_status=request.status,
            user_roles=user.roles
        )

        # Показываем выбор нового статуса
        keyboard = get_status_selection_keyboard(available_statuses, lang)
        
        await callback.message.edit_text(
            get_text("request_status_mgmt.handlers.select_status", language=lang).format(
                current_status=get_status_display(request.status, language=lang)
            ),
            reply_markup=keyboard
        )
        
        # Переходим в состояние выбора статуса
        await state.set_state(RequestStatusStates.waiting_for_status)
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка начала изменения статуса: {e}")
        await callback.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)

@router.callback_query(F.data.startswith("status_"))
async def handle_status_selection(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru"):
    """Обработка выбора нового статуса"""
    try:
        lang = language
        # Получаем новый статус из callback data
        new_status = callback.data.split("_", 1)[1]

        # Сохраняем новый статус в состоянии
        await state.update_data(new_status=new_status)

        # Получаем данные заявки
        data = await state.get_data()
        request_number = data.get("request_number")

        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer(get_text("request_status_mgmt.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Проверяем, нужен ли комментарий для этого статуса
        requires_comment = new_status in [REQUEST_STATUS_PURCHASE, REQUEST_STATUS_CLARIFICATION, REQUEST_STATUS_EXECUTED]

        if requires_comment:
            # Запрашиваем комментарий
            comment_prompt = get_comment_prompt(new_status, lang)
            
            await callback.message.edit_text(comment_prompt)
            
            # Переходим в состояние ввода комментария
            await state.set_state(RequestStatusStates.waiting_for_comment)
        else:
            # Показываем подтверждение без комментария
            await show_status_confirmation(callback, state, db, new_status)
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка выбора статуса: {e}")
        await callback.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)

@router.message(RequestStatusStates.waiting_for_comment)
async def handle_comment_input(message: Message, state: FSMContext, db: Session, language: str = "ru"):
    """Обработка ввода комментария для изменения статуса"""
    try:
        lang = language
        # Получаем комментарий
        comment = message.text.strip()

        if not comment:
            await message.answer(get_text("request_status_mgmt.handlers.please_enter_comment", language=lang))
            return
        
        # Сохраняем комментарий в состоянии
        await state.update_data(comment=comment)
        
        # Получаем данные из состояния
        data = await state.get_data()
        new_status = data.get("new_status")
        
        # Показываем подтверждение с комментарием
        await show_status_confirmation(message, state, db, new_status, comment)
        
    except Exception as e:
        logger.error(f"Ошибка ввода комментария: {e}")
        await message.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)))

@router.callback_query(F.data == "confirm_status_change")
async def handle_status_confirmation(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru", user: User = None):
    """Подтверждение изменения статуса"""
    try:
        lang = language
        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")
        current_status = data.get("current_status")
        new_status = data.get("new_status")
        comment = data.get("comment")

        if not request_number or not new_status:
            await callback.answer(get_text("request_status_mgmt.handlers.data_not_found", language=lang), show_alert=True)
            return
        
        # Создаем сервисы
        request_service = RequestService(db)
        comment_service = CommentService(db)
        
        # Изменяем статус заявки
        result = request_service.update_status_by_actor(
            request_number=request_number,
            new_status=new_status,
            actor_telegram_id=callback.from_user.id
        )
        if not result["success"]:
            await callback.message.edit_text(f"❌ {result['message']}")
            await state.clear()
            return

        # Добавляем комментарий об изменении статуса
        if user:
            if comment:
                comment_service.add_status_change_comment(
                    request_number=request_number,
                    user_id=user.id,
                    previous_status=current_status,
                    new_status=new_status,
                    additional_comment=comment
                )
            else:
                comment_service.add_status_change_comment(
                    request_number=request_number,
                    user_id=user.id,
                    previous_status=current_status,
                    new_status=new_status
                )
        
        # Показываем сообщение об успехе
        success_text = get_text("request_status_mgmt.handlers.success", language=lang).format(
            request_number=request_number,
            old_status=get_status_display(current_status, language=lang),
            new_status=get_status_display(new_status, language=lang)
        )
        
        await callback.message.edit_text(success_text)
        
        # Очищаем состояние
        await state.clear()
        
        await callback.answer(get_text("request_status_mgmt.handlers.status_changed_success", language=lang))

    except Exception as e:
        logger.error(f"Ошибка подтверждения изменения статуса: {e}")
        await callback.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)

@router.callback_query(F.data == "cancel_status_change")
async def handle_status_cancellation(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru"):
    """Отмена изменения статуса"""
    try:
        lang = language
        # Очищаем состояние
        await state.clear()

        await callback.message.edit_text(get_text("request_status_mgmt.handlers.status_change_cancelled", language=lang))
        await callback.answer(get_text("request_status_mgmt.handlers.status_change_cancelled", language=lang))

    except Exception as e:
        logger.error(f"Ошибка отмены изменения статуса: {e}")
        await callback.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)

# Специальные обработчики для исполнителей

@router.callback_query(F.data.startswith("take_to_work_"))
async def handle_take_to_work(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru"):
    """Исполнитель берет заявку в работу"""
    try:
        lang = language
        # Проверяем права доступа
        if not await check_user_role(callback.from_user.id, ROLE_EXECUTOR, db):
            await callback.answer(get_text("request_status_mgmt.handlers.no_permission", language=lang), show_alert=True)
            return

        request_number = callback.data.split("_")[-1]

        # Проверяем, что заявка назначена этому исполнителю
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request or request.executor_id != callback.from_user.id:
            await callback.answer(get_text("request_status_mgmt.handlers.request_not_assigned_to_you", language=lang), show_alert=True)
            return
        
        # Изменяем статус на "В работе"
        request_service = RequestService(db)
        comment_service = CommentService(db)

        result = request_service.update_status_by_actor(
            request_number=request_number,
            new_status=REQUEST_STATUS_IN_PROGRESS,
            actor_telegram_id=callback.from_user.id
        )
        if not result["success"]:
            await callback.answer(result["message"], show_alert=True)
            return

        # Добавляем комментарий
        comment_service.add_status_change_comment(
            request_number=request_number,
            actor_telegram_id=callback.from_user.id,
            previous_status=request.status,
            new_status=REQUEST_STATUS_IN_PROGRESS,
            additional_comment="Исполнитель взял заявку в работу"
        )

        await callback.answer(get_text("request_status_mgmt.handlers.request_taken_to_work", language=lang))

    except Exception as e:
        logger.error(f"Ошибка взятия в работу: {e}")
        await callback.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)

@router.callback_query(F.data.startswith("purchase_materials_"))
async def handle_purchase_materials(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru"):
    """Перевод заявки в статус закупки материалов"""
    try:
        lang = language
        # Проверяем права доступа
        if not await check_user_role(callback.from_user.id, ROLE_EXECUTOR, db):
            await callback.answer(get_text("request_status_mgmt.handlers.no_permission", language=lang), show_alert=True)
            return

        request_number = callback.data.split("_")[-1]

        # Сохраняем данные в состоянии
        await state.update_data(
            request_number=request_number,
            action="purchase_materials"
        )

        # Запрашиваем список материалов
        await callback.message.edit_text(
            get_text("request_status_mgmt.handlers.enter_materials", language=lang)
        )

        # Переходим в состояние ввода материалов
        await state.set_state(RequestStatusStates.waiting_for_materials)

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка закупки материалов: {e}")
        await callback.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)

@router.message(RequestStatusStates.waiting_for_materials)
async def handle_materials_input(message: Message, state: FSMContext, db: Session, language: str = "ru", user: User = None):
    """Обработка ввода списка материалов"""
    try:
        lang = language
        # Получаем список материалов
        materials = message.text.strip()

        if not materials:
            await message.answer(get_text("request_status_mgmt.handlers.please_enter_materials", language=lang))
            return
        
        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")
        
        # Создаем сервисы
        request_service = RequestService(db)
        comment_service = CommentService(db)
        
        # Получаем текущую заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await message.answer(get_text("request_status_mgmt.handlers.request_not_found", language=lang))
            return

        # Используем номер заявки
        request_id = request_number
        
        # Изменяем статус на "Закуп"
        result = request_service.update_status_by_actor(
            request_number=request_number,
            new_status=REQUEST_STATUS_PURCHASE,
            actor_telegram_id=message.from_user.id
        )
        if not result["success"]:
            await message.answer(f"❌ {result['message']}")
            await state.clear()
            return

        # Проверяем, есть ли история закупок для восстановления данных
        if request.purchase_history and not request.requested_materials:
            # Если есть история, но нет текущих данных - это повторный переход в закуп
            # Извлекаем последние данные из истории для восстановления
            history_lines = request.purchase_history.split('\n')
            last_requested = None
            last_comment = None
            
            # Ищем последние данные в истории (идем с конца)
            for i in range(len(history_lines) - 1, -1, -1):
                line = history_lines[i].strip()
                if line.startswith("Запрошенные материалы:"):
                    last_requested = line.replace("Запрошенные материалы:", "").strip()
                elif line.startswith("Комментарий менеджера:") and not last_comment:
                    last_comment = line.replace("Комментарий менеджера:", "").strip()
                
                # Если нашли оба поля, можем остановиться
                if last_requested and last_comment:
                    break
            
            # Восстанавливаем данные из истории
            if last_requested and last_requested != "Не указано":
                request.requested_materials = last_requested
            if last_comment and last_comment != "Без комментариев":
                request.manager_materials_comment = last_comment
        
        # Добавляем новые материалы к существующему списку
        if request.requested_materials:
            # Если уже есть материалы, добавляем новые к существующим
            request.requested_materials += f"\n{materials}"
        else:
            # Если это первый переход в закуп - сохраняем новые материалы
            request.requested_materials = materials
        
        # Для обратной совместимости также сохраняем в старое поле
        request.purchase_materials = materials
        
        # Добавляем комментарий о закупке
        if user:
            comment_service.add_purchase_comment(
                request_number=request_number,
                user_id=user.id,
                materials=materials
            )
        
        db.commit()
        
        # Показываем подтверждение с текущими данными
        confirmation_text = get_text("request_status_mgmt.handlers.purchase_status_set", language=lang).format(request_number=request_number)

        if request.requested_materials:
            confirmation_text += get_text("request_status_mgmt.handlers.requested_materials", language=lang).format(materials=request.requested_materials)

        if request.manager_materials_comment:
            confirmation_text += get_text("request_status_mgmt.handlers.manager_comment", language=lang).format(comment=request.manager_materials_comment)

        confirmation_text += get_text("request_status_mgmt.handlers.new_input", language=lang).format(materials=materials)

        await message.answer(confirmation_text)
        
        # Перенаправляем к списку активных заявок
        active_statuses = [REQUEST_STATUS_IN_PROGRESS, REQUEST_STATUS_PURCHASE, REQUEST_STATUS_CLARIFICATION]
        q = (
            db.query(Request)
            .filter(Request.status.in_(active_statuses))
            .order_by(Request.updated_at.desc().nullslast(), Request.created_at.desc())
        )
        requests = q.limit(10).all()
        
        if requests:
            # Показываем список активных заявок
            text = get_text("request_status_mgmt.handlers.active_requests_header", language=lang)
            for i, r in enumerate(requests, 1):
                addr = r.address[:40] + ("…" if len(r.address) > 40 else "")
                text += f"{i}. {get_status_with_emoji(r.status, language=lang)} #{r.request_number} - {r.category}\n"
                text += f"   📍 {addr}\n\n"
            
            from uk_management_bot.keyboards.admin import get_manager_main_keyboard
            await message.answer(text, reply_markup=get_manager_main_keyboard(language=lang))
        
        # Очищаем состояние
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка сохранения материалов: {e}")
        await message.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)))

@router.callback_query(F.data.startswith("complete_work_"))
async def handle_complete_work(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru"):
    """Завершение работы по заявке"""
    try:
        lang = language
        # Проверяем права доступа
        if not await check_user_role(callback.from_user.id, ROLE_EXECUTOR, db):
            await callback.answer(get_text("request_status_mgmt.handlers.no_permission", language=lang), show_alert=True)
            return

        request_number = callback.data.split("_")[-1]

        # Сохраняем данные в состоянии
        await state.update_data(
            request_number=request_number,
            action="complete_work"
        )

        # Запрашиваем отчет о выполнении
        await callback.message.edit_text(
            get_text("request_status_mgmt.handlers.enter_completion_report", language=lang)
        )

        # Переходим в состояние ввода отчета
        await state.set_state(RequestStatusStates.waiting_for_completion_report)

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка завершения работы: {e}")
        await callback.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)

@router.message(RequestStatusStates.waiting_for_completion_report, F.photo | F.video)
async def handle_completion_report_media(message: Message, state: FSMContext, db: Session, language: str = "ru", user: User = None):
    """Обработка фото/видео в отчете о выполнении"""
    try:
        lang = language
        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")

        if not request_number:
            await message.answer(get_text("request_status_mgmt.handlers.request_not_found_in_state", language=lang))
            return

        # Получаем file_id
        if message.photo:
            file_id = message.photo[-1].file_id
            file_type = "photo"
        else:
            file_id = message.video.file_id
            file_type = "video"

        # Сохраняем file_id в FSM
        report_media = data.get('report_media', [])
        if len(report_media) >= 5:
            await message.answer(get_text("request_status_mgmt.handlers.max_files_reached", language=lang))
            return

        report_media.append(file_id)
        await state.update_data(report_media=report_media)

        # Загружаем файл в Media Service
        from uk_management_bot.utils.media_helpers import upload_report_file_to_media_service
        try:
            await upload_report_file_to_media_service(
                bot=message.bot,
                file_id=file_id,
                request_number=request_number,
                report_type=f"completion_{file_type}",
                description=f"Фото/видео отчета #{len(report_media)}",
                uploaded_by=user.id if user else None
            )
            logger.info(f"Файл отчета загружен в Media Service для заявки {request_number}")
        except Exception as e:
            logger.error(f"Ошибка загрузки файла отчета в Media Service: {e}")

        await message.answer(
            get_text("request_status_mgmt.handlers.file_added", language=lang).format(
                count=len(report_media), max=5
            )
        )

    except Exception as e:
        logger.error(f"Ошибка обработки медиа отчета: {e}")
        await message.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)))


@router.message(RequestStatusStates.waiting_for_completion_report)
async def handle_completion_report_input(message: Message, state: FSMContext, db: Session, language: str = "ru", user: User = None):
    """Обработка ввода отчета о выполнении"""
    try:
        lang = language
        # Получаем отчет
        report = message.text.strip() if message.text else ""

        if not report:
            await message.answer(get_text("request_status_mgmt.handlers.please_enter_report", language=lang))
            return

        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")
        report_media = data.get("report_media", [])

        # Создаем сервисы
        request_service = RequestService(db)
        comment_service = CommentService(db)

        # Получаем текущую заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await message.answer(get_text("request_status_mgmt.handlers.request_not_found", language=lang))
            return

        # Изменяем статус на "Выполнена"
        result = request_service.update_status_by_actor(
            request_number=request_number,
            new_status=REQUEST_STATUS_EXECUTED,
            actor_telegram_id=message.from_user.id
        )
        if not result["success"]:
            await message.answer(get_text("request_status_mgmt.handlers.work_completion_failed", language=lang).format(message=result['message']))
            await state.clear()
            return

        # Сохраняем отчет в заявке
        full_report = report
        if report_media:
            full_report += "\n" + get_text("request_status_mgmt.handlers.attached_files", language=lang).format(count=len(report_media))
        request.completion_report = full_report

        # Добавляем комментарий с отчетом
        if user:
            comment_service.add_completion_report_comment(
                request_number=request_number,
                user_id=user.id,
                report=full_report
            )

        db.commit()
        
        # Отправляем уведомление заявителю
        from uk_management_bot.services.notification_service import NotificationService
        notification_service = NotificationService(db)
        await notification_service.notify_request_completed(request.request_number, request.user_id)
        
        # Показываем подтверждение
        success_text = get_text("request_status_mgmt.handlers.work_completed", language=lang).format(
            request_id=request_number
        )

        await message.answer(success_text)

        # Очищаем состояние
        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка завершения работы: {e}")
        await message.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)))

# Вспомогательные функции

def get_available_statuses(user: User, request: Request) -> list:
    """Получение доступных статусов в зависимости от роли пользователя и текущего статуса"""
    available_statuses = []
    
    # Проверяем роли пользователя
    user_roles = user.roles if user.roles else []
    
    current_status = request.status
    
    # Менеджеры могут изменять статусы
    if ROLE_MANAGER in user_roles:
        if current_status == REQUEST_STATUS_NEW:
            available_statuses.extend([REQUEST_STATUS_IN_PROGRESS, REQUEST_STATUS_CLARIFICATION])
        elif current_status == REQUEST_STATUS_IN_PROGRESS:
            available_statuses.extend([REQUEST_STATUS_CLARIFICATION, REQUEST_STATUS_EXECUTED])
        elif current_status == REQUEST_STATUS_PURCHASE:
            available_statuses.append(REQUEST_STATUS_IN_PROGRESS)
        elif current_status == REQUEST_STATUS_CLARIFICATION:
            available_statuses.append(REQUEST_STATUS_IN_PROGRESS)
        elif current_status == REQUEST_STATUS_EXECUTED:
            available_statuses.append(REQUEST_STATUS_APPROVED)
        elif current_status == REQUEST_STATUS_COMPLETED:
            available_statuses.append(REQUEST_STATUS_APPROVED)

    # Исполнители могут изменять статусы своих заявок
    elif ROLE_EXECUTOR in user_roles and request.executor_id == user.id:
        if current_status == REQUEST_STATUS_IN_PROGRESS:
            available_statuses.extend([REQUEST_STATUS_PURCHASE, REQUEST_STATUS_CLARIFICATION, REQUEST_STATUS_EXECUTED])
        elif current_status == REQUEST_STATUS_PURCHASE:
            available_statuses.append(REQUEST_STATUS_IN_PROGRESS)

    # Заявители могут принимать выполненные заявки
    elif ROLE_APPLICANT in user_roles and request.user_id == user.id:
        if current_status == REQUEST_STATUS_EXECUTED:
            available_statuses.append(REQUEST_STATUS_APPROVED)
        elif current_status == REQUEST_STATUS_COMPLETED:
            available_statuses.append(REQUEST_STATUS_APPROVED)
    
    return available_statuses

def get_comment_prompt(status: str, language: str = "ru") -> str:
    """Получение промпта для комментария в зависимости от статуса"""
    prompts = {
        REQUEST_STATUS_PURCHASE: get_text("request_status_mgmt.handlers.prompt_purchase", language=language),
        REQUEST_STATUS_CLARIFICATION: get_text("request_status_mgmt.handlers.prompt_clarification", language=language),
        REQUEST_STATUS_EXECUTED: get_text("request_status_mgmt.handlers.prompt_executed", language=language),
    }

    return prompts.get(status, get_text("request_status_mgmt.handlers.prompt_default", language=language))

async def show_status_confirmation(callback_or_message, state: FSMContext, db: Session, new_status: str, comment: str = None):
    """Показ подтверждения изменения статуса"""
    try:
        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")
        current_status = data.get("current_status")
        
        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            lang_fallback = callback_or_message.from_user.language_code or "ru" if hasattr(callback_or_message, 'from_user') else "ru"
            not_found_text = get_text("request_status_mgmt.handlers.request_not_found", language=lang_fallback)
            if hasattr(callback_or_message, 'edit_text'):
                await callback_or_message.answer(not_found_text, show_alert=True)
            else:
                await callback_or_message.answer(not_found_text)
            return
        
        # Формируем текст подтверждения
        lang = get_language_from_event(callback_or_message, db)
        confirmation_text = get_text("request_status_mgmt.handlers.confirmation", language=lang).format(
            request_number=request_number,
            current_status=get_status_display(current_status, language=lang),
            new_status=get_status_display(new_status, language=lang),
            category=request.category,
            address=request.address
        )
        
        if comment:
            confirmation_text += get_text("request_status_mgmt.handlers.confirmation_comment", language=lang).format(comment=comment)
        
        # Показываем клавиатуру подтверждения
        keyboard = get_status_confirmation_keyboard(lang)
        
        if hasattr(callback_or_message, 'edit_text'):
            await callback_or_message.edit_text(confirmation_text, reply_markup=keyboard)
        else:
            await callback_or_message.answer(confirmation_text, reply_markup=keyboard)
        
        # Переходим в состояние подтверждения
        await state.set_state(RequestStatusStates.waiting_for_confirmation)
        
    except Exception as e:
        logger.error(f"Ошибка показа подтверждения: {e}")
        lang_err = callback_or_message.from_user.language_code or "ru" if hasattr(callback_or_message, 'from_user') else "ru"
        err_text = get_text("request_status_mgmt.handlers.error_occurred", language=lang_err).format(error=str(e))
        if hasattr(callback_or_message, 'edit_text'):
            await callback_or_message.answer(err_text, show_alert=True)
        else:
            await callback_or_message.answer(err_text)
