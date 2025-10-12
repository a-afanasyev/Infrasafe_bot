# Analytics Service - Production Deployment Checklist

**Version**: 1.0.0
**Service**: Analytics Service
**Target Environment**: Production
**Deployment Date**: ___________
**Deployed By**: ___________

---

## Pre-Deployment Checklist

### 1. Code Review & Quality ✅

- [ ] All code reviewed and approved by tech lead
- [ ] No `TODO`, `FIXME`, or `HACK` comments in production code
- [ ] All debug logging removed or set to appropriate level
- [ ] No hardcoded credentials or secrets in code
- [ ] Code follows team coding standards
- [ ] All linting warnings resolved
- [ ] Type hints added to all public methods

**Reviewer**: ___________ **Date**: ___________

---

### 2. Testing ✅

#### Unit Tests
- [ ] All unit tests passing (40+ tests)
- [ ] Test coverage ≥ 60%
- [ ] No flaky tests
- [ ] Critical path tests included

**Test Results**: ___________ **Coverage**: ___________%

#### Integration Tests
- [ ] All integration tests passing (30+ tests)
- [ ] Event processing flow tested
- [ ] Aggregation pipeline tested
- [ ] Real-time metrics flow tested
- [ ] Dashboard rendering tested

**Test Results**: ___________

#### Performance Tests
- [ ] Event processing: ≥1000 events/sec
- [ ] Query performance: <500ms uncached, <50ms cached
- [ ] WebSocket: 100+ concurrent connections
- [ ] Cache hit rate: ≥80%

**Performance Results**: ___________

#### Security Tests
- [ ] SQL injection tests passed
- [ ] XSS tests passed
- [ ] CORS configured correctly
- [ ] Rate limiting tested
- [ ] Authentication/authorization tested

**Security Scan Results**: ___________

---

### 3. Infrastructure ✅

#### Hardware Resources
- [ ] Service instance: 2+ CPU cores, 4+ GB RAM
- [ ] Consumer instance: 2+ CPU cores, 2+ GB RAM
- [ ] PostgreSQL: 4+ CPU cores, 8+ GB RAM, 100+ GB SSD
- [ ] Redis: 2+ CPU cores, 4+ GB RAM

**Approved By**: ___________ **Date**: ___________

#### Network
- [ ] Port 8006 accessible internally
- [ ] PostgreSQL accessible (internal only)
- [ ] Redis accessible (internal only)
- [ ] Firewall rules configured
- [ ] Load balancer configured (if applicable)

**Network Configuration**: ___________

#### Docker
- [ ] Docker 24+ installed
- [ ] Docker Compose 2.20+ installed
- [ ] Docker network `analytics-network` created
- [ ] Persistent volumes created
- [ ] Resource limits configured

**Docker Version**: ___________

---

### 4. Database Setup ✅

- [ ] PostgreSQL 15+ running
- [ ] Database `analytics_db` created
- [ ] User `analytics_user` created with strong password
- [ ] Permissions granted correctly
- [ ] Connection pooling configured (pgBouncer recommended)
- [ ] Backups scheduled
- [ ] Retention policy configured

**Database Version**: ___________
**Backup Schedule**: ___________

#### Migrations
- [ ] Alembic migrations tested in staging
- [ ] Migration dry-run executed successfully
- [ ] Rollback procedure tested
- [ ] Migration executed: `alembic upgrade head`
- [ ] Tables verified: `event_logs`, `kpi_aggregates`, `dashboards`

**Migration Status**: ___________

#### Indexes
- [ ] All required indexes created
- [ ] Index performance verified
- [ ] No missing indexes detected

**Index Check**: ___________

---

### 5. Cache Setup ✅

- [ ] Redis 7+ running
- [ ] Redis maxmemory configured (4GB recommended)
- [ ] Redis eviction policy: `allkeys-lru`
- [ ] Redis persistence enabled (AOF)
- [ ] Redis backup scheduled

**Redis Version**: ___________
**Max Memory**: ___________

---

### 6. Configuration ✅

#### Environment Variables
- [ ] `.env.production` file created
- [ ] All required variables set
- [ ] No default/example values in production
- [ ] Strong passwords generated
- [ ] SECRET_KEY generated (32+ characters)
- [ ] File permissions: 600 (owner read/write only)

