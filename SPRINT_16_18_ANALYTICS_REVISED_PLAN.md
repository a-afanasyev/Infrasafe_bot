# Sprint 16-18: Analytics Service - REVISED REALISTIC PLAN

**Дата пересмотра**: 6 октября 2025
**Статус**: 📋 REVISED - READY FOR APPROVAL
**Приоритет**: 🥇 КРИТИЧЕСКИЙ
**Версия**: 2.0 (Revised)

---

## ⚠️ КРИТИЧЕСКИЕ ИЗМЕНЕНИЯ от v1.0

### Проблемы исходного плана:
1. ❌ **Переоценка объема**: 120 часов ≠ 3-4 недели (реально 6-8 недель)
2. ❌ **AI функциональность**: 8 часов для 95% accuracy нереалистично
3. ❌ **Интеграция 7 сервисов**: зависимость не учтена, ресурсы не выделены
4. ❌ **Нагрузочное тестирование**: 24-часовые тесты требуют +3-5 дней
5. ❌ **Отсутствие рисков**: нет анализа рисков и fallback планов
6. ❌ **Производительность**: 10k events/sec без архитектуры масштабирования

### Новый подход:
✅ **Incremental delivery** - 3 инкремента вместо 1 спринта
✅ **Realistic timelines** - 8-10 недель вместо 3-4
✅ **Risk management** - детальный анализ рисков
✅ **Clear dependencies** - выделенные ресурсы для интеграций
✅ **Measurable criteria** - реалистичные метрики успеха

---

## 🎯 REVISED STRATEGY: 3 INCREMENTS

### Increment 1: Foundation & Core KPIs (4 weeks)
**Goal**: Stable event collection + basic analytics
**Scope**: 40% of original plan
**Team**: 2 developers full-time

### Increment 2: Real-time & Dashboards (3 weeks)
**Goal**: Live metrics + visualization
**Scope**: 30% of original plan
**Team**: 2 developers + 1 frontend

### Increment 3: AI & Advanced Analytics (3 weeks)
**Goal**: AI insights + predictions (R&D phase)
**Scope**: 30% of original plan
**Team**: 1 ML engineer + 1 backend dev

**Total**: 10 weeks (2.5 months) instead of 3-4 weeks

---

## 📊 INCREMENT 1: FOUNDATION (Weeks 1-4)

### Objectives
- ✅ Event collection from **2-3 services** (not 7)
- ✅ **5-7 core KPIs** (not 20+)
- ✅ Basic API endpoints (read-only)
- ✅ 60% test coverage (not 70%)
- ✅ Staging deployment

### Tasks Breakdown (60 hours total)

#### Week 1: Setup & Infrastructure (20 hours)
```yaml
Task 1.1: Project Setup (8h)
  - FastAPI application structure
  - Docker + docker-compose
  - PostgreSQL database setup
  - Alembic migrations
  - Basic health checks
  - CI/CD pipeline skeleton

  Deliverables:
    ✅ Service running in Docker
    ✅ Database connected
    ✅ Health endpoint /health
    ✅ GitHub Actions workflow

Task 1.2: Core Data Models (6h)
  Minimal schema (3 models instead of 6):
    - EventLog (raw events storage)
    - MetricSnapshot (point-in-time metrics)
    - AggregatedMetric (hourly aggregations only)

  Deliverables:
    ✅ 3 models with migrations
    ✅ Pydantic schemas
    ✅ Basic CRUD operations

Task 1.3: Redis Streams Setup (6h)
  - Redis connection manager
  - Stream consumer (single consumer group)
  - Event deserialization
  - Error handling + DLQ

  Deliverables:
    ✅ Consumes from 1 Redis stream
    ✅ Events persisted to EventLog
    ✅ Dead letter queue for failures
```

