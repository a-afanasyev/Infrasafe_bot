import re
from typing import Optional
from uk_management_bot.utils.constants import MAX_ADDRESS_LENGTH, ADDRESS_TYPES, ADDRESS_TYPE_DISPLAYS

def validate_address(address: str) -> bool:
    """Валидация адреса"""
    if not address or not isinstance(address, str):
        return False
    
    # Проверяем длину
    if len(address.strip()) < 10:
        return False
    
    if len(address) > MAX_ADDRESS_LENGTH:
        return False
    
    # Проверяем на наличие недопустимых символов
    if re.search(r'[<>"\']', address):
        return False
    
    return True

def format_address(address: str) -> str:
    """Форматирование адреса"""
    if not address:
        return ""
    
    # Убираем лишние пробелы
    formatted = re.sub(r'\s+', ' ', address.strip())
    
    # Первая буква заглавная
    formatted = formatted.capitalize()
    
    return formatted

def get_address_type_display(address_type: str) -> str:
    """Получить отображаемое название типа адреса"""
    return ADDRESS_TYPE_DISPLAYS.get(address_type, address_type)

def get_available_addresses(user) -> dict:
    """Получить доступные адреса пользователя"""
    available = {}
    
    if user.home_address and validate_address(user.home_address):
        available['home'] = user.home_address
    
    if user.apartment_address and validate_address(user.apartment_address):
        available['apartment'] = user.apartment_address
    
    if user.yard_address and validate_address(user.yard_address):
        available['yard'] = user.yard_address
    
    return available

def get_address_type_from_display(display_text: str) -> Optional[str]:
    """Получить тип адреса из отображаемого текста"""
    for addr_type, display in ADDRESS_TYPE_DISPLAYS.items():
        if display == display_text:
            return addr_type
    
    return None

def is_valid_address_type(address_type: str) -> bool:
    """Проверить, является ли тип адреса допустимым"""
    return address_type in ADDRESS_TYPES

# Новые утилиты для Task 2.2.4

def validate_address_format(address: str) -> bool:
    """
    Валидация формата адреса (синхронная версия)
    
    Args:
        address: Адрес для валидации
        
    Returns:
        bool: True если формат адреса корректный
    """
    try:
        if not address or len(address.strip()) < 10:
            return False
        
        # Проверка на наличие цифр (номер дома/квартиры)
        if not re.search(r'\d', address):
            return False
        
        # Проверка на наличие ключевых слов
        address_lower = address.lower()
        valid_keywords = ['улица', 'дом', 'квартира', 'двор', 'проспект', 'переулок']
        
        return any(keyword in address_lower for keyword in valid_keywords)
        
    except Exception:
        return False

def sanitize_address(address: str) -> str:
    """
    Очистка адреса от лишних символов
    
    Args:
        address: Исходный адрес
        
    Returns:
        str: Очищенный адрес
    """
    try:
        # Удаление лишних пробелов
        address = ' '.join(address.split())
        
        # Удаление специальных символов в начале и конце
        address = address.strip('.,!?')
        
        # Приведение к правильному регистру
        address = address.capitalize()
        
        return address
        
    except Exception:
        return address

def format_address_for_display(address: str, address_type: str) -> str:
    """
    Форматирование адреса для отображения
    
    Args:
        address: Адрес
        address_type: Тип адреса
        
    Returns:
        str: Отформатированный адрес
    """
    try:
        # Получение отображения типа адреса
        type_display = ADDRESS_TYPE_DISPLAYS.get(address_type, address_type)
        
        # Форматирование адреса
        formatted_address = f"{type_display}: {address}"
        
        return formatted_address
        
    except Exception:
        return address 