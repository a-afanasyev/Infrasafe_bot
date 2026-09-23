"""Доменный справочник категорий и срочности заявок (A9-P2-10).

Жил в UI-слое ``keyboards/requests.py``, откуда его тянули services/ и api/ —
правка клавиатуры задевала домен и HTTP-схемы. Здесь только данные и чистые
функции нормализации/локализации (без aiogram). ``keyboards/requests.py``
ре-экспортирует те же объекты для хендлеров; services/api/utils импортируют
отсюда (гейт ``tests/services/test_lower_layers_do_not_import_keyboards.py``).
"""
import logging

from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)

# Category mapping: internal key -> locale key
CATEGORY_KEYS = {
    "electricity": "categories.electricity",
    "plumbing": "categories.plumbing",
    "heating": "categories.heating",
    "elevator": "categories.elevator",
    "cleaning": "categories.cleaning",
    "landscaping": "categories.landscaping",
    "security": "categories.security",
    "internet": "categories.internet",
    "repair": "categories.repair",
}

# Расширенная карта категорий с legacy текстами для обратной совместимости
# TASK 17 Этап A: Нормализация данных категорий
CATEGORY_DEFINITIONS = {
    "electricity": {
        "locale_key": "categories.electricity",
        "legacy_texts": ["Электрика"]
    },
    "plumbing": {
        "locale_key": "categories.plumbing",
        "legacy_texts": ["Сантехника"]
    },
    "heating": {
        "locale_key": "categories.heating",
        # HVAC — старое имя специализации, встречалось и как категория
        "legacy_texts": ["Отопление", "HVAC"]
    },
    "elevator": {
        "locale_key": "categories.elevator",
        "legacy_texts": ["Лифт", "Обслуживание"]
    },
    "cleaning": {
        "locale_key": "categories.cleaning",
        "legacy_texts": ["Уборка"]
    },
    "landscaping": {
        "locale_key": "categories.landscaping",
        "legacy_texts": ["Благоустройство"]
    },
    "security": {
        "locale_key": "categories.security",
        "legacy_texts": ["Безопасность", "Охрана"]
    },
    "internet": {
        "locale_key": "categories.internet",
        "legacy_texts": ["Интернет/ТВ", "Интернет", "internet_tv"]
    },
    # FS-04: ventilation/other/repair не в бот-меню (CATEGORY_KEYS), но входят в
    # канон для нормализации/отображения web-категорий и legacy-данных.
    "ventilation": {
        "locale_key": "categories.ventilation",
        "legacy_texts": ["Вентиляция"]
    },
    "other": {
        "locale_key": "categories.other",
        "legacy_texts": ["Другое"]
    },
    "repair": {
        "locale_key": "categories.repair",
        "legacy_texts": ["Ремонт", "Установка"]
    },
    # Служебная очередь InfraSafe: `alert.engineer_required` пишет RU-лейбл
    # (services/inbound_webhooks/mappings.py:ENGINEER_REQUIRED_CATEGORY). В каноне — чтобы
    # автодиспетчер раздавал и UI локализовал; в SELECTABLE не входит — человек
    # эту категорию не выбирает ни в одной форме.
    "engineering": {
        "locale_key": "categories.engineering",
        "legacy_texts": ["Инженерный разбор"]
    },
}

# List of internal category keys (bot category-selection keyboard — 9 keys)
CATEGORY_INTERNAL_KEYS = list(CATEGORY_KEYS.keys())

# FS-04: полный канонический набор EN-ключей (включает ventilation/other/repair,
# которых нет в бот-меню). Источник истины для нормализации/валидации категории
# на всех каналах записи (бот + web/API) и для миграции legacy RU-лейблов.
CANONICAL_CATEGORY_KEYS = list(CATEGORY_DEFINITIONS.keys())

# Служебные категории: в каноне (нормализация/отображение/диспетч), но не для
# выбора человеком.
_SERVICE_CATEGORY_KEYS = frozenset({"engineering"})

