# 🤖 Sprint 10-13: AI & Assignment Services - Детальный план
**UK Management Bot - AI Microservice Migration**

---

## 📊 ИСПОЛНИТЕЛЬНОЕ РЕЗЮМЕ

### 🎯 **ЦЕЛЬ SPRINT 10-13**
Создать **AI & Assignment Service** микросервис, объединяющий все интеллектуальные компоненты системы:
- **Smart Assignment** с 4 алгоритмами оптимизации
- **Geographic Optimization** для маршрутизации
- **ML-powered Workload Prediction** для планирования
- **Recommendation Engine** для подбора исполнителей

### 📈 **КЛЮЧЕВЫЕ МЕТРИКИ**
- **Исходный код**: ~200KB (5 основных сервисов монолита)
- **Компоненты**: 8 ключевых классов для миграции
- **API Endpoints**: 18 REST API endpoints
- **Алгоритмы**: 4 оптимизационных алгоритма
- **Database**: Dedicated ai_assignments_db (PostgreSQL)
- **Время выполнения**: 4 недели (20 рабочих дней)

---

## 🔍 АНАЛИЗ СУЩЕСТВУЮЩИХ КОМПОНЕНТОВ

### **РЕАЛЬНЫЕ ИСТОЧНИКИ ДАННЫХ В МОНОЛИТЕ:**

#### **✅ Доступные данные для ML:**
```sql
-- Performance metrics (таблица shifts)
- average_completion_time ✅ KEY FEATURE
- efficiency_score ✅ KEY FEATURE
- quality_rating ✅ KEY FEATURE
- total_requests_handled ✅ KEY FEATURE

-- Assignment history (таблица request_assignments)
- request_number, executor_id, status, created_at ✅ ASSIGNMENT DATA

-- Quality ratings (таблица ratings)
- rating (1-5), request_number, user_id ✅ OUTCOME LABELS

-- Execution results (таблица shift_assignments)
- execution_quality_rating ✅ SUCCESS METRIC
- actual_duration ✅ PERFORMANCE METRIC
- had_issues ✅ BINARY OUTCOME
```

#### **❌ Отсутствующие данные:**
```sql
-- Geographic coordinates
- latitude/longitude НЕТ (только text addresses)
- distance_matrix НЕТ (будет примитивная district-based классификация)

-- Labeled ML outcomes
- success/failure labels НЕТ (используем execution_quality_rating как proxy)
- optimization_history НЕТ (начинаем с нуля)
```

### **Ключевые сервисы для миграции:**

#### **1. SmartDispatcher** (`smart_dispatcher.py`)
```python
Функциональность:
- ✅ Автоматическое назначение заявок на исполнителей
- ✅ Multi-criteria scoring (5 критериев)
- ⚠️ Geographic proximity (ОГРАНИЧЕН - district-based вместо coordinates)
- ✅ Real-time optimization
- ✅ Batch processing для множественных назначений

Алгоритмы (ADAPTED):
- Specialization matching (35% weight) ✅ FULL DATA
- District proximity (25% weight) ⚠️ SIMPLIFIED
- Workload balancing (20% weight) ✅ FULL DATA
- Executor rating (15% weight) ✅ FULL DATA
- Urgency priority (5% weight) ✅ FULL DATA
```

#### **2. AssignmentOptimizer** (`assignment_optimizer.py`)
```python
Функциональность:
- ✅ 4 optimization algorithms (Genetic, Simulated Annealing, Greedy, Hybrid)
- ✅ Constraint violation detection
- ✅ Performance metrics calculation
- ✅ Multi-objective optimization

Алгоритмы:
- Genetic Algorithm - глобальная оптимизация
- Simulated Annealing - избежание локальных минимумов
- Greedy Algorithm - быстрое назначение
- Hybrid Algorithm - баланс скорости и качества
```

#### **3. GeoOptimizer** (`geo_optimizer.py`)
```python
Функциональность:
- ✅ Daily route optimization
- ✅ Distance matrix calculation
- ✅ Territory management
- ✅ Executor-location mapping

Алгоритмы:
- TSP (Traveling Salesman Problem) solver
- Distance-based clustering
- Location caching для performance
```

#### **4. AssignmentService** (`assignment_service.py`)
```python
Функциональность:
- ✅ Unified API для всех assignment операций
- ✅ Manual assignment overrides
- ✅ Performance statistics
- ✅ Assignment history tracking
```

---

## 🏗️ АРХИТЕКТУРА AI SERVICE

