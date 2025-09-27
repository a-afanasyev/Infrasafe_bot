"""
Request Number Generation Service
UK Management Bot - Request Management System

Redis-based atomic request number generation with database fallback.
Implements YYMMDD-NNN format with guaranteed uniqueness.
"""

import asyncio
import logging
from datetime import datetime, date
from typing import Optional, Tuple
from dataclasses import dataclass
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, func
from app.core.config import settings
from app.models import Request

logger = logging.getLogger(__name__)


@dataclass
class NumberGenerationResult:
    """Result of request number generation"""
    request_number: str
    method: str  # "redis", "database", "fallback"
    counter: int
    prefix: str


class RequestNumberService:
    """
    Request number generation service with Redis + Database fallback

    Features:
    - YYMMDD-NNN format (e.g., '250927-001')
    - Redis-based atomic counters for performance
    - Database fallback for reliability
    - Unique constraint validation
    - Thread-safe operations
    """

    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self._redis_connected = False

    async def initialize(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_keepalive=True,
                health_check_interval=30,
                retry_on_timeout=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )

            # Test connection
            await self.redis_client.ping()
            self._redis_connected = True
            logger.info("RequestNumberService: Redis connection established")

        except Exception as e:
            logger.warning(f"RequestNumberService: Redis connection failed: {e}")
            self.redis_client = None
            self._redis_connected = False

    async def close(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
            self._redis_connected = False
            logger.info("RequestNumberService: Redis connection closed")

    def _generate_date_prefix(self, target_date: Optional[datetime] = None) -> str:
        """
        Generate YYMMDD prefix for request number

        Args:
            target_date: Date to use (defaults to today)

        Returns:
            String in YYMMDD format
        """
        if target_date is None:
            target_date = datetime.now()

        return target_date.strftime("%y%m%d")

    def _get_redis_key(self, date_prefix: str) -> str:
        """Get Redis key for date prefix"""
        return f"{settings.REDIS_REQUEST_NUMBER_KEY}:{date_prefix}"

    async def _generate_via_redis(self, date_prefix: str) -> Optional[int]:
        """
        Generate counter via Redis atomic increment

        Args:
            date_prefix: YYMMDD prefix

        Returns:
            Counter value or None if failed
        """
        if not self._redis_connected or not self.redis_client:
            return None

        try:
            redis_key = self._get_redis_key(date_prefix)

            # Atomic increment with expiry
            async with self.redis_client.pipeline() as pipe:
                await pipe.incr(redis_key)
                await pipe.expire(redis_key, settings.REQUEST_NUMBER_REDIS_TTL)
                results = await pipe.execute()

            counter = results[0]

            # Check if counter exceeds limit
            if counter > settings.REQUEST_NUMBER_COUNTER_MAX:
                logger.error(f"Redis counter exceeded limit for {date_prefix}: {counter}")
                return None

            logger.debug(f"Redis generated counter {counter} for prefix {date_prefix}")
            return counter

        except Exception as e:
            logger.error(f"Redis number generation failed for {date_prefix}: {e}")
            return None

    async def _validate_uniqueness_db(
        self,
        request_number: str,
        db_session: AsyncSession
    ) -> bool:
        """
        Validate request number uniqueness in database

        Args:
            request_number: Generated request number
            db_session: Database session

        Returns:
            True if unique, False if exists
        """
        try:
            query = select(func.count(Request.request_number)).where(
                Request.request_number == request_number
            )
            result = await db_session.execute(query)
            count = result.scalar()

            is_unique = count == 0
            if not is_unique:
                logger.warning(f"Request number {request_number} already exists in database")

            return is_unique

        except Exception as e:
            logger.error(f"Database uniqueness check failed for {request_number}: {e}")
            return False

    async def _generate_via_database(
        self,
        date_prefix: str,
        db_session: AsyncSession
    ) -> Optional[int]:
        """
        Generate counter via database query

        Args:
            date_prefix: YYMMDD prefix
            db_session: Database session

        Returns:
            Counter value or None if failed
        """
        try:
            # Find maximum counter for the date prefix
            query = text("""
                SELECT COALESCE(MAX(
                    CAST(SUBSTRING(request_number FROM 8) AS INTEGER)
                ), 0) + 1 as next_counter
                FROM requests
                WHERE request_number LIKE :prefix || '-%'
                AND NOT is_deleted
            """)

            result = await db_session.execute(query, {"prefix": date_prefix})
            next_counter = result.scalar()

            # Check if counter exceeds limit
            if next_counter > settings.REQUEST_NUMBER_COUNTER_MAX:
                logger.error(f"Database counter exceeded limit for {date_prefix}: {next_counter}")
                return None

            logger.debug(f"Database generated counter {next_counter} for prefix {date_prefix}")
            return next_counter

        except Exception as e:
            logger.error(f"Database number generation failed for {date_prefix}: {e}")
            return None

    async def _retry_with_backoff(
        self,
        func,
        *args,
        max_retries: int = 3,
        base_delay: float = 0.1,
        **kwargs
    ):
        """Retry function with exponential backoff"""
        for attempt in range(max_retries):
            try:
                result = await func(*args, **kwargs)
                if result is not None:
                    return result
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                logger.warning(f"Attempt {attempt + 1} failed: {e}")

            # Exponential backoff
            delay = base_delay * (2 ** attempt)
            await asyncio.sleep(delay)

        return None

    async def generate_next_number(
        self,
        db_session: AsyncSession,
        target_date: Optional[datetime] = None,
        max_attempts: int = 10
    ) -> NumberGenerationResult:
        """
        Generate next available request number with guaranteed uniqueness

        Args:
            db_session: Database session for validation and fallback
            target_date: Date to use (defaults to today)
            max_attempts: Maximum generation attempts

        Returns:
            NumberGenerationResult with generated number and metadata

        Raises:
            ValueError: If unable to generate unique number
        """
        date_prefix = self._generate_date_prefix(target_date)

        for attempt in range(max_attempts):
            try:
                # Strategy 1: Try Redis first
                if self._redis_connected:
                    counter = await self._retry_with_backoff(
                        self._generate_via_redis, date_prefix
                    )

                    if counter is not None:
                        request_number = f"{date_prefix}-{counter:03d}"

                        # Validate uniqueness in database
                        if await self._validate_uniqueness_db(request_number, db_session):
                            logger.info(f"Generated request number via Redis: {request_number}")
                            return NumberGenerationResult(
                                request_number=request_number,
                                method="redis",
                                counter=counter,
                                prefix=date_prefix
                            )
                        else:
                            logger.warning(f"Redis generated duplicate: {request_number}")

                # Strategy 2: Database fallback
                counter = await self._retry_with_backoff(
                    self._generate_via_database, date_prefix, db_session
                )

                if counter is not None:
                    request_number = f"{date_prefix}-{counter:03d}"

                    # Double-check uniqueness
                    if await self._validate_uniqueness_db(request_number, db_session):
                        logger.info(f"Generated request number via database: {request_number}")

                        # Update Redis counter to sync
                        if self._redis_connected:
                            try:
                                redis_key = self._get_redis_key(date_prefix)
                                await self.redis_client.set(
                                    redis_key,
                                    counter,
                                    ex=settings.REQUEST_NUMBER_REDIS_TTL
                                )
                            except Exception as e:
                                logger.warning(f"Failed to sync Redis counter: {e}")

                        return NumberGenerationResult(
                            request_number=request_number,
                            method="database",
                            counter=counter,
                            prefix=date_prefix
                        )

                logger.warning(f"Generation attempt {attempt + 1} failed, retrying...")
                await asyncio.sleep(0.1 * (attempt + 1))  # Progressive delay

            except Exception as e:
                logger.error(f"Number generation attempt {attempt + 1} error: {e}")
                if attempt == max_attempts - 1:
                    raise
                await asyncio.sleep(0.1 * (attempt + 1))

        # Final fallback: Use timestamp-based counter
        timestamp_suffix = int(datetime.now().timestamp() * 1000) % 1000
        fallback_number = f"{date_prefix}-{timestamp_suffix:03d}"

        logger.error(f"Using timestamp fallback: {fallback_number}")
        return NumberGenerationResult(
            request_number=fallback_number,
            method="fallback",
            counter=timestamp_suffix,
            prefix=date_prefix
        )

    async def get_daily_stats(
        self,
        db_session: AsyncSession,
        target_date: Optional[date] = None
    ) -> dict:
        """
        Get daily request number statistics

        Args:
            db_session: Database session
            target_date: Date to check (defaults to today)

        Returns:
            Dictionary with statistics
        """
        if target_date is None:
            target_date = date.today()

        date_prefix = target_date.strftime("%y%m%d")

        try:
            # Get count from database
            query = text("""
                SELECT COUNT(*) as db_count,
                       COALESCE(MAX(
                           CAST(SUBSTRING(request_number FROM 8) AS INTEGER)
                       ), 0) as max_counter
                FROM requests
                WHERE request_number LIKE :prefix || '-%'
                AND NOT is_deleted
            """)

            result = await db_session.execute(query, {"prefix": date_prefix})
            row = result.fetchone()
            db_count = row.db_count if row else 0
            max_counter = row.max_counter if row else 0

            # Get Redis counter
            redis_counter = 0
            if self._redis_connected:
                try:
                    redis_key = self._get_redis_key(date_prefix)
                    redis_counter = await self.redis_client.get(redis_key)
                    redis_counter = int(redis_counter) if redis_counter else 0
                except Exception as e:
                    logger.warning(f"Failed to get Redis stats: {e}")

            return {
                "date": target_date.isoformat(),
                "prefix": date_prefix,
                "database_count": db_count,
                "max_counter": max_counter,
                "redis_counter": redis_counter,
                "redis_connected": self._redis_connected,
                "available_numbers": settings.REQUEST_NUMBER_COUNTER_MAX - max_counter
            }

        except Exception as e:
            logger.error(f"Failed to get daily stats: {e}")
            return {
                "date": target_date.isoformat(),
                "prefix": date_prefix,
                "error": str(e)
            }

    async def reset_daily_counter(
        self,
        target_date: Optional[date] = None
    ) -> bool:
        """
        Reset Redis counter for a specific date (admin function)

        Args:
            target_date: Date to reset (defaults to today)

        Returns:
            True if successful, False otherwise
        """
        if not self._redis_connected:
            logger.warning("Cannot reset counter: Redis not connected")
            return False

        if target_date is None:
            target_date = date.today()

        date_prefix = target_date.strftime("%y%m%d")

        try:
            redis_key = self._get_redis_key(date_prefix)
            await self.redis_client.delete(redis_key)
            logger.info(f"Reset Redis counter for {date_prefix}")
            return True

        except Exception as e:
            logger.error(f"Failed to reset counter for {date_prefix}: {e}")
            return False


# Global service instance
request_number_service = RequestNumberService()