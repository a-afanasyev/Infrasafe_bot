# 📋 Request Service API Reference - Core Requests API

**Version**: 1.0.0  
**Base URL**: `http://localhost:8003/api/v1`  
**Last Updated**: 6 October 2025

---

## 📋 Table of Contents

- [Authentication](#authentication)
- [Request Management API](#request-management-api)
- [Error Handling](#error-handling)
- [Pagination](#pagination)

---

## 🔐 Authentication

Все API endpoints требуют service authentication через `Authorization` header:

```bash
Authorization: Bearer <service_token>
```

**Получение service token** от Auth Service:
```bash
curl -X POST http://auth-service:8001/api/v1/internal/service-token \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "request-service",
    "permissions": ["request:read", "request:write"]
  }'
```

---

## 📋 Request Management API

Base URL: `/api/v1/requests`

---

### POST `/api/v1/requests`

**Создание новой заявки с автоматической генерацией номера**

Создает новую заявку с уникальным номером в формате YYMMDD-NNN. Автоматически выполняет geocoding адреса, если координаты не предоставлены.

**Request Body**:
```json
{
  "title": "Протечка в ванной комнате",
  "description": "Под раковиной протекает труба, вода капает на пол",
  "category": "сантехника",
  "priority": "срочный",
  "address": "Чиланзар, район 12, дом 45",
  "apartment_number": "123",
  "building_id": "building_001",
  "applicant_user_id": 42,
  "media_file_ids": ["media_001", "media_002"],
  "latitude": 41.2995,
  "longitude": 69.2401
}
```

**Request Body Schema**:
- `title` (string, required): Заголовок заявки (макс. 200 символов)
- `description` (string, required): Подробное описание проблемы
- `category` (string, required): Категория работ (сантехника, электрика, уборка, вентиляция, обслуживание, ремонт, установка, осмотр, прочее)
- `priority` (string, required): Приоритет (низкий, обычный, высокий, срочный, аварийный)
- `address` (string, required): Адрес выполнения работ
- `apartment_number` (string, optional): Номер квартиры
- `building_id` (string, optional): ID здания в системе
- `applicant_user_id` (integer, required): ID пользователя-заявителя (User Service)
- `media_file_ids` (array[string], optional): Массив ID файлов из Media Service
- `latitude` (float, optional): Широта (auto-geocoded если не указано)
- `longitude` (float, optional): Долгота (auto-geocoded если не указано)

**Response** (201 Created):
```json
{
  "request_number": "251006-001",
  "title": "Протечка в ванной комнате",
  "description": "Под раковиной протекает труба, вода капает на пол",
  "category": "сантехника",
  "priority": "срочный",
  "status": "новая",
  "address": "Чиланзар, район 12, дом 45",
  "apartment_number": "123",
  "building_id": "building_001",
  "applicant_user_id": 42,
  "executor_user_id": null,
  "media_file_ids": ["media_001", "media_002"],
  "latitude": 41.2995,
  "longitude": 69.2401,
  "materials_requested": false,
  "materials_cost": 0.0,
  "created_at": "2025-10-06T10:30:00Z",
  "updated_at": "2025-10-06T10:30:00Z"
}
```

**cURL Example**:
```bash
curl -X POST http://localhost:8003/api/v1/requests \
  -H "Authorization: Bearer <service_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Протечка в ванной комнате",
    "description": "Под раковиной протекает труба",
    "category": "сантехника",
    "priority": "срочный",
    "address": "Чиланзар, район 12, дом 45",
    "applicant_user_id": 42
  }'
```

**Auto-Geocoding**:
Если `latitude` и `longitude` не указаны, сервис автоматически определяет координаты по адресу:
```python
# Автоматический geocoding
if address and not (latitude and longitude):
    geocoding_result = await geocoding_service.geocode_address(address)
    # Координаты добавляются автоматически с confidence > 0.5
```

**Error Responses**:
- `400 Bad Request` - Невалидные данные (отсутствуют обязательные поля)
- `500 Internal Server Error` - Ошибка создания заявки
- `503 Service Unavailable` - Redis и PostgreSQL недоступны для генерации номера

---

### GET `/api/v1/requests`

**Получение списка заявок с фильтрацией и пагинацией**

Возвращает список заявок с поддержкой множественной фильтрации по статусу, категории, исполнителю, датам и другим параметрам.

**Query Parameters**:
- `status` (string, optional): Фильтр по статусу (новая, назначена, в работе, выполнена, отменена)
- `category` (string, optional): Фильтр по категории
- `priority` (string, optional): Фильтр по приоритету
- `executor_id` (integer, optional): Фильтр по исполнителю
- `applicant_id` (integer, optional): Фильтр по заявителю
- `building_id` (string, optional): Фильтр по зданию
- `date_from` (datetime, optional): Начальная дата (ISO 8601)
- `date_to` (datetime, optional): Конечная дата (ISO 8601)
- `search_query` (string, optional): Текстовый поиск по title/description
- `page` (integer, optional): Номер страницы (default: 1)
- `size` (integer, optional): Размер страницы (default: 20, max: 100)
- `sort_by` (string, optional): Поле сортировки (created_at, priority, status)
- `sort_order` (string, optional): Порядок сортировки (asc, desc)

**Response** (200 OK):
```json
{
  "requests": [
    {
      "request_number": "251006-001",
      "title": "Протечка в ванной комнате",
      "status": "новая",
      "category": "сантехника",
      "priority": "срочный",
      "address": "Чиланзар, район 12, дом 45",
      "applicant_user_id": 42,
      "executor_user_id": null,
      "created_at": "2025-10-06T10:30:00Z"
    },
    {
      "request_number": "251006-002",
      "title": "Не работает розетка",
      "status": "назначена",
      "category": "электрика",
      "priority": "обычный",
      "address": "Юнусабад, дом 78",
      "applicant_user_id": 43,
      "executor_user_id": 15,
      "created_at": "2025-10-06T11:00:00Z"
    }
  ],
  "total": 127,
  "page": 1,
  "size": 20,
  "total_pages": 7,
  "has_next": true,
  "has_previous": false
}
```

**cURL Examples**:

```bash
# Все заявки (с пагинацией)
curl -X GET "http://localhost:8003/api/v1/requests?page=1&size=20" \
  -H "Authorization: Bearer <service_token>"

# Фильтр по статусу и категории
curl -X GET "http://localhost:8003/api/v1/requests?status=новая&category=сантехника" \
  -H "Authorization: Bearer <service_token>"

# Фильтр по исполнителю
curl -X GET "http://localhost:8003/api/v1/requests?executor_id=15" \
  -H "Authorization: Bearer <service_token>"

# Поиск по тексту
curl -X GET "http://localhost:8003/api/v1/requests?search_query=протечка" \
  -H "Authorization: Bearer <service_token>"

# Фильтр по дате
curl -X GET "http://localhost:8003/api/v1/requests?date_from=2025-10-01T00:00:00Z&date_to=2025-10-06T23:59:59Z" \
  -H "Authorization: Bearer <service_token>"

# Комбинированные фильтры
curl -X GET "http://localhost:8003/api/v1/requests?status=новая&priority=срочный&page=1&size=10&sort_by=created_at&sort_order=desc" \
  -H "Authorization: Bearer <service_token>"
```

---

### GET `/api/v1/requests/{request_number}`

**Получение детальной информации о заявке**

Возвращает полную информацию о заявке включая relationships: комментарии, рейтинги, назначения и материалы.

**Path Parameters**:
- `request_number` (string, required): Номер заявки (формат: YYMMDD-NNN)

**Response** (200 OK):
```json
{
  "request_number": "251006-001",
  "title": "Протечка в ванной комнате",
  "description": "Под раковиной протекает труба, вода капает на пол",
  "category": "сантехника",
  "priority": "срочный",
  "status": "в работе",
  "address": "Чиланзар, район 12, дом 45",
  "apartment_number": "123",
  "building_id": "building_001",
  "applicant_user_id": 42,
  "executor_user_id": 15,
  "media_file_ids": ["media_001", "media_002"],
  "latitude": 41.2995,
  "longitude": 69.2401,
  "materials_requested": true,
  "materials_cost": 150000.0,
  "materials_list": [
    {"name": "Труба ПВХ 32мм", "quantity": 2, "cost": 50000},
    {"name": "Прокладки", "quantity": 5, "cost": 5000}
  ],
  "work_completed_at": null,
  "completion_notes": null,
  "work_duration_minutes": null,
  "created_at": "2025-10-06T10:30:00Z",
  "updated_at": "2025-10-06T14:00:00Z",
  "comments": [
    {
      "id": "comment_uuid_1",
      "comment_text": "Начинаю работу",
      "author_user_id": 15,
      "is_status_change": true,
      "old_status": "назначена",
      "new_status": "в работе",
      "created_at": "2025-10-06T14:00:00Z"
    }
  ],
  "ratings": [],
  "assignments": [
    {
      "id": "assignment_uuid_1",
      "assigned_user_id": 15,
      "assigned_by_user_id": 1,
      "assignment_type": "manual",
      "is_active": true,
      "created_at": "2025-10-06T13:00:00Z"
    }
  ]
}
```

**cURL Example**:
```bash
curl -X GET "http://localhost:8003/api/v1/requests/251006-001" \
  -H "Authorization: Bearer <service_token>"
```

**Error Responses**:
- `404 Not Found` - Заявка с таким номером не найдена или удалена

---

### PUT `/api/v1/requests/{request_number}`

**Обновление заявки**

Частичное обновление полей заявки. Можно обновить любые поля кроме `request_number` и `status` (для статуса используйте PATCH `/status`).

**Path Parameters**:
- `request_number` (string, required): Номер заявки

**Request Body** (все поля optional):
```json
{
  "title": "Протечка в ванной комнате (обновлено)",
  "description": "Под раковиной протекает труба. Добавлено: повреждена стена",
  "priority": "аварийный",
  "address": "Чиланзар, район 12, дом 45, подъезд 2",
  "apartment_number": "123",
  "media_file_ids": ["media_001", "media_002", "media_003"]
}
```

**Response** (200 OK):
```json
{
  "request_number": "251006-001",
  "title": "Протечка в ванной комнате (обновлено)",
  "description": "Под раковиной протекает труба. Добавлено: повреждена стена",
  "priority": "аварийный",
  "status": "новая",
  "updated_at": "2025-10-06T15:00:00Z"
}
```

**cURL Example**:
```bash
curl -X PUT "http://localhost:8003/api/v1/requests/251006-001" \
  -H "Authorization: Bearer <service_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Протечка в ванной комнате (обновлено)",
    "priority": "аварийный"
  }'
```

**Error Responses**:
- `400 Bad Request` - Невалидные данные
- `404 Not Found` - Заявка не найдена
- `409 Conflict` - Нельзя обновить заявку в статусе "выполнена"

**Validation Rules**:
- Нельзя изменить `category` после назначения исполнителя
- Нельзя обновить заявку в terminal state (выполнена, отменена)
- `priority` можно повысить, но нельзя понизить для заявок в работе

---

### PATCH `/api/v1/requests/{request_number}/status`

**Обновление статуса заявки**

Изменение статуса заявки с валидацией разрешенных переходов. Автоматически создает comment с изменением статуса для audit trail.

**Path Parameters**:
- `request_number` (string, required): Номер заявки

**Request Body**:
```json
{
  "new_status": "назначена",
  "reason": "Назначен исполнитель",
  "updated_by": 1
}
```

**Request Body Schema**:
- `new_status` (string, required): Новый статус
- `reason` (string, optional): Причина изменения статуса
- `updated_by` (integer, required): ID пользователя, меняющего статус

**Response** (200 OK):
```json
{
  "request_number": "251006-001",
  "old_status": "новая",
  "new_status": "назначена",
  "updated_at": "2025-10-06T15:30:00Z",
  "audit_comment_created": true
}
```

**Допустимые переходы статусов**:
```
новая → назначена, отклонена, отменена
назначена → в работе, новая (reassign), отменена
в работе → заказаны материалы, ожидает оплаты, выполнена, отменена
заказаны материалы → материалы доставлены, ожидает оплаты, отменена
материалы доставлены → в работе, выполнена, отменена
ожидает оплаты → выполнена, отменена
```

**Terminal States** (нельзя изменить):
- `выполнена` (COMPLETED)
- `отменена` (CANCELLED)
- `отклонена` (REJECTED)

**cURL Example**:
```bash
curl -X PATCH "http://localhost:8003/api/v1/requests/251006-001/status" \
  -H "Authorization: Bearer <service_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "new_status": "в работе",
    "reason": "Исполнитель начал работу",
    "updated_by": 15
  }'
```

**Error Responses**:
- `400 Bad Request` - Недопустимый переход статуса
- `404 Not Found` - Заявка не найдена
- `409 Conflict` - Заявка в terminal state

---

### DELETE `/api/v1/requests/{request_number}`

**Мягкое удаление заявки**

Помечает заявку как удаленную (soft delete) без физического удаления из базы данных. Удаленные заявки не отображаются в обычных запросах.

**Path Parameters**:
- `request_number` (string, required): Номер заявки

**Query Parameters**:
- `deleted_by` (integer, required): ID пользователя, удаляющего заявку
- `deletion_reason` (string, optional): Причина удаления

**Response** (200 OK):
```json
{
  "request_number": "251006-001",
  "is_deleted": true,
  "deleted_at": "2025-10-06T16:00:00Z",
  "deleted_by": 1,
  "deletion_reason": "Дублирующая заявка"
}
```

**cURL Example**:
```bash
curl -X DELETE "http://localhost:8003/api/v1/requests/251006-001?deleted_by=1&deletion_reason=Дублирующая%20заявка" \
  -H "Authorization: Bearer <service_token>"
```

**Error Responses**:
- `404 Not Found` - Заявка не найдена
- `409 Conflict` - Заявка в статусе "в работе" (нельзя удалять активные заявки)

**Validation Rules**:
- Можно удалить только заявки в статусах: новая, назначена, отклонена, отменена
- Нельзя удалить заявки в работе или выполненные
- Удаление можно отменить через админ панель

---

### POST `/api/v1/requests/{request_number}/assign`

**Назначение исполнителя на заявку**

Назначает исполнителя на заявку и меняет статус на "назначена". Создает запись assignment для audit trail.

**Path Parameters**:
- `request_number` (string, required): Номер заявки

**Request Body**:
```json
{
  "executor_id": 15,
  "assigned_by": 1,
  "assignment_type": "manual",
  "assignment_reason": "Специалист по сантехнике в этом районе"
}
```

**Request Body Schema**:
- `executor_id` (integer, required): ID исполнителя (User Service)
- `assigned_by` (integer, required): ID пользователя, назначающего
- `assignment_type` (string, optional): Тип назначения (manual, auto, ai_recommended, default: manual)
- `assignment_reason` (string, optional): Причина назначения
- `specialization_required` (string, optional): Требуемая специализация

**Response** (200 OK):
```json
{
  "request_number": "251006-001",
  "executor_id": 15,
  "status": "назначена",
  "assignment": {
    "id": "assignment_uuid_1",
    "assigned_user_id": 15,
    "assigned_by_user_id": 1,
    "assignment_type": "manual",
    "assignment_reason": "Специалист по сантехнике в этом районе",
    "is_active": true,
    "created_at": "2025-10-06T13:00:00Z"
  },
  "notification_sent": true
}
```

**cURL Example**:
```bash
curl -X POST "http://localhost:8003/api/v1/requests/251006-001/assign" \
  -H "Authorization: Bearer <service_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "executor_id": 15,
    "assigned_by": 1,
    "assignment_type": "manual"
  }'
```

**Side Effects**:
- Статус заявки меняется на "назначена"
- Создается запись в `request_assignments`
- Отправляется уведомление исполнителю (через Notification Service)
- Создается audit comment с изменением статуса

**Error Responses**:
- `400 Bad Request` - Невалидный executor_id или заявка уже назначена
- `404 Not Found` - Заявка не найдена
- `409 Conflict` - Заявка в неподходящем статусе для назначения

**Validation Rules**:
- Заявка должна быть в статусе "новая"
- Executor должен существовать в User Service
- Executor должен иметь соответствующую специализацию
- Executor должен быть доступен

---

### GET `/api/v1/requests/stats`

**Статистика по заявкам**

Возвращает агрегированную статистику по заявкам: распределение по статусам, категориям, среднее время выполнения.

**Query Parameters**:
- `date_from` (datetime, optional): Начальная дата для статистики
- `date_to` (datetime, optional): Конечная дата
- `group_by` (string, optional): Группировка (status, category, priority, executor)

**Response** (200 OK):
```json
{
  "total_requests": 1547,
  "period": {
    "from": "2025-09-01T00:00:00Z",
    "to": "2025-10-06T23:59:59Z",
    "days": 36
  },
  "by_status": {
    "новая": 45,
    "назначена": 123,
    "в работе": 78,
    "выполнена": 1245,
    "отменена": 56
  },
  "by_category": {
    "сантехника": 618,
    "уборка": 387,
    "электрика": 232,
    "обслуживание": 155,
    "прочее": 155
  },
  "by_priority": {
    "низкий": 310,
    "обычный": 927,
    "высокий": 232,
    "срочный": 62,
    "аварийный": 16
  },
  "performance_metrics": {
    "avg_completion_time_hours": 18.5,
    "avg_assignment_time_minutes": 45,
    "completion_rate": 80.5,
    "avg_rating": 4.3
  },
  "top_executors": [
    {
      "executor_id": 15,
      "requests_completed": 87,
      "avg_rating": 4.8,
      "avg_completion_time_hours": 12.3
    },
    {
      "executor_id": 23,
      "requests_completed": 76,
      "avg_rating": 4.6,
      "avg_completion_time_hours": 14.1
    }
  ]
}
```

**cURL Example**:
```bash
curl -X GET "http://localhost:8003/api/v1/requests/stats?date_from=2025-09-01T00:00:00Z&date_to=2025-10-06T23:59:59Z" \
  -H "Authorization: Bearer <service_token>"
```

---

## 🔄 Pagination

Все list endpoints поддерживают стандартную пагинацию:

**Request Parameters**:
```
page: номер страницы (начинается с 1)
size: размер страницы (default: 20, max: 100)
```

**Response Format**:
```json
{
  "items": [...],
  "total": 127,
  "page": 1,
  "size": 20,
  "total_pages": 7,
  "has_next": true,
  "has_previous": false
}
```

**Примеры**:
```bash
# Первая страница (20 items)
GET /api/v1/requests?page=1&size=20

# Вторая страница (20 items)
GET /api/v1/requests?page=2&size=20

# Большой размер страницы (100 items)
GET /api/v1/requests?page=1&size=100
```

---

## ❌ Error Handling

### Standard Error Response Format

```json
{
  "detail": "Request 251006-999 not found",
  "status_code": 404,
  "timestamp": "2025-10-06T16:00:00Z",
  "path": "/api/v1/requests/251006-999",
  "request_id": "req_abc123"
}
```

### HTTP Status Codes

| Code | Meaning | When |
|------|---------|------|
| `200` | OK | Успешный запрос |
| `201` | Created | Ресурс создан |
| `400` | Bad Request | Невалидные данные |
| `401` | Unauthorized | Отсутствует/невалидный токен |
| `403` | Forbidden | Недостаточно прав |
| `404` | Not Found | Ресурс не найден |
| `409` | Conflict | Конфликт (дублирующий номер, недопустимый переход статуса) |
| `422` | Unprocessable Entity | Ошибка валидации Pydantic |
| `429` | Too Many Requests | Rate limit превышен |
| `500` | Internal Server Error | Серверная ошибка |
| `503` | Service Unavailable | Сервис временно недоступен |

### Common Error Scenarios

**1. Дублирующий номер заявки** (очень редко, race condition):
```json
{
  "detail": "Request number 251006-001 already exists",
  "status_code": 409
}
```

**2. Недопустимый переход статуса**:
```json
{
  "detail": "Cannot transition from 'выполнена' to 'в работе'",
  "status_code": 409,
  "allowed_transitions": ["выполнена"]
}
```

**3. Redis и PostgreSQL недоступны** (критическая ошибка):
```json
{
  "detail": "Cannot generate request number: both Redis and PostgreSQL failed",
  "status_code": 503
}
```

---

## 🔑 Request Numbering System

### Format: YYMMDD-NNN

**Components**:
- `YY`: Год (2 цифры)
- `MM`: Месяц (2 цифры)
- `DD`: День (2 цифры)
- `NNN`: Порядковый номер (3 цифры, 001-999)

**Examples**:
- `251006-001` - Первая заявка 6 октября 2025
- `251006-042` - 42-я заявка 6 октября 2025
- `251231-999` - 999-я заявка 31 декабря 2025

### Generation Algorithm

**Двухуровневая система с fallback**:

```python
# Шаг 1: Redis atomic increment (primary)
counter = await redis.incr(f"request_service:request_numbers:251006")
request_number = f"251006-{counter:03d}"

# Шаг 2: Проверка уникальности в PostgreSQL
existing = await db.execute("SELECT 1 FROM requests WHERE request_number = :num")
if existing:
    # Fallback to database generation

# Шаг 3: PostgreSQL fallback (если Redis недоступен)
max_number = await db.execute(
    "SELECT MAX(request_number) FROM requests WHERE request_number LIKE '251006-%'"
)
next_seq = extract_sequence(max_number) + 1
request_number = f"251006-{next_seq:03d}"
```

**Гарантии**:
- ✅ **100% уникальность** (atomic operations + unique constraint)
- ✅ **Thread safety** (Redis INCR - atomic)
- ✅ **Daily reset** (counter сбрасывается в полночь)
- ✅ **Fallback** (работает даже без Redis)
- ✅ **Collision prevention** (проверка в БД перед сохранением)

**TTL**:
- Redis counter ключ: TTL 24 часа (автоматически сбрасывается в полночь)
- Формат ключа: `request_service:request_numbers:YYMMDD`

---

## 📝 Request Status Lifecycle

### State Machine

```
┌─────────┐
│  новая  │ ──────────────┐
└─────────┘               │
     │                    │
     │ assign             │ reject
     ▼                    ▼
┌──────────┐         ┌──────────┐
│назначена │         │отклонена │ (terminal)
└──────────┘         └──────────┘
     │
     │ start_work
     ▼
┌──────────┐
│ в работе │ ─────────────┐
└──────────┘              │
     │                    │ cancel
     │ request_materials  ▼
     ▼                ┌─────────┐
┌─────────────────┐  │отменена │ (terminal)
│заказаны материалы│  └─────────┘
└─────────────────┘
     │
     │ deliver_materials
     ▼
┌───────────────────┐
│материалы доставлены│
└───────────────────┘
     │
     │ request_payment
     ▼
┌──────────────┐
│ожидает оплаты│
└──────────────┘
     │
     │ approve_payment
     ▼
┌──────────┐
│выполнена │ (terminal)
└──────────┘
```

### Status Descriptions

**новая** (NEW):
- Начальный статус после создания
- Ожидает назначения исполнителя
- Видна всем менеджерам для назначения

**назначена** (ASSIGNED):
- Исполнитель назначен
- Ожидает начала работы исполнителем
- Исполнитель получил уведомление

**в работе** (IN_PROGRESS):
- Исполнитель начал работу
- Активная работа на объекте
- Может запросить материалы или завершить

**заказаны материалы** (MATERIALS_REQUESTED):
- Материалы заказаны
- Ожидание доставки
- Временная приостановка работ

**материалы доставлены** (MATERIALS_DELIVERED):
- Материалы получены
- Можно продолжить работу

**ожидает оплаты** (WAITING_PAYMENT):
- Работа выполнена
- Ожидает подтверждения оплаты
- Требует одобрения менеджера

**выполнена** (COMPLETED):
- Работа завершена и оплачена
- Terminal state
- Доступна для оценки

**отменена** (CANCELLED):
- Заявка отменена по инициативе пользователя или системы
- Terminal state
- Содержит причину отмены

**отклонена** (REJECTED):
- Заявка отклонена менеджером
- Terminal state
- Содержит причину отклонения

---

## 🏷️ Request Categories

### Supported Categories

| Russian | English | Description | Typical Specialists |
|---------|---------|-------------|-------------------|
| **сантехника** | PLUMBING | Сантехнические работы | Сантехник, слесарь |
| **электрика** | ELECTRICAL | Электромонтажные работы | Электрик |
| **вентиляция** | HVAC | Отопление, вентиляция, кондиционирование | Вентиляционщик, теплотехник |
| **уборка** | CLEANING | Уборочные работы | Уборщик, клининг |
| **обслуживание** | MAINTENANCE | Техническое обслуживание | Инженер, техник |
| **ремонт** | REPAIR | Общие ремонтные работы | Мастер-универсал |
| **установка** | INSTALLATION | Установка оборудования | Монтажник, установщик |
| **осмотр** | INSPECTION | Осмотр и оценка | Инспектор, оценщик |
| **прочее** | OTHER | Прочие услуги | Определяется индивидуально |

### Category Validation

```python
# Enum в коде
class RequestCategory(str, Enum):
    PLUMBING = "сантехника"
    ELECTRICAL = "электрика"
    HVAC = "вентиляция"
    CLEANING = "уборка"
    MAINTENANCE = "обслуживание"
    REPAIR = "ремонт"
    INSTALLATION = "установка"
    INSPECTION = "осмотр"
    OTHER = "прочее"
```

---

## ⚡ Priority Levels

### Supported Priorities

| Russian | English | SLA | Response Time | Typical Cases |
|---------|---------|-----|---------------|---------------|
| **аварийный** | EMERGENCY | 1 час | Немедленно | Прорыв трубы, пожар, утечка газа |
| **срочный** | URGENT | 4 часа | В течение часа | Нет света, нет воды, серьезная протечка |
| **высокий** | HIGH | 24 часа | В течение дня | Частичная неисправность, дискомфорт |
| **обычный** | NORMAL | 72 часа | 1-2 дня | Плановые работы, косметические дефекты |
| **низкий** | LOW | 1 неделя | По возможности | Улучшения, необязательные работы |

### Priority Auto-Escalation

Система автоматически повышает приоритет если:
- Заявка не назначена > 24 часа: обычный → высокий
- Заявка не назначена > 48 часов: высокий → срочный
- В описании есть ключевые слова: "авария", "прорыв", "затопление" → аварийный

```python
# Enum в коде
class RequestPriority(str, Enum):
    LOW = "низкий"
    NORMAL = "обычный"
    HIGH = "высокий"
    URGENT = "срочный"
    EMERGENCY = "аварийный"
```

---

## 📖 See Also

- [API_REFERENCE_ASSIGNMENTS.md](API_REFERENCE_ASSIGNMENTS.md) - Assignments & Reassignment API
- [API_REFERENCE_COMMENTS.md](API_REFERENCE_COMMENTS.md) - Comments, Ratings, Materials API
- [API_REFERENCE_INTEGRATION.md](API_REFERENCE_INTEGRATION.md) - Bot, AI, Search, Export API
- [REQUEST_SERVICE_DOCUMENTATION.md](REQUEST_SERVICE_DOCUMENTATION.md) - Полная техническая документация
- [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) - Руководство по интеграциям


