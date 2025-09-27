# Simplified Health Checker
# UK Management Bot - Notification Service

import asyncio
import logging
import time
from typing import Dict, Any
from datetime import datetime

from config import settings

logger = logging.getLogger(__name__)

class SimpleHealthChecker:
    """Simplified service health checker"""

    def __init__(self):
        self.start_time = datetime.utcnow()
        self.check_count = 0
        self.last_check = None
        self.status = "starting"

    async def start(self):
        """Start health checker"""
        self.status = "running"
        logger.info("Health checker started")

    async def stop(self):
        """Stop health checker"""
        self.status = "stopped"
        logger.info("Health checker stopped")

    async def check_health(self) -> Dict[str, Any]:
        """Perform health check"""
        self.check_count += 1
        self.last_check = datetime.utcnow()

        uptime_seconds = (self.last_check - self.start_time).total_seconds()

        return {
            "status": self.status,
            "uptime_seconds": round(uptime_seconds, 2),
            "check_count": self.check_count,
            "last_check": self.last_check.isoformat(),
            "service": settings.service_name,
            "version": "1.0.0"
        }

    async def detailed_health_check(self, db_session=None, redis_client=None, event_publisher=None) -> Dict[str, Any]:
        """Perform detailed health check"""
        health_data = await self.check_health()

        # Check database
        db_status = "unknown"
        if db_session:
            try:
                from sqlalchemy import text
                await db_session.execute(text("SELECT 1"))
                db_status = "healthy"
            except Exception as e:
                db_status = f"unhealthy: {str(e)}"

        # Check Redis
        redis_status = "unknown"
        if redis_client:
            try:
                await redis_client.ping()
                redis_status = "healthy"
            except Exception as e:
                redis_status = f"unhealthy: {str(e)}"

        # Check event system
        event_status = "unknown"
        if event_publisher:
            try:
                event_health = await event_publisher.health_check()
                event_status = event_health.get("status", "unknown")
            except Exception as e:
                event_status = f"unhealthy: {str(e)}"

        health_data.update({
            "components": {
                "database": db_status,
                "redis": redis_status,
                "events": event_status
            }
        })

        return health_data