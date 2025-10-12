# 🚀 SPRINT 19-22: Integration Service + Bot Gateway + Telegram WebApp
## Detailed Implementation Plan

**Created**: 6 октября 2025
**Status**: 📋 READY TO START
**Timeline**: 6 недель (3 недели Sprint 19-20 + 3 недели Sprint 21-22)
**Progress**: 0/58 задач завершено (0%)

---

## 📊 EXECUTIVE SUMMARY

### Цель спринтов
Завершить миграцию монолитного UK Management Bot в микросервисную архитектуру путем создания:
1. **Integration Service** - централизованный адаптер внешних API (Google Sheets, геокодинг, и т.д.)
2. **Bot Gateway Service** - Telegram Bot интерфейс на базе Aiogram 3.x
3. **Telegram WebApp** - современный мини-апп интерфейс с платежами и расширенными функциями

### Ключевые метрики успеха
- ✅ Все внешние API интеграции работают через Integration Service
- ✅ Bot Gateway полностью заменяет монолитный бот
- ✅ Telegram WebApp функционирует с авторизацией и платежами
- ✅ Load testing пройден (5000+ concurrent users)
- ✅ Монолит полностью отключен
- ✅ Zero-downtime deployment готов

### Архитектурный контекст
```
Текущее состояние (78% миграции):
✅ Infrastructure (Sprint 0)
✅ Service Templates (Sprint 1-2)
✅ Notification Service (Sprint 3-4)
✅ Auth + User Services (Sprint 5-7)
✅ Request Service (Sprint 8-9)
⚠️ AI Services (Sprint 10-13) - Stage 1 only
✅ Shift Planning Service (Sprint 14-15)
✅ Analytics Service (Sprint 16-18)
🔄 Integration + Bot Gateway (Sprint 19-22) ← МЫ ЗДЕСЬ
```

## 🔗 DEPENDENCY ANALYSIS

### Диаграмма зависимостей между компонентами
```mermaid
graph TD
    subgraph "Week 1: Integration Service"
        A1[Integration Architecture] --> A2[Google Sheets Adapter]
        A1 --> A3[Geocoding Adapter]
        A2 --> A4[Integration Infrastructure]
        A3 --> A4
        A4 --> A5[Integration Testing]
    end
    
    subgraph "Week 2: Bot Gateway"
        B1[Bot Gateway Architecture] --> B2[Aiogram 3.x Setup]
        B2 --> B3[FSM State Migration]
        B3 --> B4[Request Handlers]
        B4 --> B5[Webhook/Polling Config]
    end
    
    subgraph "Week 3: WebApp"
        C1[WebApp Authentication] --> C2[WebApp Frontend]
        C2 --> C3[Payment Integration]
        C3 --> C4[Location/Camera Features]
    end
    
    subgraph "Week 4-6: Advanced Features"
        D1[API Versioning] --> D2[Circuit Breakers]
        D2 --> D3[Distributed Tracing]
        D3 --> D4[Performance Optimization]
        D4 --> D5[Monolith Cleanup]
    end
    
    A5 --> B1
    B5 --> C1
    C4 --> D1
    D5 --> E1[Production Launch]
```

### Критические зависимости
- **Integration Service** → **Bot Gateway** (внешние API нужны для геокодинга)
- **Bot Gateway** → **WebApp** (аутентификация через Bot Gateway)
- **All Services** → **Testing** (все сервисы должны быть протестированы)
- **Testing** → **Production Deployment** (без тестов нельзя деплоить)

## 🎯 TASK PRIORITIZATION

### P0 (Критические - Блокеры)
1. **Integration Service Foundation** - Без него не работают внешние API
2. **Bot Gateway Core** - Основной интерфейс пользователей
3. **Authentication & Security** - Безопасность системы
4. **Data Migration Verification** - Проверка целостности данных

### P1 (Высокие - Ключевые функции)
5. **FSM State Migration** - Функциональность бота
6. **WebApp Basic Features** - Новый интерфейс
7. **Testing Framework** - Качество системы
8. **Performance Optimization** - Производительность

### P2 (Средние - Улучшения)
9. **Advanced Features** - Дополнительные возможности
10. **Documentation** - Поддержка и развитие
11. **Monitoring Setup** - Наблюдаемость

## 👥 RESOURCE ANALYSIS

### Команда
```yaml
Backend Developers:
  - Senior Developer (Integration Service): 6 недель, 40 часов/неделя
  - Senior Developer (Bot Gateway): 6 недель, 40 часов/неделя
  
Frontend Developer:
  - WebApp Developer: 4 недели, 30 часов/неделя
  
DevOps Engineer:
  - Infrastructure & Deployment: 6 недель, 20 часов/неделя
  
QA Engineer:
  - Testing & Quality Assurance: 6 недель, 25 часов/неделя
  
Total Team Size: 5 человек
Total Effort: 1,410 часов (35 недель-человек)
```

### Инфраструктура
```yaml
Development Environment:
  - Docker containers: 8 сервисов
  - Databases: 2 PostgreSQL + 1 Redis
  - External APIs: Google Sheets, Maps API
  
Staging Environment:
  - Production-like setup
  - Load testing tools
  - Monitoring stack
  
Production Environment:
  - High availability setup
  - SSL certificates
  - Backup systems
  - Monitoring & alerting
```

## 📈 MILESTONES & CHECKPOINTS

### Веха 1: Integration Service Ready (Конец недели 1)
**Критерии готовности:**
- ✅ Integration Service deployed и healthy
- ✅ Google Sheets adapter работает
- ✅ Geocoding adapter функционирует
- ✅ Health checks проходят
- ✅ Unit tests покрывают 80%+ кода

**Проверка:** Smoke test всех адаптеров

### Веха 2: Bot Gateway Functional (Конец недели 2)
**Критерии готовности:**
- ✅ Bot Gateway запускается без ошибок
- ✅ 50% FSM состояний мигрированы
- ✅ Основные команды работают (/start, /help)
- ✅ Authentication middleware функционирует
- ✅ Webhook/polling настроены

**Проверка:** End-to-end тест создания заявки через бот

### Веха 3: WebApp Operational (Конец недели 3)
**Критерии готовности:**
- ✅ WebApp аутентификация работает
- ✅ Основные страницы загружаются
- ✅ Payment integration функционирует
- ✅ Location/Camera features работают
- ✅ Mobile-responsive дизайн

**Проверка:** Полный user journey через WebApp

### Веха 4: Advanced Features Complete (Конец недели 4)
**Критерии готовности:**
- ✅ API versioning реализован
- ✅ Circuit breakers защищают все сервисы
- ✅ Distributed tracing работает
- ✅ Performance targets достигнуты
- ✅ Load testing пройден (1000+ users)

**Проверка:** Load test и performance benchmarks

### Веха 5: Production Ready (Конец недели 5)
**Критерии готовности:**
- ✅ All services healthy в staging
- ✅ Data migration verified (zero data loss)
- ✅ Rollback procedures tested
- ✅ Documentation complete
- ✅ Team trained на новые процессы

**Проверка:** Production smoke tests

### Веха 6: Migration Complete (Конец недели 6)
**Критерии готовности:**
- ✅ 100% traffic на microservices
- ✅ Monolith decommissioned
- ✅ Zero downtime achieved
- ✅ All metrics green
- ✅ Post-migration monitoring active

**Проверка:** 24-hour stability test

## 🧪 TESTING STRATEGY

### Unit Testing
```yaml
Coverage Targets:
  - Integration Service: 80%+
  - Bot Gateway: 75%+
  - WebApp Components: 70%+

Test Types:
  - Service layer tests
  - Adapter tests
  - Handler tests
  - Component tests

Tools:
  - pytest (Python)
  - Jest (TypeScript)
  - Vue Test Utils (Vue.js)
```

### Integration Testing
```yaml
Test Scenarios:
  - Service-to-service communication
  - Database operations
  - External API integrations
  - Authentication flows

Tools:
  - pytest-asyncio
  - Testcontainers
  - Mock services
```

### End-to-End Testing
```yaml
User Journeys:
  - Request creation via Bot
  - Request creation via WebApp
  - Payment processing
  - Admin operations

Tools:
  - Playwright
  - Custom test framework
  - Telegram Bot testing
```

### Performance Testing
```yaml
Load Tests:
  - 1000 concurrent users
  - 5000 requests/minute
  - Response time < 200ms (p95)
  - Error rate < 0.1%

Tools:
  - Locust
  - k6
  - Custom load generators
```

### Security Testing
```yaml
Security Checks:
  - Authentication bypass attempts
  - Authorization violations
  - SQL injection tests
  - XSS vulnerability scans
  - API security testing

Tools:
  - OWASP ZAP
  - Custom security tests
  - Penetration testing
```

