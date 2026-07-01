"""Действия модерации (approve/block/unblock/delete) и работа с документами."""
import logging

from aiogram import F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session

from uk_management_bot.services.user_management_service import UserManagementService
from uk_management_bot.keyboards.user_management import (
    get_user_management_main_keyboard,
    get_user_actions_keyboard,
    get_cancel_keyboard,
)
from uk_management_bot.states.user_management import UserManagementStates
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.auth_helpers import has_admin_access
from uk_management_bot.database.models.user import User

from ._router import router

logger = logging.getLogger(__name__)


# ═══ ДЕЙСТВИЯ МОДЕРАЦИИ ═══

@router.callback_query(F.data.startswith("user_action_approve_"))
async def handle_approve_user(callback: CallbackQuery, state: FSMContext, db: Session, 
                             roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработать одобрение пользователя"""
    lang = language
    
    # Проверяем права доступа через утилитарную функцию
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        # Получаем ID целевого пользователя
        target_user_id = int(callback.data.split('_')[-1])
        
        # Получаем внутренний ID менеджера из базы данных
        manager = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not manager:
            await callback.answer(get_text('user_mgmt.handlers.manager_not_found', language=lang), show_alert=True)
            return
            
        # Сохраняем данные в состоянии FSM
        await state.update_data({
            'action': 'approve',
            'target_user_id': target_user_id,
            'manager_id': manager.id  # Используем внутренний ID из базы данных
        })
        
        await state.set_state(UserManagementStates.waiting_for_approval_comment)
        
        await callback.message.edit_text(
            get_text('moderation.enter_approval_comment', language=lang),
            reply_markup=get_cancel_keyboard(lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка обработки одобрения пользователя: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("user_action_block_"))
async def handle_block_user(callback: CallbackQuery, state: FSMContext, db: Session, 
                           roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработать блокировку пользователя"""
    lang = language
    
    # Проверяем права доступа через утилитарную функцию
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        target_user_id = int(callback.data.split('_')[-1])
        
        # Получаем внутренний ID менеджера из базы данных
        manager = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not manager:
            await callback.answer(get_text('user_mgmt.handlers.manager_not_found', language=lang), show_alert=True)
            return
            
        await state.update_data({
            'action': 'block',
            'target_user_id': target_user_id,
            'manager_id': manager.id  # Используем внутренний ID из базы данных
        })
        
        await state.set_state(UserManagementStates.waiting_for_block_reason)
        
        await callback.message.edit_text(
            get_text('moderation.enter_block_reason', language=lang),
            reply_markup=get_cancel_keyboard(lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка обработки блокировки пользователя: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("user_action_unblock_"))
async def handle_unblock_user(callback: CallbackQuery, state: FSMContext, db: Session, 
                             roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработать разблокировку пользователя"""
    lang = language
    
    # Проверяем права доступа через утилитарную функцию
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        target_user_id = int(callback.data.split('_')[-1])
        
        # Получаем внутренний ID менеджера из базы данных
        manager = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not manager:
            await callback.answer(get_text('user_mgmt.handlers.manager_not_found', language=lang), show_alert=True)
            return
            
        await state.update_data({
            'action': 'unblock',
            'target_user_id': target_user_id,
            'manager_id': manager.id  # Используем внутренний ID из базы данных
        })
        
        await state.set_state(UserManagementStates.waiting_for_unblock_comment)
        
        await callback.message.edit_text(
            get_text('moderation.enter_unblock_comment', language=lang),
            reply_markup=get_cancel_keyboard(lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка обработки разблокировки пользователя: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("user_action_delete_"))
async def handle_delete_user(callback: CallbackQuery, state: FSMContext, db: Session, 
                           roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработать удаление пользователя"""
    lang = language
    
    # Проверяем права доступа через утилитарную функцию
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        target_user_id = int(callback.data.split('_')[-1])
        
        # Получаем внутренний ID менеджера из базы данных
        manager = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not manager:
            await callback.answer(get_text('user_mgmt.handlers.manager_not_found', language=lang), show_alert=True)
            return
            
        await state.update_data({
            'action': 'delete',
            'target_user_id': target_user_id,
            'manager_id': manager.id  # Используем внутренний ID из базы данных
        })
        
        await state.set_state(UserManagementStates.waiting_for_delete_reason)
        
        await callback.message.edit_text(
            get_text('moderation.enter_delete_reason', language=lang),
            reply_markup=get_cancel_keyboard(lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка обработки удаления пользователя: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("user_action_view_documents_"))
async def handle_view_user_documents(callback: CallbackQuery, db: Session, 
                                   roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать документы пользователя"""
    lang = language
    
    # Проверяем права доступа через утилитарную функцию
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        target_user_id = int(callback.data.split('_')[-1])
        
        # Получаем пользователя
        user_mgmt_service = UserManagementService(db)
        target_user = user_mgmt_service.get_user_by_id(target_user_id)
        
        if not target_user:
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return
        
        # Получаем документы пользователя
        from uk_management_bot.services.user_verification_service import UserVerificationService
        
        verification_service = UserVerificationService(db)
        documents = verification_service.get_user_documents(target_user_id)
        
        if not documents:
            unknown = get_text('user_mgmt.handlers.unknown_user', language=lang)
            await callback.message.edit_text(
                get_text('user_mgmt.handlers.documents_title', language=lang).format(name=target_user.first_name or target_user.username or unknown) + "\n\n"
                + get_text('user_mgmt.handlers.no_documents_uploaded', language=lang),
                reply_markup=get_cancel_keyboard(lang)
            )
            await callback.answer()
            return

        # Формируем список документов
        unknown = get_text('user_mgmt.handlers.unknown_user', language=lang)
        user_name = target_user.first_name or target_user.username or unknown

        documents_text = get_text('user_mgmt.handlers.documents_title', language=lang).format(name=user_name) + "\n\n"
        
        for i, doc in enumerate(documents, 1):
            from uk_management_bot.database.models.user_verification import VerificationStatus
            status_emoji = "✅" if doc.verification_status == VerificationStatus.APPROVED else "⏳" if doc.verification_status == VerificationStatus.PENDING else "❌"

            # Получаем название типа документа
            doc_type_name = get_text(f'user_mgmt.handlers.doc_type.{doc.document_type.value}', language=lang)

            file_name = doc.file_name or get_text('user_mgmt.handlers.no_title', language=lang)

            documents_text += f"{i}. {status_emoji} <b>{doc_type_name}</b>\n"
            documents_text += get_text('user_mgmt.handlers.doc_file', language=lang).format(name=file_name) + "\n"
            if doc.file_size:
                documents_text += get_text('user_mgmt.handlers.doc_size', language=lang).format(size=doc.file_size // 1024) + "\n"
            documents_text += get_text('user_mgmt.handlers.doc_uploaded', language=lang).format(date=doc.created_at.strftime('%d.%m.%Y %H:%M')) + "\n"

            if doc.verification_notes:
                documents_text += get_text('user_mgmt.handlers.doc_comment', language=lang).format(comment=doc.verification_notes) + "\n"

            documents_text += "\n"
        
        # Создаем клавиатуру с кнопками для каждого документа
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        keyboard_buttons = []
        
        # Добавляем кнопки для каждого документа
        for i, doc in enumerate(documents, 1):
            doc_type_name = get_text(f'user_mgmt.handlers.doc_type.{doc.document_type.value}', language=lang)

            keyboard_buttons.append([InlineKeyboardButton(
                text=get_text('user_mgmt.handlers.download_doc_btn', language=lang).format(doc_type=doc_type_name),
                callback_data=f"download_document_{doc.id}"
            )])
        
        # Добавляем кнопки управления
        keyboard_buttons.append([InlineKeyboardButton(
            text=get_text('user_mgmt.handlers.request_additional_docs_btn', language=lang),
            callback_data=f"request_documents_{target_user_id}"
        )])
        
        keyboard_buttons.append([InlineKeyboardButton(
            text=f"◀️ {get_text('buttons.back', language=lang)}",
            callback_data=f"user_mgmt_user_{target_user_id}"
        )])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        await callback.message.edit_text(
            documents_text,
            reply_markup=keyboard
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка просмотра документов пользователя: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )

@router.callback_query(F.data.startswith("download_document_"))
async def handle_download_document(callback: CallbackQuery, db: Session, 
                                 roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Скачать документ пользователя"""
    lang = language
    
    # Проверяем права доступа через утилитарную функцию
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        document_id = int(callback.data.split('_')[-1])
        
        # Получаем документ
        from uk_management_bot.database.models.user_verification import UserDocument
        document = db.query(UserDocument).filter(UserDocument.id == document_id).first()
        
        if not document:
            await callback.answer(
                get_text('user_mgmt.handlers.document_not_found', language=lang),
                show_alert=True
            )
            return
        
        # Отправляем файл
        bot = callback.bot

        try:
            # Получаем название типа документа
            doc_type_name = get_text(f'user_mgmt.handlers.doc_type.{document.document_type.value}', language=lang)

            caption = f"📄 {doc_type_name}\n"
            caption += get_text('user_mgmt.handlers.doc_uploaded', language=lang).format(date=document.created_at.strftime('%d.%m.%Y %H:%M')) + "\n"

            if document.file_size:
                caption += get_text('user_mgmt.handlers.doc_size', language=lang).format(size=document.file_size // 1024)

            # Определяем тип файла по file_name или пробуем отправить как фото
            try:
                # Сначала пробуем отправить как документ
                await bot.send_document(
                    chat_id=callback.from_user.id,
                    document=document.file_id,
                    caption=caption
                )
                await callback.answer(get_text('user_mgmt.handlers.document_sent_to_dm', language=lang))
            except Exception as doc_error:
                # Если ошибка "can't use file of type Photo", отправляем как фото
                if "can't use file of type Photo" in str(doc_error):
                    logger.info(f"Файл {document.file_id} является фото, отправляем как photo")
                    await bot.send_photo(
                        chat_id=callback.from_user.id,
                        photo=document.file_id,
                        caption=caption
                    )
                    await callback.answer(get_text('user_mgmt.handlers.document_sent_to_dm', language=lang))
                else:
                    raise  # Пробрасываем другие ошибки

        except Exception as e:
            logger.error(f"Ошибка отправки документа: {e}")
            await callback.answer(get_text('user_mgmt.handlers.error_sending_document', language=lang), show_alert=True)
        
    except Exception as e:
        logger.error(f"Ошибка скачивания документа: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )

@router.callback_query(F.data.startswith("user_action_request_docs_"))
async def handle_request_documents(callback: CallbackQuery, state: FSMContext, db: Session, 
                                 roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработать запрос дополнительных документов"""
    lang = language
    
    logger.info(f"🔍 HANDLE_REQUEST_DOCUMENTS: Вызван обработчик для {callback.data}")
    
    # Проверяем права доступа через утилитарную функцию
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        target_user_id = int(callback.data.split('_')[-1])
        
        # Получаем внутренний ID менеджера из базы данных
        manager = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not manager:
            await callback.answer(get_text('user_mgmt.handlers.manager_not_found', language=lang), show_alert=True)
            return
            
        await state.update_data({
            'action': 'request_documents',
            'target_user_id': target_user_id,
            'manager_id': manager.id  # Используем внутренний ID из базы данных
        })
        
        # Очищаем предыдущее состояние
        await state.clear()
        
        # Показываем меню с галочками для выбора документов
        from uk_management_bot.keyboards.user_verification import get_document_checklist_keyboard
        await callback.message.edit_text(
            get_text('moderation.select_documents_checklist', language=lang),
            reply_markup=get_document_checklist_keyboard(target_user_id, [], lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка обработки запроса документов: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# DEAD-16 (PR-8): «ВРЕМЕННО ОТКЛЮЧЕННЫЙ» handle_document_type_selection
# (61 строка комментариев) удалён — заменён обработчиками галочек ниже.


# ═══ ОБРАБОТКА ГАЛОЧЕК ДОКУМЕНТОВ ═══

@router.callback_query(F.data.startswith("check_document_"))
async def handle_check_document(callback: CallbackQuery, state: FSMContext, db: Session, 
                               roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработать выбор документа (галочка)"""
    lang = language
    
    # Проверяем права доступа
    has_access = has_admin_access(roles=roles, user=user)
    if not has_access:
        await callback.answer(get_text('errors.permission_denied', language=lang), show_alert=True)
        return
    
    try:
        # Парсим данные: check_document_{user_id}_{document_type}
        parts = callback.data.split('_')
        target_user_id = int(parts[2])
        document_type = parts[3]
        
        # Получаем текущий список выбранных документов
        data = await state.get_data()
        selected_docs = data.get('selected_documents', [])
        
        # Добавляем документ, если его нет
        if document_type not in selected_docs:
            selected_docs.append(document_type)
        
        # Обновляем состояние
        await state.update_data({
            'target_user_id': target_user_id,
            'selected_documents': selected_docs
        })
        
        # Обновляем клавиатуру
        from uk_management_bot.keyboards.user_verification import get_document_checklist_keyboard
        await callback.message.edit_reply_markup(
            reply_markup=get_document_checklist_keyboard(target_user_id, selected_docs, lang)
        )
        
        await callback.answer(get_text('user_mgmt.handlers.doc_selected', language=lang).format(doc_type=get_text(f'verification.document_types.{document_type}', language=lang)))
        
    except Exception as e:
        logger.error(f"Ошибка выбора документа: {e}")
        await callback.answer(get_text('errors.unknown_error', language=lang), show_alert=True)


@router.callback_query(F.data.startswith("uncheck_document_"))
async def handle_uncheck_document(callback: CallbackQuery, state: FSMContext, db: Session, 
                                 roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработать отмену выбора документа (убрать галочку)"""
    lang = language
    
    # Проверяем права доступа
    has_access = has_admin_access(roles=roles, user=user)
    if not has_access:
        await callback.answer(get_text('errors.permission_denied', language=lang), show_alert=True)
        return
    
    try:
        # Парсим данные: uncheck_document_{user_id}_{document_type}
        parts = callback.data.split('_')
        target_user_id = int(parts[2])
        document_type = parts[3]
        
        # Получаем текущий список выбранных документов
        data = await state.get_data()
        selected_docs = data.get('selected_documents', [])
        
        # Убираем документ, если он есть
        if document_type in selected_docs:
            selected_docs.remove(document_type)
        
        # Обновляем состояние
        await state.update_data({
            'target_user_id': target_user_id,
            'selected_documents': selected_docs
        })
        
        # Обновляем клавиатуру
        from uk_management_bot.keyboards.user_verification import get_document_checklist_keyboard
        await callback.message.edit_reply_markup(
            reply_markup=get_document_checklist_keyboard(target_user_id, selected_docs, lang)
        )
        
        await callback.answer(get_text('user_mgmt.handlers.doc_deselected', language=lang).format(doc_type=get_text(f'verification.document_types.{document_type}', language=lang)))
        
    except Exception as e:
        logger.error(f"Ошибка отмены выбора документа: {e}")
        await callback.answer(get_text('errors.unknown_error', language=lang), show_alert=True)


@router.callback_query(F.data.startswith("req_docs_"))
async def handle_request_selected_documents(callback: CallbackQuery, state: FSMContext, db: Session, 
                                           roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработать запрос выбранных документов"""
    lang = language
    
    # Проверяем права доступа
    has_access = has_admin_access(roles=roles, user=user)
    if not has_access:
        await callback.answer(get_text('errors.permission_denied', language=lang), show_alert=True)
        return
    
    try:
        # Парсим данные: req_docs_{user_id}_{doc1,doc2,doc3+2}
        parts = callback.data.split('_')
        target_user_id = int(parts[2])
        docs_str = parts[3] if len(parts) > 3 else ""
        
        # Обрабатываем формат с количеством дополнительных документов
        if '+' in docs_str:
            # Получаем полный список из состояния
            data = await state.get_data()
            selected_docs = data.get('selected_documents', [])
        else:
            selected_docs = docs_str.split(',') if docs_str else []
        
        # Получаем внутренний ID менеджера
        manager = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not manager:
            await callback.answer(get_text('user_mgmt.handlers.manager_not_found', language=lang), show_alert=True)
            return
        
        # Сохраняем данные в состоянии
        await state.update_data({
            'action': 'request_multiple_documents',
            'target_user_id': target_user_id,
            'manager_id': manager.id,
            'selected_documents': selected_docs
        })
        
        await state.set_state(UserManagementStates.waiting_for_document_request)
        
        # Формируем список названий документов
        doc_names = []
        for doc_type in selected_docs:
            doc_name = get_text(f'verification.document_types.{doc_type}', language=lang)
            doc_names.append(doc_name)
        
        doc_list = ", ".join(doc_names)
        
        await callback.message.edit_text(
            get_text('moderation.enter_document_request_multiple', language=lang).format(
                documents=doc_list
            ),
            reply_markup=get_cancel_keyboard(lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка запроса выбранных документов: {e}")
        await callback.answer(get_text('errors.unknown_error', language=lang), show_alert=True)


@router.callback_query(F.data.startswith("cancel_document_selection_"))
async def handle_cancel_document_selection(callback: CallbackQuery, state: FSMContext, db: Session,
                                         roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Отменить выбор документов"""
    lang = language
    
    logger.info(f"🔍 HANDLE_CANCEL_DOCUMENT_SELECTION: Вызван обработчик для {callback.data}")
    
    # Проверяем права доступа
    has_access = has_admin_access(roles=roles, user=user)
    if not has_access:
        await callback.answer(get_text('errors.permission_denied', language=lang), show_alert=True)
        return
    
    try:
        # Парсим данные: cancel_document_selection_{user_id}
        parts = callback.data.split('_')
        if len(parts) >= 4:
            target_user_id = int(parts[3])
        else:
            logger.error(f"Неверный формат callback_data: {callback.data}")
            await callback.answer(get_text('user_mgmt.handlers.error_invalid_format', language=lang), show_alert=True)
            return
        
        # Очищаем состояние
        await state.clear()
        
        # Возвращаемся к деталям пользователя
        user_mgmt_service = UserManagementService(db)
        target_user = user_mgmt_service.get_user_by_id(target_user_id)
        
        if target_user:
            user_info = user_mgmt_service.format_user_info(target_user, lang, detailed=True)
            await callback.message.edit_text(
                user_info,
                reply_markup=get_user_actions_keyboard(target_user, lang)
            )
        
        await callback.answer(get_text('buttons.operation_cancelled', language=lang))
        
    except Exception as e:
        logger.error(f"Ошибка отмены выбора документов: {e}")
        await callback.answer(get_text('errors.unknown_error', language=lang), show_alert=True)


@router.callback_query(F.data == "cancel_action")
async def handle_cancel_action(callback: CallbackQuery, state: FSMContext, db: Session, 
                              roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Обработать отмену действия (кнопка Отмена в клавиатурах)"""
    lang = language
    
    # Проверяем права доступа
    has_access = has_admin_access(roles=roles, user=user)
    if not has_access:
        await callback.answer(get_text('errors.permission_denied', language=lang), show_alert=True)
        return
    
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
        
        await callback.answer(get_text('buttons.operation_cancelled', language=lang))
        
    except Exception as e:
        logger.error(f"Ошибка отмены действия: {e}")
        await callback.answer(get_text('errors.unknown_error', language=lang), show_alert=True)


@router.callback_query(F.data.startswith("back_to_user_details_"))
async def handle_back_to_user_details(callback: CallbackQuery, state: FSMContext, db: Session, 
                                     roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Вернуться к деталям пользователя"""
    lang = language
    
    # Проверяем права доступа
    has_access = has_admin_access(roles=roles, user=user)
    if not has_access:
        await callback.answer(get_text('errors.permission_denied', language=lang), show_alert=True)
        return
    
    try:
        # Парсим данные: back_to_user_details_{user_id}
        parts = callback.data.split('_')
        target_user_id = int(parts[4])  # back_to_user_details_{user_id}
        
        # Очищаем состояние
        await state.clear()
        
        # Возвращаемся к деталям пользователя
        user_mgmt_service = UserManagementService(db)
        target_user = user_mgmt_service.get_user_by_id(target_user_id)
        
        if target_user:
            user_info = user_mgmt_service.format_user_info(target_user, lang, detailed=True)
            await callback.message.edit_text(
                user_info,
                reply_markup=get_user_actions_keyboard(target_user, lang)
            )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка возврата к деталям пользователя: {e}")
        await callback.answer(get_text('errors.unknown_error', language=lang), show_alert=True)


