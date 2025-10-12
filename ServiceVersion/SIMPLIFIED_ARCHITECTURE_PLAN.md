# 🎯 План упрощения микросервисной архитектуры UK Management Bot

**Версия**: 1.1.0
**Дата**: 8 октября 2025
**Статус**: 🔄 К реализации
**Автор**: Архитектурный анализ системы
**Обновлено**: Интегрирован Building Assets Module в Core Service

---

## 📊 Исполнительное резюме

### Текущие проблемы
- **10 микросервисов** с массивным дублированием кода (70-95%)
- **7,600+ строк** идентичного инфраструктурного кода
- **Синхронные блокировки** в критических операциях (2-10 секунд)
- **200+ database connections** из-за изолированных пулов
- **Отсутствие retry/DLQ механизмов** → каскадные сбои

### Предлагаемое решение
- **Консолидация 10→7 сервисов** (6 основных + 1 AI/ML в будущем)
- **AI/ML Service изолирован** - развертывается независимо, когда готов
- **Analytics и Integration разделены** - разные паттерны нагрузки
- **RabbitMQ + Celery** для асинхронной обработки задач
- **Shared Library** для устранения дублирования
- **Priority Queues** для управления нагрузкой

### Ожидаемые результаты
- **Response time**: 2000ms → 100ms (20x улучшение)
- **Codebase**: -7,600 строк (-25% от общего объема)
- **Maintenance**: -50% усилий на поддержку
- **Reliability**: Auto-retry + Dead Letter Queue

---

## 🔍 Анализ текущей архитектуры

### Карта дублирования кода

| Компонент | Файлов | Дублированных строк | % совпадения | Затронуто сервисов |
|-----------|--------|---------------------|--------------|-------------------|
| **JWT Auth Middleware** | 7 | ~1,200 | 90% | 7 |
| **Event Publishers** | 6 | ~1,400 | 95% | 6 |
| **Logging Middleware** | 5 | ~840 | 100% | 5 |
| **Tracing Middleware** | 4 | ~572 | 100% | 4 |
| **Configuration** | 10 | ~600 | 85% | 10 |
| **Database Sessions** | 8 | ~600 | 80% | 8 |
| **Health Checks** | 4 | ~400 | 95% | 4 |
| **ИТОГО** | **100+** | **~7,600** | **70-95%** | **10** |

### Выявленные блокировки

| Операция | Текущее время | Причина блокировки |
|----------|--------------|-------------------|
| **Telegram Media Upload** | 2-5 секунд | Синхронная загрузка |
| **AI Assignment** | 5-10 секунд | ML вычисления в request thread |
| **Batch Notifications** | 500ms × N | Последовательная отправка |
| **Analytics Aggregation** | До 30 секунд | Тяжелые SQL запросы |
| **Request Creation** | 1-2 секунды | 5+ синхронных вызовов сервисов |

---

## 🏗️ Новая упрощенная архитектура

### Консолидация сервисов: 10 → 7 + Frontend

```
ТЕКУЩАЯ АРХИТЕКТУРА (10 сервисов)     →    НОВАЯ АРХИТЕКТУРА (7 сервисов + 3 Frontend)
─────────────────────────────────           ──────────────────────────────────────────

BACKEND SERVICES:
1. Auth Service          ┐
2. User Service          ├─────→            1. Core Service
3. Request Service       ┘                  (auth + users + requests + building assets)
                                            📍 Includes: Building Assets Module

4. Shift Service        ───────→            2. Operations Service
                                            (shifts + assignments + scheduling)

5. AI Service           ───────→            3. AI/ML Service [FUTURE]
                                            (ML models + optimization + predictions)
                                            ⚠️ Развертывается позже, независимо

6. Notification Service  ┐                  4. Communication Hub
7. Bot Gateway          ┘─────→            (notifications OUT + bot + WebSocket)
                                            📤 Outbound: уведомления пользователям

8. Media Service        ───────→            5. Media Storage Service
                                            (upload + processing + CDN)

9. Analytics Service    ───────→            6. Analytics Service
                                            (metrics + KPIs + reports + dashboards)
                                            📊 Internal: аналитика системы

10. Integration Service ───────→            7. Integration Hub
                                            (external APIs IN + caching + webhooks)
                                            📥 Inbound: данные из внешних систем

FRONTEND APPLICATIONS:
[Не существовало]       ───────→            1. WebApp (React/Vue SPA)
                                            (user interface, PWA)

[Bot Gateway UI]        ───────→            2. Telegram Bot Client
                                            (команды, меню, inline)

[Не существовало]       ───────→            3. Admin Panel
                                            (monitoring, management)
```

### Архитектура с Message Queue

```
┌──────────────────────────────────────────────────────────┐
│                    API Gateway / Load Balancer            │
│                         (Nginx/Traefik)                   │
└──────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   WebApp     │    │ Bot Gateway  │    │  Admin Panel │
│   (3000)     │    │  (Telegram)  │    │    (3001)    │
├──────────────┤    ├──────────────┤    ├──────────────┤
│ • React/Vue  │    │ • Webhook    │    │ • Dashboard  │
│ • User UI    │    │ • Polling    │    │ • Reports    │
│ • PWA        │    │ • Commands   │    │ • Analytics  │
└──────────────┘    └──────────────┘    └──────────────┘
        │                   │                   │
        └───────────────────┼───────────────────┘
                            ▼
                    [HTTP/WebSocket]
                            │
     ┌──────────────────────┴──────────────────────┐
     │              BACKEND SERVICES               │
     │                                             │
┌────▼──────┐ ┌────────────┐ ┌──────────┐ ┌──────────┐
│   Core    │ │ Operations │ │  Comm.   │ │  Media   │
│  Service  │ │  Service   │ │   Hub    │ │ Storage  │
│  (8001)   │ │   (8002)   │ │  (8003)  │ │  (8004)  │
└─────┬─────┘ └─────┬──────┘ └────┬─────┘ └────┬─────┘
      │             │              │             │
┌─────▼─────┐ ┌─────▼──────┐ ┌────▼─────┐      │
│ Analytics │ │Integration │ │ AI/ML    │      │
│  Service  │ │    Hub     │ │ [FUTURE] │      │
│  (8005)   │ │   (8006)   │ │  (8007)  │      │
└─────┬─────┘ └─────┬──────┘ └────┬─────┘      │
      │             │              │             │
      └─────────────┴──────────────┴─────────────┘
                            │
                    [Publish Tasks]
                            ▼
┌──────────────────────────────────────────────────────────┐
│                 🐰 RabbitMQ Message Broker                │
│                        (Port: 5672)                       │
├──────────────────────────────────────────────────────────┤
│  Queues & Priorities:                                     │
│  ┌─────────────────────────────────────────────────┐     │
│  │ 🔴 HIGH PRIORITY (9-10)                         │     │
│  │ • comm.urgent     - Critical notifications      │     │
│  │ • ops.emergency   - Emergency assignments       │     │
│  └─────────────────────────────────────────────────┘     │
│  ┌─────────────────────────────────────────────────┐     │
│  │ 🟡 MEDIUM PRIORITY (4-8)                        │     │
│  │ • core.tasks      - Request processing          │     │
│  │ • media.upload    - File uploads                │     │
│  │ • integration.api - External API calls          │     │
│  └─────────────────────────────────────────────────┘     │
│  ┌─────────────────────────────────────────────────┐     │
│  │ 🟢 LOW PRIORITY (1-3)                           │     │
│  │ • analytics.batch - Hourly aggregations         │     │
│  │ • comm.batch      - Bulk notifications          │     │
│  │ • ai.ml.train     - Model training              │     │
│  └─────────────────────────────────────────────────┘     │
│  ┌─────────────────────────────────────────────────┐     │
│  │ ☠️ Dead Letter Queue (DLQ)                      │     │
│  │ • Failed tasks after max retries                │     │
│  └─────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────┘
                            │
                    [Consume Tasks]
                            ▼
┌──────────────────────────────────────────────────────────┐
│               🔄 Celery Workers Pool                      │
│                                                          │
├─────────────────────┬────────────────────────────────────┤
│ Worker Type         │ Config                             │
├─────────────────────┼────────────────────────────────────┤
│ core-worker (x3)    │ Queues: core.tasks                 │
│                     │ Concurrency: 4                     │
├─────────────────────┼────────────────────────────────────┤
│ ops-worker (x2)     │ Queues: ops.*, scheduling          │
│                     │ Concurrency: 2                     │
├─────────────────────┼────────────────────────────────────┤
│ comm-worker (x5)    │ Queues: comm.urgent, comm.regular  │
│                     │ Concurrency: 10                    │
├─────────────────────┼────────────────────────────────────┤
│ media-worker (x3)   │ Queues: media.upload, media.process│
│                     │ Concurrency: 3                     │
├─────────────────────┼────────────────────────────────────┤
│ analytics-worker(x2)│ Queues: analytics.batch            │
│                     │ Concurrency: 2, Time limit: 600s   │
├─────────────────────┼────────────────────────────────────┤
│ integration-worker  │ Queues: integration.api, sync      │
│         (x3)        │ Concurrency: 5                     │
└─────────────────────┴────────────────────────────────────┘

Data Flow:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Service publishes task → RabbitMQ Queue
2. Celery Worker consumes task from Queue
3. Worker executes task (async)
4. Result stored in Redis backend
5. Service polls/callbacks for result
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 📍 Building Assets Module в Core Service

### Обоснование решения

#### Почему в Core Service, а не отдельный сервис?

1. **Производительность** - нет дополнительных сетевых вызовов между сервисами
2. **Целостность данных** - foreign keys в одной БД для связей User ↔ Apartment ↔ Request
3. **Простота для MVP** - не нужен 8-й микросервис
4. **Тесная интеграция** - заявки и пользователи всегда связаны с адресами

#### Критическая важность для управляющей компании

- **Единая точка истины** - исключает разночтения в адресах
- **Оптимизация маршрутов** - геоданные для расчета оптимальных путей исполнителей
- **Точная адресация** - от комплекса до конкретной квартиры/парковочного места
- **Зоны обслуживания** - распределение территории между исполнителями

### Иерархия данных недвижимости

```
Complex (Жилой комплекс)
├── Building (Здание)
│   ├── Entrance (Подъезд)
│   │   ├── Floor (Этаж)
│   │   │   ├── Apartment (Квартира)
│   │   │   ├── Office (Офис)
│   │   │   └── Storage (Кладовка)
│   ├── Parking (Парковка)
│   │   └── Parking Spot (Место)
│   └── Infrastructure
│       ├── Elevator (Лифт)
│       └── Technical Room
└── Territory
    ├── Playground
    └── Green Zone
```

### Геофункциональность

#### PostGIS Extensions
- `GEOGRAPHY(POINT, 4326)` - координаты объектов
- `GEOGRAPHY(POLYGON, 4326)` - границы территорий
- Spatial индексы для быстрого поиска (< 50ms)
- Функции: ST_DWithin, ST_Contains, ST_Distance

#### Кеширование в Redis
- Адрес → Координаты: TTL 30 дней
- Building metadata: TTL 5 минут
- Distance matrix: TTL 7 дней

### API Endpoints

```
# Управление активами
GET    /api/v1/assets/complexes
GET    /api/v1/assets/buildings
GET    /api/v1/assets/apartments
POST   /api/v1/assets/apartments/{id}/residents

# Геопоиск
GET    /api/v1/assets/search/nearby?lat={lat}&lng={lng}&radius={radius}
POST   /api/v1/assets/geocode
GET    /api/v1/assets/zones/{id}/assets

