from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.orm import Session
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.session import get_db
from uk_management_bot.database.models.user import User
from uk_management_bot.keyboards.requests import (
    get_categories_keyboard, 
    get_urgency_keyboard,
    get_cancel_keyboard,
    get_media_keyboard,
    get_confirmation_keyboard,
    get_address_selection_keyboard,
    parse_selected_address,
    get_categories_inline_keyboard,
    get_categories_inline_keyboard_with_cancel,
    get_urgency_inline_keyboard,
    get_inline_confirmation_keyboard,
)
from uk_management_bot.keyboards.base import get_main_keyboard, get_contextual_keyboard, get_user_contextual_keyboard
from uk_management_bot.keyboards.requests import (
    get_status_filter_inline_keyboard,
    get_category_filter_inline_keyboard,
    get_reset_filters_inline_keyboard,
    get_period_filter_inline_keyboard,
    get_executor_filter_inline_keyboard,
)
from uk_management_bot.utils.validators import (
    validate_address, 
    validate_description, 
    validate_media_file
)
from uk_management_bot.config.settings import settings
from uk_management_bot.utils.constants import REQUEST_CATEGORIES, REQUEST_URGENCIES
from uk_management_bot.utils.constants import REQUEST_CATEGORIES
import logging
from datetime import datetime
from uk_management_bot.services.request_service import RequestService
from uk_management_bot.services.auth_service import AuthService
from uk_management_bot.services.notification_service import async_notify_action_denied
from uk_management_bot.utils.constants import ERROR_MESSAGES
from typing import Optional

logger = logging.getLogger(__name__)

router = Router()

# Добавляем middleware в роутер
from uk_management_bot.middlewares.auth import auth_middleware, role_mode_middleware
router.message.middleware(auth_middleware)
router.message.middleware(role_mode_middleware)
router.callback_query.middleware(auth_middleware)
router.callback_query.middleware(role_mode_middleware)

# Вспомогательные функции для улучшенной обработки ошибок и UX

async def _deny_if_pending_message(message: Message, user_status: Optional[str]) -> bool:
    """Единый ранний отказ для пользователей со статусом pending (Message).

    Возвращает True, если обработку нужно прервать.
    """
    if user_status == "pending":
        try:
            from uk_management_bot.utils.helpers import get_text
            lang = getattr(message.from_user, "language_code", None) or "ru"
            await message.answer(get_text("auth.pending", language=lang))
        except Exception:
            await message.answer("⏳ Ваша заявка на регистрацию находится на рассмотрении.")
        return True
    return False

async def _deny_if_pending_callback(callback: CallbackQuery, user_status: Optional[str]) -> bool:
    """Единый ранний отказ для пользователей со статусом pending (CallbackQuery).

    Возвращает True, если обработку нужно прервать.
    """
    if user_status == "pending":
        try:
            from uk_management_bot.utils.helpers import get_text
            lang = getattr(callback.from_user, "language_code", None) or "ru"
            await callback.answer(get_text("auth.pending", language=lang), show_alert=True)
        except Exception:
            await callback.answer("⏳ Ожидайте одобрения администратора.", show_alert=True)
        return True
    return False

def get_contextual_help(address_type: str) -> str:
    """
    Получить контекстную помощь в зависимости от типа адреса
    
    Args:
        address_type: Тип адреса (home/apartment/yard)
        
    Returns:
        str: Контекстное сообщение с подсказками
    """
    help_templates = {
        "home": "🏠 Вы выбрали дом. Обычно проблемы связаны с:\n• Электрикой\n• Отоплением\n• Водоснабжением\n• Безопасностью\n\nОпишите проблему подробно:",
        "apartment": "🏢 Вы выбрали квартиру. Частые проблемы:\n• Сантехника\n• Электрика\n• Вентиляция\n• Лифт\n\nОпишите проблему подробно:",
        "yard": "🌳 Вы выбрали двор. Типичные проблемы:\n• Благоустройство\n• Освещение\n• Уборка\n• Безопасность\n\nОпишите проблему подробно:"
    }
    return help_templates.get(address_type, "Опишите проблему подробно:")

async def graceful_fallback(message: Message, error_type: str):
    """
    Graceful degradation при ошибках
    
    Args:
        message: Сообщение пользователя
        error_type: Тип ошибки
    """
    fallback_messages = {
        "auth_service_error": "Временно недоступны сохраненные адреса. Введите адрес вручную:",
        "parsing_error": "Не удалось распознать выбор. Пожалуйста, выберите из списка:",
        "keyboard_error": "Проблемы с отображением клавиатуры. Введите адрес вручную:",
        "critical_error": "Произошла ошибка. Попробуйте еще раз или введите адрес вручную:"
    }
    
    error_message = fallback_messages.get(error_type, "Произошла ошибка. Попробуйте еще раз:")
    await message.answer(error_message, reply_markup=get_cancel_keyboard())
    
    logger.warning(f"[GRACEFUL_FALLBACK] Ошибка типа '{error_type}' для пользователя {message.from_user.id}")

def smart_address_validation(address_text: str) -> dict:
    """
    Умная валидация адреса с предложениями
    
    Args:
        address_text: Текст адреса для валидации
        
    Returns:
        dict: Результат валидации с предложениями
    """
    suggestions = []
    is_valid = True
    
    # Проверка минимальной длины
    if len(address_text) < 10:
        suggestions.append("Добавьте больше деталей (улица, дом, квартира)")
        is_valid = False
    
    # Проверка наличия улицы
    street_indicators = ["ул.", "улица", "проспект", "просп.", "переулок", "пер."]
    has_street = any(indicator in address_text.lower() for indicator in street_indicators)
    if not has_street:
        suggestions.append("Укажите тип улицы (ул., проспект, переулок)")
        is_valid = False
    
    # Проверка наличия номера дома (улучшенная логика)
    house_indicators = ["д.", "дом", "№"]
    has_house = any(indicator in address_text.lower() for indicator in house_indicators)
    
    # Дополнительная проверка: если есть цифры после запятой или пробела, считаем что номер дома есть
    import re
    if not has_house:
        # Ищем паттерн: улица + запятая/пробел + цифра
        house_pattern = r'[,\s]\d+'
        if re.search(house_pattern, address_text):
            has_house = True
    
    if not has_house:
        suggestions.append("Укажите номер дома")
        is_valid = False
    
    # Проверка на наличие цифр (номера)
    if not any(char.isdigit() for char in address_text):
        suggestions.append("Добавьте номера (дом, квартира)")
        is_valid = False
    
    return {
        'is_valid': is_valid,
        'suggestions': suggestions
    }

# Временно отключаем отладочный обработчик
# @router.message(F.text)
# async def debug_all_messages(message: Message):
#     """Отладочный обработчик для всех текстовых сообщений"""
#     logger.info(f"DEBUG: Получено сообщение от {message.from_user.id}: '{message.text}'")

