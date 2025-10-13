"""
Обработчики для системы верификации пользователей

Содержит обработчики для:
- Управления верификацией пользователей
- Запроса дополнительной информации
- Проверки документов
- Управления правами доступа
"""

import logging
from typing import Dict, Any

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session

from uk_management_bot.services.user_verification_service import UserVerificationService
from uk_management_bot.services.notification_service import NotificationService
from uk_management_bot.keyboards.user_verification import (
    get_verification_main_keyboard,
    get_user_verification_keyboard,
    get_document_verification_keyboard,
    get_access_rights_keyboard,
    get_verification_request_keyboard,
    get_cancel_keyboard
)
from uk_management_bot.states.user_verification import UserVerificationStates
from uk_management_bot.database.models.user_verification import (
    DocumentType, VerificationStatus, AccessLevel
)
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.auth_helpers import has_admin_access

logger = logging.getLogger(__name__)
router = Router()


# ═══ ГЛАВНОЕ МЕНЮ ВЕРИФИКАЦИИ ═══

@router.callback_query(F.data == "user_verification_panel")
async def show_verification_panel(callback: CallbackQuery, db: Session, roles: list = None):
    """Показать панель верификации пользователей"""
    lang = callback.from_user.language_code or 'ru'
    
    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        # Получаем статистику верификации
        verification_service = UserVerificationService(db)
        stats = verification_service.get_verification_stats()
        
        # Показываем главное меню
        await callback.message.edit_text(
            get_text('verification.main_title', language=lang),
            reply_markup=get_verification_main_keyboard(stats, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка отображения панели верификации: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ УПРАВЛЕНИЕ ВЕРИФИКАЦИЕЙ ПОЛЬЗОВАТЕЛЕЙ ═══

@router.callback_query(F.data.startswith("verification_user_"))
async def show_user_verification(callback: CallbackQuery, db: Session, roles: list = None):
    """Показать информацию о верификации пользователя"""
    lang = callback.from_user.language_code or 'ru'
    user_id = int(callback.data.split("_")[2])
    
    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        from uk_management_bot.database.models.user import User
        from uk_management_bot.database.models.user_verification import UserDocument, UserVerification, AccessRights
        
        # Получаем пользователя
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return
        
        # Получаем документы пользователя
        documents = db.query(UserDocument).filter(UserDocument.user_id == user_id).all()
        
        # Получаем права доступа
        access_rights = db.query(AccessRights).filter(
            AccessRights.user_id == user_id,
            AccessRights.is_active == True
        ).all()
        
        # Формируем информацию о пользователе
        user_info = f"""
👤 **Информация о пользователе**

📝 **Основные данные:**
• Имя: {user.first_name or 'Не указано'}
• Фамилия: {user.last_name or 'Не указано'}
• Username: @{user.username or 'Не указано'}
• Телефон: {user.phone or 'Не указано'}

📍 **Адреса:**"""

        # ОБНОВЛЕНО: Используем новую систему квартир
        if user.user_apartments:
            approved_apartments = [ua for ua in user.user_apartments if ua.status == 'approved']
            if approved_apartments:
                user_info += "\n"
                for ua in approved_apartments:
                    apartment = ua.apartment
                    primary_marker = " ⭐" if ua.is_primary else ""
                    owner_marker = " (Владелец)" if ua.is_owner else ""
                    address = apartment.full_address if hasattr(apartment, 'full_address') else f"Квартира {apartment.apartment_number}"
                    user_info += f"• {address}{primary_marker}{owner_marker}\n"
            else:
                user_info += "\n• Адреса не указаны (заявки на рассмотрении)\n"
        else:
            user_info += "\n• Адреса не указаны\n"

        user_info += """

📋 **Статус верификации:** {get_text(f'verification.status.{user.verification_status}', language=lang)}
"""
        
        if user.verification_notes:
            user_info += f"\n📝 **Комментарии:** {user.verification_notes}"
        
        # Добавляем информацию о документах
        if documents:
            user_info += f"\n\n📄 **Документы ({len(documents)}):**"
            for doc in documents:
                status_emoji = "✅" if doc.verification_status == VerificationStatus.APPROVED else "⏳" if doc.verification_status == VerificationStatus.PENDING else "❌"
                doc_type_name = get_text(f'verification.document_types.{doc.document_type.value}', language=lang)
                user_info += f"\n{status_emoji} {doc_type_name}"
        else:
            user_info += f"\n\n📄 **Документы:** Не загружены"
        
        # Добавляем информацию о правах доступа
        if access_rights:
            user_info += f"\n\n🔑 **Права доступа ({len(access_rights)}):**"
            for right in access_rights:
                user_info += f"\n• {right.access_level.value}"
                if right.apartment_number:
                    user_info += f" (кв. {right.apartment_number})"
                elif right.house_number:
                    user_info += f" (дом {right.house_number})"
                elif right.yard_name:
                    user_info += f" (двор {right.yard_name})"
        
        await callback.message.edit_text(
            user_info,
            reply_markup=get_user_verification_keyboard(user_id, lang),
            parse_mode="Markdown"
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка отображения верификации пользователя: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ ЗАПРОС ДОПОЛНИТЕЛЬНОЙ ИНФОРМАЦИИ ═══

@router.callback_query(F.data.startswith("verification_request_"))
async def request_additional_info(callback: CallbackQuery, db: Session, roles: list = None):
    """Запросить дополнительную информацию от пользователя"""
    lang = callback.from_user.language_code or 'ru'
    user_id = int(callback.data.split("_")[2])
    
    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        # Переходим в состояние запроса информации
        await callback.message.edit_text(
            get_text('verification.request_info_title', language=lang),
            reply_markup=get_verification_request_keyboard(user_id, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка запроса дополнительной информации: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )

# ═══ ПРОСМОТР ДОКУМЕНТОВ ПОЛЬЗОВАТЕЛЯ ═══

@router.callback_query(F.data.startswith("view_user_documents_"))
async def view_user_documents(callback: CallbackQuery, db: Session, roles: list = None):
    """Показать документы пользователя"""
    lang = callback.from_user.language_code or 'ru'
    user_id = int(callback.data.split("_")[3])
    
    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        from uk_management_bot.database.models.user import User
        from uk_management_bot.database.models.user_verification import UserDocument
        
        # Получаем пользователя
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return
        
        # Получаем документы пользователя
        documents = db.query(UserDocument).filter(UserDocument.user_id == user_id).order_by(UserDocument.created_at.desc()).all()
        
        if not documents:
            await callback.message.edit_text(
                f"📄 **Документы пользователя {user.first_name or user.username or 'Неизвестный'}**\n\n"
                f"Документы не загружены.",
                reply_markup=get_cancel_keyboard(lang),
                parse_mode="Markdown"
            )
            await callback.answer()
            return
        
        # Формируем список документов
        documents_text = f"📄 **Документы пользователя {user.first_name or user.username or 'Неизвестный'}**\n\n"
        
        for i, doc in enumerate(documents, 1):
            status_emoji = "✅" if doc.verification_status == VerificationStatus.APPROVED else "⏳" if doc.verification_status == VerificationStatus.PENDING else "❌"
            doc_type_name = get_text(f'verification.document_types.{doc.document_type.value}', language=lang)
            
            documents_text += f"{i}. {status_emoji} **{doc_type_name}**\n"
            documents_text += f"   📁 Файл: {doc.file_name or 'Без названия'}\n"
            if doc.file_size:
                documents_text += f"   📏 Размер: {doc.file_size // 1024} KB\n"
            documents_text += f"   📅 Загружен: {doc.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            
            if doc.verification_notes:
                documents_text += f"   📝 Комментарий: {doc.verification_notes}\n"
            
            documents_text += "\n"
        
        # Добавляем кнопки для управления документами
        from uk_management_bot.keyboards.user_verification import get_document_management_keyboard
        keyboard = get_document_management_keyboard(user_id, lang)
        
        await callback.message.edit_text(
            documents_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка просмотра документов пользователя: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )

@router.callback_query(F.data.startswith("download_document_"))
async def download_user_document(callback: CallbackQuery, db: Session, roles: list = None):
    """Скачать документ пользователя"""
    lang = callback.from_user.language_code or 'ru'
    document_id = int(callback.data.split("_")[2])
    
    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        from uk_management_bot.database.models.user_verification import UserDocument
        
        # Получаем документ
        document = db.query(UserDocument).filter(UserDocument.id == document_id).first()
        if not document:
            await callback.answer(
                "Документ не найден",
                show_alert=True
            )
            return
        
        # Отправляем файл
        from aiogram import Bot
        from uk_management_bot.config.settings import settings
        
        bot = Bot(token=settings.BOT_TOKEN)
        
        try:
            caption = (f"📄 {get_text(f'verification.document_types.{document.document_type.value}', language=lang)}\n"
                      f"📅 Загружен: {document.created_at.strftime('%d.%m.%Y %H:%M')}")

            # Пробуем отправить как документ, если не получится - как фото
            try:
                await bot.send_document(
                    chat_id=callback.from_user.id,
                    document=document.file_id,
                    caption=caption
                )
                await callback.answer("Документ отправлен в личные сообщения")
            except Exception as doc_error:
                # Если ошибка "can't use file of type Photo", отправляем как фото
                if "can't use file of type Photo" in str(doc_error):
                    logger.info(f"Файл {document.file_id} является фото, отправляем как photo")
                    await bot.send_photo(
                        chat_id=callback.from_user.id,
                        photo=document.file_id,
                        caption=caption
                    )
                    await callback.answer("Документ отправлен в личные сообщения")
                else:
                    raise  # Пробрасываем другие ошибки
        except Exception as e:
            logger.error(f"Ошибка отправки документа: {e}")
            await callback.answer("Ошибка отправки документа", show_alert=True)
        finally:
            await bot.session.close()
        
    except Exception as e:
        logger.error(f"Ошибка скачивания документа: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("request_info_"))
async def select_info_type(callback: CallbackQuery, state: FSMContext, db: Session, roles: list = None):
    """Выбрать тип запрашиваемой информации"""
    lang = callback.from_user.language_code or 'ru'
    parts = callback.data.split("_")
    user_id = int(parts[2])
    info_type = parts[3]
    
    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        # Сохраняем данные в состоянии
        await state.update_data(
            target_user_id=user_id,
            info_type=info_type
        )
        
        # Переходим в состояние ввода комментария
        await state.set_state(UserVerificationStates.enter_request_comment)
        
        await callback.message.edit_text(
            get_text('verification.enter_request_comment', language=lang),
            reply_markup=get_cancel_keyboard(lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка выбора типа информации: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.message(UserVerificationStates.enter_request_comment)
async def process_request_comment(message: Message, state: FSMContext, db: Session, roles: list = None):
    """Обработать комментарий к запросу информации"""
    lang = message.from_user.language_code or 'ru'
    comment = message.text
    
    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await message.answer(get_text('errors.permission_denied', language=lang))
        return
    
    try:
        # Получаем данные из состояния
        data = await state.get_data()
        user_id = data.get('target_user_id')
        info_type = data.get('info_type')
        
        # Создаем запрос верификации
        verification_service = UserVerificationService(db)
        requested_info = {
            'type': info_type,
            'comment': comment
        }
        
        verification = verification_service.create_verification_request(
            user_id=user_id,
            admin_id=message.from_user.id,
            requested_info=requested_info
        )
        
        # Отправляем уведомление пользователю
        notification_service = NotificationService(db)
        await notification_service.send_verification_request_notification(user_id, info_type, comment)
        
        # Очищаем состояние
        await state.clear()
        
        await message.answer(
            get_text('verification.request_sent_successfully', language=lang),
            reply_markup=get_verification_main_keyboard({}, lang)
        )
        
    except Exception as e:
        logger.error(f"Ошибка обработки комментария запроса: {e}")
        await message.answer(get_text('errors.unknown_error', language=lang))


# ═══ УПРАВЛЕНИЕ ДОКУМЕНТАМИ ═══

@router.callback_query(F.data.startswith("document_verify_"))
async def verify_document(callback: CallbackQuery, db: Session, roles: list = None):
    """Проверить документ пользователя"""
    lang = callback.from_user.language_code or 'ru'
    document_id = int(callback.data.split("_")[2])
    
    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        from uk_management_bot.database.models.user_verification import UserDocument
        
        # Получаем документ
        document = db.query(UserDocument).filter(UserDocument.id == document_id).first()
        if not document:
            await callback.answer(
                get_text('errors.document_not_found', language=lang),
                show_alert=True
            )
            return
        
        # Показываем информацию о документе
        document_info = f"""
📄 **Информация о документе**

📋 **Тип:** {document.document_type.value}
📅 **Загружен:** {document.created_at.strftime('%d.%m.%Y %H:%M')}
📊 **Размер:** {document.file_size or 'Неизвестно'} байт
📝 **Статус:** {get_text(f'verification.document_status.{document.verification_status.value}', language=lang)}
"""
        
        if document.verification_notes:
            document_info += f"\n📝 **Комментарии:** {document.verification_notes}"
        
        await callback.message.edit_text(
            document_info,
            reply_markup=get_document_verification_keyboard(document_id, lang),
            parse_mode="Markdown"
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка проверки документа: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("document_approve_"))
async def approve_document(callback: CallbackQuery, db: Session, roles: list = None):
    """Одобрить документ"""
    lang = callback.from_user.language_code or 'ru'
    document_id = int(callback.data.split("_")[2])
    
    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        verification_service = UserVerificationService(db)
        success = verification_service.verify_document(
            document_id=document_id,
            admin_id=callback.from_user.id,
            status=VerificationStatus.APPROVED
        )
        
        if success:
            await callback.answer(
                get_text('verification.document_approved', language=lang),
                show_alert=True
            )
        else:
            await callback.answer(
                get_text('errors.operation_failed', language=lang),
                show_alert=True
            )
        
    except Exception as e:
        logger.error(f"Ошибка одобрения документа: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("document_reject_"))
async def reject_document(callback: CallbackQuery, db: Session, roles: list = None):
    """Отклонить документ"""
    lang = callback.from_user.language_code or 'ru'
    document_id = int(callback.data.split("_")[2])
    
    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        verification_service = UserVerificationService(db)
        success = verification_service.verify_document(
            document_id=document_id,
            admin_id=callback.from_user.id,
            status=VerificationStatus.REJECTED,
            notes="Документ отклонен администратором"
        )
        
        if success:
            await callback.answer(
                get_text('verification.document_rejected', language=lang),
                show_alert=True
            )
        else:
            await callback.answer(
                get_text('errors.operation_failed', language=lang),
                show_alert=True
            )
        
    except Exception as e:
        logger.error(f"Ошибка отклонения документа: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ УПРАВЛЕНИЕ ПРАВАМИ ДОСТУПА ═══

@router.callback_query(F.data.startswith("access_rights_"))
async def manage_access_rights(callback: CallbackQuery, db: Session, roles: list = None):
    """Управление правами доступа пользователя"""
    lang = callback.from_user.language_code or 'ru'
    user_id = int(callback.data.split("_")[2])
    
    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        from uk_management_bot.database.models.user import User
        from uk_management_bot.database.models.user_verification import AccessRights
        
        # Получаем пользователя
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return
        
        # Получаем текущие права доступа
        current_rights = db.query(AccessRights).filter(
            AccessRights.user_id == user_id,
            AccessRights.is_active == True
        ).all()
        
        # Формируем информацию о правах доступа
        rights_info = f"""
🔑 **Права доступа пользователя**

👤 **Пользователь:** {user.first_name} {user.last_name or ''}

📋 **Текущие права ({len(current_rights)}):**
"""
        
        if current_rights:
            for right in current_rights:
                rights_info += f"• {right.access_level.value}"
                if right.apartment_number:
                    rights_info += f" (кв. {right.apartment_number})"
                elif right.house_number:
                    rights_info += f" (дом {right.house_number})"
                elif right.yard_name:
                    rights_info += f" (двор {right.yard_name})"
                rights_info += "\n"
        else:
            rights_info += "• Права доступа не назначены\n"
        
        await callback.message.edit_text(
            rights_info,
            reply_markup=get_access_rights_keyboard(user_id, lang),
            parse_mode="Markdown"
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка управления правами доступа: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ ОДОБРЕНИЕ/ОТКЛОНЕНИЕ ВЕРИФИКАЦИИ ═══

@router.callback_query(F.data.startswith("verify_approve_"))
async def approve_user_verification(callback: CallbackQuery, db: Session, roles: list = None):
    """Одобрить верификацию пользователя"""
    lang = callback.from_user.language_code or 'ru'
    user_id = int(callback.data.split("_")[2])
    
    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        verification_service = UserVerificationService(db)
        success = await verification_service.approve_verification(
            user_id=user_id,
            admin_id=callback.from_user.id
        )
        
        if success:
            # Отправляем уведомление пользователю
            notification_service = NotificationService(db)
            await notification_service.send_verification_approved_notification(user_id)
            
            # Отправляем обновленное главное меню пользователю
            try:
                from aiogram import Bot
                from uk_management_bot.config.settings import settings
                from uk_management_bot.keyboards.base import get_main_keyboard_for_role
                from uk_management_bot.database.models.user import User
                
                # Получаем пользователя
                target_user = db.query(User).filter(User.id == user_id).first()
                if target_user:
                    bot = Bot(token=settings.BOT_TOKEN)
                    
                    # Получаем роли пользователя
                    user_roles = []
                    if target_user.roles:
                        try:
                            import json
                            user_roles = json.loads(target_user.roles) if isinstance(target_user.roles, str) else target_user.roles
                        except:
                            user_roles = ["applicant"]
                    else:
                        user_roles = ["applicant"]
                    
                    # Создаем клавиатуру с кнопкой перезапуска
                    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                    restart_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔄 Перезапустить бота", callback_data="restart_bot")]
                    ])
                    
                    # Отправляем уведомление об одобрении с кнопкой перезапуска
                    await bot.send_message(
                        chat_id=target_user.telegram_id,
                        text="✅ Ваша заявка одобрена! Нажмите кнопку ниже для перезапуска бота.",
                        reply_markup=restart_keyboard
                    )
                    
                    await bot.session.close()
                    
            except Exception as e:
                logger.error(f"Ошибка отправки обновленного меню пользователю {user_id}: {e}")
            
            await callback.answer(
                get_text('verification.user_approved', language=lang),
                show_alert=True
            )
        else:
            await callback.answer(
                get_text('errors.operation_failed', language=lang),
                show_alert=True
            )
        
    except Exception as e:
        logger.error(f"Ошибка одобрения верификации: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("verify_reject_"))
async def reject_user_verification(callback: CallbackQuery, db: Session, roles: list = None):
    """Отклонить верификацию пользователя"""
    lang = callback.from_user.language_code or 'ru'
    user_id = int(callback.data.split("_")[2])
    
    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        verification_service = UserVerificationService(db)
        success = verification_service.reject_verification(
            user_id=user_id,
            admin_id=callback.from_user.id,
            notes="Верификация отклонена администратором"
        )
        
        if success:
            # Отправляем уведомление пользователю
            notification_service = NotificationService(db)
            await notification_service.send_verification_rejected_notification(user_id)
            
            await callback.answer(
                get_text('verification.user_rejected', language=lang),
                show_alert=True
            )
        else:
            await callback.answer(
                get_text('errors.operation_failed', language=lang),
                show_alert=True
            )
        
    except Exception as e:
        logger.error(f"Ошибка отклонения верификации: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )
