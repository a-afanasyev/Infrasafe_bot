"""Разделяемое для requests-пакета: константы (тексты кнопок + regex номеров), RequestStates, helper-функции (db-scope, язык, pending-гарды, адреса) (AUD3-06)."""
from contextlib import contextmanager

from aiogram.types import Message, CallbackQuery
from aiogram.fsm.state import State, StatesGroup
from uk_management_bot.database.session import session_scope
from uk_management_bot.services.request_handler_service import RequestHandlerService
import re
from uk_management_bot.services.request_number_service import REQUEST_NUMBER_CORE

from uk_management_bot.keyboards.requests import (
    get_cancel_keyboard,
)
import logging
from typing import Optional

# Localization imports - TASK 17 Phase 2
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.language_helpers import (
    get_language_from_message
)
# Single Source of Truth for button texts - TASK 17 Entry Handler Fix
from uk_management_bot.utils.button_texts import (
    get_create_request_texts,
    get_group_pool_texts,
    get_my_requests_texts
)

logger = logging.getLogger(__name__)

# BUG-122: view_/cancel_ callback matchers built from the shared request-number
# core (\d{3,}) so 4-digit (>999/day) numbers match too — single source of truth.
_VIEW_REQUEST_NUMBER_RE = rf"^view(?:_request)?_{REQUEST_NUMBER_CORE}$"
_CANCEL_REQUEST_NUMBER_RE = re.compile(rf"^cancel_{REQUEST_NUMBER_CORE}$")
# BUG-BOT-037: edit_/approve_ owner-action callbacks bound to the shared
# request-number core (strict regex) instead of open-set startswith+exclusion
# lists, so future edit_*/approve_* callbacks aren't swallowed by these handlers.
_EDIT_REQUEST_NUMBER_RE = rf"^edit_{REQUEST_NUMBER_CORE}$"
_APPROVE_REQUEST_NUMBER_RE = rf"^approve_{REQUEST_NUMBER_CORE}$"


# Константа для фильтрации сообщений создания заявки
# Использует единый источник правды для автоматического масштабирования на все языки
# Вычисляется один раз при импорте модуля (критично для фильтров aiogram)
CREATE_REQUEST_TEXTS = get_create_request_texts()
MY_REQUESTS_TEXTS = get_my_requests_texts()
GROUP_POOL_TEXTS = get_group_pool_texts()


@contextmanager
def _db_scope(db):
    """Сессия для хендлера: инъецированная (владелец — вызывающий, НЕ закрываем
    здесь) либо свежая через ``session_scope()`` (закроется на выходе).

    CODE-04: заменяет ``db = next(get_db())`` + ``finally: db.close()``. Сохраняет
    seam внедрения ``db`` в тестах (близкий к исходному: переданный db не трогаем,
    а если db нет — берём и гарантированно закрываем).
    """
    if db is not None:
        yield db
    else:
        with session_scope() as scoped:
            yield scoped


# Вспомогательные функции для улучшенной обработки ошибок и UX

async def _get_user_language(message: Message = None, callback: CallbackQuery = None, user_id: int = None) -> str:
    """Get user language from message, callback, or user_id
    
    ВАЖНО: Использует язык из базы данных, а не только language_code из Telegram.
    Это обеспечивает правильную локализацию для всех пользователей.

    Args:
        message: Telegram message object
        callback: Telegram callback query object
        user_id: User telegram ID

    Returns:
        Language code (ru/uz), defaults to 'ru'
    """
    try:
        # Получаем user_id из сообщения или callback
        target_user_id = None
        if message:
            target_user_id = message.from_user.id
        elif callback:
            target_user_id = callback.from_user.id
        elif user_id:
            target_user_id = user_id
        
        # Используем язык из базы данных (приоритет над language_code из Telegram)
        if target_user_id:
            with _db_scope(None) as db:
                try:
                    from uk_management_bot.utils.helpers import get_user_language
                    lang = get_user_language(target_user_id, db)
                    if lang and lang in ['ru', 'uz']:
                        return lang
                except Exception as e:
                    logger.warning(f"Failed to get user language from DB for {target_user_id}: {e}")
        
        # Fallback: используем language_code из Telegram
        if message:
            return get_language_from_message(message)
        elif callback:
            return get_language_from_message(callback)
    except Exception as e:
        logger.warning(f"Failed to get user language: {e}")

    return "ru"  # Fallback to Russian

