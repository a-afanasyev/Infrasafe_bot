# 🤖 AI Service - Basic Assignment Microservice (Stage 1 MVP)

**UK Management Bot - AI Service**

---

## 🤖 Service Overview

AI Service provides basic rule-based assignment functionality for the UK Management Bot microservices ecosystem. This is a **Stage 1 MVP implementation** with weighted scoring algorithms for request-to-executor assignment.

### 🎯 Core Responsibilities (Stage 1)

- **Basic Assignment**: Rule-based request-to-executor assignment with weighted scoring
- **Executor Recommendations**: Ranked list of suitable executors with score explanations
- **Health Monitoring**: Service health checks and basic status reporting
- **API Integration**: RESTful endpoints for assignment operations
- **Docker Deployment**: Containerized deployment with database connectivity

### ✅ **Текущая работающая функциональность → [CURRENT_FUNCTIONALITY.md](./CURRENT_FUNCTIONALITY.md)**

### ⚠️ **NOT IMPLEMENTED** (Future Stages)
- ❌ Machine Learning predictions
- ❌ Geographic optimization
- ❌ Advanced algorithms (Genetic, Simulated Annealing)
- ❌ Database persistence (tables exist but unused)
- ❌ Service-to-service integration
- ❌ Monitoring/metrics collection

---

## 🏗️ Architecture

### **Service Status: ✅ OPERATIONAL (Stage 1 MVP)**
- **Port**: 8006
- **Health**: `/health` endpoint
- **Database**: `ai_db` (PostgreSQL) - ✅ Connected, ❌ Not Used for Persistence
- **Cache**: Redis DB 6 - ✅ Connected, ❌ Not Used
- **Actual Implementation**: Stage 1 Basic Assignment Only
- **Running Application**: `main_simple.py` (basic service shell)

### **Database Schema (Created but Unused)**

```sql
-- Tables are created but no ORM models exist to use them
-- All data operations are in-memory only
ai_assignments:     -- ✅ Table exists, ❌ No SQLAlchemy model
ml_models:          -- ✅ Table exists, ❌ No SQLAlchemy model
model_predictions:  -- ✅ Table exists, ❌ No SQLAlchemy model
model_evaluations:  -- ✅ Table exists, ❌ No SQLAlchemy model
district_mapping:   -- ✅ Table exists, ❌ No SQLAlchemy model
```

### **Service Layer (Stage 1 Only)**

- **SmartDispatcher**: Basic rule-based assignment with weighted scoring
- **AssignmentService**: Core assignment logic and executor selection
- **HealthChecker**: Service health monitoring
- **MockDataProvider**: Hardcoded executor data for development

---

## 🚀 API Endpoints (Stage 1)

### **Basic Assignment (`/api/v1/assignments`)**

```yaml
POST   /basic-assign              # Basic rule-based assignment
GET    /recommendations/{request_number}  # Get executor recommendations
GET    /stats                     # Basic assignment statistics
```

#### **Basic Assignment Example:**
```bash
curl -X POST http://localhost:8006/api/v1/assignments/basic-assign \
  -H "Content-Type: application/json" \
  -d '{
    "request_number": "250928-001",
    "category": "plumber",
    "urgency": 4,
    "description": "Urgent plumbing repair",
    "address": "Чиланзар, дом 15"
  }'

# Response:
{
  "request_number": "250928-001",
  "success": true,
  "executor_id": 1,
  "algorithm": "basic_rules",
  "score": 0.875,
  "factors": {
    "specialization_match": true,
    "efficiency_score": 85.0,
    "current_load": 2,
    "capacity": 5,
    "district": "Чиланзар",
    "executor_name": "Иван Иванов"
  },
  "processing_time_ms": 0,
  "fallback_used": false
}
```

### **Health & Monitoring**

```yaml
GET    /health                    # Simple health check
GET    /api/v1/health            # Detailed health with stage info
GET    /metrics                  # Placeholder metrics endpoint
```

#### **Health Check:**
```bash
curl http://localhost:8006/health

{
  "status": "healthy",
  "service": "ai-service",
  "version": "1.0.0",
  "stage": "1_basic_assignment",
  "ml_enabled": false,
  "geo_enabled": false,
  "database": "connected",
  "events": "connected"
}
```