**Required Variables Checklist**:
- [ ] DATABASE_URL
- [ ] REDIS_URL
- [ ] SECRET_KEY
- [ ] MAX_WORKERS
- [ ] CORS_ORIGINS
- [ ] LOG_LEVEL=INFO
- [ ] DEBUG=false

**Configuration Review**: ___________

#### Service Configuration
- [ ] Port 8006 configured
- [ ] Worker count: 3 (or tuned based on load)
- [ ] Batch size: 100
- [ ] Cache TTLs configured
- [ ] Scheduler enabled
- [ ] CORS origins whitelisted

**Configuration File**: ___________

---

### 7. Monitoring & Logging ✅

#### Health Checks
- [ ] Health endpoint configured: `/api/v1/health`
- [ ] Dependencies health check: `/api/v1/health/dependencies`
- [ ] Readiness probe configured
- [ ] Liveness probe configured

**Health Check URL**: ___________

#### Logging
- [ ] Log level: INFO (not DEBUG)
- [ ] Centralized logging configured (optional)
- [ ] Log rotation configured
- [ ] Error tracking configured (Sentry, etc. - optional)

**Logging Setup**: ___________

#### Metrics (Optional)
- [ ] Prometheus metrics endpoint (optional)
- [ ] Grafana dashboards created (optional)
- [ ] Alerting rules configured (optional)

**Monitoring Setup**: ___________

---

### 8. Security ✅

- [ ] No hardcoded secrets in code
- [ ] Environment variables used for all secrets
- [ ] Database credentials strong and unique
- [ ] Redis password set (if exposed)
- [ ] CORS properly configured
- [ ] SQL injection prevention verified
- [ ] Input validation on all endpoints
- [ ] Rate limiting configured (optional)
- [ ] SSL/TLS configured (if external access)

**Security Audit**: ___________ **Date**: ___________

---

### 9. Documentation ✅

- [ ] README.md updated
- [ ] API documentation available (`/docs`)
- [ ] Deployment guide reviewed
- [ ] Runbook created
- [ ] Team trained on operations
- [ ] On-call rotation established

**Documentation Review**: ___________

---

## Deployment Steps

### Phase 1: Pre-Deployment (15 minutes)

- [ ] **Backup current database** (if updating existing system)
  ```bash
  docker exec analytics-postgres pg_dump -U analytics_user analytics_db > backup_$(date +%Y%m%d_%H%M%S).sql
  ```
  **Backup Location**: ___________

- [ ] **Stop current services** (if updating)
  ```bash
  docker-compose -f docker-compose.prod.yml down
  ```
  **Stopped At**: ___________

- [ ] **Pull latest images**
  ```bash
  docker pull analytics-service:1.0.0
  ```
  **Image Tag**: ___________

- [ ] **Verify environment variables**
  ```bash
  source .env.production
  env | grep -E "DATABASE_URL|REDIS_URL|MAX_WORKERS"
  ```
  **Verified By**: ___________

---

### Phase 2: Database Migration (10 minutes)

- [ ] **Dry-run migration**
  ```bash
  docker run --rm --network analytics-network \
    -e DATABASE_URL=$DATABASE_URL \
    analytics-service:1.0.0 \
    alembic upgrade head --sql
  ```
  **Dry-run Result**: ___________

- [ ] **Execute migration**
  ```bash
  docker run --rm --network analytics-network \
    -e DATABASE_URL=$DATABASE_URL \
    analytics-service:1.0.0 \
    alembic upgrade head
  ```
  **Migration Completed**: ___________

- [ ] **Verify tables**
  ```bash
  docker exec analytics-postgres psql -U analytics_user -d analytics_db -c "\dt"
  ```
  **Tables Verified**: ___________

---

### Phase 3: Service Startup (10 minutes)

- [ ] **Start services**
  ```bash
  docker-compose -f docker-compose.prod.yml up -d
  ```
  **Started At**: ___________

- [ ] **Watch startup logs**
  ```bash
  docker-compose -f docker-compose.prod.yml logs -f
  ```
  **Expected Output**:
  - "🚀 Starting Analytics Service..."
  - "✅ Database initialized"
  - "✅ Aggregation scheduler started"
  - "INFO: Uvicorn running on http://0.0.0.0:8006"

  **Startup Successful**: ___________