# Адресный поиск
GET    /api/v1/assets/search?q={query}
GET    /api/v1/assets/validate-address
```

### Интеграции с другими сервисами

#### Operations Service
```python
# Получает геоданные для оптимизации маршрутов
buildings = CoreService.get_buildings_in_zone(zone_id)
route = calculate_optimal_route(buildings.locations)
```

#### Integration Hub
```python
# Синхронизирует с внешним Building Directory API
external_data = fetch_building_directory()
CoreService.sync_building_assets(external_data)
```

#### Analytics Service
```python
# Анализирует распределение заявок по зданиям
heatmap = CoreService.get_request_density_by_buildings()
```

### Преимущества решения

#### Для бизнеса
- ✅ Точное понимание где находится каждая заявка
- ✅ Оптимальное распределение исполнителей по территории
- ✅ Исключение ошибок в адресах
- ✅ Быстрый поиск по любым критериям

#### Для разработки
- ✅ Нет дополнительного микросервиса
- ✅ Простые JOIN'ы в одной БД
- ✅ Единая транзакция для связанных данных
- ✅ Быстрый старт без сложной инфраструктуры

#### Для производительности
- ✅ Геопоиск < 50ms с индексами
- ✅ Кеширование частых запросов
- ✅ Batch операции для импорта
- ✅ Нет сетевых задержек между сервисами

---

## 📦 Shared Library Structure

```
microservices/shared_lib/
├── setup.py
├── requirements.txt
├── README.md
│
├── core/
│   ├── __init__.py
│   ├── config.py              # BaseSettings для всех сервисов
│   ├── database.py            # AsyncDatabase manager
│   ├── redis_client.py        # Единый Redis client
│   ├── exceptions.py          # Common exceptions
│   └── models.py              # Base SQLAlchemy models
│
├── middleware/
│   ├── __init__.py
│   ├── auth.py                # JWT middleware (единая реализация)
│   ├── logging.py             # Structured logging middleware
│   ├── tracing.py             # OpenTelemetry integration
│   ├── rate_limit.py          # Rate limiting with Redis
│   └── error_handler.py       # Global error handling
│
├── messaging/
│   ├── __init__.py
│   ├── rabbitmq.py            # RabbitMQ connection pool
│   ├── celery_app.py          # Celery configuration
│   ├── publisher.py           # Event publisher base class
│   ├── consumer.py            # Event consumer base class
│   └── schemas.py             # Event schemas (Pydantic)
│
├── clients/
│   ├── __init__.py
│   ├── http_client.py         # Service-to-service HTTP client
│   ├── circuit_breaker.py     # Circuit breaker pattern
│   └── retry_policy.py        # Retry with exponential backoff
│
└── utils/
    ├── __init__.py
    ├── health_check.py        # Unified health check
    ├── validators.py          # Common validators
    ├── security.py            # Security utilities
    └── monitoring.py          # Prometheus metrics
```

---

## 🚀 План реализации

### Фаза 1: Инфраструктура (Неделя 1)

#### 1.1 Развертывание RabbitMQ и Celery

```yaml
# docker-compose.yml additions

# Frontend Applications
webapp:
  build:
    context: ./webapp
    dockerfile: Dockerfile
  container_name: webapp
  ports:
    - "3000:80"
  environment:
    - REACT_APP_API_URL=http://localhost:8001
    - REACT_APP_WS_URL=ws://localhost:8003/ws
  depends_on:
    - core-service
    - communication-hub
  volumes:
    - ./webapp/nginx.conf:/etc/nginx/conf.d/default.conf
  networks:
    - microservices-network

admin-panel:
  build:
    context: ./admin_panel
    dockerfile: Dockerfile
  container_name: admin-panel
  ports:
    - "3001:80"
  environment:
    - REACT_APP_API_URL=http://localhost:8001
    - REACT_APP_GRAFANA_URL=http://localhost:3000
    - REACT_APP_FLOWER_URL=http://localhost:5555
  depends_on:
    - core-service
  networks:
    - microservices-network

# Message Queue Infrastructure
rabbitmq:
  image: rabbitmq:3.12-management-alpine
  container_name: rabbitmq
  ports:
    - "5672:5672"      # AMQP
    - "15672:15672"    # Management UI
  environment:
    RABBITMQ_DEFAULT_USER: uk_admin
    RABBITMQ_DEFAULT_PASS: ${RABBITMQ_PASSWORD}
    RABBITMQ_DEFAULT_VHOST: /uk_management
  volumes:
    - rabbitmq_data:/var/lib/rabbitmq
    - ./rabbitmq/rabbitmq.conf:/etc/rabbitmq/rabbitmq.conf
    - ./rabbitmq/definitions.json:/etc/rabbitmq/definitions.json
  healthcheck:
    test: ["CMD", "rabbitmq-diagnostics", "ping"]
    interval: 30s
    timeout: 10s
    retries: 5

celery-flower:
  image: mher/flower:2.0
  container_name: celery-flower
  command: celery --broker=amqp://uk_admin:${RABBITMQ_PASSWORD}@rabbitmq:5672//uk_management flower --port=5555
  ports:
    - "5555:5555"
  depends_on:
    rabbitmq:
      condition: service_healthy
  environment:
    FLOWER_BASIC_AUTH: admin:${FLOWER_PASSWORD}
```

#### 1.2 Создание Shared Library

```python
# shared_lib/setup.py
from setuptools import setup, find_packages

setup(
    name="uk-shared-lib",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.104.0",
        "sqlalchemy>=2.0.0",
        "redis>=5.0.0",
        "celery>=5.3.0",
        "pydantic>=2.0.0",
        "python-jose>=3.3.0",
        "httpx>=0.25.0",
        "prometheus-client>=0.18.0",
        "opentelemetry-api>=1.20.0",
    ],
)
```

### Фаза 2: Core Service (Недели 2-3)

#### 2.1 Структура Core Service

```python
# core_service/main.py
from fastapi import FastAPI
from shared_lib.middleware import JWTMiddleware, LoggingMiddleware, TracingMiddleware
from shared_lib.core import BaseSettings

class CoreSettings(BaseSettings):
    service_name: str = "core-service"
    service_port: int = 8001
    # Специфичные настройки Core Service

app = FastAPI(title="Core Service")

