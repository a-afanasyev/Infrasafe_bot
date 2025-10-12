"""
Optimized Redis Streams Consumer

Task 5.1: Redis Streams Optimization
Parallel consumer workers for 1000 events/sec throughput
"""

import asyncio
import logging
from typing import List, Optional
from datetime import datetime

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from core.redis_client import get_redis
from db.session import AsyncSessionLocal
from models.event_log import EventLog
from core.stream_consumer import StreamConsumer

logger = logging.getLogger(__name__)


class OptimizedStreamConsumer:
    """
    Optimized multi-worker Redis Streams consumer

    Improvements:
    - Multiple parallel workers (3 workers default)
    - Batch processing (100 events per batch)
    - Connection pooling
    - Backpressure handling
    - Lag monitoring
    """

    def __init__(self, num_workers: int = None):
        """
        Initialize optimized consumer

        Args:
            num_workers: Number of parallel workers (default: from settings)
        """
        self.num_workers = num_workers or settings.MAX_WORKERS
        self.workers: List[asyncio.Task] = []
        self.running = False
        self.stream_name = settings.REDIS_STREAM_NAME
        self.consumer_group = settings.REDIS_CONSUMER_GROUP
        self.batch_size = settings.REDIS_BATCH_SIZE
        self.block_time = settings.REDIS_BLOCK_TIME

        # Performance metrics
        self.events_processed = 0
        self.events_failed = 0
        self.last_lag_check = datetime.utcnow()

    async def initialize(self) -> None:
        """Initialize consumer group and workers"""
        try:
            redis_client = await get_redis()

            # Create consumer group (ignore if exists)
            try:
                await redis_client.xgroup_create(
                    name=self.stream_name,
                    groupname=self.consumer_group,
                    id="0",
                    mkstream=True
                )
                logger.info(f"✅ Consumer group '{self.consumer_group}' created")
            except redis.ResponseError as e:
                if "BUSYGROUP" in str(e):
                    logger.info(f"ℹ️  Consumer group '{self.consumer_group}' already exists")
                else:
                    raise

            logger.info(f"✅ Optimized consumer initialized with {self.num_workers} workers")

        except Exception as e:
            logger.error(f"❌ Failed to initialize optimized consumer: {e}")
            raise

    async def start(self) -> None:
        """Start all worker tasks"""
        if self.running:
            logger.warning("Consumer already running")
            return

        await self.initialize()
        self.running = True

        # Start worker tasks
        for i in range(self.num_workers):
            worker_task = asyncio.create_task(
                self._worker(worker_id=i),
                name=f"consumer-worker-{i}"
            )
            self.workers.append(worker_task)

        # Start monitoring task
        monitor_task = asyncio.create_task(
            self._monitor_lag(),
            name="consumer-monitor"
        )
        self.workers.append(monitor_task)

        logger.info(f"🚀 Started {self.num_workers} consumer workers + 1 monitor")

    async def stop(self) -> None:
        """Stop all workers gracefully"""
        logger.info("Stopping optimized consumer...")
        self.running = False

        # Cancel all worker tasks
        for worker in self.workers:
            worker.cancel()

        # Wait for workers to finish
        await asyncio.gather(*self.workers, return_exceptions=True)

        self.workers.clear()
        logger.info("✅ All workers stopped")

    async def _worker(self, worker_id: int) -> None:
        """
        Worker coroutine - processes events from stream

        Args:
            worker_id: Unique worker identifier
        """
        consumer_name = f"{settings.REDIS_CONSUMER_NAME}-{worker_id}"
        logger.info(f"Worker {worker_id} started: {consumer_name}")

        redis_client = await get_redis()

        while self.running:
            try:
                # Read batch of events
                messages = await redis_client.xreadgroup(
                    groupname=self.consumer_group,
                    consumername=consumer_name,
                    streams={self.stream_name: ">"},
                    count=self.batch_size,
                    block=self.block_time
                )

                if not messages:
                    continue

                # Process batch
                await self._process_batch(
                    redis_client,
                    worker_id,
                    messages
                )

            except asyncio.CancelledError:
                logger.info(f"Worker {worker_id} cancelled")
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}", exc_info=True)
                await asyncio.sleep(5)  # Backoff on error

        logger.info(f"Worker {worker_id} stopped")

    async def _process_batch(
        self,
        redis_client: redis.Redis,
        worker_id: int,
        messages: List
    ) -> None:
        """
        Process batch of messages

        Args:
            redis_client: Redis client
            worker_id: Worker ID
            messages: List of messages from stream
        """
        for stream_name, stream_messages in messages:
            # Collect events for bulk insert
            events_to_insert = []

            for message_id, data in stream_messages:
                try:
                    # Deserialize event
                    event_data = self._deserialize_event(data)

                    # Create EventLog instance
                    event_log = EventLog(
                        event_id=event_data.get("event_id", message_id),
                        event_type=event_data["event_type"],
                        service_name=event_data["service_name"],
                        service_version=event_data.get("service_version"),
                        payload=event_data["payload"],
                        metadata=event_data.get("metadata", {}),
                        status="pending",
                        created_at=datetime.utcnow()
                    )

                    events_to_insert.append(event_log)

                    # Acknowledge message
                    await redis_client.xack(
                        self.stream_name,
                        self.consumer_group,
                        message_id
                    )

                    self.events_processed += 1

                except Exception as e:
                    logger.error(f"Worker {worker_id} failed to process message {message_id}: {e}")
                    self.events_failed += 1
                    # Move to DLQ
                    await self._handle_failed_message(redis_client, message_id, data, str(e))

            # Bulk insert to database
            if events_to_insert:
                await self._bulk_insert_events(events_to_insert)

                logger.debug(
                    f"Worker {worker_id}: Processed {len(events_to_insert)} events "
                    f"(total: {self.events_processed}, failed: {self.events_failed})"
                )

    async def _bulk_insert_events(self, events: List[EventLog]) -> None:
        """
        Bulk insert events to database

        Args:
            events: List of EventLog instances
        """
        try:
            async with AsyncSessionLocal() as db:
                db.add_all(events)
                await db.commit()

        except Exception as e:
            logger.error(f"Bulk insert failed: {e}", exc_info=True)
            raise

    def _deserialize_event(self, data: dict) -> dict:
        """
        Deserialize event data from Redis

        Args:
            data: Raw data from Redis Stream

        Returns:
            Deserialized event dictionary
        """
        import json

        event = {}
        for key, value in data.items():
            if key in ["payload", "metadata"] and isinstance(value, str):
                event[key] = json.loads(value)
            else:
                event[key] = value

        # Validate required fields
        required_fields = ["event_type", "service_name", "payload"]
        for field in required_fields:
            if field not in event:
                raise ValueError(f"Missing required field: {field}")

        return event

    async def _handle_failed_message(
        self,
        redis_client: redis.Redis,
        message_id: str,
        data: dict,
        error: str
    ) -> None:
        """
        Handle failed message - send to DLQ

        Args:
            redis_client: Redis client
            message_id: Message ID
            data: Event data
            error: Error message
        """
        try:
            dlq_stream = f"{self.stream_name}:dlq"

            dlq_data = {
                **data,
                "original_message_id": message_id,
                "error": error,
                "failed_at": datetime.utcnow().isoformat()
            }

            await redis_client.xadd(dlq_stream, dlq_data)

            # Acknowledge original message
            await redis_client.xack(
                self.stream_name,
                self.consumer_group,
                message_id
            )

            logger.warning(f"⚠️  Message {message_id} moved to DLQ")

        except Exception as e:
            logger.error(f"Failed to handle DLQ: {e}")

    async def _monitor_lag(self) -> None:
        """Monitor stream lag and log metrics"""
        redis_client = await get_redis()

        while self.running:
            try:
                await asyncio.sleep(60)  # Check every minute

                # Get stream info
                stream_info = await redis_client.xinfo_stream(self.stream_name)
                stream_length = stream_info.get('length', 0)

                # Get consumer group info
                groups_info = await redis_client.xinfo_groups(self.stream_name)

                for group in groups_info:
                    if group['name'] == self.consumer_group:
                        pending = group.get('pending', 0)
                        lag = stream_length - pending

                        logger.info(
                            f"📊 Stream metrics: "
                            f"length={stream_length}, "
                            f"pending={pending}, "
                            f"lag={lag}, "
                            f"processed={self.events_processed}, "
                            f"failed={self.events_failed}"
                        )

                        # Alert if lag is high
                        if lag > 1000:
                            logger.warning(
                                f"⚠️  High lag detected: {lag} events behind"
                            )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                await asyncio.sleep(60)

    async def get_metrics(self) -> dict:
        """
        Get consumer performance metrics

        Returns:
            Dictionary with metrics
        """
        redis_client = await get_redis()

        try:
            stream_info = await redis_client.xinfo_stream(self.stream_name)
            stream_length = stream_info.get('length', 0)

            groups_info = await redis_client.xinfo_groups(self.stream_name)
            pending = 0
            for group in groups_info:
                if group['name'] == self.consumer_group:
                    pending = group.get('pending', 0)
                    break

            return {
                "workers": self.num_workers,
                "running": self.running,
                "events_processed": self.events_processed,
                "events_failed": self.events_failed,
                "stream_length": stream_length,
                "pending": pending,
                "lag": stream_length - pending,
                "success_rate": (
                    (self.events_processed / (self.events_processed + self.events_failed) * 100)
                    if (self.events_processed + self.events_failed) > 0
                    else 100.0
                )
            }

        except Exception as e:
            logger.error(f"Failed to get metrics: {e}")
            return {
                "workers": self.num_workers,
                "running": self.running,
                "error": str(e)
            }


# Global optimized consumer instance
optimized_consumer = OptimizedStreamConsumer()
