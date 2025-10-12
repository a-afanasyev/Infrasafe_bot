# Analytics Service - Quick Start Guide

**For Developers**: Get up and running in 5 minutes

---

## Prerequisites

- Docker & Docker Compose installed
- Git clone of the repository
- Basic knowledge of Python and REST APIs

---

## 1. Clone & Navigate

```bash
# Navigate to analytics service
cd microservices/analytics_service
```

---

## 2. Environment Setup

```bash
# Copy example environment
cp .env.example .env

# Edit if needed (defaults work for local development)
nano .env
```

**Default values work for local development**, but you can customize:
```env
PORT=8006
DATABASE_URL=postgresql+asyncpg://analytics:password@postgres:5432/analytics_db
REDIS_URL=redis://redis:6379/0
MAX_WORKERS=3
DEBUG=true
```

---

## 3. Start Services

```bash
# Build and start everything
docker-compose up --build

# Or in background
docker-compose up -d

# Watch logs
docker-compose logs -f
```

**Wait for**:
```
analytics-service | ✅ Database initialized
analytics-service | ✅ Aggregation scheduler started
analytics-service | INFO: Uvicorn running on http://0.0.0.0:8006
```

---

## 4. Verify It Works

```bash
# Health check
curl http://localhost:8006/api/v1/health

# Expected response:
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2025-10-06T12:00:00Z"
}
```

✅ **Success!** Analytics Service is running.

---

## 5. Load Sample Dashboards

```bash
# Load 5 pre-configured dashboards
docker exec -i analytics-postgres psql -U analytics_user -d analytics_db < sample_dashboards.sql

# Verify
curl http://localhost:8006/api/v1/dashboards

# Should see 5 dashboards
```

---

## 6. Explore the API

### Interactive Documentation

Open in browser: **http://localhost:8006/docs**

You'll see:
- All 45+ API endpoints
- Interactive "Try it out" buttons
- Request/response examples
- Authentication info

### Key Endpoints

#### Health & Status
```bash
# Service health
curl http://localhost:8006/api/v1/health

# Dependencies health (PostgreSQL, Redis)
curl http://localhost:8006/api/v1/health/dependencies
```

#### Real-time Metrics
```bash
# Current active shifts
curl http://localhost:8006/api/v1/realtime/active-shifts

# Current requests in progress
curl http://localhost:8006/api/v1/realtime/requests-in-progress

# Active users (last 5 minutes)
curl http://localhost:8006/api/v1/realtime/active-users

# All real-time metrics
curl http://localhost:8006/api/v1/realtime/summary
```

#### Dashboards
```bash
# List all dashboards
curl http://localhost:8006/api/v1/dashboards

# Render specific dashboard
curl http://localhost:8006/api/v1/dashboards/1/render

# Render by slug
curl http://localhost:8006/api/v1/dashboards/slug/shift-management-overview/render
```

#### Consumer Status
```bash
# Consumer metrics
curl http://localhost:8006/api/v1/consumer/metrics

# Consumer health
curl http://localhost:8006/api/v1/consumer/health
```

#### Scheduler
```bash
# List scheduled jobs
curl http://localhost:8006/api/v1/scheduler/jobs

# Manually trigger daily aggregation
curl -X POST http://localhost:8006/api/v1/scheduler/trigger/daily_aggregation
```

---

## 7. Test WebSocket Streaming

### Using wscat (install if needed)
```bash
# Install wscat
npm install -g wscat

# Connect to WebSocket
wscat -c ws://localhost:8006/api/v1/ws/metrics

# You'll receive metrics every 5 seconds:
{
  "type": "metrics_update",
  "timestamp": "2025-10-06T12:00:00Z",
  "data": {
    "active_shifts": 15,
    "requests_in_progress": 23,
    "active_users": 8
  }
}
```

### Using JavaScript
```javascript
const ws = new WebSocket('ws://localhost:8006/api/v1/ws/metrics');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Received metrics:', data);
};

ws.onopen = () => {
  console.log('Connected to Analytics Service');
};
```