### **Микросервис Structure:**
```
ai_service/
├── app/
│   ├── models/           # Database models
│   │   ├── assignment.py
│   │   ├── ml_model.py
│   │   ├── optimization_result.py
│   │   ├── geo_cache.py
│   │   └── workload_prediction.py
│   ├── services/         # Business logic
│   │   ├── smart_dispatcher.py      # Core assignment logic
│   │   ├── assignment_optimizer.py  # ML optimization algorithms
│   │   ├── geo_optimizer.py         # Geographic optimization
│   │   ├── recommendation_engine.py # Executor recommendations
│   │   └── workload_predictor.py    # Load prediction
│   ├── api/
│   │   └── v1/
│   │       ├── assignments.py       # Assignment endpoints
│   │       ├── optimization.py      # Optimization endpoints
│   │       ├── geo.py              # Geographic endpoints
│   │       └── ml.py               # ML model endpoints
│   ├── core/
│   │   ├── algorithms/              # Core algorithms
│   │   │   ├── genetic.py
│   │   │   ├── simulated_annealing.py
│   │   │   ├── greedy.py
│   │   │   └── hybrid.py
│   │   └── ml/                     # ML utilities
│   │       ├── feature_engineering.py
│   │       ├── model_training.py
│   │       └── prediction.py
│   └── integrations/
│       ├── user_service.py         # User data integration
│       ├── request_service.py      # Request data integration
│       └── shift_service.py        # Shift data integration
├── migrations/           # Database migrations
├── tests/               # Comprehensive test suite
└── docs/               # API documentation
```

### **Database Schema: `ai_assignments_db`**
```sql
-- Core assignments table
CREATE TABLE assignments (
    id SERIAL PRIMARY KEY,
    request_number VARCHAR(20) NOT NULL,
    executor_id INTEGER NOT NULL,
    algorithm_used VARCHAR(50) NOT NULL,
    assignment_score FLOAT NOT NULL,
    factors JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- ML models metadata
CREATE TABLE ml_models (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    version VARCHAR(20) NOT NULL,
    model_type VARCHAR(50) NOT NULL,
    parameters JSONB NOT NULL,
    performance_metrics JSONB,
    trained_at TIMESTAMP NOT NULL,
    is_active BOOLEAN DEFAULT false
);

-- Optimization results tracking
CREATE TABLE optimization_results (
    id SERIAL PRIMARY KEY,
    request_number VARCHAR(20) NOT NULL,
    algorithm VARCHAR(50) NOT NULL,
    initial_score FLOAT NOT NULL,
    optimized_score FLOAT NOT NULL,
    improvement FLOAT NOT NULL,
    processing_time_ms INTEGER NOT NULL,
    changes_made JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Geographic data cache
CREATE TABLE geo_cache (
    id SERIAL PRIMARY KEY,
    address TEXT NOT NULL UNIQUE,
    latitude DECIMAL(10, 8) NOT NULL,
    longitude DECIMAL(11, 8) NOT NULL,
    region VARCHAR(100),
    district VARCHAR(100),
    cached_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP
);

-- Workload predictions
CREATE TABLE workload_predictions (
    id SERIAL PRIMARY KEY,
    executor_id INTEGER NOT NULL,
    prediction_date DATE NOT NULL,
    predicted_load INTEGER NOT NULL,
    confidence_score FLOAT NOT NULL,
    features JSONB NOT NULL,
    actual_load INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(executor_id, prediction_date)
);
```

---

## 🚀 IMPLEMENTATION ROADMAP

### **Week 1: Foundation & Data Migration (REALISTIC)**

#### **Days 1-2: Service Bootstrap + Historical Data**
- ✅ **FastAPI service setup** с async/await
- ✅ **Database schema creation** (AI-focused tables)
- ✅ **Historical data migration script** (request_assignments → ai_assignments)
- ✅ **Performance metrics extraction** (shifts → executor_performance)
- ✅ **Data quality validation** и cleaning

#### **Days 3-5: Core SmartDispatcher Migration (ADAPTED)**
- ✅ **SmartDispatcher class** с district-based geography
- ✅ **AssignmentScore dataclass** using REAL performance data
- ✅ **Feature engineering pipeline** (executor_efficiency, avg_completion_time)
- ✅ **Simplified scoring** без coordinates (district matching)
- ✅ **Real-time assignment** API с fallback logic

### **Week 2: Algorithms + Basic ML (REALISTIC)**

#### **Days 6-8: AssignmentOptimizer Implementation (DATA-DRIVEN)**
- ✅ **Greedy Algorithm** using real executor performance data
- ✅ **Simple optimization** based on efficiency_score + quality_rating
- ✅ **Constraint validation** (workload limits, specialization matching)
- ⚠️ **Basic genetic algorithm** (simplified, no complex geo optimization)
- ✅ **Performance comparison** против существующих назначений

#### **Days 9-10: Basic ML Pipeline (FEASIBLE)**
- ✅ **Feature extraction** from existing performance data
- ✅ **Simple prediction model** (executor success probability)
- ✅ **Model using sklearn** (RandomForest/LogisticRegression)
- ✅ **Success prediction** based on execution_quality_rating history
- ✅ **Basic model versioning** и tracking

