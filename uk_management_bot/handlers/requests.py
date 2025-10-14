from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.orm import Session
from sqlalchemy import or_
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
    get_yard_selection_keyboard,
    get_building_selection_keyboard,
    get_apartment_selection_keyboard,
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

async def auto_assign_request_by_category(request_number: str, db_session: Session, manager_telegram_id: int):
    """
    Автоматически назначает заявку исполнителям по категории/специализации
    
    Args:
        request_number: Номер заявки для назначения
        db_session: Сессия базы данных
        manager_telegram_id: Telegram ID менеджера, который назначает заявку
    """
    try:
        from uk_management_bot.database.models.request_assignment import RequestAssignment
        from uk_management_bot.database.models.user import User
        from uk_management_bot.database.models.request import Request
        import json
        
        # Получаем заявку
        request = db_session.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            logger.error(f"Заявка {request_number} не найдена для назначения")
            return
        
        # Получаем менеджера
        manager = db_session.query(User).filter(User.telegram_id == manager_telegram_id).first()
        if not manager:
            logger.error(f"Менеджер {manager_telegram_id} не найден")
            return
        
        # Маппинг категорий заявок на специализации
        category_to_specialization = {
            "Сантехника": "plumber",
            "Электрика": "electrician", 
            "Благоустройство": "landscaping",
            "Уборка": "cleaning",
            "Безопасность": "security",
            "Ремонт": "repair",
            "Установка": "installation",
            "Обслуживание": "maintenance",
            "HVAC": "hvac"
        }
        
        # Определяем специализацию по категории заявки
        specialization = category_to_specialization.get(request.category)
        if not specialization:
            logger.warning(f"Неизвестная категория заявки: {request.category}")
            return
        
        # Находим исполнителей с нужной специализацией
        executors = db_session.query(User).filter(
            User.active_role == "executor",
            User.status == "approved"
        ).all()
        
        matching_executors = []
        for executor in executors:
            if executor.specialization:
                try:
                    # Парсим специализации исполнителя
                    if isinstance(executor.specialization, str):
                        executor_specializations = json.loads(executor.specialization)
                    else:
                        executor_specializations = executor.specialization
                    
                    # Проверяем, есть ли нужная специализация
                    if specialization in executor_specializations:
                        matching_executors.append(executor)
                except (json.JSONDecodeError, TypeError):
                    # Если специализация - просто строка
                    if executor.specialization == specialization:
                        matching_executors.append(executor)
        
        if not matching_executors:
            logger.warning(f"Не найдено исполнителей для специализации {specialization}")
            return
        
        # Проверяем, есть ли уже назначение для этой заявки
        existing_assignment = db_session.query(RequestAssignment).filter(
            RequestAssignment.request_number == request_number,
            RequestAssignment.status == "active"
        ).first()
        
        if existing_assignment:
            logger.info(f"Заявка {request_number} уже назначена, пропускаем")
            return
        
        # Дополнительная проверка на групповые назначения для той же специализации
        existing_group_assignment = db_session.query(RequestAssignment).filter(
            RequestAssignment.request_number == request_number,
            RequestAssignment.assignment_type == "group",
            RequestAssignment.group_specialization == specialization,
            RequestAssignment.status == "active"
        ).first()
        
        if existing_group_assignment:
            logger.info(f"Заявка {request_number} уже назначена группе {specialization}, пропускаем")
            return
        
        # Создаем групповое назначение
        assignment = RequestAssignment(
            request_number=request_number,
            assignment_type="group",
            group_specialization=specialization,
            status="active",
            created_by=manager.id
        )
        
        db_session.add(assignment)
        
        # Обновляем поля заявки
        request.assignment_type = "group"
        request.assigned_group = specialization
        request.assigned_at = datetime.now()
        request.assigned_by = manager.id
        
        logger.info(f"Заявка {request_number} автоматически назначена группе {specialization} ({len(matching_executors)} исполнителей)")
        
    except Exception as e:
        logger.error(f"Ошибка автоматического назначения заявки {request_number}: {e}")


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