## 📢 COMMUNICATION PLAN

### Stakeholder Communication
```yaml
Daily Updates:
  - Team standups (15 min)
  - Progress reports в Slack
  - Issue tracking в Jira

Weekly Reports:
  - Milestone progress
  - Risk assessment
  - Resource utilization
  - Next week priorities

Stakeholder Meetings:
  - Sprint planning (2 hours)
  - Mid-sprint review (1 hour)
  - Sprint retrospective (1 hour)
  - Demo sessions (30 min)
```

### Escalation Procedures
```yaml
Level 1 (Team Lead):
  - Technical blockers
  - Resource conflicts
  - Timeline delays < 1 day

Level 2 (Project Manager):
  - Timeline delays > 1 day
  - Scope changes
  - External dependencies

Level 3 (Engineering Director):
  - Critical system failures
  - Security incidents
  - Major scope changes
```

### Documentation Updates
```yaml
Technical Documentation:
  - API documentation (Swagger)
  - Architecture diagrams
  - Deployment guides
  - Troubleshooting guides

User Documentation:
  - User guides
  - Admin manuals
  - Training materials
  - FAQ updates
```

---

## 🎯 SPRINT 19-20: INTEGRATION SERVICE & BOT GATEWAY (Недели 1-3)

### WEEK 1: Integration Service Foundation

#### **ДЕНЬ 1-2: Integration Service Архитектура и Структура**

**Задача 1.1: Проектирование архитектуры Integration Service** (4 часа)
```yaml
Deliverables:
  - Архитектурная диаграмма Integration Service
  - API контракты для внешних интеграций
  - Event schema для integration events
  - Database schema (integration_db)

Database Tables (5 таблиц):
  1. external_services:
     - id, name, type, base_url
     - api_key_encrypted, rate_limit_config
     - health_status, last_check_at
     - created_at, updated_at

  2. integration_logs:
     - id, service_id, request_type
     - request_payload, response_payload
     - status, error_message
     - duration_ms, created_at

  3. webhook_configs:
     - id, service_id, webhook_url
     - event_types[], secret_token
     - retry_config, is_active
     - created_at, updated_at

  4. api_rate_limits:
     - id, service_id, endpoint
     - requests_per_minute, requests_per_hour
     - current_count, reset_at

  5. integration_cache:
     - id, cache_key, cache_value
     - service_id, ttl_seconds
     - created_at, expires_at

Event Types:
  - integration.service.registered
  - integration.request.sent
  - integration.request.completed
  - integration.request.failed
  - integration.webhook.received
  - integration.rate_limit.exceeded

Критерии готовности:
  ✅ Архитектурный документ создан
  ✅ Database migrations готовы
  ✅ Event contracts определены
  ✅ API specifications написаны (OpenAPI 3.0)
```

**Задача 1.2: Создание базовой структуры Integration Service** (4 часа)
```bash
microservices/integration_service/
├── app/
│   ├── main.py                    # FastAPI приложение
│   ├── models/                    # SQLAlchemy модели (5 таблиц)
│   │   ├── external_service.py
│   │   ├── integration_log.py
│   │   ├── webhook_config.py
│   │   └── rate_limit.py
│   ├── services/                  # Бизнес-логика
│   │   ├── integration_service.py  # Core integration logic
│   │   ├── webhook_service.py      # Webhook management
│   │   ├── rate_limiter.py         # Rate limiting
│   │   └── retry_service.py        # Retry logic
│   ├── adapters/                  # External API adapters
│   │   ├── base_adapter.py        # Abstract base
│   │   ├── google_sheets_adapter.py
│   │   ├── geocoding_adapter.py
│   │   └── payment_adapter.py
│   ├── api/v1/                    # API endpoints
│   │   ├── integrations.py        # Integration management
│   │   ├── webhooks.py            # Webhook endpoints
│   │   └── health.py              # Health checks
│   ├── core/
│   │   ├── config.py              # Configuration
│   │   ├── database.py            # Database setup
│   │   └── events.py              # Event publisher
│   └── middleware/
│       ├── auth.py                # JWT validation
│       └── logging.py             # Request logging
├── tests/
│   ├── test_adapters.py
│   ├── test_webhooks.py
│   └── test_rate_limiting.py
├── alembic/                       # Database migrations
├── Dockerfile
├── requirements.txt
├── .env.example
└── README.md

Ключевые файлы:
1. app/main.py - FastAPI app с middleware
2. app/services/integration_service.py - Core integration orchestration
3. app/adapters/base_adapter.py - Base class для всех адаптеров
4. app/api/v1/integrations.py - REST API endpoints
```

#### **ДЕНЬ 3-4: Google Sheets Integration Migration**

**Задача 1.3: Google Sheets Adapter Implementation** (6 часов)
```python
# app/adapters/google_sheets_adapter.py
from typing import List, Dict, Any
from app.adapters.base_adapter import BaseAdapter

class GoogleSheetsAdapter(BaseAdapter):
    """
    Adapter для Google Sheets API интеграции.

    Функциональность:
    - Read/Write операции с таблицами
    - Batch operations для производительности
    - Автоматический retry при rate limits
    - Кэширование часто запрашиваемых данных
    """

    async def read_range(
        self,
        spreadsheet_id: str,
        range_name: str
    ) -> List[List[str]]:
        """Чтение диапазона ячеек из таблицы"""
        pass

    async def write_range(
        self,
        spreadsheet_id: str,
        range_name: str,
        values: List[List[str]]
    ) -> Dict[str, Any]:
        """Запись данных в таблицу"""
        pass

    async def append_rows(
        self,
        spreadsheet_id: str,
        range_name: str,
        values: List[List[str]]
    ) -> Dict[str, Any]:
        """Добавление новых строк в конец таблицы"""
        pass

    async def batch_update(
        self,
        spreadsheet_id: str,
        requests: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Batch операции для множественных обновлений"""
        pass

Миграция из монолита:
  Источник: uk_management_bot/integrations/google_sheets.py

  Функции для миграции:
    ✅ get_addresses() → read_range()
    ✅ update_request_status() → write_range()
    ✅ export_analytics() → batch_update()
    ✅ sync_employee_list() → append_rows()

API Endpoints:
  POST /api/v1/integrations/google-sheets/read
  POST /api/v1/integrations/google-sheets/write
  POST /api/v1/integrations/google-sheets/append
  POST /api/v1/integrations/google-sheets/batch-update

Rate Limiting:
  - 100 requests per 100 seconds (Google API limit)
  - Automatic exponential backoff
  - Request queuing for burst traffic
```

**Задача 1.4: Geocoding Integration** (4 часов)
```python
# app/adapters/geocoding_adapter.py
class GeocodingAdapter(BaseAdapter):
    """
    Адаптер для геокодинг сервисов (Google Maps / Yandex Maps).

    Features:
    - Преобразование адресов в координаты
    - Reverse geocoding (координаты → адрес)
    - Расчет расстояний между точками
    - Оптимизация маршрутов
    - Multi-provider fallback (Google → Yandex)
    """

    async def geocode_address(
        self,
        address: str,
        provider: str = "google"
    ) -> Dict[str, Any]:
        """Получение координат по адресу"""
        return {
            "latitude": 41.311081,
            "longitude": 69.240562,
            "formatted_address": "Tashkent, Uzbekistan",
            "confidence": 0.95
        }

    async def reverse_geocode(
        self,
        latitude: float,
        longitude: float
    ) -> Dict[str, Any]:
        """Получение адреса по координатам"""
        pass

    async def calculate_distance(
        self,
        origin: Dict[str, float],
        destination: Dict[str, float]
    ) -> Dict[str, Any]:
        """Расчет расстояния между двумя точками"""
        return {
            "distance_meters": 5420,
            "distance_km": 5.42,
            "duration_seconds": 960,
            "duration_minutes": 16
        }

    async def optimize_route(
        self,
        waypoints: List[Dict[str, float]]
    ) -> Dict[str, Any]:
        """Оптимизация маршрута через множество точек"""
        pass

Integration Config:
  providers:
    - name: google_maps
      api_key: env:GOOGLE_MAPS_API_KEY
      priority: 1
      rate_limit: 1000/day

    - name: yandex_maps
      api_key: env:YANDEX_MAPS_API_KEY
      priority: 2
      rate_limit: 25000/day

Caching Strategy:
  - Geocoding results: 30 days TTL
  - Distance calculations: 7 days TTL
  - Route optimizations: 1 day TTL
```

#### **ДЕНЬ 5: Integration Service Infrastructure**