#### Week 2: Event Integration (20 hours)
```yaml
Task 2.1: Shift Service Integration (8h)
  Why Shift Service first:
    ✓ Already has analytics_service.py
    ✓ Events already defined
    ✓ Team familiar with codebase

  Steps:
    1. Add event publishing to Shift Service (4h)
    2. Configure Redis Streams (1h)
    3. Test event flow (2h)
    4. Monitor & validate (1h)

  Events to capture:
    - shift.created
    - shift.completed
    - shift.cancelled

  Deliverables:
    ✅ Shift Service publishes 3 event types
    ✅ Analytics consumes all 3
    ✅ Events visible in EventLog table

Task 2.2: Request Service Integration (8h)
  Events to capture:
    - request.created
    - request.assigned
    - request.completed

  Deliverables:
    ✅ Request Service publishes events
    ✅ Analytics processes both services
    ✅ No event loss (<0.1% drop rate)

Task 2.3: Event Validation & Storage (4h)
  - Schema validation (Pydantic)
  - Duplicate detection
  - Timestamp normalization
  - Metadata enrichment

  Deliverables:
    ✅ Invalid events rejected
    ✅ Duplicates filtered
    ✅ Metadata added (service, version)
```

#### Week 3: Core KPIs (12 hours)
```yaml
Task 3.1: KPI Calculator (8h)
  7 Core KPIs only:
    1. Active shifts (current count)
    2. Shift completion rate (%)
    3. Total requests (daily count)
    4. Request completion rate (%)
    5. Average request resolution time (hours)
    6. Executor utilization (%)
    7. System error rate (%)

  Implementation:
    - Simple SQL queries (no complex aggregations)
    - Hourly updates (not real-time)
    - Basic caching (Redis, 5min TTL)

  Deliverables:
    ✅ 7 KPIs calculate correctly
    ✅ Updates every hour
    ✅ Cached in Redis

Task 3.2: Basic API (4h)
  3 Endpoints only:
    GET /api/v1/metrics/{metric_name}
    GET /api/v1/metrics/summary
    GET /api/v1/health

  Features:
    - JWT authentication (via Auth Service)
    - Date range filtering
    - Simple JSON response

  Deliverables:
    ✅ 3 endpoints working
    ✅ Authentication verified
    ✅ Response time < 500ms
```

#### Week 4: Testing & Deployment (8 hours)
```yaml
Task 4.1: Testing (6h)
  Target: 60% coverage (realistic)

  Unit Tests (30%):
    - Model tests
    - KPI calculation tests
    - Event validation tests

  Integration Tests (30%):
    - API endpoint tests
    - Database integration
    - Redis integration

  Deliverables:
    ✅ 60% test coverage
    ✅ All critical paths tested
    ✅ CI passes

Task 4.2: Staging Deployment (2h)
  - Deploy to staging environment
  - Smoke tests
  - Monitor for 48 hours

  Deliverables:
    ✅ Service running in staging
    ✅ No critical errors
    ✅ Metrics collecting
```

### Success Criteria Increment 1
```yaml
Functional:
  ✅ 2 services integrated (Shift, Request)
  ✅ 7 KPIs calculating correctly
  ✅ Events stored with <1% loss
  ✅ API responds in <500ms

Performance (relaxed):
  ✅ 100 events/sec (not 10k)
  ✅ 10 concurrent API requests
  ✅ 1GB storage for 7 days

Quality:
  ✅ 60% test coverage
  ✅ Zero critical bugs
  ✅ 95% uptime in staging
```

---

## 📊 INCREMENT 2: REAL-TIME & DASHBOARDS (Weeks 5-7)

### Objectives
- ✅ Real-time metrics (5 sec updates)
- ✅ WebSocket support
- ✅ 2 dashboards (not 4)
- ✅ Add 2-3 more services
- ✅ Hourly aggregations

### Tasks (48 hours)

