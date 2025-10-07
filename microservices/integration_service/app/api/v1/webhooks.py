"""
Webhook API Endpoints
UK Management Bot - Integration Service

Endpoints for receiving webhook events from external services.
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional
from uuid import UUID

from fastapi import APIRouter, Request, Depends, HTTPException, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.events import get_event_publisher, EventPublisher
from app.services.webhook_service import WebhookService
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class WebhookResponse(BaseModel):
    """Webhook processing response"""
    status: str
    event_id: Optional[str] = None
    message: Optional[str] = None


@router.post("/stripe", response_model=WebhookResponse)
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    event_publisher: EventPublisher = Depends(get_event_publisher),
    x_stripe_signature: Optional[str] = Header(None)
):
    """
    Receive Stripe webhook events.

    Handles:
    - payment_intent.succeeded
    - payment_intent.failed
    - charge.succeeded
    - charge.failed
    - invoice.paid
    - customer.subscription.updated

    Security:
    - Signature verification
    - Idempotency handling
    """
    try:
        # Get request body
        body = await request.json()

        # Extract event type
        event_type = body.get("type", "unknown")

        # Get headers
        headers = dict(request.headers)
        if x_stripe_signature:
            headers["x-stripe-signature"] = x_stripe_signature

        # Process webhook
        webhook_service = WebhookService(db, event_publisher)
        result = await webhook_service.receive_webhook(
            source="stripe",
            event_type=event_type,
            headers=headers,
            body=body,
            path=str(request.url.path),
            method=request.method,
            ip_address=request.client.host if request.client else None
        )

        return WebhookResponse(**result)

    except Exception as e:
        logger.error(f"Stripe webhook error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/google/sheets", response_model=WebhookResponse)
async def google_sheets_webhook(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    event_publisher: EventPublisher = Depends(get_event_publisher)
):
    """
    Receive Google Sheets webhook events.

    Handles:
    - spreadsheet.updated
    - sheet.created
    - sheet.deleted
    - cell.updated

    Note: Google Sheets doesn't natively support webhooks.
    This endpoint is for custom integrations (e.g., Apps Script triggers).
    """
    try:
        body = await request.json()
        event_type = body.get("eventType", "sheet.updated")

        webhook_service = WebhookService(db, event_publisher)
        result = await webhook_service.receive_webhook(
            source="google_sheets",
            event_type=event_type,
            headers=dict(request.headers),
            body=body,
            path=str(request.url.path),
            method=request.method,
            ip_address=request.client.host if request.client else None
        )

        return WebhookResponse(**result)

    except Exception as e:
        logger.error(f"Google Sheets webhook error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/yandex/maps", response_model=WebhookResponse)
async def yandex_maps_webhook(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    event_publisher: EventPublisher = Depends(get_event_publisher)
):
    """
    Receive Yandex Maps webhook events.

    Handles:
    - geocode.completed
    - route.calculated
    - address.verified
    """
    try:
        body = await request.json()
        event_type = body.get("event_type", "unknown")

        webhook_service = WebhookService(db, event_publisher)
        result = await webhook_service.receive_webhook(
            source="yandex_maps",
            event_type=event_type,
            headers=dict(request.headers),
            body=body,
            path=str(request.url.path),
            method=request.method,
            ip_address=request.client.host if request.client else None
        )

        return WebhookResponse(**result)

    except Exception as e:
        logger.error(f"Yandex Maps webhook error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/generic/{source}", response_model=WebhookResponse)
async def generic_webhook(
    source: str,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    event_publisher: EventPublisher = Depends(get_event_publisher)
):
    """
    Generic webhook endpoint for any external service.

    Use this for services without dedicated endpoints.

    Path parameter:
    - source: Service identifier (e.g., "custom_api", "third_party")
    """
    try:
        body = await request.json()
        event_type = body.get("event_type", body.get("type", "unknown"))

        webhook_service = WebhookService(db, event_publisher)
        result = await webhook_service.receive_webhook(
            source=source,
            event_type=event_type,
            headers=dict(request.headers),
            body=body,
            path=str(request.url.path),
            method=request.method,
            ip_address=request.client.host if request.client else None
        )

        return WebhookResponse(**result)

    except Exception as e:
        logger.error(f"Generic webhook error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# Admin endpoints for webhook management

@router.get("/events/{event_id}")
async def get_webhook_event(
    event_id: UUID,
    db: AsyncSession = Depends(get_async_session)
):
    """Get webhook event details by ID."""
    from sqlalchemy import select
    from app.models.webhook_event import WebhookEvent

    result = await db.execute(
        select(WebhookEvent).where(WebhookEvent.id == event_id)
    )
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook event not found"
        )

    return {
        "id": str(event.id),
        "source": event.source,
        "event_type": event.event_type,
        "status": event.status.value,
        "created_at": event.created_at.isoformat(),
        "processed_at": event.processed_at.isoformat() if event.processed_at else None,
        "processing_duration_ms": event.processing_duration_ms,
        "retry_count": event.retry_count,
        "error_message": event.error_message
    }


@router.post("/events/{event_id}/retry")
async def retry_webhook_event(
    event_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    event_publisher: EventPublisher = Depends(get_event_publisher)
):
    """
    Manually retry a failed webhook event.

    Use this for debugging or forcing re-processing.
    """
    from sqlalchemy import select
    from app.models.webhook_event import WebhookEvent, WebhookEventStatus

    # Get event
    result = await db.execute(
        select(WebhookEvent).where(WebhookEvent.id == event_id)
    )
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook event not found"
        )

    # Retry event
    webhook_service = WebhookService(db, event_publisher)

    try:
        result = await webhook_service._process_webhook_event(
            event,
            event.request_body
        )

        event.status = WebhookEventStatus.COMPLETED
        event.processed_at = datetime.utcnow()
        event.response_body = result
        event.retry_count += 1

        await db.commit()

        return {
            "status": "success",
            "message": "Event retried successfully",
            "result": result
        }

    except Exception as e:
        event.status = WebhookEventStatus.FAILED
        event.error_message = str(e)
        event.retry_count += 1

        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Retry failed: {str(e)}"
        )


@router.get("/health")
async def webhook_health():
    """Webhook service health check."""
    return {
        "status": "healthy",
        "service": "Webhook Handler",
        "endpoints": [
            "/webhooks/stripe",
            "/webhooks/google/sheets",
            "/webhooks/yandex/maps",
            "/webhooks/generic/{source}"
        ]
    }