**Задача 1.5: Docker & Production Setup** (4 часа)
```yaml
# docker-compose.yml addition
services:
  integration-service:
    build:
      context: ./integration_service
      dockerfile: Dockerfile
    container_name: integration-service
    restart: unless-stopped
    ports:
      - "8009:8009"
    environment:
      - DATABASE_URL=postgresql+asyncpg://integration_user:integration_pass@integration-db:5432/integration_db
      - REDIS_URL=redis://shared-redis:6379/9
      - AUTH_SERVICE_URL=http://auth-service:8001
      - GOOGLE_SHEETS_API_KEY=${GOOGLE_SHEETS_API_KEY}
      - GOOGLE_MAPS_API_KEY=${GOOGLE_MAPS_API_KEY}
      - YANDEX_MAPS_API_KEY=${YANDEX_MAPS_API_KEY}
    depends_on:
      integration-db:
        condition: service_healthy
      shared-redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8009/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - microservices

  integration-db:
    image: postgres:15-alpine
    container_name: integration-db
    restart: unless-stopped
    environment:
      - POSTGRES_USER=integration_user
      - POSTGRES_PASSWORD=integration_pass
      - POSTGRES_DB=integration_db
    volumes:
      - integration_db_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U integration_user -d integration_db"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - microservices

volumes:
  integration_db_data:

Health Endpoints:
  GET /health - Service health status
  GET /ready - Readiness check (DB + Redis + External APIs)
  GET /metrics - Prometheus metrics

Monitoring:
  - Request/response logging
  - External API latency tracking
  - Rate limit monitoring
  - Error rate alerting
```

**Задача 1.6: Integration Service Testing** (4 часов)
```python
# tests/test_google_sheets_adapter.py
import pytest
from app.adapters.google_sheets_adapter import GoogleSheetsAdapter

@pytest.mark.asyncio
async def test_read_range():
    """Test reading data from Google Sheets"""
    adapter = GoogleSheetsAdapter()
    result = await adapter.read_range(
        spreadsheet_id="test_sheet_id",
        range_name="Sheet1!A1:B10"
    )
    assert len(result) > 0
    assert isinstance(result[0], list)

@pytest.mark.asyncio
async def test_write_range():
    """Test writing data to Google Sheets"""
    adapter = GoogleSheetsAdapter()
    result = await adapter.write_range(
        spreadsheet_id="test_sheet_id",
        range_name="Sheet1!A1:B2",
        values=[["Name", "Value"], ["Test", "123"]]
    )
    assert result["updatedRows"] == 2

@pytest.mark.asyncio
async def test_rate_limiting():
    """Test rate limiting behavior"""
    adapter = GoogleSheetsAdapter()
    # Make 101 requests to trigger rate limit
    for i in range(101):
        try:
            await adapter.read_range("test", "A1:A1")
        except RateLimitExceeded:
            assert i == 100  # Should fail on 101st request
            break

Coverage Target: 80%+
Test Types: Unit, Integration, Performance
```

---

### WEEK 2: Bot Gateway Service Foundation

#### **ДЕНЬ 6-7: Bot Gateway Architecture & Structure**

**Задача 2.1: Bot Gateway Architecture Design** (6 часов)
```yaml
Architecture Components:
  1. Telegram Bot API Layer (Aiogram 3.x)
  2. Message Router (распределение по микросервисам)
  3. FSM State Manager (миграция из монолита)
  4. Session Manager (Redis-based)
  5. Middleware Stack (auth, logging, rate limiting)

Database Schema (bot_gateway_db):
  Tables (4):
    1. bot_sessions:
       - user_id, telegram_id, state_data
       - current_state, context_json
       - created_at, updated_at, expires_at

    2. bot_commands:
       - id, command, description
       - handler_service, is_active
       - required_roles[], created_at

    3. inline_keyboard_cache:
       - id, message_id, keyboard_data
       - user_id, created_at, expires_at

    4. bot_metrics:
       - id, metric_type, value
       - user_id, timestamp

Message Flow:
  User → Telegram → Bot Gateway → Auth Service (validate)
                                → User Service (get profile)
                                → Request Service (business logic)
                                → Response → User

FSM States to Migrate (50+ states):
  From: uk_management_bot/states/
  - RequestCreationStates (7 states)
  - ShiftManagementStates (12 states)
  - AdminStates (15 states)
  - ExecutorStates (10 states)
  - ApplicantStates (6 states)
```

**Задача 2.2: Aiogram 3.x Bot Setup** (8 часов)
```python
# app/main.py
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.client.default import DefaultBotProperties

async def create_bot_application():
    """
    Создание Bot Gateway приложения.

    Components:
    - Aiogram 3.x Bot instance
    - Dispatcher with Redis FSM storage
    - Middleware stack (auth, logging, rate limiting)
    - Router registration for all handlers
    - Webhook/polling support
    """

    # Bot initialization
    bot = Bot(
        token=settings.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML")
    )

    # FSM storage (Redis)
    storage = RedisStorage.from_url(settings.REDIS_URL)

    # Dispatcher
    dp = Dispatcher(storage=storage)

    # Middleware registration
    dp.message.middleware(AuthMiddleware())
    dp.message.middleware(LoggingMiddleware())
    dp.message.middleware(RateLimitMiddleware())

    # Router registration
    dp.include_router(request_router)
    dp.include_router(shift_router)
    dp.include_router(admin_router)
    dp.include_router(executor_router)

    return bot, dp

# Структура проекта:
microservices/bot_gateway/
├── app/
│   ├── main.py                    # Bot initialization
│   ├── routers/                   # Message handlers
│   │   ├── request_handlers.py    # Request management
│   │   ├── shift_handlers.py      # Shift management
│   │   ├── admin_handlers.py      # Admin functions
│   │   ├── executor_handlers.py   # Executor interface
│   │   └── common_handlers.py     # /start, /help, etc.
│   ├── states/                    # FSM states (migrated)
│   │   ├── request_states.py
│   │   ├── shift_states.py
│   │   └── admin_states.py
│   ├── keyboards/                 # Inline/Reply keyboards
│   │   ├── request_keyboards.py
│   │   ├── shift_keyboards.py
│   │   └── common_keyboards.py
│   ├── middleware/
│   │   ├── auth.py                # User authentication
│   │   ├── logging.py             # Request logging
│   │   └── rate_limit.py          # Flood control
│   ├── services/
│   │   ├── message_router.py      # Route to microservices
│   │   ├── session_manager.py     # User session management
│   │   └── file_proxy.py          # File upload/download
│   └── integrations/              # Service clients
│       ├── auth_client.py
│       ├── user_client.py
│       ├── request_client.py
│       └── media_client.py
├── Dockerfile
├── requirements.txt
└── README.md

Key Dependencies:
  - aiogram==3.13.1
  - aiohttp==3.10.5
  - redis==5.0.8
  - sqlalchemy[asyncio]==2.0.35
  - pydantic==2.9.2
```

#### **ДЕНЬ 8-9: FSM State Migration**

**Задача 2.3: Request Creation Flow Migration** (10 часов)
```python
# app/routers/request_handlers.py
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from app.states.request_states import RequestCreationStates
from app.keyboards.request_keyboards import get_request_category_keyboard
from app.integrations.request_client import RequestServiceClient

request_router = Router(name="request_router")

@request_router.message(Command("create_request"))
async def start_request_creation(message: Message, state: FSMContext):
    """
    Начало создания заявки.

    Flow:
    1. Validate user authentication (Auth Service)
    2. Get user profile (User Service)
    3. Check permissions
    4. Show category selection keyboard
    5. Set FSM state to waiting_for_category
    """
    # Authenticate user
    auth_client = AuthServiceClient()
    user_data = await auth_client.validate_telegram_user(message.from_user.id)

    if not user_data:
        await message.answer("⛔ Вы не авторизованы. Используйте /start")
        return

    # Get user profile
    user_client = UserServiceClient()
    profile = await user_client.get_profile(user_data["user_id"])

    # Show category keyboard
    keyboard = get_request_category_keyboard()
    await message.answer(
        "📝 Создание новой заявки\n\nВыберите категорию:",
        reply_markup=keyboard
    )

    # Set FSM state
    await state.set_state(RequestCreationStates.waiting_for_category)
    await state.update_data(user_id=user_data["user_id"])

@request_router.callback_query(
    F.data.startswith("category_"),
    RequestCreationStates.waiting_for_category
)
async def process_category_selection(
    callback: CallbackQuery,
    state: FSMContext
):
    """Process category selection and ask for address"""
    category = callback.data.replace("category_", "")

    await state.update_data(category=category)
    await state.set_state(RequestCreationStates.waiting_for_address)

    await callback.message.edit_text(
        f"✅ Категория: {category}\n\n📍 Введите адрес:"
    )

@request_router.message(RequestCreationStates.waiting_for_address)
async def process_address_input(message: Message, state: FSMContext):
    """
    Process address and geocode it.

    Integration with Integration Service:
    - Call geocoding adapter
    - Get coordinates
    - Validate address
    """
    address = message.text

    # Geocode address via Integration Service
    integration_client = IntegrationServiceClient()
    geocode_result = await integration_client.geocode_address(address)

    if not geocode_result["success"]:
        await message.answer(
            "⚠️ Не удалось определить адрес. Попробуйте еще раз."
        )
        return

    await state.update_data(
        address=address,
        latitude=geocode_result["latitude"],
        longitude=geocode_result["longitude"]
    )
    await state.set_state(RequestCreationStates.waiting_for_description)

    await message.answer("✅ Адрес принят\n\n📝 Опишите проблему:")

# Миграция всех FSM состояний из монолита:
States to Migrate (50+):
  ✅ RequestCreationStates (7 states)
  ✅ RequestManagementStates (5 states)
  ✅ ShiftStates (12 states)
  ✅ AdminStates (15 states)
  ✅ ExecutorStates (10 states)
  ✅ ApplicantStates (6 states)

Migration Checklist per State:
  ✅ Extract handler function from monolith
  ✅ Adapt to Aiogram 3.x syntax
  ✅ Replace direct DB calls with service API calls
  ✅ Update keyboard generation
  ✅ Test state transitions
  ✅ Add error handling
```