# Используем shared middleware
app.add_middleware(JWTMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(TracingMiddleware)

# Подключаем роутеры
app.include_router(auth_router, prefix="/api/v1/auth")
app.include_router(users_router, prefix="/api/v1/users")
app.include_router(requests_router, prefix="/api/v1/requests")
app.include_router(assets_router, prefix="/api/v1/assets")  # Building Assets Module
```

#### 2.2 Celery Tasks для Core Service

```python
# core_service/tasks/request_tasks.py
from shared_lib.messaging.celery_app import create_celery_app

celery = create_celery_app('core-service')

@celery.task(
    name='core.request.create',
    queue='core.tasks',
    bind=True,
    max_retries=3
)
def create_request_async(self, request_data: dict) -> dict:
    """
    Асинхронное создание заявки с Saga pattern

    Шаги:
    1. Создать заявку в БД с привязкой к Building Asset
    2. Получить геоданные из Building Assets Module
    3. Назначить исполнителя (Operations Service)
    4. Отправить уведомления (Communication Hub)
    5. Обновить аналитику

    При ошибке - компенсирующие транзакции
    """
    try:
        # Step 1: Create request with building/asset association
        request = RequestService.create(request_data)

        # Step 2: Get building data from Building Assets Module
        building = BuildingAssetsService.get_by_apartment(request.apartment_id)
        request.location = building.location
        request.building_id = building.id
        request.entrance_info = building.get_entrance_info()

        # Step 3: Assign executor (async call to Operations)
        # Передаем геоданные для оптимизации маршрута
        assignment_task = assign_executor.delay(
            request_id=request.id,
            location=request.location,
            building_id=request.building_id
        )

        # Step 4: Send notifications (async call to Communication)
        notification_task = send_notification.delay(
            event_type='request.created',
            request_id=request.id,
            address=building.formatted_address
        )

        return {'request_id': request.id, 'status': 'processing'}

    except Exception as exc:
        # Compensating transaction
        if 'request' in locals():
            RequestService.rollback(request.id)
        raise self.retry(exc=exc, countdown=60)

@celery.task(
    name='core.assets.sync',
    queue='core.tasks',
    bind=True,
    max_retries=3
)
def sync_building_assets(self) -> dict:
    """
    Синхронизация справочника зданий с внешними источниками

    Запускается по расписанию или по команде
    """
    from services.building_assets import BuildingAssetsSync

    sync = BuildingAssetsSync()
    result = sync.sync_with_external_directory()

    return {
        'synced': result.synced_count,
        'updated': result.updated_count,
        'errors': result.error_count
    }
```

### Фаза 3: Operations Service (Недели 4-5)

#### 3.1 Shift Management Configuration

```python
# operations_service/services/shift_service.py
from shared_lib.messaging.celery_app import create_celery_app

celery = create_celery_app('operations-service')

@celery.task(
    name='ops.shift.plan',
    queue='ops.scheduling',
    bind=True,
    max_retries=3
)
def plan_shifts(period: str, template: str = 'standard') -> Dict:
    """
    Автоматическое планирование смен

    Periods: daily, weekly, monthly
    Templates: standard, 24h, flexible
    """
    from services.shift_planner import ShiftPlanner

    planner = ShiftPlanner()
    shifts = planner.create_shifts(
        period=period,
        template=template,
        auto_assign=True
    )

    return {
        'created_shifts': len(shifts),
        'period': period,
        'template': template
    }

@celery.task(
    name='ops.assignment.basic',
    queue='ops.assignments'
)
def assign_executor_basic(request_id: str) -> Dict:
    """
    Базовое назначение исполнителя (без ML)

    Использует простые правила:
    - По специализации
    - По географической близости
    - По текущей загрузке
    - По рейтингу
    """
    from services.basic_assignment import BasicAssignmentService

    service = BasicAssignmentService()

    # Простой алгоритм назначения
    assignment = service.assign(
        request_id=request_id,
        strategy='balanced',  # balanced, nearest, rating
        fallback_enabled=True
    )

    return {
        'request_id': request_id,
        'executor_id': assignment.executor_id,
        'score': assignment.score,
        'method': 'basic_rules'
    }

@celery.task(
    name='ops.assignment.with_ai',
    queue='ops.assignments'
)
def assign_executor_with_ai(request_id: str) -> Dict:
    """
    Назначение с использованием AI Service (если доступен)

    Fallback to basic assignment if AI Service unavailable
    """
    from clients.ai_service_client import AIServiceClient

    ai_client = AIServiceClient()

    try:
        # Попытка использовать AI Service
        if ai_client.is_available():
            result = await ai_client.optimize_assignment(request_id)
            return {
                'request_id': request_id,
                'executor_id': result.executor_id,
                'score': result.confidence,
                'method': 'ai_optimized'
            }
    except Exception as e:
        logger.warning(f"AI Service unavailable: {e}, falling back to basic")

    # Fallback к базовому алгоритму
    return assign_executor_basic.apply(args=[request_id]).get()
```

### Фаза 3.5: AI/ML Service [FUTURE PHASE]

#### 3.5.1 Независимый AI/ML Service

```python
# ai_ml_service/main.py
"""
AI/ML Service - развертывается независимо после MVP

Функции:
- ML модели для оптимизации назначений
- Предсказания времени выполнения
- Аномалии и паттерны
- Рекомендации

Может быть развернут в любой момент без изменения других сервисов
"""

from fastapi import FastAPI
from shared_lib.middleware import JWTMiddleware

app = FastAPI(title="AI/ML Service")

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "ai-ml-service",
        "features": {
            "ml_optimization": True,
            "predictions": True,
            "anomaly_detection": False  # В разработке
        }
    }
```

#### 3.5.2 ML Tasks (будущая реализация)

```python
# ai_ml_service/tasks/ml_tasks.py
from shared_lib.messaging.celery_app import create_celery_app

celery = create_celery_app('ai-ml-service')

@celery.task(
    name='ai.ml.optimize',
    queue='ai.compute',
    time_limit=300,      # 5 min hard limit
    soft_time_limit=240  # 4 min soft limit
)
def optimize_with_ml(
    request_ids: List[str],
    executor_ids: List[str],
    algorithm: str = 'hybrid'
) -> Dict:
    """
    ML оптимизация назначений

    Algorithms:
    - genetic: Genetic Algorithm
    - annealing: Simulated Annealing
    - neural: Neural Network
    - hybrid: Combined approach

    Returns optimal assignment matrix
    """
    from services.ml_optimizer import MLOptimizer

    optimizer = MLOptimizer(algorithm=algorithm)
    assignments = optimizer.optimize(
        requests=request_ids,
        executors=executor_ids,
        constraints={
            'max_distance': 10_000,
            'specialization_match': 0.8,
            'load_balance': True
        }
    )

    return {
        'assignments': assignments,
        'confidence': optimizer.confidence_score,
        'computation_time': optimizer.elapsed_time,
        'algorithm_used': algorithm
    }

@celery.task(
    name='ai.ml.predict',
    queue='ai.compute'
)
def predict_completion_time(request_data: Dict) -> Dict:
    """
    Предсказание времени выполнения заявки
    """
    # ML модель для предсказания
    pass

@celery.task(
    name='ai.ml.train',
    queue='ai.compute',
    time_limit=3600  # 1 hour for training
)
def train_models(training_data: List[Dict]) -> Dict:
    """
    Переобучение ML моделей (weekly job)
    """
    # Обучение моделей
    pass
```

### Фаза 4: Communication Hub (Недели 6-7)

#### 4.1 Priority Queue System

```python
# communication_hub/tasks/notification_tasks.py
from shared_lib.messaging.celery_app import create_celery_app

celery = create_celery_app('communication-hub')

# Критичные уведомления (Priority 9/10)
@celery.task(
    name='comm.notify.urgent',
    queue='comm.urgent',
    priority=9,
    max_retries=10,
    default_retry_delay=30
)
def send_urgent_notification(
    user_id: str,
    message: str,
    channels: List[str] = ['telegram']
) -> Dict:
    """
    Критичные уведомления:
    - Новые заявки
    - Экстренные ситуации
    - Смена смены

    Max retries: 10
    Retry delay: 30s exponential backoff
    """
    from services.notification_sender import NotificationSender

    sender = NotificationSender()
    results = []

    for channel in channels:
        result = sender.send(
            channel=channel,
            user_id=user_id,
            message=message,
            priority='urgent'
        )
        results.append(result)

    return {'sent': len(results), 'channels': channels}

