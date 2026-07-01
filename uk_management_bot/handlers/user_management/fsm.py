"""FSM-обработка комментариев модерации и навигация."""
import logging

from aiogram import F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session

from uk_management_bot.services.user_management_service import UserManagementService
from uk_management_bot.services.auth_service import AuthService
from uk_management_bot.keyboards.user_management import (
    get_user_management_main_keyboard,
    get_user_actions_keyboard,
)
from uk_management_bot.keyboards.base import get_main_keyboard
from uk_management_bot.states.user_management import UserManagementStates
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.auth_helpers import has_admin_access
from uk_management_bot.database.models.user import User

from ._router import router

logger = logging.getLogger(__name__)


# ═══ ОБРАБОТКА КОММЕНТАРИЕВ ═══

@router.message(UserManagementStates.waiting_for_approval_comment)
async def process_approval_comment(message: Message, state: FSMContext, db: Session, language: str = "ru"):
    """Обработать комментарий для одобрения"""
    lang = language
    
    try:
        data = await state.get_data()
        target_user_id = data.get('target_user_id')
        manager_id = data.get('manager_id')
        comment = message.text
        
        # Выполняем одобрение
        auth_service = AuthService(db)
        success = auth_service.approve_user(target_user_id, manager_id, comment)
        
        if success:
            # Получаем обновленную информацию о пользователе
            user_mgmt_service = UserManagementService(db)
            target_user = user_mgmt_service.get_user_by_id(target_user_id)
            
            user_name = target_user.first_name or target_user.username or str(target_user.telegram_id)
            
            await message.answer(
                get_text('moderation.user_approved_successfully', language=lang).format(
                    user_name=user_name
                )
            )
            
            # Отправляем обновленное главное меню пользователю
            try:

                # Создаем клавиатуру с кнопкой перезапуска
                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

                # Определяем язык целевого пользователя
                target_lang = target_user.language or 'ru'

                restart_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=get_text('user_mgmt.handlers.restart_bot_btn', language=target_lang), callback_data="restart_bot")]
                ])

                # Отправляем уведомление об одобрении с кнопкой перезапуска
                await message.bot.send_message(
                    chat_id=target_user.telegram_id,
                    text=get_text('user_mgmt.handlers.application_approved_restart', language=target_lang),
                    reply_markup=restart_keyboard
                )

            except Exception as e:
                logger.error(f"Ошибка отправки обновленного меню пользователю {target_user.telegram_id}: {e}")
            
            # Показываем детали пользователя
            user_info = user_mgmt_service.format_user_info(target_user, lang, detailed=True)
            await message.answer(
                user_info,
                reply_markup=get_user_actions_keyboard(target_user, lang)
            )
        else:
            await message.answer(
                get_text('moderation.operation_failed', language=lang)
            )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка обработки комментария одобрения: {e}")
        await message.answer(
            get_text('errors.unknown_error', language=lang)
        )
        await state.clear()


@router.message(UserManagementStates.waiting_for_block_reason)
async def process_block_reason(message: Message, state: FSMContext, db: Session, language: str = "ru"):
    """Обработать причину блокировки"""
    lang = language
    
    try:
        data = await state.get_data()
        target_user_id = data.get('target_user_id')
        manager_id = data.get('manager_id')
        reason = message.text
        
        # Выполняем блокировку
        auth_service = AuthService(db)
        success = auth_service.block_user(target_user_id, manager_id, reason)
        
        if success:
            user_mgmt_service = UserManagementService(db)
            target_user = user_mgmt_service.get_user_by_id(target_user_id)
            
            user_name = target_user.first_name or target_user.username or str(target_user.telegram_id)
            
            await message.answer(
                get_text('moderation.user_blocked_successfully', language=lang).format(
                    user_name=user_name
                )
            )
            
            # Показываем обновленные детали пользователя
            user_info = user_mgmt_service.format_user_info(target_user, lang, detailed=True)
            await message.answer(
                user_info,
                reply_markup=get_user_actions_keyboard(target_user, lang)
            )
        else:
            await message.answer(
                get_text('moderation.operation_failed', language=lang)
            )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка обработки причины блокировки: {e}")
        await message.answer(
            get_text('errors.unknown_error', language=lang)
        )
        await state.clear()


