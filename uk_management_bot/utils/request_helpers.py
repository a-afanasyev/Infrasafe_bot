"""
Утилиты для работы с номерами заявок в новом формате
"""
import re
import logging
from typing import Optional
from uk_management_bot.services.request_number_service import RequestNumberService

logger = logging.getLogger(__name__)

class RequestCallbackHelper:
    """Утилиты для работы с callback data содержащими номера заявок"""
    
    @staticmethod
    def extract_request_number_from_callback(callback_data: str, prefix: str) -> Optional[str]:
        """
        Извлекает номер заявки из callback data
        
        Args:
            callback_data: Callback data (например: "view_250917-001")
            prefix: Префикс для удаления (например: "view_")
            
        Returns:
            Номер заявки или None если формат неверный
        """
        if not callback_data.startswith(prefix):
            return None
        
        request_number = callback_data.replace(prefix, "")
        
        # Проверяем корректность формата номера
        if RequestNumberService.validate_request_number_format(request_number):
            return request_number
        
        return None
    
    @staticmethod
    def create_callback_data_with_request_number(prefix: str, request_number: str) -> str:
        """
        Создает callback data с номером заявки
        
        Args:
            prefix: Префикс (например: "view_")
            request_number: Номер заявки
            
        Returns:
            Callback data (например: "view_250917-001")
        """
        if not RequestNumberService.validate_request_number_format(request_number):
            logger.warning(f"Invalid request number format: {request_number}")
        
        return f"{prefix}{request_number}"
    
    @staticmethod
    def is_request_number_callback(callback_data: str, prefix: str) -> bool:
        """
        Проверяет, содержит ли callback data корректный номер заявки
        
        Args:
            callback_data: Callback data для проверки
            prefix: Ожидаемый префикс
            
        Returns:
            True если callback data содержит корректный номер заявки
        """
        request_number = RequestCallbackHelper.extract_request_number_from_callback(
            callback_data, prefix
        )
        return request_number is not None

def format_request_for_list(request, include_number=True):
    """
    Форматирует заявку для отображения в списке
    
    Args:
        request: Объект заявки
        include_number: Включать ли номер заявки
        
    Returns:
        Отформатированная строка
    """
    if include_number:
        number_display = request.format_number_for_display()
        return f"{number_display}\n📍 {request.address}\n🏷️ {request.category}\n📊 {request.status}"
    else:
        return f"📍 {request.address}\n🏷️ {request.category}\n📊 {request.status}"

def format_request_details(request, language="ru"):
    """
    Форматирует детали заявки для отображения

    ОБНОВЛЕНО: Поддержка отображения информации о квартире из справочника

    Args:
        request: Объект заявки
        language: Язык интерфейса

    Returns:
        Детальная информация о заявке
    """
    # Форматируем номер заявки
    number_display = request.format_number_for_display()

    details = f"📋 Заявка {number_display}\n\n"
    details += f"🏷️ Категория: {request.category}\n"
    details += f"📊 Статус: {request.status}\n"

    # НОВОЕ: Отображение адреса с индикатором источника
    if hasattr(request, 'apartment_obj') and request.apartment_obj:
        # Заявка привязана к квартире из справочника
        from uk_management_bot.services.address_service import AddressService
        formatted_address = AddressService.format_apartment_address(request.apartment_obj)
        details += f"📍 Адрес: {formatted_address} 🏢\n"  # Иконка здания = из справочника

        # Дополнительная информация о квартире
        apartment = request.apartment_obj
        apartment_details = []
        if apartment.entrance:
            apartment_details.append(f"Подъезд: {apartment.entrance}")
        if apartment.floor:
            apartment_details.append(f"Этаж: {apartment.floor}")
        if apartment.rooms_count:
            apartment_details.append(f"Комнат: {apartment.rooms_count}")
        if apartment.area:
            apartment_details.append(f"Площадь: {apartment.area} м²")

        for i, detail in enumerate(apartment_details):
            prefix = "   └" if i == len(apartment_details) - 1 else "   ├"
            details += f"{prefix} {detail}\n"
    else:
        # Legacy: текстовый адрес
        details += f"📍 Адрес: {request.address}\n"

        # Legacy поле apartment (если есть)
        if request.apartment:
            details += f"🏠 Квартира: {request.apartment}\n"

    details += f"📝 Описание: {request.description}\n"
    details += f"⚡ Срочность: {request.urgency}\n"

    details += f"🕐 Создана: {request.created_at.strftime('%d.%m.%Y %H:%M')}\n"

    if request.executor:
        executor_name = request.executor.first_name or request.executor.username or "Не указан"
        details += f"👤 Исполнитель: {executor_name}\n"

    if request.completed_at:
        details += f"✅ Завершена: {request.completed_at.strftime('%d.%m.%Y %H:%M')}\n"

    return details

def validate_callback_request_number(callback_data: str, expected_prefix: str) -> Optional[str]:
    """
    Валидирует callback data и возвращает номер заявки
    
    Args:
        callback_data: Callback data для валидации
        expected_prefix: Ожидаемый префикс
        
    Returns:
        Номер заявки или None если валидация не прошла
    """
    try:
        return RequestCallbackHelper.extract_request_number_from_callback(
            callback_data, expected_prefix
        )
    except Exception as e:
        logger.error(f"Error validating callback data {callback_data}: {e}")
        return None