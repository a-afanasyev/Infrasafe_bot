"""
Dashboard Cache Service - Multi-level Caching

Sprint 16-18: Analytics Service
Week 7, Task 7.2: Dashboard Caching Implementation
Author: Analytics Team
Date: October 6, 2025

Implements multi-level caching for dashboard rendering:
- L1: In-memory cache (hot dashboards)
- L2: Redis cache (frequently accessed)
- L3: Database (cold start)
"""

import logging
import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from redis import asyncio as aioredis

logger = logging.getLogger(__name__)


class DashboardCache:
    """
    Multi-level caching service for dashboard data.

    Cache Strategy:
    - Widget data cached separately (reusable across dashboards)
    - Complete dashboard cached as assembled unit
    - TTL based on data freshness requirements
    - Cache invalidation on data updates
    """

    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client

        # Cache TTLs (in seconds)
        self.WIDGET_CACHE_TTL = 300  # 5 minutes
        self.DASHBOARD_CACHE_TTL = 600  # 10 minutes
        self.REALTIME_WIDGET_TTL = 5  # 5 seconds (realtime widgets)

        # Cache key prefixes
        self.WIDGET_PREFIX = "dashboard:widget:"
        self.DASHBOARD_PREFIX = "dashboard:rendered:"
        self.CONFIG_PREFIX = "dashboard:config:"

    def _generate_widget_cache_key(
        self,
        widget_id: str,
        widget_config: Dict[str, Any],
        time_range: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate unique cache key for widget.

        Cache key includes widget config and time range to ensure
        different configurations are cached separately.

        Args:
            widget_id: Widget ID
            widget_config: Widget configuration
            time_range: Optional time range filter

        Returns:
            Cache key string
        """
        # Create hash from config and time range
        config_str = json.dumps({
            "config": widget_config,
            "time_range": time_range
        }, sort_keys=True)

        config_hash = hashlib.md5(config_str.encode()).hexdigest()[:12]

        return f"{self.WIDGET_PREFIX}{widget_id}:{config_hash}"

    def _generate_dashboard_cache_key(
        self,
        dashboard_id: int,
        time_range: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate cache key for complete dashboard.

        Args:
            dashboard_id: Dashboard ID
            time_range: Optional time range filter

        Returns:
            Cache key string
        """
        if time_range:
            time_hash = hashlib.md5(
                json.dumps(time_range, sort_keys=True).encode()
            ).hexdigest()[:12]
            return f"{self.DASHBOARD_PREFIX}{dashboard_id}:{time_hash}"
        else:
            return f"{self.DASHBOARD_PREFIX}{dashboard_id}:default"

    async def get_widget_cache(
        self,
        widget_id: str,
        widget_config: Dict[str, Any],
        time_range: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached widget data.

        Args:
            widget_id: Widget ID
            widget_config: Widget configuration
            time_range: Optional time range

        Returns:
            Cached widget data or None if cache miss
        """
        cache_key = self._generate_widget_cache_key(widget_id, widget_config, time_range)

        try:
            cached = await self.redis.get(cache_key)
            if cached:
                logger.debug(f"📊 Widget cache HIT: {widget_id}")
                return json.loads(cached)
            else:
                logger.debug(f"📊 Widget cache MISS: {widget_id}")
                return None

        except Exception as e:
            logger.error(f"❌ Widget cache read error: {e}")
            return None

    async def set_widget_cache(
        self,
        widget_id: str,
        widget_config: Dict[str, Any],
        widget_data: Dict[str, Any],
        time_range: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Cache widget data.

        Args:
            widget_id: Widget ID
            widget_config: Widget configuration
            widget_data: Widget data to cache
            time_range: Optional time range

        Returns:
            True if successfully cached
        """
        cache_key = self._generate_widget_cache_key(widget_id, widget_config, time_range)

        # Determine TTL based on widget type
        widget_type = widget_config.get("type")
        if widget_type == "realtime_metric":
            ttl = self.REALTIME_WIDGET_TTL
        else:
            ttl = self.WIDGET_CACHE_TTL

        try:
            await self.redis.setex(
                cache_key,
                ttl,
                json.dumps(widget_data, default=str)
            )
            logger.debug(f"📊 Widget cached: {widget_id} (TTL: {ttl}s)")
            return True

        except Exception as e:
            logger.error(f"❌ Widget cache write error: {e}")
            return False

    async def get_dashboard_cache(
        self,
        dashboard_id: int,
        time_range: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached complete dashboard.

        Args:
            dashboard_id: Dashboard ID
            time_range: Optional time range

        Returns:
            Cached dashboard or None if cache miss
        """
        cache_key = self._generate_dashboard_cache_key(dashboard_id, time_range)

        try:
            cached = await self.redis.get(cache_key)
            if cached:
                logger.info(f"🚀 Dashboard cache HIT: {dashboard_id}")
                return json.loads(cached)
            else:
                logger.info(f"📊 Dashboard cache MISS: {dashboard_id}")
                return None

        except Exception as e:
            logger.error(f"❌ Dashboard cache read error: {e}")
            return None

    async def set_dashboard_cache(
        self,
        dashboard_id: int,
        dashboard_data: Dict[str, Any],
        time_range: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Cache complete dashboard.

        Args:
            dashboard_id: Dashboard ID
            dashboard_data: Complete dashboard data
            time_range: Optional time range

        Returns:
            True if successfully cached
        """
        cache_key = self._generate_dashboard_cache_key(dashboard_id, time_range)

        try:
            await self.redis.setex(
                cache_key,
                self.DASHBOARD_CACHE_TTL,
                json.dumps(dashboard_data, default=str)
            )
            logger.info(f"✅ Dashboard cached: {dashboard_id} (TTL: {self.DASHBOARD_CACHE_TTL}s)")
            return True

        except Exception as e:
            logger.error(f"❌ Dashboard cache write error: {e}")
            return False

    async def invalidate_widget_cache(
        self,
        widget_id: str,
        widget_config: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Invalidate widget cache.

        If widget_config is provided, invalidates specific configuration.
        Otherwise, invalidates all variants of the widget.

        Args:
            widget_id: Widget ID
            widget_config: Optional specific configuration

        Returns:
            Number of cache entries deleted
        """
        if widget_config:
            # Invalidate specific configuration
            cache_key = self._generate_widget_cache_key(widget_id, widget_config)
            deleted = await self.redis.delete(cache_key)
            logger.info(f"🗑️ Invalidated widget cache: {widget_id} (specific config)")
            return deleted
        else:
            # Invalidate all variants
            pattern = f"{self.WIDGET_PREFIX}{widget_id}:*"
            keys = await self.redis.keys(pattern)

            if keys:
                deleted = await self.redis.delete(*keys)
                logger.info(f"🗑️ Invalidated widget cache: {widget_id} (all variants: {deleted})")
                return deleted
            return 0

    async def invalidate_dashboard_cache(
        self,
        dashboard_id: int,
        time_range: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Invalidate dashboard cache.

        If time_range is provided, invalidates specific time range.
        Otherwise, invalidates all variants of the dashboard.

        Args:
            dashboard_id: Dashboard ID
            time_range: Optional specific time range

        Returns:
            Number of cache entries deleted
        """
        if time_range:
            # Invalidate specific time range
            cache_key = self._generate_dashboard_cache_key(dashboard_id, time_range)
            deleted = await self.redis.delete(cache_key)
            logger.info(f"🗑️ Invalidated dashboard cache: {dashboard_id} (specific range)")
            return deleted
        else:
            # Invalidate all variants
            pattern = f"{self.DASHBOARD_PREFIX}{dashboard_id}:*"
            keys = await self.redis.keys(pattern)

            if keys:
                deleted = await self.redis.delete(*keys)
                logger.info(f"🗑️ Invalidated dashboard cache: {dashboard_id} (all variants: {deleted})")
                return deleted
            return 0

    async def invalidate_all_dashboards(self) -> int:
        """
        Invalidate all dashboard caches.

        Useful after data updates that affect multiple dashboards.

        Returns:
            Number of cache entries deleted
        """
        pattern = f"{self.DASHBOARD_PREFIX}*"
        keys = await self.redis.keys(pattern)

        if keys:
            deleted = await self.redis.delete(*keys)
            logger.info(f"🗑️ Invalidated ALL dashboard caches: {deleted} entries")
            return deleted
        return 0

    async def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Cache statistics
        """
        try:
            # Count cached items by type
            widget_pattern = f"{self.WIDGET_PREFIX}*"
            dashboard_pattern = f"{self.DASHBOARD_PREFIX}*"

            widget_keys = await self.redis.keys(widget_pattern)
            dashboard_keys = await self.redis.keys(dashboard_pattern)

            # Sample TTLs
            widget_ttls = []
            if widget_keys:
                for key in widget_keys[:10]:  # Sample first 10
                    ttl = await self.redis.ttl(key)
                    if ttl > 0:
                        widget_ttls.append(ttl)

            dashboard_ttls = []
            if dashboard_keys:
                for key in dashboard_keys[:10]:  # Sample first 10
                    ttl = await self.redis.ttl(key)
                    if ttl > 0:
                        dashboard_ttls.append(ttl)

            return {
                "widget_cache": {
                    "count": len(widget_keys),
                    "avg_ttl": sum(widget_ttls) / len(widget_ttls) if widget_ttls else 0,
                    "max_ttl": self.WIDGET_CACHE_TTL
                },
                "dashboard_cache": {
                    "count": len(dashboard_keys),
                    "avg_ttl": sum(dashboard_ttls) / len(dashboard_ttls) if dashboard_ttls else 0,
                    "max_ttl": self.DASHBOARD_CACHE_TTL
                },
                "total_cached_items": len(widget_keys) + len(dashboard_keys),
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"❌ Error getting cache stats: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }

    async def warmup_dashboard(
        self,
        dashboard_id: int,
        dashboard_service: Any
    ) -> bool:
        """
        Pre-warm dashboard cache.

        Useful for frequently accessed dashboards.

        Args:
            dashboard_id: Dashboard ID
            dashboard_service: DashboardService instance

        Returns:
            True if successfully warmed up
        """
        try:
            logger.info(f"🔥 Warming up dashboard cache: {dashboard_id}")

            # Render dashboard (will populate cache)
            rendered = await dashboard_service.render_dashboard(dashboard_id)

            # Cache it
            await self.set_dashboard_cache(dashboard_id, rendered)

            logger.info(f"✅ Dashboard cache warmed up: {dashboard_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Dashboard warmup failed: {e}")
            return False


# Singleton
_dashboard_cache: Optional[DashboardCache] = None


def get_dashboard_cache(redis_client: aioredis.Redis) -> DashboardCache:
    """Get or create DashboardCache singleton"""
    global _dashboard_cache
    if _dashboard_cache is None:
        _dashboard_cache = DashboardCache(redis_client)
    return _dashboard_cache