@router.message(UserManagementStates.waiting_for_unblock_comment)
async def process_unblock_comment(message: Message, state: FSMContext, db: Session, language: str = "ru"):
    """Обработать комментарий для разблокировки"""
    lang = language
    
    try:
        data = await state.get_data()
        target_user_id = data.get('target_user_id')
        manager_id = data.get('manager_id')
        comment = message.text
        
        # Выполняем разблокировку
        auth_service = AuthService(db)
        success = auth_service.unblock_user(target_user_id, manager_id, comment)
        
        if success:
            user_mgmt_service = UserManagementService(db)
            target_user = user_mgmt_service.get_user_by_id(target_user_id)
            
            user_name = target_user.first_name or target_user.username or str(target_user.telegram_id)
            
            await message.answer(
                get_text('moderation.user_unblocked_successfully', language=lang).format(
                    user_name=user_name
                )
            )
            
            # Показываем обновленные детали пользователя
            user_info = user_mgmt_service.format_user_info(target_user, lang, detailed=True)
            await message.answer(
                user_info,
                reply_markup=get_user_actions_keyboard(target_user, lang)
            )
        else:
            await message.answer(
                get_text('moderation.operation_failed', language=lang)
            )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка обработки комментария разблокировки: {e}")
        await message.answer(
            get_text('errors.unknown_error', language=lang)
        )
        await state.clear()


@router.message(UserManagementStates.waiting_for_delete_reason)
async def process_delete_reason(message: Message, state: FSMContext, db: Session, language: str = "ru"):
    """Обработать причину удаления пользователя"""
    lang = language
    
    try:
        data = await state.get_data()
        target_user_id = data.get('target_user_id')
        manager_id = data.get('manager_id')
        reason = message.text
        
        # Выполняем удаление
        auth_service = AuthService(db)
        success = auth_service.delete_user(target_user_id, manager_id, reason)
        
        if success:
            await message.answer(
                get_text('moderation.user_deleted_successfully', language=lang)
            )
            
            try:
                # Возвращаемся к панели управления пользователями
                user_mgmt_service = UserManagementService(db)
                stats = user_mgmt_service.get_user_stats()
                
                await message.answer(
                    get_text('user_management.main_title', language=lang),
                    reply_markup=get_user_management_main_keyboard(stats, lang)
                )
            except Exception as e:
                logger.error(f"Ошибка при возврате к панели управления пользователями после удаления: {e}")
                await message.answer(
                    get_text('moderation.user_deleted_successfully', language=lang) +
                    "\n\n" + get_text('user_mgmt.handlers.error_returning_to_panel', language=lang)
                )
        else:
            await message.answer(
                get_text('moderation.operation_failed', language=lang)
            )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка обработки причины удаления: {e}")
        await message.answer(
            get_text('errors.unknown_error', language=lang)
        )
        await state.clear()