#### **ДЕНЬ 10: Webhook & Polling Support**

**Задача 2.4: Webhook/Polling Configuration** (6 часов)
```python
# app/webhook.py
from aiogram import Bot
from aiogram.types import Update
from fastapi import FastAPI, Request

app = FastAPI()

async def setup_webhook(bot: Bot):
    """
    Setup Telegram webhook for production.

    Webhook URL: https://yourdomain.com/webhook/bot

    Benefits:
    - Lower latency than polling
    - Efficient resource usage
    - Automatic HTTPS handling via Traefik
    """
    webhook_url = f"{settings.WEBHOOK_BASE_URL}/webhook/bot"

    await bot.set_webhook(
        url=webhook_url,
        secret_token=settings.WEBHOOK_SECRET_TOKEN,
        drop_pending_updates=True
    )

    logger.info(f"Webhook set to {webhook_url}")

@app.post("/webhook/bot")
async def webhook_handler(request: Request):
    """
    Handle incoming webhook updates from Telegram.

    Security:
    - Verify webhook secret token
    - Validate request signature
    - Rate limiting
    """
    # Verify secret token
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret_token != settings.WEBHOOK_SECRET_TOKEN:
        return {"error": "Invalid secret token"}

    # Process update
    update_dict = await request.json()
    update = Update(**update_dict)

    await dp.feed_update(bot, update)

    return {"ok": True}

# Polling mode for development
async def start_polling(bot: Bot, dp: Dispatcher):
    """
    Start bot in polling mode for development.

    Use when:
    - Local development
    - No public domain available
    - Testing changes
    """
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

# Configuration in settings
class Settings:
    MODE: str = "webhook"  # or "polling"
    WEBHOOK_BASE_URL: str = "https://your-domain.com"
    WEBHOOK_SECRET_TOKEN: str = "random-secret-token"
```

---

### WEEK 3: Telegram WebApp Integration

#### **ДЕНЬ 11-12: WebApp Authentication & Backend**

**Задача 3.1: Telegram WebApp Authentication** (8 часов)
```python
# app/api/v1/webapp.py
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import hashlib
import hmac
from urllib.parse import parse_qs

router = APIRouter(prefix="/api/v1/webapp", tags=["webapp"])

class WebAppInitData(BaseModel):
    """
    Telegram WebApp InitData structure.

    Fields from Telegram:
    - query_id: Unique query identifier
    - user: JSON user data
    - auth_date: Unix timestamp
    - hash: HMAC-SHA-256 signature
    """
    query_id: str
    user: str  # JSON string
    auth_date: int
    hash: str

def validate_webapp_data(init_data: str, bot_token: str) -> bool:
    """
    Validate Telegram WebApp InitData.

    Algorithm (Telegram official):
    1. Parse init_data string
    2. Create data_check_string (sorted params except hash)
    3. Create secret_key = HMAC-SHA-256(bot_token, "WebAppData")
    4. Create hash = HMAC-SHA-256(secret_key, data_check_string)
    5. Compare with provided hash

    Returns:
        True if valid, False otherwise
    """
    try:
        # Parse init_data
        params = parse_qs(init_data)
        received_hash = params.pop('hash', [None])[0]

        if not received_hash:
            return False

        # Create data_check_string
        data_check_string = '\n'.join(
            f"{k}={v[0]}" for k, v in sorted(params.items())
        )

        # Create secret_key
        secret_key = hmac.new(
            key=b"WebAppData",
            msg=bot_token.encode(),
            digestmod=hashlib.sha256
        ).digest()

        # Create hash
        calculated_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode(),
            digestmod=hashlib.sha256
        ).hexdigest()

        # Compare
        return calculated_hash == received_hash

    except Exception as e:
        logger.error(f"WebApp validation error: {e}")
        return False

@router.post("/auth")
async def authenticate_webapp(init_data: str):
    """
    Authenticate Telegram WebApp user.

    Process:
    1. Validate InitData signature
    2. Extract user information
    3. Get or create user in User Service
    4. Generate JWT token for WebApp
    5. Return token + user data
    """
    # Validate InitData
    if not validate_webapp_data(init_data, settings.TELEGRAM_BOT_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid InitData")

    # Parse user data
    params = parse_qs(init_data)
    user_data = json.loads(params['user'][0])

    telegram_id = user_data['id']
    username = user_data.get('username')
    first_name = user_data.get('first_name')

    # Get user from User Service
    user_client = UserServiceClient()
    user = await user_client.get_by_telegram_id(telegram_id)

    if not user:
        # Auto-register user
        user = await user_client.create_from_telegram(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name
        )

    # Generate JWT for WebApp
    auth_client = AuthServiceClient()
    token = await auth_client.create_webapp_token(
        user_id=user['id'],
        telegram_id=telegram_id
    )

    return {
        "success": True,
        "token": token,
        "user": user
    }

@router.get("/user/profile")
async def get_user_profile(
    current_user: dict = Depends(get_current_webapp_user)
):
    """
    Get user profile for WebApp.

    Protected endpoint requiring valid JWT.
    """
    user_client = UserServiceClient()
    profile = await user_client.get_full_profile(current_user['user_id'])

    return profile
```

**Задача 3.2: WebApp Frontend Scaffold** (10 часов)
```typescript
// bot_gateway/webapp/src/main.ts
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'

// Telegram WebApp SDK
import type { WebApp } from '@twa-dev/types'

declare global {
  interface Window {
    Telegram: {
      WebApp: WebApp
    }
  }
}

const app = createApp(App)
app.use(createPinia())
app.use(router)

// Initialize Telegram WebApp
const tg = window.Telegram.WebApp
tg.ready()
tg.expand()

// Set color scheme
if (tg.colorScheme === 'dark') {
  document.documentElement.classList.add('dark')
}

app.mount('#app')

// Project Structure:
webapp/
├── src/
│   ├── main.ts                    # App entry point
│   ├── App.vue                    # Root component
│   ├── router/
│   │   └── index.ts               # Vue Router config
│   ├── stores/                    # Pinia stores
│   │   ├── auth.ts                # Authentication state
│   │   ├── requests.ts            # Request management
│   │   └── user.ts                # User profile
│   ├── views/                     # Page components
│   │   ├── HomeView.vue           # Dashboard
│   │   ├── RequestsView.vue       # My requests
│   │   ├── CreateRequestView.vue  # Create request
│   │   ├── ShiftsView.vue         # My shifts
│   │   └── ProfileView.vue        # User profile
│   ├── components/                # Reusable components
│   │   ├── RequestCard.vue
│   │   ├── ShiftCard.vue
│   │   ├── CategorySelector.vue
│   │   └── MapPicker.vue
│   ├── services/                  # API services
│   │   ├── api.ts                 # Base API client
│   │   ├── auth.service.ts
│   │   ├── request.service.ts
│   │   └── user.service.ts
│   ├── utils/
│   │   ├── telegram.ts            # Telegram WebApp helpers
│   │   └── validation.ts
│   └── assets/
│       └── styles/
├── public/
│   └── index.html
├── package.json
├── vite.config.ts
├── tsconfig.json
└── tailwind.config.js

Key Features:
  ✅ Vue 3 + TypeScript
  ✅ Tailwind CSS (mobile-first)
  ✅ Telegram WebApp SDK integration
  ✅ Dark/Light theme support
  ✅ Responsive design
  ✅ PWA capabilities
```