#### Week 5: Real-time Processing (16h)
```yaml
Task 5.1: Redis Streams Optimization (6h)
  - Consumer group optimization
  - Parallel processing (3 workers)
  - Backpressure handling

  Deliverables:
    ✅ Processes 1000 events/sec
    ✅ Lag < 5 seconds
    ✅ Auto-scaling workers

Task 5.2: WebSocket Server (6h)
  - WebSocket endpoint /ws/metrics
  - Connection management
  - Message broadcasting
  - Heartbeat/reconnection

  Deliverables:
    ✅ Support 100 concurrent connections
    ✅ Real-time metric updates
    ✅ Stable connections (99% uptime)

Task 5.3: Real-time KPIs (4h)
  Add 3 real-time metrics:
    - Active users (current)
    - Requests in progress (current)
    - Active shifts (current)

  Deliverables:
    ✅ Updates every 5 seconds
    ✅ Push via WebSocket
    ✅ Fallback to polling
```

#### Week 6: Aggregations & Integration (20h)
```yaml
Task 6.1: Hourly Aggregations (8h)
  - Scheduled jobs (APScheduler)
  - Rollup logic (1hour → 1day)
  - Retention policy (30 days hourly, 365 days daily)

  Tables:
    - metrics_hourly (30 day retention)
    - metrics_daily (365 day retention)

  Deliverables:
    ✅ Hourly aggregation job runs
    ✅ Daily rollup works
    ✅ Old data purged

Task 6.2: Additional Service Integrations (12h)
  Services to add:
    - Auth Service (4h) - login/logout events
    - User Service (4h) - user created events
    - Notification Service (4h) - notification sent events

  Total: 5 services (Shift, Request, Auth, User, Notification)

  Deliverables:
    ✅ 3 new services integrated
    ✅ 5 services total publishing events
    ✅ Event schemas validated
```

#### Week 7: Dashboards (12h)
```yaml
Task 7.1: Dashboard API (4h)
  Endpoints:
    GET /api/v1/dashboards
    GET /api/v1/dashboards/{id}
    POST /api/v1/dashboards

  Deliverables:
    ✅ CRUD for dashboards
    ✅ JSON configuration
    ✅ Widget rendering data

Task 7.2: Executive Dashboard (4h)
  Widgets:
    - Active users (gauge)
    - Request volume (line chart)
    - Shift coverage (pie chart)
    - Error rate (number card)

  Deliverables:
    ✅ 4 widgets working
    ✅ Live updates via WebSocket
    ✅ Export to JSON

Task 7.3: Operations Dashboard (4h)
  Widgets:
    - Request queue (table)
    - SLA compliance (gauge)
    - Shift schedule (calendar view)

  Deliverables:
    ✅ 3 widgets working
    ✅ Filterable by date
    ✅ Exportable
```

### Success Criteria Increment 2
```yaml
Functional:
  ✅ 5 services integrated
  ✅ 10 total KPIs (7 base + 3 real-time)
  ✅ 2 dashboards operational
  ✅ Real-time updates working

Performance:
  ✅ 1000 events/sec (10x Increment 1)
  ✅ 100 concurrent WebSocket clients
  ✅ WebSocket latency < 1 sec

Quality:
  ✅ 65% test coverage
  ✅ 48-hour staging validation
  ✅ Zero data loss
```

---

## 📊 INCREMENT 3: ANALYTICS & PRODUCTION (Weeks 8-10)

⚠️ **AI FEATURES DEFERRED**: Все ML/AI функции отложены до готовности AI Service
📋 **См. детали**: [AI_INTEGRATION_FUTURE_PLAN.md](./AI_INTEGRATION_FUTURE_PLAN.md)

### Objectives
- ✅ Alert system (rule-based, БЕЗ AI)
- ✅ Historical analysis (SQL-based)
- ✅ AI Service stubs (заглушки)
- ✅ Documentation
- ✅ Production deployment

### Tasks (36 hours, было 48h)

