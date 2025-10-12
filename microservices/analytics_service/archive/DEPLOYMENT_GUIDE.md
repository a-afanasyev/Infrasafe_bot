# Analytics Service Deployment Guide

**Version**: 1.0.0
**Environment**: Staging → Production
**Date**: October 6, 2025

---

## 📋 Prerequisites

### Infrastructure Requirements

✅ **Docker Host**:
- Docker 24.0+
- Docker Compose 2.20+
- 4GB RAM minimum (8GB recommended)
- 20GB disk space

✅ **Database**:
- PostgreSQL 15+
- Database: `analytics_db`
- User: `analytics_user`
- Port: 5432 (internal)

✅ **Redis**:
- Redis 7+
- Persistence enabled (AOF)
- Port: 6379 (internal)

✅ **Network**:
- Access to microservices network
- Port 8006 exposed (Analytics API)

---

## 🚀 Staging Deployment (Task 4.2)

### Step 1: Prepare Environment

```bash
# Navigate to analytics service
cd microservices/analytics_service

# Copy environment template
cp .env.example .env.staging

# Edit staging configuration
nano .env.staging
```

### Step 2: Staging Environment Variables

```env
# .env.staging

# Application
DEBUG=False
ANALYTICS_PORT=8006
LOG_LEVEL=INFO

# Database (Staging)
POSTGRES_USER=analytics_user
POSTGRES_PASSWORD=<SECURE_PASSWORD>
POSTGRES_DB=analytics_db_staging
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# Redis (Staging)
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=2
REDIS_PASSWORD=<SECURE_PASSWORD>

# Redis Streams
REDIS_STREAM_NAME=analytics:events
REDIS_CONSUMER_GROUP=analytics-consumers
REDIS_CONSUMER_NAME=analytics-consumer-staging
REDIS_BATCH_SIZE=100
REDIS_BLOCK_TIME=5000

# Event Processing
MAX_WORKERS=3
EVENT_BATCH_SIZE=100
EVENT_RETENTION_DAYS=30

# Metrics
METRICS_UPDATE_INTERVAL=3600
METRICS_CACHE_TTL=300

# Security
SECRET_KEY=<GENERATE_SECURE_KEY>

# Auth Service
AUTH_SERVICE_URL=http://auth-service:8001

# CORS (Staging)
CORS_ORIGINS=["https://staging.example.com"]
```

### Step 3: Deploy to Staging

```bash
# Build images
docker-compose -f docker-compose.staging.yml build

# Start services
docker-compose -f docker-compose.staging.yml up -d

# Check status
docker-compose -f docker-compose.staging.yml ps

# View logs
docker-compose -f docker-compose.staging.yml logs -f analytics-service
```

### Step 4: Verify Deployment

```bash
# Health check
curl http://localhost:8006/api/v1/health

# Expected response:
{
  "service": "analytics-service",
  "version": "1.0.0",
  "status": "healthy",
  "timestamp": "2025-10-06T15:00:00Z",
  "components": {
    "database": {"status": "healthy", "type": "PostgreSQL"},
    "redis": {"status": "healthy", "type": "Redis"}
  }
}

# Readiness check
curl http://localhost:8006/api/v1/health/ready

# List available metrics
curl http://localhost:8006/api/v1/metrics

# Get metrics summary
curl http://localhost:8006/api/v1/metrics/summary?period_hours=24
```

### Step 5: Smoke Tests

```bash
# Run smoke tests
docker-compose -f docker-compose.staging.yml exec analytics-service pytest tests/test_smoke.py -v

# Check consumer is processing events
docker-compose -f docker-compose.staging.yml logs analytics-consumer | grep "Event stored"

# Verify database connectivity
docker-compose -f docker-compose.staging.yml exec postgres psql -U analytics_user -d analytics_db_staging -c "SELECT COUNT(*) FROM event_logs;"

# Verify Redis connectivity
docker-compose -f docker-compose.staging.yml exec redis redis-cli PING
```

### Step 6: 48-Hour Monitoring

**Monitoring Checklist**:

```yaml
Hour 0-2: Initial Observation
  - [ ] All containers running
  - [ ] Health checks passing
  - [ ] Consumer processing events
  - [ ] No error logs

Hour 2-24: Stability Check
  - [ ] Memory usage stable (<2GB)
  - [ ] CPU usage <50%
  - [ ] No memory leaks
  - [ ] Event processing rate consistent
  - [ ] API response times <500ms

Hour 24-48: Performance Validation
  - [ ] 99%+ uptime
  - [ ] Zero critical errors
  - [ ] Cache hit rate >70%
  - [ ] Database queries optimized
  - [ ] Redis memory <1GB
```

**Monitoring Commands**:

```bash
# Watch container stats
docker stats analytics-service analytics-consumer

# Count events processed
docker-compose -f docker-compose.staging.yml exec postgres psql -U analytics_user -d analytics_db_staging -c "SELECT event_type, COUNT(*) FROM event_logs GROUP BY event_type;"

# Check Redis memory
docker-compose -f docker-compose.staging.yml exec redis redis-cli INFO memory

# View error logs
docker-compose -f docker-compose.staging.yml logs analytics-service | grep ERROR

# API performance test
ab -n 1000 -c 10 http://localhost:8006/api/v1/metrics/summary
```