#### **ДЕНЬ 13-15: WebApp Advanced Features**

**Задача 3.3: Telegram Payments Integration** (12 часов)
```typescript
// src/services/payment.service.ts
import { ref } from 'vue'

interface PaymentParams {
  title: string
  description: string
  amount: number  // in kopecks
  currency: string
  payload: string
}

class PaymentService {
  /**
   * Initiate Telegram payment.
   *
   * Supported providers:
   * - Telegram Stars (native)
   * - Stripe
   * - YooKassa (for Russia/CIS)
   * - Click/Payme (for Uzbekistan)
   */
  async initiatePayment(params: PaymentParams) {
    const tg = window.Telegram.WebApp

    // Create invoice via backend
    const response = await api.post('/api/v1/payments/create-invoice', {
      title: params.title,
      description: params.description,
      amount: params.amount,
      currency: params.currency,
      payload: params.payload
    })

    const { invoice_link } = response.data

    // Open Telegram payment dialog
    tg.openInvoice(invoice_link, (status) => {
      if (status === 'paid') {
        this.handlePaymentSuccess(params.payload)
      } else if (status === 'cancelled') {
        this.handlePaymentCancelled()
      } else {
        this.handlePaymentFailed()
      }
    })
  }

  async handlePaymentSuccess(payload: string) {
    // Notify backend about successful payment
    await api.post('/api/v1/payments/confirm', { payload })

    // Show success message
    const tg = window.Telegram.WebApp
    tg.showAlert('✅ Оплата прошла успешно!')
  }
}

// Example usage in component:
// <script setup lang="ts">
import { usePaymentService } from '@/services/payment.service'

const paymentService = usePaymentService()

async function payForRequest(requestId: string) {
  await paymentService.initiatePayment({
    title: 'Оплата заявки #250918-001',
    description: 'Ремонт электропроводки',
    amount: 50000,  // 500.00 UZS
    currency: 'UZS',
    payload: `request:${requestId}`
  })
}
// </script>
```

**Задача 3.4: Location & Camera Integration** (8 часов)
```typescript
// src/components/LocationPicker.vue
<template>
  <div class="location-picker">
    <button @click="requestLocation" class="btn-primary">
      📍 Отправить геолокацию
    </button>

    <div v-if="location" class="location-preview">
      <p>Координаты: {{ location.latitude }}, {{ location.longitude }}</p>
      <div id="map" style="height: 300px"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const location = ref<{latitude: number, longitude: number} | null>(null)

function requestLocation() {
  const tg = window.Telegram.WebApp

  // Request location from Telegram
  tg.requestLocation((result) => {
    if (result) {
      location.value = {
        latitude: result.latitude,
        longitude: result.longitude
      }

      // Reverse geocode
      reverseGeocode(result.latitude, result.longitude)
    }
  })
}

async function reverseGeocode(lat: number, lon: number) {
  const response = await api.post('/api/v1/integrations/geocoding/reverse', {
    latitude: lat,
    longitude: lon
  })

  const address = response.data.formatted_address
  console.log('Address:', address)
}
</script>

// Camera/Photo Upload
// src/components/PhotoUpload.vue
<script setup lang="ts">
async function uploadPhoto() {
  const tg = window.Telegram.WebApp

  // Request write access
  tg.requestWriteAccess((granted) => {
    if (granted) {
      // Open camera/gallery
      tg.showPopup({
        title: 'Загрузить фото',
        message: 'Выберите источник',
        buttons: [
          { id: 'camera', type: 'default', text: 'Камера' },
          { id: 'gallery', type: 'default', text: 'Галерея' }
        ]
      }, async (buttonId) => {
        if (buttonId === 'camera') {
          const photo = await capturePhoto()
          await uploadToServer(photo)
        }
      })
    }
  })
}

async function uploadToServer(photoData: Blob) {
  const formData = new FormData()
  formData.append('file', photoData, 'photo.jpg')

  const response = await api.post('/api/v1/media/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })

  return response.data.file_id
}
</script>
```

---

## 🎯 SPRINT 21-22: ADVANCED FEATURES & MONOLITH CLEANUP (Недели 4-6)

### WEEK 4: Advanced Gateway Features

#### **ДЕНЬ 16-17: API Versioning & Circuit Breakers**

**Задача 4.1: API Versioning Implementation** (6 часов)
```python
# bot_gateway/app/api/versioning.py
from fastapi import APIRouter, Request
from typing import Optional

def create_versioned_router(version: str) -> APIRouter:
    """
    Create API router with version prefix.

    Versions:
    - v1: Current stable API
    - v2: New features with breaking changes

    URL format: /api/v1/requests, /api/v2/requests
    """
    return APIRouter(prefix=f"/api/{version}")

# Version detection from headers
def get_api_version(request: Request) -> str:
    """
    Detect API version from:
    1. Accept header: Accept: application/vnd.api+json; version=1
    2. Custom header: X-API-Version: 1
    3. URL path: /api/v1/
    4. Default: v1
    """
    # Check custom header
    version = request.headers.get("X-API-Version")
    if version:
        return f"v{version}"

    # Check Accept header
    accept = request.headers.get("Accept", "")
    if "version=" in accept:
        version = accept.split("version=")[1].split(";")[0]
        return f"v{version}"

    # Default
    return "v1"

# Support multiple versions simultaneously
app.include_router(v1_router, prefix="/api/v1")
app.include_router(v2_router, prefix="/api/v2")

# Deprecation warnings
@app.middleware("http")
async def deprecation_middleware(request: Request, call_next):
    """Add deprecation warnings for old API versions"""
    if "/api/v1" in request.url.path:
        response = await call_next(request)
        response.headers["X-API-Deprecated"] = "true"
        response.headers["X-API-Sunset"] = "2026-01-01"
        return response
    return await call_next(request)
```

**Задача 4.2: Circuit Breaker Pattern** (8 часов)
```python
# shared/middleware/circuit_breaker.py
from enum import Enum
from datetime import datetime, timedelta
import asyncio

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered

class CircuitBreaker:
    """
    Circuit breaker для защиты от каскадных отказов.

    States:
    - CLOSED: Normal operation, все запросы проходят
    - OPEN: Service failing, все запросы отклоняются
    - HALF_OPEN: Testing recovery, пропускаем limited requests

    Thresholds:
    - failure_threshold: 5 failures → OPEN
    - success_threshold: 2 successes → CLOSED
    - timeout: 60 seconds before HALF_OPEN
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout: int = 60
    ):
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout = timeout

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None

    async def call(self, func, *args, **kwargs):
        """
        Execute function with circuit breaker protection.

        Returns:
            Function result if circuit is closed

        Raises:
            CircuitBreakerOpen: If circuit is open
        """
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
            else:
                raise CircuitBreakerOpen("Circuit breaker is OPEN")

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result

        except Exception as e:
            self._on_failure()
            raise e

    def _on_success(self):
        """Handle successful call"""
        self.failure_count = 0

        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self.state = CircuitState.CLOSED
                self.success_count = 0

    def _on_failure(self):
        """Handle failed call"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

    def _should_attempt_reset(self) -> bool:
        """Check if enough time passed to try HALF_OPEN"""
        if self.last_failure_time is None:
            return False

        elapsed = datetime.now() - self.last_failure_time
        return elapsed > timedelta(seconds=self.timeout)

# Usage example:
request_service_breaker = CircuitBreaker(
    failure_threshold=5,
    success_threshold=2,
    timeout=60
)

async def call_request_service():
    try:
        result = await request_service_breaker.call(
            request_client.create_request,
            data=request_data
        )
        return result
    except CircuitBreakerOpen:
        # Fallback: return cached data or error
        return {"error": "Request service temporarily unavailable"}
```

#### **ДЕНЬ 18-19: Distributed Tracing & Advanced Rate Limiting**

