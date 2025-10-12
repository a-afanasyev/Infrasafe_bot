# Sprint 16-18: Analytics Service - Quick Start Guide

**Дата**: 6 октября 2025
**Статус**: 📋 ГОТОВ К СТАРТУ
**Длительность**: 3-4 недели

---

## 🎯 Что Создаем

**Analytics Service** - централизованная платформа аналитики для всех микросервисов:

- 📊 **20+ KPI метрик** в реальном времени
- 🔄 **Event-driven архитектура** с Redis Streams
- 📈 **Historical analytics** за 90 дней
- 🤖 **AI-powered insights** и predictions
- 📱 **4 готовых dashboard** для бизнес-аналитики

---

## 📋 Быстрый План (25 Задач)

### Неделя 1: Foundation (3 задачи)
```
✅ Task 1.1: Project Setup (4h)
   - FastAPI + Docker + Database

✅ Task 1.2: Data Models (6h)
   - 6 core models (MetricSnapshot, AggregatedMetric, EventLog...)

✅ Task 1.3: Integration Hub (8h)
   - Event consumer + router + validator
```

### Неделя 2: Pipeline (3 задачи)
```
✅ Task 2.1: KPI Calculator (12h)
   - 20+ KPIs (users, requests, shifts, system)

✅ Task 2.2: Data Aggregator (8h)
   - Pre-aggregation (1min, 1hour, 1day)

✅ Task 2.3: Real-time Processing (10h)
   - Redis Streams + WebSocket
```

### Неделя 3: API & Integration (3 задачи)
```
✅ Task 3.1: Analytics REST API (10h)
   - 9 endpoints (metrics, KPI, dashboards, alerts)

✅ Task 3.2: Service Integration (8h)
   - 7 сервисов (Auth, User, Request, Shift, Notification, Media, AI)

✅ Task 3.3: Dashboard Framework (6h)
   - 4 dashboards + 6 widget types
```

### Неделя 4: AI & Quality (6 задач)
```
✅ Task 4.1: AI Insights (8h)
   - Anomaly detection + predictions

✅ Task 4.2: Alerting (6h)
   - Smart alerts + Telegram/Email

✅ Task 4.3: Historical Analysis (6h)
   - Trends + cohorts + funnels

✅ Task 5.1: Testing (12h)
   - 70%+ coverage

✅ Task 5.2: Documentation (8h)
   - 6 docs + API reference

✅ Task 5.3: Production Readiness (8h)
   - Deploy to staging + monitoring
```

**Итого**: 120 часов = 3 недели работы

---

## 🚀 Как Начать

### Шаг 1: Создать структуру проекта (30 мин)

```bash
cd /path/to/UK/microservices
mkdir -p analytics_service/{api/v1,models,schemas,services,tasks,tests/{unit,integration},migrations/versions}

# Создать базовые файлы
touch analytics_service/{main.py,config.py,requirements.txt,Dockerfile,.env.example}
touch analytics_service/api/__init__.py
touch analytics_service/api/v1/{__init__.py,analytics.py,dashboards.py,alerts.py}
```

### Шаг 2: Setup Database (20 мин)

```yaml
# docker-compose.analytics.yml
version: '3.8'

services:
  analytics-db:
    image: postgres:15-alpine
    container_name: analytics-db
    environment:
      POSTGRES_DB: analytics
      POSTGRES_USER: analytics_user
      POSTGRES_PASSWORD: analytics_pass
    ports:
      - "5440:5432"
    volumes:
      - analytics_db_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U analytics_user"]
      interval: 10s
      timeout: 5s
      retries: 5

  analytics-service:
    build: ./analytics_service
    container_name: analytics-service
    depends_on:
      analytics-db:
        condition: service_healthy
      shared-redis:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql+asyncpg://analytics_user:analytics_pass@analytics-db:5432/analytics
      REDIS_URL: redis://shared-redis:6379
    ports:
      - "8008:8008"
    volumes:
      - ./analytics_service:/app

volumes:
  analytics_db_data:
```

### Шаг 3: Install Dependencies (10 мин)