# Обычные уведомления (Priority 5/10)
@celery.task(
    name='comm.notify.regular',
    queue='comm.regular',
    priority=5,
    max_retries=3
)
def send_regular_notification(
    user_id: str,
    message: str
) -> Dict:
    """
    Обычные уведомления:
    - Обновления статуса
    - Комментарии
    - Информационные сообщения
    """
    pass

# Массовые рассылки (Priority 1/10)
@celery.task(
    name='comm.notify.batch',
    queue='comm.batch',
    priority=1
)
def send_batch_notifications(
    notifications: List[Dict],
    batch_size: int = 50
) -> Dict:
    """
    Массовые рассылки:
    - Дайджесты
    - Отчеты
    - Маркетинг

    Обрабатывает батчами по 50 сообщений
    Rate limit: 20 msg/sec
    """
    from services.batch_sender import BatchSender

    sender = BatchSender(rate_limit=20)
    results = sender.send_batch(
        notifications=notifications,
        batch_size=batch_size
    )

    return {
        'total': len(notifications),
        'sent': results['sent'],
        'failed': results['failed']
    }
```

### Фаза 5: Media Storage Service (Неделя 8)

#### 5.1 Async Media Processing

```python
# media_service/tasks/media_tasks.py
from shared_lib.messaging.celery_app import create_celery_app

celery = create_celery_app('media-service')

@celery.task(
    name='media.upload.telegram',
    queue='media.upload',
    bind=True,
    max_retries=5,
    retry_backoff=True,
    retry_backoff_max=600
)
def upload_to_telegram_async(
    self,
    file_path: str,
    chat_id: int,
    caption: str = None
) -> Dict:
    """
    Асинхронная загрузка в Telegram

    Retry strategy:
    - 1st: 60s
    - 2nd: 120s
    - 3rd: 240s
    - 4th: 480s
    - 5th: 600s
    """
    from services.telegram_uploader import TelegramUploader

    try:
        uploader = TelegramUploader()
        result = uploader.upload(
            file_path=file_path,
            chat_id=chat_id,
            caption=caption
        )

        return {
            'status': 'success',
            'telegram_file_id': result.file_id,
            'upload_time': result.duration
        }

    except Exception as exc:
        # Exponential backoff retry
        countdown = min(60 * (2 ** self.request.retries), 600)
        raise self.retry(exc=exc, countdown=countdown)

@celery.task(
    name='media.process.video',
    queue='media.process',
    time_limit=600  # 10 min for video processing
)
def process_video(
    file_id: str,
    operations: List[str]
) -> Dict:
    """
    Video processing pipeline:
    - transcode: Convert to H.264
    - compress: Reduce size
    - thumbnail: Generate preview
    - watermark: Add logo
    """
    pass
```

### Фаза 6: WebApp Frontend (Неделя 9)

#### 6.1 WebApp Architecture

```
microservices/webapp/
├── public/                    # Static files
├── src/
│   ├── api/                  # API client layer
│   │   ├── auth.ts           # Auth API calls
│   │   ├── requests.ts       # Requests API
│   │   └── websocket.ts      # Real-time updates
│   ├── components/           # React/Vue components
│   │   ├── common/          # Shared components
│   │   ├── requests/        # Request management UI
│   │   ├── shifts/          # Shift planning UI
│   │   └── analytics/       # Dashboards
│   ├── hooks/               # Custom React hooks
│   │   ├── useAuth.ts      # Authentication
│   │   ├── useWebSocket.ts # Real-time connection
│   │   └── useApi.ts       # API wrapper
│   ├── stores/              # State management (Redux/Pinia)
│   │   ├── auth.store.ts
│   │   ├── request.store.ts
│   │   └── notification.store.ts
│   └── pages/               # Page components
│       ├── Dashboard.tsx
│       ├── Requests/
│       ├── Shifts/
│       └── Profile/
├── Dockerfile
└── nginx.conf              # SPA routing config
```

#### 6.2 WebApp Features

```typescript
// webapp/src/api/client.ts
class APIClient {
  private baseURL = process.env.REACT_APP_API_URL || 'http://localhost:8001';
  private ws: WebSocket;

  constructor() {
    this.initWebSocket();
  }

  private initWebSocket() {
    // Connect to Communication Hub WebSocket
    this.ws = new WebSocket('ws://localhost:8003/ws');

    this.ws.on('message', (data) => {
      // Real-time updates for:
      // - New requests
      // - Status changes
      // - Notifications
      store.dispatch('handleRealtimeUpdate', data);
    });
  }

  // API methods with queue status
  async createRequest(data: RequestDTO): Promise<{ id: string, status: 'queued' }> {
    const response = await this.post('/api/v1/requests', data);

    // Show queue status in UI
    if (response.status === 'queued') {
      this.showQueueNotification(response.taskId);
    }

    return response;
  }

  private showQueueNotification(taskId: string) {
    // Poll task status via Celery result backend
    const pollInterval = setInterval(async () => {
      const status = await this.get(`/api/v1/tasks/${taskId}/status`);

      if (status.state === 'SUCCESS') {
        clearInterval(pollInterval);
        notification.success('Request processed successfully!');
      } else if (status.state === 'FAILURE') {
        clearInterval(pollInterval);
        notification.error('Request processing failed');
      }
    }, 1000);
  }
}
```

#### 6.3 Progressive Web App (PWA) Configuration

```javascript
// webapp/src/serviceWorker.js
// PWA для работы offline и push-уведомлений

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open('uk-app-v1').then((cache) => {
      return cache.addAll([
        '/',
        '/static/css/main.css',
        '/static/js/bundle.js',
        '/offline.html'
      ]);
    })
  );
});

// Push notifications from Communication Hub
self.addEventListener('push', (event) => {
  const data = event.data.json();

  const options = {
    body: data.message,
    icon: '/logo192.png',
    badge: '/badge.png',
    actions: [
      { action: 'view', title: 'View' },
      { action: 'dismiss', title: 'Dismiss' }
    ]
  };

  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});
