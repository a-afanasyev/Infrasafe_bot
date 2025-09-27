# Health Checker for FastAPI Service Template
# UK Management Bot - Microservices

import asyncio
import logging
import time
from typing import Dict, Any, List
from datetime import datetime, timedelta

from .config import settings

logger = logging.getLogger(__name__)

class HealthChecker:
    """Service health checker"""

    def __init__(self):
        self.start_time = time.time()
        self.last_check = None
        self.health_status = "starting"
        self.checks = {}

    async def start(self):
        """Start health monitoring"""
        self.health_status = "healthy"
        self.last_check = datetime.utcnow()
        logger.info("Health checker started")

    async def check_database(self) -> Dict[str, Any]:
        """Check database connectivity"""
        try:
            from .main import AsyncSessionLocal
            async with AsyncSessionLocal() as session:
                await session.execute("SELECT 1")
                return {"status": "healthy", "response_time_ms": 0}
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {"status": "unhealthy", "error": str(e)}

    async def check_redis(self) -> Dict[str, Any]:
        """Check Redis connectivity"""
        try:
            import redis.asyncio as redis
            client = redis.from_url(settings.redis_url)
            await client.ping()
            await client.close()
            return {"status": "healthy", "response_time_ms": 0}
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return {"status": "unhealthy", "error": str(e)}

    async def check_external_dependencies(self) -> Dict[str, Any]:
        """Check external service dependencies"""
        checks = {}

        # Check database
        checks["database"] = await self.check_database()

        # Check Redis
        checks["redis"] = await self.check_redis()

        # Add more dependency checks here
        return checks

    async def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status"""
        try:
            # Run dependency checks
            dependency_checks = await self.check_external_dependencies()

            # Calculate uptime
            uptime_seconds = time.time() - self.start_time

            # Overall health status
            all_healthy = all(
                check.get("status") == "healthy"
                for check in dependency_checks.values()
            )

            status = {
                "service": settings.service_name,
                "version": settings.version,
                "status": "healthy" if all_healthy else "degraded",
                "timestamp": datetime.utcnow().isoformat(),
                "uptime_seconds": int(uptime_seconds),
                "checks": dependency_checks,
                "system": {
                    "python_version": "3.11",
                    "environment": "development" if settings.debug else "production"
                }
            }

            self.last_check = datetime.utcnow()
            return status

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "service": settings.service_name,
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }

    async def get_readiness_status(self) -> Dict[str, Any]:
        """Get readiness status (ready to serve traffic)"""
        try:
            # Basic readiness checks
            ready = (
                self.health_status == "healthy" and
                self.last_check and
                (datetime.utcnow() - self.last_check).seconds < 60
            )

            return {
                "service": settings.service_name,
                "ready": ready,
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Readiness check failed: {e}")
            return {
                "service": settings.service_name,
                "ready": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }

    async def get_liveness_status(self) -> Dict[str, Any]:
        """Get liveness status (service is alive)"""
        return {
            "service": settings.service_name,
            "alive": True,
            "timestamp": datetime.utcnow().isoformat(),
            "uptime_seconds": int(time.time() - self.start_time)
        }