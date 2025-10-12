# Техническое задание: Core Service

## 1. Общее описание

### 1.1 Назначение
Core Service - центральный сервис системы управления, объединяющий функции аутентификации, управления пользователями и обработки заявок.

### 1.2 Цели
- Централизация базовых функций системы
- Обеспечение единой точки входа для аутентификации
- Управление жизненным циклом заявок
- Минимизация дублирования кода

### 1.3 Ключевые характеристики
- **Порт**: 8001
- **Тип нагрузки**: Сбалансированная (50% чтение, 50% запись)
- **Критичность**: Высокая (core functionality)
- **Масштабирование**: Горизонтальное

## 2. Функциональные требования

### 2.1 Модуль аутентификации

#### 2.1.1 JWT Authentication
- Генерация JWT токенов с настраиваемым TTL
- Refresh token механизм
- Blacklist для отозванных токенов
- Поддержка multiple sessions per user

#### 2.1.2 OAuth2 Support
- Authorization Code flow
- Client Credentials flow
- Интеграция с внешними провайдерами (Google, GitHub)

#### 2.1.3 Multi-Factor Authentication (MFA)
- TOTP (Time-based One-Time Password)
- SMS verification (опционально)
- Backup codes

#### 2.1.4 API Keys Management
- Генерация API ключей для сервисов
- Rate limiting per API key
- Scopes и permissions

### 2.2 Модуль управления пользователями

#### 2.2.1 User Management
- CRUD операции для пользователей
- Профили с расширенными атрибутами
- Аватары и файлы пользователей
- Soft delete с возможностью восстановления

#### 2.2.2 Role-Based Access Control (RBAC)
- Роли: applicant, executor, manager, admin
- Динамические permissions
- Наследование ролей
- Временные роли с expiration

**Политика множественных ролей (Q1.1)**

**Принято решение**: При наличии у пользователя нескольких ролей применяется вариант "Максимальные привилегии"

**Приоритет ролей** (от высшего к низшему):
1. **admin** - полный доступ ко всем функциям
2. **manager** - управление заявками, пользователями, отчеты
3. **executor** - выполнение заявок, смены, отчеты о работе
4. **applicant** - создание заявок, просмотр своих заявок

**Правила доступа**:
- Все роли могут создавать заявки
- Права определяются по роли с максимальными привилегиями
- Территориальные ограничения применяются только к роли executor
- История действий логируется с указанием активной роли

#### 2.2.3 User Verification (Q1.2)

**Политика хранения верификационных документов**:
- Хранение: в стране использования системы, без трансграничной передачи
- Попытки верификации: 3 попытки
- Блокировка: 30 дней после 3 отклонений
- Удаление документов: сразу после принятия решения (одобрено/отклонено)
- Шифрование: в покое (encryption at rest)
- Compliance: согласно локальному законодательству

**Верификационный процесс**:
- Email verification - обязательный
- Phone verification - обязательный
- Document verification workflow - паспорт + селфи
- Attempts tracking - максимум 3 попытки
- Auto-cleanup - немедленное удаление после решения
- KYC (Know Your Customer) процесс

#### 2.2.4 User Activity
- Activity log
- Last seen tracking
- Device management
- Session management

### 2.3 Модуль управления заявками

#### 2.3.1 Request Lifecycle (Q2.1)

**Создание и управление заявкой**:
- Создание заявки с уникальным номером (YYMMDD-NNN)
- Версионирование изменений
- Архивирование старых заявок

**Статусы заявок**:
- `new` - Новая заявка
- `in_progress` - В работе
- `purchase` - Требуется закуп материалов
- `clarification` - Требуется уточнение у заявителя
- `completed` - Выполнена (ожидает подтверждения)
- `confirmed` - Подтверждена заявителем
- `cancelled` - Отменена

**Матрица переходов статусов**:
```
new → in_progress / clarification / cancelled
in_progress → purchase / completed / cancelled / clarification
purchase → in_progress
clarification → in_progress / cancelled
completed → confirmed / in_progress (возврат при недовольстве)
confirmed → [final state]
cancelled → [final state]
```

**Правила переходов**:
- Возврат из "completed" в "in_progress" разрешен если заявитель не принял работу
- Автовозврата из "clarification" НЕТ - исполнитель/менеджер уточняют вручную
- Неактивные заявки требуют актуализации раз в неделю (напоминание)
- Автоматическая отмена/закрытие неактивных заявок НЕ производится
- Уточнения от имени исполнителя с указанием источника информации

#### 2.3.2 Request Number Generation
- Атомарная генерация номеров
- Формат: YYMMDD-NNN (250918-001)
- Сброс счетчика каждый день
- Резервирование диапазонов номеров

#### 2.3.3 Request Processing
- Валидация входных данных
- Бизнес-правила проверки
- Автоматическое заполнение полей
- Шаблоны заявок

