from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.orm import Session
from sqlalchemy import or_
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.session import get_db
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.request_assignment import RequestAssignment
import re
from uk_management_bot.services.request_number_service import REQUEST_NUMBER_CORE

from uk_management_bot.keyboards.requests import (
    get_categories_keyboard,
    get_cancel_keyboard,
    get_media_keyboard,
    get_confirmation_keyboard,
    get_categories_inline_keyboard_with_cancel,
    get_urgency_inline_keyboard,
    get_inline_confirmation_keyboard,
    get_status_filter_inline_keyboard,
)
from uk_management_bot.keyboards.base import get_main_keyboard, get_contextual_keyboard, get_user_contextual_keyboard
from uk_management_bot.utils.validators import (
    validate_media_file
)
import logging
from uk_management_bot.services.request_service import RequestService
from typing import Optional

# Localization imports - TASK 17 Phase 2
from uk_management_bot.utils.helpers import get_text, get_user_language
from uk_management_bot.utils.status_display import get_status_display as _sd_get_status_display, STATUS_EMOJI
from uk_management_bot.utils.language_helpers import (
    get_language_from_message
)
# Single Source of Truth for button texts - TASK 17 Entry Handler Fix
from uk_management_bot.utils.button_texts import (
    get_create_request_texts,
    get_group_pool_texts,
    get_my_requests_texts
)

# BUG-122: view_/cancel_ callback matchers built from the shared request-number
# core (\d{3,}) so 4-digit (>999/day) numbers match too — single source of truth.
_VIEW_REQUEST_NUMBER_RE = rf"^view(?:_request)?_{REQUEST_NUMBER_CORE}$"
_CANCEL_REQUEST_NUMBER_RE = re.compile(rf"^cancel_{REQUEST_NUMBER_CORE}$")
# BUG-BOT-037: edit_/approve_ owner-action callbacks bound to the shared
# request-number core (strict regex) instead of open-set startswith+exclusion
# lists, so future edit_*/approve_* callbacks aren't swallowed by these handlers.
_EDIT_REQUEST_NUMBER_RE = rf"^edit_{REQUEST_NUMBER_CORE}$"
_APPROVE_REQUEST_NUMBER_RE = rf"^approve_{REQUEST_NUMBER_CORE}$"

logger = logging.getLogger(__name__)

router = Router()

# NOTE: auth_middleware and role_mode_middleware are registered globally in main.py
# Do NOT register them again at router level to avoid double execution.

# Константа для фильтрации сообщений создания заявки
# Использует единый источник правды для автоматического масштабирования на все языки
# Вычисляется один раз при импорте модуля (критично для фильтров aiogram)
CREATE_REQUEST_TEXTS = get_create_request_texts()
MY_REQUESTS_TEXTS = get_my_requests_texts()
GROUP_POOL_TEXTS = get_group_pool_texts()

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
            db = next(get_db())
            try:
                from uk_management_bot.utils.helpers import get_user_language
                lang = get_user_language(target_user_id, db)
                if lang and lang in ['ru', 'uz']:
                    return lang
            except Exception as e:
                logger.warning(f"Failed to get user language from DB for {target_user_id}: {e}")
            finally:
                db.close()
        
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


# Временно отключаем отладочный обработчик
# @router.message(F.text)
# async def debug_all_messages(message: Message):
#     """Отладочный обработчик для всех текстовых сообщений"""

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
    from uk_management_bot.database.models.user import User
    from uk_management_bot.services.request_address import (
        list_available_request_addresses_sync,
    )

    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user:
            return None
        return list_available_request_addresses_sync(db, user.id)
    finally:
        db.close()


def _has_any_address(addresses: Optional[dict]) -> bool:
    return bool(
        addresses
        and (addresses.get("apartments") or addresses.get("buildings") or addresses.get("yards"))
    )

# Начало создания заявки
# Использует единый источник правды для поддержки всех языков из SUPPORTED_LANGUAGES
# ВАЖНО: Этот handler должен быть зарегистрирован ДО handlers с FSM состояниями
@router.message(F.text.in_(CREATE_REQUEST_TEXTS))
async def start_request_creation(message: Message, state: FSMContext, user_status: Optional[str] = None):
    """Начало создания заявки"""
    # Отладочное логирование
    logger.info(f"[ENTRY_HANDLER] ✅ Handler сработал! Сообщение: '{message.text}' от пользователя {message.from_user.id}")
    logger.info(f"[ENTRY_HANDLER] CREATE_REQUEST_TEXTS: {CREATE_REQUEST_TEXTS}")
    logger.info(f"[ENTRY_HANDLER] Текущее FSM состояние: {await state.get_state()}")
    
    # Get user language
    lang = await _get_user_language(message=message)

    if await _deny_if_pending_message(message, user_status):
        return

    # Проверяем наличие телефона у пользователя
    from uk_management_bot.database.session import get_db
    from uk_management_bot.database.models.user import User

    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        # Approved-applicant гейт (план «Обходчик»): applicant-flow стал
        # role-gated. Менеджер/обходчик заводят заявки своими путями. Гейт —
        # ЖЁСТКИЙ: при отсутствии юзера/ошибке БД не входим в FSM (fail-closed).
        if user is None:
            await message.answer(get_text("requests.applicant_only", language=lang))
            return
        from uk_management_bot.api.dependencies import _parse_user_roles
        user_roles = _parse_user_roles(user)
        if "applicant" not in user_roles or user.status != "approved":
            await message.answer(get_text("requests.applicant_only", language=lang))
            return
        if not user.phone:
            await message.answer(get_text("requests.phone_required", language=lang))
            return
    except Exception as e:
        logger.error(f"Ошибка проверки доступа пользователя {message.from_user.id}: {e}", exc_info=True)
        await message.answer(get_text("errors.default", language=lang))
        return
    finally:
        db.close()

    logger.info(f"Пользователь {message.from_user.id} начал создание заявки (текст: '{message.text}')")
    await state.set_state(RequestStates.category)

    # Скрываем главное меню (ReplyKeyboard) на время сценария создания заявки
    await message.answer(
        get_text("requests.starting_request_creation", language=lang),
        reply_markup=ReplyKeyboardRemove()
    )

    # Показываем inline-клавиатуру категорий
    await message.answer(
        get_text("requests.select_category", language=lang),
        reply_markup=get_categories_inline_keyboard_with_cancel(language=lang)
    )

    logger.info(f"Пользователь {message.from_user.id} начал создание заявки")

# DEAD-16 (PR-8): закомментированный text-based category filter (43 строки,
# отключён в TASK 17 — ломал узбекскую локаль) удалён; категория выбирается
# callback-хендлером handle_category_selection (language-independent IDs).

# Игнор/подсказка для любых других текстов в состоянии выбора категории
@router.message(RequestStates.category)
async def process_category_other_inputs(message: Message, state: FSMContext):
    """Обработчик для любых других текстовых сообщений в состоянии выбора категории"""
    lang = await _get_user_language(message=message)
    user_id = message.from_user.id
    logger.info(f"[CATEGORY_SELECTION] Пользователь {user_id} отправил неожиданный текст: '{message.text}'")

    if message.text == get_text("buttons.cancel", language=lang):
        await cancel_request(message, state, lang=lang)
        return

    # Отправляем подсказку с повторной отправкой inline-клавиатуры
    await message.answer(
        get_text("requests.use_category_buttons", language=lang),
        reply_markup=get_categories_inline_keyboard_with_cancel(language=lang)
    )

# Обработка выбора адреса (обновленная логика)
@router.callback_query(F.data.startswith("addr:"), RequestStates.address)
async def handle_address_selection(callback: CallbackQuery, state: FSMContext, user_status: Optional[str] = None):
    """Выбор адреса заявки по callback addr:<type>:<id>.

    Резолв через resolve_request_address_sync (принадлежность+активность). Чужой
    адрес → отказ; неактивный/несуществующий → отказ. id, а не текст — поэтому
    неуникальный Building.address больше не уводит в чужой дом (R17).
    """
    lang = await _get_user_language(callback=callback)
    if await _deny_if_pending_callback(callback, user_status):
        return
    try:
        _, atype, raw_id = callback.data.split(":", 2)
        address_id = int(raw_id)
    except (ValueError, AttributeError):
        await callback.answer(get_text("errors.default", language=lang), show_alert=True)
        return

    from uk_management_bot.database.models.user import User
    from uk_management_bot.services.request_address import (
        resolve_request_address_sync,
        AddressResolutionError,
    )

    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not user:
            await callback.answer(get_text("errors.default", language=lang), show_alert=True)
            return
        try:
            resolved = resolve_request_address_sync(db, user.id, "applicant", atype, address_id)
        except AddressResolutionError:
            await callback.answer(
                get_text("requests.address_not_available", language=lang), show_alert=True
            )
            return
    finally:
        db.close()

    await state.update_data(
        address=resolved.canonical_address,
        address_type=resolved.address_type,
        address_id=address_id,
        apartment_id=resolved.apartment_id,
        building_id=resolved.building_id,
        yard_id=resolved.yard_id,
    )
    await state.set_state(RequestStates.description)
    try:
        await callback.message.edit_text(
            get_text("requests.address_selected", language=lang, address=resolved.canonical_address)
        )
    except Exception:
        pass
    await callback.message.answer(
        get_text("requests.description", language=lang),
        reply_markup=get_cancel_keyboard(language=lang),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("addr_page:"), RequestStates.address)
async def handle_address_page(callback: CallbackQuery, state: FSMContext):
    """Пагинация inline-списка адресов."""
    lang = await _get_user_language(callback=callback)
    try:
        page = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer()
        return
    from uk_management_bot.keyboards.requests import build_request_address_inline_keyboard

    addresses = _load_user_request_addresses(callback.from_user.id)
    if not _has_any_address(addresses):
        await callback.answer()
        return
    try:
        await callback.message.edit_reply_markup(
            reply_markup=build_request_address_inline_keyboard(addresses, page=page, language=lang)
        )
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "addr_page_noop")
async def handle_address_page_noop(callback: CallbackQuery):
    await callback.answer()


@router.message(RequestStates.address)
async def process_address(message: Message, state: FSMContext):
    """Адрес выбирается ТОЛЬКО inline-кнопками (addr:<type>:<id>). Свободный
    текст отклоняем и переотправляем кнопки — глобальный поиск по тексту убран
    (R17: неуникальный Building.address мог увести в чужой дом)."""
    lang = await _get_user_language(message=message)
    from uk_management_bot.keyboards.requests import build_request_address_inline_keyboard

    addresses = _load_user_request_addresses(message.from_user.id)
    if not _has_any_address(addresses):
        await message.answer(get_text("requests.no_available_addresses", language=lang))
        await state.clear()
        return
    await message.answer(
        get_text("requests.choose_address_prompt", language=lang),
        reply_markup=build_request_address_inline_keyboard(addresses, page=0, language=lang),
    )

# Обработка ввода описания
@router.message(RequestStates.description)
async def process_description(message: Message, state: FSMContext):
    """Обработка ввода описания проблемы"""
    lang = await _get_user_language(message=message)

    if message.text == get_text("buttons.cancel", language=lang):
        await cancel_request(message, state)
        return

    # Валидируем описание с помощью валидатора
    from uk_management_bot.utils.validators import Validator
    is_valid, error_message = Validator.validate_description(message.text, language=lang)
    if not is_valid:
        await message.answer(error_message)
        return

    # Сохраняем описание и переходим к выбору срочности
    await state.update_data(description=message.text)
    await state.set_state(RequestStates.urgency)
    await message.answer(
        get_text("requests.select_urgency", language=lang),
        reply_markup=get_urgency_inline_keyboard(language=lang)
    )
    logger.info(f"Пользователь {message.from_user.id} ввел описание")

# Обработка выбора срочности
@router.message(RequestStates.urgency)
async def process_urgency(message: Message, state: FSMContext):
    """Обработка выбора срочности (квартира больше не запрашивается отдельно)"""
    lang = await _get_user_language(message=message)

    if message.text == get_text("buttons.cancel", language=lang):
        await cancel_request(message, state, lang=lang)
        return

    # Срочность выбирается через inline-клавиатуру. Если пришел текст — показать inline-клавиатуру снова.
    await message.answer(
        get_text("requests.select_urgency", language=lang),
        reply_markup=get_urgency_inline_keyboard(language=lang)
    )
    return

## Шаг квартиры полностью исключён из процесса.

# Обработка медиафайлов
@router.message(RequestStates.media, F.photo | F.video)
async def process_media(message: Message, state: FSMContext):
    """Обработка медиафайлов"""
    lang = await _get_user_language(message=message)

    data = await state.get_data()
    media_files = data.get('media_files', [])

    if len(media_files) >= 5:
        await message.answer(get_text("requests.max_5_files", language=lang))
        return

    # Получаем file_id
    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    else:
        file_id = message.video.file_id
        file_type = "video"

    # Проверяем размер файла (примерная проверка)
    if not validate_media_file(0, file_type):  # Размер файла проверяется на уровне Telegram
        await message.answer(get_text("requests.file_too_large", language=lang))
        return

    media_files.append(file_id)
    await state.update_data(media_files=media_files)

    await message.answer(
        get_text("requests.file_added", language=lang).replace("{...}", str(len(media_files))),
        reply_markup=get_media_keyboard(language=lang)
    )
    logger.info(f"Пользователь {message.from_user.id} добавил медиафайл")

# Обработка текста в состоянии media (продолжить/отмена)
@router.message(RequestStates.media)
async def process_media_text(message: Message, state: FSMContext):
    """Обработка текста в состоянии media"""
    lang = await _get_user_language(message=message)

    if message.text == get_text("buttons.cancel", language=lang):
        await cancel_request(message, state)
        return

    if message.text == get_text("buttons.continue", language=lang):
        await state.set_state(RequestStates.confirm)
        await show_confirmation(message, state)
        return

    await message.answer(
        get_text("requests.send_photo_or_video", language=lang),
        reply_markup=get_media_keyboard(language=lang)
    )

