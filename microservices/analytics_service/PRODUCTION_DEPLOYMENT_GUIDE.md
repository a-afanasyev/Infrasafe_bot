# Analytics Service - Production Deployment Guide

**Version**: 1.0.0
**Date**: October 6, 2025
**Status**: Production Ready

---

## Table of Contents

1. [Pre-Deployment Checklist](#pre-deployment-checklist)
2. [Infrastructure Setup](#infrastructure-setup)
3. [Database Setup](#database-setup)
4. [Service Configuration](#service-configuration)
5. [Deployment Steps](#deployment-steps)
6. [Health Checks](#health-checks)
7. [Monitoring Setup](#monitoring-setup)
8. [Rollback Procedures](#rollback-procedures)
9. [Troubleshooting](#troubleshooting)

---

## Pre-Deployment Checklist

### ✅ Infrastructure Requirements

**Hardware Requirements**:
```
Service Instance:
- CPU: 2 cores minimum (4 cores recommended)
- RAM: 4GB minimum (8GB recommended)
- Disk: 50GB SSD minimum

Consumer Instance:
- CPU: 2 cores minimum
- RAM: 2GB minimum
- Disk: 10GB

Database (PostgreSQL):
- CPU: 4 cores
- RAM: 8GB
- Disk: 100GB SSD (with auto-scaling)

Cache (Redis):
- CPU: 2 cores
- RAM: 4GB
- Disk: 20GB
```

**Network Requirements**:
```
Ports:
- 8006: Analytics Service API (internal)
- 5432: PostgreSQL (internal only)
- 6379: Redis (internal only)

Outbound:
- Access to Shift Service
- Access to Request Service
- Access to other microservices
```

**Software Requirements**:
```
- Docker 24+
- Docker Compose 2.20+
- PostgreSQL 15+
- Redis 7+
- Python 3.11+ (for local development)
```

### ✅ Pre-Deployment Validation

**1. Code Review**:
- [ ] All code reviewed and approved
- [ ] No TODO or FIXME comments in production code
- [ ] All debug logging removed or disabled
- [ ] Security vulnerabilities scanned (0 high/critical)

**2. Testing**:
- [ ] All unit tests passing (95+ cases)
- [ ] All integration tests passing (30+ cases)
- [ ] Performance tests passing (1000+ events/sec)
- [ ] Load testing completed
- [ ] Security testing completed

**3. Documentation**:
- [ ] API documentation up to date
- [ ] Deployment guide reviewed
- [ ] Runbook created
- [ ] Team trained on operations

**4. Dependencies**:
- [ ] PostgreSQL 15 available
- [ ] Redis 7 available
- [ ] Shift Service running
- [ ] Request Service running
- [ ] Network connectivity verified

---

## Infrastructure Setup

### Docker Network

```bash
# Create dedicated network for analytics services
docker network create analytics-network

# Verify network
docker network ls | grep analytics
```

### Persistent Volumes

```bash
# Create volumes for data persistence
docker volume create analytics_postgres_data
docker volume create analytics_redis_data

# Verify volumes
docker volume ls | grep analytics
```

### Resource Limits

**docker-compose.prod.yml**:
```yaml
version: '3.8'

services:
  analytics-service:
    image: analytics-service:1.0.0
    container_name: analytics-service
    restart: unless-stopped
    ports:
      - "8006:8006"
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - LOG_LEVEL=INFO
      - DEBUG=false
    networks:
      - analytics-network
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8006/api/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  analytics-consumer:
    image: analytics-service:1.0.0
    container_name: analytics-consumer
    restart: unless-stopped
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - MAX_WORKERS=3
      - LOG_LEVEL=INFO
    networks:
      - analytics-network
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: python start_consumer.py
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '1.0'
          memory: 1G

  postgres:
    image: postgres:15-alpine
    container_name: analytics-postgres
    restart: unless-stopped
    environment:
      - POSTGRES_USER=${POSTGRES_USER}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - POSTGRES_DB=${POSTGRES_DB}
      - POSTGRES_MAX_CONNECTIONS=200
      - POSTGRES_SHARED_BUFFERS=256MB
    networks:
      - analytics-network
    volumes:
      - analytics_postgres_data:/var/lib/postgresql/data
    deploy:
      resources:
        limits:
          cpus: '4.0'
          memory: 8G
        reservations:
          cpus: '2.0'
          memory: 4G
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: analytics-redis
    restart: unless-stopped
    command: >
      redis-server
      --appendonly yes
      --maxmemory 2gb
      --maxmemory-policy allkeys-lru
    networks:
      - analytics-network
    volumes:
      - analytics_redis_data:/data
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

networks:
  analytics-network:
    driver: bridge

volumes:
  analytics_postgres_data:
    external: true
  analytics_redis_data:
    external: true
```

---

## Database Setup

### 1. Database Creation

```bash
# Connect to PostgreSQL
docker exec -it analytics-postgres psql -U postgres

# Create database and user
CREATE DATABASE analytics_db;
CREATE USER analytics_user WITH ENCRYPTED PASSWORD 'STRONG_PASSWORD_HERE';
GRANT ALL PRIVILEGES ON DATABASE analytics_db TO analytics_user;

# Grant schema permissions
\c analytics_db
GRANT ALL ON SCHEMA public TO analytics_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO analytics_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO analytics_user;

\q
```

### 2. Run Migrations

```bash
# Set environment variables
export DATABASE_URL="postgresql+asyncpg://analytics_user:PASSWORD@localhost:5432/analytics_db"

# Run migrations
docker exec -it analytics-service alembic upgrade head

# Verify tables created
docker exec -it analytics-postgres psql -U analytics_user -d analytics_db -c "\dt"

# Expected output:
#  event_logs
#  kpi_aggregates
#  dashboards
#  alembic_version
```

### 3. Create Indexes

```sql
-- Additional performance indexes
CREATE INDEX CONCURRENTLY idx_event_logs_created_at_desc
  ON event_logs(created_at DESC);

CREATE INDEX CONCURRENTLY idx_event_logs_event_type_created
  ON event_logs(event_type, created_at);

CREATE INDEX CONCURRENTLY idx_kpi_aggregates_period_date_desc
  ON kpi_aggregates(period_date DESC);

-- Verify indexes
SELECT schemaname, tablename, indexname
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;
```

### 4. Set Up Connection Pooling

```bash
# Install pgBouncer (recommended for production)
docker run -d \
  --name pgbouncer \
  --network analytics-network \
  -e POSTGRESQL_HOST=analytics-postgres \
  -e POSTGRESQL_PORT=5432 \
  -e POSTGRESQL_USERNAME=analytics_user \
  -e POSTGRESQL_PASSWORD=PASSWORD \
  -e POSTGRESQL_DATABASE=analytics_db \
  -e PGBOUNCER_POOL_MODE=transaction \
  -e PGBOUNCER_MAX_CLIENT_CONN=1000 \
  -e PGBOUNCER_DEFAULT_POOL_SIZE=25 \
  bitnami/pgbouncer:latest

# Update DATABASE_URL to use pgBouncer
export DATABASE_URL="postgresql+asyncpg://analytics_user:PASSWORD@pgbouncer:6432/analytics_db"
```

---

## Service Configuration

### Environment Variables

Create `.env.production`:

```bash
# Service
SERVICE_NAME=analytics-service
VERSION=1.0.0
PORT=8006
DEBUG=false
LOG_LEVEL=INFO

# Database
DATABASE_URL=postgresql+asyncpg://analytics_user:CHANGE_ME@pgbouncer:6432/analytics_db
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10
DATABASE_POOL_TIMEOUT=30
DATABASE_POOL_RECYCLE=3600

# Redis
REDIS_URL=redis://analytics-redis:6379/0
REDIS_STREAM_NAME=analytics:events
REDIS_CONSUMER_GROUP=analytics-consumers
REDIS_MAX_CONNECTIONS=50

# Consumer
MAX_WORKERS=3
REDIS_BATCH_SIZE=100
CONSUMER_BLOCK_TIME=5000

# Aggregation Scheduler
AGGREGATION_SCHEDULE_ENABLED=true
DAILY_AGGREGATION_HOUR=0
DAILY_AGGREGATION_MINUTE=30
WEEKLY_AGGREGATION_DAY=monday
WEEKLY_AGGREGATION_HOUR=1
MONTHLY_AGGREGATION_DAY=1
MONTHLY_AGGREGATION_HOUR=2

# Cache
WIDGET_CACHE_TTL=300
DASHBOARD_CACHE_TTL=600
REALTIME_WIDGET_TTL=5

# CORS
CORS_ORIGINS=["https://dashboard.yourdomain.com","https://api.yourdomain.com"]

# Security
SECRET_KEY=GENERATE_STRONG_SECRET_KEY_HERE
ALLOWED_HOSTS=["analytics-service","localhost"]

# Monitoring
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id
ENABLE_METRICS=true
METRICS_PORT=9090
```

### Security Hardening

**1. Generate Strong Secrets**:
```bash
# Generate SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate database password
openssl rand -base64 32
```

**2. File Permissions**:
```bash
# Secure environment file
chmod 600 .env.production
chown root:root .env.production

# Verify
ls -la .env.production
# Expected: -rw------- 1 root root
```

**3. Network Security**:
```yaml
# docker-compose.prod.yml
services:
  analytics-service:
    networks:
      - analytics-network
      - frontend-network  # Only if UI needs direct access
    # Expose only what's necessary
    ports:
      - "127.0.0.1:8006:8006"  # Bind to localhost only

  postgres:
    networks:
      - analytics-network  # Internal only
    # NO ports exposed externally
```

---

## Deployment Steps

### Step 1: Pre-Deployment

```bash
# 1. Backup current database (if updating)
docker exec analytics-postgres pg_dump -U analytics_user analytics_db > backup_$(date +%Y%m%d_%H%M%S).sql

# 2. Stop current services (if updating)
docker-compose -f docker-compose.prod.yml down

# 3. Pull latest images
docker pull analytics-service:1.0.0

# 4. Verify environment variables
set -a
source .env.production
set +a
env | grep -E "DATABASE_URL|REDIS_URL|MAX_WORKERS"
```

### Step 2: Database Migration

```bash
# 1. Run migrations (dry-run first)
docker run --rm \
  --network analytics-network \
  -e DATABASE_URL=$DATABASE_URL \
  analytics-service:1.0.0 \
  alembic upgrade head --sql

# 2. If dry-run OK, run actual migration
docker run --rm \
  --network analytics-network \
  -e DATABASE_URL=$DATABASE_URL \
  analytics-service:1.0.0 \
  alembic upgrade head

# 3. Verify migration
docker exec analytics-postgres psql -U analytics_user -d analytics_db \
  -c "SELECT version_num FROM alembic_version;"
```

### Step 3: Service Deployment

```bash
# 1. Start services
docker-compose -f docker-compose.prod.yml up -d

# 2. Watch startup logs
docker-compose -f docker-compose.prod.yml logs -f

# Expected output:
# analytics-service    | 🚀 Starting Analytics Service...
# analytics-service    | ✅ Database initialized
# analytics-service    | ✅ Aggregation scheduler started
# analytics-service    | INFO:     Uvicorn running on http://0.0.0.0:8006
# analytics-consumer   | 🚀 Starting consumer with 3 workers...
# analytics-consumer   | ✅ Consumer started

# 3. Verify containers running
docker-compose -f docker-compose.prod.yml ps

# All services should show "Up (healthy)"
```

### Step 4: Smoke Tests

```bash
# 1. Health check
curl http://localhost:8006/api/v1/health
# Expected: {"status": "healthy", ...}

# 2. Dependencies health
curl http://localhost:8006/api/v1/health/dependencies
# Expected: All dependencies "healthy"

# 3. Test metric endpoint
curl http://localhost:8006/api/v1/metrics/summary
# Expected: KPI data returned

# 4. Test real-time endpoint
curl http://localhost:8006/api/v1/realtime/summary
# Expected: Real-time metrics returned

# 5. Check consumer
curl http://localhost:8006/api/v1/consumer/health
# Expected: {"status": "healthy", "lag": <number>}

# 6. Check scheduler
curl http://localhost:8006/api/v1/scheduler/jobs
# Expected: 3 scheduled jobs listed

# 7. Test WebSocket
wscat -c ws://localhost:8006/api/v1/ws/metrics
# Expected: Connection successful, metrics broadcasted every 5 seconds
```

### Step 5: Integration Tests

```bash
# 1. Publish test event
curl -X POST http://localhost:8006/api/v1/test/event \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "shift.created",
    "service_name": "test",
    "payload": {"shift_id": 999}
  }'

# 2. Verify event processed
sleep 2
curl http://localhost:8006/api/v1/consumer/metrics
# Check: processed_count incremented

# 3. Test aggregation
curl -X POST http://localhost:8006/api/v1/aggregates/calculate?target_date=$(date -d yesterday +%Y-%m-%d)
# Expected: Aggregates calculated

# 4. Test dashboard render
curl http://localhost:8006/api/v1/dashboards/1/render
# Expected: Dashboard data returned

# 5. Test cache
curl http://localhost:8006/api/v1/cache/stats
# Expected: Cache statistics returned
```

---

## Health Checks

### Automated Health Monitoring

**1. Service Health**:
```bash
#!/bin/bash
# healthcheck.sh

SERVICE_URL="http://localhost:8006"

# Check service health
response=$(curl -s -o /dev/null -w "%{http_code}" $SERVICE_URL/api/v1/health)
if [ $response -eq 200 ]; then
  echo "✅ Service healthy"
else
  echo "❌ Service unhealthy (HTTP $response)"
  exit 1
fi

# Check dependencies
response=$(curl -s $SERVICE_URL/api/v1/health/dependencies)
db_status=$(echo $response | jq -r '.database')
redis_status=$(echo $response | jq -r '.redis')

if [ "$db_status" != "healthy" ]; then
  echo "❌ Database unhealthy"
  exit 1
fi

if [ "$redis_status" != "healthy" ]; then
  echo "❌ Redis unhealthy"
  exit 1
fi

echo "✅ All dependencies healthy"
```

**2. Consumer Health**:
```bash
#!/bin/bash
# check_consumer.sh

# Check consumer lag
lag=$(curl -s http://localhost:8006/api/v1/consumer/health | jq -r '.lag')

if [ $lag -gt 1000 ]; then
  echo "⚠️ High consumer lag: $lag messages"
  # Send alert
  exit 1
fi

echo "✅ Consumer lag acceptable: $lag messages"
```

**3. Database Connection Pool**:
```sql
-- Monitor active connections
SELECT
  count(*) as total_connections,
  count(*) FILTER (WHERE state = 'active') as active_connections,
  count(*) FILTER (WHERE state = 'idle') as idle_connections
FROM pg_stat_activity
WHERE datname = 'analytics_db';

-- Should see: total < 50, active < 20
```

**4. Redis Memory**:
```bash
# Check Redis memory usage
docker exec analytics-redis redis-cli INFO memory | grep used_memory_human

# Should be < 2GB
```

---

## Monitoring Setup

### Prometheus Metrics (Optional)

**1. Add Prometheus exporter**:
```python
# Add to main.py
from prometheus_client import make_asgi_app, Counter, Histogram

# Metrics
http_requests_total = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint'])
http_request_duration = Histogram('http_request_duration_seconds', 'HTTP request duration')

# Mount Prometheus metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
```

**2. Prometheus configuration**:
```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'analytics-service'
    scrape_interval: 15s
    static_configs:
      - targets: ['analytics-service:9090']
```

### Logging

**1. Centralized Logging**:
```yaml
# docker-compose.prod.yml
services:
  analytics-service:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
        labels: "service,version"
```

**2. Log Aggregation (Optional - Loki)**:
```yaml
# Add Loki for log aggregation
  loki:
    image: grafana/loki:latest
    ports:
      - "3100:3100"
    command: -config.file=/etc/loki/local-config.yaml
```

### Alerting

**Alert Rules**:
```yaml
# alerts.yml
groups:
  - name: analytics_service
    interval: 30s
    rules:
      - alert: HighConsumerLag
        expr: consumer_lag > 1000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High consumer lag detected"

      - alert: ServiceDown
        expr: up{job="analytics-service"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Analytics Service is down"

      - alert: HighDatabaseConnections
        expr: pg_stat_database_numbackends > 150
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High number of database connections"
```

---

## Rollback Procedures

### Quick Rollback (< 5 minutes)

```bash
# 1. Stop current version
docker-compose -f docker-compose.prod.yml down

# 2. Restore previous version
docker-compose -f docker-compose.prod.yml.backup up -d

# 3. Verify health
curl http://localhost:8006/api/v1/health

# 4. Check logs
docker-compose -f docker-compose.prod.yml logs -f
```

### Database Rollback

```bash
# 1. Stop services
docker-compose -f docker-compose.prod.yml down

# 2. Restore database
cat backup_YYYYMMDD_HHMMSS.sql | \
  docker exec -i analytics-postgres psql -U analytics_user -d analytics_db

# 3. Rollback migrations (if needed)
docker run --rm \
  --network analytics-network \
  -e DATABASE_URL=$DATABASE_URL \
  analytics-service:previous-version \
  alembic downgrade -1

# 4. Restart services
docker-compose -f docker-compose.prod.yml up -d
```

---

## Troubleshooting

### Issue 1: Service Won't Start

**Symptoms**:
- Container exits immediately
- Health check fails

**Diagnosis**:
```bash
# Check logs
docker logs analytics-service --tail 100

# Common issues:
# - Database connection failed
# - Redis connection failed
# - Missing environment variables
```

**Solutions**:
```bash
# Test database connection
docker exec analytics-postgres psql -U analytics_user -d analytics_db -c "SELECT 1;"

# Test Redis connection
docker exec analytics-redis redis-cli ping

# Verify environment variables
docker exec analytics-service env | grep -E "DATABASE_URL|REDIS_URL"
```

### Issue 2: High Consumer Lag

**Symptoms**:
- Lag > 1000 messages
- Events not processing

**Diagnosis**:
```bash
# Check consumer metrics
curl http://localhost:8006/api/v1/consumer/metrics

# Check consumer logs
docker logs analytics-consumer --tail 100
```

**Solutions**:
```bash
# Option 1: Increase workers
docker-compose -f docker-compose.prod.yml down
# Edit .env.production: MAX_WORKERS=5
docker-compose -f docker-compose.prod.yml up -d

# Option 2: Check for errors in DLQ
curl http://localhost:8006/api/v1/consumer/dlq

# Option 3: Restart consumer
docker restart analytics-consumer
```

### Issue 3: High Database Connections

**Symptoms**:
- "too many connections" errors
- Slow queries

**Diagnosis**:
```sql
-- Check active connections
SELECT count(*) FROM pg_stat_activity WHERE datname = 'analytics_db';

-- Check connection pool
SHOW max_connections;
```

**Solutions**:
```bash
# Option 1: Increase max_connections
docker exec analytics-postgres psql -U postgres -c \
  "ALTER SYSTEM SET max_connections = 300;"
docker restart analytics-postgres

# Option 2: Add pgBouncer (recommended)
# See "Database Setup" section
```

### Issue 4: Cache Misses

**Symptoms**:
- Low cache hit rate (<70%)
- Slow dashboard loading

**Diagnosis**:
```bash
# Check cache stats
curl http://localhost:8006/api/v1/cache/stats

# Check Redis memory
docker exec analytics-redis redis-cli INFO memory
```

**Solutions**:
```bash
# Option 1: Increase Redis memory
# Edit docker-compose.prod.yml:
#   redis:
#     command: redis-server --maxmemory 4gb

# Option 2: Warmup popular dashboards
curl -X POST http://localhost:8006/api/v1/cache/warmup/dashboard/1
curl -X POST http://localhost:8006/api/v1/cache/warmup/dashboard/2

# Option 3: Increase TTLs
# Edit .env.production:
#   DASHBOARD_CACHE_TTL=1200
```

---

## Maintenance

### Daily Tasks

```bash
# 1. Check service health
curl http://localhost:8006/api/v1/health

# 2. Check consumer lag
curl http://localhost:8006/api/v1/consumer/health

# 3. Review logs for errors
docker-compose -f docker-compose.prod.yml logs --since 24h | grep ERROR
```

### Weekly Tasks

```bash
# 1. Database backup
docker exec analytics-postgres pg_dump -U analytics_user analytics_db > \
  weekly_backup_$(date +%Y%m%d).sql

# 2. Check database size
docker exec analytics-postgres psql -U analytics_user -d analytics_db -c \
  "SELECT pg_size_pretty(pg_database_size('analytics_db'));"

# 3. Check slow queries
docker exec analytics-postgres psql -U analytics_user -d analytics_db -c \
  "SELECT query, calls, total_time, mean_time FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;"

# 4. Vacuum database
docker exec analytics-postgres psql -U analytics_user -d analytics_db -c "VACUUM ANALYZE;"
```

### Monthly Tasks

```bash
# 1. Review and clean old events (if retention policy)
docker exec analytics-postgres psql -U analytics_user -d analytics_db -c \
  "DELETE FROM event_logs WHERE created_at < NOW() - INTERVAL '90 days';"

# 2. Review indexes
docker exec analytics-postgres psql -U analytics_user -d analytics_db -c \
  "SELECT schemaname, tablename, indexname, idx_scan FROM pg_stat_user_indexes ORDER BY idx_scan;"

# 3. Update Docker images
docker pull postgres:15-alpine
docker pull redis:7-alpine

# 4. Security updates
docker exec analytics-service pip list --outdated
```

---

## Performance Tuning

### PostgreSQL Tuning

```sql
-- Edit postgresql.conf
ALTER SYSTEM SET shared_buffers = '2GB';
ALTER SYSTEM SET effective_cache_size = '6GB';
ALTER SYSTEM SET maintenance_work_mem = '512MB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET wal_buffers = '16MB';
ALTER SYSTEM SET default_statistics_target = 100;
ALTER SYSTEM SET random_page_cost = 1.1;
ALTER SYSTEM SET effective_io_concurrency = 200;
ALTER SYSTEM SET work_mem = '10MB';
ALTER SYSTEM SET min_wal_size = '1GB';
ALTER SYSTEM SET max_wal_size = '4GB';

-- Restart PostgreSQL
docker restart analytics-postgres
```

### Redis Tuning

```bash
# Edit redis.conf
docker exec analytics-redis redis-cli CONFIG SET maxmemory-policy allkeys-lru
docker exec analytics-redis redis-cli CONFIG SET maxmemory 4gb
docker exec analytics-redis redis-cli CONFIG SET save "900 1 300 10 60 10000"
docker exec analytics-redis redis-cli CONFIG REWRITE
```

---

## Support

### Contacts

- **Deployment Issues**: devops@yourcompany.com
- **Application Bugs**: analytics-team@yourcompany.com
- **On-Call**: +1-XXX-XXX-XXXX

### Documentation

- API Docs: http://localhost:8006/docs
- Architecture: See ANALYTICS_SERVICE_FINAL_REPORT.md
- Runbook: See this document

---

**Document Version**: 1.0.0
**Last Updated**: October 6, 2025
**Next Review**: November 6, 2025