**Задача 4.3: Jaeger Distributed Tracing** (6 часов)
```python
# shared/middleware/tracing.py
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor

def setup_tracing(app: FastAPI, service_name: str):
    """
    Setup Jaeger distributed tracing.

    Features:
    - Automatic span creation for HTTP requests
    - Service-to-service trace propagation
    - Custom span attributes
    - Error tracking

    Jaeger UI: http://localhost:16686
    """
    # Create Jaeger exporter
    jaeger_exporter = JaegerExporter(
        agent_host_name="jaeger",
        agent_port=6831,
    )

    # Setup tracer provider
    trace.set_tracer_provider(TracerProvider())
    trace.get_tracer_provider().add_span_processor(
        BatchSpanProcessor(jaeger_exporter)
    )

    # Instrument FastAPI
    FastAPIInstrumentor.instrument_app(app)

    # Instrument aiohttp (for service-to-service calls)
    AioHttpClientInstrumentor().instrument()

    return trace.get_tracer(service_name)

# Usage in handlers:
tracer = trace.get_tracer(__name__)

@router.post("/requests")
async def create_request(request_data: RequestCreate):
    with tracer.start_as_current_span("create_request") as span:
        # Add custom attributes
        span.set_attribute("request.category", request_data.category)
        span.set_attribute("user.id", current_user.id)

        # Call request service (automatically traced)
        result = await request_client.create(request_data)

        span.set_attribute("request.number", result.request_number)

        return result

# Service-to-service trace propagation
async def call_user_service(user_id: str):
    """Traces automatically propagate via HTTP headers"""
    async with aiohttp.ClientSession() as session:
        # OpenTelemetry automatically injects trace headers
        async with session.get(
            f"http://user-service:8002/api/v1/users/{user_id}"
        ) as response:
            return await response.json()

# View traces:
# 1. Open Jaeger UI: http://localhost:16686
# 2. Select service: bot-gateway
# 3. Click "Find Traces"
# 4. See full request flow across all services
```

**Задача 4.4: Advanced Rate Limiting** (6 часов)
```python
# shared/middleware/rate_limit_advanced.py
from typing import Optional
import redis.asyncio as redis
from fastapi import HTTPException

class AdvancedRateLimiter:
    """
    Advanced rate limiting with multiple strategies.

    Strategies:
    1. Fixed Window: 100 requests per minute
    2. Sliding Window: More accurate than fixed
    3. Token Bucket: Allows bursts
    4. Leaky Bucket: Smooth rate

    Per-user quotas:
    - Free users: 60 requests/minute
    - Premium users: 300 requests/minute
    - Admins: Unlimited
    """

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def check_rate_limit(
        self,
        user_id: str,
        endpoint: str,
        user_tier: str = "free"
    ) -> bool:
        """
        Check if user exceeded rate limit.

        Returns:
            True if within limits
            False if exceeded
        """
        # Get quota for user tier
        quota = self._get_quota(user_tier)

        if quota is None:  # Unlimited (admin)
            return True

        # Use sliding window algorithm
        key = f"rate_limit:{user_id}:{endpoint}"
        now = int(time.time())
        window = 60  # 60 seconds

        # Remove old entries
        await self.redis.zremrangebyscore(
            key,
            0,
            now - window
        )

        # Count requests in window
        count = await self.redis.zcard(key)

        if count >= quota:
            # Get reset time
            oldest = await self.redis.zrange(key, 0, 0, withscores=True)
            if oldest:
                reset_at = int(oldest[0][1]) + window
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Try again in {reset_at - now}s",
                    headers={
                        "X-RateLimit-Limit": str(quota),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(reset_at)
                    }
                )

        # Add current request
        await self.redis.zadd(key, {str(uuid.uuid4()): now})
        await self.redis.expire(key, window)

        return True

    def _get_quota(self, user_tier: str) -> Optional[int]:
        """Get rate limit quota for user tier"""
        quotas = {
            "free": 60,
            "premium": 300,
            "admin": None  # Unlimited
        }
        return quotas.get(user_tier, 60)

# Usage in middleware:
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    user = request.state.user

    rate_limiter = AdvancedRateLimiter(redis_client)

    await rate_limiter.check_rate_limit(
        user_id=user.id,
        endpoint=request.url.path,
        user_tier=user.tier
    )

    response = await call_next(request)

    # Add rate limit headers
    response.headers["X-RateLimit-Limit"] = "60"
    response.headers["X-RateLimit-Remaining"] = "45"

    return response
```

#### **ДЕНЬ 20: WebApp Performance Optimization**

**Задача 4.5: WebApp Performance Optimization** (8 часов)
```typescript
// vite.config.ts - Build optimization
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { compression } from 'vite-plugin-compression'

export default defineConfig({
  plugins: [
    vue(),

    // Gzip compression
    compression({
      algorithm: 'gzip',
      ext: '.gz'
    }),

    // Brotli compression
    compression({
      algorithm: 'brotliCompress',
      ext: '.br'
    })
  ],

  build: {
    // Code splitting
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor': ['vue', 'vue-router', 'pinia'],
          'ui': ['@headlessui/vue', '@heroicons/vue'],
          'telegram': ['@twa-dev/sdk']
        }
      }
    },

    // Minification
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true,
        drop_debugger: true
      }
    },

    // Target modern browsers
    target: 'es2020',

    // Asset optimization
    assetsInlineLimit: 4096,
    chunkSizeWarningLimit: 500
  },

  // CSS optimization
  css: {
    devSourcemap: false
  }
})

// src/utils/lazy-loading.ts - Lazy load components
import { defineAsyncComponent } from 'vue'

export const lazyLoad = (path: string) => {
  return defineAsyncComponent(() => import(path))
}

// router/index.ts - Route-based code splitting
const routes = [
  {
    path: '/',
    component: () => import('@/views/HomeView.vue')
  },
  {
    path: '/requests',
    component: () => import('@/views/RequestsView.vue')
  },
  {
    path: '/create-request',
    component: () => import('@/views/CreateRequestView.vue')
  }
]

// Image optimization
// src/components/OptimizedImage.vue
<template>
  <img
    :src="currentSrc"
    :srcset="srcset"
    :loading="lazy ? 'lazy' : 'eager'"
    @load="onLoad"
  />
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

interface Props {
  src: string
  lazy?: boolean
  sizes?: string
}

const props = withDefaults(defineProps<Props>(), {
  lazy: true,
  sizes: '100vw'
})

// Generate WebP version
const currentSrc = computed(() => {
  if (supportsWebP.value) {
    return props.src.replace(/\.(jpg|png)$/, '.webp')
  }
  return props.src
})

// Responsive srcset
const srcset = computed(() => {
  const base = props.src.replace(/\.(jpg|png)$/, '')
  return `
    ${base}-320w.webp 320w,
    ${base}-640w.webp 640w,
    ${base}-1024w.webp 1024w
  `
})
</script>

Performance Targets:
  - First Contentful Paint: < 1.5s
  - Time to Interactive: < 3.0s
  - Lighthouse Score: > 90
  - Bundle size: < 200KB (gzipped)
```

---

### WEEK 5: WebApp Advanced Features & Testing

#### **ДЕНЬ 21-22: WebApp Analytics & Push Notifications**

**Задача 5.1: WebApp Analytics Integration** (6 часов)
```typescript
// src/services/analytics.service.ts
class AnalyticsService {
  /**
   * Track user events for analytics.
   *
   * Events tracked:
   * - Page views
   * - Button clicks
   * - Request creation
   * - Payment initiation
   * - Errors
   */

  trackPageView(pageName: string) {
    const tg = window.Telegram.WebApp

    // Send to backend
    api.post('/api/v1/analytics/events', {
      event_type: 'page_view',
      event_data: {
        page: pageName,
        user_id: tg.initDataUnsafe.user?.id,
        timestamp: Date.now()
      }
    })
  }

  trackEvent(eventName: string, eventData: any) {
    api.post('/api/v1/analytics/events', {
      event_type: eventName,
      event_data: {
        ...eventData,
        webapp_version: '1.0.0',
        platform: tg.platform
      }
    })
  }

  // User behavior tracking
  trackRequestCreated(requestNumber: string) {
    this.trackEvent('request_created', {
      request_number: requestNumber,
      source: 'webapp'
    })
  }

  trackPaymentInitiated(amount: number, currency: string) {
    this.trackEvent('payment_initiated', {
      amount,
      currency,
      source: 'webapp'
    })
  }
}

// Usage in components:
// router.afterEach((to) => {
//   analytics.trackPageView(to.name as string)
// })
```

