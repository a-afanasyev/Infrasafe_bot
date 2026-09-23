# Техническое задание: Полное переписывание UK Management Bot на Node.js

**Версия:** 1.0
**Дата:** 2026-03-09
**Исполнитель:** Claude Opus 4.6
**Источник:** audit/ документация UK Management Bot v1.0.0 + InfraSafe Habitat IQ v1.0.1
**Цель:** Переписать UK Management Bot с Python/aiogram на Node.js/Express.js (стек InfraSafe), одновременно интегрировав IoT-функциональность InfraSafe в единый продукт

---

## КРАТКОЕ РЕЗЮМЕ

Данный документ — мастер-план (план планов) для полного переписывания Telegram-бота управления ЖКХ с Python (aiogram 3.x, SQLAlchemy 2.x, FastAPI) на JavaScript (Node.js 20+, Express.js, grammY, PostgreSQL + PostGIS). Переписывание преследует две цели: (1) унификация стека с InfraSafe Habitat IQ для последующего объединения в единый продукт, (2) устранение архитектурных ограничений текущей реализации.

Мастер-план состоит из **15 планов**, каждый из которых является самостоятельной единицей работы с чёткими входами, выходами и критериями приёмки. Планы разбиты на 4 фазы: Foundation (планы 01-04), Core Business Logic (05-08), Intelligence & Integration (09-11), Production Readiness (12-15). Общий объём: ~16-20 недель для одного разработчика.

**Ключевые архитектурные решения:**
- **Telegram framework:** grammY (современный, TypeScript-совместимый, middleware-архитектура аналогична aiogram 3.x)
- **ORM:** Prisma (type-safe, миграции, отношения — заменяет SQLAlchemy)
- **Scheduler:** node-cron + BullMQ (заменяет APScheduler)
- **FSM:** grammY conversations plugin (заменяет aiogram FSM)
- **PostGIS:** уже используется в InfraSafe, расширяется для адресного справочника UK Bot

---

## СОДЕРЖАНИЕ