class RequestStates(StatesGroup):
    """Состояния FSM для создания заявок"""
    category = State()           # Выбор категории
    address_yard = State()       # Выбор двора (шаг 1)
    address_building = State()   # Выбор здания (шаг 2)
    address_apartment = State()  # Выбор квартиры (шаг 3)
    address = State()            # Устаревший: прямой выбор адреса
    address_manual = State()     # Ручной ввод адреса
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
    
    # Проверяем наличие телефона у пользователя
    from uk_management_bot.database.session import get_db
    from uk_management_bot.database.models.user import User
    from uk_management_bot.utils.helpers import get_text
    
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if user and not user.phone:
            lang = getattr(message.from_user, "language_code", None) or "ru"
            await message.answer(get_text("requests.phone_required", language=lang))
            return
    except Exception as e:
        logger.error(f"Ошибка проверки телефона пользователя {message.from_user.id}: {e}")
    finally:
        db.close()
    
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
    
    # Проверяем наличие телефона у пользователя
    from uk_management_bot.database.session import get_db
    from uk_management_bot.database.models.user import User
    from uk_management_bot.utils.helpers import get_text
    
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if user and not user.phone:
            lang = getattr(message.from_user, "language_code", None) or "ru"
            await message.answer(get_text("requests.phone_required", language=lang))
            return
    except Exception as e:
        logger.error(f"Ошибка проверки телефона пользователя {message.from_user.id}: {e}")
    finally:
        db.close()
    
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

    # Показываем единую клавиатуру с квартирами, домами и дворами
    try:
        logger.info(f"[CATEGORY_SELECTION] Создание клавиатуры выбора адреса для пользователя {user_id}")
        keyboard = get_address_selection_keyboard(user_id)
        logger.info(f"[CATEGORY_SELECTION] Клавиатура адресов создана, отправка пользователю {user_id}")

        await message.answer(
            "📍 Выберите адрес:\n"
            "• 🏠 Квартира - для проблем в квартире\n"
            "• 🏢 Дом - для общедомовых проблем\n"
            "• 🏘️ Двор - для проблем во дворе",
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
    """
    Обработка выбора адреса

    ОБНОВЛЕНО: Поддержка выбора квартир из справочника адресов
    """
    user_id = message.from_user.id
    selected_text = message.text

    # Улучшенное логирование с контекстом
    logger.info(f"[ADDRESS_SELECTION] Пользователь {user_id}: '{selected_text}'")
    logger.info(f"[ADDRESS_SELECTION] Время: {datetime.now()}")
    logger.info(f"[ADDRESS_SELECTION] Состояние FSM: {await state.get_state()}")

    try:
        from uk_management_bot.services.address_service import AddressService

        # НОВАЯ ЛОГИКА: Проверка типа выбранного адреса

        # 1. КВАРТИРА (🏠) - для проблем в квартире
        if selected_text.startswith("🏠 "):
            address_text = selected_text[2:].strip()
            db = next(get_db())
            try:
                apartments = await AddressService.get_user_approved_apartments(db, user_id)

                selected_apartment = None
                for apartment in apartments:
                    formatted_address = AddressService.format_apartment_address(apartment)
                    if formatted_address == address_text or formatted_address.startswith(address_text.replace("...", "")):
                        selected_apartment = apartment
                        break

                if selected_apartment:
                    full_address = AddressService.format_apartment_address(selected_apartment)
                    await state.update_data(
                        address=full_address,
                        apartment_id=selected_apartment.id,
                        building_id=selected_apartment.building_id if selected_apartment.building else None,
                        yard_id=selected_apartment.building.yard_id if selected_apartment.building and selected_apartment.building.yard else None,
                        address_type='apartment'
                    )
                    await state.set_state(RequestStates.description)

                    await message.answer(
                        f"✅ Адрес сохранен: 🏠 {full_address}\n\n"
                        f"Опишите проблему в квартире:",
                        reply_markup=get_cancel_keyboard()
                    )

                    logger.info(f"[ADDRESS_SELECTION] Пользователь {user_id} выбрал квартиру: {full_address}")
                    return
                else:
                    logger.warning(f"[ADDRESS_SELECTION] Квартира не найдена: '{address_text}'")
                    await message.answer(
                        "⚠️ Квартира не найдена. Выберите адрес из предложенных вариантов:",
                        reply_markup=get_address_selection_keyboard(user_id)
                    )
                    return
            finally:
                db.close()

        # 2. ДОМ/ЗДАНИЕ (🏢) - для общедомовых проблем
        elif selected_text.startswith("🏢 "):
            address_text = selected_text[2:].strip()
            db = next(get_db())
            try:
                from uk_management_bot.database.models import Building

                # Находим здание по адресу
                building = db.query(Building).filter(Building.address == address_text).first()

                if building:
                    await state.update_data(
                        address=f"Дом: {building.address}",
                        apartment_id=None,
                        building_id=building.id,
                        yard_id=building.yard_id if building.yard else None,
                        address_type='building'
                    )
                    await state.set_state(RequestStates.description)

                    await message.answer(
                        f"✅ Адрес сохранен: 🏢 {building.address}\n\n"
                        f"Опишите общедомовую проблему:",
                        reply_markup=get_cancel_keyboard()
                    )

                    logger.info(f"[ADDRESS_SELECTION] Пользователь {user_id} выбрал дом: {building.address}")
                    return
                else:
                    logger.warning(f"[ADDRESS_SELECTION] Здание не найдено: '{address_text}'")
                    await message.answer(
                        "⚠️ Здание не найдено. Выберите адрес из предложенных вариантов:",
                        reply_markup=get_address_selection_keyboard(user_id)
                    )
                    return
            finally:
                db.close()

        # 3. ДВОР (🏘️) - для проблем во дворе
        elif selected_text.startswith("🏘️ "):
            address_text = selected_text[2:].strip()
            db = next(get_db())
            try:
                from uk_management_bot.database.models import Yard

                # Находим двор по названию
                yard = db.query(Yard).filter(Yard.name == address_text).first()

                if yard:
                    await state.update_data(
                        address=f"Двор: {yard.name}",
                        apartment_id=None,
                        building_id=None,
                        yard_id=yard.id,
                        address_type='yard'
                    )
                    await state.set_state(RequestStates.description)

                    await message.answer(
                        f"✅ Адрес сохранен: 🏘️ {yard.name}\n\n"
                        f"Опишите проблему во дворе:",
                        reply_markup=get_cancel_keyboard()
                    )

                    logger.info(f"[ADDRESS_SELECTION] Пользователь {user_id} выбрал двор: {yard.name}")
                    return
                else:
                    logger.warning(f"[ADDRESS_SELECTION] Двор не найден: '{address_text}'")
                    await message.answer(
                        "⚠️ Двор не найден. Выберите адрес из предложенных вариантов:",
                        reply_markup=get_address_selection_keyboard(user_id)
                    )
                    return
            finally:
                db.close()

        # СТАРАЯ ЛОГИКА: Обработка legacy адресов и команд
        # Парсим выбор пользователя
        result = await parse_selected_address(selected_text)
        logger.info(f"[ADDRESS_SELECTION] Результат парсинга: {result}")

        if result['type'] == 'predefined':
            # Используем выбранный адрес; квартира считается указанной в адресе
            # NOTE: Legacy path - для старых адресов без apartment_id
            await state.update_data(address=result['address'], apartment_id=None)
            await state.set_state(RequestStates.description)

            # Контекстное сообщение в зависимости от типа адреса
            context_message = get_contextual_help(result['address_type'])
            await message.answer(context_message, reply_markup=get_cancel_keyboard())

            logger.info(f"[ADDRESS_SELECTION] Пользователь {user_id} выбрал готовый адрес: {result['address']}, тип: {result['address_type']}")

        elif result['type'] == 'cancel':
            # Отменить создание заявки
            await cancel_request(message, state)
            return

        elif result['type'] == 'unknown':
            # Неизвестный выбор - улучшенная обработка
            logger.warning(f"[ADDRESS_SELECTION] Неизвестный выбор адреса: '{selected_text}' от пользователя {user_id}")
            await message.answer(
                "⚠️ Пожалуйста, выберите адрес из предложенных вариантов"
            )
            # Показываем клавиатуру снова
            try:
                keyboard = get_address_selection_keyboard(user_id)
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
    
    # Сохраняем адрес (без apartment_id для ручного ввода)
    await state.update_data(address=address_text, apartment_id=None)

    # В новой логике квартира вводится прямо в адресе при ручном вводе
    await state.set_state(RequestStates.description)
    await message.answer(
        "✅ Адрес сохранен! Опишите проблему:",
        reply_markup=get_cancel_keyboard()
    )
    logger.info(f"[ADDRESS_MANUAL] Пользователь {user_id} ввел адрес вручную: {address_text}")

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
        success = await save_request(data, message.from_user.id, db, message.bot)
        
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
async def save_request(data: dict, user_id: int, db: Session, bot: Bot = None) -> bool:
    """Сохранение заявки в базу данных"""
    try:
        # Получаем пользователя из базы данных по telegram_id
        from uk_management_bot.database.models.user import User
        user = db.query(User).filter(User.telegram_id == user_id).first()

        if not user:
            logger.error(f"Пользователь с telegram_id {user_id} не найден в базе данных")
            return False

        # Генерируем уникальный номер заявки
        request_number = Request.generate_request_number(db)

        # Загружаем медиа-файлы в Media Service (если есть)
        media_file_ids = data.get('media_files', [])
        if media_file_ids and bot:
            from uk_management_bot.utils.media_helpers import upload_multiple_telegram_files
            try:
                uploaded_files = await upload_multiple_telegram_files(
                    bot=bot,
                    file_ids=media_file_ids,
                    request_number=request_number,
                    uploaded_by=user.id
                )
                logger.info(f"Загружено {len(uploaded_files)} файлов в Media Service для заявки {request_number}")
            except Exception as e:
                logger.error(f"Ошибка загрузки файлов в Media Service: {e}")
                # Продолжаем создание заявки даже если загрузка не удалась

        request = Request(
            request_number=request_number,
            category=data['category'],
            address=data['address'],
            description=data['description'],
            urgency=data['urgency'],
            apartment=data.get('apartment'),  # Legacy field
            apartment_id=data.get('apartment_id'),  # NEW: Link to address directory
            # В модели media_files ожидается JSON (список), поэтому сохраняем список
            # Теперь храним file_ids как backup, основное хранилище - Media Service
            media_files=list(media_file_ids),
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
        keyboard = get_address_selection_keyboard(callback.from_user.id)
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
            success = await save_request(data, callback.from_user.id, db_session, callback.bot)
            
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
                "Принято": "✅",
                "Новая": "🆕",
            }
            return mapping.get(st, "")
        for i, request in enumerate(page_requests, 1):
            message_text += f"{i}. {_icon(request.status)} #{request.request_number} - {request.category} - {request.status}\n"
            message_text += f"   Адрес: {request.address}\n"
            message_text += f"   Создана: {request.created_at.strftime('%d.%m.%Y')}\n"
            if request.status == "Отменена" and request.notes:
                message_text += f"   Причина отказа: {request.notes}\n"
            elif request.status == "Уточнение" and request.notes:
                # Показываем последние сообщения из диалога уточнения
                notes_lines = request.notes.strip().split('\n')
                last_messages = [line for line in notes_lines[-3:] if line.strip()]  # Последние 3 сообщения
                if last_messages:
                    preview = '\n'.join(last_messages)
                    if len(preview) > 100:
                        preview = preview[:97] + '...'
                    message_text += f"   Уточнение: {preview}\n"
            message_text += "\n"
        
        # Создаем комбинированную клавиатуру: фильтр + кнопки ответа (по каждой) + пагинация
        from uk_management_bot.keyboards.requests import get_pagination_keyboard
        from uk_management_bot.keyboards.requests import get_status_filter_inline_keyboard
        filter_kb = get_status_filter_inline_keyboard(active_status if active_status != "all" else None)
        rows = list(filter_kb.inline_keyboard)
        for i, r in enumerate(page_requests, 1):
            if r.status == "Уточнение":
                rows.append([InlineKeyboardButton(text=f"💬 Ответить по #{r.request_number}", callback_data=f"replyclarify_{r.request_number}")])
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
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("view_") and not c.data.startswith("view_comments") and not c.data.startswith("view_report") and not c.data.startswith("view_assignments") and not c.data.startswith("view_schedule") and not c.data.startswith("view_week") and not c.data.startswith("view_completed") and not c.data.startswith("view_completion_media") and not c.data.startswith("view_user"))
async def handle_view_request(callback: CallbackQuery, state: FSMContext):
    """Обработка просмотра деталей заявки"""
    try:
        logger.info(f"Обработка просмотра заявки для пользователя {callback.from_user.id}")

        # Извлекаем номер заявки из callback_data (view_ или view_request_)
        request_number = callback.data.replace("view_request_", "").replace("view_", "")

        # Получаем заявку из базы данных
        db_session = next(get_db())
        request = db_session.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        # Получаем пользователя и проверяем права доступа
        from uk_management_bot.database.models.user import User
        from uk_management_bot.database.models.request_assignment import RequestAssignment
        user = db_session.query(User).filter(User.telegram_id == callback.from_user.id).first()

        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
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
            # Для исполнителей: проверяем назначение
            assignment = db_session.query(RequestAssignment).filter(
                RequestAssignment.request_number == request.request_number,
                RequestAssignment.status == "active"
            ).first()

            if assignment:
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
            # Для заявителей и других ролей: проверяем владение заявкой
            if request.user_id == user.id:
                has_access = True

        if not has_access:
            await callback.answer("Нет прав для просмотра этой заявки", show_alert=True)
            return
        
        # Формируем детальную информацию о заявке
        message_text = f"📋 Заявка #{request.request_number}\n\n"
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

        # Добавляем информацию об исполнителе для заявителей
        if active_role != "executor" and request.executor_id:
            executor = db_session.query(User).filter(User.id == request.executor_id).first()
            if executor:
                executor_name = f"{executor.first_name or ''} {executor.last_name or ''}".strip()
                message_text += f"Исполнитель: {executor_name}\n"

        # Проверяем наличие медиа-файлов
        has_media = bool(request.media_files)
        media_count = 0
        if has_media:
            try:
                import json
                media_files = json.loads(request.media_files) if isinstance(request.media_files, str) else request.media_files
                media_count = len(media_files) if media_files else 0
                if media_count > 0:
                    message_text += f"\n📎 Медиа-файлов: {media_count}\n"
                else:
                    has_media = False
            except (json.JSONDecodeError, TypeError):
                has_media = False

        # Создаем клавиатуру в зависимости от роли
        rows = []

        if active_role == "executor":
            # Для исполнителей: только действия по работе с заявкой
            if request.status == "В работе":
                rows.append([InlineKeyboardButton(text="✅ Выполнена", callback_data=f"executor_complete_{request.request_number}")])
                rows.append([InlineKeyboardButton(text="💰 Нужен закуп", callback_data=f"executor_purchase_{request.request_number}")])
            elif request.status == "Закуп":
                rows.append([InlineKeyboardButton(text="🔄 Вернуть в работу", callback_data=f"executor_work_{request.request_number}")])
            elif request.status == "Уточнение":
                rows.append([InlineKeyboardButton(text="🔄 Вернуть в работу", callback_data=f"executor_work_{request.request_number}")])
            elif request.status in ["Выполнена", "Принято", "Подтверждена"]:
                # Заявка завершена - только просмотр
                pass

            # Кнопка просмотра медиа (если есть)
            if has_media:
                rows.append([InlineKeyboardButton(text="📎 Просмотр медиа", callback_data=f"executor_view_media_{request.request_number}")])
        elif active_role in ["admin", "manager"]:
            # Для менеджеров/админов: полная клавиатура управления
            from uk_management_bot.keyboards.requests import get_request_actions_keyboard
            actions_kb = get_request_actions_keyboard(request.request_number)
            rows = list(actions_kb.inline_keyboard)
        else:
            # Для заявителей: ограниченная клавиатура (только просмотр и ответ на уточнения)
            if request.status == "Уточнение":
                # Если требуется уточнение - кнопка ответа
                rows.append([InlineKeyboardButton(text="💬 Ответить", callback_data=f"replyclarify_{request.request_number}")])
            elif request.status == "Выполнена":
                # Если работа выполнена - кнопка подтверждения
                rows.append([InlineKeyboardButton(text="✅ Подтвердить выполнение", callback_data=f"approve_{request.request_number}")])

            # Кнопка просмотра медиа (если есть)
            if has_media:
                rows.append([InlineKeyboardButton(text="📎 Просмотр медиа", callback_data=f"view_request_media_{request.request_number}")])

        # Добавляем кнопку "Назад к списку"
        data = await state.get_data()
        current_page = int(data.get("my_requests_page", 1))
        rows.append([InlineKeyboardButton(text="🔙 Назад к списку", callback_data=f"back_list_{current_page}")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

        await callback.message.edit_text(message_text, reply_markup=keyboard)
        
        logger.info(f"Показаны детали заявки {request.request_number} для пользователя {callback.from_user.id}")
        
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

        # Удаляем текущее сообщение с деталями
        await callback.message.delete()

        # Получаем данные пользователя
        telegram_id = callback.from_user.id
        data = await state.get_data()
        active_status = data.get("my_requests_status", "active")
        current_page = int(data.get("my_requests_page", 1))

        db_session = next(get_db())
        user = db_session.query(User).filter(User.telegram_id == telegram_id).first()

        if not user:
            await callback.message.answer("Пользователь не найден в базе данных.")
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
                query = query.filter(Request.status.in_(["Выполнена", "Принято", "Подтверждена", "Отменена"]))
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

        if not requests:
            if active_role == "executor":
                message_text = "📋 <b>Назначенные заявки</b>\n\nУ вас пока нет назначенных заявок."
            else:
                if active_status == "active":
                    message_text = "📋 <b>Активные заявки</b>\n\nУ вас пока нет активных заявок."
                elif active_status == "archive":
                    message_text = "📋 <b>Архив заявок</b>\n\nУ вас пока нет заявок в архиве."
                else:
                    message_text = "📋 <b>Все заявки</b>\n\nУ вас пока нет заявок."

            await callback.message.answer(message_text, parse_mode="HTML")
            await callback.answer()
            return

        # Иконка в зависимости от статуса
        def _icon(st: str) -> str:
            mapping = {
                "В работе": "🛠️",
                "Выполнена": "✅",
                "Закуп": "💰",
                "Уточнение": "❓",
                "Принято": "✅",
                "Новая": "🆕",
                "Подтверждена": "⭐",
                "Отменена": "❌",
            }
            return mapping.get(st, "📋")

        # Формируем сообщение
        if active_role == "executor":
            message_text = f"📋 <b>Назначенные заявки</b> (стр. {current_page}/{total_pages})\n\n"
            message_text += "Выберите заявку для просмотра деталей:\n\n"
        else:
            if active_status == "active":
                status_name = "Активные"
            elif active_status == "archive":
                status_name = "Архив"
            else:
                status_name = "Все"
            message_text = f"📋 <b>{status_name} заявки</b> (стр. {current_page}/{total_pages})\n\n"

        # Для заявителей - текстовый список, для исполнителей - кнопки
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()

        if active_role != "executor":
            # Текстовый список для заявителей
            for i, req in enumerate(requests, 1):
                address = req.address
                if len(address) > 60:
                    address = address[:60] + "…"
                message_text += f"{i}. {_icon(req.status)} #{req.request_number} - {req.category} - {req.status}\n"
                message_text += f"   Адрес: {address}\n"
                message_text += f"   Создана: {req.created_at.strftime('%d.%m.%Y')}\n"
                # Дополнительная информация
                if req.status == "Отменена" and req.notes:
                    message_text += f"   Причина отказа: {req.notes[:100]}...\n" if len(req.notes) > 100 else f"   Причина отказа: {req.notes}\n"
                elif req.status == "Уточнение" and req.notes:
                    notes_lines = req.notes.strip().split('\n')
                    last_messages = [line for line in notes_lines[-2:] if line.strip()]
                    if last_messages:
                        preview = '\n'.join(last_messages)
                        if len(preview) > 80:
                            preview = preview[:77] + '...'
                        message_text += f"   Уточнение: {preview}\n"
                message_text += "\n"
        else:
            # Кнопки для исполнителей
            for req in requests:
                button_text = f"{_icon(req.status)} #{req.request_number} - {req.category}"
                builder.button(text=button_text, callback_data=f"view_request_{req.request_number}")

            builder.adjust(1)  # По одной кнопке в ряд

        # Добавляем кнопки пагинации
        pagination_buttons = []
        if current_page > 1:
            pagination_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"requests_page_{current_page - 1}"))
        if current_page < total_pages:
            pagination_buttons.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"requests_page_{current_page + 1}"))

        if pagination_buttons:
            builder.row(*pagination_buttons)

        # Добавляем фильтры только для не-исполнителей
        if active_role != "executor":
            filter_buttons = [
                InlineKeyboardButton(text="📋 Все" if active_status == "all" else "⚪️ Все", callback_data="requests_filter_all"),
                InlineKeyboardButton(text="🟢 Активные" if active_status == "active" else "⚪️ Активные", callback_data="requests_filter_active"),
                InlineKeyboardButton(text="📦 Архив" if active_status == "archive" else "⚪️ Архив", callback_data="requests_filter_archive")
            ]
            builder.row(*filter_buttons)

            # Добавляем кнопки для заявок, требующих действий заявителя
            for req in requests:
                if req.status == "Уточнение":
                    builder.row(InlineKeyboardButton(
                        text=f"💬 Ответить на #{req.request_number}",
                        callback_data=f"replyclarify_{req.request_number}"
                    ))
                elif req.status == "Выполнена":
                    builder.row(InlineKeyboardButton(
                        text=f"✅ Подтвердить #{req.request_number}",
                        callback_data=f"approve_{req.request_number}"
                    ))

        await callback.message.answer(
            message_text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка возврата к списку: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data.startswith("edit_") & ~F.data.startswith("edit_employee_") & ~F.data.startswith("edit_profile") & ~F.data.startswith("edit_first_name") & ~F.data.startswith("edit_last_name"))