```txt
# requirements.txt
fastapi==0.104.1
uvicorn[standard]==0.24.0
sqlalchemy[asyncio]==2.0.23
asyncpg==0.29.0
redis[hiredis]==5.0.1
pydantic==2.5.0
pydantic-settings==2.1.0
alembic==1.13.0
python-jose[cryptography]==3.3.0
httpx==0.25.2
prometheus-client==0.19.0
pandas==2.1.4  # for data analysis
numpy==1.26.2  # for calculations
python-multipart==0.0.6

# Development
pytest==7.4.3
pytest-asyncio==0.21.1
pytest-cov==4.1.0
black==23.12.0
ruff==0.1.8
```

### Шаг 4: Create main.py (15 мин)

```python
# analytics_service/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from api.v1 import analytics, dashboards, alerts
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Analytics Service",
    description="Centralized analytics and metrics platform",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["analytics"])
app.include_router(dashboards.router, prefix="/api/v1/dashboards", tags=["dashboards"])
app.include_router(alerts.router, prefix="/api/v1/alerts", tags=["alerts"])

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "analytics-service",
        "version": "1.0.0"
    }

@app.on_event("startup")
async def startup_event():
    logger.info("Analytics Service starting...")
    # Initialize Redis connection
    # Start event consumer

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Analytics Service shutting down...")
    # Close connections

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8008)
```

### Шаг 5: Запустить сервис (5 мин)

```bash
# Build and run
cd microservices
docker-compose -f docker-compose.analytics.yml up -d --build

# Check health
curl http://localhost:8008/health

# Expected response:
# {"status":"healthy","service":"analytics-service","version":"1.0.0"}
```

---

## 📊 Ключевые Метрики

### KPIs для Отслеживания

**User Metrics** (5 KPIs):
- Active users (DAU/WAU/MAU)
- New users (daily/weekly)
- User retention rate
- Session duration (avg)
- Login frequency

**Request Metrics** (7 KPIs):
- Total requests (created/completed)
- Completion rate
- Average resolution time
- Request backlog
- SLA compliance rate
- Requests by priority
- Requests by category

**Shift Metrics** (6 KPIs):
- Total shifts (scheduled/completed)
- Shift coverage rate
- Average shift duration
- Executor utilization
- Shift transfer rate
- Efficiency score

**System Metrics** (5 KPIs):
- API response time (p50/p95/p99)
- Error rate
- Throughput (req/sec)
- Service availability
- Database query performance

---

## 🔧 Архитектура

```
Event Sources (7 Services)
    ↓
Redis Streams (Event Bus)
    ↓
Integration Hub (Event Consumer)
    ↓
Event Processor → KPI Calculator
    ↓
Data Aggregator → PostgreSQL
    ↓
Analytics API (REST)
    ↓
Dashboards (Grafana/Custom)
```

**Event Flow**:
1. Services publish events to Redis Streams
2. Integration Hub consumes events
3. Events processed and validated
4. KPIs calculated and cached
5. Data aggregated at multiple time windows
6. API serves metrics to consumers

---

## ✅ Success Criteria

**Week 1 Checkpoint**:
- [ ] Service running in Docker
- [ ] Database connected
- [ ] Integration Hub consuming events from 1 service
- [ ] Basic health check working

**Week 2 Checkpoint**:
- [ ] 20+ KPIs calculating correctly
- [ ] Pre-aggregation working (1min, 1hour, 1day)
- [ ] Real-time metrics updating every 5 sec
- [ ] API endpoint returning metrics

**Week 3 Checkpoint**:
- [ ] All 7 services integrated
- [ ] 9 API endpoints implemented
- [ ] 4 dashboards created
- [ ] Authentication working

**Week 4 Final**:
- [ ] AI insights integrated
- [ ] Alerting system active
- [ ] 70%+ test coverage
- [ ] Documentation complete
- [ ] Deployed to staging

---

## 🎯 Ready to Start?

**Next Action**:
```bash
# 1. Review the full plan
cat SPRINT_16_18_ANALYTICS_PLAN.md

# 2. Create project structure
./scripts/create_analytics_structure.sh

# 3. Start Week 1 Task 1.1: Project Setup
git checkout -b feature/analytics-service-foundation
cd microservices/analytics_service
# ... follow Task 1.1 instructions
```

**Questions?**
- Review [SPRINT_16_18_ANALYTICS_PLAN.md](SPRINT_16_18_ANALYTICS_PLAN.md) for details
- Check existing analytics in shift_service for examples
- Refer to IMPLEMENTATION_PLAN.md for context

**Let's Build! 🚀**
