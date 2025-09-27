# Notification API endpoints
# UK Management Bot - Notification Service

from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from models.notification import NotificationStatus, NotificationType, NotificationChannel
from schemas.notification import (
    NotificationCreate,
    NotificationResponse,
    NotificationBatch,
    NotificationQuery,
    NotificationStats,
    NotificationStatusUpdate
)
from services.notification_service import NotificationService
from middleware.auth import get_current_user, get_optional_current_user, require_any_role
from config import settings
from database import get_db

router = APIRouter(prefix="/notifications", tags=["notifications"])

# Add pipeline metrics endpoint
@router.get("/pipeline/metrics")
async def get_pipeline_metrics(
    request: Request,
    current_user: Dict[str, Any] = Depends(require_any_role(["admin", "manager"]))
):
    """Get delivery pipeline metrics (admin only)"""
    try:
        delivery_pipeline = getattr(request.app.state, 'delivery_pipeline', None)

        if not delivery_pipeline:
            return {"error": "Delivery pipeline not available"}

        metrics = await delivery_pipeline.get_metrics()
        return metrics

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get pipeline metrics: {str(e)}")

@router.get("/pipeline/health")
async def get_pipeline_health(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get delivery pipeline health status"""
    try:
        delivery_pipeline = getattr(request.app.state, 'delivery_pipeline', None)

        if not delivery_pipeline:
            return {"status": "unavailable", "error": "Delivery pipeline not configured"}

        health = await delivery_pipeline.health_check()
        return health

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check pipeline health: {str(e)}")

@router.post("/send", response_model=NotificationResponse)
async def send_notification(
    notification: NotificationCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Send a single notification"""
    try:
        # Get delivery pipeline from app state if available
        from fastapi import Request
        request = Request(scope={"type": "http"})
        delivery_pipeline = getattr(request.app.state, 'delivery_pipeline', None) if hasattr(request, 'app') else None

        service = NotificationService(db, delivery_pipeline)

        # Add service context to notification
        # Handle both service tokens and user tokens
        if current_user.get("type") == "service":
            # Service token - extract service_name and permissions
            service_name = current_user.get("service_name", "unknown-service")
            service_permissions = current_user.get("permissions", [])

            notification.service_origin = service_name
            if not notification.correlation_id:
                notification.correlation_id = f"service_{service_name}_{notification.event_type}"

            # Store service permissions for audit/debugging
            if hasattr(notification, 'metadata') and isinstance(notification.metadata, dict):
                notification.metadata["service_permissions"] = service_permissions

        else:
            # User token - fallback to user context
            user_id = current_user.get("user_id", "unknown")
            notification.service_origin = "user-initiated"
            if not notification.correlation_id:
                notification.correlation_id = f"user_{user_id}_{notification.event_type}"

        result = await service.send_notification(notification)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send notification: {str(e)}")

@router.post("/send/batch", response_model=List[NotificationResponse])
async def send_batch_notifications(
    batch: NotificationBatch,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Send multiple notifications in batch"""
    if len(batch.notifications) > 100:
        raise HTTPException(status_code=400, detail="Batch size cannot exceed 100 notifications")

    try:
        service = NotificationService(db)
        results = await service.send_batch(batch)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send batch notifications: {str(e)}")

@router.get("/", response_model=List[NotificationResponse])
async def get_notifications(
    status: NotificationStatus = None,
    notification_type: NotificationType = None,
    channel: NotificationChannel = None,
    recipient_id: int = None,
    request_number: str = None,
    service_origin: str = None,
    correlation_id: str = None,
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """Get notifications with filtering"""
    query = NotificationQuery(
        status=status,
        notification_type=notification_type,
        channel=channel,
        recipient_id=recipient_id,
        request_number=request_number,
        service_origin=service_origin,
        correlation_id=correlation_id,
        limit=limit,
        offset=offset
    )

    try:
        service = NotificationService(db)
        notifications = await service.get_notifications(query)
        return notifications
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve notifications: {str(e)}")

@router.get("/{notification_id}", response_model=NotificationResponse)
async def get_notification(
    notification_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get single notification by ID"""
    try:
        service = NotificationService(db)
        notification = await service.get_notification_by_id(notification_id)

        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")

        return notification
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve notification: {str(e)}")

@router.patch("/{notification_id}/status", response_model=NotificationResponse)
async def update_notification_status(
    notification_id: int,
    status_update: NotificationStatusUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update notification status"""
    try:
        service = NotificationService(db)
        updated_notification = await service.update_notification_status(notification_id, status_update)

        if not updated_notification:
            raise HTTPException(status_code=404, detail="Notification not found")

        return updated_notification
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update notification status: {str(e)}")

@router.post("/retry-failed")
async def retry_failed_notifications(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Retry failed notifications"""
    try:
        service = NotificationService(db)

        # Run retry in background to avoid blocking
        async def retry_task():
            retry_count = await service.retry_failed_notifications()
            return retry_count

        background_tasks.add_task(retry_task)

        return {"message": "Retry process started", "status": "processing"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start retry process: {str(e)}")

@router.get("/stats/overview", response_model=NotificationStats)
async def get_notification_stats(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db)
):
    """Get notification statistics"""
    try:
        service = NotificationService(db)
        stats = await service.get_statistics(days)
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve statistics: {str(e)}")

# === Convenience endpoints for common notification types ===

@router.post("/shift/started")
async def notify_shift_started(
    user_id: int,
    telegram_id: int,
    shift_data: dict,
    db: AsyncSession = Depends(get_db)
):
    """Send shift started notification"""
    try:
        service = NotificationService(db)

        # User notification
        user_notification = NotificationCreate(
            notification_type=NotificationType.SHIFT_STARTED,
            channel=NotificationChannel.TELEGRAM,
            recipient_id=user_id,
            recipient_telegram_id=telegram_id,
            message=f"✅ Ваша смена начата в {shift_data.get('start_time', 'неизвестно')}",
            message_data=shift_data,
            service_origin="shift-service"
        )

        # Channel notification
        channel_notification = NotificationCreate(
            notification_type=NotificationType.SHIFT_STARTED,
            channel=NotificationChannel.TELEGRAM,
            recipient_telegram_id=int(settings.telegram_channel_id) if settings.telegram_channel_id.isdigit() else None,
            message=f"🔔 Смена начата: user_id={telegram_id} в {shift_data.get('start_time', 'неизвестно')}",
            message_data=shift_data,
            service_origin="shift-service"
        ) if settings.telegram_channel_id else None

        results = [await service.send_notification(user_notification)]
        if channel_notification:
            results.append(await service.send_notification(channel_notification))

        return {"message": "Shift started notifications sent", "results": results}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send shift started notifications: {str(e)}")

@router.post("/shift/ended")
async def notify_shift_ended(
    user_id: int,
    telegram_id: int,
    shift_data: dict,
    db: AsyncSession = Depends(get_db)
):
    """Send shift ended notification"""
    try:
        service = NotificationService(db)

        duration = shift_data.get('duration', 'неизвестно')
        end_time = shift_data.get('end_time', 'неизвестно')

        # User notification
        user_notification = NotificationCreate(
            notification_type=NotificationType.SHIFT_ENDED,
            channel=NotificationChannel.TELEGRAM,
            recipient_id=user_id,
            recipient_telegram_id=telegram_id,
            message=f"✅ Смена завершена в {end_time}. Длительность: {duration}",
            message_data=shift_data,
            service_origin="shift-service"
        )

        # Channel notification
        channel_notification = NotificationCreate(
            notification_type=NotificationType.SHIFT_ENDED,
            channel=NotificationChannel.TELEGRAM,
            recipient_telegram_id=int(settings.telegram_channel_id) if settings.telegram_channel_id.isdigit() else None,
            message=f"📤 Смена завершена: user_id={telegram_id} в {end_time} (длительность {duration})",
            message_data=shift_data,
            service_origin="shift-service"
        ) if settings.telegram_channel_id else None

        results = [await service.send_notification(user_notification)]
        if channel_notification:
            results.append(await service.send_notification(channel_notification))

        return {"message": "Shift ended notifications sent", "results": results}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send shift ended notifications: {str(e)}")

@router.post("/request/status-changed")
async def notify_request_status_changed(
    request_data: dict,
    old_status: str,
    new_status: str,
    db: AsyncSession = Depends(get_db)
):
    """Send request status change notification"""
    try:
        service = NotificationService(db)
        results = []

        request_number = request_data.get('request_number', 'неизвестно')
        category = request_data.get('category', '')
        address = request_data.get('address', '')

        # Applicant notification
        if request_data.get('applicant_telegram_id'):
            applicant_msg = f"📌 Статус вашей заявки #{request_number} изменён: {old_status} → {new_status}\\n"
            applicant_msg += f"Категория: {category}\\n"
            if address:
                address_short = address[:60] + '…' if len(address) > 60 else address
                applicant_msg += f"Адрес: {address_short}"

            applicant_notification = NotificationCreate(
                notification_type=NotificationType.STATUS_CHANGED,
                channel=NotificationChannel.TELEGRAM,
                recipient_id=request_data.get('user_id'),
                recipient_telegram_id=request_data.get('applicant_telegram_id'),
                message=applicant_msg,
                message_data=request_data,
                request_number=request_number,
                service_origin="request-service"
            )
            results.append(await service.send_notification(applicant_notification))

        # Executor notification
        if request_data.get('executor_telegram_id'):
            executor_msg = f"📌 Статус заявки #{request_number} изменён: {old_status} → {new_status}\\n"
            executor_msg += f"Категория: {category} — назначена вам"

            executor_notification = NotificationCreate(
                notification_type=NotificationType.STATUS_CHANGED,
                channel=NotificationChannel.TELEGRAM,
                recipient_id=request_data.get('executor_id'),
                recipient_telegram_id=request_data.get('executor_telegram_id'),
                message=executor_msg,
                message_data=request_data,
                request_number=request_number,
                service_origin="request-service"
            )
            results.append(await service.send_notification(executor_notification))

        # Channel notification
        if settings.telegram_channel_id:
            channel_msg = f"🔔 Заявка #{request_number}: {old_status} → {new_status}\\n"
            channel_msg += f"Категория: {category}"

            channel_notification = NotificationCreate(
                notification_type=NotificationType.STATUS_CHANGED,
                channel=NotificationChannel.TELEGRAM,
                recipient_telegram_id=int(settings.telegram_channel_id) if settings.telegram_channel_id.isdigit() else None,
                message=channel_msg,
                message_data=request_data,
                request_number=request_number,
                service_origin="request-service"
            )
            results.append(await service.send_notification(channel_notification))

        return {"message": "Request status change notifications sent", "results": results}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send status change notifications: {str(e)}")

@router.post("/document/request")
async def notify_document_request(
    user_id: int,
    telegram_id: int,
    request_text: str,
    document_type: str = None,
    db: AsyncSession = Depends(get_db)
):
    """Send document request notification"""
    try:
        service = NotificationService(db)

        # Document type mapping
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

        notification = NotificationCreate(
            notification_type=NotificationType.DOCUMENT_REQUEST,
            channel=NotificationChannel.TELEGRAM,
            recipient_id=user_id,
            recipient_telegram_id=telegram_id,
            title="📋 Администратор запросил документы",
            message=message,
            message_data={
                "document_type": document_type,
                "request_text": request_text,
                "document_name": doc_name
            },
            service_origin="user-service"
        )

        result = await service.send_notification(notification)
        return {"message": "Document request notification sent", "result": result}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send document request notification: {str(e)}")