"""
Клавиатуры для редактирования профиля пользователя
"""
import logging
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)


def get_profile_edit_keyboard(language: str = "ru", user=None) -> InlineKeyboardMarkup:
    """Клавиатура для редактирования профиля с отображением текущих значений"""
    try:
        logger.info(f"Создание клавиатуры редактирования профиля для языка: {language}")

        builder = InlineKeyboardBuilder()

        # Получаем текущие значения
        current_phone = user.phone if user and user.phone else get_text("profile.keyboards.not_specified_m", language=language)
        current_first_name = user.first_name if user and user.first_name else get_text("profile.keyboards.not_specified_n", language=language)
        current_last_name = user.last_name if user and user.last_name else get_text("profile.keyboards.not_specified_n", language=language)

        # Определяем текущий язык
        if user and user.language:
            current_lang = "🇷🇺 RU" if user.language == "ru" else "🇺🇿 UZ"
        else:
            current_lang = "🇷🇺 RU"

        # Кнопки редактирования
        cancel_text = get_text('buttons.cancel', language=language)

        logger.debug(f"Текущие значения: phone_set={bool(user and user.phone)}, language={current_lang}, first_name_set={bool(user and user.first_name)}, last_name_set={bool(user and user.last_name)}")

        # Редактирование телефона и языка с текущими значениями
        builder.add(InlineKeyboardButton(
            text=f"📱 {current_phone}",
            callback_data="edit_phone"
        ))

        builder.add(InlineKeyboardButton(
            text=f"🌐 {current_lang}",
            callback_data="edit_language"
        ))

        # Кнопки редактирования ФИО с текущими значениями
        builder.add(InlineKeyboardButton(
            text=f"👤 {current_first_name}",
            callback_data="edit_first_name"
        ))

        builder.add(InlineKeyboardButton(
            text=f"👤 {current_last_name}",
            callback_data="edit_last_name"
        ))

        # Кнопка "Мои квартиры" для управления квартирами из справочника
        builder.add(InlineKeyboardButton(
            text=get_text("profile.keyboards.my_apartments", language=language),
            callback_data="my_apartments"
        ))

        # Кнопка отмены
        builder.add(InlineKeyboardButton(
            text=cancel_text,
            callback_data="cancel_profile_edit"
        ))

        builder.adjust(2, 2, 1, 1)
        keyboard = builder.as_markup()
        
        logger.info("Клавиатура редактирования профиля успешно создана")
        return keyboard
        
    except Exception as e:
        logger.error(f"Ошибка создания клавиатуры редактирования профиля: {e}")
        logger.error(f"Тип ошибки: {type(e).__name__}")
        raise


def get_language_choice_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура для выбора языка"""
    builder = InlineKeyboardBuilder()
    
    # Кнопки языков с учетом текущего языка
    if language == "uz":
        builder.add(InlineKeyboardButton(
            text=get_text("profile.keyboards.lang_russian", language=language),
            callback_data="set_language_ru"
        ))

        builder.add(InlineKeyboardButton(
            text=get_text("profile.keyboards.lang_uzbek_selected", language=language),
            callback_data="set_language_uz"
        ))
        
        # Кнопка отмены на узбекском
        builder.add(InlineKeyboardButton(
            text=get_text('buttons.cancel', language=language),
            callback_data="cancel_language_choice"
        ))
    else:
        builder.add(InlineKeyboardButton(
            text=get_text("profile.keyboards.lang_russian_selected", language=language),
            callback_data="set_language_ru"
        ))

        builder.add(InlineKeyboardButton(
            text=get_text("profile.keyboards.lang_uzbek", language=language),
            callback_data="set_language_uz"
        ))

        # Кнопка отмены на русском
        builder.add(InlineKeyboardButton(
            text=get_text('buttons.cancel', language=language),
            callback_data="cancel_language_choice"
        ))
    
    builder.adjust(2, 1)
    return builder.as_markup()


def get_address_type_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура для выбора типа адреса"""
    builder = InlineKeyboardBuilder()
    
    # Кнопки типов адресов
    builder.add(InlineKeyboardButton(
        text=get_text("profile.keyboards.address_home", language=language),
        callback_data="address_type_home"
    ))
    
    builder.add(InlineKeyboardButton(
        text=get_text("profile.keyboards.address_apartment", language=language),
        callback_data="address_type_apartment"
    ))
    
    builder.add(InlineKeyboardButton(
        text=get_text("profile.keyboards.address_yard", language=language),
        callback_data="address_type_yard"
    ))
    
    # Кнопка отмены
    builder.add(InlineKeyboardButton(
        text=get_text('buttons.cancel', language=language),
        callback_data="cancel_address_type"
    ))
    
    builder.adjust(1, 1, 1)
    return builder.as_markup()


def get_cancel_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Простая клавиатура с кнопкой отмены"""
    builder = InlineKeyboardBuilder()
    
    builder.add(InlineKeyboardButton(
        text=get_text('buttons.cancel', language=language),
        callback_data="cancel_input"
    ))
    
    return builder.as_markup()