#### Week 8: Stubs + Alerts (12h, было 16h)
```yaml
Task 8.1: AI Service Stubs Implementation (4h) - НОВОЕ
  Создание заглушек для будущей AI интеграции:
    - AIServiceClientStub (HTTP client stub)
    - AnomalyDetectorStub (rule-based fallback)
    - PredictorStub (average-based fallback)
    - Clear "AI not ready" messaging

  Method:
    - Stub возвращает {"error": "AI_SERVICE_NOT_READY"}
    - Fallback: rule-based detection (value > max*1.5)
    - Fallback: predictions = 7-day average
    - Warning messages for users

  Deliverables:
    ✅ Stubs implemented and tested
    ✅ No crashes when AI unavailable
    ✅ Clear warnings to users
    ✅ Ready for future AI integration

  Deferred to AI Sprint:
    ⏳ Real ML anomaly detection (85%+ accuracy)
    ⏳ AI Service integration
    ⏳ Circuit breaker pattern

Task 8.2: Alert System Implementation (8h)
  Rule-based alerts (NO AI/ML):
    - Threshold-based rules only
    - 3 severity levels (critical, warning, info)
    - 2 channels (Telegram, Email)
    - De-duplication (5 min window)

  Alert Rules (простые IF-условия):
    - Error rate > 5% → critical alert
    - Request backlog > 100 → warning
    - Shift coverage < 80% → warning
    - Value > historical_max * 1.5 → anomaly flag

  Deliverables:
    ✅ 3 alert rules working
    ✅ Alerts sent to Telegram/Email
    ✅ No spam (de-duplicated)
    ✅ Rule-based anomaly flagging (60% accuracy)

  Deferred to AI Sprint:
    ⏳ ML-based anomaly detection
    ⏳ Smart alert prioritization
    ⏳ Predictive alerts
```

#### Week 9: Historical Analysis (12h, было 20h)
```yaml
Task 9.1: Historical Analysis (8h)
  Features:
    - 30-day historical data (not 90)
    - Week-over-week comparison
    - Simple trend analysis
    - CSV export

  Endpoints:
    GET /api/v1/analytics/historical/trends
    GET /api/v1/analytics/historical/compare

  Deliverables:
    ✅ 30-day data accessible
    ✅ WoW comparison works
    ✅ CSV export functional

Task 9.2: Documentation (4h)
  ⚠️ ВАЖНО: Документировать AI limitations

  Documents:
    - README.md (quickstart + AI disclaimer)
    - API_REFERENCE.md (endpoints + stub endpoints)
    - INTEGRATION_GUIDE.md (event publishing)
    - AI_LIMITATIONS.md (что работает, что отложено)

  AI Disclaimer template:
    "⚠️ AI features (anomaly detection, predictions) temporarily use
    statistical fallbacks. ML-based features will be available after
    AI Service is ready. See AI_INTEGRATION_FUTURE_PLAN.md"

  Deliverables:
    ✅ 4 docs completed (включая AI limitations)
    ✅ OpenAPI spec with stub endpoints
    ✅ Clear "Coming Soon" badges
    ✅ Examples tested
```

#### Week 10: Production Deployment (12h)
```yaml
Task 10.1: Load Testing (6h)
  Realistic targets:
    - 1000 req/sec (not 10k)
    - 100 concurrent WebSockets (not 1000)
    - 2-hour endurance test (not 24h)

  Tools:
    - Locust for HTTP load
    - Custom script for WebSocket
    - Monitor with Prometheus

  Deliverables:
    ✅ Handles 1000 req/sec
    ✅ 100 WebSocket stable
    ✅ 2-hour test passes

Task 10.2: Production Hardening (4h)
  Checklist:
    - [ ] Resource limits (CPU: 2 cores, RAM: 4GB)
    - [ ] Graceful shutdown
    - [ ] Health checks accurate
    - [ ] Logging structured
    - [ ] Monitoring dashboard

  Deliverables:
    ✅ All checks passed
    ✅ Monitoring active
    ✅ Alerts configured

Task 10.3: Production Deployment (2h)
  Strategy:
    - Blue-green deployment
    - Deploy to 10% traffic
    - Monitor for 24 hours
    - Gradual rollout to 100%

  Deliverables:
    ✅ Production deployment successful
    ✅ Zero downtime
    ✅ No rollback needed
```