@router.message(UserManagementStates.waiting_for_document_request)
async def process_document_request(message: Message, state: FSMContext, db: Session, 
                                 roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработать запрос дополнительных документов"""
    lang = language
    
    logger.info("🔍 PROCESS_DOCUMENT_REQUEST: Начало обработки запроса документов")
    logger.info(f"🔍 PROCESS_DOCUMENT_REQUEST: Пользователь: {message.from_user.id}, Текст: {message.text}")
    
    # Проверяем права доступа через утилитарную функцию
    has_access = has_admin_access(roles=roles, user=user)
    logger.info(f"🔍 PROCESS_DOCUMENT_REQUEST: Права доступа: {has_access}")
    
    if not has_access:
        await message.answer(
            get_text('errors.permission_denied', language=lang),
            reply_markup=get_main_keyboard(lang)
        )
        await state.clear()
        return
    
    try:
        data = await state.get_data()
        logger.info(f"🔍 PROCESS_DOCUMENT_REQUEST: Данные состояния: {data}")
        
        target_user_id = data.get('target_user_id')
        manager_id = data.get('manager_id')
        request_text = message.text
        action = data.get('action', 'request_documents')
        
        logger.info(f"🔍 PROCESS_DOCUMENT_REQUEST: target_user_id={target_user_id}, manager_id={manager_id}, action={action}")
        
        if action == 'request_specific_document':
            # Запрос конкретного типа документа
            document_type = data.get('document_type')
            logger.info(f"🔍 PROCESS_DOCUMENT_REQUEST: Запрос конкретного документа типа: {document_type}")
            
            from uk_management_bot.services.user_verification_service import UserVerificationService
            user_verification_service = UserVerificationService(db)
            success = user_verification_service.request_specific_document(target_user_id, manager_id, document_type, request_text)
            logger.info(f"🔍 PROCESS_DOCUMENT_REQUEST: Результат запроса конкретного документа: {success}")
        elif action == 'request_multiple_documents':
            # Запрос множественных документов
            selected_docs = data.get('selected_documents', [])
            logger.info(f"🔍 PROCESS_DOCUMENT_REQUEST: Запрос множественных документов: {selected_docs}")
            
            from uk_management_bot.services.user_verification_service import UserVerificationService
            user_verification_service = UserVerificationService(db)
            success = user_verification_service.request_multiple_documents(target_user_id, manager_id, selected_docs, request_text)
            logger.info(f"🔍 PROCESS_DOCUMENT_REQUEST: Результат запроса множественных документов: {success}")
        else:
            # Общий запрос документов (для обратной совместимости)
            logger.info("🔍 PROCESS_DOCUMENT_REQUEST: Общий запрос документов")
            from uk_management_bot.services.user_verification_service import UserVerificationService
            user_verification_service = UserVerificationService(db)
            success = user_verification_service.request_additional_documents(target_user_id, manager_id, request_text)
            logger.info(f"🔍 PROCESS_DOCUMENT_REQUEST: Результат общего запроса: {success}")
        
        if success:
            # Отправляем уведомление пользователю
            from uk_management_bot.services.notification_service import async_notify_document_request
            target_user = db.query(User).filter(User.id == target_user_id).first()
            
            if target_user:
                # Получаем бота из контекста сообщения
                bot = message.bot
                
                if action == 'request_specific_document':
                    document_type = data.get('document_type')
                    await async_notify_document_request(bot, db, target_user, request_text, document_type)
                elif action == 'request_multiple_documents':
                    selected_docs = data.get('selected_documents', [])
                    # Для множественных документов передаем список
                    from uk_management_bot.services.notification_service import async_notify_multiple_documents_request
                    await async_notify_multiple_documents_request(bot, db, target_user, request_text, selected_docs)
                else:
                    await async_notify_document_request(bot, db, target_user, request_text)
            
            await message.answer(
                get_text('moderation.document_request_sent', language=lang)
            )
        else:
            await message.answer(
                get_text('moderation.operation_failed', language=lang)
            )
            await state.clear()
            return
        
        # Возвращаемся к деталям пользователя
        user_mgmt_service = UserManagementService(db)
        target_user = user_mgmt_service.get_user_by_id(target_user_id)
        
        if target_user:
            user_info = user_mgmt_service.format_user_info(target_user, lang, detailed=True)
            await message.answer(
                user_info,
                reply_markup=get_user_actions_keyboard(target_user, lang)
            )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка обработки запроса документов: {e}")
        await message.answer(
            get_text('errors.unknown_error', language=lang)
        )
        await state.clear()


# ═══ ОТМЕНА ОПЕРАЦИЙ ═══

@router.callback_query(F.data == "user_mgmt_cancel")
async def cancel_user_management_operation(callback: CallbackQuery, state: FSMContext, db: Session, 
                                         roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Отменить текущую операцию управления пользователями"""
    lang = language
    
    try:
        await state.clear()
        
        # Возвращаемся к главному меню панели управления
        user_mgmt_service = UserManagementService(db)
        stats = user_mgmt_service.get_user_stats()
        
        await callback.message.edit_text(
            get_text('user_management.main_title', language=lang),
            reply_markup=get_user_management_main_keyboard(stats, lang)
        )
        
        await callback.answer(
            get_text('buttons.operation_cancelled', language=lang)
        )
        
    except Exception as e:
        logger.error(f"Ошибка отмены операции: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ ЗАГЛУШКИ ДЛЯ НЕАКТИВНЫХ КНОПОК ═══

@router.callback_query(F.data == "user_mgmt_nop")
async def user_management_nop(callback: CallbackQuery, language: str = "ru"):
    """Заглушка для неактивных кнопок"""
    await callback.answer()


# ═══ НАВИГАЦИЯ ═══

@router.callback_query(F.data == "user_mgmt_back_to_list")
async def back_to_user_list(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru"):
    """Вернуться к списку пользователей"""
    lang = language
    
    try:
        # Очищаем состояние
        await state.clear()
        
        # Возвращаемся к главному меню панели управления
        user_mgmt_service = UserManagementService(db)
        stats = user_mgmt_service.get_user_stats()
        
        await callback.message.edit_text(
            get_text('user_management.main_title', language=lang),
            reply_markup=get_user_management_main_keyboard(stats, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка возврата к списку: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