#### 2.3.4 Assignment Management
- Назначение исполнителей
- История назначений
- Передача заявок между исполнителями
- Автоматический выбор исполнителя (базовый)

#### 2.3.5 Comments System
- Древовидные комментарии
- Упоминания пользователей (@mentions)
- Файлы в комментариях
- Редактирование и удаление

#### 2.3.6 Request Search & Filters (Q7.1)

**MVP (Phase 1)** - Без полнотекстового поиска:
- Поиск по request_number (точное совпадение)
- Поиск по метаданным (status, category, urgency)
- Фильтры по всем полям
- Сохраненные фильтры
- Экспорт результатов

**Будущее (Phase 3)** - ElasticSearch:
- Полнотекстовый поиск по описанию и комментариям
- Морфологический анализ
- Поддержка локали (RU/UZ/EN)
- Fuzzy search
- Faceted search

## 3. API Specifications

### 3.1 RESTful API

#### Authentication Endpoints
```
POST   /api/v1/auth/login
POST   /api/v1/auth/logout
POST   /api/v1/auth/refresh
POST   /api/v1/auth/verify
POST   /api/v1/auth/mfa/setup
POST   /api/v1/auth/mfa/verify
POST   /api/v1/auth/password/reset
POST   /api/v1/auth/password/change
```

#### Users Endpoints
```
GET    /api/v1/users
GET    /api/v1/users/{id}
POST   /api/v1/users
PUT    /api/v1/users/{id}
DELETE /api/v1/users/{id}
GET    /api/v1/users/{id}/roles
POST   /api/v1/users/{id}/roles
DELETE /api/v1/users/{id}/roles/{role_id}
GET    /api/v1/users/{id}/sessions
DELETE /api/v1/users/{id}/sessions/{session_id}
POST   /api/v1/users/{id}/verify
GET    /api/v1/users/{id}/activity
```

#### Requests Endpoints
```
GET    /api/v1/requests
GET    /api/v1/requests/{request_number}
POST   /api/v1/requests
PUT    /api/v1/requests/{request_number}
DELETE /api/v1/requests/{request_number}
POST   /api/v1/requests/{request_number}/assign
POST   /api/v1/requests/{request_number}/status
GET    /api/v1/requests/{request_number}/history
POST   /api/v1/requests/{request_number}/comments
GET    /api/v1/requests/{request_number}/comments
PUT    /api/v1/requests/{request_number}/comments/{id}
DELETE /api/v1/requests/{request_number}/comments/{id}
```

### 3.2 GraphQL API (опционально)
- Schema для всех сущностей
- Subscriptions для real-time updates
- Батching и caching
- Фрагменты и директивы

### 3.3 gRPC API (для межсервисного взаимодействия)
- Proto файлы для всех сервисов
- Streaming для больших данных
- Bi-directional streaming для real-time

## 4. Асинхронные задачи

### 4.1 Очереди и приоритеты

#### HIGH Priority (9-10)
- `core.auth.revoke` - Отзыв токенов
- `core.request.urgent` - Срочные заявки

#### MEDIUM Priority (4-8)
- `core.request.create` - Создание заявки
- `core.user.verify` - Верификация пользователя
- `core.request.assign` - Назначение исполнителя

#### LOW Priority (1-3)
- `core.user.cleanup` - Очистка старых сессий
- `core.request.archive` - Архивирование заявок

### 4.2 Saga Patterns

#### Request Creation Saga
1. Валидация данных
2. Генерация номера
3. Создание в БД
4. Публикация события `request.created`
5. Запуск assignment процесса
6. Отправка уведомлений
7. Компенсация при ошибках

## 5. События и интеграции

### 5.1 Публикуемые события
```
auth.login
auth.logout
auth.token.revoked
user.created
user.updated
user.deleted
user.verified
user.role.changed
request.created
request.updated
request.assigned
request.status.changed
request.completed
request.cancelled
comment.added
comment.updated
comment.deleted
```

### 5.2 Подписки на события
```
operations.assignment.completed
operations.executor.available
communication.notification.delivered
media.file.uploaded
```

### 5.3 Webhooks
- Настраиваемые webhooks для внешних систем
- Retry механизм с exponential backoff
- Подпись запросов (HMAC-SHA256)
- Event filtering

## 6. Безопасность

### 6.1 Аутентификация и авторизация
- JWT с RS256 подписью
- Token rotation
- IP whitelisting
- Rate limiting по IP и user

### 6.2 Защита данных
- Шифрование sensitive данных в БД
- Маскирование PII в логах
- Audit trail для всех операций
- GDPR compliance (right to be forgotten)

### 6.3 Защита API
- Input validation
- SQL injection prevention
- XSS protection
- CSRF tokens
- CORS configuration

## 7. Производительность

### 7.1 Требования
- Response time: < 100ms (p95)
- Throughput: 1000 RPS
- Concurrent users: 10,000
- Database connections: 20-50

