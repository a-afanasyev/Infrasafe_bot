# Template service for notification formatting
# UK Management Bot - Notification Service

import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from models.notification import NotificationTemplate, NotificationType, NotificationChannel
from schemas.notification import (
    NotificationTemplateCreate,
    NotificationTemplateResponse
)

logger = logging.getLogger(__name__)

class TemplateService:
    """Service for managing notification templates"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_template(self, template_data: NotificationTemplateCreate) -> NotificationTemplateResponse:
        """Create a new notification template"""
        template = NotificationTemplate(
            template_key=template_data.template_key,
            notification_type=template_data.notification_type,
            channel=template_data.channel,
            language=template_data.language,
            title_template=template_data.title_template,
            message_template=template_data.message_template,
            priority=template_data.priority,
            is_active=template_data.is_active
        )

        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)

        return NotificationTemplateResponse.from_orm(template)

    async def get_template(
        self,
        notification_type: NotificationType,
        channel: NotificationChannel,
        language: str = "ru"
    ) -> Optional[NotificationTemplateResponse]:
        """Get template for specific notification type, channel and language"""

        stmt = select(NotificationTemplate).where(
            and_(
                NotificationTemplate.notification_type == notification_type,
                NotificationTemplate.channel == channel,
                NotificationTemplate.language == language,
                NotificationTemplate.is_active == True
            )
        )

        result = await self.db.execute(stmt)
        template = result.scalar_one_or_none()

        if template:
            return NotificationTemplateResponse.from_orm(template)

        # Fallback to default language if not found
        if language != "ru":
            return await self.get_template(notification_type, channel, "ru")

        return None

    async def get_all_templates(self) -> List[NotificationTemplateResponse]:
        """Get all notification templates"""
        stmt = select(NotificationTemplate).order_by(
            NotificationTemplate.notification_type,
            NotificationTemplate.channel,
            NotificationTemplate.language
        )

        result = await self.db.execute(stmt)
        templates = result.scalars().all()

        return [NotificationTemplateResponse.from_orm(template) for template in templates]

    async def update_template(
        self,
        template_id: int,
        template_data: NotificationTemplateCreate
    ) -> Optional[NotificationTemplateResponse]:
        """Update existing template"""

        stmt = select(NotificationTemplate).where(NotificationTemplate.id == template_id)
        result = await self.db.execute(stmt)
        template = result.scalar_one_or_none()

        if not template:
            return None

        template.template_key = template_data.template_key
        template.notification_type = template_data.notification_type
        template.channel = template_data.channel
        template.language = template_data.language
        template.title_template = template_data.title_template
        template.message_template = template_data.message_template
        template.priority = template_data.priority
        template.is_active = template_data.is_active

        await self.db.commit()
        await self.db.refresh(template)

        return NotificationTemplateResponse.from_orm(template)

    async def delete_template(self, template_id: int) -> bool:
        """Delete template"""
        stmt = select(NotificationTemplate).where(NotificationTemplate.id == template_id)
        result = await self.db.execute(stmt)
        template = result.scalar_one_or_none()

        if not template:
            return False

        await self.db.delete(template)
        await self.db.commit()
        return True

    async def render_template(
        self,
        template: NotificationTemplateResponse,
        variables: Dict[str, Any]
    ) -> Dict[str, str]:
        """Render template with variables"""
        try:
            title = ""
            if template.title_template:
                title = template.title_template.format(**variables)

            message = template.message_template.format(**variables)

            return {
                "title": title,
                "message": message
            }

        except KeyError as e:
            logger.error(f"Missing template variable: {e}")
            raise ValueError(f"Missing template variable: {e}")

        except Exception as e:
            logger.error(f"Error rendering template {template.template_key}: {e}")
            raise ValueError(f"Error rendering template: {e}")

    async def initialize_default_templates(self):
        """Initialize default templates for common notification types"""
        default_templates = [
            # Shift notifications
            {
                "template_key": "shift_started_user",
                "notification_type": NotificationType.SHIFT_STARTED,
                "channel": NotificationChannel.TELEGRAM,
                "language": "ru",
                "message_template": "✅ Ваша смена начата в {start_time}"
            },
            {
                "template_key": "shift_started_channel",
                "notification_type": NotificationType.SHIFT_STARTED,
                "channel": NotificationChannel.TELEGRAM,
                "language": "ru",
                "message_template": "🔔 Смена начата: user_id={user_id} в {start_time}"
            },
            {
                "template_key": "shift_ended_user",
                "notification_type": NotificationType.SHIFT_ENDED,
                "channel": NotificationChannel.TELEGRAM,
                "language": "ru",
                "message_template": "✅ Смена завершена в {end_time}. Длительность: {duration}"
            },
            {
                "template_key": "shift_ended_channel",
                "notification_type": NotificationType.SHIFT_ENDED,
                "channel": NotificationChannel.TELEGRAM,
                "language": "ru",
                "message_template": "📤 Смена завершена: user_id={user_id} в {end_time} (длительность {duration})"
            },

            # Request status notifications
            {
                "template_key": "status_changed_user",
                "notification_type": NotificationType.STATUS_CHANGED,
                "channel": NotificationChannel.TELEGRAM,
                "language": "ru",
                "message_template": "📌 Статус вашей заявки #{request_number} изменён: {old_status} → {new_status}\\nКатегория: {category}\\nАдрес: {address}"
            },
            {
                "template_key": "status_changed_channel",
                "notification_type": NotificationType.STATUS_CHANGED,
                "channel": NotificationChannel.TELEGRAM,
                "language": "ru",
                "message_template": "🔔 Заявка #{request_number}: {old_status} → {new_status}\\nКатегория: {category}"
            },

            # Document requests
            {
                "template_key": "document_request",
                "notification_type": NotificationType.DOCUMENT_REQUEST,
                "channel": NotificationChannel.TELEGRAM,
                "language": "ru",
                "title_template": "📋 Администратор запросил документы",
                "message_template": "🔍 **Требуемый документ:** {document_name}\\n\\n💬 **Комментарий:**\\n{comment}\\n\\n📤 Пожалуйста, загрузите запрошенный документ в ближайшее время."
            },

            # Verification notifications
            {
                "template_key": "verification_approved",
                "notification_type": NotificationType.VERIFICATION_APPROVED,
                "channel": NotificationChannel.TELEGRAM,
                "language": "ru",
                "title_template": "✅ Верификация одобрена!",
                "message_template": "Ваша учетная запись успешно верифицирована администратором.\\n\\nТеперь вы можете полноценно использовать все функции системы."
            },
            {
                "template_key": "verification_rejected",
                "notification_type": NotificationType.VERIFICATION_REJECTED,
                "channel": NotificationChannel.TELEGRAM,
                "language": "ru",
                "title_template": "❌ Верификация отклонена",
                "message_template": "К сожалению, ваша учетная запись не прошла верификацию.\\n\\nПожалуйста, свяжитесь с администратором для уточнения деталей."
            },

            # Access control
            {
                "template_key": "access_granted",
                "notification_type": NotificationType.ACCESS_GRANTED,
                "channel": NotificationChannel.TELEGRAM,
                "language": "ru",
                "title_template": "🔑 Права доступа предоставлены",
                "message_template": "Вам предоставлены права на подачу заявок для {access_type}.\\n\\n📍 **Детали:** {details}"
            },
            {
                "template_key": "access_revoked",
                "notification_type": NotificationType.ACCESS_REVOKED,
                "channel": NotificationChannel.TELEGRAM,
                "language": "ru",
                "title_template": "🚫 Права доступа отозваны",
                "message_template": "Ваши права на подачу заявок для {access_type} были отозваны.\\n\\n💬 **Причина:** {reason}"
            },

            # System notifications
            {
                "template_key": "system_notification",
                "notification_type": NotificationType.SYSTEM,
                "channel": NotificationChannel.TELEGRAM,
                "language": "ru",
                "message_template": "{message}"
            }
        ]

        for template_data in default_templates:
            # Check if template already exists
            existing_stmt = select(NotificationTemplate).where(
                NotificationTemplate.template_key == template_data["template_key"]
            )
            result = await self.db.execute(existing_stmt)
            existing = result.scalar_one_or_none()

            if not existing:
                template = NotificationTemplate(**template_data)
                self.db.add(template)

        await self.db.commit()
        logger.info(f"Initialized {len(default_templates)} default notification templates")