```

#### 6.4 Admin Panel

```
microservices/admin_panel/
├── src/
│   ├── components/
│   │   ├── Dashboard/        # Real-time metrics
│   │   ├── QueueMonitor/     # Celery queue status
│   │   ├── ServiceHealth/    # Service health checks
│   │   └── Reports/          # Analytics reports
│   ├── pages/
│   │   ├── SystemOverview.tsx
│   │   ├── UserManagement.tsx
│   │   ├── RequestsAdmin.tsx
│   │   └── Settings.tsx
│   └── api/
│       └── admin.ts          # Admin API client
└── Dockerfile
```

### Фаза 7: Analytics Service (Неделя 10)

#### 7.1 Analytics Service Configuration

```python
# analytics_service/main.py
from fastapi import FastAPI
from shared_lib.middleware import LoggingMiddleware

app = FastAPI(title="Analytics Service")

# Характеристики:
# - Read-heavy (90% чтение, 10% запись)
# - Batch processing для агрегаций
# - Time-series база данных (TimescaleDB)
# - Вертикальное масштабирование (больше CPU/RAM)
```

#### 7.2 Analytics Batch Processing

```python
# analytics_service/celery_beat_schedule.py
from celery.schedules import crontab
from shared_lib.messaging.celery_app import create_celery_app

celery = create_celery_app('analytics-service')

# Celery Beat Schedule (замена APScheduler)
celery.conf.beat_schedule = {
    'aggregate-hourly-metrics': {
        'task': 'analytics.aggregate.hourly',
        'schedule': crontab(minute=5),  # Every hour at :05
        'options': {
            'queue': 'analytics.batch',
            'priority': 5
        }
    },

    'generate-daily-reports': {
        'task': 'analytics.reports.daily',
        'schedule': crontab(hour=1, minute=0),  # 01:00 daily
        'options': {
            'queue': 'analytics.batch',
            'priority': 7
        }
    },

    'sync-external-data': {
        'task': 'integration.sync.google_sheets',
        'schedule': crontab(minute='*/15'),  # Every 15 minutes
        'options': {
            'queue': 'analytics.batch',
            'priority': 3
        }
    },

    'cleanup-old-events': {
        'task': 'analytics.cleanup.events',
        'schedule': crontab(hour=3, minute=0),  # 03:00 daily
        'options': {
            'queue': 'analytics.batch',
            'priority': 1
        }
    }
}
```

### Фаза 8: Integration Hub (Неделя 11)

#### 8.1 Integration Hub Configuration

```python
# integration_hub/main.py
from fastapi import FastAPI
from shared_lib.middleware import RateLimitMiddleware

app = FastAPI(title="Integration Hub")

# Характеристики:
# - Write-heavy (60% запись в кеш, 40% чтение)
# - Real-time processing внешних API
# - Key-value кеш (Redis)
# - Горизонтальное масштабирование (много инстансов)
```

#### 8.2 External API Tasks

```python
# integration_hub/tasks/api_tasks.py
from shared_lib.messaging.celery_app import create_celery_app
from tenacity import retry, wait_exponential, stop_after_attempt

celery = create_celery_app('integration-hub')

@celery.task(
    name='integration.api.building',
    queue='integration.api',
    bind=True,
    max_retries=3
)
@retry(
    wait=wait_exponential(multiplier=1, min=4, max=10),
    stop=stop_after_attempt(3)
)
def fetch_building_data(self, building_id: str) -> Dict:
    """
    Получение данных о здании из Building Directory API

    Features:
    - Exponential backoff retry
    - Result caching (TTL 5 minutes)
    - Rate limiting (100 req/min)
    """
    from clients.building_directory import BuildingDirectoryClient

    client = BuildingDirectoryClient()

    # Check cache first
    cached = cache.get(f"building:{building_id}")
    if cached:
        return cached

    # Fetch from API
    building = client.get_building(building_id)

    # Cache result
    cache.set(f"building:{building_id}", building, ttl=300)

    return building

@celery.task(
    name='integration.api.geocode',
    queue='integration.api',
    time_limit=30
)
def geocode_address(address: str, provider: str = 'google') -> Dict:
    """
    Геокодирование адреса

    Providers:
    - google: Google Maps API
    - yandex: Yandex Maps API
    - osm: OpenStreetMap Nominatim
    """
    from clients.geocoding import GeocodingClient

    client = GeocodingClient(provider=provider)
    coords = client.geocode(address)

    return {
        'address': address,
        'latitude': coords.lat,
        'longitude': coords.lng,
        'provider': provider
    }

@celery.task(
    name='integration.sync.google_sheets',
    queue='integration.sync',
    time_limit=300
)
def sync_google_sheets(spreadsheet_id: str) -> Dict:
    """
    Синхронизация с Google Sheets

    - Двусторонняя синхронизация
    - Batch updates для производительности
    - Conflict resolution
    """
    from clients.google_sheets import GoogleSheetsClient

    client = GoogleSheetsClient()

    # Pull changes from sheet
    sheet_data = client.get_sheet_data(spreadsheet_id)

    # Process and sync with database
    sync_results = process_sheet_sync(sheet_data)

    # Push updates back to sheet
    if sync_results['changes']:
        client.update_sheet_batch(
            spreadsheet_id,
            sync_results['changes']
        )

    return {
        'pulled': len(sheet_data),
        'pushed': len(sync_results['changes']),
        'conflicts': sync_results['conflicts']
    }
```

#### 8.3 Webhook Handler

```python
# integration_hub/api/webhooks.py
from fastapi import APIRouter, HTTPException
from typing import Dict, Any

router = APIRouter(prefix="/webhooks")

@router.post("/{provider}")
async def handle_webhook(provider: str, payload: Dict[str, Any]):
    """
    Universal webhook handler for external systems

    Supported providers:
    - building_directory: Building updates
    - payment_gateway: Payment notifications
    - sms_gateway: Delivery reports
    """

    # Validate webhook signature
    if not validate_webhook_signature(provider, payload):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Queue for processing
    process_webhook.delay(provider, payload)

    return {"status": "queued"}
```

---

## 📊 Метрики и мониторинг

### Prometheus Metrics

```python
# shared_lib/utils/monitoring.py
from prometheus_client import Counter, Histogram, Gauge, Summary

# Celery metrics
celery_task_total = Counter(
    'celery_task_total',
    'Total number of Celery tasks',
    ['service', 'task_name', 'status']
)

celery_task_duration = Histogram(
    'celery_task_duration_seconds',
    'Task execution duration',
    ['service', 'task_name'],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300]
)

celery_queue_length = Gauge(
    'celery_queue_length',
    'Current queue length',
    ['queue_name']
)

# API metrics
api_requests_total = Counter(
    'api_requests_total',
    'Total API requests',
    ['service', 'method', 'endpoint', 'status']
)

api_request_duration = Histogram(
    'api_request_duration_seconds',
    'API request duration',
    ['service', 'method', 'endpoint']
)