async def handle_edit_request(callback: CallbackQuery, state: FSMContext):
    """Обработка редактирования заявки"""
    try:
        logger.info(f"Обработка редактирования заявки для пользователя {callback.from_user.id}")
        
        request_number = callback.data.replace("edit_", "")
        
        # Получаем заявку из базы данных
        db_session = next(get_db())
        request = db_session.query(Request).filter(Request.request_number == request_number).first()
        
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        # Проверяем права доступа (сравниваем с telegram_id пользователя)
        from uk_management_bot.database.models.user import User
        user = db_session.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not user or request.user_id != user.id:
            await callback.answer("Нет прав для редактирования этой заявки", show_alert=True)
            return
        
        # Сохраняем номер заявки в FSM для редактирования
        await state.update_data(editing_request_number=request_number)
        await state.set_state(RequestStates.category)
        
        await callback.message.edit_text(
            f"Редактирование заявки #{request_number}\n\nВыберите новую категорию:",
            reply_markup=get_categories_keyboard()
        )
        
        logger.info(f"Начато редактирование заявки {request_number} пользователем {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки редактирования заявки: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(
    F.data.startswith("delete_") &
    ~F.data.startswith("delete_employee_")
)
async def handle_delete_request(callback: CallbackQuery, state: FSMContext):
    """Обработка удаления заявки"""
    try:
        logger.info(f"Обработка удаления заявки для пользователя {callback.from_user.id}")
        
        request_number = callback.data.replace("delete_", "")
        
        # Получаем заявку из базы данных
        db_session = next(get_db())
        request = db_session.query(Request).filter(Request.request_number == request_number).first()
        
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        # Проверяем права доступа (сравниваем с telegram_id пользователя)
        from uk_management_bot.database.models.user import User
        user = db_session.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not user or request.user_id != user.id:
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
        
        logger.info(f"Заявка {request_number} удалена пользователем {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки удаления заявки: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("accept_") and not c.data.startswith("accept_request_"))
async def handle_accept_request(callback: CallbackQuery, state: FSMContext):
    """Обработка принятия заявки менеджером - показывает выбор типа назначения"""
    try:
        logger.info(f"Обработка принятия заявки менеджером для пользователя {callback.from_user.id}")
        # Проверяем, что действие выполняет менеджер
        db_session = next(get_db())
        auth = AuthService(db_session)
        if not await auth.is_user_manager(callback.from_user.id):
            await callback.answer("Доступно только менеджеру", show_alert=True)
            return

        request_number = callback.data.replace("accept_", "")

        # Получаем заявку для отображения информации
        request = db_session.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        # Изменяем статус на "В работе"
        service = RequestService(db_session)
        result = service.update_status_by_actor(
            request_number=request_number,
            new_status="В работе",
            actor_telegram_id=callback.from_user.id,
        )

        if not result.get("success"):
            await callback.answer(result.get("message", "Ошибка"), show_alert=True)
            return

        # Показываем выбор типа назначения
        from uk_management_bot.keyboards.admin import get_assignment_type_keyboard

        await callback.message.edit_text(
            f"✅ <b>Заявка #{request_number} принята в работу</b>\n\n"
            f"📂 Категория: {request.category}\n"
            f"📍 Адрес: {request.address}\n\n"
            f"<b>Выберите способ назначения исполнителя:</b>",
            reply_markup=get_assignment_type_keyboard(request_number),
            parse_mode="HTML"
        )

        logger.info(f"Заявка {request_number} принята в работу менеджером {callback.from_user.id}, ожидание выбора типа назначения")

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
        request_number = callback.data.replace("complete_", "")
        service = RequestService(db_session)
        result = service.update_status_by_actor(
            request_number=request_number,
            new_status="Выполнена",
            actor_telegram_id=callback.from_user.id,
        )

        if not result.get("success"):
            await callback.answer(result.get("message", "Ошибка"), show_alert=True)
            return

        await callback.message.edit_text(
            f"✅ Заявка #{request_number} отмечена как выполненная"
        )
        await callback.message.answer(
            "Возврат в главное меню.",
            reply_markup=get_user_contextual_keyboard(callback.from_user.id)
        )
        logger.info(f"Заявка {request_number} завершена пользователем {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки завершения заявки: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("clarify_"))
async def handle_clarify_request(callback: CallbackQuery, state: FSMContext):
    """Обработка перевода заявки в статус 'Уточнение'"""
    try:
        # Только менеджер
        request_number = callback.data.replace("clarify_", "")
        db_session = next(get_db())
        auth = AuthService(db_session)
        if not await auth.is_user_manager(callback.from_user.id):
            await callback.answer("Доступно только менеджеру", show_alert=True)
            return
        service = RequestService(db_session)
        result = service.update_status_by_actor(
            request_number=request_number,
            new_status="Уточнение",
            actor_telegram_id=callback.from_user.id,
        )
        if not result.get("success"):
            await callback.answer(result.get("message", "Ошибка"), show_alert=True)
            return
        await callback.message.edit_text(
            f"❓ Заявка #{request_number} переведена в статус 'Уточнение'",
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка обработки перевода в 'Уточнение': {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("purchase_") and not c.data.startswith("purchase_materials_"))
async def handle_purchase_request(callback: CallbackQuery, state: FSMContext):
    """Обработка перевода заявки в статус 'Закуп'"""
    try:
        # Только менеджер
        request_number = callback.data.replace("purchase_", "")
        db_session = next(get_db())
        auth = AuthService(db_session)
        if not await auth.is_user_manager(callback.from_user.id):
            await callback.answer("Доступно только менеджеру", show_alert=True)
            return
        service = RequestService(db_session)
        result = service.update_status_by_actor(
            request_number=request_number,
            new_status="Закуп",
            actor_telegram_id=callback.from_user.id,
        )
        if not result.get("success"):
            await callback.answer(result.get("message", "Ошибка"), show_alert=True)
            return
        await callback.message.edit_text(
            f"💰 Заявка #{request_number} переведена в статус 'Закуп'",
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка обработки перевода в 'Закуп': {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(
    F.data.startswith("cancel_") &
    ~F.data.startswith("cancel_document_selection_") &
    ~F.data.in_(["cancel_action", "cancel_apartment_selection"])
)
async def handle_cancel_request(callback: CallbackQuery, state: FSMContext):
    """Обработка отмены заявки"""
    try:
        # Менеджер или владелец (в RequestService также есть проверка)
        request_number = callback.data.replace("cancel_", "")
        db_session = next(get_db())
        auth = AuthService(db_session)
        is_manager = await auth.is_user_manager(callback.from_user.id)
        service = RequestService(db_session)
        result = service.update_status_by_actor(
            request_number=request_number,
            new_status="Отменена",
            actor_telegram_id=callback.from_user.id,
        )
        if not result.get("success"):
            await callback.answer(result.get("message", "Ошибка"), show_alert=True)
            return
        await callback.message.edit_text(
            f"❌ Заявка #{request_number} отменена",
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка обработки отмены заявки: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("deny_"))
async def handle_executor_propose_deny(callback: CallbackQuery, state: FSMContext):
    """Исполнитель предлагает отказ (эскалируется менеджеру). Добавляем запись в notes без смены статуса."""
    try:
        request_number = callback.data.replace("deny_", "")
        db_session = next(get_db())
        auth = AuthService(db_session)
        # Только исполнитель
        if not await auth.is_user_executor(callback.from_user.id):
            await callback.answer("Доступно только исполнителю", show_alert=True)
            return
        service = RequestService(db_session)
        req = service.get_request_by_number(request_number)
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


@router.callback_query(F.data.startswith("approve_") & ~F.data.startswith("approve_employee_") & ~F.data.startswith("approve_user_"))
async def handle_approve_request(callback: CallbackQuery, state: FSMContext):
    """Подтверждение выполненной заявки заявителем -> 'Подтверждена'"""
    try:
        request_number = callback.data.replace("approve_", "")
        db_session = next(get_db())
        service = RequestService(db_session)
        result = service.update_status_by_actor(
            request_number=request_number,
            new_status="Подтверждена",
            actor_telegram_id=callback.from_user.id,
        )
        if not result.get("success"):
            await callback.answer(result.get("message", "Ошибка"), show_alert=True)
            return
        await callback.message.edit_text(
            f"✅ Заявка #{request_number} подтверждена",
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
        active_status = data.get("my_requests_status", "all")  # По умолчанию показываем все заявки
        current_page = int(data.get("my_requests_page", 1))

        # Убеждаемся, что статус установлен в FSM
        if not data.get("my_requests_status"):
            await state.update_data(my_requests_status="all")
        db_session = next(get_db())
        
        # Получаем пользователя из базы данных по telegram_id
        from uk_management_bot.database.models.user import User
        user = db_session.query(User).filter(User.telegram_id == telegram_id).first()
        
        if not user:
            await message.answer("Пользователь не найден в базе данных.")
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
            # Для исполнителей: показываем заявки, назначенные им или их специализации (если в активной смене)
            from uk_management_bot.database.models.request_assignment import RequestAssignment
            from uk_management_bot.database.models.shift import Shift
            from datetime import datetime

            # Получаем специализации исполнителя (может быть несколько)
            executor_specializations = []
            if user.specialization:
                try:
                    # Проверяем, является ли специализация JSON массивом
                    if isinstance(user.specialization, str) and user.specialization.startswith('['):
                        executor_specializations = json.loads(user.specialization)
                    else:
                        # Если это простая строка, используем её как единственную специализацию
                        executor_specializations = [user.specialization]
                except (json.JSONDecodeError, TypeError) as e:
                    # В случае ошибки парсинга, используем как строку
                    logger.warning(f"Ошибка парсинга специализации пользователя {user.id}: {e}")
                    executor_specializations = [user.specialization] if user.specialization else []

            # Проверяем, находится ли исполнитель в активной смене
            now = datetime.now()
            active_shift = db_session.query(Shift).filter(
                Shift.user_id == user.id,
                Shift.status == "active",
                Shift.start_time <= now,
                or_(Shift.end_time.is_(None), Shift.end_time >= now)
            ).first()

            has_active_shift = active_shift is not None
            logger.info(f"Исполнитель {user.id}: активная смена = {has_active_shift}")

            # Запрос для получения назначенных заявок
            query = db_session.query(Request).join(RequestAssignment).filter(
                RequestAssignment.status == "active"
            )

            # Фильтруем по назначениям
            assignment_conditions = []

            # 1. Индивидуальные назначения этому исполнителю (ВСЕГДА показываем)
            assignment_conditions.append(RequestAssignment.executor_id == user.id)

            # 2. Групповые назначения по специализациям (ТОЛЬКО если в активной смене)
            if has_active_shift and executor_specializations:
                for spec in executor_specializations:
                    assignment_conditions.append(
                        (RequestAssignment.assignment_type == "group") &
                        (RequestAssignment.group_specialization == spec)
                    )
                logger.info(f"Исполнитель в смене: добавлены групповые назначения для специализаций {executor_specializations}")
            else:
                if not has_active_shift:
                    logger.info(f"Исполнитель НЕ в смене: групповые назначения НЕ показываются")

            # Если есть условия назначений, применяем их
            if assignment_conditions:
                query = query.filter(or_(*assignment_conditions))
            else:
                # Если нет специализации, показываем только индивидуальные назначения
                query = query.filter(RequestAssignment.executor_id == user.id)

            logger.info(f"Исполнитель {user.id}: специализации={executor_specializations}, условий назначения={len(assignment_conditions)}")

        else:
            # Для заявителей и других ролей: показываем их собственные заявки
            query = db_session.query(Request).filter(Request.user_id == user.id)
            logger.info(f"Заявитель/другая роль {user.id}: показываем заявки с user_id={user.id}")
        
        # Фильтр статуса: применяем для ВСЕХ ролей (включая исполнителей)
        if active_status == "active":
            # Активные: рабочие статусы (ожидают действий)
            query = query.filter(Request.status.in_(["Новая", "В работе", "Закуп", "Уточнение"]))
            logger.info(f"Применен фильтр active_status='active': статусы=['Новая', 'В работе', 'Закуп', 'Уточнение']")
        elif active_status == "archive":
            # Архив: финальные и завершенные статусы
            query = query.filter(Request.status.in_(["Выполнена", "Принято", "Подтверждена", "Отменена"]))
            logger.info(f"Применен фильтр active_status='archive': статусы=['Выполнена', 'Принято', 'Подтверждена', 'Отменена']")
        elif active_status == "all":
            # Все заявки: без фильтра по статусу
            logger.info(f"Применен фильтр active_status='all': показываем все заявки без фильтра статуса")
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
        logger.info(f"Пользователь {telegram_id} (роль: {active_role}, специализации: {executor_specializations if active_role == 'executor' else 'N/A'}) - найдено заявок: {len(user_requests)}")
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

        # Определяем заголовок в зависимости от роли
        if active_role == "executor":
            # Для исполнителей - назначенные заявки
            message_text = f"📋 Назначенные заявки (страница {current_page}/{total_pages}):\n\n"
        else:
            # Для заявителей - с фильтром
            if active_status == "active":
                status_title = "Активные заявки"
            elif active_status == "archive":
                status_title = "Архив заявок"
            else:
                status_title = "Все заявки"
            message_text = f"📋 {status_title} (страница {current_page}/{total_pages}):\n\n"

        # Иконки для статусов
        def _icon(st: str) -> str:
            mapping = {
                "В работе": "🛠️",
                "Закуп": "💰",
                "Уточнение": "❓",
                "Подтверждена": "⭐",
                "Отменена": "❌",
                "Выполнена": "✅",
                "Новая": "🆕",
                "Принято": "✅",
            }
            return mapping.get(st, "")

        if not page_requests:
            if active_role == "executor":
                message_text += "Пока нет назначенных вам заявок."
            else:
                message_text += "Пока нет заявок. Нажмите 'Создать заявку' в главном меню."
        else:
            # Для заявителей показываем текстовый список
            if active_role != "executor":
                for i, r in enumerate(page_requests, 1):
                    address = r.address
                    if len(address) > 60:
                        address = address[:60] + "…"
                    message_text += f"{i}. {_icon(r.status)} #{r.request_number} - {r.category} - {r.status}\n"
                    message_text += f"   Адрес: {address}\n"
                    message_text += f"   Создана: {r.created_at.strftime('%d.%m.%Y')}\n"
                    # Показываем дополнительную информацию для некоторых статусов
                    if r.status == "Отменена" and r.notes:
                        message_text += f"   Причина отказа: {r.notes[:100]}...\n" if len(r.notes) > 100 else f"   Причина отказа: {r.notes}\n"
                    elif r.status == "Уточнение" and r.notes:
                        notes_lines = r.notes.strip().split('\n')
                        last_messages = [line for line in notes_lines[-2:] if line.strip()]
                        if last_messages:
                            preview = '\n'.join(last_messages)
                            if len(preview) > 80:
                                preview = preview[:77] + '...'
                            message_text += f"   Уточнение: {preview}\n"
                    message_text += "\n"

        from uk_management_bot.keyboards.requests import get_pagination_keyboard

        # Формируем клавиатуру
        rows = []

        # Для исполнителей НЕ показываем кнопки фильтрации (Активные/Архив)
        # Они видят только заявки, назначенные им
        if active_role != "executor":
            # Для заявителей и других ролей - показываем фильтры
            filter_status_kb = get_status_filter_inline_keyboard(active_status)
            rows = list(filter_status_kb.inline_keyboard)

            # Добавляем кнопки для заявок, требующих действий заявителя
            for r in page_requests:
                if r.status == "Уточнение":
                    # Кнопка для ответа на уточнение
                    rows.append([InlineKeyboardButton(
                        text=f"💬 Ответить на #{r.request_number}",
                        callback_data=f"replyclarify_{r.request_number}"
                    )])
                elif r.status == "Выполнена":
                    # Кнопка для подтверждения выполнения
                    rows.append([InlineKeyboardButton(
                        text=f"✅ Подтвердить #{r.request_number}",
                        callback_data=f"approve_{r.request_number}"
                    )])
        else:
            # Для исполнителей добавляем кнопки заявок
            message_text += "Выберите заявку для просмотра деталей:\n\n"
            for i, r in enumerate(page_requests, 1):
                button_text = f"{_icon(r.status)} #{r.request_number} - {r.category}"
                rows.append([InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"view_request_{r.request_number}"
                )])

        # Добавляем пагинацию в конце
        pagination_kb = get_pagination_keyboard(current_page, total_pages)
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
        request_number = callback.data.replace("replyclarify_", "")
        # Показать текущий диалог из notes перед вводом
        db_session = next(get_db())
        req = db_session.query(Request).filter(Request.request_number == request_number).first()
        await state.update_data(reply_request_number=request_number)
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
        request_number = data.get("reply_request_number")
        if not request_number:
            await message.answer("Ошибка: номер заявки не найден")
            await state.clear()
            return
        
        db_session = next(get_db())
        service = RequestService(db_session)
        req = service.get_request_by_number(request_number)
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
        data = await state.get_data()
        db_session = next(get_db())

        # Получаем пользователя из базы данных по telegram_id
        from uk_management_bot.database.models.user import User
        user = db_session.query(User).filter(User.telegram_id == callback.from_user.id).first()

        if not user:
            await callback.answer("Пользователь не найден в базе данных.", show_alert=True)
            return

        query = db_session.query(Request).filter(Request.user_id == user.id)
        if choice == "active" or choice == "В работе":
            # Активные: рабочие статусы (ожидают действий)
            query = query.filter(Request.status.in_(["Новая", "В работе", "Закуп", "Уточнение"]))
        elif choice == "archive":
            # Архив: финальные и завершенные статусы
            query = query.filter(Request.status.in_(["Выполнена", "Принято", "Подтверждена", "Отменена"]))
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
            status_title = "Активные заявки"
        elif choice == "archive":
            status_title = "Архив заявок"
        else:
            status_title = "Все заявки"
        message_text = f"📋 {status_title} (страница {current_page}/{total_pages}):\n\n"
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
                    "Принято": "✅",
                    "Новая": "🆕",
                }
                return mapping.get(st, "")
            for i, request in enumerate(page_requests, 1):
                address = request.address
                if len(address) > 60:
                    address = address[:60] + "…"
                message_text += f"{i}. {_icon(request.status)} #{request.request_number} - {request.category} - {request.status}\n"
                message_text += f"   Адрес: {address}\n"
                message_text += f"   Создана: {request.created_at.strftime('%d.%m.%Y')}\n"
                if choice == "archive" and request.status == "Отменена" and request.notes:
                    message_text += f"   Причина отказа: {request.notes}\n"
                elif request.status == "Уточнение" and request.notes:
                    # Показываем последние сообщения из диалога уточнения
                    notes_lines = request.notes.strip().split('\n')
                    last_messages = [line for line in notes_lines[-3:] if line.strip()]  # Последние 3 сообщения
                    if last_messages:
                        preview = '\n'.join(last_messages)
                        if len(preview) > 100:
                            preview = preview[:97] + '...'
                        message_text += f"   Уточнение: {preview}\n"
                message_text += "\n"

        from uk_management_bot.keyboards.requests import get_pagination_keyboard
        filter_status_kb = get_status_filter_inline_keyboard(choice)

        # Формируем клавиатуру
        combined_rows = list(filter_status_kb.inline_keyboard)

        # Добавляем кнопки для заявок, требующих действий заявителя
        for r in page_requests:
            if r.status == "Уточнение":
                # Кнопка для ответа на уточнение
                combined_rows.append([InlineKeyboardButton(
                    text=f"💬 Ответить на #{r.request_number}",
                    callback_data=f"replyclarify_{r.request_number}"
                )])
            elif r.status == "Выполнена":
                # Кнопка для подтверждения выполнения
                combined_rows.append([InlineKeyboardButton(
                    text=f"✅ Подтвердить #{r.request_number}",
                    callback_data=f"approve_{r.request_number}"
                )])

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


# ===== ОБРАБОТЧИКИ НАЗНАЧЕНИЯ ИСПОЛНИТЕЛЕЙ =====

@router.callback_query(F.data.startswith("assign_duty_"))
async def handle_assign_duty_executor(callback: CallbackQuery):
    """Назначение дежурного специалиста (автоматическое по сменам)"""
    try:
        request_number = callback.data.replace("assign_duty_", "")
        logger.info(f"Назначение дежурного специалиста для заявки {request_number}")

        db_session = next(get_db())

        # Используем существующую логику auto_assign
        await auto_assign_request_by_category(request_number, db_session, callback.from_user.id)

        await callback.message.edit_text(
            f"✅ <b>Заявка #{request_number} назначена дежурному специалисту</b>\n\n"
            f"Назначение выполнено автоматически на основе:\n"
            f"• Текущих смен\n"
            f"• Специализации исполнителей\n"
            f"• Загруженности\n\n"
            f"Исполнитель получит уведомление.",
            parse_mode="HTML"
        )

        await callback.message.answer(
            "Возврат в главное меню.",
            reply_markup=get_user_contextual_keyboard(callback.from_user.id)
        )

        logger.info(f"Заявка {request_number} назначена дежурному специалисту")

    except Exception as e:
        logger.error(f"Ошибка назначения дежурного специалиста: {e}")
        await callback.answer("Произошла ошибка при назначении", show_alert=True)


@router.callback_query(F.data.startswith("assign_specific_"))
async def handle_assign_specific_executor(callback: CallbackQuery):
    """Показать список исполнителей для ручного выбора"""
    try:
        request_number = callback.data.replace("assign_specific_", "")
        logger.info(f"Выбор конкретного исполнителя для заявки {request_number}")

        db_session = next(get_db())

        # Получаем заявку
        request = db_session.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        # Получаем исполнителей с нужной специализацией
        # Определяем специализацию на основе категории
        category_to_spec = {
            "Электрика": "electrician",
            "Сантехника": "plumber",
            "Охрана": "security",
            "Уборка": "cleaner",
        }

        spec = category_to_spec.get(request.category, "other")

        # Получаем всех исполнителей с данной специализацией
        from uk_management_bot.database.models.user import User
        import json

        executors = db_session.query(User).filter(
            User.roles.contains('"executor"'),
            User.status == "approved"
        ).all()

        # Фильтруем по специализации
        filtered_executors = []
        for ex in executors:
            if ex.specialization:
                try:
                    specializations = json.loads(ex.specialization) if isinstance(ex.specialization, str) else ex.specialization
                    if spec in specializations or "other" in specializations:
                        filtered_executors.append(ex)
                except:
                    pass

        # Показываем клавиатуру с исполнителями
        from uk_management_bot.keyboards.admin import get_executors_by_category_keyboard

        executors_text = f"Найдено исполнителей: {len(filtered_executors)}" if filtered_executors else "Нет доступных исполнителей"

        await callback.message.edit_text(
            f"👤 <b>Выбор исполнителя</b>\n\n"
            f"📋 Заявка: #{request_number}\n"
            f"📂 Категория: {request.category}\n"
            f"🔧 Специализация: {spec}\n\n"
            f"{executors_text}\n\n"
            f"🟢 - На смене\n"
            f"⚪ - Не на смене",
            reply_markup=get_executors_by_category_keyboard(request_number, request.category, filtered_executors),
            parse_mode="HTML"
        )

        logger.info(f"Показан список из {len(filtered_executors)} исполнителей для заявки {request_number}")

    except Exception as e:
        logger.error(f"Ошибка показа списка исполнителей: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("assign_executor_"))
async def handle_final_executor_assignment(callback: CallbackQuery):
    """Финальное назначение конкретного исполнителя"""
    try:
        # Парсим данные: assign_executor_251013-001_123
        parts = callback.data.replace("assign_executor_", "").split("_")
        request_number = parts[0]
        executor_id = int(parts[1])

        logger.info(f"Финальное назначение исполнителя {executor_id} на заявку {request_number}")

        db_session = next(get_db())

        # Получаем заявку и исполнителя
        request = db_session.query(Request).filter(Request.request_number == request_number).first()
        from uk_management_bot.database.models.user import User
        executor = db_session.query(User).filter(User.id == executor_id).first()

        if not request or not executor:
            await callback.answer("Заявка или исполнитель не найдены", show_alert=True)
            return

        # Назначаем исполнителя
        request.executor_id = executor_id
        request.assignment_type = "manual"  # Помечаем как ручное назначение
        db_session.commit()

        executor_name = f"{executor.first_name or ''} {executor.last_name or ''}".strip()
        if not executor_name:
            executor_name = f"@{executor.username}" if executor.username else f"ID{executor.id}"

        await callback.message.edit_text(
            f"✅ <b>Заявка #{request_number} назначена исполнителю</b>\n\n"
            f"👤 Исполнитель: {executor_name}\n"
            f"📂 Категория: {request.category}\n"
            f"📍 Адрес: {request.address}\n\n"
            f"Исполнитель получит уведомление о назначении.",
            parse_mode="HTML"
        )

        # Отправляем уведомление исполнителю
        try:
            from aiogram import Bot
            bot = Bot.get_current()

            notification_text = (
                f"📋 <b>Вам назначена новая заявка!</b>\n\n"
                f"№ заявки: #{request.format_number_for_display()}\n"
                f"📂 Категория: {request.category}\n"
                f"📍 Адрес: {request.address}\n"
                f"📝 Описание: {request.description}\n\n"
                f"Пожалуйста, приступите к выполнению."
            )

            await bot.send_message(executor.telegram_id, notification_text, parse_mode="HTML")
            logger.info(f"Уведомление о назначении отправлено исполнителю {executor.telegram_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления исполнителю: {e}")

        await callback.message.answer(
            "Возврат в главное меню.",
            reply_markup=get_user_contextual_keyboard(callback.from_user.id)
        )

        logger.info(f"Заявка {request_number} назначена исполнителю {executor_id}")

    except Exception as e:
        logger.error(f"Ошибка финального назначения исполнителя: {e}")
        await callback.answer("Произошла ошибка при назначении", show_alert=True)


@router.callback_query(F.data.startswith("back_to_assignment_type_"))
async def handle_back_to_assignment_type(callback: CallbackQuery):
    """Возврат к выбору типа назначения"""
    try:
        request_number = callback.data.replace("back_to_assignment_type_", "")

        db_session = next(get_db())
        request = db_session.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        from uk_management_bot.keyboards.admin import get_assignment_type_keyboard

        await callback.message.edit_text(
            f"✅ <b>Заявка #{request_number} принята в работу</b>\n\n"
            f"📂 Категория: {request.category}\n"
            f"📍 Адрес: {request.address}\n\n"
            f"<b>Выберите способ назначения исполнителя:</b>",
            reply_markup=get_assignment_type_keyboard(request_number),
            parse_mode="HTML"
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка возврата к выбору типа назначения: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


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
    try:
        request_number = callback.data.replace("executor_view_media_", "")
        db_session = next(get_db())
        request = db_session.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
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
            await callback.answer("✅ Медиа-файлы отправлены")
        else:
            await callback.answer("Нет медиа-файлов", show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка просмотра медиа исполнителем: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("executor_purchase_"))
async def executor_request_purchase(callback: CallbackQuery, state: FSMContext):
    """Исполнитель переводит заявку в 'Закуп'"""
    try:
        request_number = callback.data.replace("executor_purchase_", "")
        await state.update_data(executor_request_number=request_number)
        await state.set_state(ExecutorRequestStates.waiting_purchase_comment)

        await callback.message.edit_text(
            f"💰 <b>Перевод заявки #{request_number} в статус 'Закуп'</b>\n\n"
            f"Укажите, что требуется приобрести:",
            parse_mode="HTML"
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка начала процесса закупа: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.message(ExecutorRequestStates.waiting_purchase_comment)
async def executor_process_purchase_comment(message: Message, state: FSMContext):
    """Обработка комментария для закупа"""
    try:
        data = await state.get_data()
        request_number = data.get("executor_request_number")

        db_session = next(get_db())
        request = db_session.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await message.answer("Заявка не найдена")
            await state.clear()
            return

        # Обновляем статус и добавляем комментарий
        old_status = request.status
        request.status = "Закуп"

        # Добавляем комментарий в notes
        purchase_note = f"\n[Исполнитель] Требуется закуп: {message.text}"
        request.notes = (request.notes or "") + purchase_note
        request.updated_at = db_session.query(Request).filter(Request.request_number == request_number).first().updated_at

        db_session.commit()

        # Отправляем уведомление
        from uk_management_bot.services.notification_service import async_notify_request_status_changed
        try:
            bot = Bot.get_current()
            await async_notify_request_status_changed(bot, db_session, request, old_status, "Закуп")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления: {e}")

        await message.answer(
            f"✅ Заявка #{request_number} переведена в статус 'Закуп'\n\n"
            f"Комментарий сохранен.",
            reply_markup=get_user_contextual_keyboard(message.from_user.id)
        )

        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка обработки комментария закупа: {e}")
        await message.answer("Произошла ошибка")
        await state.clear()


@router.callback_query(F.data.startswith("executor_complete_"))
async def executor_complete_request(callback: CallbackQuery, state: FSMContext):
    """Исполнитель переводит заявку в 'Выполнено'"""
    try:
        request_number = callback.data.replace("executor_complete_", "")
        await state.update_data(executor_request_number=request_number, completion_media=[])
        await state.set_state(ExecutorRequestStates.waiting_completion_comment)

        await callback.message.edit_text(
            f"✅ <b>Завершение заявки #{request_number}</b>\n\n"
            f"Напишите комментарий о выполненной работе:",
            parse_mode="HTML"
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка начала завершения заявки: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.message(ExecutorRequestStates.waiting_completion_comment)
async def executor_process_completion_comment(message: Message, state: FSMContext):
    """Обработка комментария для завершения"""
    try:
        data = await state.get_data()
        request_number = data.get("executor_request_number")

        await state.update_data(completion_comment=message.text)
        await state.set_state(ExecutorRequestStates.waiting_completion_media)

        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Завершить без медиа", callback_data=f"executor_finish_completion_{request_number}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"view_request_{request_number}")]
        ])

        await message.answer(
            f"📎 Теперь отправьте фото/видео результата работ или нажмите 'Завершить без медиа'",
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Ошибка обработки комментария завершения: {e}")
        await message.answer("Произошла ошибка")
        await state.clear()


@router.message(ExecutorRequestStates.waiting_completion_media, F.photo | F.video | F.document)
async def executor_collect_completion_media(message: Message, state: FSMContext):
    """Сбор медиа-файлов для завершения заявки"""
    try:
        data = await state.get_data()
        completion_media = data.get("completion_media", [])
        request_number = data.get("executor_request_number")

        # Добавляем файл в список
        if message.photo:
            completion_media.append({"type": "photo", "file_id": message.photo[-1].file_id})
        elif message.video:
            completion_media.append({"type": "video", "file_id": message.video.file_id})
        elif message.document:
            completion_media.append({"type": "document", "file_id": message.document.file_id})

        await state.update_data(completion_media=completion_media)

        # Обновляем клавиатуру с счетчиком
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"✅ Завершить ({len(completion_media)} файлов)", callback_data=f"executor_finish_completion_{request_number}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"view_request_{request_number}")]
        ])

        await message.answer(
            f"📎 Файл добавлен ({len(completion_media)}). Отправьте еще или нажмите 'Завершить'",
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Ошибка сбора медиа для завершения: {e}")
        await message.answer("Произошла ошибка")


@router.callback_query(F.data.startswith("executor_finish_completion_"))
async def executor_finish_completion(callback: CallbackQuery, state: FSMContext):
    """Финализация завершения заявки"""
    try:
        request_number = callback.data.replace("executor_finish_completion_", "")
        data = await state.get_data()
        completion_comment = data.get("completion_comment", "")
        completion_media = data.get("completion_media", [])

        db_session = next(get_db())
        request = db_session.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
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
                        description=f"Отчет о выполнении работы #{idx}",
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

        # Обновляем статус
        old_status = request.status
        request.status = "Выполнена"

        # Добавляем комментарий
        completion_note = f"\n[Исполнитель] Работа выполнена: {completion_comment}"
        request.notes = (request.notes or "") + completion_note

        # Сохраняем медиа (и Telegram file_id, и Media Service IDs)
        if media_service_files:
            import json
            # Сохраняем информацию о файлах в Media Service
            request.completion_media = json.dumps(media_service_files)
            logger.info(f"Сохранено {len(media_service_files)} файлов в completion_media")
        elif completion_media:
            # Если загрузка в Media Service не удалась, сохраняем хотя бы Telegram file_id
            import json
            request.completion_media = json.dumps(completion_media)
            logger.warning(f"Сохранены только Telegram file_id, без Media Service")

        db_session.commit()

        # Отправляем уведомление
        from uk_management_bot.services.notification_service import async_notify_request_status_changed
        try:
            await async_notify_request_status_changed(callback.bot, db_session, request, old_status, "Выполнена")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления: {e}")

        # Формируем сообщение с результатом
        message_text = f"✅ <b>Заявка #{request_number} выполнена!</b>\n\n"
        message_text += f"Комментарий: {completion_comment}\n"
        if media_service_files:
            message_text += f"📎 Загружено файлов в Media Service: {len(media_service_files)}"
        elif completion_media:
            message_text += f"⚠️ Файлов: {len(completion_media)} (сохранены локально)"

        await callback.message.edit_text(message_text, parse_mode="HTML")

        await state.clear()
        await callback.answer("✅ Заявка завершена")

    except Exception as e:
        logger.error(f"Ошибка финализации завершения: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)
        await state.clear()


@router.callback_query(F.data.startswith("executor_work_"))
async def executor_return_to_work(callback: CallbackQuery):
    """Возврат заявки в работу из статуса Закуп/Уточнение"""
    try:
        request_number = callback.data.replace("executor_work_", "")
        db_session = next(get_db())
        request = db_session.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        old_status = request.status
        request.status = "В работе"
        db_session.commit()

        # Отправляем уведомление
        from uk_management_bot.services.notification_service import async_notify_request_status_changed
        try:
            bot = Bot.get_current()
            await async_notify_request_status_changed(bot, db_session, request, old_status, "В работе")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления: {e}")

        await callback.message.edit_text(
            f"🔄 Заявка #{request_number} возвращена в работу",
            parse_mode="HTML"
        )
        await callback.answer("✅ Заявка в работе")

    except Exception as e:
        logger.error(f"Ошибка возврата заявки в работу: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)
