"""
Обработчики для управления пользователями

Содержит обработчики для:
- Панели управления пользователями
- Списков и поиска пользователей
- Действий модерации
- Управления ролями и специализациями
- Интеграции с системой верификации
"""

import logging
from typing import Dict, Any

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session

from uk_management_bot.services.user_management_service import UserManagementService
from uk_management_bot.services.specialization_service import SpecializationService
from uk_management_bot.services.auth_service import AuthService
from uk_management_bot.keyboards.user_management import (
    get_user_management_main_keyboard,
    get_user_list_keyboard,
    get_user_actions_keyboard,
    get_roles_management_keyboard,
    get_specializations_selection_keyboard,
    get_cancel_keyboard,
    get_confirmation_keyboard
)
from uk_management_bot.states.user_management import UserManagementStates
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.auth_helpers import has_admin_access
from uk_management_bot.database.models.user import User

logger = logging.getLogger(__name__)
router = Router()


# ═══ ГЛАВНОЕ МЕНЮ УПРАВЛЕНИЯ ПОЛЬЗОВАТЕЛЯМИ ═══

@router.callback_query(F.data == "user_management_panel")
async def show_user_management_panel(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать панель управления пользователями"""
    lang = language
    
    # Проверяем права доступа через утилитарную функцию
    from uk_management_bot.utils.auth_helpers import has_admin_access
    
    has_access = has_admin_access(roles=roles, user=user)
    logger.debug(f"User management panel access: user_id={callback.from_user.id}, access_granted={has_access}")
    
    if not has_access:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        # Получаем статистику пользователей
        user_mgmt_service = UserManagementService(db)
        stats = user_mgmt_service.get_user_stats()
        
        # Показываем главное меню
        await callback.message.edit_text(
            get_text('user_management.main_title', language=lang),
            reply_markup=get_user_management_main_keyboard(stats, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка отображения панели управления пользователями: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data == "user_mgmt_main")
async def back_to_main_panel(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Вернуться к главному меню панели управления"""
    await show_user_management_panel(callback, db, roles, active_role, user)


@router.callback_query(F.data == "user_mgmt_stats")
async def show_user_stats(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать статистику пользователей"""
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
        user_mgmt_service = UserManagementService(db)
        stats = user_mgmt_service.get_user_stats()
        
        stats_text = user_mgmt_service.format_stats_message(stats, lang)
        
        await callback.message.edit_text(
            stats_text,
            reply_markup=get_user_management_main_keyboard(stats, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка отображения статистики пользователей: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ ИНТЕГРАЦИЯ С СИСТЕМОЙ ВЕРИФИКАЦИИ ═══

@router.callback_query(F.data == "user_verification_panel")
async def show_verification_panel(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать панель верификации пользователей"""
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
        # Импортируем сервис верификации
        from uk_management_bot.services.user_verification_service import UserVerificationService
        
        # Получаем статистику верификации
        verification_service = UserVerificationService(db)
        stats = verification_service.get_verification_stats()
        
        # Импортируем клавиатуру верификации
        from uk_management_bot.keyboards.user_verification import get_verification_main_keyboard
        
        # Показываем панель верификации
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


# ═══ ОБНОВЛЕНИЕ СТАТИСТИКИ С ВЕРИФИКАЦИЕЙ ═══

@router.callback_query(F.data == "user_mgmt_stats_with_verification")
async def show_user_stats_with_verification(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать расширенную статистику пользователей с верификацией"""
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
        # Получаем базовую статистику
        user_mgmt_service = UserManagementService(db)
        stats = user_mgmt_service.get_user_stats()
        
        # Получаем статистику верификации
        from uk_management_bot.services.user_verification_service import UserVerificationService
        verification_service = UserVerificationService(db)
        verification_stats = verification_service.get_verification_stats()
        
        # Формируем расширенную статистику
        extended_stats = get_text('user_mgmt.handlers.extended_stats', language=lang).format(
            total=stats.get('total', 0),
            pending=stats.get('pending', 0),
            approved=stats.get('approved', 0),
            blocked=stats.get('blocked', 0),
            staff=stats.get('staff', 0),
            ver_pending=verification_stats.get('pending', 0),
            ver_verified=verification_stats.get('verified', 0),
            ver_rejected=verification_stats.get('rejected', 0),
            ver_pending_docs=verification_stats.get('pending_documents', 0),
            ver_total_docs=verification_stats.get('total_documents', 0)
        )

        # Показываем расширенную статистику
        await callback.message.edit_text(
            extended_stats,
            reply_markup=get_user_management_main_keyboard(stats, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка отображения расширенной статистики: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ ОБРАБОТЧИКИ ДЛЯ УВЕДОМЛЕНИЙ О РЕГИСТРАЦИИ ═══

@router.callback_query(F.data.startswith("approve_user_"))
async def handle_approve_user_from_notification(callback: CallbackQuery, db: Session, roles: list = None, user: User = None, language: str = "ru"):
    """Одобрить пользователя из уведомления о регистрации"""
    lang = language
    logger.info(f"🔵 handle_approve_user_from_notification вызван: callback_data={callback.data}, roles={roles}")

    try:
        user_id = int(callback.data.split("_")[2])
        logger.info(f"🔵 Parsed user_id: {user_id}")
    except (IndexError, ValueError) as e:
        logger.error(f"Ошибка парсинга user_id из callback.data '{callback.data}': {e}")
        await callback.answer(get_text('user_mgmt.handlers.error_processing_request', language=lang), show_alert=True)
        return

    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return

    try:
        from uk_management_bot.database.models.user import User as UserModel
        from uk_management_bot.services.auth_service import AuthService

        # Получаем пользователя
        target_user = db.query(UserModel).filter(UserModel.id == user_id).first()

        if not target_user:
            await callback.answer(get_text('user_mgmt.handlers.user_not_found', language=lang), show_alert=True)
            return

        # Одобряем пользователя (используем sync метод с user_id)
        auth_service = AuthService(db)
        # Получаем ID текущего менеджера (из параметра user или callback)
        manager_id = user.id if user else callback.from_user.id
        success = auth_service.approve_user(user_id, manager_id, get_text('user_mgmt.handlers.approved_via_notification', language=lang))

        if success:
            await callback.answer(get_text('user_mgmt.handlers.user_approved_alert', language=lang).format(name=target_user.first_name), show_alert=True)

            # Обновляем сообщение
            await callback.message.edit_text(
                callback.message.text + get_text('user_mgmt.handlers.approved_by', language=lang).format(name=callback.from_user.first_name),
                reply_markup=None
            )

            logger.info(f"Пользователь {user_id} одобрен менеджером {callback.from_user.id}")
        else:
            await callback.answer(get_text('user_mgmt.handlers.error_approving_user', language=lang), show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка одобрения пользователя {user_id}: {e}", exc_info=True)
        await callback.answer(get_text('user_mgmt.handlers.error_occurred', language=lang), show_alert=True)


@router.callback_query(F.data.startswith("reject_user_"))
async def handle_reject_user_from_notification(callback: CallbackQuery, db: Session, roles: list = None, language: str = "ru"):
    """Отклонить пользователя из уведомления о регистрации"""
    lang = language

    try:
        user_id = int(callback.data.split("_")[2])
    except (IndexError, ValueError) as e:
        logger.error(f"Ошибка парсинга user_id из callback.data '{callback.data}': {e}")
        await callback.answer(get_text('user_mgmt.handlers.error_processing_request', language=lang), show_alert=True)
        return

    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return

    try:
        from uk_management_bot.database.models.user import User as UserModel

        # Получаем пользователя
        target_user = db.query(UserModel).filter(UserModel.id == user_id).first()

        if not target_user:
            await callback.answer(get_text('user_mgmt.handlers.user_not_found', language=lang), show_alert=True)
            return

        # Отклоняем пользователя (блокируем) - используем sync метод с user_id
        from uk_management_bot.services.auth_service import AuthService
        from uk_management_bot.database.models.user import User as UserModel

        auth_service = AuthService(db)
        # Получаем ID текущего менеджера
        manager = db.query(UserModel).filter(UserModel.telegram_id == callback.from_user.id).first()
        manager_id = manager.id if manager else callback.from_user.id

        success = auth_service.block_user(user_id, manager_id, get_text('user_mgmt.handlers.rejected_via_notification', language=lang))

        if success:
            await callback.answer(get_text('user_mgmt.handlers.user_rejected_alert', language=lang).format(name=target_user.first_name), show_alert=True)

            # Обновляем сообщение
            await callback.message.edit_text(
                callback.message.text + get_text('user_mgmt.handlers.rejected_by', language=lang).format(name=callback.from_user.first_name),
                reply_markup=None
            )

            logger.info(f"Пользователь {user_id} отклонен менеджером {callback.from_user.id}")
        else:
            await callback.answer(get_text('user_mgmt.handlers.error_rejecting_user', language=lang), show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка отклонения пользователя {user_id}: {e}", exc_info=True)
        await callback.answer(get_text('user_mgmt.handlers.error_occurred', language=lang), show_alert=True)


@router.callback_query(F.data.startswith("view_user_"))
async def handle_view_user_from_notification(callback: CallbackQuery, db: Session, roles: list = None, language: str = "ru"):
    """Просмотреть профиль пользователя из уведомления о регистрации"""
    lang = language
    logger.info(f"🔵 handle_view_user_from_notification вызван: callback_data={callback.data}, roles={roles}")

    try:
        user_id = int(callback.data.split("_")[2])
        logger.info(f"🔵 Parsed user_id: {user_id}")
    except (IndexError, ValueError) as e:
        logger.error(f"Ошибка парсинга user_id из callback.data '{callback.data}': {e}")
        await callback.answer(get_text('user_mgmt.handlers.error_processing_request', language=lang), show_alert=True)
        return

    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return

    try:
        from uk_management_bot.database.models.user import User as UserModel

        # Получаем пользователя
        target_user = db.query(UserModel).filter(UserModel.id == user_id).first()

        if not target_user:
            await callback.answer(get_text('user_mgmt.handlers.user_not_found', language=lang), show_alert=True)
            return

        # Формируем информацию о пользователе
        not_specified = get_text('user_mgmt.handlers.not_specified', language=lang)
        profile_text = get_text('user_mgmt.handlers.profile_title', language=lang) + "\n\n"
        profile_text += f"🆔 ID: {target_user.id}\n"
        profile_text += get_text('user_mgmt.handlers.profile_name', language=lang).format(name=target_user.first_name or not_specified)
        if target_user.last_name:
            profile_text += f" {target_user.last_name}"
        profile_text += "\n"

        if target_user.username:
            profile_text += f"📱 Username: @{target_user.username}\n"
        else:
            # BUG-BOT-024: показываем "Username не указан" без префикса `@`
            profile_text += f"📱 {get_text('user_mgmt.handlers.username_not_specified', language=lang)}\n"

        profile_text += f"🆔 Telegram ID: {target_user.telegram_id}\n"
        # BUG-BOT-024: локализованные значения вместо raw DB-строк
        from uk_management_bot.utils.employee_display import format_user_status, format_roles
        roles_source = target_user.roles if getattr(target_user, "roles", None) else getattr(target_user, "role", None)
        profile_text += get_text('user_mgmt.handlers.profile_role', language=lang).format(role=format_roles(roles_source, lang)) + "\n"
        profile_text += get_text('user_mgmt.handlers.profile_status', language=lang).format(status=format_user_status(target_user.status, lang)) + "\n"

        if target_user.specialization:
            profile_text += get_text('user_mgmt.handlers.profile_specialization', language=lang).format(spec=target_user.specialization) + "\n"

        if target_user.created_at:
            profile_text += get_text('user_mgmt.handlers.profile_registered', language=lang).format(date=target_user.created_at.strftime('%d.%m.%Y %H:%M')) + "\n"

        # Отправляем новое сообщение с профилем
        await callback.message.answer(profile_text, parse_mode="HTML")
        await callback.answer()

        logger.info(f"Просмотрен профиль пользователя {user_id} менеджером {callback.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка просмотра профиля пользователя {user_id}: {e}", exc_info=True)
        await callback.answer(get_text('user_mgmt.handlers.error_occurred', language=lang), show_alert=True)


# ═══ БЫСТРЫЕ ДЕЙСТВИЯ С ВЕРИФИКАЦИЕЙ ═══

@router.callback_query(F.data.startswith("quick_verify_"))
async def quick_verify_user(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Быстрая верификация пользователя"""
    lang = language
    user_id = int(callback.data.split("_")[2])
    
    # Проверяем права доступа через утилитарную функцию
    has_access = has_admin_access(roles=roles, user=user)
    
    if not has_access:
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return
    
    try:
        # Импортируем сервис верификации
        from uk_management_bot.services.user_verification_service import UserVerificationService
        from uk_management_bot.services.notification_service import NotificationService
        
        # Одобряем верификацию
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
                from uk_management_bot.keyboards.base import get_main_keyboard_for_role

                # Получаем пользователя
                target_user = db.query(User).filter(User.id == user_id).first()
                if target_user:
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

                    # Определяем язык целевого пользователя
                    target_lang = 'ru'  # По умолчанию

                    restart_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=get_text('user_mgmt.handlers.restart_bot_btn', language=target_lang), callback_data="restart_bot")]
                    ])

                    # Отправляем уведомление об одобрении с кнопкой перезапуска
                    await callback.bot.send_message(
                        chat_id=target_user.telegram_id,
                        text=get_text('user_mgmt.handlers.application_approved_restart', language=target_lang),
                        reply_markup=restart_keyboard
                    )

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
        logger.error(f"Ошибка быстрой верификации: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("quick_reject_"))
async def quick_reject_user(callback: CallbackQuery, db: Session, roles: list = None, language: str = "ru"):
    """Быстрое отклонение пользователя"""
    lang = language

    logger.debug(f"quick_reject_user: callback.data = {callback.data}")

    # Парсим user_id из callback_data
    try:
        user_id = int(callback.data.split("_")[2])
        logger.debug(f"quick_reject_user: parsed user_id = {user_id}")
    except (IndexError, ValueError) as e:
        logger.error(f"Ошибка парсинга user_id из callback.data '{callback.data}': {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )
        return

    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return

    try:
        # Проверяем, существует ли пользователь
        from uk_management_bot.database.models.user import User
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            logger.error(f"Пользователь с ID {user_id} не найден в базе данных")
            await callback.answer(
                get_text('user_mgmt.handlers.user_not_found', language=lang),
                show_alert=True
            )
            return

        logger.info(f"Найден пользователь: ID={user.id}, telegram_id={user.telegram_id}, username={user.username}")

        # Импортируем сервис верификации
        from uk_management_bot.services.user_verification_service import UserVerificationService
        from uk_management_bot.services.notification_service import NotificationService

        # Отклоняем верификацию
        verification_service = UserVerificationService(db)
        success = verification_service.reject_verification(
            user_id=user_id,
            admin_id=callback.from_user.id,
            notes=get_text('user_mgmt.handlers.verification_rejected_by_admin', language=lang)
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
            logger.error(f"reject_verification вернул False для user_id={user_id}")
            await callback.answer(
                get_text('errors.operation_failed', language=lang),
                show_alert=True
            )

    except Exception as e:
        logger.error(f"Ошибка быстрого отклонения пользователя {user_id}: {e}", exc_info=True)
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ ОБНОВЛЕНИЕ КЛАВИАТУР С ВЕРИФИКАЦИЕЙ ═══

def get_user_actions_keyboard_with_verification(user: User, language: str = 'ru'):
    """Получить клавиатуру действий пользователя с интеграцией верификации"""
    from uk_management_bot.keyboards.user_management import get_user_actions_keyboard
    from uk_management_bot.keyboards.user_verification import get_user_verification_keyboard
    
    # Получаем базовую клавиатуру
    base_keyboard = get_user_actions_keyboard(user, language)
    
    # Добавляем кнопки верификации
    verification_keyboard = get_user_verification_keyboard(user.id, language)
    
    # Объединяем клавиатуры
    combined_buttons = base_keyboard.inline_keyboard + verification_keyboard.inline_keyboard
    
    from aiogram.types import InlineKeyboardMarkup
    return InlineKeyboardMarkup(inline_keyboard=combined_buttons)


# ═══ ОБНОВЛЕНИЕ ГЛАВНОГО МЕНЮ ═══

def get_user_management_main_keyboard_with_verification(stats: Dict[str, int], language: str = 'ru'):
    """Получить главное меню управления пользователями с интеграцией верификации"""
    from uk_management_bot.keyboards.user_management import get_user_management_main_keyboard
    from uk_management_bot.keyboards.user_verification import get_verification_main_keyboard
    
    # Получаем базовую клавиатуру
    base_keyboard = get_user_management_main_keyboard(stats, language)
    
    # Добавляем кнопку верификации
    from aiogram.types import InlineKeyboardButton
    verification_button = [InlineKeyboardButton(
        text=f"🔍 {get_text('verification.main_title', language)}",
        callback_data="user_verification_panel"
    )]
    
    # Вставляем кнопку верификации после статистики
    base_keyboard.inline_keyboard.insert(1, verification_button)
    
    return base_keyboard


# ═══ СПИСКИ ПОЛЬЗОВАТЕЛЕЙ ═══

@router.callback_query(F.data.startswith("user_mgmt_list_"))
async def show_user_list(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать список пользователей"""
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
        # Парсим callback data: user_mgmt_list_{type}_{page}
        parts = callback.data.split('_')
        list_type = parts[3]  # pending, approved, blocked, staff
        page = int(parts[4]) if len(parts) > 4 else 1
        
        user_mgmt_service = UserManagementService(db)
        
        # Получаем данные в зависимости от типа списка
        if list_type == 'staff':
            users_data = user_mgmt_service.get_staff_users(page=page)
        else:
            users_data = user_mgmt_service.get_users_by_status(list_type, page=page)
        
        # Формируем заголовок
        title_key = f"user_management.{list_type}_users"
        if list_type == 'staff':
            title_key = "user_management.staff_users"
        
        title = get_text(title_key, language=lang)
        total = users_data.get('total', 0)
        
        message_text = f"{title}\n\n"
        if total > 0:
            message_text += get_text('pagination.info', language=lang).format(
                page=page,
                total_pages=users_data.get('total_pages', 1),
                total_items=total
            )
        else:
            message_text += get_text('user_management.no_users_found', language=lang)
        
        try:
            await callback.message.edit_text(
                message_text,
                reply_markup=get_user_list_keyboard(users_data, list_type, lang)
            )
        except Exception as edit_error:
            # Если сообщение не изменилось, просто отвечаем на callback
            if "message is not modified" in str(edit_error):
                await callback.answer(get_text('user_mgmt.handlers.data_up_to_date', language=lang))
            else:
                raise edit_error
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка отображения списка пользователей: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ ДЕЙСТВИЯ С ПОЛЬЗОВАТЕЛЯМИ ═══

@router.callback_query(F.data.startswith("user_mgmt_user_"))
async def show_user_details(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать детали пользователя и доступные действия"""
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
        # Парсим user_id из callback data
        user_id = int(callback.data.split('_')[-1])
        
        user_mgmt_service = UserManagementService(db)
        user = user_mgmt_service.get_user_by_id(user_id)
        
        if not user:
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return
        
        # Форматируем информацию о пользователе
        user_info = user_mgmt_service.format_user_info(user, lang, detailed=True)
        
        await callback.message.edit_text(
            user_info,
            reply_markup=get_user_actions_keyboard(user, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка отображения деталей пользователя: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


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
        from uk_management_bot.database.models.user_verification import UserDocument
        
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


# ВРЕМЕННО ОТКЛЮЧЕН - КОНФЛИКТ С НОВЫМИ ОБРАБОТЧИКАМИ ГАЛОЧЕК
# @router.callback_query(F.data.startswith("request_document_"))
# async def handle_document_type_selection(callback: CallbackQuery, state: FSMContext, db: Session, 
#                                        roles: list = None, active_role: str = None, user: User = None):
#     """Обработать выбор типа документа для запроса"""
#     lang = language
#     
#     logger.info(f"🔍 HANDLE_DOCUMENT_TYPE_SELECTION: Вызван обработчик для {callback.data}")
#     logger.info(f"🔍 HANDLE_DOCUMENT_TYPE_SELECTION: Это старый обработчик, который не должен вызываться!")
#     
#     # Проверяем права доступа через утилитарную функцию
#     has_access = has_admin_access(roles=roles, user=user)
#     
#     if not has_access:
#         await callback.answer(
#             get_text('errors.permission_denied', language=lang),
#             show_alert=True
#         )
#         return
#     
#     try:
#         # Парсим данные: request_document_{user_id}_{document_type}
#         parts = callback.data.split('_')
#         target_user_id = int(parts[2])
#         document_type = parts[3]
#         
#         # Получаем внутренний ID менеджера из базы данных
#         manager = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
#         if not manager:
#             await callback.answer(get_text('user_mgmt.handlers.manager_not_found', language=lang), show_alert=True)
#             return
#             
#         await state.update_data({
#             'action': 'request_specific_document',
#             'target_user_id': target_user_id,
#             'manager_id': manager.id,
#             'document_type': document_type
#         })
#         
#         await state.set_state(UserManagementStates.waiting_for_document_request)
#         
#         # Получаем название типа документа
#         from uk_management_bot.database.models.user_verification import DocumentType
#         doc_type_name = get_text(f'verification.document_types.{document_type}', language=lang)
#         logger.info(f"🔍 DOCUMENT_TYPE_SELECTION: Тип документа: {document_type}, Название: {doc_type_name}")
#         
#         await callback.message.edit_text(
#             get_text('moderation.enter_document_request_specific', language=lang).format(
#                 document_type=doc_type_name
#             ),
#             reply_markup=get_cancel_keyboard(lang)
#         )
#         
#         await callback.answer()
#         
#     except Exception as e:
#         logger.error(f"Ошибка обработки выбора типа документа: {e}")
#         await callback.answer(
#             get_text('errors.unknown_error', language=lang),
#             show_alert=True
#         )


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
            base_docs = docs_str.split('+')[0].split(',')
            additional_count = int(docs_str.split('+')[1])
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
                from uk_management_bot.keyboards.base import get_main_keyboard_for_role

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

                # Определяем язык целевого пользователя
                target_lang = 'ru'  # По умолчанию

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
    
    logger.info(f"🔍 PROCESS_DOCUMENT_REQUEST: Начало обработки запроса документов")
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
            logger.info(f"🔍 PROCESS_DOCUMENT_REQUEST: Общий запрос документов")
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


# ═══ УПРАВЛЕНИЕ РОЛЯМИ ═══

@router.callback_query(F.data.startswith("user_roles_"))
async def show_user_roles_management(callback: CallbackQuery, state: FSMContext, db: Session, 
                                   roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать управление ролями пользователя"""
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
        
        auth_service = AuthService(db)
        user_roles = auth_service.get_user_roles(target_user_id)
        
        # Получаем внутренний ID менеджера из базы данных
        manager = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not manager:
            await callback.answer(get_text('user_mgmt.handlers.manager_not_found', language=lang), show_alert=True)
            return
            
        # Сохраняем данные в состоянии
        await state.update_data({
            'target_user_id': target_user_id,
            'manager_id': manager.id,  # Используем внутренний ID из базы данных
            'original_roles': user_roles.copy(),
            'current_roles': user_roles.copy()
        })
        
        await state.set_state(UserManagementStates.selecting_roles)
        
        user_mgmt_service = UserManagementService(db)
        target_user = user_mgmt_service.get_user_by_id(target_user_id)
        user_name = target_user.first_name or target_user.username or str(target_user.telegram_id)
        
        message_text = get_text('moderation.select_roles', language=lang).format(user_name=user_name)
        message_text += f"\n\n{get_text('moderation.current_roles', language=lang)}: "
        message_text += user_mgmt_service._format_user_roles(target_user, lang)
        
        await callback.message.edit_text(
            message_text,
            reply_markup=get_roles_management_keyboard(user_roles, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка отображения управления ролями: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("role_add_"), UserManagementStates.selecting_roles)
async def add_role_to_user(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Добавить роль пользователю"""
    lang = language
    
    try:
        role = callback.data.split('_')[-1]
        data = await state.get_data()
        current_roles = data.get('current_roles', [])
        
        if role not in current_roles:
            current_roles.append(role)
            await state.update_data(current_roles=current_roles)
        
        # Обновляем клавиатуру
        await callback.message.edit_reply_markup(
            reply_markup=get_roles_management_keyboard(current_roles, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка добавления роли: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("role_remove_"), UserManagementStates.selecting_roles)
async def remove_role_from_user(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Удалить роль у пользователя"""
    lang = language
    
    try:
        role = callback.data.split('_')[-1]
        data = await state.get_data()
        current_roles = data.get('current_roles', [])
        
        # Проверяем, что не удаляем последнюю роль
        if len(current_roles) <= 1:
            await callback.answer(
                get_text('moderation.cannot_remove_last_role', language=lang),
                show_alert=True
            )
            return
        
        if role in current_roles:
            current_roles.remove(role)
            await state.update_data(current_roles=current_roles)
        
        # Обновляем клавиатуру
        await callback.message.edit_reply_markup(
            reply_markup=get_roles_management_keyboard(current_roles, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка удаления роли: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data == "roles_save", UserManagementStates.selecting_roles)
async def save_user_roles(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Сохранить изменения ролей"""
    lang = language
    
    try:
        data = await state.get_data()
        target_user_id = data.get('target_user_id')
        manager_id = data.get('manager_id')
        original_roles = data.get('original_roles', [])
        current_roles = data.get('current_roles', [])
        
        # Проверяем, есть ли изменения
        if set(original_roles) == set(current_roles):
            await callback.answer(
                get_text('moderation.no_changes_made', language=lang)
            )
            await state.clear()
            return
        
        # Переходим к вводу комментария
        await state.update_data({'action': 'roles_change'})
        await state.set_state(UserManagementStates.waiting_for_role_comment)
        
        await callback.message.edit_text(
            get_text('moderation.enter_role_change_comment', language=lang),
            reply_markup=get_cancel_keyboard(lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка сохранения ролей: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data == "roles_cancel", UserManagementStates.selecting_roles)
async def cancel_roles_editing(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru"):
    """Отменить редактирование ролей"""
    lang = language
    
    try:
        data = await state.get_data()
        target_user_id = data.get('target_user_id')
        
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
        
        await callback.answer(
            get_text('buttons.operation_cancelled', language=lang)
        )
        
    except Exception as e:
        logger.error(f"Ошибка отмены редактирования ролей: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.message(UserManagementStates.waiting_for_role_comment)
async def process_role_change_comment(message: Message, state: FSMContext, db: Session, language: str = "ru"):
    """Обработать комментарий к изменению ролей"""
    lang = language
    
    try:
        data = await state.get_data()
        target_user_id = data.get('target_user_id')
        manager_id = data.get('manager_id')
        original_roles = data.get('original_roles', [])
        current_roles = data.get('current_roles', [])
        comment = message.text
        
        auth_service = AuthService(db)
        
        # Определяем добавленные и удаленные роли
        added_roles = set(current_roles) - set(original_roles)
        removed_roles = set(original_roles) - set(current_roles)
        
        success = True
        
        # Добавляем новые роли
        for role in added_roles:
            if not auth_service.assign_role(target_user_id, role, manager_id, comment):
                success = False
        
        # Удаляем роли
        for role in removed_roles:
            if not auth_service.remove_role(target_user_id, role, manager_id, comment):
                success = False
        
        if success:
            user_mgmt_service = UserManagementService(db)
            target_user = user_mgmt_service.get_user_by_id(target_user_id)
            
            user_name = target_user.first_name or target_user.username or str(target_user.telegram_id)
            
            await message.answer(
                get_text('moderation.roles_updated_successfully', language=lang).format(
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
        logger.error(f"Ошибка обработки комментария к изменению ролей: {e}")
        await message.answer(
            get_text('errors.unknown_error', language=lang)
        )
        await state.clear()


# ═══ УПРАВЛЕНИЕ СПЕЦИАЛИЗАЦИЯМИ ═══

@router.callback_query(F.data.startswith("user_specializations_"))
async def show_user_specializations_management(callback: CallbackQuery, state: FSMContext, db: Session, 
                                             roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать управление специализациями пользователя"""
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
        
        spec_service = SpecializationService(db)
        user_specializations = spec_service.get_user_specializations(target_user_id)
        
        # Получаем внутренний ID менеджера из базы данных
        manager = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not manager:
            await callback.answer(get_text('user_mgmt.handlers.manager_not_found', language=lang), show_alert=True)
            return
            
        # Сохраняем данные в состоянии
        await state.update_data({
            'target_user_id': target_user_id,
            'manager_id': manager.id,  # Используем внутренний ID из базы данных
            'original_specializations': user_specializations.copy(),
            'current_specializations': user_specializations.copy()
        })
        
        await state.set_state(UserManagementStates.selecting_specializations)
        
        user_mgmt_service = UserManagementService(db)
        target_user = user_mgmt_service.get_user_by_id(target_user_id)
        user_name = target_user.first_name or target_user.username or str(target_user.telegram_id)
        
        message_text = get_text('specializations.select_specializations', language=lang).format(user_name=user_name)
        message_text += f"\n\n{get_text('specializations.current_specializations', language=lang)}: "
        message_text += spec_service.format_specializations_list(user_specializations, lang)
        
        await callback.message.edit_text(
            message_text,
            reply_markup=get_specializations_selection_keyboard(user_specializations, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка отображения управления специализациями: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("spec_toggle_"), UserManagementStates.selecting_specializations)
async def toggle_specialization(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Переключить специализацию (добавить/удалить)"""
    lang = language
    
    try:
        specialization = callback.data.split('_')[-1]
        data = await state.get_data()
        current_specializations = data.get('current_specializations', [])
        
        if specialization in current_specializations:
            current_specializations.remove(specialization)
        else:
            current_specializations.append(specialization)
        
        await state.update_data(current_specializations=current_specializations)
        
        # Обновляем клавиатуру
        await callback.message.edit_reply_markup(
            reply_markup=get_specializations_selection_keyboard(current_specializations, lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка переключения специализации: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data == "spec_save", UserManagementStates.selecting_specializations)
async def save_user_specializations(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Сохранить изменения специализаций"""
    lang = language
    
    try:
        data = await state.get_data()
        original_specializations = data.get('original_specializations', [])
        current_specializations = data.get('current_specializations', [])
        
        # Проверяем, есть ли изменения
        if set(original_specializations) == set(current_specializations):
            await callback.answer(
                get_text('moderation.no_changes_made', language=lang)
            )
            await state.clear()
            return
        
        # Переходим к вводу комментария
        await state.update_data({'action': 'specializations_change'})
        await state.set_state(UserManagementStates.waiting_for_specialization_comment)
        
        await callback.message.edit_text(
            get_text('moderation.enter_specialization_change_comment', language=lang),
            reply_markup=get_cancel_keyboard(lang)
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка сохранения специализаций: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data == "spec_cancel", UserManagementStates.selecting_specializations)
async def cancel_specializations_editing(callback: CallbackQuery, state: FSMContext, db: Session, language: str = "ru"):
    """Отменить редактирование специализаций"""
    lang = language
    
    try:
        data = await state.get_data()
        target_user_id = data.get('target_user_id')
        
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
        
        await callback.answer(
            get_text('buttons.operation_cancelled', language=lang)
        )
        
    except Exception as e:
        logger.error(f"Ошибка отмены редактирования специализаций: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.message(UserManagementStates.waiting_for_specialization_comment)
async def process_specialization_change_comment(message: Message, state: FSMContext, db: Session, language: str = "ru"):
    """Обработать комментарий к изменению специализаций"""
    lang = language
    
    try:
        data = await state.get_data()
        target_user_id = data.get('target_user_id')
        manager_id = data.get('manager_id')
        current_specializations = data.get('current_specializations', [])
        comment = message.text
        
        spec_service = SpecializationService(db)
        success = spec_service.set_user_specializations(
            target_user_id, 
            current_specializations, 
            manager_id, 
            comment
        )
        
        if success:
            user_mgmt_service = UserManagementService(db)
            target_user = user_mgmt_service.get_user_by_id(target_user_id)
            
            user_name = target_user.first_name or target_user.username or str(target_user.telegram_id)
            
            await message.answer(
                get_text('specializations.specializations_updated', language=lang).format(
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
        logger.error(f"Ошибка обработки комментария к изменению специализаций: {e}")
        await message.answer(
            get_text('errors.unknown_error', language=lang)
        )
        await state.clear()


# ═══ ИНТЕГРАЦИЯ С АДМИН ПАНЕЛЬЮ ═══

async def open_user_management(message: Message, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Открыть панель управления пользователями (для интеграции с админ панелью)"""
    lang = language
    
    try:
        # Получаем статистику пользователей
        user_mgmt_service = UserManagementService(db)
        stats = user_mgmt_service.get_user_stats()
        
        # Показываем главное меню
        await message.answer(
            get_text('user_management.main_title', language=lang),
            reply_markup=get_user_management_main_keyboard(stats, lang)
        )
        
    except Exception as e:
        logger.error(f"Ошибка отображения панели управления пользователями: {e}")
        await message.answer(
            get_text('errors.unknown_error', language=lang)
        )


# admin_panel callback handler is in employee_management.py (uses edit_text)
