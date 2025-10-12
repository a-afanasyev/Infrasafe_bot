"""
Real-time KPI Service - 5-Second Interval Metrics

Sprint 16-18: Analytics Service
Week 5, Task 5.3: Real-time KPIs Implementation
Author: Analytics Team
Date: October 6, 2025

Real-time metrics updated every 5 seconds:
1. Active Shifts (current)
2. Requests in Progress (current)
3. Active Users (online in last 5 minutes)
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from redis import asyncio as aioredis
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import AsyncSessionLocal
from models.event_log import EventLog

logger = logging.getLogger(__name__)


class RealtimeKPIService:
    """
    Service for calculating real-time KPIs with 5-second update intervals.

    These metrics are optimized for low latency and high refresh rates.
    Uses Redis caching with short TTL (5 seconds) for real-time updates.
    """

    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client
        self.cache_ttl = 5  # 5 seconds TTL for real-time metrics

    async def get_active_shifts_realtime(self) -> Dict[str, Any]:
        """
        Get current number of active shifts.

        Active = Created - Completed - Cancelled

        This is calculated from the last 24 hours of events to avoid
        counting very old shifts.

        Returns:
            {
                "metric": "active_shifts",
                "value": int,
                "unit": "count",
                "timestamp": str,
                "type": "realtime"
            }
        """
        cache_key = "realtime:active_shifts"

        # Check cache first
        cached = await self.redis.get(cache_key)
        if cached:
            import json
            return json.loads(cached)

        # Calculate from events
        async with AsyncSessionLocal() as db:
            # Time window: last 24 hours
            since = datetime.utcnow() - timedelta(hours=24)

            # Count shift events by type
            result = await db.execute(
                select(
                    EventLog.event_type,
                    func.count(EventLog.id).label("count")
                )
                .where(
                    and_(
                        EventLog.event_type.in_([
                            "shift.created",
                            "shift.completed",
                            "shift.cancelled"
                        ]),
                        EventLog.created_at >= since,
                        EventLog.status == "processed"
                    )
                )
                .group_by(EventLog.event_type)
            )

            counts = {row.event_type: row.count for row in result}

            created = counts.get("shift.created", 0)
            completed = counts.get("shift.completed", 0)
            cancelled = counts.get("shift.cancelled", 0)

            # Active shifts = created - completed - cancelled
            active = max(0, created - completed - cancelled)

            response = {
                "metric": "active_shifts",
                "value": active,
                "unit": "count",
                "timestamp": datetime.utcnow().isoformat(),
                "type": "realtime",
                "breakdown": {
                    "created": created,
                    "completed": completed,
                    "cancelled": cancelled
                }
            }

            # Cache for 5 seconds
            import json
            await self.redis.setex(
                cache_key,
                self.cache_ttl,
                json.dumps(response)
            )

            logger.debug(f"📊 Active shifts: {active}")
            return response

    async def get_requests_in_progress_realtime(self) -> Dict[str, Any]:
        """
        Get current number of requests in progress.

        In Progress = Created - Completed - Cancelled - Rejected

        Returns:
            {
                "metric": "requests_in_progress",
                "value": int,
                "unit": "count",
                "timestamp": str,
                "type": "realtime"
            }
        """
        cache_key = "realtime:requests_in_progress"

        # Check cache first
        cached = await self.redis.get(cache_key)
        if cached:
            import json
            return json.loads(cached)

        # Calculate from events
        async with AsyncSessionLocal() as db:
            # Time window: last 7 days (requests can take longer)
            since = datetime.utcnow() - timedelta(days=7)

            # Count request events by type
            result = await db.execute(
                select(
                    EventLog.event_type,
                    func.count(EventLog.id).label("count")
                )
                .where(
                    and_(
                        EventLog.event_type.in_([
                            "request.created",
                            "request.completed",
                            "request.cancelled",
                            "request.rejected"
                        ]),
                        EventLog.created_at >= since,
                        EventLog.status == "processed"
                    )
                )
                .group_by(EventLog.event_type)
            )

            counts = {row.event_type: row.count for row in result}

            created = counts.get("request.created", 0)
            completed = counts.get("request.completed", 0)
            cancelled = counts.get("request.cancelled", 0)
            rejected = counts.get("request.rejected", 0)

            # In progress = created - completed - cancelled - rejected
            in_progress = max(0, created - completed - cancelled - rejected)

            response = {
                "metric": "requests_in_progress",
                "value": in_progress,
                "unit": "count",
                "timestamp": datetime.utcnow().isoformat(),
                "type": "realtime",
                "breakdown": {
                    "created": created,
                    "completed": completed,
                    "cancelled": cancelled,
                    "rejected": rejected
                }
            }

            # Cache for 5 seconds
            import json
            await self.redis.setex(
                cache_key,
                self.cache_ttl,
                json.dumps(response)
            )

            logger.debug(f"📊 Requests in progress: {in_progress}")
            return response

    async def get_active_users_realtime(self) -> Dict[str, Any]:
        """
        Get number of active users (online in last 5 minutes).

        Users are considered active if they triggered any event
        in the last 5 minutes.

        Returns:
            {
                "metric": "active_users",
                "value": int,
                "unit": "count",
                "timestamp": str,
                "type": "realtime"
            }
        """
        cache_key = "realtime:active_users"

        # Check cache first
        cached = await self.redis.get(cache_key)
        if cached:
            import json
            return json.loads(cached)

        # Calculate from events
        async with AsyncSessionLocal() as db:
            # Time window: last 5 minutes
            since = datetime.utcnow() - timedelta(minutes=5)

            # Count distinct user_ids from event payloads
            # Events should have user_id in payload
            result = await db.execute(
                select(func.count(func.distinct(
                    func.jsonb_extract_path_text(EventLog.payload, "user_id")
                )))
                .where(
                    and_(
                        EventLog.created_at >= since,
                        EventLog.status == "processed",
                        func.jsonb_extract_path_text(EventLog.payload, "user_id").isnot(None)
                    )
                )
            )

            active_users = result.scalar() or 0

            response = {
                "metric": "active_users",
                "value": active_users,
                "unit": "count",
                "timestamp": datetime.utcnow().isoformat(),
                "type": "realtime",
                "time_window": "5 minutes"
            }

            # Cache for 5 seconds
            import json
            await self.redis.setex(
                cache_key,
                self.cache_ttl,
                json.dumps(response)
            )

            logger.debug(f"📊 Active users: {active_users}")
            return response

    async def get_all_realtime_metrics(self) -> Dict[str, Any]:
        """
        Get all real-time metrics in a single call.

        Returns:
            {
                "metrics": {
                    "active_shifts": {...},
                    "requests_in_progress": {...},
                    "active_users": {...}
                },
                "timestamp": str,
                "type": "realtime_summary"
            }
        """
        # Fetch all metrics concurrently
        import asyncio

        active_shifts, requests_in_progress, active_users = await asyncio.gather(
            self.get_active_shifts_realtime(),
            self.get_requests_in_progress_realtime(),
            self.get_active_users_realtime()
        )

        return {
            "metrics": {
                "active_shifts": active_shifts,
                "requests_in_progress": requests_in_progress,
                "active_users": active_users
            },
            "timestamp": datetime.utcnow().isoformat(),
            "type": "realtime_summary"
        }

    async def clear_cache(self) -> None:
        """
        Clear all real-time metric caches.

        Useful for testing or forcing immediate recalculation.
        """
        keys = [
            "realtime:active_shifts",
            "realtime:requests_in_progress",
            "realtime:active_users"
        ]

        for key in keys:
            await self.redis.delete(key)

        logger.info("🗑️ Cleared real-time metric caches")

    async def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get statistics about cache usage for real-time metrics.

        Returns:
            Cache hit/miss statistics
        """
        keys = [
            "realtime:active_shifts",
            "realtime:requests_in_progress",
            "realtime:active_users"
        ]

        stats = {}
        for key in keys:
            ttl = await self.redis.ttl(key)
            exists = await self.redis.exists(key)

            stats[key] = {
                "cached": bool(exists),
                "ttl_remaining": ttl if ttl > 0 else 0
            }

        return {
            "cache_stats": stats,
            "cache_ttl": self.cache_ttl,
            "timestamp": datetime.utcnow().isoformat()
        }


# Singleton instance (optional)
_realtime_service: Optional[RealtimeKPIService] = None


def get_realtime_service(redis_client: aioredis.Redis) -> RealtimeKPIService:
    """
    Get or create RealtimeKPIService singleton instance.

    Args:
        redis_client: Redis client

    Returns:
        RealtimeKPIService instance
    """
    global _realtime_service
    if _realtime_service is None:
        _realtime_service = RealtimeKPIService(redis_client)
    return _realtime_service
