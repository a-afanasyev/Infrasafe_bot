"""
Building Directory Client - Prometheus Metrics
UK Management Bot - Request Service

Metrics for monitoring Building Directory integration health and performance.
"""

from prometheus_client import Counter, Histogram, Gauge

# Request counters by operation and status
building_directory_requests_total = Counter(
    'building_directory_requests_total',
    'Total requests to Building Directory API',
    ['operation', 'status']
)

# Request duration histogram by operation
building_directory_request_duration_seconds = Histogram(
    'building_directory_request_duration_seconds',
    'Building Directory API request duration in seconds',
    ['operation'],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
)

# Cache hit/miss counters
building_cache_operations_total = Counter(
    'building_cache_operations_total',
    'Building cache operations (hits, misses, sets)',
    ['operation']  # hit, miss, set, error
)

# Active API connections gauge
building_directory_active_connections = Gauge(
    'building_directory_active_connections',
    'Number of active connections to Building Directory API'
)

# Validation counters
building_validations_total = Counter(
    'building_validations_total',
    'Building validation attempts',
    ['result']  # valid, invalid_not_found, invalid_inactive
)

# Coordinate extraction counters
coordinate_extractions_total = Counter(
    'coordinate_extractions_total',
    'Coordinate extraction attempts',
    ['result', 'source']  # result: success/failure, source: nested/flat/missing
)

# Error counters by type
building_directory_errors_total = Counter(
    'building_directory_errors_total',
    'Building Directory client errors',
    ['error_type']  # timeout, connection, http_error, parse_error
)

# Data denormalization counters
building_denormalization_total = Counter(
    'building_denormalization_total',
    'Building data denormalization for requests',
    ['status']  # success, failure
)