1. [Контекст и обоснование](#1-контекст-и-обоснование)
2. [Технологический стек](#2-технологический-стек)
3. [Целевая архитектура](#3-целевая-архитектура)
4. [Модель данных](#4-модель-данных)
5. [Мастер-план: план планов](#5-мастер-план)
6. [План 01: Project Setup & Infrastructure](#план-01)
7. [План 02: Database Schema & Prisma](#план-02)
8. [План 03: Core Framework — Express + grammY + Middleware](#план-03)
9. [План 04: Authentication & Authorization](#план-04)
10. [План 05: User Management & Verification](#план-05)
11. [План 06: Address Registry + PostGIS](#план-06)
12. [План 07: Request Lifecycle](#план-07)
13. [План 08: Shift Management](#план-08)
14. [План 09: AI/ML Layer](#план-09)
15. [План 10: IoT Integration — Alert→Request Pipeline](#план-10)
16. [План 11: Notifications & Scheduling](#план-11)
17. [План 12: Web Dashboard — Leaflet Map + Analytics](#план-12)
18. [План 13: Payment Integration](#план-13)
19. [План 14: Testing & Security](#план-14)
20. [План 15: DevOps, Docker & Deployment](#план-15)
21. [Матрица миграции компонентов](#6-матрица-миграции)
22. [Критические замечания для исполнителя](#7-критические-замечания)

---

## 1. Контекст и обоснование

### 1.1. Зачем переписывать

| Причина | Описание |
|---------|----------|
| **Унификация стека** | InfraSafe (Node.js) + UK Bot (Python) = 2 стека для одного разработчика. Унификация на JS снижает cognitive load |
| **Общая кодовая база** | Shared models (Building, User), shared services (auth, PostGIS), shared infrastructure |
| **Объединение продуктов** | Audit 08 показал: объединение — единственный путь к жизнеспособному продукту (7.5/10 vs 4/10) |
| **Команда** | Solo-developer. Один стек = одна голова. Python + JS = переключение контекста |
| **Telegram экосистема** | grammY — лучший JS-фреймворк для Telegram ботов, сопоставим с aiogram 3.x |

### 1.2. Что НЕ переписывается, а переносится as-is

- InfraSafe backend (Node.js) — уже на целевом стеке
- InfraSafe frontend (Vanilla JS, Leaflet) — расширяется, не переписывается
- PostgreSQL + PostGIS — общая БД, расширяется новыми таблицами
- Docker Compose — унифицируется из двух конфигураций в одну

### 1.3. Что переписывается полностью

- UK Bot backend: Python → Node.js
- UK Bot services (38 штук) → JS services
- UK Bot handlers (25+ роутеров) → grammY routers
- UK Bot middlewares (6) → grammY/Express middlewares
- UK Bot models (20+ SQLAlchemy) → Prisma schema
- UK Bot FSM (12+ StatesGroup) → grammY conversations
- AI/ML layer (SmartDispatcher, WorkloadPredictor, GeoOptimizer, RecommendationEngine) → JS classes
- FastAPI web registration → Express routes (merge with InfraSafe)

---

## 2. Технологический стек

### 2.1. Целевой стек (унифицированный)

| Компонент | Технология | Версия | Замечание |
|-----------|-----------|--------|-----------|
| **Runtime** | Node.js | 20+ LTS | Как в InfraSafe |
| **Web Framework** | Express.js | ^4.18 | Как в InfraSafe |
| **Telegram Bot** | grammY | ^1.x | Замена aiogram 3.x |
| **ORM** | Prisma | ^5.x | Замена SQLAlchemy 2.x. Type-safe, миграции, отношения |
| **Database** | PostgreSQL + PostGIS | 15+ | Общая с InfraSafe |
| **Cache / Queue** | Redis | 7+ | FSM storage, rate limiting, BullMQ queues |
| **Job Queue** | BullMQ | ^5.x | Замена APScheduler. Persistent, retries, UI |
| **Scheduler** | node-cron | ^3.x | Cron triggers для BullMQ jobs |
| **Validation** | zod | ^3.x | Schema validation (замена express-validator + pydantic) |
| **Auth** | jsonwebtoken + bcrypt | | Как в InfraSafe |
| **HTTP Client** | axios | ^1.x | Замена httpx (Media Service, webhooks) |
| **Logging** | winston | ^3.x | Как в InfraSafe |
| **i18n** | i18next | ^23.x | Замена custom get_text(). Поддержка ru/uz |
| **Testing** | Jest + supertest | | Как в InfraSafe |
| **Linting** | ESLint + Prettier | | Code quality |
| **Maps** | Leaflet.js | | Как в InfraSafe |
| **Charts** | Chart.js | | Как в InfraSafe |
| **Security** | helmet, cors, DOMPurify | | Как в InfraSafe |

### 2.2. Маппинг Python → JS компонентов

| Python (текущий) | JavaScript (целевой) | Примечание |
|------------------|---------------------|------------|
| aiogram 3.x Router | grammY Router | 1:1 маппинг |
| aiogram Middleware | grammY middleware / Express middleware | Bot middleware ≠ API middleware |
| aiogram FSM (StatesGroup) | grammY conversations plugin | Более мощный: поддерживает async flows |
| aiogram CallbackData factory | grammY callback-data plugin | Аналогичный API |
| SQLAlchemy Model | Prisma model | Декларативная схема |
| SQLAlchemy Session | Prisma Client | Auto connection management |
| Alembic migration | Prisma Migrate | `prisma migrate dev/deploy` |
| FastAPI Router | Express Router | Часть общего API |
| APScheduler | node-cron + BullMQ | Cron triggers + persistent jobs |
| httpx AsyncClient | axios | HTTP client |
| structlog | winston | Structured logging |
| Jinja2 | EJS / Pug | Шаблонизация (опционально) |
| `@require_role` decorator | middleware function | `requireRole(['manager'])` |
| `get_text(key, lang)` | `i18next.t(key, { lng })` | i18n framework |
| Redis (MemoryStorage fallback) | Redis (обязательный) | Убираем fallback |
| Pydantic Settings | dotenv + zod schema | Валидация конфигурации |

---

## 3. Целевая архитектура

### 3.1. Схема компонентов

```
                        +-----------+
                        |  Браузер  |
                        +-----+-----+
                              |
                        порт 8080
                              |
                  +-----------v-----------+
                  |        Nginx          |
                  |  /           → public |
                  |  /api/*      → app    |
                  |  /bot-api/*  → app    |
                  +-----------+-----------+
                              |
                        порт 3000
                              |
              +---------------v---------------+
              |      Express.js (unified)     |
              |                               |
              |  +-------------------------+  |
              |  | Middleware Layer         |  |
              |  |  helmet, cors, morgan,  |  |
              |  |  JWT auth, rate limiter |  |
              |  +-------------------------+  |
              |                               |
              |  +------------+  +---------+  |
              |  | REST API   |  | grammY  |  |
              |  | Routes     |  | Bot     |  |
              |  | (Express)  |  | Router  |  |
              |  +------+-----+  +----+----+  |
              |         |             |        |
              |  +------v-------------v-----+  |
              |  |    Service Layer          |  |
              |  |  RequestService           |  |
              |  |  ShiftService             |  |
              |  |  SmartDispatcher          |  |
              |  |  AlertService (InfraSafe) |  |
              |  |  NotificationService      |  |
              |  +------------+-------------+  |
              |               |                |
              |  +------------v-------------+  |
              |  |    Data Layer (Prisma)    |  |
              |  |  20+ models              |  |
              |  +------------+-------------+  |
              +---------------+---------------+
                              |
                  +-----------v-----------+
                  |  PostgreSQL 15        |
                  |  + PostGIS            |
                  |  (unified schema)     |
                  +-----------+-----------+
                              |
                  +-----------v-----------+
                  |  Redis 7              |
                  |  FSM, cache, BullMQ   |
                  +-----------------------+
```

### 3.2. Структура директорий

```
uk-platform/
  src/
    bot/                          # grammY Telegram Bot
      handlers/                   #   Bot command/message handlers (25+)
        auth.js                   #     /start, /join, /login
        requests.js               #     Создание заявок (FSM conversation)
        request-status.js         #     Управление статусами
        request-assignment.js     #     Назначение заявок
        request-acceptance.js     #     Приёмка заявок
        request-comments.js       #     Комментарии
        request-reports.js        #     Отчёты
        shifts.js                 #     Управление сменами
        shift-management.js       #     Менеджерские операции со сменами
        shift-transfer.js         #     Передача смен
        my-shifts.js              #     Мои смены (исполнитель)
        admin.js                  #     Админ-панель
        user-management.js        #     Управление пользователями
        employee-management.js    #     Управление сотрудниками
        verification.js           #     Верификация
        onboarding.js             #     Онбординг
        address-yards.js          #     Справочник дворов
        address-buildings.js      #     Справочник зданий
        address-apartments.js     #     Справочник квартир
        address-moderation.js     #     Модерация адресов
        user-apartments.js        #     Квартиры пользователя
        user-yards.js             #     Дворы пользователя
        profile.js                #     Профиль
        health.js                 #     /health команда
        base.js                   #     Fallback (/start, /help)
      keyboards/                  #   Клавиатуры (Reply + Inline)
        main-menu.js
        request-keyboards.js
        shift-keyboards.js
        admin-keyboards.js
        address-keyboards.js
        common.js
      conversations/              #   FSM-диалоги (grammY conversations)
        create-request.js         #     Создание заявки (yard→building→apt→category→desc→urgency→media)
        registration.js           #     Регистрация (/join token)
        shift-transfer.js         #     Запрос передачи смены
        verification-upload.js    #     Загрузка документов верификации
        quarterly-planning.js     #     Квартальное планирование
      middleware/                  #   Bot-specific middleware
        auth.js                   #     Загрузка user по telegram_id
        role-mode.js              #     Парсинг ролей, active_role
        localization.js           #     i18n language detection
        shift-context.js          #     Загрузка контекста смены
        throttling.js             #     Rate limit 2 msg/sec
      callback-data/              #   CallbackData factories
        request-cb.js
        shift-cb.js
        admin-cb.js
    api/                          # Express REST API
      routes/                     #   API маршруты
        auth.js                   #     /api/auth/*
        requests.js               #     /api/requests/*
        shifts.js                 #     /api/shifts/*
        addresses.js              #     /api/addresses/*
        analytics.js              #     /api/analytics/*
        health.js                 #     /api/health/*
        buildings.js              #     /api/buildings/* (InfraSafe)
        controllers.js            #     /api/controllers/* (InfraSafe)
        metrics.js                #     /api/metrics/* (InfraSafe)
        alerts.js                 #     /api/alerts/* (InfraSafe)
        transformers.js           #     /api/transformers/* (InfraSafe)
        power-analytics.js        #     /api/power-analytics/* (InfraSafe)
        admin.js                  #     /api/admin/*
      controllers/                #   Контроллеры
      middleware/                  #   API-specific middleware
        jwt-auth.js
        rate-limiter.js
        validators.js
        error-handler.js
    services/                     # Бизнес-логика (shared bot + api)
      request-service.js
      auth-service.js
      invite-service.js
      shift-service.js
      shift-transfer-service.js
      shift-planning-service.js
      notification-service.js
      comment-service.js
      assignment-service.js
      verification-service.js
      user-service.js
      rating-service.js
      audit-log-service.js
      media-service-client.js
      smart-dispatcher.js        #   AI: мультифакторное назначение
      workload-predictor.js      #   AI: предсказание нагрузки
      geo-optimizer.js           #   AI: географическая оптимизация
      recommendation-engine.js   #   AI: рекомендации
      alert-service.js           #   InfraSafe: управление алертами
      telemetry-service.js       #   InfraSafe: приём IoT-данных
      analytics-service.js       #   InfraSafe: аналитика трансформаторов
      building-service.js        #   InfraSafe: управление зданиями
      cache-service.js           #   InfraSafe: кэширование
      integration-service.js     #   Alert→Request pipeline
    jobs/                         # BullMQ workers
      auto-create-shifts.js      #   Ежедневно 00:30
      rebalance-assignments.js   #   Ежедневно 06:00
      process-transfers.js       #   Каждые 30 мин
      cleanup-stale.js           #   Ежедневно 03:00
      shift-reminders.js         #   Ежедневно 07:00
      auto-assign-requests.js    #   Каждые 15 мин
      sync-assignments.js        #   Каждые 30 мин
      token-cleanup.js           #   Каждый час (InfraSafe blacklist)
    utils/
      logger.js                  #   Winston logger
      circuit-breaker.js         #   Circuit Breaker (InfraSafe)
      query-validation.js        #   SQL injection protection
      helpers.js
      enums.js                   #   RequestStatus, UserRole, ShiftStatus, etc.
      callback-factories.js      #   grammY CallbackData helpers
    config/
      database.js                #   Prisma client init
      redis.js                   #   Redis/ioredis init
      bot.js                     #   grammY bot init
      settings.js                #   Environment validation (zod)
      i18n.js                    #   i18next init
  prisma/
    schema.prisma                #   Unified data model (UK + InfraSafe)
    migrations/                  #   Prisma migrations
    seed.js                      #   Seed data
  public/                        # Frontend (from InfraSafe, extended)
    script.js                    #   Map interface (Leaflet)
    map-layers-control.js        #   Layer management
    admin.js                     #   Admin panel
    analytics/                   #   Chart.js analytics
    css/
    utils/
      domSecurity.js
      csrf.js
  locales/
    ru.json                      #   Russian translations
    uz.json                      #   Uzbek translations
  database/
    init/
      01_init_database.sql       #   Full schema (PostGIS, triggers, indices)
    migrations/                  #   Legacy SQL migrations
  tests/
    unit/
    integration/
    security/
    e2e/
  docker-compose.yml             #   Unified (dev)
  docker-compose.prod.yml        #   Production
  Dockerfile
  Dockerfile.frontend
  package.json
  .env.example
```

### 3.3. Слои приложения

```
┌─────────────────────────────────────────────────────────┐
│ Presentation Layer                                       │
│  ┌──────────────┐  ┌──────────────────┐  ┌───────────┐  │
│  │ grammY Bot   │  │ Express REST API │  │ Web UI    │  │
│  │ Handlers     │  │ Controllers      │  │ (Leaflet) │  │
│  │ Keyboards    │  │                  │  │           │  │
│  │ Conversations│  │                  │  │           │  │
│  └──────┬───────┘  └────────┬─────────┘  └─────┬─────┘  │
├─────────┼───────────────────┼──────────────────┼─────────┤
│ Middleware Layer                                         │
│  Bot: auth, role, i18n, shift-ctx, throttle              │
│  API: jwt, rate-limit, validation, error-handler         │
├─────────┼───────────────────┼──────────────────┼─────────┤
│ Service Layer (shared)                                   │
│  RequestService, ShiftService, SmartDispatcher,           │
│  NotificationService, AlertService, TelemetryService,     │
│  IntegrationService (Alert→Request), ...                  │
├──────────────────────────────────────────────────────────┤
│ Data Layer                                               │
│  Prisma Client → PostgreSQL 15 + PostGIS                 │
│  Redis (ioredis) → FSM, Cache, BullMQ                    │
└──────────────────────────────────────────────────────────┘
```

---

## 4. Модель данных

### 4.1. Unified Prisma Schema (ключевые модели)

Ниже — концептуальная Prisma-схема, объединяющая UK Bot и InfraSafe модели. При реализации каждая модель описывается в Plan 02.

**UK Bot models (переносятся из Python):**

```
User                  - telegram_id, roles (JSON), active_role, status, language, specialization
Request               - request_number (PK: YYMMDD-NNN), статусы, назначение, приёмка
Shift                 - user_id, start/end, status, type, metrics
ShiftTemplate         - шаблон для автосоздания смен
ShiftSchedule         - legacy расписание
ShiftAssignment       - привязка заявки к смене + ai_score
ShiftTransfer         - передача смены (status machine)
Rating                - 1-5 звёзд за заявку
AuditLog              - действия пользователей
Notification          - уведомления
UserDocument          - загруженные документы верификации
UserVerification      - статус верификации
AccessRights          - уровни доступа (apartment/house/yard)
QuarterlyPlan         - квартальный план
QuarterlyShiftSchedule - расписание по плану
PlanningConflict      - конфликты планирования
Yard                  - двор (GPS, is_active)
Building              - здание (address, GPS, этажи, подъезды) ← MERGE с InfraSafe buildings
Apartment             - квартира (номер, подъезд, этаж, площадь)
UserApartment         - привязка user↔apartment (pending/approved/rejected)
UserYard              - доп. доступ к дворам
RequestComment        - комментарии (status_change, clarification, purchase, report)
RequestAssignment     - история назначений
```

**InfraSafe models (уже на JS, расширяются):**

```
InfraUser             - admin/operator/user (веб-аутентификация)
Controller            - IoT-контроллер (serial, building_id, status, heartbeat)
Metric                - телеметрия (электричество, вода, тепло, микроклимат)
InfrastructureAlert   - алерт (type, severity, status, cooldown)
PowerTransformer      - трансформатор (capacity, location, PostGIS)
Line                  - линия электропередач (PostGIS LINESTRING)
WaterLine             - линия водоснабжения
ColdWaterSource       - источник ХВС
HeatSource            - источник тепла
WaterSupplier         - поставщик воды
TokenBlacklist        - отозванные JWT
RefreshToken          - refresh токены
AnalyticsHistory      - партиционированная аналитика
```

### 4.2. Ключевая точка слияния: Building

Сущность `Building` существует в обоих продуктах:

| Поле | UK Bot | InfraSafe | Unified |
|------|--------|-----------|---------|
| id | Integer PK | serial PK | serial PK |
| name | — | varchar(100) | varchar(100) |
| address | Text | text | text |
| town | — | varchar(100) | varchar(100) |
| latitude | Float | numeric(9,6) | numeric(9,6) |
| longitude | Float | numeric(9,6) | numeric(9,6) |
| geom | — | geometry(POINT) | geometry(POINT) |
| yard_id | FK → Yard | — | FK → Yard (NEW for InfraSafe) |
| entrance_count | Integer | — | Integer |
| floor_count | Integer | — | Integer |
| region | — | varchar(50) | varchar(50) |
| management_company | — | varchar(100) | varchar(100) |
| has_hot_water | — | boolean | boolean |
| transformer_ids | — | FK → transformers | FK → transformers |
| water/heat FKs | — | multiple FKs | multiple FKs |

**Стратегия:** единая таблица `buildings` с ВСЕМИ полями из обоих продуктов. `yard_id` добавляется как nullable FK для InfraSafe зданий, которые ещё не привязаны к дворам.

---

## 5. Мастер-план: план планов

### 5.1. Фазы и зависимости

```
PHASE 1: FOUNDATION (Планы 01-04, ~4 недели)
═══════════════════════════════════════════
  Plan 01 ──→ Plan 02 ──→ Plan 03 ──→ Plan 04
  Setup       Schema      Framework   Auth
                            ↓
PHASE 2: CORE BUSINESS LOGIC (Планы 05-08, ~5-6 недель)
═══════════════════════════════════════════════════════
  Plan 05 ──→ Plan 06 ──→ Plan 07
  Addresses   Requests    Shifts
                ↑            ↑
  Plan 08 ─────┘────────────┘
  AI/ML (depends on Requests + Shifts)

PHASE 3: INTELLIGENCE & INTEGRATION (Планы 09-11, ~4-5 недель)
═══════════════════════════════════════════════════════════════
  Plan 09 ────→ Plan 10
  IoT Integration  Notifications
       ↓
  Plan 11
  Dashboard

PHASE 4: PRODUCTION READINESS (Планы 12-15, ~3-4 недели)
═══════════════════════════════════════════════════════
  Plan 12      Plan 13      Plan 14      Plan 15
  Payments     Testing      Security     DevOps
  (parallel)   (parallel)   (parallel)   (sequential)
```

### 5.2. Сводная таблица планов

| # | План | Входы | Выходы | Срок | Зависимости |
|---|------|-------|--------|------|-------------|
| 01 | Project Setup | — | Рабочий проект, конфиги | 2-3 дня | — |
| 02 | Database Schema | Plan 01 | Prisma schema, миграции, seed | 3-4 дня | 01 |
| 03 | Core Framework | Plan 02 | Express + grammY + middleware | 4-5 дней | 02 |
| 04 | Auth & Authorization | Plan 03 | JWT + Telegram auth, invite system | 3-4 дня | 03 |
| 05 | Address Registry | Plan 04 | Yard→Building→Apartment + PostGIS | 3-4 дня | 04 |
| 06 | Request Lifecycle | Plans 04, 05 | CRUD, FSM, статусы, назначение | 5-7 дней | 04, 05 |
| 07 | Shift Management | Plan 04 | Смены, шаблоны, передачи, планирование | 5-7 дней | 04 |
| 08 | AI/ML Layer | Plans 06, 07 | SmartDispatcher, WorkloadPredictor, GeoOptimizer, RecommendationEngine | 5-7 дней | 06, 07 |
| 09 | IoT Integration | Plan 06 | Alert→Request pipeline, telemetry | 4-5 дней | 06 |
| 10 | Notifications & Scheduling | Plans 06, 07 | NotificationService, BullMQ jobs | 3-4 дня | 06, 07 |
| 11 | Web Dashboard | Plans 09, 06 | Leaflet map + заявки + analytics | 4-5 дней | 09, 06 |
| 12 | Payment Integration | Plan 06 | Payme/Click API | 3-4 дня | 06 |
| 13 | Testing | Plans 01-11 | Unit, integration, security, e2e тесты | 4-5 дней | все |
| 14 | Security Hardening | Plans 01-11 | OWASP, rate limiting, input validation | 2-3 дня | все |
| 15 | DevOps & Deployment | Plans 01-14 | Docker, CI/CD, monitoring, health checks | 3-4 дня | все |

---

## План 01: Project Setup & Infrastructure {#план-01}

### Цель
Создать рабочий Node.js проект с правильной структурой, конфигурацией и базовыми зависимостями.

### Задачи

1. **Инициализация проекта**
   - `npm init` с правильными метаданными
   - `.nvmrc` с Node.js 20
   - `.gitignore` для Node.js
   - ESLint + Prettier конфигурация
   - `jsconfig.json` или `tsconfig.json` (если решим использовать TypeScript)

2. **Установка зависимостей**

   ```json
   {
     "dependencies": {
       "express": "^4.18",
       "grammy": "^1.x",
       "@grammyjs/conversations": "^1.x",
       "@grammyjs/router": "^2.x",
       "@grammyjs/menu": "^1.x",
       "@grammyjs/session": "^2.x",
       "@grammyjs/storage-redis": "^2.x",
       "@prisma/client": "^5.x",
       "ioredis": "^5.x",
       "bullmq": "^5.x",
       "jsonwebtoken": "^9.x",
       "bcrypt": "^5.x",
       "zod": "^3.x",
       "i18next": "^23.x",
       "winston": "^3.x",
       "morgan": "^1.x",
       "helmet": "^7.x",
       "cors": "^2.x",
       "axios": "^1.x",
       "node-cron": "^3.x",
       "dotenv": "^16.x",
       "dompurify": "^3.x"
     },
     "devDependencies": {
       "prisma": "^5.x",
       "jest": "^29.x",
       "supertest": "^6.x",
       "eslint": "^8.x",
       "prettier": "^3.x",
       "nodemon": "^3.x"
     }
   }
   ```

3. **Структура директорий** — создать все директории по схеме из раздела 3.2

4. **Файл конфигурации** (`src/config/settings.js`)
   - Загрузка из `.env`
   - Валидация через zod schema
   - Обязательные переменные:

   | Переменная | Описание |
   |------------|----------|
   | `BOT_TOKEN` | Telegram Bot API token |
   | `DATABASE_URL` | PostgreSQL connection string |
   | `REDIS_URL` | Redis connection string |
   | `JWT_SECRET` | Секрет для access tokens |
   | `JWT_REFRESH_SECRET` | Секрет для refresh tokens |
   | `INVITE_SECRET` | HMAC ключ для инвайтов |
   | `ADMIN_TELEGRAM_IDS` | JSON-массив Telegram ID администраторов |
   | `TELEGRAM_CHANNEL_ID` | ID канала уведомлений |

5. **Logger** (`src/utils/logger.js`) — Winston с форматированием как в InfraSafe

6. **`.env.example`** с комментариями

### Критерии приёмки
- `npm install` проходит без ошибок
- `npm run lint` проходит
- `node src/config/settings.js` валидирует .env
- Структура директорий создана

---

## План 02: Database Schema & Prisma {#план-02}

### Цель
Описать unified Prisma-схему, покрывающую ВСЕ модели UK Bot + InfraSafe, создать миграции и seed-данные.

### Задачи

1. **Prisma schema** (`prisma/schema.prisma`)

   Модели UK Bot (20+):
   - `User` — telegram_id (BigInt, unique), username, first_name, last_name, role (legacy), roles (Json), active_role, status (enum: pending/approved/blocked), language (default "ru"), phone, specialization (Json), verification_status, passport data, timestamps
   - `Request` — request_number (String PK, format YYMMDD-NNN), user_id FK, category, status (enum), apartment_id FK, description, urgency (enum), media_files (Json), executor_id FK, all completion/purchase/return/manager_confirmed fields, timestamps
   - `Shift` — user_id FK, start_time, end_time, status (enum), shift_type (enum), specialization_focus (Json), coverage_areas (Json), geographic_zone, max_requests (default 10), current_request_count, priority_level, completed_requests, efficiency_score, quality_rating
   - `ShiftTemplate` — name, start_time, end_time, shift_type, specialization_focus (Json), coverage_areas (Json), max_requests, days_of_week (Json)
   - `ShiftAssignment` — shift_id FK, request_number FK, ai_score Float, assigned_at
   - `ShiftTransfer` — shift_id FK, from_user_id FK, to_user_id FK, status (enum: 6 states), reason (enum), priority, retry_count, max_retries, initiated_by FK, notes, timestamps
   - `Rating` — request_number FK, user_id FK, executor_id FK, rating (1-5), comment, created_at
   - `AuditLog` — action, user_id FK, details (Json), created_at
   - `Notification` — user_id FK, type, message, is_read, created_at
   - `UserDocument` — user_id FK, type (enum: passport/property_deed/rental_agreement/utility_bill/other), file_id, created_at
   - `UserVerification` — user_id FK, status (enum), notes, verified_by FK, created_at
   - `AccessRights` — user_id FK, level (enum: apartment/house/yard), target_id
   - `QuarterlyPlan` — year, quarter, status (enum: draft/active/archived/cancelled), specializations (Json), enable_247, enable_auto_transfer, balance_workload, created_by FK
   - `QuarterlyShiftSchedule` — plan_id FK, user_id FK, date, schedule_type (enum: duty_24_3/workday_5_2/shift_2_2/flexible), shift_data (Json)
   - `PlanningConflict` — plan_id FK, type (enum: overlap/overload/unavailable/coverage_gap), details (Json), resolved
   - `Yard` — name, description, gps_latitude, gps_longitude, is_active
   - `Building` — **UNIFIED** (см. раздел 4.2), address, yard_id FK (nullable), GPS, geom (PostGIS — через raw SQL), entrance_count, floor_count, town, region, management_company, has_hot_water, transformer FKs
   - `Apartment` — building_id FK, apartment_number, entrance, floor, rooms_count, area
   - `UserApartment` — user_id FK, apartment_id FK, status (enum: pending/approved/rejected)
   - `UserYard` — user_id FK, yard_id FK, granted_by FK
   - `RequestComment` — request_number FK, user_id FK, type (enum: status_change/clarification/purchase/report), text, media (Json), created_at
   - `RequestAssignment` — request_number FK, executor_id FK, assigned_by FK, assignment_type (enum: group/individual), assigned_group, ai_score, created_at

   Модели InfraSafe (переносятся из raw SQL в Prisma):
   - `InfraUser` — username, email, password_hash, full_name, role, is_active, failed_login_attempts, account_locked_until, timestamps
   - `Controller` — serial_number (unique), vendor, model, building_id FK, status (enum: online/offline/maintenance), installed_at, last_heartbeat
   - `Metric` — controller_id FK, timestamp, electricity (6 полей), water (4 поля), air/humidity, leak_sensor
   - `InfrastructureAlert` — type, infrastructure_id, infrastructure_type, severity (enum), status (enum: active/acknowledged/resolved), message, affected_buildings, data (Json), acknowledged_by FK, resolved_by FK
   - `PowerTransformer` — name, power_kva, voltage_kv, coordinates, geom (PostGIS), status
   - `Transformer` (legacy) — similar fields
   - `Line` — name, voltage_kv, length_km, transformer_id FK, coordinates, main_path (Json), branches (Json), geom (PostGIS LINESTRING)
   - `WaterLine` — name, diameter_mm, material, pressure_bar, status, coordinates, main_path (Json), branches (Json), geom
   - `ColdWaterSource` — name, address, coordinates, source_type, capacity, pressure, status
   - `HeatSource` — name, address, coordinates, source_type, capacity_mw, fuel_type, status
   - `WaterSupplier` — name, supplier_type, contact info, tariff, contract, status
   - `TokenBlacklist` — token_hash (unique), expires_at, blacklisted_at
   - `RefreshToken` — user_id FK, token_hash, expires_at, created_at

2. **PostGIS extensions** — Prisma не поддерживает PostGIS нативно. Решение:
   - `prisma/migrations/init/postGIS.sql` — raw SQL для создания geometry-полей, триггеров, индексов
   - Использовать `prisma.$queryRaw` для PostGIS-запросов
   - Альтернатива: Prisma для CRUD + raw pg queries для геопространственных операций

3. **Миграции**
   - `npx prisma migrate dev --name init` — начальная миграция
   - Дополнительные SQL-миграции для PostGIS: триггеры (trig_buildings_geom, trig_update_heartbeat и др.), материализованные представления (mv_transformer_load_realtime), партиционирование (analytics_history)
   - Индексы: составные (metrics: controller_id + timestamp DESC), GiST (geometry), GIN (JSONB), partial

4. **Seed** (`prisma/seed.js`)
   - Тестовые данные InfraSafe: 17 зданий Ташкента, контроллеры, метрики, трансформаторы, источники
   - Тестовые данные UK Bot: тестовые пользователи (admin, manager, executor, applicant), двор, здание, квартиры, тестовая заявка

### Критерии приёмки
- `npx prisma migrate dev` проходит
- `npx prisma db seed` заполняет данные
- `npx prisma studio` показывает все модели и связи
- PostGIS-функции работают (ST_DWithin, ST_MakePoint)

---

## План 03: Core Framework — Express + grammY + Middleware {#план-03}

### Цель
Создать каркас приложения: Express-сервер, grammY-бот, middleware-цепочки, i18n, Redis.

### Задачи

1. **Express server** (`src/server.js`)
   - Helmet, CORS (whitelist), Morgan, JSON body (1MB limit)
   - Error handler middleware (глобальный)
   - Health endpoint (`/health`, `/health/detailed`)
   - Монтирование API routes
   - Запуск grammY bot (long polling)
   - Graceful shutdown (SIGTERM/SIGINT)

2. **grammY Bot** (`src/config/bot.js`)
   - Создание Bot instance
   - Session middleware (Redis storage через `@grammyjs/storage-redis`)
   - Conversations plugin (`@grammyjs/conversations`)
   - Error handler (bot.catch)
   - Parse mode: HTML (глобально)
   - Bot API configuration

3. **Bot middleware chain** (порядок критичен — как в aiogram)

   | Порядок | Middleware | Файл | Описание |
   |---------|-----------|------|----------|
   | 1 | `throttling` | `src/bot/middleware/throttling.js` | Rate limit: 2 msg/sec (Redis key `throttle:{telegramId}`) |
   | 2 | `auth` | `src/bot/middleware/auth.js` | Загрузка User по telegram_id, блокировка blocked |
   | 3 | `roleMode` | `src/bot/middleware/role-mode.js` | Парсинг roles (JSON), active_role |
   | 4 | `localization` | `src/bot/middleware/localization.js` | i18n language из user.language или Telegram |
   | 5 | `shiftContext` | `src/bot/middleware/shift-context.js` | Текущая смена исполнителя |

   **Реализация middleware:**
   ```javascript
   // Пример: auth middleware
   async function authMiddleware(ctx, next) {
     const telegramId = ctx.from?.id;
     if (!telegramId) return;

     const user = await prisma.user.findUnique({
       where: { telegram_id: BigInt(telegramId) }
     });

     if (user?.status === 'blocked') {
       return ctx.reply(ctx.t('account_blocked'));
     }

     ctx.session.user = user;
     ctx.session.userStatus = user?.status;
     await next();
   }
   ```

4. **API middleware chain**

   | Middleware | Описание |
   |-----------|----------|
   | `authenticateJWT` | Default-deny JWT (allowlist PUBLIC_ROUTES) |
   | `optionalAuth` | Двухуровневый доступ (buildings-metrics) |
   | `isAdmin` | Проверка role === 'admin' |
   | `rateLimiter` | 6 лимитеров (analytics, admin, CRUD, telemetry, auth, register) |
   | `validators` | express-validator + zod |
   | `errorHandler` | Глобальная обработка ошибок |

5. **i18n** (`src/config/i18n.js`)
   - i18next с бэкендом из JSON-файлов
   - Языки: `ru` (default), `uz`
   - Namespace: bot, api, common
   - Интеграция с grammY через `ctx.t()` (custom property)

6. **Redis** (`src/config/redis.js`)
   - ioredis client
   - Используется для: grammY session storage, BullMQ, rate limiting, cache

7. **Router registration** (порядок как в aiogram — КРИТИЧЕСКИ ВАЖЕН)
   - Зарегистрировать все bot handlers в правильном порядке (28 роутеров)
   - Порядок регистрации определяет приоритет обработки

8. **`requireRole` middleware factory**
   ```javascript
   function requireRole(requiredRoles) {
     return async (ctx, next) => {
       const roles = ctx.session.user?.roles || [];
       if (!requiredRoles.some(r => roles.includes(r))) {
         return ctx.reply(ctx.t('no_access'));
       }
       await next();
     };
   }
   ```

### Критерии приёмки
- Express server стартует на порту 3000
- grammY bot подключается к Telegram (long polling)
- `/health` возвращает `{ status: "healthy" }`
- Redis-сессия работает (сохраняется между сообщениями)
- i18n возвращает строки на ru/uz
- Middleware chain выполняется в правильном порядке

---

## План 04: Authentication & Authorization {#план-04}

### Цель
Реализовать две системы аутентификации: JWT (для Web API) и Telegram ID (для бота), систему инвайтов и регистрации.

### Задачи

1. **AuthService** (`src/services/auth-service.js`)
   - `getOrCreateUser(telegramId, telegramData)` — создание/получение User по Telegram ID
   - `approveUser(telegramId, role)` — одобрение пользователя
   - `blockUser(telegramId)` — блокировка
   - `updateActiveRole(userId, role)` — переключение роли
   - JWT-методы (для Web API, из InfraSafe):
     - `loginWeb(username, password)` → access + refresh tokens
     - `refreshTokens(refreshToken)` → новая пара
     - `logout(accessToken)` → blacklist
     - `changePassword(userId, oldPass, newPass)`
   - Account lockout: 5 неудачных попыток → 15 мин блокировка

2. **InviteService** (`src/services/invite-service.js`)
   - `generateInvite(role, specialization, createdBy)` → `invite_v1:{base64}.{hmac}`
   - `validateInvite(token)` → `{ role, specialization, createdBy }`
   - HMAC-SHA256 подпись с `INVITE_SECRET`
   - Одноразовый nonce (Redis set `used_nonces`)
   - Expiry: 24 часа по умолчанию
   - Rate limiting: 3 попытки / 10 мин (Redis key `invite_rate:{telegramId}`)

3. **Registration conversation** (`src/bot/conversations/registration.js`)
   - grammY conversation:
     1. `/join <token>` → validate invite
     2. Запрос ФИО (мин. 2 слова)
     3. Запрос телефона
     4. Подтверждение [Confirm/Cancel]
     5. Создание User (status=pending)
     6. Уведомление админу [Approve/Reject]
   - FSM states: waiting_for_full_name → waiting_for_phone → waiting_for_confirmation

4. **Auth handler** (`src/bot/handlers/auth.js`)
   - `/start` — онбординг или главное меню
   - `/join <token>` — запуск registration conversation
   - `/login` — вход для существующих (obsolete, но оставить для совместимости)
   - Callback: `approve_user:{telegramId}`, `reject_user:{telegramId}`

5. **Role switching**
   - Кнопка "Сменить роль" → inline keyboard с доступными ролями
   - `ctx.session.user.active_role = selectedRole`
   - Обновление в БД + перерисовка главного меню

6. **Web API auth routes** (`src/api/routes/auth.js`)
   - `POST /api/auth/login` — вход
   - `POST /api/auth/register` — регистрация Web-пользователя
   - `POST /api/auth/refresh` — обновление токенов
   - `POST /api/auth/logout` — выход
   - `POST /api/auth/change-password` — смена пароля
   - `GET /api/auth/profile` — профиль

7. **Token blacklist** — двухуровневый (как в InfraSafe):
   - L1: in-memory Map (быстрый lookup)
   - L2: PostgreSQL таблица `token_blacklist` (персистентный)
   - Автоочистка: ежечасно (BullMQ job)

### Критерии приёмки
- Инвайт генерируется, валидируется, используется однократно
- Регистрация через FSM-диалог работает полностью
- Approve/Reject пользователя работает
- Переключение ролей обновляет меню
- JWT login/logout/refresh работает
- Rate limiting на инвайты работает (3/10min)

---

## План 05: Address Registry + PostGIS {#план-05}

### Цель
Реализовать справочник Yard → Building → Apartment с PostGIS-геопространственными функциями.

### Задачи

1. **CRUD Yard** (bot handlers + API)
   - Создание/редактирование/удаление дворов (менеджер)
   - Поля: name, description, gps_latitude, gps_longitude, is_active
   - Геопоиск: найти дворы в радиусе через PostGIS

2. **CRUD Building** (unified с InfraSafe)
   - Создание/редактирование/удаление зданий
   - Привязка к yard_id
   - PostGIS: автоматическое создание geometry при INSERT/UPDATE координат (триггер)
   - Геопоиск: ST_DWithin для поиска зданий в радиусе

3. **CRUD Apartment**
   - Создание/редактирование/удаление квартир
   - Привязка к building_id
   - Поля: apartment_number, entrance, floor, rooms_count, area

4. **UserApartment** — привязка пользователя к квартире
   - Пользователь выбирает: двор → здание → квартира
   - Создается запись status=pending
   - Модератор approve/reject
   - Ограничение: макс. 2 заявителя на квартиру

5. **UserYard** — дополнительный доступ к дворам
   - Менеджер назначает дополнительные дворы пользователю
   - `granted_by` = ID менеджера

6. **Bot handlers**
   - `address-yards.js` — просмотр/управление дворами
   - `address-buildings.js` — просмотр/управление зданиями
   - `address-apartments.js` — просмотр/управление квартирами
   - `address-moderation.js` — модерация привязок
   - `user-apartments.js` — управление своими квартирами
   - `user-yards.js` — управление доп. дворами

7. **API routes**
   - `GET/POST /api/addresses/yards` — CRUD дворов
   - `GET/POST /api/addresses/buildings` — CRUD зданий (unified с InfraSafe)
   - `GET/POST /api/addresses/apartments` — CRUD квартир
   - Геопоиск: `GET /api/addresses/buildings/search?lat=X&lng=Y&radius=Z`

### Критерии приёмки
- Иерархия Yard→Building→Apartment работает
- PostGIS геопоиск работает (поиск зданий в радиусе)
- UserApartment с модерацией (pending→approved/rejected)
- Ограничение 2 заявителя на квартиру работает
- Справочник InfraSafe buildings объединён с UK Bot buildings

---

## План 06: Request Lifecycle {#план-06}

### Цель
Реализовать полный жизненный цикл заявки: создание через FSM, статусные переходы, назначение, приёмка, комментарии, отчёты.

### Задачи

1. **RequestService** (`src/services/request-service.js`)
   - `createRequest(data)` — создание с номером YYMMDD-NNN
   - `getRequest(requestNumber)` — получение заявки
   - `listRequests(filters, pagination)` — список с фильтрами
   - `updateStatus(requestNumber, newStatus, userId, data)` — смена статуса с валидацией переходов
   - `assignRequest(requestNumber, executorId, assignedBy, type)` — назначение (individual/group)
   - `submitCompletionReport(requestNumber, report, media)` — отчёт исполнителя
   - `managerConfirm(requestNumber, managerId, notes)` — подтверждение менеджером
   - `acceptRequest(requestNumber, applicantId, rating, comment)` — приёмка заявителем
   - `returnRequest(requestNumber, applicantId, reason, media)` — возврат
   - `requestMaterials(requestNumber, materials)` — запрос закупки
   - `requestClarification(requestNumber, question)` — запрос уточнения

2. **Матрица переходов статусов** (жёстко закодирована)

   ```javascript
   const STATUS_TRANSITIONS = {
     'Новая': {
       manager: ['В работе', 'Уточнение', 'Отменена'],
     },
     'В работе': {
       executor: ['Закуп', 'Уточнение', 'Выполнена'],
       manager: ['Уточнение', 'Отменена'],
     },
     'Закуп': {
       executor: ['В работе'],
       manager: ['В работе'],
     },
     'Уточнение': {
       manager: ['В работе'],
       executor: ['В работе'],
     },
     'Выполнена': {
       manager: ['Принято', 'В работе'], // manager_confirmed
     },
     'Исполнено': {
       applicant: ['Принято'], // с оценкой
     },
   };
   ```

3. **Create Request conversation** (`src/bot/conversations/create-request.js`)
   - FSM: selecting_yard → selecting_building → selecting_apartment → selecting_category → entering_description → selecting_urgency → uploading_media → confirming
   - Категории: Электрика, Сантехника, Отопление, Уборка, Безопасность, Техобслуживание
   - Срочность: Обычная, Средняя, Срочная, Критическая
   - Медиафайлы: фото/видео, кнопка "Пропустить"
   - Номер заявки: YYMMDD-NNN (auto-increment за день)

4. **Request handlers**
   - `requests.js` — создание заявок (entry point для FSM)
   - `request-status-management.js` — управление статусами (по роли)
   - `request-assignment.js` — назначение исполнителя (individual/group)
   - `request-acceptance.js` — приёмка (двухэтапная: менеджер → заявитель)
   - `request-comments.js` — комментарии (status_change, clarification, purchase, report)
   - `request-reports.js` — отчёты (фильтры по статусу/категории/периоду/исполнителю)
   - `unaccepted-requests.js` — непринятые заявки (менеджер может напомнить или принять за заявителя)
   - `clarification-replies.js` — ответы на уточнения

5. **CommentService** (`src/services/comment-service.js`)
   - `addComment(requestNumber, userId, type, text, media)`
   - `getComments(requestNumber, type?)`
   - Типы: status_change, clarification, purchase, report

6. **RatingService** (`src/services/rating-service.js`)
   - `createRating(requestNumber, userId, executorId, rating, comment)`
   - `getExecutorRating(executorId)` — средний рейтинг
   - `getRequestRating(requestNumber)` — оценка конкретной заявки

7. **API routes**
   - `GET /api/requests` — список с фильтрами (status, category, executor_id, date_range)
   - `POST /api/requests` — создать
   - `GET /api/requests/:number` — получить
   - `PATCH /api/requests/:number` — обновить статус/данные
   - `POST /api/requests/:number/assign` — назначить
   - `GET /api/analytics/requests` — аналитика

### Критерии приёмки
- Создание заявки через FSM-диалог (8 шагов)
- Номер YYMMDD-NNN генерируется корректно
- Все статусные переходы работают по матрице ролей
- Двухэтапная приёмка (менеджер → заявитель) работает
- Возврат заявки с причиной и медиа работает
- Комментарии всех типов создаются
- Оценка 1-5 при приёмке сохраняется
- API endpoints работают

---

## План 07: Shift Management {#план-07}

### Цель
Реализовать полное управление сменами: шаблоны, создание, передача, квартальное планирование.

### Задачи

1. **ShiftService** (`src/services/shift-service.js`)
   - `createShift(userId, data)` — создание смены
   - `startShift(shiftId)` — planned → active
   - `pauseShift(shiftId)` / `resumeShift(shiftId)` — active ↔ paused
   - `completeShift(shiftId)` — active → completed
   - `cancelShift(shiftId)` — → cancelled
   - `getActiveShift(userId)` — текущая активная смена
   - `getShiftsForPeriod(filters)` — список смен
   - `createFromTemplate(templateId, date)` — создание по шаблону

2. **ShiftTransferService** (`src/services/shift-transfer-service.js`)
   - State machine: pending → assigned → accepted → completed | rejected → pending (retry) | cancelled
   - `requestTransfer(shiftId, fromUserId, reason)` — запрос передачи
   - `assignTransfer(transferId, toUserId, managerId)` — менеджер назначает
   - `acceptTransfer(transferId, toUserId)` — новый исполнитель принимает
   - `rejectTransfer(transferId, toUserId)` — отклонение + retry logic
   - Reasons: illness, emergency, workload, vacation, other
   - Retry: retry_count < max_retries → назад в pending

3. **ShiftPlanningService** (`src/services/shift-planning-service.js`)
   - `createQuarterlyPlan(year, quarter, specializations, options)`
   - `generateSchedule(planId)` — генерация QuarterlyShiftSchedule
   - `detectConflicts(planId)` — проверка конфликтов (overlap, overload, unavailable, coverage_gap)
   - `resolveConflict(conflictId, resolution)`
   - `activatePlan(planId)` — draft → active
   - Schedule types: duty_24_3, workday_5_2, shift_2_2, flexible

4. **ShiftTemplate** — CRUD для шаблонов смен
   - Поля: name, start_time, end_time, shift_type, specialization_focus, coverage_areas, max_requests, days_of_week

5. **Bot handlers**
   - `shift-management.js` — управление сменами (менеджер): создание, просмотр, шаблоны
   - `my-shifts.js` — мои смены (исполнитель): start/pause/resume/complete
   - `shift-transfer.js` — передача смены (FSM conversation)
   - `quarterly-planning.js` — квартальное планирование (FSM conversation)

6. **Shift Transfer conversation** (`src/bot/conversations/shift-transfer.js`)
   - Выбор смены → выбор причины → подтверждение → создание ShiftTransfer

7. **Quarterly Planning conversation** (`src/bot/conversations/quarterly-planning.js`)
   - Выбор квартала → выбор специализаций → настройка (24/7, балансировка, автопередачи) → генерация → проверка конфликтов → активация

### Критерии приёмки
- Полный lifecycle смены: planned → active → paused → active → completed
- Передача смены с retry logic работает
- Шаблоны смен создаются и применяются
- Квартальный план генерирует расписания
- Конфликты обнаруживаются и отображаются
- Все 4 типа расписаний работают

---

## План 08: AI/ML Layer {#план-08}

### Цель
Перенести AI/ML компоненты из Python в JavaScript: SmartDispatcher, WorkloadPredictor, GeoOptimizer, RecommendationEngine.

### Задачи

1. **SmartDispatcher** (`src/services/smart-dispatcher.js`)

   Мультифакторное назначение заявок:

   | Фактор | Вес | Метод расчёта |
   |--------|-----|---------------|
   | Specialization match | 0.35 | Совпадение специализации исполнителя с категорией заявки |
   | Geographic proximity | 0.25 | Haversine distance от текущей позиции исполнителя до здания |
   | Workload balance | 0.20 | Текущая нагрузка vs max_requests |
   | Executor rating | 0.15 | Средний рейтинг из Rating |
   | Urgency priority | 0.05 | Boost 0.2 для срочных |

   Методы:
   - `autoAssignRequests()` — массовое автоназначение (каждые 15 мин)
   - `handleUrgentRequests()` — приоритетная обработка (dynamic weight boost)
   - `balanceWorkload()` — перебалансировка
   - `calculateAssignmentScore(request, executor, shift)` → 0.0-1.0
   - Minimum score threshold: 0.6
   - Max requests per executor: 8

2. **WorkloadPredictor** (`src/services/workload-predictor.js`)

   Прогнозирование нагрузки на основе исторических данных:

   Факторы:
   - Seasonal: месяц → множитель (зима: 1.3-1.4, лето: 0.7-0.8)
   - Weekday: день недели → множитель (Пн: 1.2, Сб: 0.6, Вс: 0.4)
   - Holiday: праздники РУ → множитель 0.2-0.4
   - Weather: сезонные корректировки
   - Trend: линейная регрессия по данным 30+ дней

   Методы:
   - `predictDailyRequests(date)` → { predicted, factors }
   - `predictPeriodWorkload(startDate, endDate)` → daily predictions
   - `analyzeHistoricalPatterns(days = 90)` → patterns
   - `recommendShiftCount(date, specialization)` → number
   - Pattern analysis: daily, weekly, monthly, seasonal

3. **GeoOptimizer** (`src/services/geo-optimizer.js`)

   Географическая оптимизация маршрутов:

   Конфигурация:
   - EARTH_RADIUS: 6371.0 km
   - AVG_CITY_SPEED: 40.0 km/h
   - FUEL_CONSUMPTION: 0.08 L/km
   - MAX_ROUTE_POINTS: 12
   - MAX_ROUTE_DURATION: 8 hours

   Методы:
   - `optimizeDailyRoutes(date)` → optimized routes for all executors
   - `optimizeExecutorRoute(executorId, requests)` → ordered route
   - `calculateRouteMetrics(route)` → { distance_km, time_hours, fuel_liters }
   - `suggestRouteOptimizations(executorId)` → suggestions
   - `findNearbyRequests(lat, lng, radiusKm)` → requests[]
   - `clusterRequestsByLocation(requests, radiusKm = 5)` → clusters[]
   - `_calculateDistance(lat1, lng1, lat2, lng2)` → Haversine formula
   - `_nearestNeighborOptimization(points)` → optimized order

   GPS sources (priority):
   1. Building GPS (apartment → building → coordinates)
   2. Legacy additional_data JSON
   3. PostGIS geocoding

4. **RecommendationEngine** (`src/services/recommendation-engine.js`)

   Типы рекомендаций:
   - SHIFT_OPTIMIZATION — оптимизация расписания смен
   - WORKLOAD_BALANCE — балансировка нагрузки
   - RESOURCE_ALLOCATION — распределение ресурсов
   - PERFORMANCE_IMPROVEMENT — улучшение производительности
   - BOTTLENECK_RESOLUTION — устранение узких мест
   - CAPACITY_PLANNING — планирование ёмкости
   - QUALITY_ENHANCEMENT — улучшение качества

   Приоритеты: CRITICAL, HIGH, MEDIUM, LOW

   Методы:
   - `generateComprehensiveRecommendations()` → recommendations[]
   - `suggestShiftAdjustments(date)` → adjustments[]
   - `identifyPerformanceBottlenecks()` → bottlenecks[]
   - `recommendCapacityAdjustments()` → adjustments[]

   Recommendation structure:
   ```javascript
   {
     id, type, priority, title, description,
     impact, effort, timeline, actions, metrics,
     confidence // 0-100%
   }
   ```

### Критерии приёмки
- SmartDispatcher: autoAssignRequests назначает заявки исполнителям с score >= 0.6
- WorkloadPredictor: предсказания с учётом сезонных/дневных паттернов
- GeoOptimizer: Haversine distance корректен, маршруты оптимизируются
- RecommendationEngine: генерирует рекомендации всех 7 типов
- Все 4 компонента покрыты unit-тестами

---

## План 09: IoT Integration — Alert→Request Pipeline {#план-09}

### Цель
Реализовать интеграцию InfraSafe IoT с системой заявок UK Bot: автоматическое создание заявок из IoT-алертов.

### Задачи

1. **IntegrationService** (`src/services/integration-service.js`)

   Основной pipeline:
   ```
   IoT Metric → AlertService → IntegrationService → RequestService → NotificationService
   ```

   Маппинг алерт → заявка:

   | InfraSafe alert type | UK Bot категория | Срочность |
   |---------------------|-----------------|-----------|
   | TRANSFORMER_OVERLOAD | Электрика | Средняя |
   | TRANSFORMER_CRITICAL_OVERLOAD | Электрика | Критическая |
   | POWER_FAILURE | Электрика | Критическая |
   | VOLTAGE_ANOMALY | Электрика | Средняя |
   | WATER_LEAK | Сантехника | Критическая |
   | LOW_PRESSURE (water) | Сантехника | Средняя |
   | OVERHEATING | Отопление | Средняя |
   | TEMPERATURE_ANOMALY | Отопление | Средняя |
   | COMMUNICATION_LOST | Техобслуживание | Обычная |

   Маппинг severity → urgency:

   | Severity | Urgency |
   |----------|---------|
   | CRITICAL | Критическая |
   | WARNING | Средняя |
   | INFO | Обычная |

   Методы:
   - `processAlert(alert)` — основной pipeline
   - `mapAlertToRequest(alert)` — конвертация алерта в данные заявки
   - `findBuildingMapping(infraBuildingId)` — поиск соответствия InfraSafe building → UK Yard/Building/Apartment
   - `isDuplicateAlert(alert)` — проверка дублей (cooldown 15 мин, тот же тип + объект)
   - `enrichRequestWithIoTData(request, alert, metric)` — добавление данных датчика в описание заявки

2. **Building Mapping Table**
   - Prisma model `BuildingMapping`:
     - `infra_building_id` FK → Building
     - `yard_id` FK → Yard
     - `building_id` FK → Building (UK context)
     - `default_apartment_id` FK → Apartment (nullable, для автозаявок без конкретной квартиры)
   - Admin UI для маппинга

3. **Alert→Request webhook** — внутренний event flow:
   - AlertService (при создании CRITICAL/WARNING) → Redis PubSub → IntegrationService
   - IntegrationService создаёт Request через RequestService
   - NotificationService уведомляет менеджера/исполнителя

4. **IoT-контекст в заявке**
   - Описание заявки включает данные датчика:
     ```
     [Автоматическая заявка от IoT-мониторинга]
     Тип: Перегрузка трансформатора
     Здание: ул. Навои, 15
     Показания: Загрузка 92%, Напряжение L1=238V L2=235V L3=241V
     Порог: 85%
     Время обнаружения: 2026-03-09 14:32:15
     ```

5. **IoT-верификация ремонта** (Phase 2 — заготовка)
   - После выполнения заявки, созданной из алерта, проверять нормализацию показаний
   - Если метрики вернулись в норму → автоматический лог в комментарий заявки
   - Заготовка в IntegrationService: `verifyRepairByIoT(requestNumber, alertId)`

6. **Telemetry endpoint** (перенос из InfraSafe)
   - `POST /api/metrics/telemetry` — публичный, без аутентификации
   - Rate limit: 120 req/min
   - При вставке метрики: триггер обновления heartbeat + проверка алертов

### Критерии приёмки
- CRITICAL алерт автоматически создаёт заявку
- Маппинг alert_type → category корректен
- Building mapping работает (InfraSafe building → UK Yard/Building)
- Дубли алертов не создают дублей заявок (cooldown)
- Заявка содержит IoT-данные в описании
- Уведомление в Telegram при автозаявке

---

## План 10: Notifications & Scheduling {#план-10}

### Цель
Реализовать систему уведомлений и фоновых задач.

### Задачи

1. **NotificationService** (`src/services/notification-service.js`)

   Каналы:
   - Личное сообщение Telegram (bot.api.sendMessage)
   - Telegram Channel (TELEGRAM_CHANNEL_ID)

   Типы уведомлений (из audit 05):

   | Событие | Получатели |
   |---------|-----------|
   | Новая заявка | Менеджеры, Канал |
   | Смена статуса | Заявитель, Исполнитель, Канал |
   | Запрос материалов | Менеджер |
   | Уточнение | Заявитель |
   | Заявка выполнена | Менеджер, Заявитель |
   | Возврат заявки | Менеджер, Канал |
   | Смена начата/завершена | Исполнитель, Канал |
   | Передача смены | Исполнитель-получатель |
   | Новый пользователь | Администраторы, Канал |
   | IoT-алерт → заявка | Менеджер, Канал (NEW) |

   Методы:
   - `notifyNewRequest(request)` — уведомление о новой заявке
   - `notifyStatusChange(request, oldStatus, newStatus, userId)` — смена статуса
   - `notifyAssignment(request, executorId)` — назначение
   - `notifyCompletion(request)` — выполнение
   - `notifyAcceptance(request, rating)` — приёмка
   - `notifyReturn(request, reason)` — возврат
   - `notifyShiftEvent(shift, event)` — событие смены
   - `notifyNewUser(user)` — новый пользователь
   - `notifyIoTAlert(alert, request)` — IoT-алерт создал заявку (NEW)
   - `sendToChannel(message)` — отправка в канал
   - `sendPersonal(telegramId, message)` — личное сообщение

2. **BullMQ Workers** (`src/jobs/`)

   | Worker | Cron | Описание |
   |--------|------|----------|
   | `auto-create-shifts.js` | `30 0 * * *` (00:30) | Создание смен по шаблонам на следующий день |
   | `rebalance-assignments.js` | `0 6 * * *` (06:00) | Перебалансировка назначений SmartDispatcher |
   | `process-transfers.js` | `*/30 * * * *` (каждые 30 мин) | Обработка ожидающих ShiftTransfer |
   | `cleanup-stale.js` | `0 3 * * *` (03:00) | Очистка устаревших данных |
   | `shift-reminders.js` | `0 7 * * *` (07:00) | Напоминания о предстоящих сменах |
   | `auto-assign-requests.js` | `*/15 * * * *` (каждые 15 мин) | SmartDispatcher.autoAssignRequests() |
   | `sync-assignments.js` | `*/30 * * * *` (каждые 30 мин) | Синхронизация ShiftAssignment |
   | `token-cleanup.js` | `0 * * * *` (каждый час) | Очистка просроченных токенов из blacklist |

3. **BullMQ Setup** (`src/config/bullmq.js`)
   - Queue: `uk-platform-jobs`
   - Worker: процессинг по типу job
   - Scheduler: node-cron триггеры → добавление job в очередь
   - Dashboard: BullMQ Board (опционально, для отладки)

4. **AuditLogService** (`src/services/audit-log-service.js`)
   - `log(action, userId, details)` — запись действия
   - Actions: user_registered, user_approved, user_blocked, request_created, request_status_changed, request_assigned, shift_started, shift_ended, rating_submitted, invite_created, iot_alert_created (NEW)

### Критерии приёмки
- Все 10+ типов уведомлений отправляются
- Сообщения в канал публикуются
- Все 8 BullMQ workers работают по расписанию
- AuditLog записывается при каждом значимом действии
- Workers переживают перезапуск (persistent queue)

---

## План 11: Web Dashboard — Leaflet Map + Analytics {#план-11}

### Цель
Расширить фронтенд InfraSafe (Leaflet-карта) overlay-слоями заявок и исполнителей UK Bot.

### Задачи

1. **Overlay-слой "Заявки"** на карте
   - Маркеры со статусами заявок на здании:
     - Зелёный: здание, нет открытых заявок, показатели в норме
     - Жёлтый: WARNING алерт ИЛИ открытые заявки
     - Красный: CRITICAL алерт, исполнитель в пути
   - Popup при клике: метрики датчиков + список заявок + текущий исполнитель на смене

2. **API endpoint для карты**
   - `GET /api/buildings-metrics` — расширить данными заявок:
     - `active_requests_count` — кол-во активных заявок
     - `latest_request_status` — последний статус
     - `assigned_executor` — имя исполнителя на смене
     - `active_alerts_count` — кол-во активных алертов

3. **Unified Analytics Dashboard** (Chart.js)
   - Корреляция: метрики IoT ↔ заявки (scatter plot)
   - Время реакции: от алерта до создания заявки (bar chart)
   - Нагрузка исполнителей по специализациям (stacked bar)
   - Заявки по статусам за период (pie chart)
   - Предсказание WorkloadPredictor (line chart)

4. **Admin panel расширение**
   - Управление building mappings (InfraSafe ↔ UK)
   - Просмотр IoT-заявок (автосозданных)
   - Статистика pipeline: алертов → заявок → выполнено

5. **Responsive layout**
   - Мобильная оптимизация карты и панелей
   - Touch-friendly элементы управления

### Критерии приёмки
- Карта отображает здания с маркерами статусов заявок
- Popup содержит IoT-метрики + заявки + исполнителя
- Аналитика отображает Chart.js графики
- Admin panel позволяет управлять building mappings

---

## План 12: Payment Integration {#план-12}

### Цель
Интегрировать платёжные системы Узбекистана (Payme/Click) для оплаты ЖКУ.

### Задачи

1. **Payme API integration**
   - Merchant API (создание чека, проверка, подтверждение)
   - Callback endpoint для уведомлений о платежах
   - Telegram-интерфейс: кнопка "Оплатить ЖКУ" → генерация ссылки на оплату

2. **Click API integration**
   - Аналогичная интеграция с Click
   - Fallback: если Payme недоступен

3. **Модель данных**
   - `Payment` — сумма, статус, provider, user_id, apartment_id, period, created_at
   - `PaymentHistory` — история платежей

4. **Bot handler**
   - Просмотр задолженности (API к биллинговой системе — заготовка)
   - Генерация QR-кода для оплаты
   - Подтверждение оплаты (webhook от Payme/Click)

### Критерии приёмки
- Заготовка интеграции с Payme API
- Модель данных Payment создана
- Telegram UI для инициации оплаты работает
- Webhook принимает callback от платёжной системы

---

## План 13: Testing & Security {#план-13}

### Цель
Покрыть критические пути тестами, обеспечить безопасность на уровне OWASP Top 10.

### Задачи

1. **Unit tests** (`tests/unit/`)
   - SmartDispatcher: scoring, assignment, weight calculation
   - WorkloadPredictor: seasonal factors, predictions
   - GeoOptimizer: Haversine distance, route optimization
   - RequestService: status transitions, validation
   - ShiftService: lifecycle transitions
   - InviteService: HMAC generation, validation, nonce
   - IntegrationService: alert→request mapping

2. **Integration tests** (`tests/integration/`)
   - API endpoints: CRUD для всех сущностей
   - Auth flow: login → access → refresh → logout
   - Request lifecycle: create → assign → complete → accept
   - Alert → Request pipeline
   - Building mapping

3. **Security tests** (`tests/security/`)
   - SQL injection attempts
   - XSS payload testing
   - JWT manipulation
   - Rate limiting verification
   - CORS policy
   - Default-deny verification (InfraSafe pattern)

4. **E2E tests** (`tests/e2e/`)
   - Full registration flow через Telegram (mock)
   - Full request lifecycle
   - Shift transfer flow

5. **Security hardening**
   - Input validation: zod schemas на всех API endpoints
   - SQL injection: параметризованные запросы (Prisma handles this)
   - XSS: DOMPurify на сервере и клиенте
   - CORS: whitelist (не wildcard)
   - Rate limiting: 6 лимитеров
   - Helmet: CSP, X-Frame-Options и др.
   - HMAC-SHA256 для инвайтов
   - bcrypt 12 rounds для паролей
   - JWT blacklist (двухуровневый)
   - Telegram Bot API: проверка telegram_id

### Критерии приёмки
- Coverage >= 70% для services/
- Все security tests проходят
- OWASP Top 10 проверки реализованы
- E2E тесты покрывают критические пути

---

## План 14: Security Hardening {#план-14}

### Цель
Финализация безопасности, исправление известных P0 проблем.

### Задачи

1. **CORS**: whitelist origins (не `*`)
2. **HTML escaping**: все user-generated content экранируется перед отображением
3. **Rate limiting**: проверить все endpoints
4. **Secrets management**: все секреты через .env, никогда в коде
5. **Dependency audit**: `npm audit`, обновление уязвимых зависимостей
6. **HTTP headers**: Helmet с продакшн-CSP
7. **File upload validation**: проверка MIME type, размера, вирусов (заготовка)
8. **Telegram Bot security**: проверка source через secret_token (webhook mode)

### Критерии приёмки
- `npm audit` — 0 high/critical уязвимостей
- Все P0 из Security Audit (8.5/10) исправлены
- Penetration test checklist пройден

---

## План 15: DevOps, Docker & Deployment {#план-15}

### Цель
Создать unified Docker Compose, CI/CD pipeline, мониторинг, health checks.

### Задачи

1. **Unified Docker Compose** (`docker-compose.yml`)

   | Сервис | Образ | Порт | Описание |
   |--------|-------|------|----------|
   | `frontend` | Dockerfile.frontend | 8080 | Nginx: статика + proxy |
   | `app` | Dockerfile | 3000 | Express + grammY + BullMQ workers |
   | `postgres` | postgis/postgis:15-3.3 | 5432 | PostgreSQL + PostGIS |
   | `redis` | redis:7-alpine | 6379 | FSM, cache, queue |

   Resources (production):
   - app: 1 CPU, 1GB RAM
   - postgres: 0.5 CPU, 512MB RAM
   - redis: 0.25 CPU, 256MB RAM

2. **Health checks**
   - `/health` — basic (status, timestamp)
   - `/health/detailed` — DB, Redis, Bot, BullMQ workers
   - Docker healthcheck: curl every 30s, 3 retries, start_period 40s

3. **CI/CD** (GitHub Actions)
   - Lint → Test → Build → Deploy
   - Автодеплой на production при push в main
   - PR checks: lint + tests

4. **Monitoring**
   - Winston logs (combined.log, error.log)
   - BullMQ Board (опционально)
   - Prometheus metrics (заготовка)

5. **Migration strategy**
   - `prisma migrate deploy` в production
   - Seed data для первого запуска
   - Backup script для PostgreSQL

6. **Environment configs**
   - `.env.development`
   - `.env.production`
   - `.env.test`

### Критерии приёмки
- `docker-compose up` запускает все сервисы
- Health check проходит для всех компонентов
- Logs пишутся в файлы
- Graceful shutdown работает (SIGTERM)

---

## 6. Матрица миграции компонентов {#6-матрица-миграции}

### Полный маппинг Python → JS файлов

| Python файл | JS файл | План |
|-------------|---------|------|
| `main.py` | `src/server.js` + `src/config/bot.js` | 03 |
| `config/settings.py` | `src/config/settings.js` | 01 |
| `middlewares/auth.py` | `src/bot/middleware/auth.js` | 03 |
| `middlewares/role_mode.py` (NEW) | `src/bot/middleware/role-mode.js` | 03 |
| `middlewares/localization.py` | `src/bot/middleware/localization.js` | 03 |
| `middlewares/shift_context.py` (NEW) | `src/bot/middleware/shift-context.js` | 03 |
| `middlewares/throttling.py` | `src/bot/middleware/throttling.js` | 03 |
| `middlewares/db.py` | N/A (Prisma handles) | — |
| `services/request_service.py` | `src/services/request-service.js` | 06 |
| `services/auth_service.py` | `src/services/auth-service.js` | 04 |
| `services/invite_service.py` | `src/services/invite-service.js` | 04 |
| `services/notification_service.py` | `src/services/notification-service.js` | 10 |
| `services/smart_dispatcher.py` | `src/services/smart-dispatcher.js` | 08 |
| `services/workload_predictor.py` | `src/services/workload-predictor.js` | 08 |
| `services/geo_optimizer.py` | `src/services/geo-optimizer.js` | 08 |
| `services/recommendation_engine.py` | `src/services/recommendation-engine.js` | 08 |
| `services/shift_service.py` (implied) | `src/services/shift-service.js` | 07 |
| `services/shift_transfer_service.py` (implied) | `src/services/shift-transfer-service.js` | 07 |
| `services/shift_planning_service.py` (implied) | `src/services/shift-planning-service.js` | 07 |
| `handlers/requests.py` | `src/bot/handlers/requests.js` | 06 |
| `handlers/request_status_management.py` | `src/bot/handlers/request-status.js` | 06 |
| `handlers/request_assignment.py` | `src/bot/handlers/request-assignment.js` | 06 |
| `handlers/request_acceptance.py` | `src/bot/handlers/request-acceptance.js` | 06 |
| `handlers/request_comments.py` | `src/bot/handlers/request-comments.js` | 06 |
| `handlers/request_reports.py` | `src/bot/handlers/request-reports.js` | 06 |
| `handlers/shift_management.py` | `src/bot/handlers/shift-management.js` | 07 |
| `handlers/my_shifts.py` | `src/bot/handlers/my-shifts.js` | 07 |
| `handlers/shift_transfer.py` | `src/bot/handlers/shift-transfer.js` | 07 |
| `handlers/admin.py` | `src/bot/handlers/admin.js` | 05 |
| `handlers/auth.py` | `src/bot/handlers/auth.js` | 04 |
| `handlers/onboarding.py` | `src/bot/handlers/onboarding.js` | 04 |
| `handlers/user_management.py` | `src/bot/handlers/user-management.js` | 05 |
| `handlers/user_verification.py` | `src/bot/handlers/verification.js` | 05 |
| `handlers/address_*.py` (4 файла) | `src/bot/handlers/address-*.js` | 05 |
| `handlers/user_apartments.py` | `src/bot/handlers/user-apartments.js` | 05 |
| `handlers/user_yards.py` (NEW) | `src/bot/handlers/user-yards.js` | 05 |
| `handlers/health.py` | `src/bot/handlers/health.js` | 03 |
| `handlers/base.py` | `src/bot/handlers/base.js` | 03 |
| `keyboards/*.py` (12+ файлов) | `src/bot/keyboards/*.js` | 03-07 |
| `states/*.py` (12+ FSM groups) | `src/bot/conversations/*.js` | 04-07 |
| `utils/callback_factories.py` | `src/bot/callback-data/*.js` | 03 |
| `utils/enums.py` | `src/utils/enums.js` | 01 |
| `utils/health_server.py` | Express health routes | 03 |
| `utils/redis_rate_limiter.py` | `src/api/middleware/rate-limiter.js` | 03 |
| `config/locales/*.json` | `locales/*.json` | 03 |
| `database/models/*.py` | `prisma/schema.prisma` | 02 |

---

## 7. Критические замечания для исполнителя {#7-критические-замечания}

### 7.1. Архитектурные решения, которые НЕЛЬЗЯ менять

1. **Порядок регистрации роутеров** — критически важен. Первый подходящий handler обрабатывает update. Порядок из раздела 1.5 audit/01 должен быть сохранён.

2. **Формат request_number** — `YYMMDD-NNN`. Это primary key, используется во всех API и интерфейсах. НЕ МЕНЯТЬ.

3. **Двухэтапная приёмка** — менеджер подтверждает → заявитель принимает с оценкой. Бизнес-правило, не упрощать.

4. **Веса SmartDispatcher** — specialization 35%, geo 25%, workload 20%, rating 15%, urgency 5%. Проверены в production.

5. **Invite token format** — `invite_v1:{base64}.{hmac}`. HMAC-SHA256 с INVITE_SECRET.

6. **Статусы заявок** — ровно 8 статусов: Новая, В работе, Закуп, Уточнение, Выполнена, Исполнено, Принято, Отменена. НЕ ПЕРЕИМЕНОВЫВАТЬ (используются в БД и API).

### 7.2. Известные проблемы для исправления при переписывании

1. **Legacy поля** — `user.role` (String) vs `user.roles` (JSON). В новой версии оставить ТОЛЬКО `roles` (JSON array) и `active_role`.

2. **Legacy адреса** — `request.address` (text) и `request.apartment` (string). В новой версии использовать ТОЛЬКО `apartment_id` FK.

3. **SQLite fallback** — убрать. Только PostgreSQL.

4. **MemoryStorage fallback** — убрать. Только Redis.

5. **Google Sheets** — не переносить (отключено).

6. **db_middleware** — не нужен с Prisma (Prisma управляет соединениями).

### 7.3. Рекомендации по реализации

1. **Начинать с Plan 01-03** — без фундамента ничего не работает.

2. **Каждый план завершать smoke-тестом** — не переходить к следующему без проверки.

3. **Prisma + PostGIS** — Prisma не поддерживает PostGIS нативно. Для геопространственных запросов использовать `prisma.$queryRaw`. Для CRUD — стандартный Prisma API.

4. **grammY conversations** — мощнее FSM в aiogram. Один conversation = один полный flow (не нужно разбивать на отдельные states).

5. **BullMQ** — надёжнее APScheduler (persistent, retries, dead letter queue). Использовать для ВСЕХ фоновых задач.

6. **TypeScript vs JavaScript** — рекомендуется JavaScript с JSDoc для type hints. Полный TypeScript добавляет complexity, а Prisma уже обеспечивает type safety для data layer.

7. **Параллельная работа** — планы одной фазы выполнять последовательно. Планы разных фаз (12-14) можно параллелить.

### 7.4. Порядок выполнения (для Claude Opus 4.6)

```
Фаза 1 (строго последовательно):
  Plan 01 → Plan 02 → Plan 03 → Plan 04

Фаза 2 (05 последовательно, 06-07 параллельно после 05, 08 после 06+07):
  Plan 05 → Plan 06 ─┐
             Plan 07 ─┤→ Plan 08
                      │
Фаза 3 (09 после 06, 10 после 06+07, 11 после 09):
  Plan 09 → Plan 11
  Plan 10

Фаза 4 (параллельно):
  Plan 12 | Plan 13 | Plan 14 → Plan 15
```

### 7.5. Контрольные точки (checkpoints)

| Checkpoint | После плана | Что проверить |
|------------|-------------|---------------|
| **CP1: Foundation** | Plan 03 | Bot стартует, middleware работает, /health отвечает |
| **CP2: Auth works** | Plan 04 | Инвайт → регистрация → approve → главное меню |
| **CP3: Core CRUD** | Plan 06 | Создание заявки → назначение → выполнение → приёмка |
| **CP4: Shifts** | Plan 07 | Создание смены → старт → завершение, передача |
| **CP5: AI works** | Plan 08 | Автоназначение заявок SmartDispatcher |
| **CP6: IoT pipeline** | Plan 09 | IoT алерт → автоматическая заявка в Telegram |
| **CP7: Full product** | Plan 11 | Карта + заявки + IoT на одном экране |
| **CP8: Production** | Plan 15 | Docker запускается, все health checks зелёные |

---

## Приложения

### A. Enums Reference

```javascript
// src/utils/enums.js

const RequestStatus = {
  NEW: 'Новая',
  IN_PROGRESS: 'В работе',
  PURCHASE: 'Закуп',
  CLARIFICATION: 'Уточнение',
  COMPLETED: 'Выполнена',
  FULFILLED: 'Исполнено',
  ACCEPTED: 'Принято',
  CANCELLED: 'Отменена',
};

const UserStatus = { PENDING: 'pending', APPROVED: 'approved', BLOCKED: 'blocked' };
const UserRole = { APPLICANT: 'applicant', EXECUTOR: 'executor', MANAGER: 'manager' };
const ShiftStatus = { PLANNED: 'planned', ACTIVE: 'active', PAUSED: 'paused', COMPLETED: 'completed', CANCELLED: 'cancelled' };
const ShiftType = { REGULAR: 'regular', EMERGENCY: 'emergency', OVERTIME: 'overtime', MAINTENANCE: 'maintenance', SECURITY: 'security' };
const ShiftTransferStatus = { PENDING: 'pending', ASSIGNED: 'assigned', ACCEPTED: 'accepted', REJECTED: 'rejected', COMPLETED: 'completed', CANCELLED: 'cancelled' };
const TransferReason = { ILLNESS: 'illness', EMERGENCY: 'emergency', WORKLOAD: 'workload', VACATION: 'vacation', OTHER: 'other' };
const VerificationStatus = { PENDING: 'pending', VERIFIED: 'verified', REJECTED: 'rejected', REQUESTED: 'requested' };
const UserApartmentStatus = { PENDING: 'pending', APPROVED: 'approved', REJECTED: 'rejected' };
const QuarterlyPlanStatus = { DRAFT: 'draft', ACTIVE: 'active', ARCHIVED: 'archived', CANCELLED: 'cancelled' };
const ScheduleType = { DUTY_24_3: 'duty_24_3', WORKDAY_5_2: 'workday_5_2', SHIFT_2_2: 'shift_2_2', FLEXIBLE: 'flexible' };
const CommentType = { STATUS_CHANGE: 'status_change', CLARIFICATION: 'clarification', PURCHASE: 'purchase', REPORT: 'report' };
const DocumentType = { PASSPORT: 'passport', PROPERTY_DEED: 'property_deed', RENTAL_AGREEMENT: 'rental_agreement', UTILITY_BILL: 'utility_bill', OTHER: 'other' };
const AccessLevel = { APARTMENT: 'apartment', HOUSE: 'house', YARD: 'yard' };
const Urgency = { NORMAL: 'Обычная', MEDIUM: 'Средняя', URGENT: 'Срочная', CRITICAL: 'Критическая' };
const Category = { ELECTRIC: 'Электрика', PLUMBING: 'Сантехника', HVAC: 'Отопление', CLEANING: 'Уборка', SECURITY: 'Безопасность', MAINTENANCE: 'Техобслуживание' };
const Specialization = { ELECTRIC: 'electric', PLUMBING: 'plumbing', HVAC: 'hvac', CLEANING: 'cleaning', SECURITY: 'security', MAINTENANCE: 'maintenance', UNIVERSAL: 'universal', OTHER: 'other' };

// InfraSafe enums
const AlertSeverity = { INFO: 'INFO', WARNING: 'WARNING', CRITICAL: 'CRITICAL' };
const AlertStatus = { ACTIVE: 'active', ACKNOWLEDGED: 'acknowledged', RESOLVED: 'resolved' };
const InfraUserRole = { ADMIN: 'admin', OPERATOR: 'operator', USER: 'user' };
const ControllerStatus = { ONLINE: 'online', OFFLINE: 'offline', MAINTENANCE: 'maintenance' };
```

### B. Специализация ↔ Категория (маппинг)

| Категория заявки | Специализация исполнителя | IoT alert type |
|-----------------|--------------------------|----------------|
| Электрика | electric | TRANSFORMER_OVERLOAD, POWER_FAILURE, VOLTAGE_ANOMALY |
| Сантехника | plumbing | WATER_LEAK, LOW_PRESSURE |
| Отопление | hvac | OVERHEATING, TEMPERATURE_ANOMALY |
| Уборка | cleaning | — |
| Безопасность | security | — |
| Техобслуживание | maintenance | COMMUNICATION_LOST |

### C. Ссылки на исходные документы

- `audit/01_architecture_overview.md` — текущая архитектура UK Bot
- `audit/02_entities_and_lifecycle.md` — модель данных UK Bot
- `audit/03_request_lifecycle.md` — жизненный цикл заявки
- `audit/04_user_registration_and_auth.md` — аутентификация
- `audit/05_business_processes.md` — бизнес-процессы
- `audit/06_api_and_integrations.md` — API
- `audit/07_market_analysis_and_product_maturity.md` — рыночный анализ
- `audit/08_integration_feasibility_UK_InfraSafe.md` — анализ объединения
- `InfraSafe/docs/refactor/TECHNICAL_SPECIFICATION.md` — ТЗ InfraSafe
- `InfraSafe/docs/refactor/UK_INTEGRATION_REVIEW.md` — обзор интеграции
