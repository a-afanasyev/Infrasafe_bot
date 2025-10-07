"""
Webhook Service
UK Management Bot - Integration Service

Handles incoming webhook events from external services.
"""

import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook_config import WebhookConfig
from app.models.webhook_event import WebhookEvent, WebhookEventStatus
from app.core.events import EventPublisher

logger = logging.getLogger(__name__)


class WebhookService:
    """
    Service for processing incoming webhooks.

    Features:
    - Signature verification
    - Idempotency handling
    - Event storage
    - Async event processing
    - Retry mechanism
    """

    def __init__(
        self,
        db: AsyncSession,
        event_publisher: EventPublisher
    ):
        self.db = db
        self.event_publisher = event_publisher

    async def receive_webhook(
        self,
        source: str,
        event_type: str,
        headers: Dict[str, str],
        body: Dict[str, Any],
        query_params: Optional[Dict[str, str]] = None,
        path: str = "/webhook",
        method: str = "POST",
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Receive and process incoming webhook.

        Args:
            source: Event source (e.g., "stripe", "google_sheets")
            event_type: Type of event
            headers: Request headers
            body: Request body
            query_params: Query parameters
            path: Request path
            method: HTTP method
            ip_address: Source IP

        Returns:
            Processing result
        """
        logger.info(f"Received webhook: {source}/{event_type}")

        # Get webhook configuration
        webhook_config = await self._get_webhook_config(source, event_type)

        # Extract event ID for idempotency
        event_id = self._extract_event_id(source, body)

        # Check for duplicate event
        if event_id:
            duplicate = await self._check_duplicate(event_id)
            if duplicate:
                logger.info(f"Duplicate event {event_id}, returning cached response")
                return {
                    "status": "duplicate",
                    "event_id": event_id,
                    "original_event_id": str(duplicate.id)
                }

        # Verify signature
        signature_valid = False
        if webhook_config:
            signature_valid = await self._verify_signature(
                webhook_config,
                headers,
                body
            )

        # Create webhook event record
        webhook_event = WebhookEvent(
            webhook_config_id=webhook_config.id if webhook_config else None,
            event_id=event_id,
            event_type=event_type,
            source=source,
            request_method=method,
            request_path=path,
            request_headers=self._sanitize_headers(headers),
            request_query=query_params,
            request_body=body,
            signature=headers.get("x-signature") or headers.get("x-hub-signature"),
            signature_valid=signature_valid,
            ip_address=ip_address,
            status=WebhookEventStatus.PENDING
        )

        self.db.add(webhook_event)
        await self.db.commit()
        await self.db.refresh(webhook_event)

        # Process event asynchronously
        try:
            result = await self._process_webhook_event(webhook_event, body)

            # Update event status
            webhook_event.status = WebhookEventStatus.COMPLETED
            webhook_event.processed_at = datetime.utcnow()
            webhook_event.response_status_code = 200
            webhook_event.response_body = result

            await self.db.commit()

            return result

        except Exception as e:
            logger.error(f"Webhook processing failed: {e}", exc_info=True)

            # Update event status
            webhook_event.status = WebhookEventStatus.FAILED
            webhook_event.error_message = str(e)
            webhook_event.response_status_code = 500

            # Schedule retry
            if webhook_event.retry_count < webhook_event.max_retries:
                webhook_event.status = WebhookEventStatus.RETRYING
                webhook_event.next_retry_at = datetime.utcnow() + timedelta(
                    minutes=2 ** webhook_event.retry_count
                )

            await self.db.commit()

            raise

    async def _get_webhook_config(
        self,
        source: str,
        event_type: str
    ) -> Optional[WebhookConfig]:
        """Get webhook configuration for source and event type."""
        result = await self.db.execute(
            select(WebhookConfig).where(
                WebhookConfig.service_id.isnot(None),  # Placeholder
                WebhookConfig.is_active == True
            )
        )
        return result.scalar_one_or_none()

    def _extract_event_id(self, source: str, body: Dict[str, Any]) -> Optional[str]:
        """Extract event ID for idempotency check."""
        # Different sources use different field names
        event_id_fields = {
            "stripe": "id",
            "google_sheets": "eventId",
            "yandex": "event_id",
            "default": "id"
        }

        field_name = event_id_fields.get(source, event_id_fields["default"])
        return body.get(field_name)

    async def _check_duplicate(self, event_id: str) -> Optional[WebhookEvent]:
        """Check if event was already processed."""
        result = await self.db.execute(
            select(WebhookEvent).where(
                WebhookEvent.event_id == event_id,
                WebhookEvent.status == WebhookEventStatus.COMPLETED
            )
        )
        return result.scalar_one_or_none()

    async def _verify_signature(
        self,
        webhook_config: WebhookConfig,
        headers: Dict[str, str],
        body: Dict[str, Any]
    ) -> bool:
        """
        Verify webhook signature.

        Supports:
        - HMAC-SHA256 (Stripe, most services)
        - Custom verification methods
        """
        if not webhook_config.secret_key:
            return False

        signature_header = webhook_config.signature_header or "x-signature"
        signature = headers.get(signature_header.lower())

        if not signature:
            return False

        # Calculate expected signature
        payload = json.dumps(body, separators=(',', ':'))
        expected_signature = hmac.new(
            webhook_config.secret_key.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()

        # Compare signatures
        return hmac.compare_digest(signature, expected_signature)

    def _sanitize_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Remove sensitive data from headers before storing."""
        sensitive_headers = {
            "authorization",
            "x-api-key",
            "x-secret-key",
            "cookie"
        }

        sanitized = {}
        for key, value in headers.items():
            if key.lower() in sensitive_headers:
                sanitized[key] = "***REDACTED***"
            else:
                sanitized[key] = value

        return sanitized

    async def _process_webhook_event(
        self,
        webhook_event: WebhookEvent,
        body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process webhook event based on event type.

        Routes to appropriate handler based on source and event_type.
        """
        start_time = datetime.utcnow()

        # Route to specific handler
        handler = self._get_event_handler(webhook_event.source, webhook_event.event_type)

        if handler:
            result = await handler(webhook_event, body)
        else:
            # Default handler: just publish event
            result = {"status": "received", "message": "No specific handler"}

        # Publish event to message bus
        await self.event_publisher.publish(
            event_type=f"webhook.{webhook_event.source}.{webhook_event.event_type}",
            data={
                "event_id": str(webhook_event.id),
                "source": webhook_event.source,
                "event_type": webhook_event.event_type,
                "body": body
            }
        )

        # Calculate processing duration
        duration = (datetime.utcnow() - start_time).total_seconds() * 1000
        webhook_event.processing_duration_ms = int(duration)

        return result

    def _get_event_handler(self, source: str, event_type: str):
        """Get appropriate event handler based on source and type."""
        handlers = {
            ("stripe", "payment.succeeded"): self._handle_stripe_payment,
            ("stripe", "payment.failed"): self._handle_stripe_payment_failed,
            ("google_sheets", "sheet.updated"): self._handle_sheet_updated,
            # Add more handlers as needed
        }

        return handlers.get((source, event_type))

    async def _handle_stripe_payment(
        self,
        webhook_event: WebhookEvent,
        body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle Stripe payment success webhook."""
        logger.info(f"Processing Stripe payment: {body.get('id')}")

        # Extract payment data
        payment_intent = body.get("data", {}).get("object", {})
        amount = payment_intent.get("amount")
        currency = payment_intent.get("currency")
        metadata = payment_intent.get("metadata", {})

        # Process payment (update request status, etc.)
        # This would integrate with Request Service

        return {
            "status": "processed",
            "payment_id": body.get("id"),
            "amount": amount,
            "currency": currency
        }

    async def _handle_stripe_payment_failed(
        self,
        webhook_event: WebhookEvent,
        body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle Stripe payment failure webhook."""
        logger.warning(f"Payment failed: {body.get('id')}")

        # Notify user, update request status, etc.

        return {
            "status": "processed",
            "payment_id": body.get("id"),
            "failure_reason": body.get("data", {}).get("object", {}).get("last_payment_error")
        }

    async def _handle_sheet_updated(
        self,
        webhook_event: WebhookEvent,
        body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle Google Sheets update webhook."""
        logger.info(f"Sheet updated: {body}")

        # Process sheet update
        # Sync data, trigger refresh, etc.

        return {
            "status": "processed",
            "sheet_id": body.get("spreadsheetId")
        }

    async def retry_failed_webhooks(self) -> int:
        """
        Retry failed webhook events.

        Returns:
            Number of events retried
        """
        now = datetime.utcnow()

        # Find events ready for retry
        result = await self.db.execute(
            select(WebhookEvent).where(
                WebhookEvent.status == WebhookEventStatus.RETRYING,
                WebhookEvent.next_retry_at <= now,
                WebhookEvent.retry_count < WebhookEvent.max_retries
            )
        )

        events = result.scalars().all()
        retry_count = 0

        for event in events:
            try:
                # Increment retry count
                event.retry_count += 1
                event.status = WebhookEventStatus.PROCESSING

                await self.db.commit()

                # Retry processing
                result = await self._process_webhook_event(
                    event,
                    event.request_body
                )

                event.status = WebhookEventStatus.COMPLETED
                event.processed_at = datetime.utcnow()
                event.response_body = result

                await self.db.commit()
                retry_count += 1

            except Exception as e:
                logger.error(f"Retry failed for event {event.id}: {e}")

                event.status = WebhookEventStatus.FAILED
                event.error_message = str(e)

                # Schedule next retry if not exceeded max
                if event.retry_count < event.max_retries:
                    event.status = WebhookEventStatus.RETRYING
                    event.next_retry_at = now + timedelta(
                        minutes=2 ** event.retry_count
                    )

                await self.db.commit()

        logger.info(f"Retried {retry_count} webhook events")
        return retry_count