### Success Criteria Increment 3 (UPDATED - БЕЗ AI)
```yaml
Functional:
  ✅ Alert system operational (rule-based, NO AI)
  ✅ Historical analysis (30 days, SQL-based)
  ✅ AI stubs implemented (не ломают систему)
  ✅ Anomaly flagging (rule-based, 60% accuracy)
  ⚠️  Predictions stub (7-day average, 0% ML accuracy)

Performance:
  ✅ Production load test passed
  ✅ 1000 req/sec sustained
  ✅ 100 WebSocket clients stable

Production:
  ✅ Deployed to production
  ✅ 99% uptime (first week)
  ✅ Zero critical incidents
  ✅ Clear messaging about AI limitations

Deferred to Future AI Sprint:
  ⏳ ML anomaly detection (85%+ accuracy)
  ⏳ ML predictions (MAE < 20%)
  ⏳ AI Service integration
  ⏳ Circuit breaker pattern
```

---

## 🚨 RISK MANAGEMENT

### Critical Risks & Mitigation

#### Risk 1: Service Integration Dependencies
**Risk**: Other services not ready to publish events
**Impact**: High - Blocks entire analytics pipeline
**Probability**: Medium (40%)

**Mitigation**:
1. ✅ Start with Shift Service (already has events)
2. ✅ Create stub events for testing
3. ✅ Dedicate 1 developer to help each service integration
4. ✅ Fallback: Manual event injection for demo

**Contingency**: If <3 services integrated by Week 4, pivot to single-service deep analytics

#### Risk 2: Performance Targets Unreachable
**Risk**: Cannot handle 10k events/sec
**Impact**: Medium - Requires re-architecture
**Probability**: High (60%)

**Mitigation**:
1. ✅ Lower target to 1000 events/sec (realistic)
2. ✅ Add Redis clustering in Increment 2
3. ✅ Horizontal scaling with multiple consumers
4. ✅ Load test early (Week 2, not Week 10)

**Contingency**: Accept 500 events/sec for MVP, plan optimization sprint

#### Risk 3: AI Service Not Ready
**Risk**: AI Service не готов к Week 8
**Impact**: Low - Функции отложены на будущее
**Probability**: Very High (95%)

**Mitigation** ✅ IMPLEMENTED:
1. ✅ AI features полностью отложены
2. ✅ Stubs реализованы для всех AI функций
3. ✅ Rule-based fallbacks работают
4. ✅ Отдельный план интеграции AI (см. AI_INTEGRATION_FUTURE_PLAN.md)

**Contingency**: ✅ АКТИВИРОВАН - Ship without AI, add in separate sprint when ready

#### Risk 4: Testing Time Insufficient
**Risk**: 24-hour endurance tests impossible in timeline
**Impact**: Medium - Production stability unknown
**Probability**: High (70%)

**Mitigation**:
1. ✅ Reduce to 2-hour load tests
2. ✅ Use staging for extended testing (parallel)
3. ✅ Gradual production rollout (10% → 100%)
4. ✅ Robust monitoring for early detection

**Contingency**: Extended staging period, delayed production by 1 week

#### Risk 5: Team Capacity
**Risk**: Not enough developers for 10-week sprint
**Impact**: High - Timeline slips
**Probability**: Medium (50%)

**Mitigation**:
1. ✅ Allocate 2 full-time developers (confirmed)
2. ✅ Part-time support from other service teams
3. ✅ Reduce scope if needed (cut AI features)
4. ✅ Clear prioritization (Increment 1 is must-have)

**Contingency**: Extend timeline or reduce scope to Increment 1+2 only

### Risk Matrix
```
High Impact + High Probability:
  - Performance targets (mitigated: lower targets)

High Impact + Medium Probability:
  - Service dependencies (mitigated: start with ready services)
  - Team capacity (mitigated: 2 FTE confirmed)

Medium Impact + High Probability:
  - Testing time (mitigated: shorter tests, gradual rollout)

Low Impact + High Probability:
  - AI accuracy (mitigated: lower targets, mark as beta)
```

