"""
Production Observability Service for Media Service
Provides metrics, telemetry, and monitoring capabilities
"""

import time
import json
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from collections import defaultdict, deque
from dataclasses import dataclass, asdict
from contextlib import asynccontextmanager

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.async_database import get_async_db_context
from app.models.media import MediaFile, MediaUploadSession

logger = logging.getLogger(__name__)


@dataclass
class MetricPoint:
    """Individual metric data point"""
    name: str
    value: float
    timestamp: float
    tags: Dict[str, str]
    metric_type: str  # counter, gauge, histogram, timer


@dataclass
class PerformanceMetrics:
    """Performance metrics for operations"""
    operation: str
    duration_ms: float
    success: bool
    error_type: Optional[str] = None
    file_size: Optional[int] = None
    timestamp: float = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


class MetricsCollector:
    """Collects and aggregates metrics"""

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis_client: Optional[redis.Redis] = None
        self.metrics_buffer = deque(maxlen=1000)  # In-memory buffer
        self.counters = defaultdict(int)
        self.gauges = defaultdict(float)
        self.histograms = defaultdict(list)
        self.timers = defaultdict(list)

    async def initialize(self):
        """Initialize metrics collector"""
        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_keepalive=True
            )
            await self.redis_client.ping()
            logger.info("Metrics collector Redis connection established")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis for metrics: {e}")
            self.redis_client = None

    async def record_counter(self, name: str, value: float = 1, tags: Dict[str, str] = None):
        """Record counter metric"""
        tags = tags or {}
        self.counters[name] += value

        metric = MetricPoint(
            name=name,
            value=value,
            timestamp=time.time(),
            tags=tags,
            metric_type="counter"
        )
        self.metrics_buffer.append(metric)

        # Store in Redis for persistence
        if self.redis_client:
            try:
                key = f"metrics:counter:{name}"
                await self.redis_client.incrbyfloat(key, value)
                await self.redis_client.expire(key, 86400)  # 24 hours
            except Exception as e:
                logger.error(f"Failed to store counter metric: {e}")

    async def record_gauge(self, name: str, value: float, tags: Dict[str, str] = None):
        """Record gauge metric"""
        tags = tags or {}
        self.gauges[name] = value

        metric = MetricPoint(
            name=name,
            value=value,
            timestamp=time.time(),
            tags=tags,
            metric_type="gauge"
        )
        self.metrics_buffer.append(metric)

        # Store in Redis
        if self.redis_client:
            try:
                key = f"metrics:gauge:{name}"
                await self.redis_client.set(key, value, ex=86400)
            except Exception as e:
                logger.error(f"Failed to store gauge metric: {e}")

    async def record_histogram(self, name: str, value: float, tags: Dict[str, str] = None):
        """Record histogram metric"""
        tags = tags or {}
        self.histograms[name].append(value)

        # Keep only recent values
        if len(self.histograms[name]) > 1000:
            self.histograms[name] = self.histograms[name][-1000:]

        metric = MetricPoint(
            name=name,
            value=value,
            timestamp=time.time(),
            tags=tags,
            metric_type="histogram"
        )
        self.metrics_buffer.append(metric)

    async def record_timer(self, name: str, duration_ms: float, tags: Dict[str, str] = None):
        """Record timer metric"""
        await self.record_histogram(f"{name}_duration_ms", duration_ms, tags)

    async def record_performance(self, perf_metric: PerformanceMetrics):
        """Record performance metrics"""
        tags = {
            "operation": perf_metric.operation,
            "success": str(perf_metric.success).lower()
        }

        if perf_metric.error_type:
            tags["error_type"] = perf_metric.error_type

        if perf_metric.file_size:
            tags["file_size_category"] = self._categorize_file_size(perf_metric.file_size)

        # Record duration
        await self.record_histogram(
            "operation_duration_ms",
            perf_metric.duration_ms,
            tags
        )

        # Record operation count
        await self.record_counter("operations_total", 1, tags)

        # Record success/failure
        if perf_metric.success:
            await self.record_counter("operations_success_total", 1, {"operation": perf_metric.operation})
        else:
            await self.record_counter("operations_error_total", 1, {
                "operation": perf_metric.operation,
                "error_type": perf_metric.error_type or "unknown"
            })

    def _categorize_file_size(self, file_size: int) -> str:
        """Categorize file size for metrics"""
        if file_size < 1024 * 1024:  # < 1MB
            return "small"
        elif file_size < 10 * 1024 * 1024:  # < 10MB
            return "medium"
        elif file_size < 50 * 1024 * 1024:  # < 50MB
            return "large"
        else:
            return "xlarge"

    async def get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of all metrics"""
        summary = {
            "timestamp": time.time(),
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
            "histograms": {},
            "timers": {}
        }

        # Calculate histogram statistics
        for name, values in self.histograms.items():
            if values:
                sorted_values = sorted(values)
                count = len(sorted_values)
                summary["histograms"][name] = {
                    "count": count,
                    "min": sorted_values[0],
                    "max": sorted_values[-1],
                    "mean": sum(sorted_values) / count,
                    "p50": sorted_values[int(count * 0.5)],
                    "p95": sorted_values[int(count * 0.95)],
                    "p99": sorted_values[int(count * 0.99)] if count > 1 else sorted_values[0]
                }

        return summary

    async def close(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()


class ObservabilityService:
    """Main observability service"""

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.metrics = MetricsCollector(redis_url)
        self.active_operations = {}  # Track ongoing operations
        self.startup_time = time.time()

    async def initialize(self):
        """Initialize observability service"""
        await self.metrics.initialize()
        logger.info("Observability service initialized")

    @asynccontextmanager
    async def track_operation(self, operation_name: str, **context):
        """Context manager to track operation performance"""
        operation_id = f"{operation_name}_{time.time()}_{id(context)}"
        start_time = time.time()

        self.active_operations[operation_id] = {
            "operation": operation_name,
            "start_time": start_time,
            "context": context
        }

        # Record operation start
        await self.metrics.record_counter("operations_started_total", 1, {"operation": operation_name})

        try:
            yield operation_id
            # Operation succeeded
            duration_ms = (time.time() - start_time) * 1000

            perf_metric = PerformanceMetrics(
                operation=operation_name,
                duration_ms=duration_ms,
                success=True,
                file_size=context.get("file_size"),
                timestamp=start_time
            )

            await self.metrics.record_performance(perf_metric)

        except Exception as e:
            # Operation failed
            duration_ms = (time.time() - start_time) * 1000

            perf_metric = PerformanceMetrics(
                operation=operation_name,
                duration_ms=duration_ms,
                success=False,
                error_type=type(e).__name__,
                file_size=context.get("file_size"),
                timestamp=start_time
            )

            await self.metrics.record_performance(perf_metric)
            raise

        finally:
            # Clean up
            self.active_operations.pop(operation_id, None)

    async def record_upload_metrics(self, file_size: int, duration_ms: float, success: bool):
        """Record file upload metrics"""
        tags = {
            "file_size_category": self.metrics._categorize_file_size(file_size),
            "success": str(success).lower()
        }

        await self.metrics.record_histogram("upload_file_size_bytes", file_size, tags)
        await self.metrics.record_histogram("upload_duration_ms", duration_ms, tags)
        await self.metrics.record_counter("uploads_total", 1, tags)

    async def record_telegram_metrics(self, operation: str, success: bool, duration_ms: float):
        """Record Telegram API interaction metrics"""
        tags = {
            "operation": operation,
            "success": str(success).lower()
        }

        await self.metrics.record_histogram("telegram_api_duration_ms", duration_ms, tags)
        await self.metrics.record_counter("telegram_api_calls_total", 1, tags)

    async def get_system_metrics(self) -> Dict[str, Any]:
        """Get system-level metrics"""
        async with get_async_db_context() as db:
            # Database metrics
            total_files_result = await db.execute(select(func.count(MediaFile.id)))
            total_files = total_files_result.scalar() or 0

            total_size_result = await db.execute(select(func.sum(MediaFile.file_size)))
            total_size = total_size_result.scalar() or 0

            # Upload sessions metrics
            active_sessions_result = await db.execute(
                select(func.count(MediaUploadSession.id))
                .where(MediaUploadSession.status == "active")
            )
            active_sessions = active_sessions_result.scalar() or 0

        # System uptime
        uptime_seconds = time.time() - self.startup_time

        return {
            "system": {
                "uptime_seconds": uptime_seconds,
                "active_operations": len(self.active_operations),
                "active_upload_sessions": active_sessions
            },
            "storage": {
                "total_files": total_files,
                "total_size_bytes": total_size,
                "total_size_gb": round(total_size / (1024**3), 2)
            },
            "timestamp": time.time()
        }

    async def get_health_metrics(self) -> Dict[str, Any]:
        """Get health-related metrics"""
        # Check recent error rates
        metrics_summary = await self.metrics.get_metrics_summary()

        error_rate = 0
        total_ops = metrics_summary["counters"].get("operations_total", 0)
        error_ops = metrics_summary["counters"].get("operations_error_total", 0)

        if total_ops > 0:
            error_rate = error_ops / total_ops

        # Check average response times
        avg_duration = 0
        duration_stats = metrics_summary["histograms"].get("operation_duration_ms", {})
        if duration_stats:
            avg_duration = duration_stats.get("mean", 0)

        # Health status
        health_status = "healthy"
        if error_rate > 0.1:  # > 10% error rate
            health_status = "degraded"
        if error_rate > 0.25:  # > 25% error rate
            health_status = "unhealthy"

        return {
            "status": health_status,
            "error_rate": error_rate,
            "avg_response_time_ms": avg_duration,
            "active_operations": len(self.active_operations),
            "metrics_collected": len(self.metrics.metrics_buffer),
            "timestamp": time.time()
        }

    async def get_prometheus_metrics(self) -> str:
        """Get metrics in Prometheus format"""
        metrics_summary = await self.metrics.get_metrics_summary()
        system_metrics = await self.get_system_metrics()

        prometheus_output = []

        # Counters
        for name, value in metrics_summary["counters"].items():
            prometheus_output.append(f"# TYPE media_service_{name} counter")
            prometheus_output.append(f"media_service_{name} {value}")

        # Gauges
        for name, value in metrics_summary["gauges"].items():
            prometheus_output.append(f"# TYPE media_service_{name} gauge")
            prometheus_output.append(f"media_service_{name} {value}")

        # System metrics
        prometheus_output.append(f"# TYPE media_service_uptime_seconds gauge")
        prometheus_output.append(f"media_service_uptime_seconds {system_metrics['system']['uptime_seconds']}")

        prometheus_output.append(f"# TYPE media_service_total_files gauge")
        prometheus_output.append(f"media_service_total_files {system_metrics['storage']['total_files']}")

        prometheus_output.append(f"# TYPE media_service_total_size_bytes gauge")
        prometheus_output.append(f"media_service_total_size_bytes {system_metrics['storage']['total_size_bytes']}")

        return "\n".join(prometheus_output)

    async def cleanup_old_metrics(self, max_age_hours: int = 24):
        """Clean up old metrics data"""
        cutoff_time = time.time() - (max_age_hours * 3600)

        # Clean in-memory buffers
        self.metrics.metrics_buffer = deque(
            [m for m in self.metrics.metrics_buffer if m.timestamp > cutoff_time],
            maxlen=1000
        )

        # Clean Redis metrics (if connected)
        if self.metrics.redis_client:
            try:
                # This would need more sophisticated cleanup logic
                # For now, we rely on Redis TTL
                pass
            except Exception as e:
                logger.error(f"Failed to cleanup old metrics: {e}")

        logger.info(f"Cleaned up metrics older than {max_age_hours} hours")

    async def close(self):
        """Close observability service"""
        await self.metrics.close()


# Global observability instance
observability_instance = None


async def get_observability() -> ObservabilityService:
    """Get global observability instance"""
    global observability_instance
    if not observability_instance:
        observability_instance = ObservabilityService()
        await observability_instance.initialize()
    return observability_instance


async def track_operation(operation_name: str, **context):
    """Convenience function to track operations"""
    obs = await get_observability()
    return obs.track_operation(operation_name, **context)


# Metrics decorators
def track_async_operation(operation_name: str):
    """Decorator to track async operation performance"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            async with track_operation(operation_name):
                return await func(*args, **kwargs)
        return wrapper
    return decorator