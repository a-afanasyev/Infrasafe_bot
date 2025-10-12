# Analytics Service - Integration Notes

**Status**: ✅ **INTEGRATED INTO MAIN MICROSERVICES**
**Date**: 6 October 2025
**Version**: 1.0.0

---

## 🎯 Integration Summary

Analytics Service has been successfully integrated into the main microservices architecture and is now part of the unified `docker-compose.yml` in the parent `microservices/` directory.

### Changes Made:

1. **Removed Standalone Deployment**:
   - ✅ `docker-compose.yml` → `docker-compose.standalone.yml.bak` (backup)
   - ✅ Separate containers stopped and removed
   - ✅ Separate volumes cleaned up

2. **Integrated into Main Compose**:
   - ✅ Added `analytics-service` to main docker-compose.yml
   - ✅ Added `analytics-consumer` worker container
   - ✅ Added `analytics-db` database container
   - ✅ Added `analytics_db_data` volume

3. **Updated Configuration**:
   - ✅ Uses `shared-redis` instead of separate Redis
   - ✅ Connected to `microservices-network`
   - ✅ Environment variables in main `.env` file

---

## 🚀 Deployment

### Start Analytics Service

From the **parent microservices directory**:

```bash
cd /path/to/microservices

# Start only analytics service
docker-compose up -d analytics-service analytics-consumer analytics-db

# Or start all services
docker-compose up -d
```

### Check Status

```bash
# Check containers
docker-compose ps | grep analytics

# Check health
curl http://localhost:8008/api/v1/health | jq

# Check consumer
curl http://localhost:8008/api/v1/consumer/health | jq

# Check scheduler
curl http://localhost:8008/api/v1/scheduler/jobs | jq
```

### View Logs

```bash
# Service logs
docker-compose logs -f analytics-service

# Consumer logs
docker-compose logs -f analytics-consumer

# All analytics logs
docker-compose logs -f analytics-service analytics-consumer
```

---

## 📊 Service Configuration

### Port Mapping

| Component | Internal Port | External Port | Description |
|-----------|--------------|---------------|-------------|
| Analytics Service | 8006 | **8008** | Main REST API |
| Analytics DB | 5432 | **5440** | PostgreSQL |
| Shared Redis | 6379 | 6379 | Redis (DB 8) |

### Environment Variables

Set in `/microservices/.env`:

```bash
# Database
ANALYTICS_DB_USER=analytics_user
ANALYTICS_DB_PASSWORD=analytics_pass
ANALYTICS_DB_NAME=analytics_db
ANALYTICS_DB_PORT=5440

# Service
ANALYTICS_SERVICE_PORT=8008

# Redis
REDIS_ANALYTICS_DB=8
```

### Service Dependencies

```yaml
analytics-service:
  depends_on:
    - analytics-db (healthy)
    - shared-redis (healthy)
    - auth-service (healthy)

analytics-consumer:
  depends_on:
    - analytics-db (healthy)
    - shared-redis (healthy)
    - analytics-service (started)
```

---

## 🔧 Architecture Integration

### Shared Infrastructure

Analytics Service now uses:

1. **Shared Redis** (`shared-redis:6379` DB 8)
   - Event streams: `analytics:events`
   - Consumer group: `analytics-consumers`
   - Caching with isolated DB

2. **Microservices Network** (`microservices-network`)
   - Communication with Auth Service
   - Service discovery via container names
   - Isolated network segment

3. **Unified Configuration**
   - Single `.env` file
   - Consistent naming conventions
   - Centralized secrets management

### Service Communication

```
┌─────────────────┐
│  Auth Service   │◀─── JWT Validation
│   (port 8001)   │
└─────────────────┘
         ▲
         │
         ▼
┌─────────────────┐     ┌──────────────┐
│ Analytics       │────▶│ Shared Redis │
│ Service         │     │  (DB 8)      │
│ (port 8008)     │◀────│              │
└─────────────────┘     └──────────────┘
         │                      ▲
         │                      │
         ▼                      │
┌─────────────────┐            │
│ Analytics       │────────────┘
│ Consumer        │  Event Processing
│ (background)    │
└─────────────────┘
         │
         ▼
┌─────────────────┐
│ Analytics DB    │
│ (port 5440)     │
└─────────────────┘
```

---

## 📋 API Endpoints

All endpoints available at `http://localhost:8008`:

### Health & Monitoring
- `GET /api/v1/health` - Service health check
- `GET /api/v1/health/live` - Liveness probe
- `GET /api/v1/health/ready` - Readiness probe

### Metrics & KPIs
- `GET /api/v1/metrics` - All metrics
- `GET /api/v1/metrics/{metric_name}` - Specific metric
- `GET /api/v1/metrics/{metric_name}/history` - Historical data
- `POST /api/v1/metrics/refresh` - Refresh metrics

### Real-time Data
- `GET /api/v1/realtime/summary` - Real-time summary
- `GET /api/v1/realtime/active-shifts` - Active shifts count
- `GET /api/v1/realtime/requests-in-progress` - Active requests
- `GET /api/v1/realtime/active-users` - Active users (5min)

### Aggregations
- `GET /api/v1/aggregates/{kpi_name}` - Aggregated KPI data
- `GET /api/v1/aggregates/{kpi_name}/latest` - Latest aggregation
- `POST /api/v1/aggregates/calculate` - Trigger calculation
- `GET /api/v1/aggregates/summary` - All aggregates summary

### Dashboards
- `GET /api/v1/dashboards` - List all dashboards
- `POST /api/v1/dashboards` - Create dashboard
- `GET /api/v1/dashboards/{id}` - Get dashboard
- `GET /api/v1/dashboards/{id}/render` - Render dashboard
- `GET /api/v1/dashboards/slug/{slug}/render` - Render by slug

