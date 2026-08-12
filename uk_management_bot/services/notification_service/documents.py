from sqlalchemy.orm import Session
from uk_management_bot.database.models.user import User
import logging

from uk_management_bot.services.notification_service.channel import (
    send_to_channel,
    send_to_user,
)

logger = logging.getLogger(__name__)


def build_document_request_message(user: User, request_text: str, document_type: str = None, for_channel: bool = False) -> str:
    """Формирует сообщение о запросе документов"""
    if for_channel:
        return f"📋 Запрос документов: user_id={user.telegram_id}, тип: {document_type}, запрос: {request_text}"
    
    # Получаем название типа документа
    document_names = {
        'passport': 'паспорт',
        'property_deed': 'свидетельство о собственности',
        'rental_agreement': 'договор аренды',
        'utility_bill': 'квитанцию ЖКХ',
        'other': 'дополнительные документы'
    }
    
    doc_name = document_names.get(document_type, document_type) if document_type else "дополнительные документы"
    
    message = "📋 **Администратор запросил документы**\n\n"
    message += f"🔍 **Требуемый документ:** {doc_name}\n\n"
    message += f"💬 **Комментарий:**\n{request_text}\n\n"
    message += "📤 Пожалуйста, загрузите запрошенный документ в ближайшее время."
    
    return message


async def async_notify_document_request(bot, db: Session, user: User, request_text: str, document_type: str = None) -> None:
    """Отправляет уведомление о запросе документов"""
    try:
        await send_to_user(bot, user.telegram_id, build_document_request_message(user, request_text, document_type, for_channel=False))
        await send_to_channel(bot, build_document_request_message(user, request_text, document_type, for_channel=True))
    except Exception as e:
        logger.warning(f"Ошибка async уведомления о запросе документов: {e}")


def build_multiple_documents_request_message(user: User, request_text: str, document_types: list, for_channel: bool = False) -> str:
    """Формирует сообщение о запросе множественных документов"""
    if for_channel:
        return f"📋 Запрос документов: user_id={user.telegram_id}, типы: {document_types}, запрос: {request_text}"
    
    # Получаем названия типов документов
    document_names = {
        'passport': 'паспорт',
        'property_deed': 'свидетельство о собственности',
        'rental_agreement': 'договор аренды',
        'utility_bill': 'квитанцию ЖКХ',
        'other': 'дополнительные документы'
    }
    
    doc_names = []
    for doc_type in document_types:
        doc_name = document_names.get(doc_type, doc_type)
        doc_names.append(doc_name)
    
    doc_list = ", ".join(doc_names)
    
    message = "📋 **Администратор запросил документы**\n\n"
    message += f"🔍 **Требуемые документы:**\n{doc_list}\n\n"
    message += f"💬 **Комментарий:**\n{request_text}\n\n"
    message += "📤 Пожалуйста, загрузите все запрошенные документы в ближайшее время."
    
    return message


async def async_notify_multiple_documents_request(bot, db: Session, user: User, request_text: str, document_types: list) -> None:
    """Отправляет уведомление о запросе множественных документов"""
    try:
        await send_to_user(bot, user.telegram_id, build_multiple_documents_request_message(user, request_text, document_types, for_channel=False))
        await send_to_channel(bot, build_multiple_documents_request_message(user, request_text, document_types, for_channel=True))
    except Exception as e:
        logger.warning(f"Ошибка async уведомления о запросе множественных документов: {e}")
