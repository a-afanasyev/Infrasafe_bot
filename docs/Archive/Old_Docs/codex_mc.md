# 🏗️ UK Management Bot — Microservices Architecture & Migration Plan

> _Последнее редактирование: 2025-10-29_

## 1. Executive Summary
- 📦 **Initial State**: Pre-production monolith with rich modular services (Telegram bot, business services, ORM models).  
- 🎯 **Objective**: Deliver a production-ready microservice ecosystem in a single 18-week program owned by Codex (architecture/devops) and Opus (QA/automation).
- 🔑 **Key Principles**: Domain boundaries, API-first contracts, event-driven collaboration, database-per-service, zero shared state, automation-first delivery.

---

## 2. Target Microservice Architecture
```
API Gateway / Bot BFF
├── Auth Service
├── User & Verification Service
├── Request Lifecycle Service
├── Assignment & AI Service
├── Shift Planning Service
├── Notification Service
├── Media Service (existing FastAPI)
├── Integration Hub
└── Analytics & Reporting Service
```

### Service Responsibilities
| Service | Core Scope | Data Store | Interfaces |
|---------|------------|------------|------------|
| **API Gateway / Bot BFF** | Telegram webhook, REST routing, rate limiting, JWT validation | Stateless | Telegram API, REST/gRPC to downstream services |
| **Auth Service** | Credentials, MFA, token lifecycle | PostgreSQL (`auth_db`), Redis sessions | `/auth/*`, JWT issuer |
| **User & Verification** | Profiles, roles, documents, verification workflows | PostgreSQL (`users_db`), MinIO/S3 | `/users/*`, `/verification/*`, events `user.*` |
| **Request Lifecycle** | Tickets, comments, attachments metadata, statuses | PostgreSQL (`requests_db`) | `/requests/*`, `/comments/*`, events `request.*` |
| **Assignment & AI** | Smart dispatcher, geo/ML optimizers, SLA metrics | PostgreSQL (`assignments_db`), Redis cache | `/assignments/*`, consumes `request.*`, emits `assignment.*` |
| **Shift Planning** | Templates, schedules, transfers, quarterly planning | PostgreSQL (`shifts_db`) | `/shifts/*`, events `shift.*` |
| **Notification** | Telegram/email/SMS delivery, templating, throttling | PostgreSQL (`notifications_db`), Redis queues | `/notifications/*`, channel webhooks |
| **Media** | Upload, storage, virus scanning (already exists) | MinIO/S3 bucket | `/media/*` |
| **Integration Hub** | Google Sheets sync, CRM/webhook adapters | PostgreSQL (`integration_db`) | Event consumer/producer, outbound webhooks |
| **Analytics & Reporting** | Aggregations, dashboards, exports | ClickHouse / BigQuery-lite | `/analytics/*`, event consumers |

Cross-cutting platform: RabbitMQ, OpenTelemetry, Vault, Consul/Kubernetes, Terraform + Helm, GitHub Actions + ArgoCD, schema registry (JSON/Protobuf).

---

## 3. Migration Timeline (18 Weeks)
Each sprint spans two weeks. Codex leads engineering; Opus ensures automated coverage.

1. **Sprints 1–2 — Foundations**  
   Stand up Kubernetes sandbox, shared observability, broker, Vault. Build service templates and Telegram gateway shell; instrument monolith with OpenTelemetry.
2. **Sprints 3–4 — Notifications & Media**  
   Extract Notification service; harden Media service (auth, signed URLs). Monolith publishes `notification.requested` via outbox pattern.
3. **Sprints 5–6 — Auth + User Domain**  
   Launch Auth service and migrate accounts. Deliver User & Verification service and migrate user data. Replace monolith DB access with service clients.
4. **Sprints 7–8 — Request Lifecycle**  
   Create Request service with `request_number` schema; migrate tickets/comments; retire monolith handlers in that domain.
5. **Sprints 9–10 — Assignment & AI**  
   Move smart dispatcher/optimizer logic into dedicated service; wire up events for automated assignments and SLA tracking.
6. **Sprints 11–12 — Shift Planning**  
   Migrate shift templates, schedules, transfers. Implement sagas for capacity updates triggered by assignments.
7. **Sprints 13–14 — Integration & Analytics**  
   Rebuild Google Sheets/CRM sync in Integration Hub; launch Analytics service consuming domain events.
8. **Sprints 15–16 — Gateway & Cleanup**  
   Complete Telegram gateway transition, decommission monolith endpoints, freeze legacy DB (read-only), perform load and security testing.
9. **Sprints 17–18 — Production Readiness**  
   Finalize runbooks, dashboards, SLOs. Run chaos and backup drills. Opus executes regression; Codex runs go-live rehearsal.

---

## 4. Workstreams & Task Backlog

### Platform & Infrastructure
- Provision Kubernetes cluster, Postgres instances, RabbitMQ, MinIO, Vault, observability stack.
- Create Terraform/Helm manifests and CI/CD pipelines for each service.
- Implement API gateway (Kong/Traefik) with JWT validation.
- Set up schema registry, event SDK, contract-testing tooling.

