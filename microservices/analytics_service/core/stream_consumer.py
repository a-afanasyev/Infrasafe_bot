"""
Redis Streams Consumer

Task 1.3: Redis Streams Setup
Consumes events from Redis Streams and processes them
"""

import asyncio
import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from core.redis_client import get_redis
from db.session import AsyncSessionLocal
from models.event_log import EventLog

logger = logging.getLogger(__name__)


class StreamConsumer:
    """
    Redis Streams Consumer

    Consumes events from Redis Stream and stores them in EventLog
    """

    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.stream_name = settings.REDIS_STREAM_NAME
        self.consumer_group = settings.REDIS_CONSUMER_GROUP
        self.consumer_name = settings.REDIS_CONSUMER_NAME
        self.block_time = settings.REDIS_BLOCK_TIME
        self.batch_size = settings.REDIS_BATCH_SIZE
        self.running = False

    async def initialize(self) -> None:
        """Initialize consumer and create consumer group if not exists"""
        try:
            self.redis_client = await get_redis()

            # Create consumer group (ignore if already exists)
            try:
                await self.redis_client.xgroup_create(
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

            logger.info(f"✅ Stream consumer initialized: {self.consumer_name}")

        except Exception as e:
            logger.error(f"❌ Failed to initialize stream consumer: {e}")
            raise

    async def consume_events(self) -> None:
        """
        Main consumer loop

        Reads events from Redis Stream and processes them
        """
        if not self.redis_client:
            await self.initialize()

        self.running = True
        logger.info(f"🚀 Starting event consumer on stream '{self.stream_name}'...")

        while self.running:
            try:
                # Read from stream
                messages = await self.redis_client.xreadgroup(
                    groupname=self.consumer_group,
                    consumername=self.consumer_name,
                    streams={self.stream_name: ">"},
                    count=self.batch_size,
                    block=self.block_time
                )

                if messages:
                    await self._process_messages(messages)

            except asyncio.CancelledError:
                logger.info("Consumer cancelled")
                break
            except Exception as e:
                logger.error(f"Error in consumer loop: {e}", exc_info=True)
                await asyncio.sleep(5)  # Wait before retry

        logger.info("🛑 Event consumer stopped")

    async def _process_messages(self, messages: List) -> None:
        """
        Process batch of messages from stream

        Args:
            messages: List of (stream_name, [(message_id, data)])
        """
        for stream_name, stream_messages in messages:
            for message_id, data in stream_messages:
                try:
                    await self._process_single_message(message_id, data)

                    # Acknowledge message
                    await self.redis_client.xack(
                        self.stream_name,
                        self.consumer_group,
                        message_id
                    )

                except Exception as e:
                    logger.error(f"Failed to process message {message_id}: {e}")
                    await self._handle_failed_message(message_id, data, str(e))

    async def _process_single_message(
        self,
        message_id: str,
        data: Dict[str, Any]
    ) -> None:
        """
        Process single event message

        Args:
            message_id: Redis stream message ID
            data: Event data
        """
        try:
            # Deserialize event
            event = self._deserialize_event(data)

            # Store in database
            async with AsyncSessionLocal() as db:
                event_log = EventLog(
                    event_id=event.get("event_id", message_id),
                    event_type=event["event_type"],
                    service_name=event["service_name"],
                    service_version=event.get("service_version"),
                    payload=event["payload"],
                    metadata=event.get("metadata", {}),
                    status="pending",
                    created_at=datetime.utcnow()
                )

                db.add(event_log)
                await db.commit()

                logger.debug(
                    f"✅ Event stored: {event['event_type']} "
                    f"from {event['service_name']}"
                )

        except Exception as e:
            logger.error(f"Error processing event: {e}", exc_info=True)
            raise

    def _deserialize_event(self, data: Dict[str, str]) -> Dict[str, Any]:
        """
        Deserialize event data from Redis

        Args:
            data: Raw data from Redis Stream

        Returns:
            Deserialized event dictionary
        """
        try:
            # Parse JSON fields if they're strings
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

        except Exception as e:
            logger.error(f"Event deserialization failed: {e}")
            raise

    async def _handle_failed_message(
        self,
        message_id: str,
        data: Dict[str, Any],
        error: str
    ) -> None:
        """
        Handle failed message - send to Dead Letter Queue

        Args:
            message_id: Message ID
            data: Event data
            error: Error message
        """
        try:
            dlq_stream = f"{self.stream_name}:dlq"

            # Add to DLQ with error info
            dlq_data = {
                **data,
                "original_message_id": message_id,
                "error": error,
                "failed_at": datetime.utcnow().isoformat()
            }

            await self.redis_client.xadd(dlq_stream, dlq_data)

            logger.warning(f"⚠️  Message {message_id} moved to DLQ")

            # Still acknowledge original message to prevent reprocessing
            await self.redis_client.xack(
                self.stream_name,
                self.consumer_group,
                message_id
            )

        except Exception as e:
            logger.error(f"Failed to handle DLQ: {e}")

    async def stop(self) -> None:
        """Stop consumer"""
        self.running = False
        logger.info("Stopping consumer...")


# Global consumer instance
stream_consumer = StreamConsumer()