### **Week 3: Simplified Geography + Workload Prediction (ADAPTED)**

#### **Days 11-13: District-Based GeoOptimizer (NO COORDINATES)**
- ✅ **District classification** system (Chilanzar, Yunusabad, etc.)
- ✅ **Simple distance proxy** (same district = 1, adjacent = 2, far = 3)
- ✅ **Territory management** по районам instead of coordinates
- ✅ **Route grouping** by district clusters
- ⚠️ **Basic clustering** без TSP (group by proximity score)

#### **Days 14-15: Basic Workload Prediction (REALISTIC)**
- ✅ **Workload prediction** based on historical patterns
- ✅ **Simple time series** (daily/weekly patterns)
- ✅ **Feature engineering** (day_of_week, hour, season)
- ✅ **Prediction using** average_completion_time + efficiency_score
- ✅ **Basic accuracy tracking** и validation

### **Week 4: Integration & Production Readiness**

#### **Days 16-17: Service Integration**
- ✅ **User Service integration** для executor данных
- ✅ **Request Service integration** для assignment данных
- ✅ **Event-driven architecture** integration
- ✅ **Cross-service API** coordination

#### **Days 18-20: Testing & Documentation**
- ✅ **Integration tests** для всех компонентов
- ✅ **Performance testing** с load scenarios
- ✅ **API documentation** (OpenAPI/Swagger)
- ✅ **Deployment guides** и runbooks

---

## 📋 DETAILED API SPECIFICATION

### **1. Assignment Management**
```yaml
POST /api/v1/assignments/auto-assign
  Description: Автоматическое назначение исполнителя на заявку
  Body: {
    "request_number": "250928-001",
    "algorithm": "hybrid",
    "constraints": ["max_distance_km", "specialization_match"]
  }
  Response: {
    "assignment_id": 123,
    "executor_id": 456,
    "assignment_score": 87.5,
    "factors": {...},
    "processing_time_ms": 150
  }

POST /api/v1/assignments/manual-assign
  Description: Ручное назначение с override логикой
  Body: {
    "request_number": "250928-001",
    "executor_id": 456,
    "override_reason": "Emergency assignment"
  }

GET /api/v1/assignments/recommendations/{request_number}
  Description: Получить топ-5 рекомендованных исполнителей
  Response: {
    "recommendations": [
      {
        "executor_id": 456,
        "score": 87.5,
        "factors": {...},
        "availability": "available"
      }
    ]
  }
```

### **2. Optimization Endpoints**
```yaml
POST /api/v1/optimization/optimize-assignments
  Description: Оптимизация существующих назначений
  Body: {
    "algorithm": "genetic",
    "date_range": {
      "start": "2025-09-28",
      "end": "2025-09-30"
    },
    "parameters": {
      "population_size": 100,
      "generations": 50
    }
  }

GET /api/v1/optimization/results/{optimization_id}
  Description: Получить результаты оптимизации

POST /api/v1/optimization/routes
  Description: Оптимизация маршрутов исполнителей
  Body: {
    "executor_ids": [456, 789],
    "date": "2025-09-28",
    "algorithm": "tsp"
  }
```

### **3. Geographic Services**
```yaml
GET /api/v1/geo/distance-matrix
  Description: Расчет матрицы расстояний
  Query: ?origins=lat1,lng1&destinations=lat2,lng2

POST /api/v1/geo/geocode
  Description: Геокодирование адресов
  Body: {
    "addresses": ["ул. Ленина 1", "пр. Мира 5"]
  }

GET /api/v1/geo/territories/{executor_id}
  Description: Получить территорию исполнителя
```

### **4. ML & Prediction**
```yaml
POST /api/v1/ml/retrain-models
  Description: Переобучение ML моделей
  Body: {
    "model_type": "workload_prediction",
    "training_period": "last_90_days"
  }

GET /api/v1/ml/predictions/workload
  Description: Прогноз нагрузки на исполнителей
  Query: ?executor_ids=456,789&date_range=week

GET /api/v1/ml/model-performance/{model_id}
  Description: Метрики производительности модели
```

---

## 🧪 TESTING STRATEGY

### **Unit Tests (70% coverage target)**
```python
tests/unit/
├── test_smart_dispatcher.py      # Core assignment logic
├── test_assignment_optimizer.py  # Optimization algorithms
├── test_geo_optimizer.py         # Geographic calculations
├── test_workload_predictor.py    # ML prediction accuracy
└── test_recommendation_engine.py # Recommendation quality
```

### **Integration Tests (20% coverage)**
```python
tests/integration/
├── test_service_communication.py # Inter-service calls
├── test_database_operations.py   # Database consistency
├── test_event_handling.py        # Event-driven workflows
└── test_api_endpoints.py         # End-to-end API testing
```

