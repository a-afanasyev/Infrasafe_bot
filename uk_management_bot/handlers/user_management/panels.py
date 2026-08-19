"""Панель управления пользователями, статистика, верификация, уведомления.

AUD3-07/AUD5-ARCH-1: DB-фаза ЖИВЫХ хендлеров — цельный sync unit-of-work,
исполняемый в worker-потоке через ``run_db``; наружу выходят DTO/скаляры, а не
ORM-строки (у ORM-объекта вне потока нет живой сессии).

Три хендлера файла МЁРТВЫ — генераторов их триггеров в проде нет (инвентарь
волны 5): ``show_user_stats_with_verification`` (``user_mgmt_stats_with_verification``),
``quick_verify_user`` (``quick_verify_``), ``quick_reject_user`` (``quick_reject_``).
Они сохранены байт-в-байт до decision владельца (прецедент BUG-137/148/150) и
продолжают работать с сессией на event loop — поэтому файл НЕ входит в ратчет
``tests/services/test_aud337_async_handlers_gate.py``.
"""
import logging
from typing import Optional

from aiogram import F
from aiogram.types import CallbackQuery

from uk_management_bot.services.user_management_service import UserManagementService
from uk_management_bot.keyboards.user_management import get_user_management_main_keyboard
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.auth_helpers import has_admin_access
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import run_db

from ._router import router

logger = logging.getLogger(__name__)


# ═══ Sync unit-of-work (исполняются в worker-потоке через run_db) ═══

def _load_user_stats(db) -> dict:
    """-> словарь счётчиков пользователей для главного меню."""
    # Получаем статистику пользователей
    user_mgmt_service = UserManagementService(db)
    return user_mgmt_service.get_user_stats()


def _load_stats_view(db, lang: str) -> tuple:
    """-> (stats, отформатированный текст статистики)."""
    user_mgmt_service = UserManagementService(db)
    stats = user_mgmt_service.get_user_stats()

    stats_text = user_mgmt_service.format_stats_message(stats, lang)

    return (stats, stats_text)


def _load_verification_stats(db) -> dict:
    """-> словарь статистики верификации."""
    # Импортируем сервис верификации
    from uk_management_bot.services.user_verification_service import UserVerificationService

    # Получаем статистику верификации
    verification_service = UserVerificationService(db)
    return verification_service.get_verification_stats()


def _apply_approve_from_notification(db, user_id: int, manager_id: int, lang: str) -> tuple:
    """-> ('user_not_found', None, None) | ('ok', first_name, success)."""
    from uk_management_bot.database.models.user import User as UserModel
    from uk_management_bot.services.auth_service import AuthService

    # Получаем пользователя
    target_user = db.query(UserModel).filter(UserModel.id == user_id).first()

    if not target_user:
        return ("user_not_found", None, None)

    # Одобряем пользователя (используем sync метод с user_id)
    auth_service = AuthService(db)
    success = auth_service.approve_user(user_id, manager_id, get_text('user_mgmt.handlers.approved_via_notification', language=lang))

    return ("ok", target_user.first_name, success)


def _apply_reject_from_notification(db, user_id: int, actor_telegram_id: int, lang: str) -> tuple:
    """-> ('user_not_found', None, None) | ('ok', first_name, success)."""
    from uk_management_bot.database.models.user import User as UserModel

    # Получаем пользователя
    target_user = db.query(UserModel).filter(UserModel.id == user_id).first()

    if not target_user:
        return ("user_not_found", None, None)

    # Отклоняем пользователя (блокируем) - используем sync метод с user_id
    from uk_management_bot.services.auth_service import AuthService
    from uk_management_bot.database.models.user import User as UserModel

    auth_service = AuthService(db)
    # Получаем ID текущего менеджера
    manager = db.query(UserModel).filter(UserModel.telegram_id == actor_telegram_id).first()
    manager_id = manager.id if manager else actor_telegram_id

    success = auth_service.block_user(user_id, manager_id, get_text('user_mgmt.handlers.rejected_via_notification', language=lang))

    return ("ok", target_user.first_name, success)


def _load_user_profile_text(db, user_id: int, lang: str) -> Optional[str]:
    """-> готовый текст профиля либо None, если пользователя нет.

    Текст собирается здесь: он читает поля ORM-пользователя, живые только
    внутри сессии.
    """
    from uk_management_bot.database.models.user import User as UserModel

    # Получаем пользователя
    target_user = db.query(UserModel).filter(UserModel.id == user_id).first()

    if not target_user:
        return None

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

    return profile_text


