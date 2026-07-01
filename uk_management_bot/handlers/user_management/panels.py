"""Панель управления пользователями, статистика, верификация, уведомления."""
import logging

from aiogram import F
from aiogram.types import CallbackQuery
from sqlalchemy.orm import Session

from uk_management_bot.services.user_management_service import UserManagementService
from uk_management_bot.keyboards.user_management import get_user_management_main_keyboard
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.auth_helpers import has_admin_access
from uk_management_bot.database.models.user import User

from ._router import router

logger = logging.getLogger(__name__)


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

                # Получаем пользователя
                target_user = db.query(User).filter(User.id == user_id).first()
                if target_user:
                    # Создаем клавиатуру с кнопкой перезапуска
                    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

                    # Определяем язык целевого пользователя
                    target_lang = target_user.language or 'ru'

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