---

## 8. Publish Test Events

### From Another Service

```python
import redis.asyncio as aioredis
import json
from datetime import datetime

# Connect to Redis
redis_client = aioredis.from_url("redis://localhost:6379/0")

# Publish test shift event
await redis_client.xadd(
    "analytics:events",
    {
        "event_id": "test-shift-001",
        "event_type": "shift.created",
        "service_name": "test-service",
        "payload": json.dumps({
            "shift_id": 123,
            "shift_number": "SH-001",
            "executor_id": 456,
            "user_id": "user_789"
        }),
        "timestamp": datetime.utcnow().isoformat()
    }
)

# Wait a moment for processing
await asyncio.sleep(1)

# Check if processed
# curl http://localhost:8006/api/v1/consumer/metrics
```

---

## 9. Run Tests

```bash
# All tests
docker-compose exec analytics-service pytest

# With coverage
docker-compose exec analytics-service pytest --cov=. --cov-report=html

# Specific test file
docker-compose exec analytics-service pytest tests/test_integration.py -v

# View coverage report
open htmlcov/index.html
```

---

## 10. Common Development Tasks

### Restart Service
```bash
# Restart just the API server
docker-compose restart analytics-service

# Restart consumer
docker-compose restart analytics-consumer

# Restart all
docker-compose restart
```

### View Logs
```bash
# All logs
docker-compose logs -f

# Specific service
docker-compose logs -f analytics-service

# Last 100 lines
docker-compose logs --tail 100 analytics-service
```

### Database Access
```bash
# PostgreSQL shell
docker-compose exec postgres psql -U analytics_user -d analytics_db

# Run query
docker-compose exec postgres psql -U analytics_user -d analytics_db \
  -c "SELECT COUNT(*) FROM event_logs;"

# Check tables
docker-compose exec postgres psql -U analytics_user -d analytics_db -c "\dt"
```

### Redis Access
```bash
# Redis CLI
docker-compose exec redis redis-cli

# Check stream
docker-compose exec redis redis-cli XLEN analytics:events

# Check cache keys
docker-compose exec redis redis-cli KEYS "dashboard:*"
```

### Run Migrations
```bash
# Create new migration
docker-compose exec analytics-service alembic revision --autogenerate -m "Add new field"

# Apply migrations
docker-compose exec analytics-service alembic upgrade head

# Rollback one migration
docker-compose exec analytics-service alembic downgrade -1
```

### Clear Cache
```bash
# Clear all dashboard caches
curl -X POST http://localhost:8006/api/v1/cache/invalidate/all

# Clear specific dashboard
curl -X POST http://localhost:8006/api/v1/cache/invalidate/dashboard/1

# View cache stats
curl http://localhost:8006/api/v1/cache/stats
```

---

## 11. Troubleshooting

### Service won't start

**Check logs**:
```bash
docker-compose logs analytics-service
```

**Common issues**:
- Database not ready → Wait 30 seconds and retry
- Port 8006 already in use → Change PORT in .env
- Redis connection failed → Check redis container is running

### Database connection error

```bash
# Check if PostgreSQL is running
docker-compose ps postgres

# Check connection
docker-compose exec postgres psql -U analytics_user -d analytics_db -c "SELECT 1;"
```

### Redis connection error

```bash
# Check if Redis is running
docker-compose ps redis

# Test connection
docker-compose exec redis redis-cli ping
# Should return: PONG
```

### No events being processed

```bash
# Check consumer is running
docker-compose ps analytics-consumer

# Check consumer logs
docker-compose logs analytics-consumer

# Check Redis stream
docker-compose exec redis redis-cli XLEN analytics:events
```

### High consumer lag

```bash
# Check current lag
curl http://localhost:8006/api/v1/consumer/health

# Increase workers (edit .env)
MAX_WORKERS=5

# Restart consumer
docker-compose restart analytics-consumer
```