### 7.2 Оптимизации
- Connection pooling
- Query optimization
- Кеширование в Redis
- Lazy loading
- Pagination
- Batch operations

### 7.3 Кеширование
- User sessions: 15 min
- User profiles: 5 min
- Permissions: 10 min
- Request list: 1 min
- Static data: 1 hour

## 8. Мониторинг и логирование

### 8.1 Метрики
- Request rate по endpoint
- Response time по endpoint
- Error rate
- Active users
- Request creation rate
- Authentication failures

### 8.2 Логирование
- Structured logging (JSON)
- Correlation IDs
- User context
- Request/Response logging
- Error stack traces

### 8.3 Health Checks
```
GET /health          - Basic health
GET /health/ready    - Readiness probe
GET /health/live     - Liveness probe
GET /health/details  - Detailed status
```

## 9. База данных

### 9.1 Схема данных

#### Users Table
- id (UUID)
- email
- phone
- password_hash
- first_name
- last_name
- avatar_url
- verified_at
- created_at
- updated_at
- deleted_at

#### Roles Table
- id
- name
- permissions (JSON)
- created_at

#### User_Roles Table
- user_id
- role_id
- assigned_at
- expires_at

#### Requests Table
- request_number (PK, String)
- title
- description
- category
- urgency
- status
- applicant_id
- executor_id
- metadata (JSON)
- created_at
- updated_at
- completed_at

#### Comments Table
- id
- request_number
- user_id
- parent_id
- content
- attachments (JSON)
- created_at
- updated_at
- deleted_at

#### Sessions Table
- id
- user_id
- token_hash
- ip_address
- user_agent
- expires_at
- created_at

### 9.2 Индексы
- users(email)
- users(phone)
- requests(status, created_at)
- requests(applicant_id)
- requests(executor_id)
- comments(request_number)
- sessions(user_id, expires_at)

### 9.3 Миграции
- Версионирование схемы
- Rollback capability
- Zero-downtime migrations
- Data migrations

## 10. Тестирование

### 10.1 Unit Tests
- Покрытие > 80%
- Все бизнес-логика
- Валидаторы
- Утилиты

### 10.2 Integration Tests
- API endpoints
- Database operations
- Cache operations
- Message queue

### 10.3 Load Tests
- Concurrent users: 1000
- Duration: 30 min
- Scenarios: login, create request, list requests

### 10.4 Security Tests
- Penetration testing
- OWASP Top 10
- Dependency scanning

## 11. Deployment

### 11.1 Конфигурация
- Environment variables
- Config files
- Secrets management
- Feature flags

### 11.2 Контейнеризация
- Multi-stage builds
- Минимальный base image
- Non-root user
- Health checks

### 11.3 Зависимости
- PostgreSQL 15+
- Redis 7+
- RabbitMQ 3.12+

### 11.4 Масштабирование
- Horizontal scaling: 2-10 instances
- Auto-scaling по CPU/Memory
- Load balancing
- Session affinity (опционально)

## 12. Документация

### 12.1 API Documentation
- OpenAPI 3.0 specification
- Interactive documentation (Swagger UI)
- Code examples
- SDKs для популярных языков

### 12.2 Developer Guide
- Architecture overview
- Setup instructions
- Configuration guide
- Troubleshooting

### 12.3 User Guide
- API usage examples
- Authentication flow
- Rate limits
- Error codes

## 13. SLA

### 13.1 Availability
- Uptime: 99.9%
- Planned maintenance: < 4 hours/month
- Incident response: < 15 min

### 13.2 Performance
- API response: < 100ms (p95)
- Batch operations: < 5s
- File upload: < 10s

### 13.3 Data
- RPO: 1 hour
- RTO: 4 hours
- Backup retention: 30 days

## 14. Риски и ограничения

### 14.1 Технические риски
- Single point of failure для auth
- Token theft
- Database bottleneck

### 14.2 Митигация
- Redis cluster для сессий
- Short-lived tokens
- Read replicas для БД

### 14.3 Ограничения (Q4.2)

**Текстовые поля**:
- Описание заявки: 10-2000 символов
- Комментарий: 5-1000 символов
- Причина отмены: 10-500 символов
- ФИО: 5-100 символов

**Форматирование**:
- Emoji: ✅ разрешены
- Markdown: ❌ не поддерживается
- HTML: ❌ запрещен
- Спецсимволы: экранируются

**Другие лимиты**:
- Max request size: 10MB
- Max comments per request: 1000
- Max file size: 50MB
- Rate limit: 1000 req/min per user

## 15. Roadmap

### Phase 1 (MVP)
- Basic authentication
- User CRUD
- Request CRUD
- Simple assignment

### Phase 2
- MFA
- Advanced search
- Batch operations
- Webhooks

### Phase 3
- OAuth2 providers
- GraphQL API
- Real-time subscriptions
- Advanced analytics