"""
Bot Gateway Service - Prometheus Metrics
UK Management Bot - Sprint 19-22

Custom metrics for monitoring bot performance and health.
"""

from prometheus_client import Counter, Histogram, Gauge, Info
from typing import Optional


# ========== Application Info ==========
app_info = Info('bot_gateway_app', 'Bot Gateway application information')


# ========== Message Metrics ==========
messages_total = Counter(
    'bot_gateway_messages_total',
    'Total number of messages received from users',
    ['message_type', 'user_role', 'language']
)

message_processing_duration = Histogram(
    'bot_gateway_message_processing_duration_seconds',
    'Time spent processing messages',
    ['message_type', 'handler'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)


# ========== Command Metrics ==========
commands_total = Counter(
    'bot_gateway_commands_total',
    'Total number of bot commands executed',
    ['command', 'user_role', 'status']
)


# ========== Callback Query Metrics ==========
callbacks_total = Counter(
    'bot_gateway_callbacks_total',
    'Total number of callback queries processed',
    ['callback_type', 'user_role', 'status']
)

callback_processing_duration = Histogram(
    'bot_gateway_callback_processing_duration_seconds',
    'Time spent processing callback queries',
    ['callback_type'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)


# ========== FSM State Metrics ==========
fsm_state_transitions = Counter(
    'bot_gateway_fsm_state_transitions_total',
    'Total number of FSM state transitions',
    ['from_state', 'to_state', 'user_role']
)

active_fsm_sessions = Gauge(
    'bot_gateway_active_fsm_sessions',
    'Number of active FSM sessions',
    ['state_group']
)


# ========== Error Metrics ==========
errors_total = Counter(
    'bot_gateway_errors_total',
    'Total number of errors',
    ['error_type', 'handler', 'severity']
)

exceptions_total = Counter(
    'bot_gateway_exceptions_total',
    'Total number of unhandled exceptions',
    ['exception_type', 'handler']
)


# ========== Middleware Metrics ==========
middleware_duration = Histogram(
    'bot_gateway_middleware_duration_seconds',
    'Time spent in middleware',
    ['middleware_name'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5]
)

rate_limit_hits = Counter(
    'bot_gateway_rate_limit_hits_total',
    'Total number of rate limit hits',
    ['user_id', 'limit_type']
)

rate_limit_blocks = Counter(
    'bot_gateway_rate_limit_blocks_total',
    'Total number of rate limit blocks',
    ['limit_type']
)


# ========== Authentication Metrics ==========
auth_attempts = Counter(
    'bot_gateway_auth_attempts_total',
    'Total number of authentication attempts',
    ['method', 'status']
)

session_duration = Histogram(
    'bot_gateway_session_duration_seconds',
    'Duration of user sessions',
    buckets=[60, 300, 900, 1800, 3600, 7200, 14400, 28800, 86400]
)

active_sessions = Gauge(
    'bot_gateway_active_sessions',
    'Number of active user sessions',
    ['user_role']
)


# ========== Service Integration Metrics ==========
service_requests_total = Counter(
    'bot_gateway_service_requests_total',
    'Total number of requests to backend services',
    ['service_name', 'endpoint', 'method', 'status']
)

service_request_duration = Histogram(
    'bot_gateway_service_request_duration_seconds',
    'Time spent on backend service requests',
    ['service_name', 'endpoint'],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

service_errors_total = Counter(
    'bot_gateway_service_errors_total',
    'Total number of backend service errors',
    ['service_name', 'endpoint', 'error_code']
)

service_circuit_breaker_state = Gauge(
    'bot_gateway_service_circuit_breaker_state',
    'Circuit breaker state (0=closed, 1=open, 2=half-open)',
    ['service_name']
)


# ========== Redis Metrics ==========
redis_operations_total = Counter(
    'bot_gateway_redis_operations_total',
    'Total number of Redis operations',
    ['operation_type', 'status']
)

redis_operation_duration = Histogram(
    'bot_gateway_redis_operation_duration_seconds',
    'Time spent on Redis operations',
    ['operation_type'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5]
)

redis_connection_pool_size = Gauge(
    'bot_gateway_redis_connection_pool_size',
    'Number of connections in Redis pool',
    ['pool_state']
)


# ========== User Activity Metrics ==========
active_users = Gauge(
    'bot_gateway_active_users',
    'Number of active users in last N minutes',
    ['time_window', 'user_role']
)

user_actions_total = Counter(
    'bot_gateway_user_actions_total',
    'Total number of user actions',
    ['action_type', 'user_role', 'language']
)


# ========== Request Management Metrics ==========
requests_created = Counter(
    'bot_gateway_requests_created_total',
    'Total number of requests created via bot',
    ['user_role', 'priority', 'language']
)

requests_viewed = Counter(
    'bot_gateway_requests_viewed_total',
    'Total number of requests viewed via bot',
    ['user_role', 'request_status']
)

requests_updated = Counter(
    'bot_gateway_requests_updated_total',
    'Total number of requests updated via bot',
    ['user_role', 'action_type']
)


# ========== Shift Management Metrics ==========
shifts_viewed = Counter(
    'bot_gateway_shifts_viewed_total',
    'Total number of shifts viewed via bot',
    ['user_role', 'view_type']
)

shifts_taken = Counter(
    'bot_gateway_shifts_taken_total',
    'Total number of shifts taken via bot',
    ['specialization']
)

shifts_released = Counter(
    'bot_gateway_shifts_released_total',
    'Total number of shifts released via bot',
    ['specialization', 'reason']
)

availability_updates = Counter(
    'bot_gateway_availability_updates_total',
    'Total number of availability updates',
    ['is_available', 'recurring']
)


# ========== Admin Panel Metrics ==========
admin_actions_total = Counter(
    'bot_gateway_admin_actions_total',
    'Total number of admin actions',
    ['admin_role', 'action_type', 'target_type']
)

admin_searches = Counter(
    'bot_gateway_admin_searches_total',
    'Total number of admin searches',
    ['search_type', 'result_count_bucket']
)

broadcasts_sent = Counter(
    'bot_gateway_broadcasts_sent_total',
    'Total number of broadcast messages sent',
    ['target_type', 'scheduled']
)

broadcast_recipients = Histogram(
    'bot_gateway_broadcast_recipients',
    'Number of recipients per broadcast',
    buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000, 5000]
)


# ========== Webhook Metrics ==========
webhook_updates_total = Counter(
    'bot_gateway_webhook_updates_total',
    'Total number of webhook updates received',
    ['update_type', 'status']
)

webhook_processing_duration = Histogram(
    'bot_gateway_webhook_processing_duration_seconds',
    'Time spent processing webhook updates',
    ['update_type'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)


# ========== Performance Metrics ==========
memory_usage_bytes = Gauge(
    'bot_gateway_memory_usage_bytes',
    'Memory usage in bytes',
    ['type']
)

cpu_usage_percent = Gauge(
    'bot_gateway_cpu_usage_percent',
    'CPU usage percentage'
)

event_loop_lag = Histogram(
    'bot_gateway_event_loop_lag_seconds',
    'Event loop lag in seconds',
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)


def init_metrics(app_name: str, version: str, environment: str):
    """
    Initialize application metrics with static information.

    Args:
        app_name: Application name
        version: Application version
        environment: Environment (dev, staging, production)
    """
    app_info.info({
        'name': app_name,
        'version': version,
        'environment': environment
    })