---

## 12. Development Workflow

### Making Changes

1. **Edit code** in your IDE
2. **Restart service** (hot reload enabled if DEBUG=true)
   ```bash
   docker-compose restart analytics-service
   ```
3. **Test your changes**
   ```bash
   curl http://localhost:8006/api/v1/your-endpoint
   ```
4. **Run tests**
   ```bash
   docker-compose exec analytics-service pytest
   ```

### Adding New Endpoint

1. **Create/edit router** in `api/v1/`
2. **Register in main.py**
   ```python
   from api.v1 import your_new_router
   app.include_router(your_new_router.router, prefix="/api/v1", tags=["your-tag"])
   ```
3. **Restart service**
4. **Test at** http://localhost:8006/docs

### Adding New KPI

1. **Add calculation method** in `services/kpi_calculator.py`
2. **Add aggregation method** in `services/aggregation_service.py`
3. **Update scheduler** (if needed) in `scheduler/aggregation_jobs.py`
4. **Test**
   ```bash
   curl http://localhost:8006/api/v1/metrics/your-new-kpi
   ```

---

## 13. Useful Commands

### Quick Reference

```bash
# Start everything
docker-compose up -d

# Stop everything
docker-compose down

# Rebuild after code changes
docker-compose up --build

# View all container status
docker-compose ps

# Follow all logs
docker-compose logs -f

# Execute command in container
docker-compose exec analytics-service <command>

# Run Python shell
docker-compose exec analytics-service python

# Run IPython (if installed)
docker-compose exec analytics-service ipython

# Check resource usage
docker stats

# Clean up everything (⚠️ DESTROYS DATA)
docker-compose down -v
```

---

## 14. Next Steps

### Learn More

- **API Documentation**: http://localhost:8006/docs
- **Architecture**: See [ANALYTICS_SERVICE_FINAL_REPORT.md](./ANALYTICS_SERVICE_FINAL_REPORT.md)
- **Production Deployment**: See [PRODUCTION_DEPLOYMENT_GUIDE.md](./PRODUCTION_DEPLOYMENT_GUIDE.md)
- **Full README**: See [README.md](./README.md)

### Explore Features

1. **Create custom dashboard**
   ```bash
   curl -X POST http://localhost:8006/api/v1/dashboards \
     -H "Content-Type: application/json" \
     -d @sample_dashboard.json
   ```

2. **Trigger manual aggregation**
   ```bash
   curl -X POST "http://localhost:8006/api/v1/aggregates/calculate?target_date=2025-10-05&granularity=daily"
   ```

3. **Monitor consumer performance**
   ```bash
   watch -n 5 'curl -s http://localhost:8006/api/v1/consumer/metrics | jq .'
   ```

4. **Test WebSocket broadcasting**
   ```bash
   # Terminal 1: Connect to WebSocket
   wscat -c ws://localhost:8006/api/v1/ws/metrics

   # Terminal 2: Publish events
   # Events will appear in Terminal 1
   ```

---

## 15. Tips & Best Practices

### Performance

- Use cached endpoints when possible
- Batch event publishing (100 events at a time)
- Use appropriate time granularity (daily for < 30 days, weekly for < 6 months, monthly for > 6 months)

### Development

- Always run tests before committing
- Use `DEBUG=true` for hot reload during development
- Check logs regularly for warnings/errors
- Use API docs for testing endpoints

### Debugging

- Enable debug logging: `LOG_LEVEL=DEBUG`
- Use `/health/dependencies` to check external services
- Monitor consumer lag if events not processing
- Check cache hit rate if queries slow

---

## Need Help?

- **Documentation**: See `/docs` folder
- **Issues**: Check existing GitHub issues
- **Team**: Contact analytics-team@yourcompany.com

---

**Happy Coding! 🚀**

---

**Last Updated**: October 6, 2025
**Version**: 1.0.0
