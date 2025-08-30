"""
Клавиатуры для редактирования профиля пользователя
"""
import logging
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)


def get_profile_edit_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура для редактирования профиля"""
    try:
        logger.info(f"Создание клавиатуры редактирования профиля для языка: {language}")
        
        builder = InlineKeyboardBuilder()
        
        # Кнопки редактирования
        home_text = get_text('profile.edit_home_address', language=language)
        apartment_text = get_text('profile.edit_apartment_address', language=language)
        yard_text = get_text('profile.edit_yard_address', language=language)
        phone_text = get_text('profile.edit_phone', language=language)
        language_text = get_text('profile.edit_language', language=language)
        first_name_text = get_text('profile.edit_first_name', language=language)
        last_name_text = get_text('profile.edit_last_name', language=language)
        cancel_text = get_text('buttons.cancel', language=language)
        
        logger.debug(f"Тексты кнопок: home={home_text}, apartment={apartment_text}, yard={yard_text}, phone={phone_text}, language={language_text}, cancel={cancel_text}")
        
        builder.add(InlineKeyboardButton(
            text=f"🏠 {home_text}",
            callback_data="edit_home_address"
        ))
        
        builder.add(InlineKeyboardButton(
            text=f"🏢 {apartment_text}",
            callback_data="edit_apartment_address"
        ))
        
        builder.add(InlineKeyboardButton(
            text=f"🏘️ {yard_text}",
            callback_data="edit_yard_address"
        ))
        
        builder.add(InlineKeyboardButton(
            text=f"📱 {phone_text}",
            callback_data="edit_phone"
        ))
        
        builder.add(InlineKeyboardButton(
            text=f"🌐 {language_text}",
            callback_data="edit_language"
        ))
        
        # Кнопки редактирования ФИО
        builder.add(InlineKeyboardButton(
            text=f"👤 {first_name_text}",
            callback_data="edit_first_name"
        ))
        
        builder.add(InlineKeyboardButton(
            text=f"👤 {last_name_text}",
            callback_data="edit_last_name"
        ))
        
        # Кнопка отмены
        builder.add(InlineKeyboardButton(
            text=f"❌ {cancel_text}",
            callback_data="cancel_profile_edit"
        ))
        
        builder.adjust(2, 2, 1, 2, 1)
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
            text="🇷🇺 Русский",
            callback_data="set_language_ru"
        ))
        
        builder.add(InlineKeyboardButton(
            text="🇺🇿 O'zbek ✓",
            callback_data="set_language_uz"
        ))
        
        # Кнопка отмены на узбекском
        builder.add(InlineKeyboardButton(
            text=f"❌ {get_text('buttons.cancel', language=language)}",
            callback_data="cancel_language_choice"
        ))
    else:
        builder.add(InlineKeyboardButton(
            text="🇷🇺 Русский ✓",
            callback_data="set_language_ru"
        ))
        
        builder.add(InlineKeyboardButton(
            text="🇺🇿 O'zbek",
            callback_data="set_language_uz"
        ))
        
        # Кнопка отмены на русском
        builder.add(InlineKeyboardButton(
            text=f"❌ {get_text('buttons.cancel', language=language)}",
            callback_data="cancel_language_choice"
        ))
    
    builder.adjust(2, 1)
    return builder.as_markup()


def get_address_type_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура для выбора типа адреса"""
    builder = InlineKeyboardBuilder()
    
    # Кнопки типов адресов
    builder.add(InlineKeyboardButton(
        text="🏠 Домашний адрес",
        callback_data="address_type_home"
    ))
    
    builder.add(InlineKeyboardButton(
        text="🏢 Адрес квартиры",
        callback_data="address_type_apartment"
    ))
    
    builder.add(InlineKeyboardButton(
        text="🏘️ Адрес двора",
        callback_data="address_type_yard"
    ))
    
    # Кнопка отмены
    builder.add(InlineKeyboardButton(
        text="❌ Отмена",
        callback_data="cancel_address_type"
    ))
    
    builder.adjust(1, 1, 1)
    return builder.as_markup()


def get_cancel_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Простая клавиатура с кнопкой отмены"""
    builder = InlineKeyboardBuilder()
    
    builder.add(InlineKeyboardButton(
        text=f"❌ {get_text('buttons.cancel', language=language)}",
        callback_data="cancel_input"
    ))
    
    return builder.as_markup()
