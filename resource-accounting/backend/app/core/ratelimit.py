"""Shared rate limiter (SEC-04).

Lives in its own module so routers can import `limiter` without a circular
dependency on app.main. Disabled by default (RESOURCE_RATE_LIMIT_ENABLED=false)
so the test suite and local dev are not throttled; enable in production.
"""

from slowapi import Limiter

from app.config import get_settings
from app.core.ratelimit_key import client_ip_key

limiter = Limiter(key_func=client_ip_key, enabled=get_settings().rate_limit_enabled)

# Per-endpoint limits (strings so slowapi parses them lazily)
AUTH_LIMIT = "10/minute"
HEAVY_LIMIT = "30/minute"
