"""Создание заявки: FSM (категория→адрес→описание→срочность→медиа→подтв.) + save_request."""

from aiogram import F, Bot
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session
from uk_management_bot.database.models.request import Request
from uk_management_bot.services.request_handler_service import RequestHandlerService

from uk_management_bot.keyboards.requests import (
    get_cancel_keyboard,
    get_media_keyboard,
    get_confirmation_keyboard,
    get_categories_inline_keyboard_with_cancel,
    get_urgency_inline_keyboard,
    get_inline_confirmation_keyboard,
)
from uk_management_bot.keyboards.base import get_contextual_keyboard, get_user_contextual_keyboard
from uk_management_bot.utils.validators import (
    validate_media_file
)
import logging
from typing import Optional

# Localization imports - TASK 17 Phase 2
from uk_management_bot.utils.helpers import get_text
# Single Source of Truth for button texts - TASK 17 Entry Handler Fix

from ._router import router

from .shared import (
    _db_scope,
    _get_user_language,
    _deny_if_pending_message,
    _deny_if_pending_callback,
    RequestStates,
    _load_user_request_addresses,
    _has_any_address,
    CREATE_REQUEST_TEXTS,
)

logger = logging.getLogger(__name__)


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
    try:
        with _db_scope(None) as db:
            user = RequestHandlerService(db).get_user_by_telegram_id(message.from_user.id)
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

    from uk_management_bot.services.request_address import (
        resolve_request_address_sync,
        AddressResolutionError,
    )

    with _db_scope(None) as db:
        user = RequestHandlerService(db).get_user_by_telegram_id(callback.from_user.id)
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
        service = RequestHandlerService(db)
        user = service.get_user_by_telegram_id(user_id)

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
        logger.info("[SAVE_REQUEST] Сохранение в БД...")
        # Адрес и FK — из резолвера (сервер), а не из FSM/клиента. В модели
        # media_files ожидается JSON (список) — храним file_ids как backup,
        # основное хранилище Media Service.
        request = service.create_request_record(
            request_number=request_number,
            category=data['category'],
            address=resolved.canonical_address,
            description=data['description'],
            urgency=data['urgency'],
            apartment_id=resolved.apartment_id,
            building_id=resolved.building_id,
            yard_id=resolved.yard_id,
            address_type=resolved.address_type,
            media_files=list(media_file_ids),
            user_id=user.id,  # Используем id пользователя из базы данных
            source=source,
            status='Новая',
        )

        # ARCH-113: emit + INSERT in one transaction — protects against orphan
        # requests (request row durable but outbox row missing on commit failure).
        # source задаёт доверенный call-site (не FSM): applicant→"bot", обходчик→"inspector".
        from uk_management_bot.services.webhook_payloads import emit_request_created_sync
        emit_request_created_sync(db, request, source=source)

        service.commit()

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