---

## 🔧 Key Features (Stage 1 Implementation)

### **Assignment Algorithm**

```python
# Weighted scoring system for executor selection
ASSIGNMENT_WEIGHTS = {
    "specialization_match": 0.40,    # 40% - Does executor match category?
    "efficiency_score": 0.30,        # 30% - Executor efficiency rating
    "workload_balance": 0.20,        # 20% - Current workload ratio
    "availability": 0.10             # 10% - Is executor available?
}

# Score calculation
total_score = (
    specialization_score * 0.4 +
    efficiency_score * 0.3 +
    workload_score * 0.2 +
    availability_score * 0.1
)
```

### **Mock Executor Data**

```python
# Hardcoded executor data for Stage 1 testing
MOCK_EXECUTORS = [
    {
        "executor_id": 1, "name": "Иван Иванов",
        "specializations": ["plumber"], "district": "Чиланзар",
        "efficiency_score": 85.0, "workload_capacity": 5
    },
    {
        "executor_id": 2, "name": "Петр Петров",
        "specializations": ["electrician"], "district": "Юнусабад",
        "efficiency_score": 78.0, "workload_capacity": 6
    },
    {
        "executor_id": 3, "name": "Сергей Сергеев",
        "specializations": ["general", "carpenter"], "district": "Мирзо-Улугбек",
        "efficiency_score": 92.0, "workload_capacity": 4
    }
]
```

---

## 🐳 Deployment

### **Current Configuration**

```yaml
# From docker-compose.yml
ai-service:
  build:
    context: ./ai_service
    dockerfile: Dockerfile
  ports:
    - "8006:8006"
  environment:
    - DATABASE_URL=postgresql+asyncpg://ai_user:ai_pass@ai-db:5432/ai_db
    - REDIS_URL=redis://shared-redis:6379/6
    - DEBUG=true
    - ML_ENABLED=false
    - GEO_ENABLED=false
  depends_on:
    - ai-db (healthy)
    - shared-redis (healthy)
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8006/health"]
    interval: 30s
    timeout: 10s
    retries: 3
```

### **Environment Variables**

```bash
# Service Configuration
SERVICE_NAME=ai-service
VERSION=1.0.0
DEBUG=true
HOST=0.0.0.0
PORT=8006

# Database (Connected but Not Used for Persistence)
DATABASE_URL=postgresql+asyncpg://ai_user:ai_pass@ai-db:5432/ai_db

# Redis (Connected but Not Used)
REDIS_URL=redis://shared-redis:6379/6

# Feature Flags (All Disabled in Stage 1)
ML_ENABLED=false
GEO_ENABLED=false
```

---

## 🧪 Testing

### **Test Coverage (Stage 1)**
- Unit tests for basic assignment logic
- Integration tests for API endpoints
- Health check tests
- Mock data validation tests

### **API Testing**
```bash
# Basic assignment test
curl -X POST http://localhost:8006/api/v1/assignments/basic-assign \
  -H "Content-Type: application/json" \
  -d '{
    "request_number": "250928-001",
    "category": "plumber",
    "urgency": 4,
    "description": "Test assignment"
  }'

# Health check
curl http://localhost:8006/health
```

---

## 📚 Development

### **Local Development**
```bash
# Start dependencies
docker-compose up ai-db shared-redis -d

# Install dependencies
pip install -r requirements.txt

# Run service (uses main_simple.py)
uvicorn main_simple:app --reload --host 0.0.0.0 --port 8006

# Access API docs
open http://localhost:8006/docs
```

### **Code Quality**
```bash
# Format code
black . && ruff . --fix

# Type checking
mypy .

# Run tests
pytest tests/ -v --cov --cov-report=html
```

---

## 🎯 Development Roadmap

### **📋 Детальный план развития → [TODO.md](./TODO.md)**

### **Stage 2: Data Pipeline + Basic ML (6-8 недель разработки)**
- **🔧 SQLAlchemy ORM models** для persistence layer
- **📊 Real data migration** из monolith системы
- **🤖 ML pipeline implementation** с real training data
- **📈 Model versioning system** с database persistence

