from sqlalchemy.orm import Session
from uk_management_bot.database.models.user import User
import logging

from uk_management_bot.services.notification_service.channel import (
    send_to_channel,
    send_to_user,
)
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)


def _user_lang(user: User) -> str:
    """Язык пользователя (как в NotificationService._get_user_lang)."""
    return getattr(user, 'language', None) or 'ru'


def _document_name(document_type: str, language: str) -> str:
    """BUG-146: локализованное название типа документа из document_types.*
    (как в send_document_approved_notification), вместо RU-хардкода."""
    if not document_type:
        return get_text("document_types.other", language=language)
    return get_text(f"document_types.{document_type}", language=language)


def build_document_request_message(user: User, request_text: str, document_type: str = None, for_channel: bool = False) -> str:
    """Формирует сообщение о запросе документов"""
    if for_channel:
        return f"📋 Запрос документов: user_id={user.telegram_id}, тип: {document_type}, запрос: {request_text}"

    lang = _user_lang(user)
    doc_name = _document_name(document_type, lang)

    # BUG-146: без markdown-разметки — отправка идёт raw (parse_mode нет).
    message = "📋 Администратор запросил документы\n\n"
    message += f"🔍 Требуемый документ: {doc_name}\n\n"
    message += f"💬 Комментарий:\n{request_text}\n\n"
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

    lang = _user_lang(user)
    doc_list = ", ".join(_document_name(doc_type, lang) for doc_type in document_types)

    # BUG-146: без markdown-разметки — отправка идёт raw (parse_mode нет).
    message = "📋 Администратор запросил документы\n\n"
    message += f"🔍 Требуемые документы:\n{doc_list}\n\n"
    message += f"💬 Комментарий:\n{request_text}\n\n"
    message += "📤 Пожалуйста, загрузите все запрошенные документы в ближайшее время."

    return message


async def async_notify_multiple_documents_request(bot, db: Session, user: User, request_text: str, document_types: list) -> None:
    """Отправляет уведомление о запросе множественных документов"""
    try:
        await send_to_user(bot, user.telegram_id, build_multiple_documents_request_message(user, request_text, document_types, for_channel=False))
        await send_to_channel(bot, build_multiple_documents_request_message(user, request_text, document_types, for_channel=True))
    except Exception as e:
        logger.warning(f"Ошибка async уведомления о запросе множественных документов: {e}")