# Показ сводки заявки
async def show_confirmation(message: Message, state: FSMContext):
    """Показать сводку заявки для подтверждения"""
    lang = await _get_user_language(message=message)
    data = await state.get_data()

    # Get localized category name from internal key
    # TASK 17 Этап A: Используем resolve_category_key для обратной совместимости
    from uk_management_bot.keyboards.requests import resolve_category_key, get_category_display
    category_raw = data.get('category')
    # Разрешаем legacy тексты в внутренние ключи
    category_key = resolve_category_key(category_raw)
    # Получаем локализованное отображение
    category_display = get_category_display(category_key, language=lang)

    # Get localized urgency name from internal key
    from uk_management_bot.keyboards.requests import URGENCY_KEYS
    urgency_key = data.get('urgency')
    if urgency_key in URGENCY_KEYS:
        urgency_display = get_text(URGENCY_KEYS[urgency_key], language=lang)
    else:
        # Fallback for old format (localized text was saved directly)
        urgency_display = urgency_key

    summary = get_text(
        "requests.confirmation_summary",
        language=lang,
        category=category_display,
        address=data.get('address', ''),
        description=data.get('description', ''),
        urgency=urgency_display,
        files_count=len(data.get('media_files', []))
    )

    await message.answer(
        summary,
        reply_markup=get_inline_confirmation_keyboard(language=lang)
    )

# Обработка подтверждения
@router.message(RequestStates.confirm)
async def process_confirmation(message: Message, state: FSMContext, db: Session, roles: list = None, active_role: str = None):
    """Обработка подтверждения заявки"""
    lang = await _get_user_language(message=message)

    if message.text == get_text("buttons.cancel", language=lang):
        await cancel_request(message, state, lang=lang)
        return

    if message.text == get_text("buttons.back", language=lang):
        await state.set_state(RequestStates.media)
        await message.answer(
            get_text("requests.back_to_media", language=lang),
            reply_markup=get_media_keyboard(language=lang)
        )
        return

    if message.text == get_text("buttons.confirm", language=lang):
        data = await state.get_data()

        # Сохраняем заявку в базу данных
        request_number = await save_request(
            data, message.from_user.id, db, message.bot, source="bot", role="applicant"
        )

        if request_number:
            await state.clear()
            await message.answer(
                get_text("requests.request_created_success", language=lang),
                reply_markup=get_contextual_keyboard(roles, active_role) if roles and active_role else get_user_contextual_keyboard(message.from_user.id)
            )
            logger.info(f"Пользователь {message.from_user.id} создал заявку")
        else:
            # Очищаем состояние, чтобы пользователь мог продолжить работу (например, открыть Мои заявки)
            await state.clear()
            await message.answer(
                get_text("errors.request_save_failed", language=lang),
                reply_markup=get_user_contextual_keyboard(message.from_user.id)
            )
            logger.error(f"Ошибка создания заявки пользователем {message.from_user.id}")
        return

    await message.answer(
        get_text("requests.select_action", language=lang),
        reply_markup=get_confirmation_keyboard(language=lang)
    )

# Отмена создания заявки
async def cancel_request(message: Message, state: FSMContext, roles: list = None, active_role: str = None, lang: str = "ru"):
    """Отмена создания заявки"""
    await state.clear()
    await message.answer(
        get_text("requests.request_creation_cancelled", language=lang),
        reply_markup=get_user_contextual_keyboard(message.from_user.id)
    )
    logger.info(f"Пользователь {message.from_user.id} отменил создание заявки")

# Сохранение заявки в базу данных
async def save_request(
    data: dict,
    user_id: int,
    db: Session,
    bot: Bot = None,
    source: str = "bot",
    role: str = "applicant",
) -> Optional[str]:
    """Сохранение заявки в базу данных. Возвращает номер заявки (str) или None.

    План «Обходчик»: адрес НЕ доверяем FSM-данным — re-резолвим выбранный
    `(address_type, address_id)` через resolve_request_address_sync (проверка
    принадлежности+активности повторно при сохранении). `source` задаёт
    доверенный call-site (applicant-бот → "bot", обходчик → "inspector"),
    а НЕ FSM/клиент.
    """
    try:
        logger.info(f"[SAVE_REQUEST] Начало сохранения заявки для пользователя {user_id}")
        logger.info(f"[SAVE_REQUEST] Данные FSM: {data.keys()}")
        logger.debug(f"[SAVE_REQUEST] Полные данные: {data}")

        # Валидация обязательных полей (адрес считает сервер из address_type+id).
        # `is None` (а не truthiness) — address_id=0 теоретически валиден.
        required_fields = ['category', 'address_type', 'address_id', 'description', 'urgency']
        missing_fields = [field for field in required_fields if data.get(field) is None]

        if missing_fields:
            logger.error(f"[SAVE_REQUEST] Отсутствуют обязательные поля: {missing_fields}")
            logger.error(f"[SAVE_REQUEST] Доступные поля: {list(data.keys())}")
            return None

        # Получаем пользователя из базы данных по telegram_id
        from uk_management_bot.database.models.user import User
        user = db.query(User).filter(User.telegram_id == user_id).first()

        if not user:
            logger.error(f"[SAVE_REQUEST] Пользователь с telegram_id {user_id} не найден в базе данных")
            return None

        logger.info(f"[SAVE_REQUEST] Пользователь найден: {user.username} (ID: {user.id})")

        # Re-резолв адреса при сохранении (принадлежность+активность ещё раз).
        from uk_management_bot.services.request_address import (
            resolve_request_address_sync,
            AddressResolutionError,
        )
        try:
            resolved = resolve_request_address_sync(
                db, user.id, role, data['address_type'], int(data['address_id'])
            )
        except AddressResolutionError as e:
            logger.warning(f"[SAVE_REQUEST] Резолв адреса отклонён ({e.status_code}): {e.message}")
            return None

        # Генерируем уникальный номер заявки (PR5: атомарный счётчик дня;
        # row-lock счётчика держится до commit → НИКАКОГО сетевого I/O до
        # commit — media upload перенесён ПОСЛЕ него).
        request_number = Request.generate_request_number(db)
        logger.info(f"[SAVE_REQUEST] Сгенерирован номер заявки: {request_number}")

        media_file_ids = data.get('media_files', [])

        logger.info("[SAVE_REQUEST] Создание объекта заявки...")
        request = Request(
            request_number=request_number,
            category=data['category'],
            # Адрес и FK — из резолвера (сервер), а не из FSM/клиента.
            address=resolved.canonical_address,
            description=data['description'],
            urgency=data['urgency'],
            apartment_id=resolved.apartment_id,
            building_id=resolved.building_id,
            yard_id=resolved.yard_id,
            address_type=resolved.address_type,
            # В модели media_files ожидается JSON (список), поэтому сохраняем список
            # Теперь храним file_ids как backup, основное хранилище - Media Service
            media_files=list(media_file_ids),
            user_id=user.id,  # Используем id пользователя из базы данных
            source=source,
            status='Новая'
        )

        logger.info("[SAVE_REQUEST] Сохранение в БД...")
        db.add(request)

        # ARCH-113: emit + INSERT in one transaction — protects against orphan
        # requests (request row durable but outbox row missing on commit failure).
        # source задаёт доверенный call-site (не FSM): applicant→"bot", обходчик→"inspector".
        from uk_management_bot.services.webhook_payloads import emit_request_created_sync
        emit_request_created_sync(db, request, source=source)

        db.commit()

        logger.info(f"[SAVE_REQUEST] ✅ Заявка {request_number} успешно сохранена")

        # FEAT-группы: авто-dispatch на группу-специализацию (Новая→В работе +
        # group-назначение) через канонический run_command. Best-effort — ошибка
        # не валит уже-созданную заявку. ПОСЛЕ commit (своя сессия, свой лок).
        from uk_management_bot.services.dispatch import auto_dispatch_new_request_sync
        auto_dispatch_new_request_sync(request_number, data['category'])

        # PR5: загрузка медиа в Media Service — ПОСЛЕ commit (раньше шла между
        # генерацией номера и INSERT, удерживая блокировки на время сетевого
        # I/O). Результат upload'а в Request не сохраняется (media_files несёт
        # telegram file_ids как backup), поэтому перенос ничего не меняет в
        # данных; заявка уже durable, ошибка upload — как и раньше не фатальна.
        if media_file_ids and bot:
            logger.info(f"[SAVE_REQUEST] Начало загрузки {len(media_file_ids)} файлов в Media Service")
            from uk_management_bot.utils.media_helpers import upload_multiple_telegram_files
            try:
                uploaded_files = await upload_multiple_telegram_files(
                    bot=bot,
                    file_ids=media_file_ids,
                    request_number=request_number,
                    uploaded_by=user.id
                )
                logger.info(f"[SAVE_REQUEST] Загружено {len(uploaded_files)} файлов в Media Service для заявки {request_number}")
            except Exception as e:
                logger.error(f"[SAVE_REQUEST] Ошибка загрузки файлов в Media Service: {e}", exc_info=True)
                # Заявка уже сохранена; недогруженные медиа не блокируют создание

        return request_number
    except Exception as e:
        logger.error(f"[SAVE_REQUEST] ❌ Ошибка сохранения заявки: {e}", exc_info=True)
        return None

# =====================================
# ОБРАБОТЧИКИ CALLBACK_QUERY ДЛЯ INLINE КЛАВИАТУР
# =====================================

@router.callback_query(F.data.startswith("category_"))
async def handle_category_selection(callback: CallbackQuery, state: FSMContext, user_status: Optional[str] = None):
    """Обработка выбора категории заявки через inline клавиатуру"""
    # Get user language
    lang = await _get_user_language(callback=callback)

    if await _deny_if_pending_callback(callback, user_status):
        return

    try:
        logger.info(f"Обработка выбора категории для пользователя {callback.from_user.id}")

        # Извлекаем внутренний ключ категории из callback данных
        category_internal_key = callback.data.replace("category_", "")

        # Импортируем CATEGORY_INTERNAL_KEYS из keyboards
        from uk_management_bot.keyboards.requests import CATEGORY_INTERNAL_KEYS, CATEGORY_KEYS

        # Валидируем категорию (теперь проверяем внутренний ключ)
        if category_internal_key not in CATEGORY_INTERNAL_KEYS:
            await callback.answer(
                get_text("errors.invalid_category", language=lang),
                show_alert=True
            )
            logger.warning(f"Неверная категория '{category_internal_key}' от пользователя {callback.from_user.id}")
            return

        # Сохраняем внутренний ключ в FSM
        await state.update_data(category=category_internal_key)
        logger.info(f"Категория '{category_internal_key}' сохранена в state для пользователя {callback.from_user.id}")

        # Получаем локализованное название категории для отображения
        category_locale_key = CATEGORY_KEYS[category_internal_key]
        category_display = get_text(category_locale_key, language=lang)

        # Переходим к следующему состоянию
        await state.set_state(RequestStates.address)

        # Информационное редактирование исходного сообщения
        await callback.message.edit_text(
            get_text("requests.category_selected", language=lang, category=category_display)
        )

        # Отправляем inline-кнопки выбора адреса (callback addr:<type>:<id>),
        # строго из набора жителя. Свободный текст/глобальный поиск убран (R17).
        try:
            from uk_management_bot.keyboards.requests import build_request_address_inline_keyboard

            addresses = _load_user_request_addresses(callback.from_user.id)
            if not _has_any_address(addresses):
                await callback.message.answer(
                    get_text("requests.no_available_addresses", language=lang)
                )
                await state.clear()
                await callback.answer()
                return
            # Прячем ReplyKeyboard главного меню на время выбора.
            await callback.message.answer(
                get_text("requests.select_address", language=lang),
                reply_markup=ReplyKeyboardRemove(),
            )
            await callback.message.answer(
                get_text("requests.choose_address_prompt", language=lang),
                reply_markup=build_request_address_inline_keyboard(addresses, page=0, language=lang),
            )
            logger.info(f"Inline-клавиатура адресов отправлена пользователю {callback.from_user.id}")
        except Exception as keyboard_error:
            logger.error(f"Ошибка создания клавиатуры адресов: {keyboard_error}", exc_info=True)
            await callback.message.answer(get_text("errors.default", language=lang))
            await state.clear()
            await callback.answer()
            return

        await callback.answer()  # Убираем "часики" на кнопке
        logger.info(f"Пользователь {callback.from_user.id} выбрал категорию: {category_internal_key}")

    except Exception as e:
        logger.error(f"Ошибка обработки выбора категории: {e}", exc_info=True)
        await callback.answer(
            get_text("errors.default", language=lang),
            show_alert=True
        )


@router.callback_query(F.data == "cancel_create")
async def handle_cancel_create(callback: CallbackQuery, state: FSMContext):
    """Отмена создания заявки из выбора категории (inline)."""
    lang = await _get_user_language(callback=callback)

    try:
        user_id = callback.from_user.id
        logger.info(f"[CANCEL_CREATE] Пользователь {user_id} отменил создание заявки через inline-кнопку")

        await state.clear()
        await callback.message.edit_text(get_text("requests.request_creation_cancelled", language=lang))
        await callback.message.answer(
            get_text("requests.return_to_main", language=lang),
            reply_markup=get_user_contextual_keyboard(callback.from_user.id)
        )
        await callback.answer()

        logger.info(f"[CANCEL_CREATE] Состояние очищено для пользователя {user_id}")
    except Exception as e:
        logger.error(f"Ошибка отмены создания заявки: {e}")
        await callback.answer(get_text("errors.default", language=lang), show_alert=True)