### **Performance Tests (10% coverage)**
```python
tests/performance/
├── test_assignment_speed.py      # Assignment latency
├── test_optimization_scale.py    # Large dataset optimization
├── test_concurrent_requests.py   # Concurrent load handling
└── test_memory_usage.py          # Memory optimization
```

---

## ⚡ REALISTIC PERFORMANCE TARGETS

### **ACHIEVABLE Assignment Performance**
- **Single Assignment**: < 200ms (using district proximity instead of coordinates)
- **Batch Assignment**: < 100ms per request (simplified algorithms)
- **Basic Optimization**: < 3 seconds for 50 requests (no complex TSP)
- **District Grouping**: < 5 seconds for route clustering

### **FEASIBLE ML Model Performance**
- **Success Prediction**: > 70% accuracy (using execution_quality_rating as labels)
- **Workload Prediction**: > 65% accuracy (daily patterns + historical averages)
- **Model Training**: < 10 minutes (simple sklearn models on limited features)
- **Inference Time**: < 50ms per prediction (basic feature engineering)
- **Memory Usage**: < 256MB per service instance (lightweight models)

### **API Response Times**
- **GET endpoints**: < 100ms
- **POST endpoints**: < 500ms
- **Optimization endpoints**: < 10s
- **Health checks**: < 50ms

---

## 🔧 DEPLOYMENT & INFRASTRUCTURE

### **Docker Configuration**
```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . /app
WORKDIR /app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8006/api/v1/health || exit 1

EXPOSE 8006
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8006"]
```

### **Environment Variables**
```bash
# Service Configuration
AI_SERVICE_PORT=8006
AI_SERVICE_HOST=0.0.0.0
DEBUG=false

# Database
AI_DATABASE_URL=postgresql+asyncpg://ai_user:ai_pass@ai-db:5432/ai_db
AI_REDIS_URL=redis://shared-redis:6379/6

# Service Integration
AUTH_SERVICE_URL=http://auth-service:8001
USER_SERVICE_URL=http://user-service:8002
REQUEST_SERVICE_URL=http://request-service:8003

# ML Configuration
ML_MODEL_PATH=/app/models
TRAINING_DATA_RETENTION_DAYS=90
MODEL_RETRAIN_SCHEDULE=weekly

# Performance Tuning
MAX_CONCURRENT_ASSIGNMENTS=10
ASSIGNMENT_TIMEOUT_SECONDS=30
OPTIMIZATION_MAX_ITERATIONS=1000
GEO_CACHE_TTL_HOURS=24
```

---

## 📊 SUCCESS CRITERIA

### **Functional Requirements** ✅
- [ ] Все 4 алгоритма оптимизации работают
- [ ] Geographic optimization функционален
- [ ] ML workload prediction точность > 85%
- [ ] API endpoints покрывают всю функциональность
- [ ] Service-to-service integration работает

### **Non-Functional Requirements** ✅
- [ ] Performance targets достигнуты
- [ ] 95%+ uptime в development
- [ ] Memory usage < 512MB per instance
- [ ] API response times в пределах SLA
- [ ] Database queries оптимизированы

### **Quality Requirements** ✅
- [ ] Unit test coverage > 70%
- [ ] Integration test coverage > 80%
- [ ] Code quality score > 8.5/10
- [ ] API documentation complete
- [ ] Deployment runbooks готовы

---

## 🔄 MIGRATION STRATEGY

### **Phase 1: Shadow Mode (Days 1-10)**
- AI Service работает параллельно с монолитом
- Сравнение результатов assignment алгоритмов
- Performance benchmarking
- Нет влияния на production

### **Phase 2: Gradual Cutover (Days 11-15)**
- 25% traffic → AI Service
- 75% traffic → Monolith
- A/B testing assignment качества
- Rollback готовность

### **Phase 3: Full Migration (Days 16-20)**
- 100% traffic → AI Service
- Monolith AI components отключены
- Performance monitoring
- Cleanup legacy code

---

## 📈 RISK MITIGATION

### **High Risk: ML Model Accuracy**
- **Mitigation**: Comprehensive training data validation
- **Fallback**: Revert to simple scoring algorithms
- **Monitoring**: Real-time accuracy tracking

### **Medium Risk: Performance Degradation**
- **Mitigation**: Extensive load testing
- **Fallback**: Horizontal scaling готовность
- **Monitoring**: Response time alerting

### **Low Risk: Service Integration**
- **Mitigation**: Contract testing между сервисами
- **Fallback**: Circuit breaker patterns
- **Monitoring**: Service health dashboards

---

**🎯 Sprint 10-13 завершит критически важный AI компонент системы и подготовит платформу для финальных спринтов!**