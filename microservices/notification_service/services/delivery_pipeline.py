# Production-Ready Notification Delivery Pipeline
# UK Management Bot - Notification Service

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from enum import Enum
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, func

from models.notification import NotificationLog, NotificationStatus
from config import settings

logger = logging.getLogger(__name__)

class DeliveryPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4

class DeliveryMetrics:
    """Metrics collection for delivery pipeline"""

    def __init__(self):
        self.total_processed = 0
        self.successful_deliveries = 0
        self.failed_deliveries = 0
        self.retries_attempted = 0
        self.avg_delivery_time = 0.0
        self.circuit_breaker_trips = 0
        self.last_reset = datetime.utcnow()

    def record_success(self, delivery_time: float):
        """Record successful delivery"""
        self.total_processed += 1
        self.successful_deliveries += 1
        # Update rolling average
        self.avg_delivery_time = (self.avg_delivery_time + delivery_time) / 2

    def record_failure(self):
        """Record failed delivery"""
        self.total_processed += 1
        self.failed_deliveries += 1

    def record_retry(self):
        """Record retry attempt"""
        self.retries_attempted += 1

    def record_circuit_break(self):
        """Record circuit breaker trip"""
        self.circuit_breaker_trips += 1

    def get_success_rate(self) -> float:
        """Get delivery success rate"""
        if self.total_processed == 0:
            return 1.0
        return self.successful_deliveries / self.total_processed

    def reset_if_needed(self):
        """Reset metrics if it's been too long"""
        if datetime.utcnow() - self.last_reset > timedelta(hours=1):
            # Keep some history but reset counters
            self.total_processed = min(self.total_processed, 1000)
            self.successful_deliveries = min(self.successful_deliveries, 1000)
            self.failed_deliveries = min(self.failed_deliveries, 1000)
            self.last_reset = datetime.utcnow()