---

## 🔧 Production Deployment

### Prerequisites for Production

✅ **Go/No-Go Checklist**:

```yaml
Staging Validation:
  ✅ 48-hour uptime: 99%+
  ✅ Zero critical bugs
  ✅ All tests passing (60%+ coverage)
  ✅ Performance benchmarks met
  ✅ Security audit complete

Infrastructure:
  ✅ Production database provisioned
  ✅ Redis cluster configured
  ✅ Monitoring setup (Prometheus/Grafana)
  ✅ Logging aggregation (ELK/Loki)
  ✅ Backup strategy defined

Documentation:
  ✅ API documentation published
  ✅ Runbook created
  ✅ Incident response plan
  ✅ Rollback procedures tested
```

### Production Environment Variables

```env
# .env.production

# Application
DEBUG=False
ANALYTICS_PORT=8006
LOG_LEVEL=WARNING

# Database (Production)
POSTGRES_USER=analytics_user
POSTGRES_PASSWORD=<STRONG_PASSWORD>
POSTGRES_DB=analytics_db
POSTGRES_HOST=postgres-primary.production.local
POSTGRES_PORT=5432

# Redis (Production - Cluster)
REDIS_HOST=redis-cluster.production.local
REDIS_PORT=6379
REDIS_DB=2
REDIS_PASSWORD=<STRONG_PASSWORD>

# Redis Streams (Production)
REDIS_STREAM_NAME=analytics:events:prod
REDIS_CONSUMER_GROUP=analytics-consumers-prod
REDIS_CONSUMER_NAME=analytics-consumer-prod-1
REDIS_BATCH_SIZE=100
REDIS_BLOCK_TIME=5000

# Event Processing (Production)
MAX_WORKERS=5
EVENT_BATCH_SIZE=100
EVENT_RETENTION_DAYS=30

# Metrics (Production)
METRICS_UPDATE_INTERVAL=1800  # 30 min
METRICS_CACHE_TTL=300

# Security (Production)
SECRET_KEY=<GENERATE_STRONG_KEY_256_BIT>

# Services (Production)
AUTH_SERVICE_URL=https://auth.production.local

# CORS (Production)
CORS_ORIGINS=["https://app.production.com","https://dashboard.production.com"]
```

### Production Deployment Steps

#### 1. Pre-deployment Checks

```bash
# Run full test suite
pytest tests/ -v --cov=. --cov-report=html

# Security scan
docker scan analytics-service:latest

# Build production image
docker build -t analytics-service:1.0.0 -f Dockerfile .

# Tag for registry
docker tag analytics-service:1.0.0 registry.production.com/analytics-service:1.0.0
docker tag analytics-service:1.0.0 registry.production.com/analytics-service:latest

# Push to registry
docker push registry.production.com/analytics-service:1.0.0
docker push registry.production.com/analytics-service:latest
```

#### 2. Database Migration

```bash
# Backup production database
pg_dump -U analytics_user analytics_db > backup_$(date +%Y%m%d_%H%M%S).sql

# Run migrations
docker-compose -f docker-compose.prod.yml run --rm analytics-service alembic upgrade head

# Verify migration
docker-compose -f docker-compose.prod.yml exec postgres psql -U analytics_user -d analytics_db -c "\dt"
```

#### 3. Blue-Green Deployment

```yaml
Strategy:
  1. Deploy new version (green) alongside old (blue)
  2. Route 10% traffic to green
  3. Monitor for 1 hour
  4. If stable: 50% → 100%
  5. If issues: Rollback to blue

Traffic Split:
  - Nginx / HAProxy weighted routing
  - Monitor error rates, latency
  - Auto-rollback on threshold breach
```

```bash
# Deploy green version
docker-compose -f docker-compose.prod-green.yml up -d

# Health check green
curl http://green.analytics.internal:8006/api/v1/health

# Switch 10% traffic (via load balancer)
# ... configure load balancer ...

# Monitor metrics
watch -n 5 'curl http://green.analytics.internal:8006/api/v1/metrics/summary | jq .kpis.system_error_rate'

# If successful, increase to 100%
# ... update load balancer ...

# Stop blue version
docker-compose -f docker-compose.prod-blue.yml down
```

#### 4. Post-deployment Validation

```bash
# Verify all endpoints
curl https://api.production.com/analytics/v1/health
curl https://api.production.com/analytics/v1/metrics

# Run smoke tests
pytest tests/test_smoke.py -v --production

# Check consumer
docker logs analytics-consumer-prod-1 | tail -100

# Monitor for 2 hours
# ... watch Grafana dashboards ...
```

---

## 📊 Monitoring & Alerts

### Key Metrics to Monitor

