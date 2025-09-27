# Production Hardening Checklist
**UK Management Bot - Microservices Production Readiness**

## 🎯 Current Status: Integration Complete ✅

The cross-service integration is complete and functional, but several production hardening items need attention before scaling deployment.

## 🚨 Critical Production Issues

### 1. **Rate Limiting: Process-Local → Redis** ⚠️ **HIGH PRIORITY**

**Current State**:
- Auth Service uses real HTTP calls to User Service ✅
- Rate limiting is still in-memory/process-local ❌
- Won't work with multiple service instances
- No shared state across pods/containers

**Problem**:
```python
# Current in-memory rate limiting (Auth Service)
class InMemoryRateLimiter:
    def __init__(self):
        self.requests = defaultdict(list)  # ❌ Process-local only
```

**Required Solution**: Redis-based distributed rate limiting

**Implementation Plan**:
```python
# Redis-based rate limiting
class RedisRateLimiter:
    def __init__(self, redis_url: str):
        self.redis = Redis.from_url(redis_url)

    async def is_allowed(self, key: str, limit: int, window: int) -> bool:
        # Use Redis sorted sets with sliding window
        # Atomic operations with Lua scripts
```

**Files to Update**:
- `auth_service/middleware/rate_limiting.py`
- `auth_service/services/auth_service.py`
- `user_service/middleware/rate_limiting.py` (if exists)

### 2. **Service Discovery & Load Balancing** ⚠️ **MEDIUM PRIORITY**

**Current State**:
- Hard-coded service URLs in config
- No automatic service discovery
- No load balancing across instances

**Required**:
- Service mesh (Istio) or service discovery (Consul)
- Load balancing for User Service calls
- Health-based routing

### 3. **Circuit Breakers** ⚠️ **MEDIUM PRIORITY**

**Current State**:
- Auth Service calls User Service with basic retry
- No circuit breaker pattern implemented
- Cascading failures possible

**Required**:
```python
# Circuit breaker for service calls
from circuitbreaker import CircuitBreaker

@CircuitBreaker(failure_threshold=5, recovery_timeout=30)
async def call_user_service(self, endpoint: str, **kwargs):
    # Protected service call
```

### 4. **Distributed Tracing** ⚠️ **LOW PRIORITY**

**Current State**:
- Basic logging per service
- No correlation IDs across services
- Difficult to trace requests

**Required**:
- OpenTelemetry integration
- Jaeger or Zipkin for trace collection
- Request correlation IDs

## 📋 Implementation Priority

### Phase 1: Redis Rate Limiting (Critical)
**Timeline**: 1-2 days
**Impact**: Required for multi-instance deployment

1. **Update Auth Service Rate Limiting**
   ```bash
   # Files to modify
   auth_service/middleware/rate_limiting.py
   auth_service/services/auth_service.py
   auth_service/config.py  # Add Redis URL
   ```

2. **Implement Distributed Rate Limiter**
   ```python
   class DistributedRateLimiter:
       """Redis-based rate limiter with sliding window"""

       async def check_rate_limit(self,
                                service_name: str,
                                endpoint: str,
                                identifier: str) -> bool:
           # Use Redis ZREMRANGEBYSCORE + ZADD for sliding window
           # Atomic operations via Lua script
   ```

3. **Update Service Configurations**
   - Add Redis connection strings
   - Update Docker Compose with Redis service
   - Configure Redis persistence and clustering

### Phase 2: Circuit Breakers (Important)
**Timeline**: 2-3 days
**Impact**: Prevents cascading failures

1. **Install Circuit Breaker Library**
   ```bash
   pip install pybreaker  # or similar
   ```

2. **Wrap Service Calls**
   ```python
   # Auth Service calling User Service
   @circuit_breaker
   async def get_user_by_telegram_id(self, telegram_id: str):
       # Protected call with automatic circuit breaking
   ```

### Phase 3: Enhanced Monitoring (Nice to Have)
**Timeline**: 3-5 days
**Impact**: Better observability

1. **Distributed Tracing**
2. **Enhanced Metrics**
3. **Alerting Rules**

## 🔧 Immediate Redis Rate Limiting Implementation

### Redis Rate Limiter Design

```python
# auth_service/services/redis_rate_limiter.py
import redis.asyncio as redis
import time
import logging
from typing import Tuple

class RedisRateLimiter:
    """Distributed rate limiter using Redis sliding window"""

    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)

    async def is_allowed(self,
                        key: str,
                        limit: int,
                        window_seconds: int) -> Tuple[bool, dict]:
        """
        Check if request is allowed using sliding window

        Returns:
            (is_allowed, rate_limit_info)
        """
        now = time.time()
        window_start = now - window_seconds

        # Lua script for atomic operations
        lua_script = """
        local key = KEYS[1]
        local now = tonumber(ARGV[1])
        local window_start = tonumber(ARGV[2])
        local limit = tonumber(ARGV[3])
        local window_seconds = tonumber(ARGV[4])

        -- Remove expired entries
        redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)

        -- Count current requests
        local current_count = redis.call('ZCARD', key)

        if current_count >= limit then
            return {0, current_count, limit}
        end

        -- Add current request
        redis.call('ZADD', key, now, now)
        redis.call('EXPIRE', key, window_seconds * 2)

        return {1, current_count + 1, limit}
        """

        result = await self.redis.eval(
            lua_script, 1, key, now, window_start, limit, window_seconds
        )

        is_allowed = bool(result[0])
        current_count = result[1]

        return is_allowed, {
            "allowed": is_allowed,
            "current_count": current_count,
            "limit": limit,
            "reset_time": int(now + window_seconds)
        }
```

### Integration Points

```python
# auth_service/services/auth_service.py
class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.rate_limiter = RedisRateLimiter(settings.redis_url)

    async def authenticate_user(self, telegram_id: str):
        # Check rate limit before calling User Service
        rate_key = f"auth:user_lookup:{telegram_id}"
        is_allowed, rate_info = await self.rate_limiter.is_allowed(
            rate_key, limit=10, window_seconds=60
        )

        if not is_allowed:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded for user lookup"
            )

        # Proceed with User Service call
        return await self._get_user_from_user_service(telegram_id)
```

## 🚀 Deployment Readiness Status

### ✅ **Currently Production Ready**
- Cross-service authentication (JWT tokens)
- Service-to-service HTTP communication
- Basic observability and health checks
- Comprehensive test coverage
- Critical runtime issues fixed

### ⚠️ **Requires Hardening Before Scale**
- **Redis rate limiting** (single instance works, multiple instances don't)
- Circuit breakers for resilience
- Proper service discovery

### 📊 **Recommended Deployment Strategy**

1. **Single Instance Deployment** ✅
   - Current implementation works perfectly
   - Use for staging and initial production

2. **Multi-Instance Deployment** ⚠️
   - Requires Redis rate limiting implementation
   - Implement before horizontal scaling

3. **High Availability Deployment** 🔄
   - Requires circuit breakers and service mesh
   - Implement after Phase 1 & 2 hardening

---

**Next Priority**: Implement Redis-based rate limiting for production scaling readiness.