### **Stage 3: Geographic + Optimization (4-6 недель разработки)**
- **🌍 Real geographic calculations** с mapping APIs
- **🧬 Advanced optimization algorithms** (Genetic, Simulated Annealing)
- **🗺️ Route optimization** для multiple assignments
- **⚡ Performance optimization** для batch processing

### **Stage 4: Production Integration (4-5 недель разработки)**
- **🔗 Service integration fixes** (исправление 404 endpoints)
- **🛡️ Real circuit breaker patterns** вместо permanent fallback
- **📊 Production monitoring** с real metrics
- **🚀 End-to-end integration** с microservices ecosystem

### **🚨 Критические задачи для завершения Sprint 10-13:**
1. **Создать SQLAlchemy models** для всех database tables
2. **Исправить service integration endpoints** (404 → success)
3. **Подключить ML/geo/production routers** к main application
4. **Заменить synthetic data** на real data pipeline
5. **Реализовать real monitoring** вместо placeholder stubs

**📊 Прогресс**: Stage 1 ✅ Complete | Stages 2-4 ❌ Требуют полной реализации
**⏱️ Время до production**: 6-8 недель active development

---

## ⚠️ Known Limitations (Stage 1)

### **Current Limitations**
- **No Persistence**: All data is in-memory, lost on restart
- **No ML**: No machine learning capabilities implemented
- **No Service Integration**: Cannot communicate with other microservices
- **Mock Data Only**: Uses hardcoded executor data
- **No Geographic Features**: No distance calculations or optimization
- **No Monitoring**: Placeholder metrics endpoints only

### **Placeholder Endpoints**
- `/metrics` - Returns placeholder message
- All ML endpoints in `app/api/v1/ml_endpoints.py` - Not mounted in main application
- All optimization endpoints - Not mounted in main application
- All production endpoints - Not mounted in main application

---

## 📄 API Documentation

### **Interactive Documentation**
- **Swagger UI**: http://localhost:8006/docs
- **ReDoc**: http://localhost:8006/redoc
- **OpenAPI JSON**: http://localhost:8006/openapi.json

### **Available Endpoints (Stage 1 Only)**
```bash
curl http://localhost:8006/api/v1/assignments/stats

{
  "available_endpoints": [
    "/api/v1/assignments/basic-assign",
    "/api/v1/assignments/recommendations/{request_number}",
    "/api/v1/assignments/stats",
    "/health",
    "/api/v1/health",
    "/metrics"
  ],
  "stage": "1_basic_assignment",
  "note": "Only basic assignment endpoints are implemented"
}
```

---

**📝 Status**: ✅ **OPERATIONAL (Stage 1 MVP)**
**🔄 Version**: 1.0.0-stage1
**📅 Last Updated**: September 29, 2025
**🎯 Port**: 8006
**💾 Database**: ai_db (PostgreSQL) - ✅ Connected, ❌ No Persistence Layer
**🔗 Dependencies**: shared-redis (connected but unused)
**📱 Integration**: None - Stage 1 standalone operation only
**🤖 AI Features**: Basic Rules Only (weighted scoring)
**🛡️ Production Features**: Basic health checks only

### **Honest Implementation Status:**
- ✅ **Stage 1**: Service Shell + Basic Assignment (IMPLEMENTED)
- ❌ **Stage 2**: Data Pipeline + ML (NOT IMPLEMENTED)
- ❌ **Stage 3**: Geographic + Optimization (NOT IMPLEMENTED)
- ❌ **Stage 4**: Production Integration (NOT IMPLEMENTED)

### **Next Development Steps:**
1. 🔧 **Реализовать SQLAlchemy ORM models** для database persistence
2. 🔄 **Добавить real data migration** из monolith системы
3. 🚀 **Разработать ML prediction capabilities** на real data
4. 🔗 **Исправить service-to-service integration** endpoints
5. 📊 **Добавить real monitoring** и metrics collection

### **📋 Полный план работ:**
**См. [TODO.md](./TODO.md)** для детального roadmap с временными рамками и техническими требованиями.

**🎯 Цель**: Завершить Stages 2-4 для полной реализации AI service как заявлено в Sprint 10-13 планах.