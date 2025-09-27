# Telegram notification service - migrated from monolith
# UK Management Bot - Notification Service

import asyncio
import logging
from typing import Optional, Dict, Any
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError

from models.notification import NotificationLog, NotificationType
from config import settings

logger = logging.getLogger(__name__)

class TelegramNotificationService:
    """Service for sending Telegram notifications"""

    def __init__(self):
        self.bot: Optional[Bot] = None

    async def initialize(self):
        """Initialize Telegram bot"""
        if settings.bot_token:
            self.bot = Bot(token=settings.bot_token)
        else:
            logger.warning("Telegram bot token not configured")

    async def close(self):
        """Close Telegram bot session"""
        if self.bot:
            await self.bot.session.close()

    async def send_telegram_notification(self, notification: NotificationLog) -> bool:
        """Send notification via Telegram"""
        if not self.bot:
            await self.initialize()

        if not self.bot:
            logger.error("Telegram bot not available")
            return False

        try:
            # Determine recipient
            telegram_id = notification.recipient_telegram_id
            if not telegram_id:
                logger.error(f"No Telegram ID for notification {notification.id}")
                return False

            # Format message based on type
            message_text = await self._format_message(notification)

            # Send message
            await self.bot.send_message(
                chat_id=telegram_id,
                text=message_text,
                parse_mode="Markdown" if self._should_use_markdown(notification) else None
            )

            # Send to channel if configured
            if settings.telegram_channel_id and notification.notification_type in self._get_channel_types():
                channel_message = await self._format_channel_message(notification)
                try:
                    await self.bot.send_message(
                        chat_id=settings.telegram_channel_id,
                        text=channel_message,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.warning(f"Failed to send to channel: {e}")

            logger.info(f"Telegram notification {notification.id} sent successfully")
            return True

        except TelegramForbiddenError:
            logger.warning(f"User {telegram_id} blocked the bot")
            notification.error_message = "User blocked bot"
            return False

        except TelegramBadRequest as e:
            logger.error(f"Telegram bad request for notification {notification.id}: {e}")
            notification.error_message = f"Bad request: {e}"
            return False

        except TelegramAPIError as e:
            logger.error(f"Telegram API error for notification {notification.id}: {e}")
            notification.error_message = f"API error: {e}"
            return False

        except Exception as e:
            logger.error(f"Unexpected error sending Telegram notification {notification.id}: {e}")
            notification.error_message = str(e)
            return False

    async def _format_message(self, notification: NotificationLog) -> str:
        """Format message based on notification type - migrated from monolith"""
        message = notification.message

        # Add title if present
        if notification.title:
            message = f"**{notification.title}**\\n\\n{message}"

        # Add context information
        if notification.request_number:
            message += f"\\n\\n📋 Заявка: #{notification.request_number}"

        return message

    async def _format_channel_message(self, notification: NotificationLog) -> str:
        """Format message for channel broadcast"""
        channel_message = f"🔔 {notification.notification_type.value}"

        if notification.recipient_telegram_id:
            channel_message += f" | user_id={notification.recipient_telegram_id}"

        if notification.request_number:
            channel_message += f" | #{notification.request_number}"

        # Add preview of message (first 100 chars)
        message_preview = notification.message[:100]
        if len(notification.message) > 100:
            message_preview += "..."

        channel_message += f"\\n{message_preview}"

        return channel_message

    def _should_use_markdown(self, notification: NotificationLog) -> bool:
        """Determine if message should use Markdown formatting"""
        # Use markdown for formatted notifications
        formatted_types = {
            NotificationType.DOCUMENT_REQUEST,
            NotificationType.VERIFICATION_REQUEST,
            NotificationType.VERIFICATION_APPROVED,
            NotificationType.VERIFICATION_REJECTED,
            NotificationType.DOCUMENT_APPROVED,
            NotificationType.DOCUMENT_REJECTED,
            NotificationType.ACCESS_GRANTED,
            NotificationType.ACCESS_REVOKED
        }
        return notification.notification_type in formatted_types

    def _get_channel_types(self) -> set:
        """Get notification types that should be sent to channel"""
        return {
            NotificationType.SHIFT_STARTED,
            NotificationType.SHIFT_ENDED,
            NotificationType.STATUS_CHANGED,
            NotificationType.SYSTEM
        }

    # ==== Migrated functions from monolith ====

    async def send_to_user(self, user_telegram_id: int, text: str) -> bool:
        """Direct user message - migrated from monolith"""
        if not self.bot:
            await self.initialize()

        if not self.bot:
            return False

        try:
            await self.bot.send_message(user_telegram_id, text)
            return True
        except Exception as e:
            logger.warning(f"Failed to send message to user {user_telegram_id}: {e}")
            return False

    async def send_to_channel(self, text: str) -> bool:
        """Channel broadcast - migrated from monolith"""
        if not self.bot or not settings.telegram_channel_id:
            return False

        try:
            await self.bot.send_message(settings.telegram_channel_id, text)
            return True
        except Exception as e:
            logger.warning(f"Failed to send message to channel: {e}")
            return False

    # ==== Message builders - migrated from monolith ====

    def build_shift_started_message(self, user_telegram_id: int, shift_data: Dict[str, Any], for_channel: bool = False) -> str:
        """Build shift started message - migrated from monolith"""
        started = shift_data.get('start_time', 'неизвестно')
        if for_channel:
            return f"🔔 Смена начата: user_id={user_telegram_id} в {started}"
        return f"✅ Ваша смена начата в {started}"

    def build_shift_ended_message(self, user_telegram_id: int, shift_data: Dict[str, Any], for_channel: bool = False) -> str:
        """Build shift ended message - migrated from monolith"""
        duration = shift_data.get('duration', 'неизвестно')
        ended = shift_data.get('end_time', 'неизвестно')
        if for_channel:
            return f"📤 Смена завершена: user_id={user_telegram_id} в {ended} (длительность {duration})"
        return f"✅ Смена завершена в {ended}. Длительность: {duration}"

    def build_document_request_message(self, user_data: Dict[str, Any], request_text: str, document_type: str = None, for_channel: bool = False) -> str:
        """Build document request message - migrated from monolith"""
        if for_channel:
            user_id = user_data.get('telegram_id', 'unknown')
            return f"📋 Запрос документов: user_id={user_id}, тип: {document_type}, запрос: {request_text}"

        # Get document name mapping
        document_names = {
            'passport': 'паспорт',
            'property_deed': 'свидетельство о собственности',
            'rental_agreement': 'договор аренды',
            'utility_bill': 'квитанцию ЖКХ',
            'other': 'дополнительные документы'
        }

        doc_name = document_names.get(document_type, document_type) if document_type else "дополнительные документы"

        message = f"📋 **Администратор запросил документы**\\n\\n"
        message += f"🔍 **Требуемый документ:** {doc_name}\\n\\n"
        message += f"💬 **Комментарий:**\\n{request_text}\\n\\n"
        message += f"📤 Пожалуйста, загрузите запрошенный документ в ближайшее время."

        return message

    def build_request_status_message(self, request_data: Dict[str, Any], old_status: str, new_status: str, for_user: bool = True) -> str:
        """Build request status change message - migrated from monolith"""
        request_number = request_data.get('request_number', 'неизвестно')
        category = request_data.get('category', '')
        address = request_data.get('address', '')

        if for_user:
            message = f"📌 Статус вашей заявки #{request_number} изменён: {old_status} → {new_status}\\n"
            message += f"Категория: {category}\\n"
            if address:
                address_short = address[:60] + '…' if len(address) > 60 else address
                message += f"Адрес: {address_short}"
        else:
            # For channel
            message = f"🔔 Заявка #{request_number}: {old_status} → {new_status}\\n"
            message += f"Категория: {category}"

        return message

    def build_role_switched_message(self, old_role: str, new_role: str, language: str = "ru") -> str:
        """Build role switch message - migrated from monolith"""
        # Simple implementation - could be enhanced with localization
        role_names = {
            "applicant": "заявитель",
            "executor": "исполнитель",
            "manager": "менеджер"
        }

        new_role_display = role_names.get(new_role, new_role)
        return f"Режим переключён: {new_role_display}"

    def build_action_denied_message(self, reason_key: str, language: str = "ru") -> str:
        """Build action denied message - migrated from monolith"""
        reasons = {
            "not_in_shift": "Действие отклонено: вы не в смене.",
            "permission_denied": "Действие отклонено: недостаточно прав.",
            "invalid_transition": "Действие отклонено: недопустимый переход статуса."
        }
        return reasons.get(reason_key, "Действие отклонено")