async def _deny_if_pending_message(message: Message, user_status: Optional[str], language: str = "ru") -> bool:
    """Единый ранний отказ для пользователей со статусом pending (Message).

    Возвращает True, если обработку нужно прервать.
    """
    if user_status == "pending":
        from uk_management_bot.utils.safe_localization import safe_get_text
        lang = language
        try:
            lang = await _get_user_language(message=message)
            await message.answer(get_text("auth.pending", language=lang))
        except Exception:
            await message.answer(safe_get_text("shifts.registration_pending", language=lang))
        return True
    return False

async def _deny_if_pending_callback(callback: CallbackQuery, user_status: Optional[str], language: str = "ru") -> bool:
    """Единый ранний отказ для пользователей со статусом pending (CallbackQuery).

    Возвращает True, если обработку нужно прервать.
    """
    if user_status == "pending":
        from uk_management_bot.utils.safe_localization import safe_get_text
        lang = language
        try:
            lang = await _get_user_language(callback=callback)
            await callback.answer(get_text("auth.pending", language=lang), show_alert=True)
        except Exception:
            await callback.answer(safe_get_text("shifts.awaiting_admin_approval", language=lang), show_alert=True)
        return True
    return False

def get_contextual_help(address_type: str, language: str = "ru") -> str:
    """
    Получить контекстную помощь в зависимости от типа адреса

    Args:
        address_type: Тип адреса (home/apartment/yard)
        language: Язык интерфейса (ru/uz)

    Returns:
        str: Контекстное сообщение с подсказками
    """
    # Map address types to locale keys (using existing keys from Phase 2 auto-generation)
    help_key_map = {
        "home": "requests.вы_выбрали_дом",
        "apartment": "requests.вы_выбрали_квартиру",
        "yard": "requests.вы_выбрали_двор"
    }

    key = help_key_map.get(address_type, "requests.help_default")
    return get_text(key, language=language)

async def graceful_fallback(message: Message, error_type: str, language: str = "ru"):
    """
    Graceful degradation при ошибках

    Args:
        message: Сообщение пользователя
        error_type: Тип ошибки
        language: Язык интерфейса (ru/uz)
    """
    # Get error message from locale
    error_key = f"errors.{error_type}"
    error_message = get_text(error_key, language=language)

    # Fallback if key not found
    if error_message == error_key:
        error_message = get_text("errors.default", language=language)

    await message.answer(error_message, reply_markup=get_cancel_keyboard(language=language))
    
    logger.warning(f"[GRACEFUL_FALLBACK] Ошибка типа '{error_type}' для пользователя {message.from_user.id}")

# auto_assign_request_by_category lived here as a duplicate of the version in
# handlers/admin.py. This copy never committed the session and never notified
# active-shift executors, so the duty-assignment flow silently did nothing. The
# admin.py version is now the single source of truth.


class RequestStates(StatesGroup):
    """Состояния FSM для создания заявок"""
    category = State()           # Выбор категории
    address_yard = State()       # Выбор двора (шаг 1)
    address_building = State()   # Выбор здания (шаг 2)
    address_apartment = State()  # Выбор квартиры (шаг 3)
    address = State()            # Устаревший: прямой выбор адреса
    description = State()        # Описание проблемы
    urgency = State()           # Выбор срочности
    media = State()             # Медиафайлы
    confirm = State()           # Подтверждение
    waiting_clarify_reply = State()  # Ответ на уточнение

# BUG-3 FIX: /start FSM reset now handled globally by start_router in base.py
# (registered first in dispatcher, catches /start from ANY FSM state)


def _load_user_request_addresses(telegram_id: int):
    """Наборы доступных жителю уровней адреса (по telegram_id → user.id).

    Единый источник правил — resolve_request_address. Возвращает dict
    {yards, buildings, apartments} или None, если пользователь не найден.
    """
    from uk_management_bot.services.request_address import (
        list_available_request_addresses_sync,
    )

    with _db_scope(None) as db:
        user = RequestHandlerService(db).get_user_by_telegram_id(telegram_id)
        if not user:
            return None
        return list_available_request_addresses_sync(db, user.id)


def _has_any_address(addresses: Optional[dict]) -> bool:
    return bool(
        addresses
        and (addresses.get("apartments") or addresses.get("buildings") or addresses.get("yards"))
    )