```yaml
Application Metrics:
  - API response time (p50, p95, p99)
  - Request rate (req/sec)
  - Error rate (%)
  - Cache hit rate (%)

Infrastructure Metrics:
  - CPU usage (%)
  - Memory usage (MB)
  - Disk I/O
  - Network throughput

Business Metrics:
  - Events processed/sec
  - Active shifts count
  - Request completion rate
  - System error rate
```

### Alert Thresholds

```yaml
Critical Alerts (PagerDuty):
  - Error rate > 5%
  - API p95 latency > 1s
  - Consumer lag > 10,000 events
  - Memory usage > 90%

Warning Alerts (Slack):
  - Error rate > 2%
  - API p95 latency > 500ms
  - Cache hit rate < 60%
  - Consumer lag > 1,000 events
```

### Prometheus Metrics

```python
# Add to main.py
from prometheus_client import Counter, Histogram, Gauge

api_requests = Counter('analytics_api_requests_total', 'Total API requests')
api_latency = Histogram('analytics_api_latency_seconds', 'API latency')
events_processed = Counter('analytics_events_processed_total', 'Events processed')
active_shifts = Gauge('analytics_active_shifts', 'Active shifts count')
```

---

## 🔄 Rollback Procedures

### Scenario 1: Critical Bug Detected

```bash
# Immediate rollback (< 5 minutes)

# 1. Switch traffic back to blue (old version)
# ... update load balancer ...

# 2. Stop green (new version)
docker-compose -f docker-compose.prod-green.yml down

# 3. Verify blue is handling traffic
curl https://api.production.com/analytics/v1/health

# 4. Investigate issue
docker logs analytics-service-green > issue_$(date +%Y%m%d_%H%M%S).log
```

### Scenario 2: Database Migration Failed

```bash
# Rollback migration

# 1. Stop all services
docker-compose -f docker-compose.prod.yml down

# 2. Restore database backup
psql -U analytics_user analytics_db < backup_YYYYMMDD_HHMMSS.sql

# 3. Downgrade Alembic
docker-compose -f docker-compose.prod.yml run --rm analytics-service alembic downgrade -1

# 4. Restart with old version
docker-compose -f docker-compose.prod-blue.yml up -d
```

### Scenario 3: Performance Degradation

```bash
# Gradual rollback

# 1. Reduce traffic to green
# ... load balancer: 100% → 50% → 0% ...

# 2. Monitor if issue resolves
# ... check metrics ...

# 3. If resolved, keep on blue
# If not resolved, investigate root cause
```

---

## 🛡️ Security Checklist

### Pre-deployment Security

```yaml
Secrets Management:
  - [ ] No hardcoded secrets in code
  - [ ] Environment variables encrypted
  - [ ] Secret rotation policy defined
  - [ ] Database passwords strong (256-bit)

Network Security:
  - [ ] HTTPS only (no HTTP)
  - [ ] CORS properly configured
  - [ ] Internal services not exposed
  - [ ] Firewall rules applied

Application Security:
  - [ ] SQL injection protected (parameterized queries)
  - [ ] Input validation on all endpoints
  - [ ] Rate limiting enabled
  - [ ] JWT validation working

Container Security:
  - [ ] Non-root user in container
  - [ ] Minimal base image
  - [ ] No unnecessary packages
  - [ ] Regular security scans
```

---

## 📋 Staging Success Criteria

### After 48 Hours

```yaml
✅ Uptime: ≥99%
✅ Zero critical errors
✅ API p95 latency: <500ms
✅ Event processing: 100+ events/sec
✅ Cache hit rate: >70%
✅ Memory usage: <2GB
✅ CPU usage: <50%
✅ All health checks passing
✅ Consumer lag: <100 events
✅ Database queries: <100ms average
```

### Go/No-Go Decision

**GO to Production** if:
- ✅ All success criteria met
- ✅ No critical bugs
- ✅ Performance acceptable
- ✅ Team confidence high

**NO-GO** if:
- ❌ Uptime <99%
- ❌ Critical bugs found
- ❌ Performance issues
- ❌ Data loss detected

---

## 📞 Support & Escalation

### On-call Rotation

```yaml
Primary On-call:
  - Analytics Team Lead
  - Contact: Slack @analytics-oncall
  - Hours: 24/7

Secondary On-call:
  - Senior Backend Engineer
  - Contact: PagerDuty
  - Hours: 24/7

Escalation Path:
  1. Analytics Team Lead (15 min)
  2. Backend Team Lead (30 min)
  3. CTO (1 hour)
```

### Incident Response

```yaml
P0 (Critical):
  - System down
  - Data loss
  - Security breach
  Response: Immediate (< 15 min)

P1 (High):
  - Partial outage
  - Performance degradation >50%
  Response: < 1 hour

P2 (Medium):
  - Minor bugs
  - Performance degradation <50%
  Response: < 4 hours

P3 (Low):
  - Feature requests
  - Documentation updates
  Response: Next sprint
```

---

**Deployment Guide Version**: 1.0
**Last Updated**: October 6, 2025
**Next Review**: After production deployment
