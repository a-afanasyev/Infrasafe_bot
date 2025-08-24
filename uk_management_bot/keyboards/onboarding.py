"""
Клавиатуры для процесса онбординга новых пользователей

Содержит клавиатуры для:
- Выбора типа документа
- Подтверждения загрузки
- Навигации по процессу онбординга
"""

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from uk_management_bot.database.models.user_verification import DocumentType
from uk_management_bot.utils.helpers import get_text

def get_document_type_keyboard(language: str = "ru") -> ReplyKeyboardMarkup:
    """
    Создает клавиатуру для выбора типа документа
    
    Args:
        language: Язык интерфейса
        
    Returns:
        ReplyKeyboardMarkup с кнопками типов документов
    """
    keyboard = [
        [
            KeyboardButton(text="📄 Паспорт"),
            KeyboardButton(text="🏠 Кадастровая выписка")
        ],
        [
            KeyboardButton(text="📋 Договор аренды"),
            KeyboardButton(text="📄 Другие документы")
        ],
        [
            KeyboardButton(text="⏭️ Пропустить документы"),
            KeyboardButton(text="✅ Завершить онбординг")
        ]
    ]
    
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )

def get_document_confirmation_keyboard(language: str = "ru") -> ReplyKeyboardMarkup:
    """
    Создает клавиатуру для подтверждения загрузки документа
    
    Args:
        language: Язык интерфейса
        
    Returns:
        ReplyKeyboardMarkup с кнопками подтверждения
    """
    keyboard = [
        [
            KeyboardButton(text="✅ Подтвердить загрузку"),
            KeyboardButton(text="❌ Отменить")
        ],
        [
            KeyboardButton(text="🔄 Загрузить другой документ")
        ]
    ]
    
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )

def get_onboarding_completion_keyboard(language: str = "ru") -> ReplyKeyboardMarkup:
    """
    Создает клавиатуру для завершения онбординга
    
    Args:
        language: Язык интерфейса
        
    Returns:
        ReplyKeyboardMarkup с кнопками завершения
    """
    keyboard = [
        [
            KeyboardButton(text="📄 Добавить еще документы"),
            KeyboardButton(text="✅ Завершить онбординг")
        ]
    ]
    
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )

def get_document_type_inline_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """
    Создает inline клавиатуру для выбора типа документа
    
    Args:
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup с кнопками типов документов
    """
    keyboard = [
        [
            InlineKeyboardButton(
                text="📄 Паспорт",
                callback_data="doc_type_passport"
            ),
            InlineKeyboardButton(
                text="🏠 Кадастровая выписка",
                callback_data="doc_type_property_deed"
            )
        ],
        [
            InlineKeyboardButton(
                text="📋 Договор аренды",
                callback_data="doc_type_rental_agreement"
            ),
            InlineKeyboardButton(
                text="📄 Другие документы",
                callback_data="doc_type_other"
            )
        ],
        [
            InlineKeyboardButton(
                text="⏭️ Пропустить документы",
                callback_data="doc_type_skip"
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_document_management_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """
    Создает inline клавиатуру для управления документами
    
    Args:
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup с кнопками управления
    """
    keyboard = [
        [
            InlineKeyboardButton(
                text="📄 Добавить документ",
                callback_data="add_document"
            ),
            InlineKeyboardButton(
                text="✅ Завершить",
                callback_data="complete_onboarding"
            )
        ],
        [
            InlineKeyboardButton(
                text="⏭️ Пропустить документы",
                callback_data="skip_documents"
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_document_type_from_text(text: str) -> DocumentType:
    """
    Определяет тип документа по тексту кнопки
    
    Args:
        text: Текст кнопки
        
    Returns:
        DocumentType enum значение
    """
    text_lower = text.lower()
    
    if "паспорт" in text_lower:
        return DocumentType.PASSPORT
    elif "кадастровая" in text_lower or "выписка" in text_lower:
        return DocumentType.PROPERTY_DEED
    elif "договор" in text_lower or "аренда" in text_lower:
        return DocumentType.RENTAL_AGREEMENT
    elif "другие" in text_lower or "other" in text_lower:
        return DocumentType.OTHER
    else:
        return DocumentType.OTHER

def get_document_type_name(document_type: DocumentType, language: str = "ru") -> str:
    """
    Получает название типа документа на указанном языке
    
    Args:
        document_type: Тип документа
        language: Язык интерфейса
        
    Returns:
        Название типа документа
    """
    document_names = {
        DocumentType.PASSPORT: "Паспорт",
        DocumentType.PROPERTY_DEED: "Кадастровая выписка",
        DocumentType.RENTAL_AGREEMENT: "Договор аренды",
        DocumentType.UTILITY_BILL: "Квитанция ЖКХ",
        DocumentType.OTHER: "Другие документы"
    }
    
    return document_names.get(document_type, "Другие документы")
