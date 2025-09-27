# Core notification service - migrated from monolith
# UK Management Bot - Notification Service

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, func
from sqlalchemy.orm import selectinload

from models.notification import (
    NotificationLog,
    NotificationTemplate,
    NotificationSubscription,
    NotificationStatus,
    NotificationType,
    NotificationChannel
)
from schemas.notification import (
    NotificationCreate,
    NotificationResponse,
    NotificationBatch,
    NotificationStats,
    NotificationQuery,
    NotificationStatusUpdate
)
from services.telegram_service import TelegramNotificationService
from services.template_service import TemplateService
from services.delivery_pipeline import ProductionDeliveryPipeline, DeliveryPriority
from config import settings

logger = logging.getLogger(__name__)

class NotificationService:
    """Core service for managing notifications"""

    def __init__(self, db: AsyncSession, delivery_pipeline: ProductionDeliveryPipeline = None):
        self.db = db
        self.telegram_service = TelegramNotificationService()
        self.template_service = TemplateService(db)
        self.delivery_pipeline = delivery_pipeline

    async def send_notification(self, notification_data: NotificationCreate) -> NotificationResponse:
        """Send a single notification"""
        try:
            # Create notification log entry
            notification_log = NotificationLog(
                notification_type=notification_data.notification_type,
                channel=notification_data.channel,
                recipient_id=notification_data.recipient_id,
                recipient_telegram_id=notification_data.recipient_telegram_id,
                recipient_email=notification_data.recipient_email,
                recipient_phone=notification_data.recipient_phone,
                title=notification_data.title,
                message=notification_data.message,
                message_data=notification_data.message_data,
                request_number=notification_data.request_number,
                service_origin=notification_data.service_origin,
                correlation_id=notification_data.correlation_id,
                language=notification_data.language,
                priority=notification_data.priority,
                expires_at=notification_data.expires_at,
                status=NotificationStatus.PENDING
            )

            self.db.add(notification_log)
            await self.db.commit()
            await self.db.refresh(notification_log)

            # Use production delivery pipeline if available
            if self.delivery_pipeline:
                # Determine priority based on notification type and priority
                priority = self._get_delivery_priority(notification_data)

                # Enqueue for production delivery
                enqueued = await self.delivery_pipeline.enqueue_notification(
                    notification_log.id,
                    priority
                )

                if enqueued:
                    notification_log.status = NotificationStatus.QUEUED
                else:
                    # Fallback to direct delivery
                    success = await self._send_via_channel(notification_log)
                    notification_log.status = NotificationStatus.SENT if success else NotificationStatus.FAILED
                    notification_log.sent_at = datetime.utcnow() if success else None
                    notification_log.failed_at = None if success else datetime.utcnow()
            else:
                # Direct delivery (development/fallback mode)
                success = await self._send_via_channel(notification_log)
                notification_log.status = NotificationStatus.SENT if success else NotificationStatus.FAILED
                notification_log.sent_at = datetime.utcnow() if success else None
                notification_log.failed_at = None if success else datetime.utcnow()

            await self.db.commit()
            await self.db.refresh(notification_log)

            return NotificationResponse.from_orm(notification_log)

        except Exception as e:
            logger.error(f"Error sending notification: {e}")
            # Update status to failed if we have the record
            if 'notification_log' in locals():
                notification_log.status = NotificationStatus.FAILED
                notification_log.error_message = str(e)
                notification_log.failed_at = datetime.utcnow()
                await self.db.commit()

            raise

    async def send_batch(self, batch: NotificationBatch) -> List[NotificationResponse]:
        """Send multiple notifications in batch"""
        results = []

        # Process in smaller batches to avoid overwhelming services
        batch_size = min(settings.batch_size, len(batch.notifications))

        for i in range(0, len(batch.notifications), batch_size):
            chunk = batch.notifications[i:i + batch_size]

            # Send chunk concurrently
            tasks = [self.send_notification(notif) for notif in chunk]
            chunk_results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in chunk_results:
                if isinstance(result, Exception):
                    logger.error(f"Batch notification failed: {result}")
                    # Create failed notification record
                    failed_notif = NotificationResponse(
                        id=0,
                        notification_type=NotificationType.SYSTEM,
                        channel=NotificationChannel.TELEGRAM,
                        status=NotificationStatus.FAILED,
                        message="Batch processing failed",
                        error_message=str(result),
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                        retry_count=0,
                        language="ru",
                        priority=1
                    )
                    results.append(failed_notif)
                else:
                    results.append(result)

            # Small delay between batches to prevent rate limiting
            if i + batch_size < len(batch.notifications):
                await asyncio.sleep(0.1)

        return results

    async def _send_via_channel(self, notification: NotificationLog) -> bool:
        """Send notification via the specified channel"""
        try:
            if notification.channel == NotificationChannel.TELEGRAM:
                return await self.telegram_service.send_telegram_notification(notification)
            elif notification.channel == NotificationChannel.EMAIL:
                # Email service integration (placeholder)
                logger.info(f"Email notifications not yet implemented for notification {notification.id}")
                return False
            elif notification.channel == NotificationChannel.SMS:
                # SMS service integration (placeholder)
                logger.info(f"SMS notifications not yet implemented for notification {notification.id}")
                return False
            else:
                logger.error(f"Unknown notification channel: {notification.channel}")
                return False

        except Exception as e:
            logger.error(f"Error sending via {notification.channel}: {e}")
            notification.error_message = str(e)
            return False

    async def get_notifications(self, query: NotificationQuery) -> List[NotificationResponse]:
        """Get notifications with filtering"""
        stmt = select(NotificationLog)

        # Apply filters
        if query.status:
            stmt = stmt.where(NotificationLog.status == query.status)
        if query.notification_type:
            stmt = stmt.where(NotificationLog.notification_type == query.notification_type)
        if query.channel:
            stmt = stmt.where(NotificationLog.channel == query.channel)
        if query.recipient_id:
            stmt = stmt.where(NotificationLog.recipient_id == query.recipient_id)
        if query.request_number:
            stmt = stmt.where(NotificationLog.request_number == query.request_number)
        if query.service_origin:
            stmt = stmt.where(NotificationLog.service_origin == query.service_origin)
        if query.correlation_id:
            stmt = stmt.where(NotificationLog.correlation_id == query.correlation_id)
        if query.created_after:
            stmt = stmt.where(NotificationLog.created_at >= query.created_after)
        if query.created_before:
            stmt = stmt.where(NotificationLog.created_at <= query.created_before)

        # Apply pagination
        stmt = stmt.offset(query.offset).limit(query.limit)
        stmt = stmt.order_by(NotificationLog.created_at.desc())

        result = await self.db.execute(stmt)
        notifications = result.scalars().all()

        return [NotificationResponse.from_orm(notif) for notif in notifications]

    async def get_notification_by_id(self, notification_id: int) -> Optional[NotificationResponse]:
        """Get single notification by ID"""
        stmt = select(NotificationLog).where(NotificationLog.id == notification_id)
        result = await self.db.execute(stmt)
        notification = result.scalar_one_or_none()

        if notification:
            return NotificationResponse.from_orm(notification)
        return None

    async def update_notification_status(self, notification_id: int, status_update: NotificationStatusUpdate) -> Optional[NotificationResponse]:
        """Update notification status"""
        stmt = select(NotificationLog).where(NotificationLog.id == notification_id)
        result = await self.db.execute(stmt)
        notification = result.scalar_one_or_none()

        if not notification:
            return None

        # Update fields
        notification.status = status_update.status
        if status_update.error_message:
            notification.error_message = status_update.error_message
        if status_update.delivered_at:
            notification.delivered_at = status_update.delivered_at
        if status_update.retry_count is not None:
            notification.retry_count = status_update.retry_count

        # Update status-specific timestamps
        if status_update.status == NotificationStatus.SENT:
            notification.sent_at = datetime.utcnow()
        elif status_update.status == NotificationStatus.DELIVERED:
            notification.delivered_at = datetime.utcnow()
        elif status_update.status == NotificationStatus.FAILED:
            notification.failed_at = datetime.utcnow()

        notification.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(notification)

        return NotificationResponse.from_orm(notification)

    async def retry_failed_notifications(self) -> int:
        """Retry failed notifications that are within retry limits"""
        retry_limit = settings.max_retry_attempts

        # Find notifications to retry
        stmt = select(NotificationLog).where(
            and_(
                NotificationLog.status == NotificationStatus.FAILED,
                NotificationLog.retry_count < retry_limit,
                NotificationLog.created_at >= datetime.utcnow() - timedelta(hours=24)  # Only retry recent failures
            )
        )

        result = await self.db.execute(stmt)
        failed_notifications = result.scalars().all()

        retry_count = 0
        for notification in failed_notifications:
            try:
                # Update status to retrying
                notification.status = NotificationStatus.RETRYING
                notification.retry_count += 1
                await self.db.commit()

                # Attempt to send
                success = await self._send_via_channel(notification)

                if success:
                    notification.status = NotificationStatus.SENT
                    notification.sent_at = datetime.utcnow()
                    retry_count += 1
                else:
                    notification.status = NotificationStatus.FAILED
                    notification.failed_at = datetime.utcnow()

                await self.db.commit()

                # Small delay between retries
                await asyncio.sleep(settings.retry_delay_seconds)

            except Exception as e:
                logger.error(f"Error retrying notification {notification.id}: {e}")
                notification.status = NotificationStatus.FAILED
                notification.error_message = str(e)
                await self.db.commit()

        return retry_count

    def _get_delivery_priority(self, notification_data: NotificationCreate) -> DeliveryPriority:
        """Determine delivery priority based on notification data"""
        # High priority for urgent notifications
        if notification_data.priority >= 4:
            return DeliveryPriority.URGENT
        elif notification_data.priority == 3:
            return DeliveryPriority.HIGH
        elif notification_data.priority == 2:
            return DeliveryPriority.NORMAL
        else:
            return DeliveryPriority.LOW

        # Special priority handling for notification types
        urgent_types = [
            NotificationType.VERIFICATION_REQUEST,
            NotificationType.ACCESS_GRANTED,
            NotificationType.ACCESS_REVOKED
        ]

        high_priority_types = [
            NotificationType.STATUS_CHANGED,
            NotificationType.SHIFT_STARTED,
            NotificationType.SHIFT_ENDED
        ]

        if notification_data.notification_type in urgent_types:
            return DeliveryPriority.URGENT
        elif notification_data.notification_type in high_priority_types:
            return DeliveryPriority.HIGH
        else:
            return DeliveryPriority.NORMAL

    async def get_statistics(self, days: int = 30) -> NotificationStats:
        """Get notification statistics"""
        since = datetime.utcnow() - timedelta(days=days)

        # Basic counts
        total_stmt = select(func.count(NotificationLog.id)).where(
            NotificationLog.created_at >= since
        )
        total_result = await self.db.execute(total_stmt)
        total_notifications = total_result.scalar() or 0

        # Status counts
        status_counts = {}
        for status in NotificationStatus:
            count_stmt = select(func.count(NotificationLog.id)).where(
                and_(
                    NotificationLog.created_at >= since,
                    NotificationLog.status == status
                )
            )
            result = await self.db.execute(count_stmt)
            status_counts[status.value] = result.scalar() or 0

        # Type counts
        type_counts = {}
        for notif_type in NotificationType:
            count_stmt = select(func.count(NotificationLog.id)).where(
                and_(
                    NotificationLog.created_at >= since,
                    NotificationLog.notification_type == notif_type
                )
            )
            result = await self.db.execute(count_stmt)
            type_counts[notif_type.value] = result.scalar() or 0

        # Channel counts
        channel_counts = {}
        for channel in NotificationChannel:
            count_stmt = select(func.count(NotificationLog.id)).where(
                and_(
                    NotificationLog.created_at >= since,
                    NotificationLog.channel == channel
                )
            )
            result = await self.db.execute(count_stmt)
            channel_counts[channel.value] = result.scalar() or 0

        # Time-based counts
        last_24h_stmt = select(func.count(NotificationLog.id)).where(
            NotificationLog.created_at >= datetime.utcnow() - timedelta(hours=24)
        )
        last_24h_result = await self.db.execute(last_24h_stmt)
        last_24h = last_24h_result.scalar() or 0

        last_week_stmt = select(func.count(NotificationLog.id)).where(
            NotificationLog.created_at >= datetime.utcnow() - timedelta(days=7)
        )
        last_week_result = await self.db.execute(last_week_stmt)
        last_week = last_week_result.scalar() or 0

        return NotificationStats(
            total_notifications=total_notifications,
            sent_count=status_counts.get(NotificationStatus.SENT.value, 0),
            delivered_count=status_counts.get(NotificationStatus.DELIVERED.value, 0),
            failed_count=status_counts.get(NotificationStatus.FAILED.value, 0),
            pending_count=status_counts.get(NotificationStatus.PENDING.value, 0),
            retry_count=status_counts.get(NotificationStatus.RETRYING.value, 0),
            by_type=type_counts,
            by_channel=channel_counts,
            by_status=status_counts,
            last_24h=last_24h,
            last_week=last_week,
            last_month=total_notifications
        )