@router.callback_query(F.data.startswith("urgency_"))
async def handle_urgency_selection(callback: CallbackQuery, state: FSMContext, user_status: Optional[str] = None):
    """Обработка выбора уровня срочности через inline клавиатуру"""
    lang = await _get_user_language(callback=callback)

    if await _deny_if_pending_callback(callback, user_status):
        return
    try:
        logger.info(f"Обработка выбора срочности для пользователя {callback.from_user.id}")

        urgency_internal_key = callback.data.replace("urgency_", "")

        from uk_management_bot.keyboards.requests import URGENCY_INTERNAL_KEYS, URGENCY_KEYS

        if urgency_internal_key not in URGENCY_INTERNAL_KEYS:
            await callback.answer(get_text("errors.invalid_urgency", language=lang), show_alert=True)
            logger.warning(f"Неверная срочность '{urgency_internal_key}' от пользователя {callback.from_user.id}")
            return

        # Сохраняем внутренний ключ срочности в FSM
        await state.update_data(urgency=urgency_internal_key)
        logger.info(f"Срочность '{urgency_internal_key}' сохранена в state для пользователя {callback.from_user.id}")

        # Переходим к следующему состоянию
        await state.set_state(RequestStates.media)

        # Получаем локализованное отображение срочности
        urgency_locale_key = URGENCY_KEYS[urgency_internal_key]
        urgency_display = get_text(urgency_locale_key, language=lang)

        # Редактируем исходное сообщение
        await callback.message.edit_text(
            get_text("requests.urgency_selected", language=lang, urgency=urgency_display)
        )

        # Отправляем новое сообщение с клавиатурой для медиа
        try:
            keyboard = get_media_keyboard(language=lang)
            await callback.message.answer(
                get_text("requests.send_photo_or_video", language=lang),
                reply_markup=keyboard
            )
            logger.info(f"Клавиатура медиа отправлена пользователю {callback.from_user.id}")
        except Exception as keyboard_error:
            logger.error(f"Ошибка создания клавиатуры медиа: {keyboard_error}", exc_info=True)
            # Fallback - показываем простую клавиатуру с кнопками
            fallback_keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text=get_text("buttons.continue", language=lang))],
                    [KeyboardButton(text=get_text("buttons.cancel", language=lang))]
                ],
                resize_keyboard=True
            )
            await callback.message.answer(
                get_text("requests.send_photo_or_video", language=lang),
                reply_markup=fallback_keyboard
            )

        await callback.answer()  # Убираем "часики" на кнопке
        logger.info(f"Пользователь {callback.from_user.id} выбрал срочность: {urgency_internal_key}, переход к медиа")

    except Exception as e:
        logger.error(f"Ошибка обработки выбора срочности: {e}", exc_info=True)
        await callback.answer(get_text("errors.default", language=lang), show_alert=True)

@router.callback_query(F.data.in_({"confirm_yes", "confirm_no"}))
async def handle_confirmation(callback: CallbackQuery, state: FSMContext, user_status: Optional[str] = None):
    """Обработка подтверждения заявки через inline клавиатуру"""
    lang = await _get_user_language(callback=callback)

    if await _deny_if_pending_callback(callback, user_status):
        return
    db_session = None          # ARCH-013: гарантируем close в finally
    try:
        logger.info(f"Обработка подтверждения для пользователя {callback.from_user.id}")

        action = callback.data.replace("confirm_", "")

        if action == "yes":
            # Получаем данные из FSM
            data = await state.get_data()

            # Создаем заявку в базе данных
            db_session = next(get_db())
            request_number = await save_request(
                data, callback.from_user.id, db_session, callback.bot, source="bot", role="applicant"
            )

            if request_number:
                # Get localized display values for category and urgency
                from uk_management_bot.keyboards.requests import CATEGORY_KEYS, URGENCY_KEYS

                category_key = data.get('category')
                if category_key in CATEGORY_KEYS:
                    category_display = get_text(CATEGORY_KEYS[category_key], language=lang)
                else:
                    category_display = category_key or get_text("common.not_specified", language=lang)

                urgency_key = data.get('urgency')
                if urgency_key in URGENCY_KEYS:
                    urgency_display = get_text(URGENCY_KEYS[urgency_key], language=lang)
                else:
                    urgency_display = urgency_key or get_text("urgency.low", language=lang)

                # Редактируем исходное сообщение без ReplyKeyboardMarkup
                await callback.message.edit_text(
                    get_text(
                        "requests.request_created_details",
                        language=lang,
                        request_number=request_number,
                        category=category_display,
                        address=data.get('address', get_text("common.not_specified", language=lang)),
                        urgency=urgency_display
                    )
                )
                # Отправляем отдельное сообщение с главной клавиатурой
                await callback.message.answer(
                    get_text("requests.return_to_main", language=lang),
                    reply_markup=get_user_contextual_keyboard(callback.from_user.id)
                )
                await state.clear()
                logger.info(f"Заявка создана пользователем {callback.from_user.id}")
            else:
                # Очищаем состояние и показываем главное меню, чтобы пользователь мог продолжить
                await state.clear()
                await callback.message.answer(
                    get_text("errors.request_save_failed", language=lang),
                    reply_markup=get_user_contextual_keyboard(callback.from_user.id)
                )
                await callback.answer(get_text("errors.request_save_failed", language=lang), show_alert=True)

        elif action == "no":
            await callback.message.edit_text(
                get_text("requests.request_creation_cancelled", language=lang)
            )
            await callback.message.answer(
                get_text("requests.return_to_main", language=lang),
                reply_markup=get_user_contextual_keyboard(callback.from_user.id)
            )
            await state.clear()
            logger.info(f"Создание заявки отменено пользователем {callback.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка обработки подтверждения: {e}")
        await callback.answer(get_text("errors.default", language=lang), show_alert=True)
    finally:
        if db_session:
            db_session.close()


def _get_executor_requests_query(db_session: Session, user: User):
    """Заявки исполнителя — ТОЛЬКО его персональные (individual / взятые).

    FEAT-группы: непривязанные group-назначения здесь больше НЕ показываем — они
    в отдельном «пуле свободных» (`_get_group_pool_query`). Сюда заявка попадает
    лишь ПОСЛЕ взятия (EXECUTOR_CLAIM конвертирует group→individual,
    executor_id := взявший).
    """
    from sqlalchemy.orm import aliased
    assignment_alias = aliased(RequestAssignment)

    query = db_session.query(Request).outerjoin(
        assignment_alias, Request.request_number == assignment_alias.request_number
    )
    conditions = [
        # активное individual-назначение на меня
        (assignment_alias.status == "active") & (assignment_alias.executor_id == user.id),
        # fallback: прямое Request.executor_id (заявки без RequestAssignment)
        Request.executor_id == user.id,
    ]
    query = query.filter(or_(*conditions))

    # Дедупликация: подзапрос по request_number, т.к. DISTINCT на всех колонках
    # не работает с JSON полями в PostgreSQL
    request_numbers_subq = query.with_entities(Request.request_number).distinct().subquery()
    return db_session.query(Request).filter(
        Request.request_number.in_(db_session.query(request_numbers_subq.c.request_number))
    )


def _get_group_pool_query(db_session: Session, user: User):
    """FEAT-группы: пул «свободных» group-заявок для исполнителя.

    Видны ТОЛЬКО дежурному сейчас (on-shift): заявки «В работе» с активным
    group-назначением по его специализации и БЕЗ исполнителя (executor_id NULL).
    Не на смене / без специализаций → пустой набор.
    """
    from sqlalchemy import false
    from sqlalchemy.orm import aliased
    from uk_management_bot.utils.shifts import is_on_shift_now_sync
    from uk_management_bot.utils.specializations import parse_specializations

    specs = parse_specializations(user)
    if not specs or not is_on_shift_now_sync(db_session, user.id):
        return db_session.query(Request).filter(false())

    assignment_alias = aliased(RequestAssignment)
    query = db_session.query(Request).join(
        assignment_alias, Request.request_number == assignment_alias.request_number
    ).filter(
        Request.status.in_(["В работе"]),
        assignment_alias.status == "active",
        assignment_alias.assignment_type == "group",
        assignment_alias.executor_id.is_(None),
        assignment_alias.group_specialization.in_(specs),
    )
    request_numbers_subq = query.with_entities(Request.request_number).distinct().subquery()
    return db_session.query(Request).filter(
        Request.request_number.in_(db_session.query(request_numbers_subq.c.request_number))
    )