- [ ] **Verify containers running**
  ```bash
  docker-compose -f docker-compose.prod.yml ps
  ```
  **All Services Up**: ___________

---

### Phase 4: Smoke Tests (15 minutes)

#### Basic Health
- [ ] **Service health check**
  ```bash
  curl http://localhost:8006/api/v1/health
  ```
  **Expected**: `{"status": "healthy"}`
  **Result**: ___________

- [ ] **Dependencies health**
  ```bash
  curl http://localhost:8006/api/v1/health/dependencies
  ```
  **Expected**: All dependencies "healthy"
  **Result**: ___________

#### Functionality
- [ ] **Metrics endpoint**
  ```bash
  curl http://localhost:8006/api/v1/metrics/summary
  ```
  **Result**: ___________

- [ ] **Real-time metrics**
  ```bash
  curl http://localhost:8006/api/v1/realtime/summary
  ```
  **Result**: ___________

- [ ] **Consumer health**
  ```bash
  curl http://localhost:8006/api/v1/consumer/health
  ```
  **Expected**: Lag < 100
  **Result**: ___________

- [ ] **Scheduler jobs**
  ```bash
  curl http://localhost:8006/api/v1/scheduler/jobs
  ```
  **Expected**: 3 jobs listed
  **Result**: ___________

- [ ] **Dashboard list**
  ```bash
  curl http://localhost:8006/api/v1/dashboards
  ```
  **Result**: ___________

#### WebSocket
- [ ] **WebSocket connection**
  ```bash
  wscat -c ws://localhost:8006/api/v1/ws/metrics
  ```
  **Expected**: Connection successful, metrics every 5 seconds
  **Result**: ___________

---

### Phase 5: Integration Tests (15 minutes)

- [ ] **Publish test event**
  ```bash
  # Use event publisher from another service
  ```
  **Event Published**: ___________

- [ ] **Verify event processed**
  ```bash
  sleep 5
  curl http://localhost:8006/api/v1/consumer/metrics
  ```
  **Processed Count Increased**: ___________

- [ ] **Test aggregation**
  ```bash
  curl -X POST "http://localhost:8006/api/v1/aggregates/calculate?target_date=$(date -d yesterday +%Y-%m-%d)"
  ```
  **Aggregation Successful**: ___________

- [ ] **Test dashboard rendering**
  ```bash
  curl http://localhost:8006/api/v1/dashboards/1/render
  ```
  **Dashboard Rendered**: ___________

- [ ] **Test cache**
  ```bash
  curl http://localhost:8006/api/v1/cache/stats
  ```
  **Cache Working**: ___________

---

### Phase 6: Load Sample Data (10 minutes)

- [ ] **Load sample dashboards**
  ```bash
  docker exec -i analytics-postgres psql -U analytics_user -d analytics_db < sample_dashboards.sql
  ```
  **Dashboards Loaded**: ___________

- [ ] **Verify dashboards**
  ```bash
  curl http://localhost:8006/api/v1/dashboards
  ```
  **Expected**: 5 dashboards
  **Result**: ___________

- [ ] **Test dashboard rendering**
  ```bash
  curl http://localhost:8006/api/v1/dashboards/slug/shift-management-overview/render
  ```
  **Result**: ___________

---

### Phase 7: Performance Validation (15 minutes)

- [ ] **Monitor resource usage**
  ```bash
  docker stats analytics-service analytics-consumer analytics-postgres analytics-redis
  ```
  **CPU < 50%**: ___________
  **Memory < 80%**: ___________

- [ ] **Check database connections**
  ```sql
  SELECT count(*) FROM pg_stat_activity WHERE datname = 'analytics_db';
  ```
  **Connections < 50**: ___________

- [ ] **Check Redis memory**
  ```bash
  docker exec analytics-redis redis-cli INFO memory | grep used_memory_human
  ```
  **Memory < 2GB**: ___________

- [ ] **Monitor consumer lag**
  ```bash
  curl http://localhost:8006/api/v1/consumer/health
  ```
  **Lag < 100**: ___________

---

## Post-Deployment Checklist

### Immediate (Within 1 hour)

- [ ] **Monitor logs for errors**
  ```bash
  docker-compose -f docker-compose.prod.yml logs --since 1h | grep ERROR
  ```
  **No Critical Errors**: ___________