class RequestStates(StatesGroup):
    """Состояния FSM для создания заявок"""
    category = State()           # Выбор категории
    address = State()            # Выбор адреса (обновлено)
    address_manual = State()     # Ручной ввод адреса (новое)
    description = State()        # Описание проблемы
    urgency = State()           # Выбор срочности
    media = State()             # Медиафайлы
    confirm = State()           # Подтверждение
    waiting_clarify_reply = State()  # Ответ на уточнение

# Начало создания заявки
@router.message(F.text == "Создать заявку")
async def start_request_creation(message: Message, state: FSMContext, user_status: Optional[str] = None):
    """Начало создания заявки"""
    if await _deny_if_pending_message(message, user_status):
        return
    logger.info(f"Пользователь {message.from_user.id} нажал 'Создать заявку'")
    await state.set_state(RequestStates.category)
    # Скрываем главное меню (ReplyKeyboard) на время сценария создания заявки
    await message.answer("Начинаем создание заявки…", reply_markup=ReplyKeyboardRemove())
    # Показываем inline-клавиатуру категорий
    await message.answer("Выберите категорию заявки:", reply_markup=get_categories_inline_keyboard_with_cancel())
    logger.info(f"Пользователь {message.from_user.id} начал создание заявки")

# Альтернативный обработчик для отладки
@router.message(F.text == "📝 Создать заявку")
async def start_request_creation_emoji(message: Message, state: FSMContext, user_status: Optional[str] = None):
    """Начало создания заявки (с эмодзи)"""

    
    if await _deny_if_pending_message(message, user_status):
        return
    logger.info(f"Пользователь {message.from_user.id} нажал '📝 Создать заявку'")
    await state.set_state(RequestStates.category)
    # Скрываем главное меню (ReplyKeyboard) на время сценария создания заявки
    await message.answer("Начинаем создание заявки…", reply_markup=ReplyKeyboardRemove())
    # Показываем inline-клавиатуру категорий
    await message.answer("Выберите категорию заявки:", reply_markup=get_categories_inline_keyboard_with_cancel())
    logger.info(f"Пользователь {message.from_user.id} начал создание заявки")

# Обработка выбора категории (только если пользователь ввёл текст ровно из списка категорий)
@router.message(RequestStates.category, F.text.in_(REQUEST_CATEGORIES))
async def process_category(message: Message, state: FSMContext):
    """Обработка выбора категории с улучшенной интеграцией"""
    user_id = message.from_user.id
    category_text = message.text
    
    logger.info(f"[CATEGORY_SELECTION] Пользователь {user_id}: '{category_text}'")
    
    if category_text == "❌ Отмена":
        await cancel_request(message, state)
        return
    
    # Сохраняем категорию и переходим к выбору адреса
    await state.update_data(category=category_text)
    await state.set_state(RequestStates.address)
    
    # Показываем клавиатуру выбора адреса с улучшенным UX
    try:
        logger.info(f"[CATEGORY_SELECTION] Создание клавиатуры выбора адреса для пользователя {user_id}")
        keyboard = await get_address_selection_keyboard(user_id)
        logger.info(f"[CATEGORY_SELECTION] Клавиатура создана, отправка пользователю {user_id}")
        
        await message.answer(
            "💡 Выберите адрес:\n"
            "• Выберите сохраненный адрес для быстрого создания\n"
            "• Или введите адрес вручную",
            reply_markup=keyboard
        )
        logger.info(f"[CATEGORY_SELECTION] Пользователь {user_id} выбрал категорию '{category_text}', переходит к выбору адреса")
    except Exception as e:
        logger.error(f"[CATEGORY_SELECTION] Ошибка создания клавиатуры выбора адреса: {e}")
        await graceful_fallback(message, "keyboard_error")

