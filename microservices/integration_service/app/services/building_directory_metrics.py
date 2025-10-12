"""
Building Directory Prometheus Metrics
Integration Service - UK Management Bot

Comprehensive metrics for Building Directory operations
"""

import logging
from functools import wraps
from typing import Callable
import time

from prometheus_client import Counter, Histogram, Gauge

logger = logging.getLogger(__name__)

# ============================================================================
# Request Metrics
# ============================================================================

building_directory_requests_total = Counter(
    name="building_directory_requests_total",
    documentation="Total Building Directory API requests",
    labelnames=["operation", "status"]  # operation=get_building,list_buildings,search status=success,error,not_found
)

building_directory_request_duration_seconds = Histogram(
    name="building_directory_request_duration_seconds",
    documentation="Building Directory request duration in seconds",
    labelnames=["operation"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

building_directory_active_connections = Gauge(
    name="building_directory_active_connections",
    documentation="Number of active connections to Building Directory API"
)

# ============================================================================
# Cache Metrics
# ============================================================================

building_cache_operations_total = Counter(
    name="building_cache_operations_total",
    documentation="Total Building Directory cache operations",
    labelnames=["operation", "result"]  # operation=get,set,invalidate result=hit,miss,error
)

# ============================================================================
# Validation Metrics
# ============================================================================

building_validations_total = Counter(
    name="building_validations_total",
    documentation="Total building validations performed",
    labelnames=["result"]  # result=valid,invalid
)

# ============================================================================
# Geocoding Metrics
# ============================================================================

coordinate_extractions_total = Counter(
    name="coordinate_extractions_total",
    documentation="Total coordinate extractions/geocoding operations",
    labelnames=["provider", "status"]  # provider=google_maps,yandex_maps status=success,failure
)

# ============================================================================
# Error Metrics
# ============================================================================

building_directory_errors_total = Counter(
    name="building_directory_errors_total",
    documentation="Total Building Directory errors",
    labelnames=["error_type", "operation"]  # error_type=not_found,validation,network,server
)

# ============================================================================
# Data Metrics
# ============================================================================

building_denormalization_total = Counter(
    name="building_denormalization_total",
    documentation="Total building data denormalizations for requests",
    labelnames=["status"]  # status=success,failure
)


# ============================================================================
# Decorator for automatic metrics tracking
# ============================================================================

def track_building_operation(operation_name: str):
    """
    Decorator to track Building Directory operations with metrics

    Usage:
        @track_building_operation("get_building")
        async def get_building(self, building_id):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Track active connections
            building_directory_active_connections.inc()

            # Track request duration
            start_time = time.time()

            try:
                result = await func(*args, **kwargs)

                # Track success
                duration = time.time() - start_time
                building_directory_requests_total.labels(
                    operation=operation_name,
                    status="success"
                ).inc()
                building_directory_request_duration_seconds.labels(
                    operation=operation_name
                ).observe(duration)

                return result

            except Exception as e:
                # Track error
                duration = time.time() - start_time
                error_type = type(e).__name__

                # Classify error
                if "NotFound" in error_type:
                    status = "not_found"
                elif "Validation" in error_type:
                    status = "validation_error"
                else:
                    status = "error"

                building_directory_requests_total.labels(
                    operation=operation_name,
                    status=status
                ).inc()
                building_directory_request_duration_seconds.labels(
                    operation=operation_name
                ).observe(duration)

                building_directory_errors_total.labels(
                    error_type=error_type,
                    operation=operation_name
                ).inc()

                raise

            finally:
                # Release connection tracking
                building_directory_active_connections.dec()

        return wrapper
    return decorator


# ============================================================================
# Metric Helper Functions
# ============================================================================

def record_cache_hit(operation: str = "get"):
    """Record cache hit"""
    building_cache_operations_total.labels(
        operation=operation,
        result="hit"
    ).inc()


def record_cache_miss(operation: str = "get"):
    """Record cache miss"""
    building_cache_operations_total.labels(
        operation=operation,
        result="miss"
    ).inc()


def record_cache_set():
    """Record cache set operation"""
    building_cache_operations_total.labels(
        operation="set",
        result="success"
    ).inc()


def record_cache_invalidation(keys_count: int = 1):
    """Record cache invalidation"""
    building_cache_operations_total.labels(
        operation="invalidate",
        result="success"
    ).inc()


def record_validation(is_valid: bool):
    """Record building validation result"""
    building_validations_total.labels(
        result="valid" if is_valid else "invalid"
    ).inc()


def record_coordinate_extraction(provider: str, success: bool):
    """Record coordinate extraction/geocoding"""
    coordinate_extractions_total.labels(
        provider=provider,
        status="success" if success else "failure"
    ).inc()


def record_denormalization(success: bool):
    """Record building data denormalization"""
    building_denormalization_total.labels(
        status="success" if success else "failure"
    ).inc()


def record_building_error(error_type: str, operation: str):
    """Record Building Directory error"""
    building_directory_errors_total.labels(
        error_type=error_type,
        operation=operation
    ).inc()


# ============================================================================
# Metric Summary
# ============================================================================

def get_metrics_summary() -> dict:
    """
    Get summary of all Building Directory metrics

    Returns:
        Dictionary with metric descriptions
    """
    return {
        "request_metrics": {
            "building_directory_requests_total": "Counter: Total requests by operation and status",
            "building_directory_request_duration_seconds": "Histogram: Request duration distribution",
            "building_directory_active_connections": "Gauge: Current active API connections"
        },
        "cache_metrics": {
            "building_cache_operations_total": "Counter: Cache operations (hits, misses, sets, invalidations)"
        },
        "validation_metrics": {
            "building_validations_total": "Counter: Building validations (valid/invalid)"
        },
        "geocoding_metrics": {
            "coordinate_extractions_total": "Counter: Coordinate extractions by provider"
        },
        "error_metrics": {
            "building_directory_errors_total": "Counter: Errors by type and operation"
        },
        "data_metrics": {
            "building_denormalization_total": "Counter: Building data denormalizations"
        }
    }


# Log metrics registration
logger.info("📊 Building Directory Prometheus metrics registered")
logger.debug(f"Metrics summary: {get_metrics_summary()}")