class CircuitBreaker:
    """Circuit breaker for delivery channels"""

    def __init__(self, failure_threshold: int = 10, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    def call_succeeded(self):
        """Record successful call"""
        self.failure_count = 0
        self.state = "CLOSED"

    def call_failed(self):
        """Record failed call"""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()

        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(f"Circuit breaker opened after {self.failure_count} failures")

    def can_call(self) -> bool:
        """Check if calls are allowed"""
        if self.state == "CLOSED":
            return True

        if self.state == "OPEN":
            if self.last_failure_time and \
               (datetime.utcnow() - self.last_failure_time).seconds >= self.recovery_timeout:
                self.state = "HALF_OPEN"
                logger.info("Circuit breaker entering half-open state")
                return True
            return False

        # HALF_OPEN state
        return True

class ProductionDeliveryPipeline:
    """Production-ready delivery pipeline with retries, persistence, and monitoring"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.redis_client: Optional[redis.Redis] = None
        self.metrics = DeliveryMetrics()
        self.circuit_breakers = {
            "telegram": CircuitBreaker(),
            "email": CircuitBreaker(),
            "sms": CircuitBreaker()
        }
        self.running = False
        self.worker_tasks = []

    async def initialize(self):
        """Initialize delivery pipeline"""
        try:
            # Initialize Redis with optimized settings
            self.redis_client = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_keepalive=True,
                socket_keepalive_options={},
                health_check_interval=30,
                retry_on_timeout=True,
                retry_on_error=[redis.ConnectionError, redis.TimeoutError]
            )

            await self.redis_client.ping()
            logger.info("Production delivery pipeline initialized")

            # Start background workers
            await self.start_workers()

        except Exception as e:
            logger.error(f"Failed to initialize delivery pipeline: {e}")
            raise

    async def shutdown(self):
        """Shutdown delivery pipeline gracefully"""
        self.running = False

        # Cancel worker tasks
        for task in self.worker_tasks:
            task.cancel()

        # Wait for tasks to complete
        if self.worker_tasks:
            await asyncio.gather(*self.worker_tasks, return_exceptions=True)

        if self.redis_client:
            await self.redis_client.close()

        logger.info("Delivery pipeline shutdown complete")

    async def start_workers(self):
        """Start background worker tasks"""
        self.running = True

        # Start delivery workers
        self.worker_tasks = [
            asyncio.create_task(self._delivery_worker(worker_id))
            for worker_id in range(settings.delivery_workers)
        ]

        # Start retry worker
        self.worker_tasks.append(
            asyncio.create_task(self._retry_worker())
        )

        # Start metrics worker
        self.worker_tasks.append(
            asyncio.create_task(self._metrics_worker())
        )

        logger.info(f"Started {len(self.worker_tasks)} delivery pipeline workers")

    async def enqueue_notification(
        self,
        notification_id: int,
        priority: DeliveryPriority = DeliveryPriority.NORMAL,
        delay_seconds: int = 0
    ) -> bool:
        """Enqueue notification for delivery with persistence"""
        try:
            queue_name = f"delivery_queue:{priority.name.lower()}"

            delivery_data = {
                "notification_id": notification_id,
                "priority": priority.value,
                "enqueued_at": datetime.utcnow().isoformat(),
                "retry_count": 0,
                "max_retries": settings.max_retry_attempts
            }

            if delay_seconds > 0:
                # Schedule for later delivery
                execute_at = time.time() + delay_seconds
                await self.redis_client.zadd(
                    "delayed_deliveries",
                    {json.dumps(delivery_data): execute_at}
                )
            else:
                # Immediate delivery
                await self.redis_client.lpush(queue_name, json.dumps(delivery_data))

            logger.debug(f"Enqueued notification {notification_id} with priority {priority.name}")
            return True

        except Exception as e:
            logger.error(f"Failed to enqueue notification {notification_id}: {e}")
            return False

    async def _delivery_worker(self, worker_id: int):
        """Background worker for processing delivery queue"""
        logger.info(f"Delivery worker {worker_id} started")

        while self.running:
            try:
                # Process delayed deliveries first
                await self._process_delayed_deliveries()

                # Process priority queues (high to low)
                for priority in [DeliveryPriority.URGENT, DeliveryPriority.HIGH,
                               DeliveryPriority.NORMAL, DeliveryPriority.LOW]:

                    queue_name = f"delivery_queue:{priority.name.lower()}"

                    # Pop from queue with timeout
                    result = await self.redis_client.brpop(queue_name, timeout=5)

                    if result:
                        _, data = result
                        delivery_data = json.loads(data)

                        start_time = time.time()
                        success = await self._process_delivery(delivery_data)
                        delivery_time = time.time() - start_time

                        if success:
                            self.metrics.record_success(delivery_time)
                        else:
                            self.metrics.record_failure()
                            # Requeue for retry if within limits
                            await self._handle_delivery_failure(delivery_data)

                        break  # Process one item then check other queues

                # Reset metrics periodically
                self.metrics.reset_if_needed()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in delivery worker {worker_id}: {e}")
                await asyncio.sleep(1)  # Brief pause on error

        logger.info(f"Delivery worker {worker_id} stopped")

    async def _process_delayed_deliveries(self):
        """Process delayed deliveries that are ready"""
        try:
            now = time.time()

            # Get deliveries ready for processing
            ready_deliveries = await self.redis_client.zrangebyscore(
                "delayed_deliveries", 0, now, withscores=True
            )

            for delivery_json, _ in ready_deliveries:
                delivery_data = json.loads(delivery_json)
                priority = DeliveryPriority(delivery_data["priority"])
                queue_name = f"delivery_queue:{priority.name.lower()}"

                # Move to immediate delivery queue
                await self.redis_client.lpush(queue_name, delivery_json)

                # Remove from delayed queue
                await self.redis_client.zrem("delayed_deliveries", delivery_json)

        except Exception as e:
            logger.error(f"Error processing delayed deliveries: {e}")

    async def _process_delivery(self, delivery_data: Dict[str, Any]) -> bool:
        """Process individual delivery"""
        notification_id = delivery_data["notification_id"]

        try:
            # Get notification from database
            stmt = select(NotificationLog).where(NotificationLog.id == notification_id)
            result = await self.db.execute(stmt)
            notification = result.scalar_one_or_none()

            if not notification:
                logger.warning(f"Notification {notification_id} not found")
                return False

            # Check circuit breaker
            channel = notification.channel.value
            circuit_breaker = self.circuit_breakers.get(channel)

            if circuit_breaker and not circuit_breaker.can_call():
                logger.warning(f"Circuit breaker open for channel {channel}")
                self.metrics.record_circuit_break()
                return False

            # Update status to processing
            notification.status = NotificationStatus.PROCESSING
            await self.db.commit()

            # Import here to avoid circular imports
            from services.notification_service import NotificationService
            notif_service = NotificationService(self.db)

            # Attempt delivery
            success = await notif_service._send_via_channel(notification)

            if success:
                notification.status = NotificationStatus.SENT
                notification.sent_at = datetime.utcnow()
                if circuit_breaker:
                    circuit_breaker.call_succeeded()
            else:
                notification.status = NotificationStatus.FAILED
                notification.failed_at = datetime.utcnow()
                if circuit_breaker:
                    circuit_breaker.call_failed()

            await self.db.commit()
            return success

        except Exception as e:
            logger.error(f"Error processing delivery for notification {notification_id}: {e}")

            # Update notification status
            try:
                stmt = select(NotificationLog).where(NotificationLog.id == notification_id)
                result = await self.db.execute(stmt)
                notification = result.scalar_one_or_none()

                if notification:
                    notification.status = NotificationStatus.FAILED
                    notification.error_message = str(e)
                    notification.failed_at = datetime.utcnow()
                    await self.db.commit()

            except Exception as db_error:
                logger.error(f"Failed to update notification status: {db_error}")

            return False

    async def _handle_delivery_failure(self, delivery_data: Dict[str, Any]):
        """Handle failed delivery with retry logic"""
        retry_count = delivery_data.get("retry_count", 0)
        max_retries = delivery_data.get("max_retries", settings.max_retry_attempts)

        if retry_count < max_retries:
            # Exponential backoff with jitter
            delay = min(300, (2 ** retry_count) + asyncio.get_event_loop().time() % 10)

            delivery_data["retry_count"] = retry_count + 1
            delivery_data["last_retry"] = datetime.utcnow().isoformat()

            # Enqueue for retry with delay
            await self.enqueue_notification(
                delivery_data["notification_id"],
                DeliveryPriority(delivery_data["priority"]),
                delay_seconds=int(delay)
            )

            self.metrics.record_retry()
            logger.info(f"Scheduled retry {retry_count + 1} for notification {delivery_data['notification_id']} in {delay}s")
        else:
            logger.error(f"Notification {delivery_data['notification_id']} exceeded max retries ({max_retries})")

            # Move to dead letter queue for manual intervention
            await self.redis_client.lpush(
                "dead_letter_queue",
                json.dumps({
                    **delivery_data,
                    "failed_at": datetime.utcnow().isoformat(),
                    "reason": "max_retries_exceeded"
                })
            )

    async def _retry_worker(self):
        """Background worker for processing retries"""
        logger.info("Retry worker started")

        while self.running:
            try:
                # Process delayed retries
                await self._process_delayed_deliveries()
                await asyncio.sleep(10)  # Check every 10 seconds

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in retry worker: {e}")
                await asyncio.sleep(30)

        logger.info("Retry worker stopped")

    async def _metrics_worker(self):
        """Background worker for metrics collection"""
        logger.info("Metrics worker started")

        while self.running:
            try:
                # Store metrics in Redis for Prometheus scraping
                metrics_data = {
                    "total_processed": self.metrics.total_processed,
                    "successful_deliveries": self.metrics.successful_deliveries,
                    "failed_deliveries": self.metrics.failed_deliveries,
                    "retries_attempted": self.metrics.retries_attempted,
                    "avg_delivery_time": self.metrics.avg_delivery_time,
                    "success_rate": self.metrics.get_success_rate(),
                    "circuit_breaker_trips": self.metrics.circuit_breaker_trips,
                    "timestamp": datetime.utcnow().isoformat()
                }

                await self.redis_client.setex(
                    "notification_metrics",
                    300,  # 5-minute TTL
                    json.dumps(metrics_data)
                )

                # Also log important metrics
                if self.metrics.total_processed > 0:
                    logger.info(f"Delivery metrics: {self.metrics.successful_deliveries}/{self.metrics.total_processed} success rate: {self.metrics.get_success_rate():.2%}")

                await asyncio.sleep(60)  # Update every minute

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in metrics worker: {e}")
                await asyncio.sleep(60)

        logger.info("Metrics worker stopped")

    async def get_metrics(self) -> Dict[str, Any]:
        """Get current delivery metrics"""
        return {
            "pipeline_status": "running" if self.running else "stopped",
            "workers_active": len([t for t in self.worker_tasks if not t.done()]),
            "total_processed": self.metrics.total_processed,
            "successful_deliveries": self.metrics.successful_deliveries,
            "failed_deliveries": self.metrics.failed_deliveries,
            "retries_attempted": self.metrics.retries_attempted,
            "avg_delivery_time_ms": self.metrics.avg_delivery_time * 1000,
            "success_rate": self.metrics.get_success_rate(),
            "circuit_breaker_trips": self.metrics.circuit_breaker_trips,
            "circuit_breaker_states": {
                channel: breaker.state
                for channel, breaker in self.circuit_breakers.items()
            },
            "queue_sizes": await self._get_queue_sizes()
        }

    async def _get_queue_sizes(self) -> Dict[str, int]:
        """Get current queue sizes"""
        try:
            sizes = {}
            for priority in DeliveryPriority:
                queue_name = f"delivery_queue:{priority.name.lower()}"
                size = await self.redis_client.llen(queue_name)
                sizes[queue_name] = size

            sizes["delayed_deliveries"] = await self.redis_client.zcard("delayed_deliveries")
            sizes["dead_letter_queue"] = await self.redis_client.llen("dead_letter_queue")

            return sizes
        except Exception as e:
            logger.error(f"Error getting queue sizes: {e}")
            return {}

    async def health_check(self) -> Dict[str, Any]:
        """Health check for delivery pipeline"""
        try:
            if not self.redis_client:
                return {"status": "unhealthy", "error": "Redis not connected"}

            await self.redis_client.ping()

            # Check worker health
            active_workers = len([t for t in self.worker_tasks if not t.done()])
            expected_workers = settings.delivery_workers + 2  # +2 for retry and metrics workers

            if active_workers < expected_workers * 0.8:  # 80% threshold
                return {
                    "status": "degraded",
                    "active_workers": active_workers,
                    "expected_workers": expected_workers,
                    "warning": "Some workers are not running"
                }

            return {
                "status": "healthy",
                "active_workers": active_workers,
                "expected_workers": expected_workers,
                "redis_connected": True,
                "pipeline_running": self.running
            }

        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}