**Задача 5.2: Push Notifications via WebApp** (6 часов)
```typescript
// src/services/notification.service.ts
class NotificationService {
  /**
   * Handle push notifications in WebApp.
   *
   * Methods:
   * - Telegram notifications (native)
   * - In-app notifications
   * - Badge updates
   */

  async requestPermission() {
    const tg = window.Telegram.WebApp

    // Request notification permission
    tg.requestNotificationPermission((granted) => {
      if (granted) {
        this.subscribeToNotifications()
      }
    })
  }

  async subscribeToNotifications() {
    // Register for push notifications
    const response = await api.post('/api/v1/notifications/subscribe', {
      webapp_id: window.Telegram.WebApp.initDataUnsafe.user?.id,
      platform: 'webapp'
    })

    return response.data
  }

  // Show in-app notification
  showNotification(title: string, message: string, type: 'info' | 'success' | 'error' = 'info') {
    const tg = window.Telegram.WebApp

    // Use Telegram's native notification
    tg.showAlert(message)

    // Or show custom in-app notification
    this.showCustomNotification({
      title,
      message,
      type,
      duration: 3000
    })
  }

  // Update badge count
  updateBadge(count: number) {
    const tg = window.Telegram.WebApp

    // Update badge on Telegram icon
    tg.setBadge(count)
  }
}

// WebSocket for real-time notifications
// src/services/websocket.service.ts
class WebSocketService {
  private ws: WebSocket | null = null

  connect() {
    const token = localStorage.getItem('token')
    this.ws = new WebSocket(`wss://api.example.com/ws?token=${token}`)

    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data)

      if (data.type === 'notification') {
        notificationService.showNotification(
          data.title,
          data.message,
          data.notification_type
        )
      }

      if (data.type === 'request_update') {
        // Update request in store
        requestStore.updateRequest(data.request)
      }
    }
  }
}
```

#### **ДЕНЬ 23-24: Integration Testing**

**Задача 5.3: End-to-End Testing** (10 часов)
```typescript
// tests/e2e/request-creation.spec.ts
import { test, expect } from '@playwright/test'

test.describe('Request Creation Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Mock Telegram WebApp
    await page.addInitScript(() => {
      window.Telegram = {
        WebApp: {
          initData: 'mock_init_data',
          initDataUnsafe: {
            user: {
              id: 12345,
              first_name: 'Test',
              username: 'testuser'
            }
          },
          ready: () => {},
          expand: () => {},
          close: () => {},
          // ... other methods
        }
      }
    })

    // Navigate to app
    await page.goto('http://localhost:5173')
  })

  test('should create request successfully', async ({ page }) => {
    // Click create request
    await page.click('text=Создать заявку')

    // Select category
    await page.click('text=Электрика')

    // Enter address
    await page.fill('input[name="address"]', 'Tashkent, Mirzo Ulugbek 12')

    // Enter description
    await page.fill('textarea[name="description"]', 'Не работает розетка')

    // Upload photo
    await page.setInputFiles('input[type="file"]', 'tests/fixtures/photo.jpg')

    // Submit
    await page.click('button:has-text("Отправить")')

    // Verify success
    await expect(page.locator('text=Заявка создана')).toBeVisible()

    // Verify request number format (YYMMDD-NNN)
    const requestNumber = await page.locator('[data-testid="request-number"]').textContent()
    expect(requestNumber).toMatch(/^\d{6}-\d{3}$/)
  })

  test('should validate required fields', async ({ page }) => {
    await page.click('text=Создать заявку')

    // Try to submit without filling
    await page.click('button:has-text("Отправить")')

    // Check validation errors
    await expect(page.locator('text=Выберите категорию')).toBeVisible()
    await expect(page.locator('text=Введите адрес')).toBeVisible()
  })
})

// Integration tests for Bot Gateway
// tests/integration/test_bot_integration.py
import pytest
from aiogram.types import Update, Message

@pytest.mark.asyncio
async def test_create_request_flow(bot_client, mock_services):
    """Test full request creation flow via bot"""

    # Mock external services
    mock_services.auth.validate_user.return_value = {
        "valid": True,
        "user_id": "user123"
    }

    mock_services.request.create.return_value = {
        "request_number": "251006-001",
        "status": "new"
    }

    # Simulate /create_request command
    update = Update(
        message=Message(
            text="/create_request",
            from_user={"id": 12345, "username": "testuser"}
        )
    )

    await bot_client.process_update(update)

    # Verify response
    sent_messages = bot_client.get_sent_messages()
    assert len(sent_messages) == 1
    assert "Выберите категорию" in sent_messages[0].text

    # Simulate category selection
    callback_update = Update(
        callback_query={
            "data": "category_electric",
            "from_user": {"id": 12345}
        }
    )

    await bot_client.process_update(callback_update)

    # Continue flow...

Coverage Target: 85%+
```

---

### WEEK 6: Monolith Cleanup & Production Launch

#### **ДЕНЬ 25-26: Monolith Migration Verification**

**Задача 6.1: Data Migration Verification** (8 часов)
```python
# scripts/verify_migration.py
"""
Verify that all data migrated correctly from monolith to microservices.

Checks:
1. User count matches
2. Request count matches
3. All request numbers valid (YYMMDD-NNN)
4. All relationships intact
5. No data loss
"""

import asyncio
from sqlalchemy import select, func
from monolith.database import MonolithSession
from microservices.request_service.models import Request as NewRequest
from microservices.user_service.models import User as NewUser

async def verify_user_migration():
    """Verify all users migrated correctly"""
    # Count in monolith
    async with MonolithSession() as old_db:
        old_count = await old_db.scalar(select(func.count(OldUser.id)))

    # Count in microservice
    async with UserServiceDB() as new_db:
        new_count = await new_db.scalar(select(func.count(NewUser.id)))

    assert old_count == new_count, f"User count mismatch: {old_count} vs {new_count}"

    print(f"✅ Users: {new_count} migrated successfully")

async def verify_request_migration():
    """Verify all requests migrated correctly"""
    async with RequestServiceDB() as new_db:
        # Check request numbers
        invalid_numbers = await new_db.execute(
            select(NewRequest.request_number).where(
                ~NewRequest.request_number.op('~')(r'^\d{6}-\d{3}$')
            )
        )

        invalid = invalid_numbers.scalars().all()
        assert len(invalid) == 0, f"Found {len(invalid)} invalid request numbers"

        # Check relationships
        orphaned = await new_db.execute(
            select(NewRequest).where(
                NewRequest.assigned_executor_id.isnot(None),
                ~NewRequest.assigned_executor_id.in_(
                    select(NewUser.id)
                )
            )
        )

        orphaned_count = len(orphaned.scalars().all())
        assert orphaned_count == 0, f"Found {orphaned_count} orphaned requests"

    print("✅ Requests: All migrated correctly")

async def verify_media_files():
    """Verify all media files accessible"""
    async with MediaServiceDB() as db:
        files = await db.execute(select(MediaFile))

        for file in files.scalars():
            # Check if file exists in Telegram channel
            exists = await check_telegram_file(file.telegram_file_id)
            assert exists, f"File {file.id} not found in Telegram"

    print("✅ Media: All files accessible")

# Run verification
if __name__ == "__main__":
    asyncio.run(verify_user_migration())
    asyncio.run(verify_request_migration())
    asyncio.run(verify_media_files())

    print("\n🎉 Migration verification completed successfully!")
```

**Задача 6.2: Performance Comparison** (6 часов)
```python
# scripts/performance_comparison.py
"""
Compare performance: Monolith vs Microservices.

Metrics:
- Request creation time
- User profile lookup
- Search performance
- Concurrent user handling
"""

import asyncio
import time
from locust import HttpUser, task, between

class MonolithUser(HttpUser):
    """Load test for monolith"""
    wait_time = between(1, 3)
    host = "http://monolith:8000"

    @task
    def create_request(self):
        self.client.post("/api/requests", json={
            "category": "electric",
            "address": "Test address",
            "description": "Test request"
        })

class MicroservicesUser(HttpUser):
    """Load test for microservices"""
    wait_time = between(1, 3)
    host = "http://bot-gateway:8010"

    @task
    def create_request(self):
        self.client.post("/api/v1/requests", json={
            "category": "electric",
            "address": "Test address",
            "description": "Test request"
        })

# Run comparison:
# locust -f performance_comparison.py --users 1000 --spawn-rate 50

# Expected results:
# Metric                    | Monolith | Microservices | Improvement
# --------------------------|----------|---------------|------------
# Avg Response Time         | 450ms    | 180ms         | 60% faster
# p95 Response Time         | 1200ms   | 350ms         | 71% faster
# Requests/sec              | 120      | 450           | 275% more
# Max Concurrent Users      | 500      | 5000          | 10x more
# Error Rate                | 2.5%     | 0.1%          | 96% less
```

#### **ДЕНЬ 27-28: Monolith Decommissioning**

**Задача 6.3: Gradual Traffic Migration** (8 часов)
```yaml
# Canary Deployment Strategy
# Traefik configuration for gradual migration

# Step 1: 10% traffic to microservices (Day 27 morning)
http:
  routers:
    monolith-router:
      rule: "Host(`api.example.com`)"
      service: "weighted-service"
      weight: 90

    microservices-router:
      rule: "Host(`api.example.com`)"
      service: "microservices"
      weight: 10