---

## 📋 DEPENDENCIES & PREREQUISITES

### External Dependencies

#### 1. Service Teams Must Provide:
```yaml
Shift Service:
  Status: ✅ Ready (already has events)
  Action: None
  Timeline: Week 1

Request Service:
  Status: ⏳ Needs work
  Action: Add event publishing (4h work)
  Owner: Request Service team
  Timeline: Week 2

Auth Service:
  Status: ⏳ Needs work
  Action: Add login/logout events (4h)
  Owner: Auth Service team
  Timeline: Week 5

User Service:
  Status: ⏳ Needs work
  Action: Add user created events (4h)
  Owner: User Service team
  Timeline: Week 6

Notification Service:
  Status: ⏳ Needs work
  Action: Add notification sent events (4h)
  Owner: Notification Service team
  Timeline: Week 6
```

**Total external team time**: 16 hours across 4 teams

#### 2. Infrastructure Prerequisites:
```yaml
Redis Cluster:
  Status: ⏳ To be setup
  Action: Configure Redis Streams + persistence
  Owner: DevOps
  Timeline: Week 1
  Effort: 8 hours

PostgreSQL Analytics DB:
  Status: ✅ Ready (template exists)
  Action: Create analytics database
  Owner: DevOps
  Timeline: Week 1
  Effort: 2 hours

Monitoring Stack:
  Status: ✅ Ready (Prometheus + Grafana)
  Action: Add analytics dashboards
  Owner: Analytics team
  Timeline: Week 7
  Effort: 4 hours
```

#### 3. AI Service Prerequisites:
```yaml
AI Service Endpoint:
  Status: ⏳ NOT READY - Отложено
  Action: NONE (stubs implemented instead)
  Owner: AI Service team
  Timeline: DEFERRED to separate AI Integration Sprint
  Effort: 0 hours (не требуется для Sprint 16-18)

  Resolution: ✅ Stubs implemented, no AI dependency
  See: AI_INTEGRATION_FUTURE_PLAN.md for future integration
```

---

## 📊 REVISED TIMELINE

### 10-Week Gantt Chart
```
Week 1: [████████] Setup + Infrastructure (20h)
Week 2: [████████] Event Integration (20h)
Week 3: [████████] Core KPIs (12h)
Week 4: [████████] Testing + Deploy (8h)
        └─ MILESTONE: Increment 1 Complete

Week 5: [████████] Real-time Processing (16h)
Week 6: [████████] Aggregations + Integration (20h)
Week 7: [████████] Dashboards (12h)
        └─ MILESTONE: Increment 2 Complete

Week 8: [██████░░] Stubs + Alerts (12h, было 16h)
Week 9: [██████░░] Historical + Docs (12h, было 20h)
Week 10:[████████] Production Deploy (12h)
        └─ MILESTONE: Increment 3 Complete, PRODUCTION (БЕЗ AI)

Buffer: +1-2 weeks for unforeseen issues
```

### Critical Path
```
Week 1: Infrastructure → Week 2: Integration → Week 3: KPIs → Week 4: Deploy
(Cannot parallelize - sequential dependencies)

Week 5: Real-time (depends on Week 4 deploy)
Week 6: More integrations (can parallelize with Week 5)
Week 7: Dashboards (depends on Week 6)

Week 8: AI (can start early if AI Service ready)
Week 9: Alerting (depends on Week 8)
Week 10: Production (depends on all previous)
```

---

## 📈 REALISTIC SUCCESS METRICS

### Increment 1 (Week 4)
```yaml
Must Have:
  ✅ 2 services integrated (Shift, Request)
  ✅ 7 core KPIs working
  ✅ API responds <500ms
  ✅ 60% test coverage
  ✅ Staging deployment successful

Performance (Relaxed):
  ✅ 100 events/sec (not 10k)
  ✅ 10 concurrent API clients
  ✅ 99% uptime in staging
```