# Что человек может ВЫБРАТЬ (бот-клавиатуры, TWA, колл-центр, смена категории,
# picker в приёмке групп). Фронтовый `frontend/src/constants.ts:CATEGORIES`
# зеркалит этот список — менять парой.
SELECTABLE_CATEGORY_KEYS = [
    key for key in CANONICAL_CATEGORY_KEYS if key not in _SERVICE_CATEGORY_KEYS
]


# TASK 17 Этап A: Helper функции для работы с категориями

def get_category_display(category_key: str, language: str = "ru") -> str:
    """
    Получить локализованное отображаемое название категории по внутреннему ключу.
    
    Args:
        category_key: Внутренний ключ категории (например, "electricity", "plumbing")
        language: Язык интерфейса (ru/uz)
        
    Returns:
        Локализованное название категории или оригинальный ключ, если не найден
        
    Example:
        get_category_display("electricity", "ru") -> "Электрика"
        get_category_display("electricity", "uz") -> "Elektr"
    """
    if category_key in CATEGORY_DEFINITIONS:
        locale_key = CATEGORY_DEFINITIONS[category_key]["locale_key"]
        return get_text(locale_key, language=language)
    
    # Fallback: если ключ не найден, возвращаем оригинальный ключ
    logger.warning(f"Unknown category key: {category_key}, returning as-is")
    return category_key


def resolve_category_key(raw_value: str) -> str:
    """
    Разрешить значение категории (legacy текст или внутренний ключ) в внутренний ключ.
    
    Используется для обратной совместимости со старыми данными в БД,
    где категории могут храниться как русские строки.
    
    Args:
        raw_value: Значение из БД (может быть внутренний ключ или legacy текст)
        
    Returns:
        Внутренний ключ категории или оригинальное значение, если не найдено соответствие
        
    Example:
        resolve_category_key("Электрика") -> "electricity"
        resolve_category_key("electricity") -> "electricity"
        resolve_category_key("unknown") -> "unknown" (с предупреждением в логах)
    """
    # Если это уже канонический ключ (FS-04: полный набор, не только бот-меню)
    if raw_value in CATEGORY_DEFINITIONS:
        return raw_value
    
    # Ищем в legacy текстах
    for internal_key, definition in CATEGORY_DEFINITIONS.items():
        if raw_value in definition.get("legacy_texts", []):
            logger.info(f"Resolved legacy category '{raw_value}' to internal key '{internal_key}'")
            return internal_key
    
    # Если не найдено, логируем предупреждение и возвращаем оригинал
    logger.warning(f"Could not resolve category value '{raw_value}' to internal key, using as-is")
    return raw_value


# Urgency mapping: internal key -> locale key
URGENCY_KEYS = {
    "low": "urgency.low",
    "medium": "urgency.medium",
    "high": "urgency.high",
    "critical": "urgency.critical",
}

# List of internal urgency keys (for use in callbacks)
URGENCY_INTERNAL_KEYS = list(URGENCY_KEYS.keys())


# TASK 17: Helper функция для получения локализованного названия срочности
def get_urgency_display(urgency_key: str, language: str = "ru") -> str:
    """
    Получить локализованное отображаемое название срочности по внутреннему ключу.
    
    Args:
        urgency_key: Внутренний ключ срочности (low, medium, high, critical)
        language: Язык интерфейса (ru/uz)
        
    Returns:
        Локализованное название срочности или оригинальный ключ, если не найден
        
    Example:
        get_urgency_display("low", "ru") -> "Обычная"
        get_urgency_display("low", "uz") -> "Oddiy"
    """
    if urgency_key in URGENCY_KEYS:
        locale_key = URGENCY_KEYS[urgency_key]
        localized = get_text(locale_key, language=language)
        # Если ключ не найден, get_text вернёт сам ключ - используем fallback
        if localized == locale_key:
            logger.warning(f"Locale key '{locale_key}' not found for urgency '{urgency_key}', using original")
            return urgency_key
        return localized
    
    # Fallback: если ключ не найден, возвращаем оригинальный ключ
    logger.warning(f"Unknown urgency key: {urgency_key}, returning as-is")
    return urgency_key