# Step 2: 50% traffic (Day 27 afternoon)
# Update weights: 50/50

# Step 3: 90% traffic (Day 28 morning)
# Update weights: 10/90

# Step 4: 100% traffic (Day 28 afternoon)
# Update weights: 0/100

# Monitoring during migration:
monitors:
  - name: "Error Rate"
    alert_threshold: 1%
    action: "rollback"

  - name: "Response Time p95"
    alert_threshold: 500ms
    action: "hold_migration"

  - name: "Success Rate"
    alert_threshold: 99%
    action: "rollback"

# Rollback procedure:
rollback:
  trigger: "manual OR automated_alert"
  steps:
    - Set traffic to 100% monolith
    - Notify team
    - Investigate issue
    - Fix and retry
```

**Задача 6.4: Monolith Shutdown & Cleanup** (6 часов)
```bash
#!/bin/bash
# scripts/decommission_monolith.sh

echo "🚀 Starting monolith decommissioning..."

# Step 1: Verify 100% traffic on microservices
echo "📊 Checking traffic distribution..."
MONOLITH_REQUESTS=$(curl -s http://prometheus:9090/api/v1/query?query=http_requests_total{service="monolith"})
if [ "$MONOLITH_REQUESTS" != "0" ]; then
  echo "❌ Still receiving traffic on monolith. Aborting."
  exit 1
fi

# Step 2: Final data backup
echo "💾 Creating final backup..."
docker-compose exec monolith-db pg_dump -U uk_bot uk_management > monolith_final_backup.sql
gzip monolith_final_backup.sql

# Step 3: Archive monolith code
echo "📦 Archiving monolith codebase..."
tar -czf monolith_archive_$(date +%Y%m%d).tar.gz uk_management_bot/
mv monolith_archive_*.tar.gz /archive/

# Step 4: Stop monolith services
echo "🛑 Stopping monolith services..."
docker-compose stop monolith-app monolith-db

# Step 5: Update documentation
echo "📝 Updating documentation..."
cat > MIGRATION_COMPLETE.md << EOF
# ✅ Monolith Migration Complete

**Completion Date**: $(date)
**Final Metrics**:
- Total Users Migrated: $(psql -U uk_bot -c "SELECT COUNT(*) FROM users;" -t)
- Total Requests Migrated: $(psql -U request_user -c "SELECT COUNT(*) FROM requests;" -t)
- Zero Data Loss: Verified ✅
- Zero Downtime: Achieved ✅

**Archive Location**: /archive/monolith_archive_$(date +%Y%m%d).tar.gz
**Backup Location**: /backups/monolith_final_backup.sql.gz

**Microservices Status**:
- Auth Service: ✅ Running
- User Service: ✅ Running
- Request Service: ✅ Running
- Media Service: ✅ Running
- Notification Service: ✅ Running
- Integration Service: ✅ Running
- Bot Gateway: ✅ Running

**Next Steps**:
- Monitor microservices for 30 days
- Decommission hardware after 60 days
- Delete archived monolith after 1 year
EOF

echo "✅ Monolith decommissioned successfully!"
echo "📊 All services now running on microservices architecture"
```

#### **ДЕНЬ 29-30: Final Testing & Documentation**

**Задача 6.5: Production Smoke Tests** (6 часов)
```python
# tests/production/smoke_tests.py
"""
Production smoke tests to run after deployment.

Tests critical user journeys:
1. User registration
2. Request creation
3. Payment processing
4. Notifications
"""

import pytest
import asyncio
from playwright.async_api import async_playwright

@pytest.mark.production
async def test_critical_user_journey():
    """Test end-to-end user journey in production"""

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        # 1. Open Telegram WebApp
        await page.goto('https://t.me/uk_management_bot/app')

        # 2. Authenticate
        await page.click('text=Войти')

        # 3. Create request
        await page.click('text=Создать заявку')
        await page.select_option('select[name="category"]', 'electric')
        await page.fill('input[name="address"]', 'Production Test Address')
        await page.fill('textarea[name="description"]', 'Smoke test request')
        await page.click('button:has-text("Отправить")')

        # 4. Verify request created
        request_number = await page.locator('[data-testid="request-number"]').text_content()
        assert request_number, "Request number not found"

        # 5. Verify notification received
        # (check notification service logs)

        await browser.close()

    print(f"✅ Smoke test passed. Request: {request_number}")

@pytest.mark.production
async def test_service_health():
    """Check all services are healthy"""
    services = [
        "http://auth-service:8001/health",
        "http://user-service:8002/health",
        "http://request-service:8003/health",
        "http://media-service:8004/health",
        "http://notification-service:8005/health",
        "http://integration-service:8009/health",
        "http://bot-gateway:8010/health"
    ]

    for service_url in services:
        async with aiohttp.ClientSession() as session:
            async with session.get(service_url) as response:
                assert response.status == 200, f"{service_url} unhealthy"

    print("✅ All services healthy")
```

**Задача 6.6: Final Documentation** (8 часов)
```markdown
# 📚 Final Documentation Creation

## Documents to Create:

### 1. DEPLOYMENT_GUIDE.md
- Production deployment steps
- Environment variables
- SSL certificate setup
- Database setup
- Monitoring configuration
- Backup procedures

### 2. OPERATIONS_RUNBOOK.md
- Common operations tasks
- Troubleshooting guide
- Scaling procedures
- Disaster recovery
- On-call procedures

### 3. API_MIGRATION_GUIDE.md
- API changes from monolith
- Breaking changes
- Migration examples
- Client library updates

### 4. ARCHITECTURE_DECISION_RECORDS.md
- Why microservices
- Technology choices
- Design patterns used
- Trade-offs made

### 5. PERFORMANCE_BENCHMARKS.md
- Load test results
- Comparison with monolith
- Optimization opportunities
- Scalability limits

### 6. SECURITY_AUDIT_REPORT.md
- Security measures implemented
- Penetration test results
- Compliance checklist
- Future improvements
```

---

## 📊 SPRINT COMPLETION METRICS

### Sprint 19-20 Success Criteria (Week 1-3)
- ✅ Integration Service deployed with 3+ adapters
- ✅ Bot Gateway replaces monolith Telegram interface
- ✅ Telegram WebApp functional with authentication
- ✅ 50+ FSM states migrated
- ✅ All integration tests passing
- ✅ Load test: 1000+ concurrent users

### Sprint 21-22 Success Criteria (Week 4-6)
- ✅ Advanced features deployed (payments, location, camera)
- ✅ Circuit breakers protecting all service calls
- ✅ Distributed tracing operational
- ✅ WebApp performance targets met
- ✅ Monolith successfully decommissioned
- ✅ Production deployment completed
- ✅ Zero data loss verified
- ✅ Zero downtime achieved

---

## 🎯 RISK MITIGATION

### High-Risk Items
1. **FSM State Migration**
   - Risk: State data loss during migration
   - Mitigation: Redis backup, gradual rollout

2. **Telegram WebApp Browser Compatibility**
   - Risk: Different behavior in iOS vs Android
   - Mitigation: Extensive cross-platform testing

3. **Payment Integration**
   - Risk: Failed transactions, double charging
   - Mitigation: Idempotency keys, webhook verification

### Rollback Plan
```yaml
If Migration Fails:
  1. Immediate Actions:
     - Revert Traefik config to 100% monolith
     - Stop bot gateway container
     - Notify all stakeholders

  2. Investigation:
     - Check error logs
     - Identify root cause
     - Estimate fix time

  3. Decision:
     - Fix < 2 hours: Fix and retry
     - Fix > 2 hours: Postpone sprint
```

---

## 📋 TASK SUMMARY

**Total Tasks**: 58
**Estimated Time**: 242 hours (6 weeks @ 40 hours/week)

### By Week:
- **Week 1**: 10 tasks, 34 hours
- **Week 2**: 10 tasks, 42 hours
- **Week 3**: 10 tasks, 42 hours
- **Week 4**: 10 tasks, 40 hours
- **Week 5**: 10 tasks, 40 hours
- **Week 6**: 8 tasks, 44 hours

### By Component:
- **Integration Service**: 12 tasks, 50 hours
- **Bot Gateway**: 18 tasks, 76 hours
- **Telegram WebApp**: 14 tasks, 60 hours
- **Advanced Features**: 8 tasks, 32 hours
- **Testing & Deployment**: 6 tasks, 24 hours

---

**Document Version**: 1.0
**Created**: 6 октября 2025
**Status**: ✅ READY FOR EXECUTION
**Next Action**: Begin Sprint 19 Day 1 - Integration Service Architecture