# ═══ ГЛАВНОЕ МЕНЮ УПРАВЛЕНИЯ ПОЛЬЗОВАТЕЛЯМИ ═══

@router.callback_query(F.data == "user_management_panel")
async def show_user_management_panel(callback: CallbackQuery, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
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
        stats = await run_db(_load_user_stats, db=_db)

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
async def back_to_main_panel(callback: CallbackQuery, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
    """Вернуться к главному меню панели управления"""
    # ⚠️ Предсуществующий дефект (сохранён 1:1): `language` не пробрасывается —
    # панель после «назад» рендерится на "ru" независимо от языка менеджера.
    await show_user_management_panel(callback, roles, active_role, user, _db=_db)


@router.callback_query(F.data == "user_mgmt_stats")
async def show_user_stats(callback: CallbackQuery, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
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
        stats, stats_text = await run_db(lambda s: _load_stats_view(s, lang), db=_db)

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
async def show_verification_panel(callback: CallbackQuery, roles: list = None, active_role: str = None, user: User = None, language: str = "ru", *, _db=None):
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
        stats = await run_db(_load_verification_stats, db=_db)

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


# ═══ ОБРАБОТЧИКИ ДЛЯ УВЕДОМЛЕНИЙ О РЕГИСТРАЦИИ ═══

@router.callback_query(F.data.startswith("approve_user_"))
async def handle_approve_user_from_notification(callback: CallbackQuery, roles: list = None, user: User = None, language: str = "ru", *, _db=None):
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
        # Получаем ID текущего менеджера (из параметра user или callback)
        manager_id = user.id if user else callback.from_user.id

        verdict, target_first_name, success = await run_db(
            lambda s: _apply_approve_from_notification(s, user_id, manager_id, lang), db=_db
        )

        if verdict == "user_not_found":
            await callback.answer(get_text('user_mgmt.handlers.user_not_found', language=lang), show_alert=True)
            return

        if success:
            await callback.answer(get_text('user_mgmt.handlers.user_approved_alert', language=lang).format(name=target_first_name), show_alert=True)

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
async def handle_reject_user_from_notification(callback: CallbackQuery, roles: list = None, language: str = "ru", *, _db=None):
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
        verdict, target_first_name, success = await run_db(
            lambda s: _apply_reject_from_notification(s, user_id, callback.from_user.id, lang), db=_db
        )

        if verdict == "user_not_found":
            await callback.answer(get_text('user_mgmt.handlers.user_not_found', language=lang), show_alert=True)
            return

        if success:
            await callback.answer(get_text('user_mgmt.handlers.user_rejected_alert', language=lang).format(name=target_first_name), show_alert=True)

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


# BUG-155 п.3 (закрыто 2026-08-18): фильтр-префикс "view_user_" перехватывал и
# "view_user_documents_{id}" (keyboards/user_verification.py), адресованный
# user_verification/documents.py — роутер user_management включён в main.py
# раньше. `int("documents")` падал ValueError, и менеджер вместо списка
# документов получал «ошибка обработки запроса».
#
# Строгий регекс вместо открытого префикса (прецедент PR-25/BUG-BOT-034):
# закрывает не только известный случай, но и любой будущий
# `view_user_<слово>_<id>`, который иначе снова провалился бы сюда.
_VIEW_USER_ID_RE = r"^view_user_\d+$"


@router.callback_query(F.data.regexp(_VIEW_USER_ID_RE))
async def handle_view_user_from_notification(callback: CallbackQuery, roles: list = None, language: str = "ru", *, _db=None):
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
        profile_text = await run_db(
            lambda s: _load_user_profile_text(s, user_id, lang), db=_db
        )

        if profile_text is None:
            await callback.answer(get_text('user_mgmt.handlers.user_not_found', language=lang), show_alert=True)
            return

        # Отправляем новое сообщение с профилем
        await callback.message.answer(profile_text, parse_mode="HTML")
        await callback.answer()

        logger.info(f"Просмотрен профиль пользователя {user_id} менеджером {callback.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка просмотра профиля пользователя {user_id}: {e}", exc_info=True)
        await callback.answer(get_text('user_mgmt.handlers.error_occurred', language=lang), show_alert=True)


