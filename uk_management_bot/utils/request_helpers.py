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

def format_request_details(request, language="ru", show_executor=True, active_role=None, db_session=None):
    """
    Форматирует детали заявки для отображения с полной локализацией

    TASK 17 Issue #4: Полностью локализованная версия с поддержкой всех языков.
    Все метки используют get_text() для локализации.

    Args:
        request: Объект заявки
        language: Язык интерфейса (ru/uz)
        show_executor: Показывать ли информацию об исполнителе
        active_role: Активная роль пользователя (для условной логики)
        db_session: Сессия БД (для запроса исполнителя если нужно)

    Returns:
        Детальная информация о заявке с локализованными метками
    """
    from uk_management_bot.utils.helpers import get_text

    # Get localized labels
    labels = {
        'request': get_text('requests.request_label', language=language),
        'category': get_text('requests.category_label', language=language),
        'status': get_text('commons.status_label', language=language),
        'address': get_text('requests.address_label', language=language),
        'description': get_text('requests.description_label', language=language),
        'urgency': get_text('requests.urgency_label', language=language),
        'apartment': get_text('requests.apartment_label', language=language),
        'created': get_text('requests.created_label', language=language),
        'updated': get_text('requests.updated_label', language=language),
        'executor': get_text('requests.executor_label', language=language),
        'media_count': get_text('requests.media_count_label', language=language),
    }

    # Build message with localized labels
    message_text = f"📋 {labels['request']} #{request.request_number}\n\n"
    message_text += f"{labels['category']} {request.category}\n"
    message_text += f"{labels['status']} {request.status}\n"
    message_text += f"{labels['address']} {request.address}\n"
    message_text += f"{labels['description']} {request.description}\n"
    message_text += f"{labels['urgency']} {request.urgency}\n"

    if request.apartment:
        message_text += f"{labels['apartment']} {request.apartment}\n"

    message_text += f"{labels['created']} {request.created_at.strftime('%d.%m.%Y %H:%M')}\n"

    if request.updated_at:
        message_text += f"{labels['updated']} {request.updated_at.strftime('%d.%m.%Y %H:%M')}\n"

    # Add executor info if needed
    if show_executor and active_role != "executor" and request.executor_id:
        if db_session:
            from uk_management_bot.database.models.user import User
            executor = db_session.query(User).filter(User.id == request.executor_id).first()
            if executor:
                executor_name = f"{executor.first_name or ''} {executor.last_name or ''}".strip()
                if executor_name:
                    message_text += f"{labels['executor']} {executor_name}\n"

    # Add media files count if present
    if hasattr(request, 'media_files') and request.media_files:
        try:
            import json
            media_files = json.loads(request.media_files) if isinstance(request.media_files, str) else request.media_files
            media_count = len(media_files) if media_files else 0
            if media_count > 0:
                message_text += f"\n📎 {labels['media_count']} {media_count}\n"
        except (json.JSONDecodeError, TypeError):
            pass

    return message_text

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