# Игнор/подсказка для любых других текстов в состоянии выбора категории
@router.message(RequestStates.category)
async def process_category_other_inputs(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await cancel_request(message, state)
        return
    # Ничего не навязываем: мягкая подсказка без повторной отправки клавиатуры категорий
    await message.answer("Пожалуйста, используйте кнопки выбора категории выше или нажмите '❌ Отмена'.")

# Обработка выбора адреса (обновленная логика)
@router.message(RequestStates.address)
async def process_address(message: Message, state: FSMContext):
    """Обработка выбора адреса с новой клавиатурой"""
    user_id = message.from_user.id
    selected_text = message.text
    
    # Улучшенное логирование с контекстом
    logger.info(f"[ADDRESS_SELECTION] Пользователь {user_id}: '{selected_text}'")
    logger.info(f"[ADDRESS_SELECTION] Время: {datetime.now()}")
    logger.info(f"[ADDRESS_SELECTION] Состояние FSM: {await state.get_state()}")
    
    try:
        # Парсим выбор пользователя
        result = await parse_selected_address(selected_text)
        logger.info(f"[ADDRESS_SELECTION] Результат парсинга: {result}")
        
        if result['type'] == 'predefined':
            # Используем выбранный адрес; квартира считается указанной в адресе
            await state.update_data(address=result['address'])
            await state.set_state(RequestStates.description)
            
            # Контекстное сообщение в зависимости от типа адреса
            context_message = get_contextual_help(result['address_type'])
            await message.answer(context_message, reply_markup=get_cancel_keyboard())
            
            logger.info(f"[ADDRESS_SELECTION] Пользователь {user_id} выбрал готовый адрес: {result['address']}, тип: {result['address_type']}")
            
        elif result['type'] == 'manual':
            # Перейти к ручному вводу
            await state.set_state(RequestStates.address_manual)
            await message.answer(
                "✏️ Введите адрес вручную:\n"
                "Например: ул. Ленина, 1, кв. 5",
                reply_markup=get_cancel_keyboard()
            )
            logger.info(f"[ADDRESS_SELECTION] Пользователь {user_id} перешел к ручному вводу адреса")
            
        elif result['type'] == 'cancel':
            # Отменить создание заявки
            await cancel_request(message, state)
            return
            
        elif result['type'] == 'unknown':
            # Неизвестный выбор - улучшенная обработка
            logger.warning(f"[ADDRESS_SELECTION] Неизвестный выбор адреса: '{selected_text}' от пользователя {user_id}")
            await message.answer(
                "Пожалуйста, выберите адрес из предложенных вариантов или введите вручную"
            )
            # Показываем клавиатуру снова
            try:
                keyboard = await get_address_selection_keyboard(user_id)
                await message.answer("Выберите адрес:", reply_markup=keyboard)
            except Exception as keyboard_error:
                logger.error(f"[ADDRESS_SELECTION] Ошибка создания клавиатуры: {keyboard_error}")
                await graceful_fallback(message, "keyboard_error")
            
        else:
            # Обработка других типов ошибок
            logger.error(f"[ADDRESS_SELECTION] Неожиданный тип результата: {result['type']}")
            await graceful_fallback(message, "parsing_error")
            
    except Exception as e:
        logger.error(f"[ADDRESS_SELECTION] Критическая ошибка обработки выбора адреса: {e}")
        await graceful_fallback(message, "critical_error")

# Обработка ручного ввода адреса (новое состояние)
@router.message(RequestStates.address_manual)
async def process_address_manual(message: Message, state: FSMContext):
    """Обработка ручного ввода адреса с умной валидацией"""
    user_id = message.from_user.id
    address_text = message.text
    
    logger.info(f"[ADDRESS_MANUAL] Пользователь {user_id}: '{address_text}'")
    
    if address_text == "❌ Отмена":
        await cancel_request(message, state)
        return
    
    # Умная валидация с предложениями
    validation_result = smart_address_validation(address_text)
    if not validation_result['is_valid']:
        suggestions_text = "\n".join([f"• {suggestion}" for suggestion in validation_result['suggestions']])
        await message.answer(
            f"⚠️ Адрес требует доработки:\n{suggestions_text}\n\nПопробуйте еще раз:",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    # Сохраняем адрес
    await state.update_data(address=address_text)
    
    # В новой логике квартира вводится прямо в адресе при ручном вводе
    await state.set_state(RequestStates.description)
    await message.answer(
        "✅ Адрес сохранен! Опишите проблему:",
        reply_markup=get_cancel_keyboard()
    )
    logger.info(f"[ADDRESS_MANUAL] Пользователь {user_id} ввел адрес: {address_text}")

# Обработка ввода описания
@router.message(RequestStates.description)
async def process_description(message: Message, state: FSMContext):
    """Обработка ввода описания проблемы"""
    if message.text == "❌ Отмена":
        await cancel_request(message, state)
        return
    
    # Валидируем описание с помощью валидатора
    from uk_management_bot.utils.validators import Validator
    is_valid, error_message = Validator.validate_description(message.text)
    if not is_valid:
        await message.answer(error_message)
        return
    
    # Сохраняем описание и переходим к выбору срочности
    await state.update_data(description=message.text)
    await state.set_state(RequestStates.urgency)
    await message.answer(
        "Выберите срочность:",
        reply_markup=get_urgency_inline_keyboard()
    )
    logger.info(f"Пользователь {message.from_user.id} ввел описание")

# Обработка выбора срочности
@router.message(RequestStates.urgency)
async def process_urgency(message: Message, state: FSMContext):
    """Обработка выбора срочности (квартира больше не запрашивается отдельно)"""
    if message.text == "❌ Отмена":
        await cancel_request(message, state)
        return
    
    valid_urgency_levels = REQUEST_URGENCIES
    
    if message.text not in valid_urgency_levels:
        # Срочность выбирается через inline-клавиатуру. Если пришел текст — показать inline-клавиатуру снова.
        await message.answer(
            "Пожалуйста, выберите срочность из списка:",
            reply_markup=get_urgency_inline_keyboard()
        )
        return
    
    # Сохраняем срочность и сразу переходим к медиа
    await state.update_data(urgency=message.text)
    await state.set_state(RequestStates.media)
    await message.answer(
        "Отправьте фото или видео (опционально, максимум 5 файлов):\n"
        "Или нажмите 'Продолжить' для перехода к подтверждению",
        reply_markup=get_media_keyboard()
    )
    logger.info(f"Пользователь {message.from_user.id} выбрал срочность: {message.text}")

## Шаг квартиры полностью исключён из процесса.

# Обработка медиафайлов
@router.message(RequestStates.media, F.photo | F.video)
async def process_media(message: Message, state: FSMContext):
    """Обработка медиафайлов"""
    data = await state.get_data()
    media_files = data.get('media_files', [])
    
    if len(media_files) >= 5:
        await message.answer("Максимум 5 файлов")
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
        await message.answer("Файл слишком большой. Максимальный размер: 20MB")
        return
    
    media_files.append(file_id)
    await state.update_data(media_files=media_files)
    
    await message.answer(
        f"Файл добавлен ({len(media_files)}/5). Отправьте еще файлы или нажмите 'Продолжить'",
        reply_markup=get_media_keyboard()
    )
    logger.info(f"Пользователь {message.from_user.id} добавил медиафайл")

# Обработка текста в состоянии media (продолжить/отмена)
@router.message(RequestStates.media)
async def process_media_text(message: Message, state: FSMContext):
    """Обработка текста в состоянии media"""
    if message.text == "❌ Отмена":
        await cancel_request(message, state)
        return
    
    if message.text == "▶️ Продолжить":
        await state.set_state(RequestStates.confirm)
        await show_confirmation(message, state)
        return
    
    await message.answer(
        "Отправьте фото/видео или нажмите 'Продолжить'",
        reply_markup=get_media_keyboard()
    )

# Показ сводки заявки
async def show_confirmation(message: Message, state: FSMContext):
    """Показать сводку заявки для подтверждения"""
    data = await state.get_data()
    
    summary = (
        "📋 Сводка заявки:\n\n"
        f"🏷️ Категория: {data['category']}\n"
        f"📍 Адрес: {data['address']}\n"
        f"📝 Описание: {data['description']}\n"
        f"⚡ Срочность: {data['urgency']}\n"
        f"📸 Файлов: {len(data.get('media_files', []))}\n\n"
        "Подтвердите создание заявки:"
    )
    
    await message.answer(
        summary,
        reply_markup=get_inline_confirmation_keyboard()
    )

# Обработка подтверждения
@router.message(RequestStates.confirm)
async def process_confirmation(message: Message, state: FSMContext, db: Session, roles: list = None, active_role: str = None):
    """Обработка подтверждения заявки"""
    if message.text == "❌ Отмена":
        await cancel_request(message, state)
        return
    
    if message.text == "🔙 Назад":
        await state.set_state(RequestStates.media)
        await message.answer(
            "Вернулись к загрузке файлов. Отправьте фото/видео или нажмите 'Продолжить'",
            reply_markup=get_media_keyboard()
        )
        return
    
    if message.text == "✅ Подтвердить":
        data = await state.get_data()
        
        # Сохраняем заявку в базу данных
        success = await save_request(data, message.from_user.id, db)
        
        if success:
            await state.clear()
            await message.answer(
                "✅ Заявка успешно создана! Мы рассмотрим её в ближайшее время.",
                reply_markup=get_contextual_keyboard(roles, active_role) if roles and active_role else get_user_contextual_keyboard(message.from_user.id)
            )
            logger.info(f"Пользователь {message.from_user.id} создал заявку")
        else:
            # Очищаем состояние, чтобы пользователь мог продолжить работу (например, открыть Мои заявки)
            await state.clear()
            await message.answer(
                "❌ Ошибка при создании заявки. Попробуйте еще раз.",
                reply_markup=get_user_contextual_keyboard(message.from_user.id)
            )
            logger.error(f"Ошибка создания заявки пользователем {message.from_user.id}")
        return
    
    await message.answer(
        "Пожалуйста, выберите действие:",
        reply_markup=get_confirmation_keyboard()
    )

# Отмена создания заявки
async def cancel_request(message: Message, state: FSMContext, roles: list = None, active_role: str = None):
    """Отмена создания заявки"""
    await state.clear()
    await message.answer(
        "Создание заявки отменено.",
        reply_markup=get_user_contextual_keyboard(message.from_user.id)
    )
    logger.info(f"Пользователь {message.from_user.id} отменил создание заявки")

# Сохранение заявки в базу данных
async def save_request(data: dict, user_id: int, db: Session) -> bool:
    """Сохранение заявки в базу данных"""
    try:
        # Получаем пользователя из базы данных по telegram_id
        from uk_management_bot.database.models.user import User
        user = db.query(User).filter(User.telegram_id == user_id).first()
        
        if not user:
            logger.error(f"Пользователь с telegram_id {user_id} не найден в базе данных")
            return False
        
        request = Request(
            category=data['category'],
            address=data['address'],
            description=data['description'],
            urgency=data['urgency'],
            apartment=data.get('apartment'),
            # В модели media_files ожидается JSON (список), поэтому сохраняем список
            media_files=list(data.get('media_files', [])),
            user_id=user.id,  # Используем id пользователя из базы данных
            status='Новая'
        )
        
        db.add(request)
        db.commit()
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения заявки: {e}")
        return False

# =====================================
# ОБРАБОТЧИКИ CALLBACK_QUERY ДЛЯ INLINE КЛАВИАТУР
# =====================================

@router.callback_query(F.data.startswith("category_"))
async def handle_category_selection(callback: CallbackQuery, state: FSMContext, user_status: Optional[str] = None):
    """Обработка выбора категории заявки через inline клавиатуру"""
    if await _deny_if_pending_callback(callback, user_status):
        return
    try:
        logger.info(f"Обработка выбора категории для пользователя {callback.from_user.id}")
        
        # Извлекаем категорию из callback данных
        category = callback.data.replace("category_", "")
        
        # Валидируем категорию
        valid_categories = REQUEST_CATEGORIES
        
        if category not in valid_categories:
            await callback.answer("Неверная категория", show_alert=True)
            logger.warning(f"Неверная категория '{category}' от пользователя {callback.from_user.id}")
            return
        
        # Сохраняем в FSM
        await state.update_data(category=category)
        
        # Переходим к следующему состоянию
        await state.set_state(RequestStates.address)
        
        # Информационное редактирование исходного сообщения (без ReplyKeyboardMarkup)
        await callback.message.edit_text(
            f"Выбрана категория: {category}\n\nВыберите адрес:"
        )
        # Отправляем новое сообщение с ReplyKeyboardMarkup для выбора адреса
        keyboard = await get_address_selection_keyboard(callback.from_user.id)
        await callback.message.answer(
            "💡 Выберите адрес или введите вручную:",
            reply_markup=keyboard
        )
        
        logger.info(f"Пользователь {callback.from_user.id} выбрал категорию: {category}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки выбора категории: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "cancel_create")
async def handle_cancel_create(callback: CallbackQuery, state: FSMContext):
    """Отмена создания заявки из выбора категории (inline)."""
    try:
        await state.clear()
        await callback.message.edit_text("Создание заявки отменено.")
        await callback.message.answer("Возврат в главное меню.", reply_markup=get_user_contextual_keyboard(callback.from_user.id))
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка отмены создания заявки: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data.startswith("urgency_"))
async def handle_urgency_selection(callback: CallbackQuery, state: FSMContext, user_status: Optional[str] = None):
    """Обработка выбора уровня срочности через inline клавиатуру"""
    if await _deny_if_pending_callback(callback, user_status):
        return
    try:
        logger.info(f"Обработка выбора срочности для пользователя {callback.from_user.id}")
        
        urgency = callback.data.replace("urgency_", "")
        valid_urgency = REQUEST_URGENCIES
        
        if urgency not in valid_urgency:
            await callback.answer("Неверный уровень срочности", show_alert=True)
            logger.warning(f"Неверная срочность '{urgency}' от пользователя {callback.from_user.id}")
            return
        
        await state.update_data(urgency=urgency)

        # Редактируем исходное сообщение (без передачи ReplyKeyboardMarkup)
        await callback.message.edit_text(
            f"Выбрана срочность: {urgency}"
        )

        # Шаг квартиры исключён: сразу переходим к медиа
        await state.set_state(RequestStates.media)
        await callback.message.answer(
            "Отправьте фото или видео (опционально, максимум 5 файлов):\nИли нажмите 'Продолжить' для перехода к подтверждению",
            reply_markup=get_media_keyboard()
        )
        logger.info(f"Пользователь {callback.from_user.id} выбрал срочность: {urgency}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки выбора срочности: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data.startswith("confirm_"))
async def handle_confirmation(callback: CallbackQuery, state: FSMContext, user_status: Optional[str] = None):
    """Обработка подтверждения заявки через inline клавиатуру"""
    if await _deny_if_pending_callback(callback, user_status):
        return
    try:
        logger.info(f"Обработка подтверждения для пользователя {callback.from_user.id}")
        
        action = callback.data.replace("confirm_", "")
        
        if action == "yes":
            # Получаем данные из FSM
            data = await state.get_data()
            
            # Создаем заявку в базе данных
            db_session = next(get_db())
            success = await save_request(data, callback.from_user.id, db_session)
            
            if success:
                # Редактируем исходное сообщение без ReplyKeyboardMarkup
                await callback.message.edit_text(
                    f"✅ Заявка успешно создана!\n\n"
                    f"Категория: {data.get('category', 'Не указана')}\n"
                    f"Адрес: {data.get('address', 'Не указан')}\n"
                    f"Срочность: {data.get('urgency', 'Обычная')}"
                )
                # Отправляем отдельное сообщение с главной клавиатурой
                await callback.message.answer(
                    "Возврат в главное меню.",
                    reply_markup=get_user_contextual_keyboard(callback.from_user.id)
                )
                await state.clear()
                logger.info(f"Заявка создана пользователем {callback.from_user.id}")
            else:
                # Очищаем состояние и показываем главное меню, чтобы пользователь мог продолжить
                await state.clear()
                await callback.message.answer(
                    "❌ Ошибка при создании заявки. Попробуйте ещё раз.",
                    reply_markup=get_user_contextual_keyboard(callback.from_user.id)
                )
                await callback.answer("Ошибка сохранения заявки", show_alert=True)
                
        elif action == "no":
            await callback.message.edit_text(
                "❌ Создание заявки отменено"
            )
            await callback.message.answer(
                "Возврат в главное меню.",
                reply_markup=get_user_contextual_keyboard(callback.from_user.id)
            )
            await state.clear()
            logger.info(f"Создание заявки отменено пользователем {callback.from_user.id}")
            
    except Exception as e:
        logger.error(f"Ошибка обработки подтверждения: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data.startswith("page_"))
async def handle_pagination(callback: CallbackQuery, state: FSMContext):
    """Обработка пагинации списков заявок"""
    try:
        logger.info(f"Обработка пагинации для пользователя {callback.from_user.id}")
        
        # Парсим данные пагинации
        current_page = int(callback.data.replace("page_", ""))

        # Читаем активный фильтр из FSM
        data = await state.get_data()
        active_status = data.get("my_requests_status")

        # Получаем список заявок пользователя с учетом фильтра
        db_session = next(get_db())
        
        # Получаем пользователя из базы данных по telegram_id
        from uk_management_bot.database.models.user import User
        user = db_session.query(User).filter(User.telegram_id == callback.from_user.id).first()
        
        if not user:
            await callback.answer("Пользователь не найден в базе данных.", show_alert=True)
            return
        
        query = db_session.query(Request).filter(Request.user_id == user.id)
        if active_status == "active":
            query = query.filter(~Request.status.in_(["Выполнена", "Подтверждена", "Отменена"]))
        elif active_status == "archive":
            query = query.filter(Request.status.in_(["Выполнена", "Подтверждена", "Отменена"]))
        user_requests = query.order_by(Request.created_at.desc()).all()

        # Вычисляем общее количество страниц
        total_requests = len(user_requests)
        requests_per_page = 5
        total_pages = max(1, (total_requests + requests_per_page - 1) // requests_per_page)
        
        if current_page < 1 or current_page > total_pages:
            await callback.answer("Страница не найдена", show_alert=True)
            return
        
        # Получаем заявки для текущей страницы
        start_idx = (current_page - 1) * requests_per_page
        end_idx = start_idx + requests_per_page
        page_requests = user_requests[start_idx:end_idx]
        
        # Формируем текст сообщения с эмодзи статусов и причиной отказа
        message_text = f"📋 Ваши заявки (страница {current_page}/{total_pages}):\n\n"
        def _icon(st: str) -> str:
            mapping = {
                "В работе": "🛠️",
                "Закуп": "💰",
                "Уточнение": "❓",
                "Подтверждена": "⭐",
                "Отменена": "❌",
                "Выполнена": "✅",
                "Новая": "🆕",
            }
            return mapping.get(st, "")
        for i, request in enumerate(page_requests, 1):
            message_text += f"{i}. {_icon(request.status)} {request.category} - {request.status}\n"
            message_text += f"   Адрес: {request.address}\n"
            message_text += f"   Создана: {request.created_at.strftime('%d.%m.%Y')}\n"
            if request.status == "Отменена" and request.notes:
                message_text += f"   Причина отказа: {request.notes}\n"
            message_text += "\n"
        
        # Создаем комбинированную клавиатуру: фильтр + кнопки ответа (по каждой) + пагинация
        from uk_management_bot.keyboards.requests import get_pagination_keyboard
        from uk_management_bot.keyboards.requests import get_status_filter_inline_keyboard
        filter_kb = get_status_filter_inline_keyboard(active_status if active_status != "all" else None)
        rows = list(filter_kb.inline_keyboard)
        for r in page_requests:
            if r.status == "Уточнение":
                rows.append([InlineKeyboardButton(text=f"💬 Ответить по #{r.id}", callback_data=f"replyclarify_{r.id}")])
        pagination_kb = get_pagination_keyboard(current_page, total_pages, request_id=None, show_reply_clarify=False)
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
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data.startswith("view_"))
async def handle_view_request(callback: CallbackQuery, state: FSMContext):
    """Обработка просмотра деталей заявки"""
    try:
        logger.info(f"Обработка просмотра заявки для пользователя {callback.from_user.id}")
        
        request_id = int(callback.data.replace("view_", ""))
        
        # Получаем заявку из базы данных
        db_session = next(get_db())
        request = db_session.query(Request).filter(Request.id == request_id).first()
        
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        # Проверяем права доступа
        from uk_management_bot.database.models.user import User
        user = db_session.query(User).filter(User.telegram_id == callback.from_user.id).first()
        
        if not user or request.user_id != user.id:
            await callback.answer("Нет прав для просмотра этой заявки", show_alert=True)
            return
        
        # Формируем детальную информацию о заявке
        message_text = f"📋 Заявка #{request.id}\n\n"
        message_text += f"Категория: {request.category}\n"
        message_text += f"Статус: {request.status}\n"
        message_text += f"Адрес: {request.address}\n"
        message_text += f"Описание: {request.description}\n"
        message_text += f"Срочность: {request.urgency}\n"
        if request.apartment:
            message_text += f"Квартира: {request.apartment}\n"
        message_text += f"Создана: {request.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        if request.updated_at:
            message_text += f"Обновлена: {request.updated_at.strftime('%d.%m.%Y %H:%M')}\n"
        
        # Создаем клавиатуру действий + кнопка Назад к списку
        from uk_management_bot.keyboards.requests import get_request_actions_keyboard
        actions_kb = get_request_actions_keyboard(request.id)
        rows = list(actions_kb.inline_keyboard)
        # Сохраняем в callback_data информацию: back_list_{page}
        data = await state.get_data()
        current_page = int(data.get("my_requests_page", 1))
        rows.append([InlineKeyboardButton(text="🔙 Назад к списку", callback_data=f"back_list_{current_page}")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

        await callback.message.edit_text(message_text, reply_markup=keyboard)
        
        logger.info(f"Показаны детали заявки {request.id} для пользователя {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки просмотра заявки: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("back_list_"))
async def handle_back_to_list(callback: CallbackQuery, state: FSMContext):
    """Возврат из деталей заявки к списку с восстановлением страницы и фильтра"""
    try:
        # Восстанавливаем страницу из callback_data
        page = int(callback.data.replace("back_list_", ""))
        await state.update_data(my_requests_page=page)
        # Прорисовываем список
        # Нельзя модифицировать frozen from_user у Message в Aiogram 3 — перерисуем через отправку нового сообщения
        await show_my_requests(Message.model_construct(from_user=callback.from_user, chat=callback.message.chat), state)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка возврата к списку: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data.startswith("edit_") & ~F.data.startswith("edit_employee_"))
async def handle_edit_request(callback: CallbackQuery, state: FSMContext):
    """Обработка редактирования заявки"""
    try:
        logger.info(f"Обработка редактирования заявки для пользователя {callback.from_user.id}")
        
        request_id = int(callback.data.replace("edit_", ""))
        
        # Получаем заявку из базы данных
        db_session = next(get_db())
        request = db_session.query(Request).filter(Request.id == request_id).first()
        
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        # Проверяем права доступа
        if request.user_id != callback.from_user.id:
            await callback.answer("Нет прав для редактирования этой заявки", show_alert=True)
            return
        
        # Сохраняем ID заявки в FSM для редактирования
        await state.update_data(editing_request_id=request_id)
        await state.set_state(RequestStates.category)
        
        await callback.message.edit_text(
            f"Редактирование заявки #{request_id}\n\nВыберите новую категорию:",
            reply_markup=get_categories_keyboard()
        )
        
        logger.info(f"Начато редактирование заявки {request_id} пользователем {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки редактирования заявки: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data.startswith("delete_"))
async def handle_delete_request(callback: CallbackQuery, state: FSMContext):
    """Обработка удаления заявки"""
    try:
        logger.info(f"Обработка удаления заявки для пользователя {callback.from_user.id}")
        
        request_id = int(callback.data.replace("delete_", ""))
        
        # Получаем заявку из базы данных
        db_session = next(get_db())
        request = db_session.query(Request).filter(Request.id == request_id).first()
        
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        # Проверяем права доступа
        if request.user_id != callback.from_user.id:
            await callback.answer("Нет прав для удаления этой заявки", show_alert=True)
            return
        
        # Удаляем заявку
        db_session.delete(request)
        db_session.commit()
        
        await callback.message.edit_text(
            "🗑️ Заявка удалена"
        )
        await callback.message.answer(
            "Возврат в главное меню.",
            reply_markup=get_user_contextual_keyboard(callback.from_user.id)
        )
        
        logger.info(f"Заявка {request_id} удалена пользователем {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки удаления заявки: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data.startswith("accept_"))
async def handle_accept_request(callback: CallbackQuery, state: FSMContext):
    """Обработка принятия заявки"""
    try:
        logger.info(f"Обработка принятия заявки для пользователя {callback.from_user.id}")
        # Проверяем, что действие выполняет менеджер
        db_session = next(get_db())
        auth = AuthService(db_session)
        if not await auth.is_user_manager(callback.from_user.id):
            await callback.answer("Доступно только менеджеру", show_alert=True)
            return
        request_id = int(callback.data.replace("accept_", ""))
        service = RequestService(db_session)
        result = service.update_status_by_actor(
            request_id=request_id,
            new_status="В работе",
            actor_telegram_id=callback.from_user.id,
        )

        if not result.get("success"):
            await callback.answer(result.get("message", "Ошибка"), show_alert=True)
            return

        await callback.message.edit_text(
            f"✅ Заявка #{request_id} принята в работу"
        )
        await callback.message.answer(
            "Возврат в главное меню.",
            reply_markup=get_user_contextual_keyboard(callback.from_user.id)
        )
        logger.info(f"Заявка {request_id} принята пользователем {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки принятия заявки: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data.startswith("complete_"))
async def handle_complete_request(callback: CallbackQuery, state: FSMContext):
    """Обработка завершения заявки"""
    try:
        logger.info(f"Обработка завершения заявки для пользователя {callback.from_user.id}")
        # Разрешаем только исполнителю
        db_session = next(get_db())
        auth = AuthService(db_session)
        if not await auth.is_user_executor(callback.from_user.id):
            await callback.answer("Доступно только исполнителю", show_alert=True)
            return
        # Ранняя проверка смены из middleware (если подключено на роутер)
        try:
            shift_ctx = state and (await state.get_data()).get("__shift_ctx__")  # резерв, если сохраняли в FSM
        except Exception:
            shift_ctx = None
        # Предпочтительно берем из data контекста aiogram (если middleware установил)
        # Aiogram 3 передает data в handler, но в нашей сигнатуре его нет. Поэтому используем сервисную проверку ниже как основной барьер.
        # Для ранней UX-подсказки перед сервисной проверкой повторно проверим смену быстрим способом:
        from uk_management_bot.services.shift_service import ShiftService
        quick_service = ShiftService(db_session)
        if not quick_service.is_user_in_active_shift(callback.from_user.id):
            await callback.answer(ERROR_MESSAGES.get("not_in_shift", "Вы не в смене"), show_alert=True)
            # Дополнительное единичное уведомление пользователю (best-effort)
            try:
                from aiogram import Bot
                bot: Bot = callback.message.bot
                await async_notify_action_denied(bot, db_session, callback.from_user.id, "not_in_shift")
            except Exception:
                pass
            return
        request_id = int(callback.data.replace("complete_", ""))
        service = RequestService(db_session)
        result = service.update_status_by_actor(
            request_id=request_id,
            new_status="Выполнена",
            actor_telegram_id=callback.from_user.id,
        )

        if not result.get("success"):
            await callback.answer(result.get("message", "Ошибка"), show_alert=True)
            return

        await callback.message.edit_text(
            f"✅ Заявка #{request_id} отмечена как выполненная"
        )
        await callback.message.answer(
            "Возврат в главное меню.",
            reply_markup=get_user_contextual_keyboard(callback.from_user.id)
        )
        logger.info(f"Заявка {request_id} завершена пользователем {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки завершения заявки: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("clarify_"))
async def handle_clarify_request(callback: CallbackQuery, state: FSMContext):
    """Обработка перевода заявки в статус 'Уточнение'"""
    try:
        # Только менеджер
        request_id = int(callback.data.replace("clarify_", ""))
        db_session = next(get_db())
        auth = AuthService(db_session)
        if not await auth.is_user_manager(callback.from_user.id):
            await callback.answer("Доступно только менеджеру", show_alert=True)
            return
        service = RequestService(db_session)
        result = service.update_status_by_actor(
            request_id=request_id,
            new_status="Уточнение",
            actor_telegram_id=callback.from_user.id,
        )
        if not result.get("success"):
            await callback.answer(result.get("message", "Ошибка"), show_alert=True)
            return
        await callback.message.edit_text(
            f"❓ Заявка #{request_id} переведена в статус 'Уточнение'",
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка обработки перевода в 'Уточнение': {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("purchase_"))
async def handle_purchase_request(callback: CallbackQuery, state: FSMContext):
    """Обработка перевода заявки в статус 'Закуп'"""
    try:
        # Только менеджер
        request_id = int(callback.data.replace("purchase_", ""))
        db_session = next(get_db())
        auth = AuthService(db_session)
        if not await auth.is_user_manager(callback.from_user.id):
            await callback.answer("Доступно только менеджеру", show_alert=True)
            return
        service = RequestService(db_session)
        result = service.update_status_by_actor(
            request_id=request_id,
            new_status="Закуп",
            actor_telegram_id=callback.from_user.id,
        )
        if not result.get("success"):
            await callback.answer(result.get("message", "Ошибка"), show_alert=True)
            return
        await callback.message.edit_text(
            f"💰 Заявка #{request_id} переведена в статус 'Закуп'",
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка обработки перевода в 'Закуп': {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("cancel_") & ~F.data.startswith("cancel_document_selection_"))
async def handle_cancel_request(callback: CallbackQuery, state: FSMContext):
    """Обработка отмены заявки"""
    try:
        # Менеджер или владелец (в RequestService также есть проверка)
        request_id = int(callback.data.replace("cancel_", ""))
        db_session = next(get_db())
        auth = AuthService(db_session)
        is_manager = await auth.is_user_manager(callback.from_user.id)
        service = RequestService(db_session)
        result = service.update_status_by_actor(
            request_id=request_id,
            new_status="Отменена",
            actor_telegram_id=callback.from_user.id,
        )
        if not result.get("success"):
            await callback.answer(result.get("message", "Ошибка"), show_alert=True)
            return
        await callback.message.edit_text(
            f"❌ Заявка #{request_id} отменена",
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка обработки отмены заявки: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("deny_"))
async def handle_executor_propose_deny(callback: CallbackQuery, state: FSMContext):
    """Исполнитель предлагает отказ (эскалируется менеджеру). Добавляем запись в notes без смены статуса."""
    try:
        request_id = int(callback.data.replace("deny_", ""))
        db_session = next(get_db())
        auth = AuthService(db_session)
        # Только исполнитель
        if not await auth.is_user_executor(callback.from_user.id):
            await callback.answer("Доступно только исполнителю", show_alert=True)
            return
        service = RequestService(db_session)
        req = service.get_request_by_id(request_id)
        if not req:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        existing = (req.notes or "").strip()
        new_notes = (existing + "\n" if existing else "") + "[Исполнитель] Предложение отказа: требуется подтверждение менеджера"
        req.notes = new_notes
        db_session.commit()
        await callback.answer("Предложение отказа отправлено менеджеру", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка предложения отказа: {e}")
        await callback.answer("Ошибка", show_alert=True)


@router.callback_query(F.data.startswith("approve_") & ~F.data.startswith("approve_employee_"))
async def handle_approve_request(callback: CallbackQuery, state: FSMContext):
    """Подтверждение выполненной заявки заявителем -> 'Подтверждена'"""
    try:
        request_id = int(callback.data.replace("approve_", ""))
        db_session = next(get_db())
        service = RequestService(db_session)
        result = service.update_status_by_actor(
            request_id=request_id,
            new_status="Подтверждена",
            actor_telegram_id=callback.from_user.id,
        )
        if not result.get("success"):
            await callback.answer(result.get("message", "Ошибка"), show_alert=True)
            return
        await callback.message.edit_text(
            f"✅ Заявка #{request_id} подтверждена",
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка обработки подтверждения заявки: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


# ============================
# Мои заявки (список + пагинация)
# ============================

@router.message(F.text == "📋 Мои заявки")
async def show_my_requests(message: Message, state: FSMContext):
    """Показать список заявок пользователя (страница 1)"""
    try:
        telegram_id = message.from_user.id
        # Читаем активный фильтр и страницу из FSM
        data = await state.get_data()
        active_status = data.get("my_requests_status")
        current_page = int(data.get("my_requests_page", 1))
        db_session = next(get_db())
        
        # Получаем пользователя из базы данных по telegram_id
        from uk_management_bot.database.models.user import User
        user = db_session.query(User).filter(User.telegram_id == telegram_id).first()
        
        if not user:
            await message.answer("Пользователь не найден в базе данных.")
            return
        
        # Получаем заявки пользователя с учетом фильтров
        query = db_session.query(Request).filter(Request.user_id == user.id)
        # Фильтр статуса: только "active" или "archive"
        if active_status == "active":
            # Активные: все, кроме финальных
            query = query.filter(~Request.status.in_(["Выполнена", "Подтверждена", "Отменена"]))
        elif active_status == "archive":
            # Архив: финальные статусы
            query = query.filter(Request.status.in_(["Выполнена", "Подтверждена", "Отменена"]))
        # Прочие фильтры (категория/период/исполнитель) отключены
        user_requests = query.order_by(Request.created_at.desc()).all()

        total_requests = len(user_requests)
        requests_per_page = 5
        total_pages = max(1, (total_requests + requests_per_page - 1) // requests_per_page)
        # Корректируем текущую страницу, если вышла за диапазон
        if current_page > total_pages:
            current_page = total_pages

        start_idx = (current_page - 1) * requests_per_page
        end_idx = start_idx + requests_per_page
        page_requests = user_requests[start_idx:end_idx]

        message_text = f"📋 Ваши заявки (страница {current_page}/{total_pages}):\n\n"
        if not page_requests:
            message_text += "Пока нет заявок. Нажмите 'Создать заявку' в главном меню."
        else:
            def _icon(st: str) -> str:
                mapping = {
                    "В работе": "🛠️",
                    "Закуп": "💰",
                    "Уточнение": "❓",
                    "Подтверждена": "⭐",
                    "Отменена": "❌",
                    "Выполнена": "✅",
                    "Новая": "🆕",
                }
                return mapping.get(st, "")
            for i, request in enumerate(page_requests, 1):
                # Ограничиваем длину адреса до 60 символов
                address = request.address
                if len(address) > 60:
                    address = address[:60] + "…"
                message_text += f"{i}. {_icon(request.status)} {request.category} - {request.status}\n"
                message_text += f"   Адрес: {address}\n"
                message_text += f"   Создана: {request.created_at.strftime('%d.%m.%Y')}\n\n"

        from uk_management_bot.keyboards.requests import get_pagination_keyboard
        # Только фильтр статуса (Активные/Архив) и пагинация + кнопки ответа по заявкам в уточнении
        filter_status_kb = get_status_filter_inline_keyboard(active_status)
        pagination_kb = get_pagination_keyboard(current_page, total_pages)
        rows = list(filter_status_kb.inline_keyboard)
        for r in page_requests:
            if r.status == "Уточнение":
                rows.append([InlineKeyboardButton(text=f"💬 Ответить по #{r.id}", callback_data=f"replyclarify_{r.id}")])
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
        await message.answer("Произошла ошибка при загрузке списка заявок.")


@router.message(Command("my_requests"))
async def cmd_my_requests(message: Message, state: FSMContext):
    """Команда /my_requests показывает страницу 1 списка заявок"""
    # По умолчанию показываем активные
    await state.update_data(my_requests_status="active")
    await show_my_requests(message, state)


@router.callback_query(F.data.startswith("replyclarify_"))
async def handle_reply_clarify_start(callback: CallbackQuery, state: FSMContext):
    """Пользователь хочет ответить на запрос уточнения. Просим ввести текст."""
    try:
        request_id = int(callback.data.replace("replyclarify_", ""))
        # Показать текущий диалог из notes перед вводом
        db_session = next(get_db())
        req = db_session.query(Request).filter(Request.id == request_id).first()
        await state.update_data(reply_request_id=request_id)
        await state.set_state(RequestStates.waiting_clarify_reply)
        # Получаем пользователя из базы данных по telegram_id
        from uk_management_bot.database.models.user import User
        user = db_session.query(User).filter(User.telegram_id == callback.from_user.id).first()
        
        if req and user and req.user_id == user.id:
            notes_text = (req.notes or "").strip()
            if notes_text:
                await callback.message.answer(f"Текущий диалог:\n{notes_text}")
            else:
                await callback.message.answer("Диалог пока пуст.")
        await callback.message.answer(
            "Введите ответ для уточнения (текст будет добавлен в примечания к заявке):",
            reply_markup=get_cancel_keyboard(),
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка старта ответа на уточнение: {e}")
        await callback.answer("Ошибка")


@router.message(RequestStates.waiting_clarify_reply)
async def handle_reply_clarify_text(message: Message, state: FSMContext):
    """Сохраняем ответ пользователя в notes без смены статуса."""
    try:
        data = await state.get_data()
        request_id = int(data.get("reply_request_id"))
        db_session = next(get_db())
        service = RequestService(db_session)
        req = service.get_request_by_id(request_id)
        # Получаем пользователя из базы данных по telegram_id
        from uk_management_bot.database.models.user import User
        user = db_session.query(User).filter(User.telegram_id == message.from_user.id).first()
        
        if not req or not user or req.user_id != user.id:
            await message.answer("Заявка не найдена или недоступна.")
            await state.clear()
            await message.answer("Возврат в меню", reply_markup=get_user_contextual_keyboard(message.from_user.id))
            return
        existing = (req.notes or "").strip()
        to_add = message.text.strip()
        # Добавляем с ролью пользователя
        new_notes = (existing + "\n" if existing else "") + f"[Пользователь] Уточнение: {to_add}"
        req.notes = new_notes
        db_session.commit()
        await message.answer("Ответ сохранён.", reply_markup=get_main_keyboard())
        await state.clear()
    except Exception as e:
        logger.error(f"Ошибка сохранения ответа на уточнение: {e}")
        await state.clear()
        await message.answer("Не удалось сохранить ответ. Попробуйте позже.", reply_markup=get_main_keyboard())


@router.callback_query(F.data.startswith("status_"))
async def handle_status_filter(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора фильтра статуса для списка заявок"""
    try:
        # Совместимость с тестами: поддержать текстовые статусы, но маппить на упрощённые "active"/"archive"
        raw = callback.data.replace("status_", "")
        if raw in ("active", "archive"):
            choice = raw
        elif raw == "В работе":
            choice = "В работе"
        else:
            choice = raw
        # Запоминаем фильтр и сбрасываем страницу
        await state.update_data(my_requests_status=choice, my_requests_page=1)

        # Собираем список заявок и клавиатуру, затем редактируем сообщение
        data = await state.get_data()
        db_session = next(get_db())
        
        # Получаем пользователя из базы данных по telegram_id
        from uk_management_bot.database.models.user import User
        user = db_session.query(User).filter(User.telegram_id == callback.from_user.id).first()
        
        if not user:
            await callback.answer("Пользователь не найден в базе данных.", show_alert=True)
            return
        
        query = db_session.query(Request).filter(Request.user_id == user.id)
        if choice in ("active", "В работе"):
            # Активные: все, кроме финальных
            query = query.filter(~Request.status.in_(["Выполнена", "Подтверждена", "Отменена"]))
        else:
            query = query.filter(Request.status.in_(["Выполнена", "Подтверждена", "Отменена"]))

        user_requests = query.order_by(Request.created_at.desc()).all()
        current_page = 1
        requests_per_page = 5
        total_pages = max(1, (len(user_requests) + requests_per_page - 1) // requests_per_page)
        page_requests = user_requests[:requests_per_page]

        message_text = f"📋 Ваши заявки (страница {current_page}/{total_pages}):\n\n"
        if not page_requests:
            message_text += "Пока нет заявок. Нажмите 'Создать заявку' в главном меню."
        else:
            def _icon(st: str) -> str:
                mapping = {
                    "В работе": "🛠️",
                    "Закуп": "💰",
                    "Уточнение": "❓",
                    "Подтверждена": "⭐",
                    "Отменена": "❌",
                    "Выполнена": "✅",
                    "Новая": "🆕",
                }
                return mapping.get(st, "")
            for i, request in enumerate(page_requests, 1):
                address = request.address
                if len(address) > 60:
                    address = address[:60] + "…"
                message_text += f"{i}. {_icon(request.status)} {request.category} - {request.status}\n"
                message_text += f"   Адрес: {address}\n"
                message_text += f"   Создана: {request.created_at.strftime('%d.%m.%Y')}\n"
                if choice == "archive" and request.status == "Отменена" and request.notes:
                    message_text += f"   Причина отказа: {request.notes}\n"
                message_text += "\n"

        from uk_management_bot.keyboards.requests import get_pagination_keyboard
        filter_status_kb = get_status_filter_inline_keyboard(choice)
        show_reply = any(r.status == "Уточнение" for r in page_requests)
        pagination_kb = get_pagination_keyboard(current_page, total_pages, show_reply_clarify=show_reply)
        combined_rows = filter_status_kb.inline_keyboard + pagination_kb.inline_keyboard
        combined = type(pagination_kb)(inline_keyboard=combined_rows)

        try:
            await callback.message.edit_text(message_text, reply_markup=combined)
        except TelegramBadRequest:
            # Повторное нажатие по тому же фильтру/такому же тексту — просто ответим без алерта
            pass
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка применения фильтра статуса: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)
@router.callback_query(F.data.startswith("categoryfilter_"))
async def handle_category_filter(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора фильтра категории"""
    try:
        choice = callback.data.replace("categoryfilter_", "")
        await state.update_data(my_requests_category=choice, my_requests_page=1)
        fake_message = callback.message
        fake_message.from_user = callback.from_user
        await show_my_requests(fake_message, state)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка применения фильтра категории: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "filters_reset")
async def handle_filters_reset(callback: CallbackQuery, state: FSMContext):
    """Сброс всех фильтров списка заявок"""
    try:
        await state.update_data(
            my_requests_status="all",
            my_requests_category="all",
            my_requests_period="all",
            my_requests_executor="all",
            my_requests_page=1,
        )
        await show_my_requests(Message.model_construct(from_user=callback.from_user, chat=callback.message.chat), state)
        await callback.answer("Фильтры сброшены")
    except Exception as e:
        logger.error(f"Ошибка сброса фильтров: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("period_"))
async def handle_period_filter(callback: CallbackQuery, state: FSMContext):
    try:
        choice = callback.data.replace("period_", "")
        await state.update_data(my_requests_period=choice, my_requests_page=1)
        await show_my_requests(Message.model_construct(from_user=callback.from_user, chat=callback.message.chat), state)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка применения фильтра периода: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("executorfilter_"))
async def handle_executor_filter(callback: CallbackQuery, state: FSMContext):
    try:
        choice = callback.data.replace("executorfilter_", "")
        await state.update_data(my_requests_executor=choice, my_requests_page=1)
        await show_my_requests(Message.model_construct(from_user=callback.from_user, chat=callback.message.chat), state)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка применения фильтра исполнителя: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)