# Business metrics
business_requests_created = Counter(
    'business_requests_created_total',
    'Total requests created',
    ['category', 'urgency']
)

business_notifications_sent = Counter(
    'business_notifications_sent_total',
    'Total notifications sent',
    ['channel', 'priority', 'status']
)
```

### Grafana Dashboards

1. **System Overview Dashboard**
   - Services health status
   - Request rate & latency
   - Error rate by service
   - Database connections

2. **Celery Performance Dashboard**
   - Task execution rate
   - Queue lengths
   - Worker utilization
   - Failed tasks & retries

3. **Business Metrics Dashboard**
   - Requests created/completed
   - User activity
   - Notification delivery rate
   - SLA compliance

---

## 🔄 План миграции

### Стратегия: Blue-Green Deployment с постепенной миграцией

#### Этап 1: Подготовка (Неделя 1)
- ✅ Развернуть RabbitMQ и Celery infrastructure
- ✅ Создать и опубликовать shared_lib
- ✅ Настроить мониторинг (Flower, Prometheus, Grafana)

#### Этап 2: Core Service (Недели 2-3)
- ✅ Развернуть Core Service параллельно с Auth/User/Request
- ✅ Перенаправить 10% трафика на Core Service
- ✅ Мониторинг и исправление issues
- ✅ Постепенное увеличение трафика до 100%
- ✅ Отключение старых Auth/User/Request сервисов

#### Этап 3: Operations Service (Недели 4-5)
- ✅ Объединить Shift + AI Services
- ✅ Миграция background jobs на Celery
- ✅ Тестирование ML workers

#### Этап 4: Communication Hub (Недели 6-7)
- ✅ Объединить Bot Gateway + Notification Service
- ✅ Настроить priority queues
- ✅ Миграция уведомлений на async

#### Этап 5: Оптимизация (Недели 8-9)
- ✅ Media Service async processing
- ✅ Analytics batch jobs на Celery Beat
- ✅ Отключение APScheduler

#### Этап 6: Frontend Deployment (Неделя 10)
- ✅ Развернуть WebApp (React/Vue SPA)
- ✅ Настроить WebSocket для real-time updates
- ✅ Развернуть Admin Panel
- ✅ Настроить PWA и push notifications

#### Этап 7: Финализация (Неделя 11)
- ✅ Полное тестирование всей системы
- ✅ Performance tuning
- ✅ Документация
- ✅ Отключение старых сервисов

---

## 📈 Ожидаемые результаты

### Performance Improvements

| Метрика | Текущее | Целевое | Улучшение |
|---------|---------|---------|-----------|
| **API Response Time (p95)** | 2000ms | 100ms | **20x** |
| **Telegram Upload** | 2-5s blocking | 50ms async | **100x** |
| **AI Assignment** | 5-10s blocking | 100ms queue | **50-100x** |
| **Notification Delivery** | 500ms sync | 10ms queue | **50x** |
| **Request Creation** | 1-2s | 50-100ms | **10-20x** |
| **Throughput** | 100 req/min | 5000 req/min | **50x** |

### Resource Optimization

| Ресурс | Текущее | После оптимизации | Экономия |
|--------|---------|-------------------|----------|
| **Backend Microservices** | 10 | 6 (+1 AI future) | -40% сейчас |
| **Frontend Applications** | 0 | 3 (WebApp, Bot, Admin) | +3 |
| **Docker Containers** | 10 | 9 (6 backend + 3 frontend) + workers | -10% overall |
| **Database Connections** | 200 | 100 | -50% |
| **Memory Usage** | ~15GB | ~10GB (8GB backend + 2GB frontend) | -33% |
| **CPU Cores** | 20 | 17 (15 backend + 2 frontend) | -15% |
| **Code Duplication** | 7,600 lines | 0 | -100% |
| **AI/ML Dependencies** | Встроены везде | Изолированы в отдельный сервис | 100% независимость |

### Operational Benefits

- **Maintenance Effort**: -50% (5 сервисов вместо 10)
- **Deployment Time**: -40% (меньше контейнеров)
- **MTTR**: -60% (auto-retry и DLQ)
- **Error Rate**: -70% (circuit breakers)
- **Development Velocity**: +40% (shared library)

---

## 🚦 Риски и митигация

### Технические риски

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| **RabbitMQ отказ** | Низкая | Высокое | Cluster mode + persistence |
| **Celery worker crash** | Средняя | Среднее | Auto-restart + monitoring |
| **Migration bugs** | Высокая | Среднее | Blue-green deployment |
| **Performance degradation** | Низкая | Высокое | Load testing + rollback |

### Организационные риски

| Риск | Митигация |
|------|-----------|
| **Недостаток экспертизы** | Документация + обучение |
| **Сопротивление изменениям** | Постепенная миграция |
| **Временные затраты** | Поэтапный план |

---

## 🎯 Quick Wins (Быстрые победы)

### Неделя 1
1. **Shared Library** → -7,600 строк дублированного кода
2. **RabbitMQ Setup** → готовность к async

### Неделя 2
3. **Media Service Async** → response time 2s → 50ms
4. **Notification Queues** → приоритизация сообщений

### Неделя 3
5. **Core Service Launch** → -3 микросервиса
6. **Celery Monitoring** → Flower dashboard

---

## 📚 Приложения

### A. Конфигурация RabbitMQ

```json
{
  "vhosts": [
    {"name": "/uk_management"}
  ],
  "users": [
    {
      "name": "uk_admin",
      "password": "secure_password",
      "tags": "administrator"
    }
  ],
  "permissions": [
    {
      "user": "uk_admin",
      "vhost": "/uk_management",
      "configure": ".*",
      "write": ".*",
      "read": ".*"
    }
  ],
  "exchanges": [
    {"name": "core.events", "vhost": "/uk_management", "type": "topic"},
    {"name": "ops.tasks", "vhost": "/uk_management", "type": "direct"},
    {"name": "comm.messages", "vhost": "/uk_management", "type": "topic"},
    {"name": "media.process", "vhost": "/uk_management", "type": "direct"},
    {"name": "analytics.batch", "vhost": "/uk_management", "type": "fanout"}
  ],
  "queues": [
    {"name": "core.tasks", "vhost": "/uk_management", "durable": true},
    {"name": "ops.compute", "vhost": "/uk_management", "durable": true},
    {"name": "comm.urgent", "vhost": "/uk_management", "durable": true, "arguments": {"x-priority": 10}},
    {"name": "comm.regular", "vhost": "/uk_management", "durable": true, "arguments": {"x-priority": 5}},
    {"name": "comm.batch", "vhost": "/uk_management", "durable": true, "arguments": {"x-priority": 1}},
    {"name": "media.upload", "vhost": "/uk_management", "durable": true},
    {"name": "analytics.batch", "vhost": "/uk_management", "durable": true}
  ]
}
```

### B. Celery Worker Configuration

```python
# celery_worker_config.py
from kombu import Queue, Exchange
from kombu.common import Broadcast