### Service Delivery
1. Notification service extraction (REST API, queue workers, templating).  
2. Media service hardening (auth middleware, signed URL issuance, antivirus integration).  
3. Auth service (login, refresh, MFA, session management).  
4. User service (CRUD, roles, verification workflows, document storage).  
5. Request service (ticket lifecycle, comments, attachments, history).  
6. Assignment & AI service (auto assign, geo optimization, workload prediction).  
7. Shift service (templates, schedules, transfers, quarterly planning).  
8. Integration hub (Sheets sync, webhook orchestration).  
9. Analytics service (event ingestion, aggregation, reporting APIs).

### Migration & Data Tasks
- Define `request_number` enforcement, remove legacy `request_id` artifacts.
- Build dual-write/dual-read adapters for transitional periods.
- Develop data migration scripts + validation reports per domain.
- Archive legacy tables after cutover; maintain read-only snapshot.

### Quality & Operations
- Build automated tests: unit, contract, integration, end-to-end flows.  
- Publish OpenAPI specs + test harnesses.  
- Establish observability dashboards, alert policies, SLOs.  
- Run security audits (mTLS, RBAC, secret scanning).  
- Prepare runbooks, on-call rotations, and incident workflows.

---

## 5. Risk & Mitigation Highlights
| Risk | Mitigation |
|------|------------|
| Residual `request_id` usage | Static analysis + migration scripts; fail deployment if legacy columns detected |
| Two-team bandwidth | Enforce WIP limits, shared sprint rituals, automation-first testing |
| Event schema drift | Adopt transactional outbox + schema registry + CI contract tests |
| Security gaps | Vault integration sprint 1; enable mTLS, network policies post-auth rollout |
| Migration errors | Dry-run in sandbox, checksum comparisons, automated validation post-cutover |

---

## 6. Immediate Next Actions (Week 0)
1. Ratify this blueprint with stakeholders.  
2. Provision sandbox infrastructure and smoke-test Notification service skeleton through pipeline.  
3. Draft OpenAPI contracts for Auth, User, Request services before Sprint 3.  
4. Launch shared documentation hub (architecture diagrams, service ownership, runbooks).  
5. Instrument monolith to emit domain events ahead of service extraction.

---

# 🏗️ UK Management Bot — Архитектура микросервисов и план миграции
## 1. Исполнительное резюме
- 📦 **Текущее состояние**: Предпродовый монолит с богатым набором модулей (Telegram-бот, бизнес-сервисы, ORM модели).  
- 🎯 **Цель**: В течение одной 18-недельной программы развернуть архитектуру микросервисов силами Codex (архитектура/DevOps) и Opus (QA/автоматизация).  
- 🔑 **Принципы**: Границы доменов, контракты API-first, событийное взаимодействие, отдельные БД, отсутствие общего состояния, автоматизация с первого дня.

---

## 2. Целевая архитектура микросервисов
```
API Gateway / Bot BFF
├── Auth Service
├── User & Verification Service
├── Request Lifecycle Service
├── Assignment & AI Service
├── Shift Planning Service
├── Notification Service
├── Media Service (существующий FastAPI)
├── Integration Hub
└── Analytics & Reporting Service
```

### Ответственности сервисов
| Сервис | Основная зона | Хранилище | Интерфейсы |
|--------|---------------|-----------|------------|
| **API Gateway / Bot BFF** | Telegram webhook, маршрутизация REST, лимитирование, проверка JWT | Stateless | Telegram API, REST/gRPC вниз по цепочке |
| **Auth Service** | Учетные данные, MFA, жизненный цикл токенов | PostgreSQL (`auth_db`), Redis sessions | `/auth/*`, выдача JWT |
| **User & Verification** | Профили, роли, документы, верификация | PostgreSQL (`users_db`), MinIO/S3 | `/users/*`, `/verification/*`, события `user.*` |
| **Request Lifecycle** | Заявки, комментарии, метаданные вложений, статусы | PostgreSQL (`requests_db`) | `/requests/*`, `/comments/*`, события `request.*` |
| **Assignment & AI** | Smart dispatcher, ML/гео оптимизация, SLA | PostgreSQL (`assignments_db`), Redis cache | `/assignments/*`, потребляет `request.*`, публикует `assignment.*` |
| **Shift Planning** | Шаблоны смен, расписания, переводы, квартальное планирование | PostgreSQL (`shifts_db`) | `/shifts/*`, события `shift.*` |
| **Notification** | Доставка (Telegram/email/SMS), шаблоны, тротлинг | PostgreSQL (`notifications_db`), Redis очереди | `/notifications/*`, webhooks каналов |
| **Media** | Загрузка, хранение, антивирус (уже есть) | MinIO/S3 bucket | `/media/*` |
| **Integration Hub** | Google Sheets, CRM, внешние webhooks | PostgreSQL (`integration_db`) | Потребление/публикация событий, внешние вебхуки |
| **Analytics & Reporting** | Агрегаты, дашборды, экспорт | ClickHouse / BigQuery-lite | `/analytics/*`, потребители событий |