### Increment 2 (Week 7)
```yaml
Must Have:
  ✅ 5 services integrated
  ✅ 10 total KPIs
  ✅ Real-time updates (5 sec)
  ✅ 2 dashboards working
  ✅ WebSocket support (100 clients)

Performance:
  ✅ 1000 events/sec
  ✅ WebSocket latency <1 sec
  ✅ 65% test coverage
```

### Increment 3 (Week 10) - UPDATED БЕЗ AI
```yaml
Must Have:
  ✅ AI stubs implemented (не ломают систему)
  ✅ Anomaly flagging (rule-based, 60% accuracy)
  ⚠️  Predictions stub (7-day average, NOT ML)
  ✅ Alert system working (threshold-based)
  ✅ 30-day historical data (SQL-based)
  ✅ Production deployment
  ✅ Clear AI limitations documentation

Performance:
  ✅ 1000 req/sec sustained
  ✅ 100 WebSocket clients
  ✅ 99% uptime (first week production)

Quality:
  ✅ 70% test coverage
  ✅ Zero critical bugs
  ✅ Documentation complete (включая AI disclaimer)

Deferred to Future Sprint:
  ⏳ AI Service integration (when ready)
  ⏳ ML anomaly detection (85%+ accuracy)
  ⏳ ML predictions (MAE <20%)
```

---

## 🎯 GO/NO-GO CRITERIA

### Increment 1 Go/No-Go (End of Week 4)
```yaml
GO Criteria (All must be YES):
  ✅ 2+ services publishing events
  ✅ 7 KPIs calculating correctly
  ✅ API response time <500ms (p95)
  ✅ 60%+ test coverage
  ✅ Staging deployment stable (48h+)
  ✅ Zero critical bugs

NO-GO Triggers:
  ❌ <2 services integrated → Delay Increment 2
  ❌ Test coverage <50% → Add 1 week for testing
  ❌ Critical bugs found → Fix before proceeding
```

### Increment 2 Go/No-Go (End of Week 7)
```yaml
GO Criteria:
  ✅ Real-time updates working
  ✅ 5+ services integrated
  ✅ WebSocket stable (100 clients)
  ✅ 2 dashboards functional
  ✅ Performance tests passed

NO-GO Triggers:
  ❌ WebSocket unstable → Pivot to polling
  ❌ Performance <500 events/sec → Re-architecture needed
```

### Increment 3 Go/No-Go (End of Week 10) - UPDATED
```yaml
GO to Production Criteria:
  ✅ AI stubs implemented and tested
  ✅ Rule-based alerts working
  ✅ Historical analysis functional
  ✅ Load tests passed (1000 req/sec)
  ✅ 2-hour endurance test passed
  ✅ Security audit complete
  ✅ Monitoring dashboards ready
  ✅ Runbook documentation done
  ✅ AI limitations clearly documented
  ✅ Rollback plan tested

NO-GO Triggers:
  ❌ Stubs crash or return errors → Fix before production
  ❌ Load test failures → Optimize + retest
  ❌ Security issues → Fix before production
  ❌ Missing monitoring → Delay 1 week
  ❌ Missing AI disclaimer documentation → Add before production
```

---

## 📝 REVISED TASK CHECKLIST

### Increment 1: Foundation (Weeks 1-4)
- [ ] Week 1: Setup (20h)
  - [ ] FastAPI + Docker + DB (8h)
  - [ ] Core models (6h)
  - [ ] Redis Streams (6h)

- [ ] Week 2: Integration (20h)
  - [ ] Shift Service events (8h)
  - [ ] Request Service events (8h)
  - [ ] Validation (4h)

- [ ] Week 3: KPIs (12h)
  - [ ] 7 KPI calculators (8h)
  - [ ] Basic API (4h)

- [ ] Week 4: Testing (8h)
  - [ ] Unit + Integration tests (6h)
  - [ ] Staging deployment (2h)

### Increment 2: Real-time (Weeks 5-7)
- [ ] Week 5: Real-time (16h)
- [ ] Week 6: Aggregations (20h)
- [ ] Week 7: Dashboards (12h)