### Consumer & Events
- `GET /api/v1/consumer/health` - Consumer health
- `GET /api/v1/consumer/metrics` - Consumer metrics
- `GET /api/v1/consumer/dlq` - Dead letter queue
- `POST /api/v1/consumer/dlq/retry/{id}` - Retry failed event
- `DELETE /api/v1/consumer/dlq/clear` - Clear DLQ

### Scheduler
- `GET /api/v1/scheduler/jobs` - List scheduled jobs
- `POST /api/v1/scheduler/trigger/{job_name}` - Trigger job manually
- `POST /api/v1/scheduler/backfill` - Backfill aggregations

### Cache Management
- `GET /api/v1/cache/stats` - Cache statistics
- `POST /api/v1/cache/invalidate/all` - Invalidate all cache
- `POST /api/v1/cache/invalidate/dashboard/{id}` - Invalidate dashboard
- `POST /api/v1/cache/warmup/dashboard/{id}` - Warm up cache

### WebSocket
- `WS /api/v1/ws/metrics` - WebSocket connection for real-time updates
- `GET /api/v1/ws/stats` - WebSocket stats
- `POST /api/v1/ws/broadcast` - Broadcast message

### Interactive Docs
- `GET /docs` - Swagger UI (OpenAPI)
- `GET /redoc` - ReDoc documentation
- `GET /openapi.json` - OpenAPI schema

---

## 🧪 Testing

### Quick Health Check

```bash
# Service health
curl http://localhost:8008/api/v1/health | jq

# Consumer status
curl http://localhost:8008/api/v1/consumer/health | jq

# Scheduler jobs
curl http://localhost:8008/api/v1/scheduler/jobs | jq
```

### Publish Test Event

```bash
# Publish to Redis Stream
redis-cli -h localhost -p 6379 XADD analytics:events "*" \
  event_id "test-123" \
  event_type "shift.created" \
  service_name "shift-service" \
  payload '{"shift_id": 1, "executor_id": 1}'
```

### Check Metrics

```bash
# Real-time summary
curl http://localhost:8008/api/v1/realtime/summary | jq

# Active shifts
curl http://localhost:8008/api/v1/realtime/active-shifts | jq

# Metrics history
curl http://localhost:8008/api/v1/metrics/active_shifts/history?days=7 | jq
```

---

## 🔄 Migration from Standalone

If migrating from standalone deployment:

### 1. Stop Standalone Containers

```bash
cd analytics_service/
docker-compose -f docker-compose.standalone.yml.bak down -v
```

### 2. Migrate Data (if needed)

```bash
# Backup standalone data
docker run --rm \
  -v analytics_service_analytics_postgres_data:/source \
  -v $(pwd)/backup:/backup \
  alpine tar czf /backup/analytics_db_backup.tar.gz -C /source .

# Restore to main compose
docker run --rm \
  -v microservices_analytics_db_data:/target \
  -v $(pwd)/backup:/backup \
  alpine tar xzf /backup/analytics_db_backup.tar.gz -C /target
```

### 3. Update Application Config

Update any application code that referenced:
- `localhost:8006` → `localhost:8008` (external access)
- `analytics-service:8006` → `analytics-service:8006` (internal - no change)
- Redis host: `analytics-redis` → `shared-redis`

---

## 📝 Maintenance

### Update Service

```bash
cd /path/to/microservices

# Rebuild and restart
docker-compose build analytics-service analytics-consumer
docker-compose up -d analytics-service analytics-consumer
```

### Database Migrations

```bash
# Run migrations
docker-compose exec analytics-service alembic upgrade head

# Create migration
docker-compose exec analytics-service alembic revision --autogenerate -m "description"
```

### Clear Cache

```bash
# Clear all cache
curl -X POST http://localhost:8008/api/v1/cache/invalidate/all

# Warm up cache
curl -X POST http://localhost:8008/api/v1/cache/warmup/dashboard/1
```

---

## 🚨 Troubleshooting

### Service Won't Start

1. Check dependencies:
   ```bash
   docker-compose ps analytics-db shared-redis auth-service
   ```

2. Check logs:
   ```bash
   docker-compose logs analytics-service
   ```

3. Verify environment variables:
   ```bash
   docker-compose config | grep -A 20 analytics-service
   ```

### Consumer Not Processing Events

1. Check consumer health:
   ```bash
   curl http://localhost:8008/api/v1/consumer/health
   ```

2. Check Redis stream:
   ```bash
   docker-compose exec shared-redis redis-cli XINFO STREAM analytics:events
   ```

3. Check consumer logs:
   ```bash
   docker-compose logs analytics-consumer
   ```

### Database Connection Issues

1. Verify database is running:
   ```bash
   docker-compose exec analytics-db pg_isready -U analytics_user
   ```

2. Test connection:
   ```bash
   docker-compose exec analytics-db psql -U analytics_user -d analytics_db -c "SELECT 1"
   ```

---

## 📚 References

- Main Documentation: [../MICROSERVICES_ARCHITECTURE.md](../MICROSERVICES_ARCHITECTURE.md)
- Analytics Service Docs: [README.md](README.md)
- API Documentation: http://localhost:8008/docs
- Final Report: [ANALYTICS_SERVICE_FINAL_REPORT.md](ANALYTICS_SERVICE_FINAL_REPORT.md)
- Production Guide: [PRODUCTION_DEPLOYMENT_GUIDE.md](PRODUCTION_DEPLOYMENT_GUIDE.md)

---

**✅ Analytics Service is now fully integrated into the main microservices architecture!**