Платформа: RabbitMQ, OpenTelemetry, Vault, Consul/Kubernetes, Terraform + Helm, GitHub Actions + ArgoCD, реестр схем (JSON/Protobuf).

---

## 3. План миграции (18 недель)
Каждый спринт длится две недели. Codex отвечает за разработку, Opus — за автоматизацию и тестирование.

1. **Спринты 1–2 — Фундаменты**  
   Развертывание Kubernetes-песочницы, наблюдаемости, брокера, Vault. Создание шаблонов сервисов и оболочки Telegram gateway; инструментирование монолита OpenTelemetry.
2. **Спринты 3–4 — Уведомления и медиа**  
   Выделение Notification service; усиление Media service (авторизация, подписанные ссылки). Монолит публикует `notification.requested` через outbox.
3. **Спринты 5–6 — Auth + User**  
   Запуск Auth service и миграция аккаунтов. Реализация User & Verification service и перенос данных. Замена доступа к БД монолита на обращения к сервисам.
4. **Спринты 7–8 — Request Lifecycle**  
   Создание сервиса заявок с новой схемой `request_number`; миграция заявок/комментариев; отключение соответствующих обработчиков в монолите.
5. **Спринты 9–10 — Assignment & AI**  
   Перенос smart dispatcher/optimizer в отдельный сервис; настройка событий для автоматических назначений и SLA.
6. **Спринты 11–12 — Shift Planning**  
   Миграция шаблонов, расписаний, переводов смен. Реализация саг для координации загрузки.
7. **Спринты 13–14 — Integration & Analytics**  
   Перезапуск Google Sheets/CRM синхронизаций в Integration Hub; запуск Analytics service.
8. **Спринты 15–16 — Gateway и очистка**  
   Полный переход Telegram gateway, выключение эндпоинтов монолита, заморозка старой БД (read-only), нагрузочные и секьюрити тесты.
9. **Спринты 17–18 — Готовность к продакшену**  
   Runbook'и, дашборды, SLO. Chaos и backup-тесты. Регрессия от Opus; репетиция запуска от Codex.

---

## 4. Направления работ и backlog

### Платформа и инфраструктура
- Provision: Kubernetes, Postgres, RabbitMQ, MinIO, Vault, Observability.  
- Terraform/Helm манифесты, CI/CD пайплайны на сервис.  
- API gateway (Kong/Traefik) с проверкой JWT.  
- Реестр схем, SDK событий, инструменты контрактного тестирования.

### Доставка сервисов
1. Notification service (REST API, очереди, шаблоны).  
2. Media service hardening (auth, подписанные ссылки, антивирус).  
3. Auth service (логин, refresh, MFA, сессии).  
4. User service (CRUD, роли, верификация, документы).  
5. Request service (жизненный цикл, комментарии, вложения, история).  
6. Assignment & AI service (автоназначение, гео, прогноз).  
7. Shift service (шаблоны, расписания, переводы, планирование).  
8. Integration hub (Sheets, webhooks, CRM).  
9. Analytics service (ингест событий, агрегации, API).

### Миграции и данные
- Жесткая фиксация `request_number`, удаление `request_id`.  
- Dual-write/read адаптеры для переходного периода.  
- Скрипты миграций + отчеты валидации по доменам.  
- Архивирование легаси таблиц после cutover (read-only снимок).

### Качество и эксплуатация
- Автотесты: unit, контрактные, интеграционные, end-to-end.  
- Публикация OpenAPI и тестовых стендов.  
- Observability: дашборды, алерты, SLO.  
- Security: mTLS, сетевые политики, секрет-скан.  
- Runbook'и, on-call, реакция на инциденты.

---

## 5. Риски и снижения
| Риск | Митигирующая мера |
|------|-------------------|
| Остатки `request_id` | Статический анализ + миграционные скрипты, fail deployment при обнаружении |
| Ограниченная команда | WIP лимиты, общие церемонии спринта, тестирование через автоматизацию |
| Дрейф схем событий | Transactional outbox + реестр схем + контрактные тесты в CI |
| Паузы по безопасности | Vault интеграция в спринте 1, включение mTLS и policy после релиза Auth |
| Ошибки миграций | Прогоны в песочнице, сравнения checksum, автоматическая валидация после cutover |

---

## 6. Ближайшие шаги (Неделя 0)
1. Утвердить документ с заинтересованными сторонами.  
2. Развернуть инфраструктурную песочницу и прогнать скелет Notification сервиса через pipeline.  
3. Подготовить OpenAPI контракты Auth/User/Request до начала спринта 3.  
4. Запустить хаб документации (диаграммы, владение сервисами, runbook'и).  
5. Внедрить в монолит публикацию событий домена до выделения сервисов.

---

*Document authored by Codex (GPT-5) — 23 September 2025*
