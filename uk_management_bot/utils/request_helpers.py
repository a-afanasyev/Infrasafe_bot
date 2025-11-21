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
    TASK 17 Этап A: Использует resolve_category_key и get_category_display для нормализации категорий.
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
    from uk_management_bot.keyboards.requests import resolve_category_key, get_category_display

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

    # TASK 17 Этап A: Разрешаем категорию из БД (может быть legacy текст) в внутренний ключ
    category_key = resolve_category_key(request.category)
    category_display = get_category_display(category_key, language=language)

    # TASK 17 Этап C: Локализуем статус
    from uk_management_bot.keyboards.requests import get_status_display
    status_display = get_status_display(request.status, language=language)

    # Build message with localized labels
    message_text = f"📋 {labels['request']} #{request.request_number}\n\n"
    message_text += f"{labels['category']} {category_display}\n"
    message_text += f"{labels['status']} {status_display}\n"
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

def get_status_icon(status: str) -> str:
    """
    Get emoji icon for request status

    TASK 17 Issue #5: Helper for status icons in list views

    Args:
        status: Request status (Russian text)

    Returns:
        Emoji icon for the status
    """
    status_icons = {
        "Новая": "🆕",
        "В работе": "🔧",
        "Выполнена": "✅",
        "Отменена": "❌",
        "Уточнение": "💬",
        "Закуп": "💰",
        "Исполнено": "✅",
        "Принято": "👍"
    }
    return status_icons.get(status, "📋")


def format_requests_list_header(
    total_requests: int,
    current_page: int,
    total_pages: int,
    status_filter: str,
    role: str,
    language: str
) -> str:
    """
    Format the header for requests list page with localization

    TASK 17 Issue #5: Localized list header for all languages

    Args:
        total_requests: Total number of requests
        current_page: Current page number
        total_pages: Total number of pages
        status_filter: Filter status (all/active/archive)
        role: User's active role (executor/applicant)
        language: Language code (ru/uz)

    Returns:
        Formatted header text with localized title
    """
    from uk_management_bot.utils.helpers import get_text

    page_indicator = get_text('requests.page_indicator', language=language)

    if role == "executor":
        title = get_text('requests.assigned_requests_title', language=language)
        prompt = get_text('requests.select_request_prompt', language=language)
        return f"📋 <b>{title}</b> ({page_indicator} {current_page}/{total_pages})\n\n{prompt}\n\n"
    else:
        if status_filter == "active":
            title = get_text('requests.active_requests_title', language=language)
        elif status_filter == "archive":
            title = get_text('requests.archive_title', language=language)
        else:
            title = get_text('requests.all_filter', language=language)

        return f"📋 <b>{title}</b> ({page_indicator} {current_page}/{total_pages})\n\n"


def format_request_list_item(
    request,
    index: int,
    language: str,
    show_details: bool = True
) -> str:
    """
    Format a single request list item with localization

    TASK 17 Issue #5: Localized list item for all languages
    TASK 17 Этап A: Использует resolve_category_key и get_category_display для нормализации категорий.

    Args:
        request: Request model instance
        index: Item number in list (1-based)
        language: Language code (ru/uz)
        show_details: Whether to show detailed info (address, date, notes)

    Returns:
        Formatted list item text
    """
    from uk_management_bot.utils.helpers import get_text
    from uk_management_bot.keyboards.requests import resolve_category_key, get_category_display

    # TASK 17 Этап A: Разрешаем категорию из БД в внутренний ключ и получаем локализованное отображение
    category_key = resolve_category_key(request.category)
    category_display = get_category_display(category_key, language=language)

    # TASK 17 Этап C: Локализуем статус
    from uk_management_bot.keyboards.requests import get_status_display
    status_display = get_status_display(request.status, language=language)

    icon = get_status_icon(request.status)
    item_text = f"{index}. {icon} #{request.request_number} - {category_display} - {status_display}\n"

    if show_details:
        # Get localized labels
        address_label = get_text('requests.address_label', language=language)
        created_label = get_text('requests.created_label', language=language)

        # Format address (truncate if too long)
        address = request.address
        if len(address) > 60:
            address = address[:60] + "…"

        item_text += f"   {address_label} {address}\n"
        item_text += f"   {created_label} {request.created_at.strftime('%d.%m.%Y')}\n"

        # Handle special statuses with notes
        if request.status == "Отменена" and request.notes:
            reason_label = get_text('requests.cancellation_reason_label', language=language)
            notes = request.notes[:100] + "..." if len(request.notes) > 100 else request.notes
            item_text += f"   {reason_label} {notes}\n"

        elif request.status == "Уточнение" and request.notes:
            clarification_label = get_text('requests.clarification_label', language=language)
            # Show last 2 messages
            notes_lines = request.notes.strip().split('\n')
            last_messages = [line for line in notes_lines[-2:] if line.strip()]
            if last_messages:
                preview = '\n'.join(last_messages)
                if len(preview) > 80:
                    preview = preview[:77] + '...'
                item_text += f"   {clarification_label} {preview}\n"

        item_text += "\n"

    return item_text


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