# Task routing
task_routes = {
    'core.*': {'queue': 'core.tasks'},
    'ops.ml.*': {'queue': 'ops.compute'},
    'ops.shift.*': {'queue': 'ops.scheduling'},
    'comm.notify.urgent.*': {'queue': 'comm.urgent'},
    'comm.notify.regular.*': {'queue': 'comm.regular'},
    'comm.notify.batch.*': {'queue': 'comm.batch'},
    'media.*': {'queue': 'media.upload'},
    'analytics.*': {'queue': 'analytics.batch'},
}

# Queue configuration
task_queues = (
    Queue('core.tasks', Exchange('core', type='direct'), routing_key='core.#'),
    Queue('ops.compute', Exchange('ops', type='topic'), routing_key='ops.ml.#'),
    Queue('ops.scheduling', Exchange('ops', type='topic'), routing_key='ops.shift.#'),
    Queue('comm.urgent', Exchange('comm', type='topic'), routing_key='comm.urgent.#', priority=10),
    Queue('comm.regular', Exchange('comm', type='topic'), routing_key='comm.regular.#', priority=5),
    Queue('comm.batch', Exchange('comm', type='topic'), routing_key='comm.batch.#', priority=1),
    Queue('media.upload', Exchange('media', type='direct'), routing_key='media.#'),
    Queue('analytics.batch', Exchange('analytics', type='fanout')),
)

# Worker configuration
worker_config = {
    'core-worker': {
        'queues': ['core.tasks'],
        'concurrency': 4,
        'prefetch': 1,
        'max_tasks_per_child': 1000
    },
    'ops-ml-worker': {
        'queues': ['ops.compute'],
        'concurrency': 2,
        'prefetch': 1,
        'max_tasks_per_child': 100,
        'time_limit': 300
    },
    'comm-worker': {
        'queues': ['comm.urgent', 'comm.regular', 'comm.batch'],
        'concurrency': 10,
        'prefetch': 4,
        'max_tasks_per_child': 5000
    },
    'media-worker': {
        'queues': ['media.upload', 'media.process'],
        'concurrency': 3,
        'prefetch': 1,
        'max_tasks_per_child': 500
    },
    'analytics-worker': {
        'queues': ['analytics.batch'],
        'concurrency': 2,
        'prefetch': 1,
        'max_tasks_per_child': 100
    }
}
```

---

## 🎯 Преимущества изоляции AI/ML Service

### Независимая разработка
- **Нет блокировок**: Operations Service работает с базовыми алгоритмами
- **Graceful degradation**: Автоматический fallback при недоступности AI
- **Отдельная команда**: ML инженеры работают независимо
- **Собственный релизный цикл**: Деплой без влияния на core систему

### Гибкая архитектура
```python
# Operations Service - всегда работает
if ai_service.is_available():
    result = ai_service.optimize()  # Используем AI когда доступен
else:
    result = basic_assignment()     # Fallback к простым правилам

# AI Service можно:
# - Развернуть позже
# - Отключить для экономии
# - Масштабировать независимо
# - Использовать GPU инстансы
```

### Экономия ресурсов
- **MVP без AI**: -4GB RAM, -4 CPU cores
- **Pay-as-you-grow**: AI только когда нужен
- **Selective deployment**: AI только в production, не в dev/test

## 📝 Заключение

План упрощения архитектуры UK Management Bot предлагает:

### Финальная архитектура: 7 backend + 3 frontend сервисов

**Backend Services:**
1. **Core Service** - auth, users, requests, building assets (консолидация 3→1 + модуль)
   - 📍 **Building Assets Module**: централизованный справочник недвижимости
   - 🗺️ **PostGIS геофункциональность**: оптимизация маршрутов исполнителей
   - 🏢 **Иерархия объектов**: Complex → Building → Entrance → Floor → Apartment
   - ⚡ **Производительность**: геопоиск < 50ms благодаря spatial индексам
2. **Operations Service** - shifts, scheduling, basic assignments
3. **Communication Hub** - notifications OUT, bot, WebSocket
4. **Media Storage** - files, processing, CDN
5. **Analytics Service** - metrics, KPIs, reports (batch processing)
6. **Integration Hub** - external APIs IN, caching (real-time)
7. **AI/ML Service [FUTURE]** - ML models, optimization (опционально)

**Frontend Applications:**
1. **WebApp** - React/Vue SPA с PWA
2. **Telegram Bot** - интегрирован в Communication Hub
3. **Admin Panel** - мониторинг и управление

### Ключевые архитектурные решения:

#### Building Assets Module
- **Размещение в Core Service** обоснованно:
  - Тесная связь с Users и Requests (foreign keys в одной БД)
  - Отсутствие сетевых задержек при JOIN операциях
  - Единая транзакционность для критичных операций
- **Функциональность**:
  - Полная иерархия объектов недвижимости
  - Геокодирование и reverse-геокодирование
  - Оптимизация маршрутов через геоданные
  - Интеграция с Building Directory API через Integration Hub

#### Разделение сервисов
- **Analytics и Integration разделены** из-за противоположных паттернов нагрузки:
  - Analytics: read-heavy (90%), batch processing
  - Integration: write-heavy (60%), real-time processing
- **AI/ML изолирован** для независимой разработки и развертывания
- **RabbitMQ + Celery** для всей асинхронной обработки
- **Shared Library** устраняет 7,600 строк дублированного кода

### Результаты:
- **Микросервисы**: 10 → 6 активных (-40%)
- **Response time**: 2s → 100ms (20x faster)
- **Codebase**: -7,600 строк дублей (-25%)
- **Maintenance**: -40% усилий
- **Геоданные**: единая точка истины для всех адресов

### Timeline:
- **Недели 1-11**: Основная миграция включая Building Assets Module
- **Неделя 12+**: AI/ML Service при готовности

Реализация займет **11-12 недель** с минимальными рисками для production.

---

**Документ подготовлен**: 8 октября 2025
**Версия**: 1.1.0 (интегрирован Building Assets Module)
**Статус**: Готов к реализации
**Следующий шаг**: Утверждение и начало Фазы 1 (Инфраструктура)