### Increment 3: Analytics & Production (Weeks 8-10) - БЕЗ AI
- [ ] Week 8: AI Stubs + Alerts (12h, было 16h)
  - [ ] AIServiceClientStub (2h)
  - [ ] AnomalyDetectorStub (1h)
  - [ ] PredictorStub (1h)
  - [ ] Alert System (8h)
- [ ] Week 9: Historical + Docs (12h, было 20h)
  - [ ] Historical analysis (8h)
  - [ ] Documentation with AI disclaimer (4h)
- [ ] Week 10: Production (12h)

**Total**: 144 hours across 10 weeks (сэкономлено 12 часов на AI)
**Deferred**: 20 hours AI work → separate AI Integration Sprint

---

## 🔄 DEGRADATION PLAN

### If Timeline Slips

**Scenario 1: Week 4 - Only 1 service integrated**
```yaml
Action:
  - Continue with 1 service (Shift)
  - Deep analytics for shifts only
  - Skip Increment 2, go directly to production
  - Add more services post-launch

Timeline Impact: -3 weeks (save Increment 2)
```

**Scenario 2: Week 7 - WebSocket unstable**
```yaml
Action:
  - Pivot to HTTP polling (simpler)
  - Update every 30 seconds instead of 5
  - Skip real-time, focus on historical

Timeline Impact: -1 week (skip WebSocket work)
```

**Scenario 3: Week 10 - AI not ready**
```yaml
Status: ✅ RESOLVED - AI features deferred proactively

Action TAKEN:
  - ✅ AI features deferred to separate sprint
  - ✅ Stubs implemented instead
  - ✅ "Coming Soon" messaging added
  - ✅ Separate AI_INTEGRATION_FUTURE_PLAN.md created

Timeline Impact: ✅ +12 hours saved in Sprint 16-18
Future work: 20 hours in separate AI Integration Sprint
```

---

## ✅ APPROVAL CHECKLIST

### Before Starting Sprint

**Team Agreement**:
- [ ] 2 full-time developers allocated (10 weeks)
- [ ] Part-time support from service teams confirmed
- [ ] DevOps support for infrastructure (Week 1)

**Dependencies Confirmed**:
- [ ] Shift Service ready to publish events (Week 1)
- [ ] Request Service team committed to add events (Week 2)
- [ ] Auth/User/Notification teams aware (Week 5-6)

**Infrastructure Ready**:
- [ ] Redis Cluster setup approved
- [ ] PostgreSQL analytics DB provisioned
- [ ] Monitoring stack configured

**Risks Accepted**:
- [ ] 10-week timeline (not 3-4 weeks)
- [ ] Reduced scope (7 KPIs not 20+)
- [ ] Relaxed performance (1k events/sec not 10k)
- [ ] Lower AI accuracy (85% not 95%)

**Stakeholder Sign-off**:
- [ ] Product Owner approved revised scope
- [ ] Tech Lead approved architecture
- [ ] DevOps approved infrastructure plan
- [ ] Team committed to timeline

---

## 🚀 NEXT STEPS

**Immediate (This Week)**:
1. ✅ Get stakeholder approval on revised plan
2. ✅ Confirm 2 FTE developers allocation
3. ✅ Setup Redis Cluster (DevOps)
4. ✅ Create analytics database

**Week 1 (Day 1)**:
```bash
# Developer 1: Project setup
cd microservices
mkdir analytics_service
# Follow Task 1.1 from revised plan

# Developer 2: Redis Streams setup
# Setup consumer groups
# Test event publishing from Shift Service

# DevOps: Infrastructure
# Provision Redis Cluster
# Create PostgreSQL analytics DB
```

**Week 2 (Day 8)**:
- Start service integrations
- Begin KPI development
- Setup monitoring

---

**Version**: 2.0 REVISED
**Status**: 📋 READY FOR APPROVAL
**Last Updated**: 6 октября 2025
**Next Review**: After Increment 1 (Week 4)