@router.callback_query(F.data.startswith("page_"))
async def handle_pagination(callback: CallbackQuery, state: FSMContext):
    """Обработка пагинации списков заявок"""
    db_session = None          # ARCH-013: гарантируем close в finally
    try:
        logger.info(f"Обработка пагинации для пользователя {callback.from_user.id}")

        # Парсим данные пагинации
        current_page = int(callback.data.replace("page_", ""))

        # Читаем активный фильтр из FSM
        data = await state.get_data()
        active_status = data.get("my_requests_status")

        # Получаем список заявок пользователя с учетом фильтра
        db_session = next(get_db())
        lang = get_user_language(callback.from_user.id, db_session)

        # Получаем пользователя из базы данных по telegram_id
        from uk_management_bot.database.models.user import User
        user = db_session.query(User).filter(User.telegram_id == callback.from_user.id).first()

        if not user:
            await callback.answer(get_text("common.user_not_found", language=lang), show_alert=True)
            return

        # Определяем активную роль пользователя
        user_roles = user.roles.strip('[]').replace('"', '').split(', ') if user.roles else []
        active_role = user.active_role or (user_roles[0] if user_roles else "applicant")

        # Получаем заявки в зависимости от роли
        if active_role == "executor":
            # Для исполнителей используем вспомогательную функцию
            query = _get_executor_requests_query(db_session, user)
        else:
            # Для заявителей и других ролей
            query = db_session.query(Request).filter(Request.user_id == user.id)

        # Применяем фильтр статуса
        if active_status == "active":
            query = query.filter(Request.status.in_(["Новая", "В работе", "Закуп", "Уточнение"]))
        elif active_status == "archive":
            query = query.filter(Request.status.in_(["Выполнена", "Исполнено", "Принято", "Отменена"]))

        user_requests = query.order_by(Request.created_at.desc()).all()

        # Вычисляем общее количество страниц
        total_requests = len(user_requests)
        requests_per_page = 5
        total_pages = max(1, (total_requests + requests_per_page - 1) // requests_per_page)
        
        if current_page < 1 or current_page > total_pages:
            await callback.answer(get_text("requests.page_not_found", language=lang), show_alert=True)
            return

        # Получаем заявки для текущей страницы
        start_idx = (current_page - 1) * requests_per_page
        end_idx = start_idx + requests_per_page
        page_requests = user_requests[start_idx:end_idx]

        # BUG-BOT-008: Унифицированный заголовок (см. format_requests_list_header).
        # Использует единый шаблон для Page1/Page2/Активные/Архив.
        from uk_management_bot.utils.request_helpers import format_requests_list_header
        message_text = format_requests_list_header(
            total_requests=total_requests,
            current_page=current_page,
            total_pages=total_pages,
            status_filter=active_status or "all",
            role=active_role,
            language=lang,
        )
        # TASK 17 Этап A: Используем resolve_category_key и get_category_display для нормализации категорий
        # TASK 17 Этап C: Локализуем статусы через status_display.py
        from uk_management_bot.keyboards.requests import resolve_category_key, get_category_display
        for i, request in enumerate(page_requests, 1):
            category_key = resolve_category_key(request.category)
            category_display = get_category_display(category_key, language=lang)
            status_display = _sd_get_status_display(request.status, language=lang)
            icon = STATUS_EMOJI.get(request.status, "📋")
            message_text += f"{i}. {icon} #{request.request_number} - {category_display} - {status_display}\n"
            # TASK 17 Этап C: Локализованные метки
            address_label = get_text("requests.address_label", language=lang) or "Адрес"
            created_label = get_text("requests.created_label", language=lang) or "Создана"
            from uk_management_bot.utils.address_helpers import localize_address
            message_text += f"   {address_label} {localize_address(request.address, lang)}\n"
            message_text += f"   {created_label} {request.created_at.strftime('%d.%m.%Y')}\n"
            if request.status == "Отменена" and request.notes:
                # TASK 17 Этап C: Локализованная метка
                reason_label = get_text("requests.cancellation_reason_label", language=lang) or "Причина отказа"
                message_text += f"   {reason_label} {request.notes}\n"
            elif request.status == "Уточнение" and request.notes:
                # Показываем последние сообщения из диалога уточнения
                # TASK 17 Этап C: Локализованная метка
                clarification_label = get_text("requests.clarification_label", language=lang) or "Уточнение"
                notes_lines = request.notes.strip().split('\n')
                last_messages = [line for line in notes_lines[-3:] if line.strip()]  # Последние 3 сообщения
                if last_messages:
                    preview = '\n'.join(last_messages)
                    if len(preview) > 100:
                        preview = preview[:97] + '...'
                    message_text += f"   {clarification_label}: {preview}\n"
            message_text += "\n"
        
        # Создаем комбинированную клавиатуру: фильтр + кнопки ответа (по каждой) + пагинация
        from uk_management_bot.keyboards.requests import get_pagination_keyboard
        from uk_management_bot.keyboards.requests import get_status_filter_inline_keyboard
        filter_kb = get_status_filter_inline_keyboard(active_status if active_status != "all" else None, language=lang)
        rows = list(filter_kb.inline_keyboard)
        for i, r in enumerate(page_requests, 1):
            if r.status == "Уточнение":
                # TASK 17 Этап C: Локализованная кнопка ответа
                reply_text = get_text("buttons.reply", language=lang) or "💬 Ответить"
                rows.append([InlineKeyboardButton(text=f"{reply_text} по #{r.request_number}", callback_data=f"replyclarify_{r.request_number}")])
        pagination_kb = get_pagination_keyboard(current_page, total_pages, request_number=None, show_reply_clarify=False)
        rows += pagination_kb.inline_keyboard
        combined = InlineKeyboardMarkup(inline_keyboard=rows)

        # Сохраняем текущую страницу в FSM
        await state.update_data(my_requests_page=current_page)

        try:
            await callback.message.edit_text(message_text, reply_markup=combined)
        except TelegramBadRequest:
            pass
        
        logger.info(f"Показана страница {current_page} для пользователя {callback.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка обработки пагинации: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("common.error", language=lang), show_alert=True)
    finally:
        if db_session:
            db_session.close()

@router.callback_query(
    # BUG-BOT-033 fix: replace fragile prefix-match + maintained exclusion list
    # with strict regex matching request_number format `view_<YYMMDD-NNN>` or
    # `view_request_<YYMMDD-NNN>`. Any other view_* callback (view_current_shifts,
    # view_apartment:N, view_week_schedule, etc.) is no longer hijacked here and
    # reaches its own handler in a later router.
    F.data.regexp(_VIEW_REQUEST_NUMBER_RE)
)
async def handle_view_request(callback: CallbackQuery, state: FSMContext):
    """Обработка просмотра деталей заявки"""
    db_session = None          # ARCH-013: гарантируем close в finally
    try:
        logger.info(f"Обработка просмотра заявки для пользователя {callback.from_user.id}")

        # Извлекаем номер заявки из callback_data (view_ или view_request_)
        request_number = callback.data.replace("view_request_", "").replace("view_", "")

        # Получаем заявку из базы данных
        db_session = next(get_db())
        lang = get_user_language(callback.from_user.id, db_session)

        request = db_session.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await callback.answer(get_text("requests.request_not_found", language=lang), show_alert=True)
            return

        # Получаем пользователя и проверяем права доступа
        from uk_management_bot.database.models.user import User
        from uk_management_bot.database.models.request_assignment import RequestAssignment
        user = db_session.query(User).filter(User.telegram_id == callback.from_user.id).first()

        if not user:
            await callback.answer(get_text("common.user_not_found", language=lang), show_alert=True)
            return

        # Определяем роль пользователя
        user_roles = []
        if user.roles:
            try:
                import json
                user_roles = json.loads(user.roles) if isinstance(user.roles, str) else user.roles
            except (json.JSONDecodeError, TypeError):
                user_roles = []

        active_role = user.active_role or (user_roles[0] if user_roles else "applicant")

        # Проверяем права доступа в зависимости от роли
        has_access = False

        if active_role == "executor":
            # BUG-BOT-004: прямое назначение через Request.executor_id (FK)
            # имеет приоритет — если исполнитель назначен напрямую, он видит заявку
            # независимо от наличия записей в RequestAssignment.
            if request.executor_id == user.id:
                has_access = True

            # Для исполнителей: проверяем назначение
            assignment = db_session.query(RequestAssignment).filter(
                RequestAssignment.request_number == request.request_number,
                RequestAssignment.status == "active"
            ).first()

            if not has_access and assignment:
                # Индивидуальное назначение
                if assignment.executor_id == user.id:
                    has_access = True
                # Групповое назначение по специализациям
                elif assignment.assignment_type == "group":
                    # Получаем ВСЕ специализации исполнителя
                    executor_specializations = []
                    if user.specialization:
                        try:
                            if isinstance(user.specialization, str) and user.specialization.startswith('['):
                                executor_specializations = json.loads(user.specialization)
                            else:
                                executor_specializations = [user.specialization]
                        except (json.JSONDecodeError, TypeError):
                            executor_specializations = [user.specialization] if user.specialization else []

                    # Проверяем, есть ли совпадение с хотя бы одной специализацией
                    if assignment.group_specialization in executor_specializations:
                        has_access = True
        else:
            # Для заявителей и других ролей: проверяем владение заявкой или квартиры
            if request.user_id == user.id:
                has_access = True
            elif request.apartment_id:
                from uk_management_bot.database.models.user_apartment import UserApartment
                is_resident = db_session.query(UserApartment).filter(
                    UserApartment.user_id == user.id,
                    UserApartment.apartment_id == request.apartment_id,
                    UserApartment.status == "approved",
                ).first()
                if is_resident:
                    has_access = True

        if not has_access:
            await callback.answer(get_text("requests.no_access_to_request", language=lang), show_alert=True)
            return

        # TASK 17 Issue #4: Use localized helper function for request details
        # Replaces 18 lines of hard-coded Russian text with reusable helper
        from uk_management_bot.utils.request_helpers import format_request_details

        message_text = format_request_details(
            request=request,
            language=lang,
            show_executor=True,
            active_role=active_role,
            db_session=db_session
        )

        # Check media files for keyboard logic
        has_media = bool(request.media_files)
        media_count = 0
        if has_media:
            try:
                import json
                media_files = json.loads(request.media_files) if isinstance(request.media_files, str) else request.media_files
                media_count = len(media_files) if media_files else 0
                if media_count == 0:
                    has_media = False
            except (json.JSONDecodeError, TypeError):
                has_media = False

        # Создаем клавиатуру в зависимости от роли
        rows = []

        if active_role == "executor":
            # Для исполнителей: только действия по работе с заявкой
            # TASK 17 Этап C: Локализованные кнопки
            if request.status == "В работе" and request.executor_id is None:
                # FEAT-группы: непривязанная group-заявка → «Взять» (а не
                # Выполнена/Закуп — работать может только взявший; авторизацию
                # взятия проверяет EXECUTOR_CLAIM в claim-callback).
                claim_text = get_text("requests.executor_claim_button", language=lang) or "🙋 Взять в работу"
                rows.append([InlineKeyboardButton(text=claim_text, callback_data=f"claim_request_{request.request_number}")])
            elif request.status == "В работе":
                complete_text = get_text("buttons.complete", language=lang) or "✅ Выполнена"
                purchase_text = get_text("buttons.purchase", language=lang) or "💰 Нужен закуп"
                rows.append([InlineKeyboardButton(text=complete_text, callback_data=f"executor_complete_{request.request_number}")])
                rows.append([InlineKeyboardButton(text=purchase_text, callback_data=f"executor_purchase_{request.request_number}")])
            elif request.status == "Закуп":
                back_to_work_text = get_text("buttons.back_to_work", language=lang) or "🔄 Вернуть в работу"
                rows.append([InlineKeyboardButton(text=back_to_work_text, callback_data=f"executor_work_{request.request_number}")])
            elif request.status == "Уточнение":
                back_to_work_text = get_text("buttons.back_to_work", language=lang) or "🔄 Вернуть в работу"
                rows.append([InlineKeyboardButton(text=back_to_work_text, callback_data=f"executor_work_{request.request_number}")])
            elif request.status in ["Выполнена", "Исполнено", "Принято"]:
                # Заявка завершена - только просмотр
                pass

            # Кнопка просмотра медиа (если есть)
            # TASK 17 Этап C: Локализованная кнопка
            if has_media:
                view_media_text = get_text("buttons.view_media", language=lang) or "📎 Просмотр медиа"
                rows.append([InlineKeyboardButton(text=view_media_text, callback_data=f"executor_view_media_{request.request_number}")])
        elif active_role in ["admin", "manager"]:
            # Для менеджеров/админов: полная клавиатура управления
            # TASK 17 Этап C: Передаём язык для локализации кнопок
            from uk_management_bot.keyboards.requests import get_request_actions_keyboard
            actions_kb = get_request_actions_keyboard(request.request_number, language=lang)
            rows = list(actions_kb.inline_keyboard)
        else:
            # Для заявителей: ограниченная клавиатура (только просмотр и ответ на уточнения)
            # TASK 17 Этап C: Локализованные кнопки
            if request.status == "Уточнение":
                # Если требуется уточнение - кнопка ответа
                reply_text = get_text("buttons.reply", language=lang) or "💬 Ответить"
                rows.append([InlineKeyboardButton(text=reply_text, callback_data=f"replyclarify_{request.request_number}")])
            # Кнопка "Подтвердить" убрана - для этого есть отдельное меню "Ожидают приёмки"

            # Кнопка просмотра медиа (если есть)
            if has_media:
                view_media_text = get_text("buttons.view_media", language=lang) or "📎 Просмотр медиа"
                rows.append([InlineKeyboardButton(text=view_media_text, callback_data=f"view_request_media_{request.request_number}")])

        # Добавляем кнопку "Назад к списку"
        # TASK 17 Этап C: Локализованная кнопка
        data = await state.get_data()
        current_page = int(data.get("my_requests_page", 1))
        back_to_list_text = get_text("buttons.back_to_list", language=lang) or "🔙 Назад к списку"
        rows.append([InlineKeyboardButton(text=back_to_list_text, callback_data=f"back_list_{current_page}")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

        await callback.message.edit_text(message_text, reply_markup=keyboard)
        
        logger.info(f"Показаны детали заявки {request.request_number} для пользователя {callback.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка обработки просмотра заявки: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("common.error", language=lang), show_alert=True)
    finally:
        if db_session:
            db_session.close()


@router.callback_query(F.data.startswith("back_list_"))
async def handle_back_to_list(callback: CallbackQuery, state: FSMContext):
    """Возврат из деталей заявки к списку с восстановлением страницы и фильтра"""
    db_session = None          # ARCH-013: гарантируем close в finally
    try:
        # Восстанавливаем страницу из callback_data
        page = int(callback.data.replace("back_list_", ""))
        await state.update_data(my_requests_page=page)

        # Удаляем текущее сообщение с деталями
        await callback.message.delete()

        # Получаем данные пользователя
        telegram_id = callback.from_user.id
        data = await state.get_data()
        active_status = data.get("my_requests_status", "active")
        current_page = int(data.get("my_requests_page", 1))

        db_session = next(get_db())
        lang = get_user_language(callback.from_user.id, db_session)

        user = db_session.query(User).filter(User.telegram_id == telegram_id).first()

        if not user:
            await callback.message.answer(get_text("common.user_not_found", language=lang))
            await callback.answer()
            return

        # Определяем роль пользователя
        user_roles = []
        if user.roles:
            try:
                import json
                user_roles = json.loads(user.roles) if isinstance(user.roles, str) else user.roles
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Ошибка парсинга ролей пользователя {user.id}: {e}")
                user_roles = []

        active_role = user.active_role or (user_roles[0] if user_roles else "applicant")

        # Получаем заявки в зависимости от роли
        if active_role == "executor":
            # Для исполнителей: показываем заявки, назначенные им или их специализации (если в активной смене)
            from uk_management_bot.database.models.request_assignment import RequestAssignment
            from uk_management_bot.database.models.shift import Shift
            from datetime import datetime

            # Получаем специализации исполнителя (может быть несколько)
            executor_specializations = []
            if user.specialization:
                try:
                    import json
                    if isinstance(user.specialization, str) and user.specialization.startswith('['):
                        executor_specializations = json.loads(user.specialization)
                    else:
                        executor_specializations = [user.specialization]
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Ошибка парсинга специализации пользователя {user.id}: {e}")
                    executor_specializations = [user.specialization] if user.specialization else []

            # Проверяем, есть ли активная смена
            now = datetime.now()
            active_shift = db_session.query(Shift).filter(
                Shift.user_id == user.id,
                Shift.status == "active",
                Shift.start_time <= now,
                or_(Shift.end_time.is_(None), Shift.end_time >= now)
            ).first()

            has_active_shift = active_shift is not None

            # Запрос назначенных заявок
            query = db_session.query(Request).join(RequestAssignment).filter(
                RequestAssignment.status == "active"
            )

            # Фильтруем по назначениям
            assignment_conditions = []

            # 1. Индивидуальные назначения (ВСЕГДА показываем)
            assignment_conditions.append(RequestAssignment.executor_id == user.id)

            # 2. Групповые назначения по специализациям (ТОЛЬКО если в активной смене)
            if has_active_shift and executor_specializations:
                for spec in executor_specializations:
                    assignment_conditions.append(
                        (RequestAssignment.assignment_type == "group") &
                        (RequestAssignment.group_specialization == spec)
                    )

            if assignment_conditions:
                query = query.filter(or_(*assignment_conditions))
            else:
                query = query.filter(RequestAssignment.executor_id == user.id)

        else:
            # Для заявителей и других ролей: показываем их собственные заявки
            query = db_session.query(Request).filter(Request.user_id == user.id)

        # Фильтр по статусу: только для не-исполнителей
        if active_role != "executor":
            if active_status == "active":
                query = query.filter(Request.status.in_(["Новая", "В работе", "Закуп", "Уточнение"]))
            elif active_status == "archive":
                query = query.filter(Request.status.in_(["Выполнена", "Исполнено", "Принято", "Отменена"]))
            elif active_status == "all":
                # Все заявки: без фильтра по статусу
                pass

        # Сортировка и пагинация
        if active_role != "executor" and active_status == "all":
            from sqlalchemy import case
            # Для "all" сортируем: сначала активные, потом архивные, внутри по дате
            status_priority = case(
                (Request.status.in_(["Новая", "В работе", "Закуп", "Уточнение"]), 0),  # Активные
                else_=1  # Архивные
            )
            query = query.order_by(status_priority, Request.created_at.desc())
        else:
            query = query.order_by(Request.created_at.desc())

        # Подсчет общего количества
        total_requests = query.count()

        # Пагинация
        ITEMS_PER_PAGE = 5
        total_pages = (total_requests + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
        offset = (current_page - 1) * ITEMS_PER_PAGE

        requests = query.offset(offset).limit(ITEMS_PER_PAGE).all()

        # TASK 17 Issue #5: Use localized helper functions for list formatting
        from uk_management_bot.utils.request_helpers import (
            format_requests_list_header,
            format_request_list_item,
            get_status_icon
        )

        if not requests:
            # Empty state message
            if active_role == "executor":
                title = get_text('requests.assigned_requests_title', language=lang)
                empty_msg = get_text('requests.no_assigned_requests', language=lang) or "У вас пока нет назначенных заявок."
                message_text = f"📋 <b>{title}</b>\n\n{empty_msg}"
            else:
                if active_status == "active":
                    title = get_text('requests.active_requests_title', language=lang)
                    empty_msg = get_text('requests.no_active_requests', language=lang) or "У вас пока нет активных заявок."
                elif active_status == "archive":
                    title = get_text('requests.archive_title', language=lang)
                    empty_msg = get_text('requests.no_archive_requests', language=lang) or "У вас пока нет заявок в архиве."
                else:
                    title = get_text('requests.all_filter', language=lang)
                    empty_msg = get_text('requests.no_requests', language=lang) or "У вас пока нет заявок."
                message_text = f"📋 <b>{title}</b>\n\n{empty_msg}"

            await callback.message.answer(message_text, parse_mode="HTML")
            await callback.answer()
            return

        # Format list header
        message_text = format_requests_list_header(
            total_requests=total_requests,
            current_page=current_page,
            total_pages=total_pages,
            status_filter=active_status,
            role=active_role,
            language=lang
        )

        # Для заявителей - текстовый список, для исполнителей - кнопки
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()

        if active_role != "executor":
            # Текстовый список для заявителей (используем helper-функцию)
            for i, req in enumerate(requests, 1):
                message_text += format_request_list_item(
                    request=req,
                    index=i,
                    language=lang,
                    show_details=True
                )
        else:
            # Кнопки для исполнителей
            # TASK 17 Этап A: Используем resolve_category_key и get_category_display для нормализации категорий
            from uk_management_bot.keyboards.requests import resolve_category_key, get_category_display
            for req in requests:
                icon = get_status_icon(req.status)
                category_key = resolve_category_key(req.category)
                category_display = get_category_display(category_key, language=lang)
                button_text = f"{icon} #{req.request_number} - {category_display}"
                builder.button(text=button_text, callback_data=f"view_request_{req.request_number}")

            builder.adjust(1)  # По одной кнопке в ряд

        # TASK 17 Issue #5: Localized pagination and filter buttons
        pagination_buttons = []
        if current_page > 1:
            back_text = get_text('buttons.back', language=lang)
            pagination_buttons.append(InlineKeyboardButton(text=f"◀️ {back_text}", callback_data=f"requests_page_{current_page - 1}"))
        if current_page < total_pages:
            forward_text = get_text('buttons.forward', language=lang)
            pagination_buttons.append(InlineKeyboardButton(text=forward_text, callback_data=f"requests_page_{current_page + 1}"))

        if pagination_buttons:
            builder.row(*pagination_buttons)

        # Добавляем фильтры только для не-исполнителей
        if active_role != "executor":
            all_text = get_text('requests.all_filter', language=lang)
            active_text = get_text('requests.active_filter', language=lang)
            archive_text = get_text('requests.archive_filter', language=lang)

            filter_buttons = [
                InlineKeyboardButton(text=f"📋 {all_text}" if active_status == "all" else f"⚪️ {all_text}", callback_data="requests_filter_all"),
                InlineKeyboardButton(text=f"🟢 {active_text}" if active_status == "active" else f"⚪️ {active_text}", callback_data="requests_filter_active"),
                InlineKeyboardButton(text=f"📦 {archive_text}" if active_status == "archive" else f"⚪️ {archive_text}", callback_data="requests_filter_archive")
            ]
            builder.row(*filter_buttons)

            # Добавляем кнопки для заявок, требующих действий заявителя
            reply_text = get_text('requests.reply_to_request', language=lang)
            for req in requests:
                if req.status == "Уточнение":
                    builder.row(InlineKeyboardButton(
                        text=f"💬 {reply_text} #{req.request_number}",
                        callback_data=f"replyclarify_{req.request_number}"
                    ))
                # Кнопка "Подтвердить" убрана - для этого есть отдельное меню "Ожидают приёмки"

        await callback.message.answer(
            message_text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка возврата к списку: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("common.error", language=lang), show_alert=True)
    finally:
        if db_session:
            db_session.close()

@router.callback_query(F.data.regexp(_EDIT_REQUEST_NUMBER_RE))
async def handle_edit_request(callback: CallbackQuery, state: FSMContext):
    """Обработка редактирования заявки"""
    db_session = None          # ARCH-013: гарантируем close в finally
    try:
        logger.info(f"Обработка редактирования заявки для пользователя {callback.from_user.id}")

        db_session = next(get_db())
        lang = get_user_language(callback.from_user.id, db_session)

        request_number = callback.data.replace("edit_", "")

        # Получаем заявку из базы данных
        request = db_session.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await callback.answer(get_text("requests.request_not_found", language=lang), show_alert=True)
            return

        # Проверяем права доступа (сравниваем с telegram_id пользователя)
        from uk_management_bot.database.models.user import User
        user = db_session.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not user or request.user_id != user.id:
            await callback.answer(get_text("requests.no_edit_permission", language=lang), show_alert=True)
            return

        # Сохраняем номер заявки в FSM для редактирования
        await state.update_data(editing_request_number=request_number)
        await state.set_state(RequestStates.category)

        await callback.message.edit_text(
            get_text("requests.edit_request_select_category", language=lang).format(request_number=request_number),
            reply_markup=get_categories_keyboard()
        )

        logger.info(f"Начато редактирование заявки {request_number} пользователем {callback.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка обработки редактирования заявки: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("common.error", language=lang), show_alert=True)
    finally:
        if db_session:
            db_session.close()

# Менеджерское удаление заявки перенесено на префикс `mgr_delete_` и живёт в
# handlers/admin.py::handle_delete_request (гейт ADMIN_USER_IDS + каскадное удаление).
# Прежний bare-`delete_` owner-delete здесь затенял админский (requests_router
# регистрируется раньше admin_router) и к тому же удалял заявку без подтверждения.
# Удалён — см. test_bug_duty_assign_routing::test_admin_router_owns_mgr_delete.

# BUG-BOT-034/PR-25: менеджерское «Принять» (`accept_<NNN>`) живёт в
# handlers/admin.py::handle_accept_request (канон-переход через workflow_runner
# MANAGER_ASSIGN + has_admin_access). Прежний bare-`accept_` handler здесь —
# ручной `update_status_by_actor("В работе")` — затенял админский (requests_router
# раньше admin_router). Удалён; admin теперь единственный владелец строгого
# `^accept_\d{6}-\d{3,}$`. См. test_bug_duty_assign_routing::test_admin_router_owns_accept.

# Менеджерское завершение заявки перенесено на префикс `mgr_complete_` и живёт в
# handlers/admin.py::handle_complete_request (статус EXECUTED + AuditLog). Прежний
# bare-`complete_` исполнительский complete здесь затенял и админский менеджерский
# complete, и выделенный `complete_work_` (по префиксу). Исполнитель завершает
# через `executor_complete_` (ниже) и `complete_work_` (request_status_management).
# Удалён — см. test_bug_duty_assign_routing::{test_admin_router_owns_mgr_complete,
# test_complete_work_routes_to_status_management}.


# BUG-BOT-022: ранее здесь был дубликат handler-а `clarify_<NNN>`. Он
# регистрировался в requests_router (включается раньше admin_router) и
# перехватывал клик "❓ Уточнить" из admin request detail, после чего падал
# в generic "Ошибка" (status update flow без интерактивного prompt-а).
# Полноценный handler с FSM-flow (prompt → text input → notify applicant)
# живёт в `uk_management_bot/handlers/admin.py::handle_clarify_request`.
# Дубликат удалён — теперь клик корректно попадает в admin-handler.


# BUG-BOT-034/PR-25: менеджерский «Закуп» (`purchase_<NNN>`) живёт в
# handlers/admin.py::handle_purchase_request (открывает ввод материалов через
# RequestStatusStates.waiting_for_materials, статус НЕ меняет до ввода). Прежний
# bare-`purchase_` handler здесь преждевременно ставил «Закуп» без ввода материалов
# и затенял админский (requests_router раньше admin_router). Удалён; admin —
# единственный владелец строгого `^purchase_\d{6}-\d{3,}$`.
# См. test_bug_duty_assign_routing::test_admin_router_owns_purchase.


# BUG-BOT-030: ранее использовался prefix-match `cancel_` с поддерживаемым exclusion list,
# что приводило к anti-pattern (open-set, ловит любые новые cancel_-callback).
# Заменено на строгий regex по формату request_number. BUG-122: матчер теперь
# собран из shared REQUEST_NUMBER_CORE (\d{3,}) — определён выше, у импортов.
@router.callback_query(F.data.regexp(_CANCEL_REQUEST_NUMBER_RE.pattern))
async def handle_cancel_request(callback: CallbackQuery, state: FSMContext):
    """Обработка отмены заявки. Срабатывает только на `cancel_<YYMMDD-NNN>`."""
    db_session = None          # ARCH-013: гарантируем close в finally
    try:
        # Менеджер или владелец (в RequestService также есть проверка)
        request_number = callback.data.replace("cancel_", "")
        db_session = next(get_db())
        lang = get_user_language(callback.from_user.id, db_session)

        service = RequestService(db_session)
        result = service.update_status_by_actor(
            request_number=request_number,
            new_status="Отменена",
            actor_telegram_id=callback.from_user.id,
        )
        if not result.get("success"):
            error_msg = result.get("message", get_text("common.error", language=lang))
            await callback.answer(error_msg, show_alert=True)
            return
        await callback.message.edit_text(
            get_text("requests.request_cancelled", language=lang).format(request_number=request_number),
            reply_markup=get_main_keyboard(language=lang)
        )
    except Exception as e:
        logger.error(f"Ошибка обработки отмены заявки: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("common.error", language=lang), show_alert=True)
    finally:
        if db_session:
            db_session.close()


# Менеджерское «Отклонить» перенесено на префикс `mgr_deny_` и живёт в
# handlers/admin.py::handle_deny_request (FSM «ввод причины отклонения»). Прежний
# bare-`deny_` handler здесь («исполнитель предлагает отказ») затенял менеджерский
# (requests_router раньше admin_router): клик менеджера давал «предложение отказа
# отправлено» вместо запроса причины. Фича propose-deny сейчас без кнопки; если
# понадобится — завести отдельный префикс `executor_deny_` + кнопку.
# Удалён — см. test_bug_duty_assign_routing::test_admin_router_owns_mgr_deny.


@router.callback_query(F.data.regexp(_APPROVE_REQUEST_NUMBER_RE))
async def handle_approve_request(callback: CallbackQuery, state: FSMContext):
    """Подтверждение выполненной заявки заявителем.

    SSOT-кластер #1, PR2c: канон требует оценку при приёмке (APPLICANT_ACCEPT
    с rating, только из «Исполнено»). Прежняя прямая запись «Принято» без
    рейтинга снята — кнопка теперь ведёт в канонический rated-accept: показываем
    клавиатуру оценки 1–5★, дальнейшую приёмку выполняет
    request_acceptance.save_rating через run_command(APPLICANT_ACCEPT).
    """
    db_session = None          # ARCH-013: гарантируем close в finally
    try:
        request_number = callback.data.replace("approve_", "")
        db_session = next(get_db())
        lang = get_user_language(callback.from_user.id, db_session)

        from uk_management_bot.keyboards.admin import get_rating_keyboard
        await callback.message.edit_text(
            get_text("request_acceptance.handlers.rate_request", language=lang),
            reply_markup=get_rating_keyboard(request_number),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Ошибка обработки подтверждения заявки: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("common.error", language=lang), show_alert=True)
    finally:
        if db_session:
            db_session.close()


# ============================
# Мои заявки (список + пагинация)
# ============================

@router.message(F.text.in_(MY_REQUESTS_TEXTS))
async def show_my_requests(message: Message, state: FSMContext):
    """Показать список заявок пользователя (страница 1)"""
    db_session = None          # ARCH-013: гарантируем close в finally
    try:
        telegram_id = message.from_user.id
        # Читаем активный фильтр и страницу из FSM
        data = await state.get_data()
        active_status = data.get("my_requests_status", "all")  # По умолчанию показываем все заявки
        current_page = int(data.get("my_requests_page", 1))

        # Убеждаемся, что статус установлен в FSM
        if not data.get("my_requests_status"):
            await state.update_data(my_requests_status="all")
        db_session = next(get_db())
        lang = get_user_language(message.from_user.id, db_session)

        # Получаем пользователя из базы данных по telegram_id
        from uk_management_bot.database.models.user import User
        user = db_session.query(User).filter(User.telegram_id == telegram_id).first()

        if not user:
            await message.answer(get_text("common.user_not_found", language=lang))
            return
        
        # Определяем роль пользователя
        user_roles = []
        if user.roles:
            try:
                import json
                user_roles = json.loads(user.roles) if isinstance(user.roles, str) else user.roles
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Ошибка парсинга ролей пользователя {user.id}: {e}")
                user_roles = []
        
        active_role = user.active_role or (user_roles[0] if user_roles else "applicant")

        # Логируем начало запроса
        logger.info(f"show_my_requests: telegram_id={telegram_id}, active_role={active_role}, active_status={active_status}, user_id={user.id}")

        # Получаем заявки в зависимости от роли
        if active_role == "executor":
            # Для исполнителей используем вспомогательную функцию
            # (работает только с новой системой через RequestAssignment)
            query = _get_executor_requests_query(db_session, user)
            logger.info(f"Исполнитель {user.id}: используется новая система назначений через RequestAssignment")

        else:
            # Для заявителей и других ролей: показываем их собственные заявки
            query = db_session.query(Request).filter(Request.user_id == user.id)
            logger.info(f"Заявитель/другая роль {user.id}: показываем заявки с user_id={user.id}")
        
        # Фильтр статуса: применяем для ВСЕХ ролей (включая исполнителей)
        if active_status == "active":
            # Активные: рабочие статусы (ожидают действий)
            # Для исполнителей: только "В работе", "Закуп", "Уточнение" (назначенные менеджером)
            # "Новая" - ещё не назначена, "Принято" - уже принята заявителем (архив)
            if active_role == "executor":
                query = query.filter(Request.status.in_(["В работе", "Закуп", "Уточнение"]))
                logger.info("Применен фильтр active_status='active' для исполнителя: статусы=['В работе', 'Закуп', 'Уточнение']")
            else:
                query = query.filter(Request.status.in_(["Новая", "В работе", "Закуп", "Уточнение"]))
                logger.info("Применен фильтр active_status='active': статусы=['Новая', 'В работе', 'Закуп', 'Уточнение']")
        elif active_status == "archive":
            # Архив: финальные и завершенные статусы
            # Для исполнителей: "Выполнена" (ждёт проверки менеджера), "Принято" (принята заявителем), "Отменена"
            if active_role == "executor":
                query = query.filter(Request.status.in_(["Выполнена", "Исполнено", "Принято", "Отменена"]))
                logger.info("Применен фильтр active_status='archive' для исполнителя: статусы=['Выполнена', 'Исполнено', 'Принято', 'Отменена']")
            else:
                query = query.filter(Request.status.in_(["Выполнена", "Исполнено", "Принято", "Отменена"]))
                logger.info("Применен фильтр active_status='archive': статусы=['Выполнена', 'Исполнено', 'Принято', 'Отменена']")
        elif active_status == "all":
            # Все заявки: без фильтра по статусу
            logger.info("Применен фильтр active_status='all': показываем все заявки без фильтра статуса")
        else:
            logger.warning(f"Фильтр статуса НЕ применен! active_status={active_status}")

        # Сортировка: для фильтра "all" сначала активные, потом архивные, внутри каждой группы по дате
        if active_role != "executor" and active_status == "all":
            from sqlalchemy import case
            # Определяем приоритет статусов: активные (0) идут перед архивными (1)
            status_priority = case(
                (Request.status.in_(["Новая", "В работе", "Закуп", "Уточнение"]), 0),  # Активные
                else_=1  # Архивные
            )
            user_requests = query.order_by(status_priority, Request.created_at.desc()).all()
        else:
            # Для остальных случаев - просто по дате создания
            user_requests = query.order_by(Request.created_at.desc()).all()

        # Добавляем логирование для отладки
        logger.info(f"Пользователь {telegram_id} (роль: {active_role}) - найдено заявок: {len(user_requests)}")
        if user_requests:
            logger.info(f"Первые 3 заявки: {[(r.request_number, r.status, r.category) for r in user_requests[:3]]}")
        if active_role == "executor" and len(user_requests) == 0:
            # Проверяем, есть ли вообще назначения для сантехников
            test_query = db_session.query(Request).join(RequestAssignment).filter(
                RequestAssignment.status == "active",
                RequestAssignment.assignment_type == "group",
                RequestAssignment.group_specialization == "plumber",
                Request.status.in_(["В работе", "Закуп", "Уточнение"])
            ).all()
            logger.info(f"Тестовый запрос для сантехников вернул {len(test_query)} заявок")

        total_requests = len(user_requests)
        requests_per_page = 5
        total_pages = max(1, (total_requests + requests_per_page - 1) // requests_per_page)
        # Корректируем текущую страницу, если вышла за диапазон
        if current_page > total_pages:
            current_page = total_pages

        start_idx = (current_page - 1) * requests_per_page
        end_idx = start_idx + requests_per_page
        page_requests = user_requests[start_idx:end_idx]

        # TASK 17 Issue #5: Use localized helper functions for formatting
        from uk_management_bot.utils.request_helpers import (
            format_requests_list_header,
            format_request_list_item,
            get_status_icon
        )

        # Use helper function for list header
        message_text = format_requests_list_header(
            total_requests=total_requests,
            current_page=current_page,
            total_pages=total_pages,
            status_filter=active_status,
            role=active_role,
            language=lang
        )

        if not page_requests:
            if active_role == "executor":
                no_requests_msg = get_text('requests.no_assigned_requests', language=lang) or "У вас пока нет назначенных заявок."
                message_text += no_requests_msg
            else:
                no_requests_msg = get_text('requests.no_requests', language=lang) or "У вас пока нет заявок."
                message_text += no_requests_msg
        else:
            # Для заявителей показываем текстовый список (используем helper-функцию)
            if active_role != "executor":
                for i, r in enumerate(page_requests, 1):
                    message_text += format_request_list_item(
                        request=r,
                        index=i,
                        language=lang,
                        show_details=True
                    )

        from uk_management_bot.keyboards.requests import get_pagination_keyboard

        # Формируем клавиатуру
        rows = []

        # Для исполнителей НЕ показываем кнопки фильтрации (Активные/Архив)
        # Они видят только заявки, назначенные им
        if active_role != "executor":
            # Для заявителей и других ролей - показываем фильтры
            filter_status_kb = get_status_filter_inline_keyboard(active_status, language=lang)
            rows = list(filter_status_kb.inline_keyboard)

            # TASK 17 Issue #5: Localized reply button
            reply_text = get_text('requests.reply_to_request', language=lang)
            for r in page_requests:
                if r.status == "Уточнение":
                    # Кнопка для ответа на уточнение
                    rows.append([InlineKeyboardButton(
                        text=f"💬 {reply_text} #{r.request_number}",
                        callback_data=f"replyclarify_{r.request_number}"
                    )])
                # Кнопка "Подтвердить" убрана - для этого есть отдельное меню "Ожидают приёмки"
        else:
            # Для исполнителей добавляем кнопки заявок
            for i, r in enumerate(page_requests, 1):
                icon = get_status_icon(r.status)
                from uk_management_bot.keyboards.requests import resolve_category_key, get_category_display
                cat_display = get_category_display(resolve_category_key(r.category), language=lang)
                button_text = f"{icon} #{r.request_number} - {cat_display}"
                rows.append([InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"view_request_{r.request_number}"
                )])

        # TASK 17 Issue #5: Add language parameter to pagination keyboard
        pagination_kb = get_pagination_keyboard(current_page, total_pages, language=lang)
        rows += pagination_kb.inline_keyboard
        combined = InlineKeyboardMarkup(inline_keyboard=rows)
        # Сохраняем актуальную страницу в FSM
        await state.update_data(my_requests_page=current_page)
        try:
            await message.answer(message_text, reply_markup=combined)
        except TelegramBadRequest:
            # повторное нажатие на тот же фильтр — просто обновим сообщением
            await message.answer(message_text, reply_markup=combined)
    except Exception as e:
        logger.error(f"Ошибка отображения списка заявок для пользователя {message.from_user.id}: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await message.answer(get_text("requests.error_loading_requests", language=lang))
    finally:
        if db_session:
            db_session.close()


@router.message(Command("my_requests"))
async def cmd_my_requests(message: Message, state: FSMContext):
    """Команда /my_requests показывает страницу 1 списка заявок"""
    # По умолчанию показываем активные
    await state.update_data(my_requests_status="active")
    await show_my_requests(message, state)


@router.callback_query(F.data.startswith("replyclarify_"))
async def handle_reply_clarify_start(callback: CallbackQuery, state: FSMContext):
    """Пользователь хочет ответить на запрос уточнения. Просим ввести текст."""
    db_session = None          # ARCH-013: гарантируем close в finally
    try:
        db_session = next(get_db())
        lang = get_user_language(callback.from_user.id, db_session)

        request_number = callback.data.replace("replyclarify_", "")
        # Показать текущий диалог из notes перед вводом
        req = db_session.query(Request).filter(Request.request_number == request_number).first()
        await state.update_data(reply_request_number=request_number)
        await state.set_state(RequestStates.waiting_clarify_reply)
        # Получаем пользователя из базы данных по telegram_id
        from uk_management_bot.database.models.user import User
        user = db_session.query(User).filter(User.telegram_id == callback.from_user.id).first()

        if req and user and req.user_id == user.id:
            notes_text = (req.notes or "").strip()
            if notes_text:
                await callback.message.answer(get_text("requests.current_dialog", language=lang).format(notes=notes_text))
            else:
                await callback.message.answer(get_text("requests.dialog_empty", language=lang))
        await callback.message.answer(
            get_text("requests.enter_clarification_reply", language=lang),
            reply_markup=get_cancel_keyboard(language=lang),
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка старта ответа на уточнение: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("common.error", language=lang))
    finally:
        if db_session:
            db_session.close()


@router.message(RequestStates.waiting_clarify_reply)
async def handle_reply_clarify_text(message: Message, state: FSMContext):
    """Сохраняем ответ пользователя в notes без смены статуса."""
    db_session = None          # ARCH-013: гарантируем close в finally
    try:
        db_session = next(get_db())
        lang = get_user_language(message.from_user.id, db_session)

        data = await state.get_data()
        request_number = data.get("reply_request_number")
        if not request_number:
            await message.answer(get_text("requests.request_number_not_found", language=lang))
            await state.clear()
            return

        service = RequestService(db_session)
        req = service.get_request_by_number(request_number)
        # Получаем пользователя из базы данных по telegram_id
        from uk_management_bot.database.models.user import User
        user = db_session.query(User).filter(User.telegram_id == message.from_user.id).first()

        if not req or not user or req.user_id != user.id:
            await message.answer(get_text("requests.request_not_found_or_unavailable", language=lang))
            await state.clear()
            await message.answer(get_text("common.return_to_menu", language=lang), reply_markup=get_user_contextual_keyboard(message.from_user.id))
            return
        existing = (req.notes or "").strip()
        to_add = message.text.strip()
        # Добавляем с ролью пользователя
        user_prefix = get_text("requests.user_prefix", language=lang)
        clarification_label = get_text("requests.clarification_label", language=lang)
        new_notes = (existing + "\n" if existing else "") + f"[{user_prefix}] {clarification_label}: {to_add}"
        req.notes = new_notes
        db_session.commit()
        await message.answer(get_text("requests.reply_saved", language=lang), reply_markup=get_main_keyboard(language=lang))
        await state.clear()
    except Exception as e:
        logger.error(f"Ошибка сохранения ответа на уточнение: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await state.clear()
        await message.answer(get_text("requests.reply_save_failed", language=lang), reply_markup=get_main_keyboard(language=lang))
    finally:
        if db_session:
            db_session.close()


@router.callback_query(F.data.startswith("status_"))
async def handle_status_filter(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора фильтра статуса для списка заявок"""
    db_session = None          # ARCH-013: гарантируем close в finally
    try:
        # Совместимость с тестами: поддержать текстовые статусы, но маппить на упрощённые "active"/"archive"/"all"
        raw = callback.data.replace("status_", "")
        if raw in ("active", "archive", "all"):
            choice = raw
        elif raw == "В работе":
            choice = "В работе"
        else:
            choice = raw
        # Запоминаем фильтр и сбрасываем страницу
        await state.update_data(my_requests_status=choice, my_requests_page=1)

        # Собираем список заявок и клавиатуру, затем редактируем сообщение
        db_session = next(get_db())

        # Получаем пользователя из базы данных по telegram_id
        from uk_management_bot.database.models.user import User
        user = db_session.query(User).filter(User.telegram_id == callback.from_user.id).first()

        lang = get_user_language(callback.from_user.id, db_session)

        if not user:
            await callback.answer(get_text("common.user_not_found", language=lang), show_alert=True)
            return

        query = db_session.query(Request).filter(Request.user_id == user.id)
        if choice == "active" or choice == "В работе":
            # Активные: рабочие статусы (ожидают действий)
            query = query.filter(Request.status.in_(["Новая", "В работе", "Закуп", "Уточнение"]))
        elif choice == "archive":
            # Архив: финальные и завершенные статусы
            query = query.filter(Request.status.in_(["Выполнена", "Исполнено", "Принято", "Отменена"]))
        elif choice == "all":
            # Все заявки: без фильтра по статусу
            pass

        # Сортировка: для "all" сначала активные, потом архивные
        if choice == "all":
            from sqlalchemy import case
            status_priority = case(
                (Request.status.in_(["Новая", "В работе", "Закуп", "Уточнение"]), 0),  # Активные
                else_=1  # Архивные
            )
            user_requests = query.order_by(status_priority, Request.created_at.desc()).all()
        else:
            user_requests = query.order_by(Request.created_at.desc()).all()
        current_page = 1
        requests_per_page = 5
        total_pages = max(1, (len(user_requests) + requests_per_page - 1) // requests_per_page)
        page_requests = user_requests[:requests_per_page]

        # Определяем заголовок в зависимости от фильтра
        if choice == "active":
            status_title = get_text("requests.handlers.active_requests_title", language=lang)
        elif choice == "archive":
            status_title = get_text("requests.handlers.archive_requests_title", language=lang)
        else:
            status_title = get_text("requests.handlers.all_requests_title", language=lang)
        message_text = get_text("requests.handlers.requests_list_page_header", language=lang).format(
            title=status_title, current_page=current_page, total_pages=total_pages
        )
        if not page_requests:
            message_text += get_text("requests.handlers.no_requests_hint", language=lang)
        else:
            for i, request in enumerate(page_requests, 1):
                from uk_management_bot.utils.address_helpers import localize_address
                address = localize_address(request.address, lang)
                if len(address) > 60:
                    address = address[:60] + "…"
                # TASK 17 Этап A и C: Локализуем категорию и статус через status_display.py
                from uk_management_bot.keyboards.requests import resolve_category_key, get_category_display
                category_key = resolve_category_key(request.category)
                category_display = get_category_display(category_key, language=lang)
                status_display = _sd_get_status_display(request.status, language=lang)
                icon = STATUS_EMOJI.get(request.status, "📋")
                message_text += f"{i}. {icon} #{request.request_number} - {category_display} - {status_display}\n"
                # TASK 17 Этап C: Локализованные метки
                address_label = get_text("requests.address_label", language=lang) or "Адрес"
                created_label = get_text("requests.created_label", language=lang) or "Создана"
                message_text += f"   {address_label} {address}\n"
                message_text += f"   {created_label} {request.created_at.strftime('%d.%m.%Y')}\n"
                if choice == "archive" and request.status == "Отменена" and request.notes:
                    # TASK 17 Этап C: Локализованная метка
                    reason_label = get_text("requests.cancellation_reason_label", language=lang) or "Причина отказа"
                    message_text += f"   {reason_label} {request.notes}\n"
                elif request.status == "Уточнение" and request.notes:
                    # TASK 17 Этап C: Локализованная метка
                    clarification_label = get_text("requests.clarification_label", language=lang) or "Уточнение"
                    # Показываем последние сообщения из диалога уточнения
                    notes_lines = request.notes.strip().split('\n')
                    last_messages = [line for line in notes_lines[-3:] if line.strip()]  # Последние 3 сообщения
                    if last_messages:
                        preview = '\n'.join(last_messages)
                        if len(preview) > 100:
                            preview = preview[:97] + '...'
                        message_text += f"   {clarification_label}: {preview}\n"
                message_text += "\n"

        from uk_management_bot.keyboards.requests import get_pagination_keyboard
        filter_status_kb = get_status_filter_inline_keyboard(choice, language=lang)

        # Формируем клавиатуру
        combined_rows = list(filter_status_kb.inline_keyboard)

        # Добавляем кнопки для заявок, требующих действий заявителя
        for r in page_requests:
            if r.status == "Уточнение":
                # Кнопка для ответа на уточнение
                combined_rows.append([InlineKeyboardButton(
                    text=get_text("requests.handlers.reply_to", language=lang).format(number=r.request_number),
                    callback_data=f"replyclarify_{r.request_number}"
                )])
            # Кнопка "Подтвердить" убрана - для этого есть отдельное меню "Ожидают приёмки"

        # Добавляем пагинацию
        pagination_kb = get_pagination_keyboard(current_page, total_pages)
        combined_rows += pagination_kb.inline_keyboard
        combined = type(pagination_kb)(inline_keyboard=combined_rows)

        try:
            await callback.message.edit_text(message_text, reply_markup=combined)
        except TelegramBadRequest:
            # Повторное нажатие по тому же фильтру/такому же тексту — просто ответим без алерта
            pass
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка применения фильтра статуса: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("requests.filter_error", language=lang), show_alert=True)
    finally:
        if db_session:
            db_session.close()
@router.callback_query(F.data.startswith("categoryfilter_"))
async def handle_category_filter(callback: CallbackQuery, state: FSMContext):
    """
    Обработка выбора фильтра категории
    
    TASK 17 Этап A: Теперь работает с внутренними ключами категорий вместо русских текстов.
    """
    db_session = None          # ARCH-013: гарантируем close в finally
    try:
        db_session = next(get_db())
        lang = get_user_language(callback.from_user.id, db_session)

        # TASK 17 Этап A: Извлекаем внутренний ключ категории (или "all")
        choice = callback.data.replace("categoryfilter_", "")
        # choice теперь содержит внутренний ключ (например, "electricity") или "all"
        await state.update_data(my_requests_category=choice, my_requests_page=1)
        fake_message = callback.message
        fake_message.from_user = callback.from_user
        await show_my_requests(fake_message, state)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка применения фильтра категории: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("requests.filter_error", language=lang), show_alert=True)
    finally:
        if db_session:
            db_session.close()


@router.callback_query(F.data == "filters_reset")
async def handle_filters_reset(callback: CallbackQuery, state: FSMContext):
    """Сброс всех фильтров списка заявок"""
    db_session = None          # ARCH-013: гарантируем close в finally
    try:
        db_session = next(get_db())
        lang = get_user_language(callback.from_user.id, db_session)

        await state.update_data(
            my_requests_status="all",
            my_requests_category="all",
            my_requests_period="all",
            my_requests_executor="all",
            my_requests_page=1,
        )
        await show_my_requests(Message.model_construct(from_user=callback.from_user, chat=callback.message.chat), state)
        await callback.answer(get_text("requests.filters_reset", language=lang))
    except Exception as e:
        logger.error(f"Ошибка сброса фильтров: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("requests.filter_error", language=lang), show_alert=True)
    finally:
        if db_session:
            db_session.close()


@router.callback_query(F.data.startswith("period_"))
async def handle_period_filter(callback: CallbackQuery, state: FSMContext):
    db_session = None          # ARCH-013: гарантируем close в finally
    try:
        db_session = next(get_db())
        lang = get_user_language(callback.from_user.id, db_session)

        choice = callback.data.replace("period_", "")
        await state.update_data(my_requests_period=choice, my_requests_page=1)
        await show_my_requests(Message.model_construct(from_user=callback.from_user, chat=callback.message.chat), state)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка применения фильтра периода: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("requests.filter_error", language=lang), show_alert=True)
    finally:
        if db_session:
            db_session.close()


@router.callback_query(F.data.startswith("executorfilter_"))
async def handle_executor_filter(callback: CallbackQuery, state: FSMContext):
    db_session = None          # ARCH-013: гарантируем close в finally
    try:
        db_session = next(get_db())
        lang = get_user_language(callback.from_user.id, db_session)

        choice = callback.data.replace("executorfilter_", "")
        await state.update_data(my_requests_executor=choice, my_requests_page=1)
        await show_my_requests(Message.model_construct(from_user=callback.from_user, chat=callback.message.chat), state)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка применения фильтра исполнителя: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("requests.filter_error", language=lang), show_alert=True)
    finally:
        if db_session:
            db_session.close()


# ===== ОБРАБОТЧИКИ НАЗНАЧЕНИЯ ИСПОЛНИТЕЛЕЙ =====

# NOTE: assign_duty_* is handled by handlers/admin.py:handle_assign_duty_executor_admin,
# which commits the group assignment and notifies executors on an active shift.
# A duplicate handler here previously shadowed it (requests_router is registered
# before admin_router) and silently dropped the assignment — see test_bug_duty_assign_routing.


# NOTE: assign_specific_* and assign_executor_* are handled by handlers/admin.py
# (handle_assign_specific_executor_admin / handle_final_executor_assignment_admin), which
# route through AssignmentService — creating a RequestAssignment row, cancelling stale
# assignments, and writing an audit log. Duplicate copies lived here and shadowed them
# (requests_router precedes admin_router); the old copy set request.executor_id directly
# with assignment_type="manual" and skipped the assignment record/audit. See
# test_bug_duty_assign_routing.


# `back_to_assignment_type_*` обрабатывается в handlers/admin.py::
# handle_back_to_assignment_type_admin (функционально идентичная копия). Дубликат
# здесь затенял её (requests_router раньше admin_router). Удалён —
# см. test_bug_duty_assign_routing::test_back_to_assignment_type_owned_by_admin.


# ============================
# ОБРАБОТЧИКИ ИСПОЛНИТЕЛЯ
# ============================

class ExecutorRequestStates(StatesGroup):
    """Состояния для работы исполнителя с заявками"""
    waiting_purchase_comment = State()  # Ожидание комментария для закупа
    waiting_completion_comment = State()  # Ожидание комментария для завершения
    waiting_completion_media = State()  # Ожидание медиа для завершения


@router.callback_query(F.data.startswith("executor_view_media_"))
async def executor_view_media(callback: CallbackQuery):
    """Просмотр медиа-файлов заявки исполнителем"""
    db_session = None          # ARCH-013: гарантируем close в finally
    try:
        request_number = callback.data.replace("executor_view_media_", "")
        db_session = next(get_db())
        lang = get_user_language(callback.from_user.id, db_session)

        request = db_session.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await callback.answer(get_text("requests.request_not_found", language=lang), show_alert=True)
            return

        # Отправляем медиа-файлы
        from aiogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument
        import json

        media_group = []

        if request.media_files:
            try:
                media_files = json.loads(request.media_files) if isinstance(request.media_files, str) else request.media_files
                if media_files:
                    for media in media_files:
                        file_id = media.get('file_id') if isinstance(media, dict) else media
                        media_type = media.get('type', 'photo') if isinstance(media, dict) else 'photo'

                        if media_type == 'photo':
                            media_group.append(InputMediaPhoto(media=file_id))
                        elif media_type == 'video':
                            media_group.append(InputMediaVideo(media=file_id))
                        elif media_type == 'document':
                            media_group.append(InputMediaDocument(media=file_id))
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(f"Ошибка парсинга media_files: {e}")

        if media_group:
            await callback.message.answer_media_group(media=media_group)
            await callback.answer(get_text("requests.media_files_sent", language=lang))
        else:
            await callback.answer(get_text("requests.no_media_files", language=lang), show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка просмотра медиа исполнителем: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("common.error", language=lang), show_alert=True)
    finally:
        if db_session:
            db_session.close()


def _run_executor_command(request_number: str, user_id, action, payload: dict,
                          command_id: str):
    """PR2a-5: исполнительский переход через единый layer (canonical-write).

    run_command сам грузит под FOR UPDATE, авторизует (assigned + активная
    смена), пишет patch+audit+outbox в одной tx. Возвращает (outcome, error_key):
    error_key=None при успехе, иначе ключ локали для ответа пользователю.
    """
    from uk_management_bot.database.session import SessionLocal
    from uk_management_bot.services.workflow_runner import (
        run_command_sync, RequestNotFound)
    from uk_management_bot.utils.request_workflow import (
        ActionCommand, PrincipalRef,
        NotAuthorized, InvalidTransition, RepeatRejected, RepeatConflict,
        WorkflowError)
    try:
        outcome = run_command_sync(
            SessionLocal, request_number,
            PrincipalRef(kind="user", user_id=user_id, source="telegram"),
            ActionCommand(command_id, action, payload),
        )
        return outcome, None
    except RequestNotFound:
        return None, "requests.request_not_found"
    except NotAuthorized:
        return None, "requests.executor_not_authorized"
    except (InvalidTransition, RepeatRejected, RepeatConflict):
        return None, "requests.executor_status_conflict"
    except WorkflowError:
        return None, "common.error"


def _build_group_pool_view(db_session: Session, user: User, lang: str):
    """FEAT-группы: построить (text, keyboard|None) пула «свободных» group-заявок
    с кнопкой «🙋 Взять #N» по каждой. Пустой пул → текст без клавиатуры."""
    from uk_management_bot.keyboards.requests import (
        resolve_category_key, get_category_display)
    from uk_management_bot.utils.address_helpers import localize_address

    pool = (_get_group_pool_query(db_session, user)
            .order_by(Request.created_at.desc()).all())
    title = get_text("requests.group_pool_title", language=lang) or "🆓 Свободные заявки"
    if not pool:
        empty = get_text("requests.group_pool_empty", language=lang) or "Свободных заявок нет"
        return f"{title}\n\n{empty}", None

    claim_text = get_text("requests.executor_claim_button", language=lang) or "🙋 Взять в работу"
    address_label = get_text("requests.address_label", language=lang) or "Адрес"
    lines = [title, ""]
    rows: list = []
    for i, r in enumerate(pool, 1):
        category_display = get_category_display(resolve_category_key(r.category), language=lang)
        lines.append(f"{i}. 🔧 #{r.request_number} — {category_display}")
        lines.append(f"   {address_label} {localize_address(r.address, lang)}")
        lines.append("")
        rows.append([InlineKeyboardButton(
            text=f"{claim_text} #{r.request_number}",
            callback_data=f"claim_request_{r.request_number}")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_group_pool(message: Message, db_session: Session,
                             user: User, lang: str) -> None:
    """edit-вариант (перерисовка после взятия / открытия из inline)."""
    text, kb = _build_group_pool_view(db_session, user, lang)
    try:
        await message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        pass


@router.message(F.text.in_(GROUP_POOL_TEXTS))
async def show_group_pool_message(message: Message, state: FSMContext):
    """FEAT-группы: реплай-кнопка «🆓 Свободные заявки» (исполнитель) → пул."""
    db_session = None
    try:
        db_session = next(get_db())
        lang = get_user_language(message.from_user.id, db_session)
        user = db_session.query(User).filter(
            User.telegram_id == message.from_user.id).first()
        if not user:
            await message.answer(get_text("common.user_not_found", language=lang))
            return
        text, kb = _build_group_pool_view(db_session, user, lang)
        await message.answer(text, reply_markup=kb)
    except Exception as e:
        logger.error(f"Ошибка показа пула (реплай): {e}")
        await message.answer(get_text("common.error", language="ru"))
    finally:
        if db_session:
            db_session.close()


async def _notify_group_pool_claimed(db_session: Session, request_number: str,
                                     claimer: User) -> None:
    """FEAT-группы (best-effort, вне tx): уведомить остальных дежурных группы,
    что заявку #N взял {claimer}. Таргет — on-shift исполнители той же
    специализации (group_specialization сохранён в назначении как история)."""
    try:
        from uk_management_bot.services.notification_service import _get_shared_bot
        from uk_management_bot.utils.auth_helpers import get_user_roles
        from uk_management_bot.utils.constants import ROLE_EXECUTOR
        from uk_management_bot.utils.shifts import is_on_shift_now_sync
        from uk_management_bot.utils.specializations import parse_specializations

        assignment = db_session.query(RequestAssignment).filter(
            RequestAssignment.request_number == request_number,
            RequestAssignment.status == "active").first()
        spec = assignment.group_specialization if assignment else None
        if not spec:
            return
        bot = _get_shared_bot()
        if bot is None:
            return
        claimer_name = claimer.first_name or str(claimer.id)
        for ex in db_session.query(User).filter(User.status == "approved").all():
            if ex.id == claimer.id or not ex.telegram_id:
                continue
            if ROLE_EXECUTOR not in get_user_roles(ex):
                continue
            if spec not in parse_specializations(ex):
                continue
            if not is_on_shift_now_sync(db_session, ex.id):
                continue
            text = get_text("requests.claimed_by_other_notify",
                            language=(ex.language or "ru")).format(
                request_number=request_number, executor=claimer_name)
            try:
                await bot.send_message(chat_id=ex.telegram_id, text=text)
            except Exception as e:
                logger.debug(f"claim-notify исполнителю {ex.id} пропущено: {e}")
    except Exception as e:
        logger.warning(f"claim-notify для {request_number} не выполнен: {e}")


@router.callback_query(F.data == "group_pool")
async def show_group_pool(callback: CallbackQuery, state: FSMContext):
    """FEAT-группы: открыть пул «свободных» group-заявок (только дежурным)."""
    db_session = None
    try:
        db_session = next(get_db())
        lang = get_user_language(callback.from_user.id, db_session)
        user = db_session.query(User).filter(
            User.telegram_id == callback.from_user.id).first()
        if not user:
            await callback.answer(get_text("common.user_not_found", language=lang), show_alert=True)
            return
        await _render_group_pool(callback.message, db_session, user, lang)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка показа пула свободных заявок: {e}")
        await callback.answer(get_text("common.error", language="ru"), show_alert=True)
    finally:
        if db_session:
            db_session.close()


@router.callback_query(F.data.startswith("claim_request_"))
async def claim_group_request(callback: CallbackQuery, state: FSMContext):
    """FEAT-группы: исполнитель «берёт» group-заявку из пула (EXECUTOR_CLAIM).

    Успех → группа конвертируется в individual на взявшего; заявка уходит из
    пула, у взявшего появляются рабочие действия. NotAuthorized → «уже взято».
    """
    from uk_management_bot.utils.request_workflow import Action
    db_session = None
    try:
        request_number = callback.data.replace("claim_request_", "")
        db_session = next(get_db())
        lang = get_user_language(callback.from_user.id, db_session)
        user = db_session.query(User).filter(
            User.telegram_id == callback.from_user.id).first()
        if not user:
            await callback.answer(get_text("common.user_not_found", language=lang), show_alert=True)
            return
        _outcome, error_key = _run_executor_command(
            request_number, user.id, Action.EXECUTOR_CLAIM, {}, callback.id)
        if error_key is not None:
            # В контексте взятия NotAuthorized/конфликт = заявку уже взяли.
            if error_key in ("requests.executor_not_authorized",
                             "requests.executor_status_conflict"):
                msg = get_text("requests.request_already_claimed", language=lang) \
                    or "Заявку уже взяли"
            else:
                msg = get_text(error_key, language=lang)
            await callback.answer(msg, show_alert=True)
            # пул мог измениться — перерисовать
            await _render_group_pool(callback.message, db_session, user, lang)
            return
        await callback.answer(
            get_text("requests.request_claimed_success", language=lang)
            or "Вы взяли заявку в работу", show_alert=True)
        await _notify_group_pool_claimed(db_session, request_number, user)
        await _render_group_pool(callback.message, db_session, user, lang)
    except Exception as e:
        logger.error(f"Ошибка взятия заявки из пула: {e}")
        await callback.answer(get_text("common.error", language="ru"), show_alert=True)
    finally:
        if db_session:
            db_session.close()


@router.callback_query(F.data.startswith("executor_purchase_"))
async def executor_request_purchase(callback: CallbackQuery, state: FSMContext):
    """Исполнитель переводит заявку в 'Закуп'"""
    db_session = None          # ARCH-013: гарантируем close в finally
    try:
        request_number = callback.data.replace("executor_purchase_", "")
        db_session = next(get_db())
        lang = get_user_language(callback.from_user.id, db_session)

        await state.update_data(executor_request_number=request_number)
        await state.set_state(ExecutorRequestStates.waiting_purchase_comment)

        await callback.message.edit_text(
            get_text("requests.executor_purchase_prompt", language=lang).format(request_number=request_number),
            parse_mode="HTML"
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка начала процесса закупа: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("common.error", language=lang), show_alert=True)
    finally:
        if db_session:
            db_session.close()


@router.message(ExecutorRequestStates.waiting_purchase_comment)
async def executor_process_purchase_comment(message: Message, state: FSMContext):
    """Обработка комментария для закупа"""
    db_session = None          # ARCH-013: гарантируем close в finally
    try:
        data = await state.get_data()
        request_number = data.get("executor_request_number")

        db_session = next(get_db())
        lang = get_user_language(message.from_user.id, db_session)

        request = db_session.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await message.answer(get_text("requests.request_not_found", language=lang))
            await state.clear()
            return

        # Канонический переход (PR2a-5): EXECUTOR_PURCHASE (В работе→Закуп)
        # через единый layer. Комментарий исполнителя → requested_materials
        # (канон-поле). Активную смену + назначение проверяет run_command.
        from uk_management_bot.database.models.user import User as _User
        from uk_management_bot.utils.request_workflow import Action
        actor = db_session.query(_User).filter(_User.telegram_id == message.from_user.id).first()
        outcome, err = _run_executor_command(
            request_number, actor.id if actor else None,
            Action.EXECUTOR_PURCHASE, {"requested_materials": message.text},
            command_id=f"exec-purchase-{request_number}-{message.message_id}",
        )
        if err:
            await message.answer(get_text(err, language=lang))
            await state.clear()
            return

        # Best-effort post-commit: уведомление + ответ. run_command коммитит в
        # отдельной сессии → expire_all сбрасывает identity-map middleware-сессии,
        # иначе повторный query вернёт устаревший объект (не свежий).
        db_session.expire_all()
        request = db_session.query(Request).filter(Request.request_number == request_number).first()
        from uk_management_bot.services.notification_service import async_notify_request_status_changed
        try:
            bot = message.bot
            await async_notify_request_status_changed(bot, db_session, request, outcome.old_status, outcome.public_status)
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления: {e}")

        await message.answer(
            get_text("requests.purchase_comment_saved", language=lang).format(request_number=request_number),
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )

        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка обработки комментария закупа: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await message.answer(get_text("common.error", language=lang))
        await state.clear()
    finally:
        if db_session:
            db_session.close()


@router.callback_query(F.data.startswith("executor_complete_"))
async def executor_complete_request(callback: CallbackQuery, state: FSMContext):
    """Исполнитель переводит заявку в 'Выполнено'"""
    db_session = None          # ARCH-013: гарантируем close в finally
    try:
        request_number = callback.data.replace("executor_complete_", "")
        db_session = next(get_db())
        lang = get_user_language(callback.from_user.id, db_session)

        await state.update_data(executor_request_number=request_number, completion_media=[])
        await state.set_state(ExecutorRequestStates.waiting_completion_comment)

        await callback.message.edit_text(
            get_text("requests.executor_complete_prompt", language=lang).format(request_number=request_number),
            parse_mode="HTML"
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка начала завершения заявки: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("common.error", language=lang), show_alert=True)
    finally:
        if db_session:
            db_session.close()


@router.message(ExecutorRequestStates.waiting_completion_comment)
async def executor_process_completion_comment(message: Message, state: FSMContext):
    """Обработка комментария для завершения"""
    db_session = None          # ARCH-013: гарантируем close в finally
    try:
        data = await state.get_data()
        request_number = data.get("executor_request_number")

        db_session = next(get_db())
        lang = get_user_language(message.from_user.id, db_session)

        await state.update_data(completion_comment=message.text)
        await state.set_state(ExecutorRequestStates.waiting_completion_media)

        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_text("requests.finish_without_media", language=lang), callback_data=f"executor_finish_completion_{request_number}")],
            [InlineKeyboardButton(text=get_text("common.cancel", language=lang), callback_data=f"view_request_{request_number}")]
        ])

        await message.answer(
            get_text("requests.send_completion_media_prompt", language=lang),
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Ошибка обработки комментария завершения: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await message.answer(get_text("common.error", language=lang))
        await state.clear()
    finally:
        if db_session:
            db_session.close()


@router.message(ExecutorRequestStates.waiting_completion_media, F.photo | F.video | F.document)
async def executor_collect_completion_media(message: Message, state: FSMContext):
    """Сбор медиа-файлов для завершения заявки"""
    db_session = None          # ARCH-013: гарантируем close в finally
    try:
        data = await state.get_data()
        completion_media = data.get("completion_media", [])
        request_number = data.get("executor_request_number")

        db_session = next(get_db())
        lang = get_user_language(message.from_user.id, db_session)

        # Добавляем файл в список
        if message.photo:
            completion_media.append({"type": "photo", "file_id": message.photo[-1].file_id})
        elif message.video:
            completion_media.append({"type": "video", "file_id": message.video.file_id})
        elif message.document:
            completion_media.append({"type": "document", "file_id": message.document.file_id})

        await state.update_data(completion_media=completion_media)

        # Обновляем клавиатуру с счетчиком
        finish_button_text = get_text("requests.finish_with_files", language=lang).format(count=len(completion_media))
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=finish_button_text, callback_data=f"executor_finish_completion_{request_number}")],
            [InlineKeyboardButton(text=get_text("common.cancel", language=lang), callback_data=f"view_request_{request_number}")]
        ])

        await message.answer(
            get_text("requests.file_added_send_more", language=lang).format(count=len(completion_media)),
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Ошибка сбора медиа для завершения: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await message.answer(get_text("common.error", language=lang))
    finally:
        if db_session:
            db_session.close()


@router.callback_query(F.data.startswith("executor_finish_completion_"))
async def executor_finish_completion(callback: CallbackQuery, state: FSMContext):
    """Финализация завершения заявки"""
    db_session = None          # ARCH-013: гарантируем close в finally
    try:
        request_number = callback.data.replace("executor_finish_completion_", "")
        data = await state.get_data()
        completion_comment = data.get("completion_comment", "")
        completion_media = data.get("completion_media", [])

        db_session = next(get_db())
        lang = get_user_language(callback.from_user.id, db_session)

        request = db_session.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await callback.answer(get_text("requests.request_not_found", language=lang), show_alert=True)
            await state.clear()
            return

        # Загружаем медиа-файлы в Media Service (если есть)
        media_service_files = []
        if completion_media:
            from uk_management_bot.utils.media_helpers import upload_report_file_to_media_service
            bot = callback.bot

            # Получаем user_id для uploaded_by
            from uk_management_bot.database.models.user import User
            user = db_session.query(User).filter(User.telegram_id == callback.from_user.id).first()
            uploaded_by = user.id if user else None

            logger.info(f"Загрузка {len(completion_media)} файлов в Media Service для заявки {request_number}")

            for idx, media_item in enumerate(completion_media, 1):
                file_id = media_item.get("file_id")
                file_type = media_item.get("type", "photo")

                # Определяем report_type на основе типа файла
                if file_type == "video":
                    report_type = "completion_video"
                elif file_type == "document":
                    report_type = "completion_document"
                else:
                    report_type = "completion_photo"

                try:
                    result = await upload_report_file_to_media_service(
                        bot=bot,
                        file_id=file_id,
                        request_number=request_number,
                        report_type=report_type,
                        description=f"Report #{idx}",
                        uploaded_by=uploaded_by
                    )

                    if result:
                        media_service_files.append({
                            "media_id": result["media_file"]["id"],
                            "file_url": result["media_file"]["file_url"],
                            "type": file_type
                        })
                        logger.info(f"Файл #{idx} загружен в Media Service: media_id={result['media_file']['id']}")
                    else:
                        logger.warning(f"Не удалось загрузить файл #{idx} в Media Service")

                except Exception as e:
                    logger.error(f"Ошибка загрузки файла #{idx} в Media Service: {e}")

        # Канонический переход (PR2a-5): EXECUTOR_COMPLETE (В работе→Выполнена)
        # через единый layer. Медиа уже загружены в Media Service ВЫШЕ (сетевой
        # I/O — вне транзакции). Отчёт → completion_report, файлы →
        # completion_media (list; ридеры принимают и list, и json-строку).
        from uk_management_bot.database.models.user import User as _User
        from uk_management_bot.utils.request_workflow import Action
        actor = db_session.query(_User).filter(_User.telegram_id == callback.from_user.id).first()
        media_payload = media_service_files if media_service_files else completion_media
        outcome, err = _run_executor_command(
            request_number, actor.id if actor else None,
            Action.EXECUTOR_COMPLETE,
            {"completion_report": completion_comment or "",
             "completion_media": media_payload or []},
            command_id=f"exec-complete-{request_number}-{callback.id}",
        )
        if err:
            await callback.answer(get_text(err, language=lang), show_alert=True)
            await state.clear()
            return

        # Best-effort post-commit: уведомление. expire_all сбрасывает identity-map
        # middleware-сессии (run_command коммитит в отдельной) → query вернёт свежий объект.
        db_session.expire_all()
        request = db_session.query(Request).filter(Request.request_number == request_number).first()
        from uk_management_bot.services.notification_service import async_notify_request_status_changed
        try:
            await async_notify_request_status_changed(callback.bot, db_session, request, outcome.old_status, outcome.public_status)
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления: {e}")

        # Формируем сообщение с результатом
        message_text = get_text("requests.request_completed_title", language=lang).format(request_number=request_number)
        message_text += get_text("requests.comment_label", language=lang).format(comment=completion_comment)
        if media_service_files:
            message_text += get_text("requests.files_uploaded_to_media_service", language=lang).format(count=len(media_service_files))
        elif completion_media:
            message_text += get_text("requests.files_saved_locally", language=lang).format(count=len(completion_media))

        await callback.message.edit_text(message_text, parse_mode="HTML")

        await state.clear()
        await callback.answer(get_text("requests.request_completed_short", language=lang))

    except Exception as e:
        logger.error(f"Ошибка финализации завершения: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("common.error", language=lang), show_alert=True)
        await state.clear()
    finally:
        if db_session:
            db_session.close()


@router.callback_query(F.data.startswith("executor_work_"))
async def executor_return_to_work(callback: CallbackQuery):
    """Возврат заявки в работу из статуса Закуп/Уточнение"""
    db_session = None          # ARCH-013: гарантируем close в finally
    try:
        request_number = callback.data.replace("executor_work_", "")
        db_session = next(get_db())
        lang = get_user_language(callback.from_user.id, db_session)

        # Канонический переход (PR2a-5): EXECUTOR_RESUME (Закуп/Уточнение→
        # В работе) через единый layer. Исполнителю разрешён self-resume
        # (продуктовое решение 2026-06-10); активную смену+назначение проверяет
        # run_command.
        from uk_management_bot.database.models.user import User as _User
        from uk_management_bot.utils.request_workflow import Action
        actor = db_session.query(_User).filter(_User.telegram_id == callback.from_user.id).first()
        outcome, err = _run_executor_command(
            request_number, actor.id if actor else None,
            Action.EXECUTOR_RESUME, {},
            command_id=f"exec-resume-{request_number}-{callback.id}",
        )
        if err:
            await callback.answer(get_text(err, language=lang), show_alert=True)
            return

        # Best-effort post-commit: уведомление. expire_all сбрасывает identity-map
        # middleware-сессии (run_command коммитит в отдельной) → query вернёт свежий объект.
        db_session.expire_all()
        request = db_session.query(Request).filter(Request.request_number == request_number).first()
        from uk_management_bot.services.notification_service import async_notify_request_status_changed
        try:
            bot = callback.bot
            await async_notify_request_status_changed(bot, db_session, request, outcome.old_status, outcome.public_status)
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления: {e}")

        await callback.message.edit_text(
            get_text("requests.request_returned_to_work", language=lang).format(request_number=request_number),
            parse_mode="HTML"
        )
        await callback.answer(get_text("requests.request_in_work", language=lang))

    except Exception as e:
        logger.error(f"Ошибка возврата заявки в работу: {e}")
        lang = "ru"            # ARCH-013: не открываем вторую сессию на error-path
        await callback.answer(get_text("common.error", language=lang), show_alert=True)
    finally:
        if db_session:
            db_session.close()