- [ ] **Verify all endpoints responding**
  - [ ] Health: ___________
  - [ ] Metrics: ___________
  - [ ] Real-time: ___________
  - [ ] Dashboards: ___________
  - [ ] WebSocket: ___________

- [ ] **Check consumer processing events**
  ```bash
  watch -n 5 'curl -s http://localhost:8006/api/v1/consumer/metrics | jq .processed_count'
  ```
  **Processing Events**: ___________

- [ ] **Verify scheduled jobs running**
  ```bash
  curl http://localhost:8006/api/v1/scheduler/jobs
  ```
  **Next Run Times Set**: ___________

---

### Short-term (Within 24 hours)

- [ ] **Monitor resource trends**
  - [ ] CPU usage stable
  - [ ] Memory usage stable
  - [ ] Disk usage acceptable
  - [ ] Network traffic normal

- [ ] **Check for memory leaks**
  ```bash
  docker stats --no-stream analytics-service
  # Compare after 24h
  ```
  **Memory Stable**: ___________

- [ ] **Verify cache hit rate**
  ```bash
  curl http://localhost:8006/api/v1/cache/stats
  ```
  **Hit Rate > 80%**: ___________

- [ ] **Check database size growth**
  ```sql
  SELECT pg_size_pretty(pg_database_size('analytics_db'));
  ```
  **Size**: ___________ **Growth Rate Acceptable**: ___________

- [ ] **Monitor consumer lag trends**
  **Average Lag**: ___________ **Max Lag**: ___________

- [ ] **Review aggregation job results**
  - [ ] Daily aggregation ran successfully
  - [ ] Weekly aggregation scheduled
  - [ ] Monthly aggregation scheduled

---

### Medium-term (Within 1 week)

- [ ] **Setup monitoring dashboards** (if not done)
- [ ] **Configure alerting rules**
- [ ] **Establish on-call rotation**
- [ ] **Document any issues encountered**
- [ ] **Tune performance if needed**
- [ ] **Review and optimize slow queries**
- [ ] **Setup backup verification**
- [ ] **Conduct disaster recovery drill**

---

## Rollback Procedure

### If Deployment Fails

**Decision Point**: If critical issues found, initiate rollback

- [ ] **Stop new services**
  ```bash
  docker-compose -f docker-compose.prod.yml down
  ```
  **Stopped At**: ___________

- [ ] **Restore database backup**
  ```bash
  cat backup_YYYYMMDD_HHMMSS.sql | \
    docker exec -i analytics-postgres psql -U analytics_user -d analytics_db
  ```
  **Restored At**: ___________

- [ ] **Rollback migrations** (if needed)
  ```bash
  docker run --rm --network analytics-network \
    -e DATABASE_URL=$DATABASE_URL \
    analytics-service:previous-version \
    alembic downgrade -1
  ```
  **Rolled Back To**: ___________

- [ ] **Start previous version**
  ```bash
  docker-compose -f docker-compose.prod.yml.backup up -d
  ```
  **Previous Version Running**: ___________

- [ ] **Verify health**
  ```bash
  curl http://localhost:8006/api/v1/health
  ```
  **Health Check**: ___________

- [ ] **Document rollback reason**: ___________________________________________

---

## Sign-off

### Deployment Team

| Role | Name | Signature | Date |
|------|------|-----------|------|
| **Tech Lead** | | | |
| **DevOps Engineer** | | | |
| **QA Engineer** | | | |
| **Product Owner** | | | |

### Go/No-Go Decision

- [ ] **GO** - Proceed with production deployment
- [ ] **NO-GO** - Issues found, deployment postponed

**Decision Made By**: ___________ **Date**: ___________

**Reason (if NO-GO)**: ___________________________________________

---

## Post-Deployment Notes

**Issues Encountered**:


**Resolutions Applied**:


**Performance Observations**:


**Recommendations for Next Deployment**:


---

**Deployment Completed**: ___________ **Time**: ___________
**Deployment Duration**: ___________ minutes
**Status**: ✅ **SUCCESS** / ❌ **FAILED** / ⚠️ **PARTIAL**

---

**Document Version**: 1.0.0
**Last Updated**: October 6, 2025
