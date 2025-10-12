# 📋 API Контракты - Core Service

**Версия**: 1.0.0
**Дата**: 09.10.2025
**Статус**: Детальная спецификация

---

## 📌 Общие соглашения

### Формат ответов

Все успешные ответы возвращаются в формате:
```json
{
  "success": true,
  "data": {...},
  "meta": {
    "timestamp": "2025-10-09T12:00:00Z",
    "request_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

### Формат ошибок

```json
{
  "success": false,
  "error": {
    "code": "AUTH_001",
    "message": "Invalid credentials",
    "details": "Email or password is incorrect",
    "field": "password",
    "timestamp": "2025-10-09T12:00:00Z",
    "request_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

### Коды ошибок

| Префикс | Сервис | Диапазон |
|---------|--------|----------|
| AUTH_   | Authentication | 001-099 |
| USER_   | User Management | 100-199 |
| REQ_    | Request Management | 200-299 |
| BUILD_  | Building Assets | 300-399 |
| PERM_   | Permissions | 400-499 |
| VAL_    | Validation | 500-599 |

### Pagination

```json
{
  "page": 1,
  "per_page": 20,
  "total": 150,
  "total_pages": 8,
  "has_next": true,
  "has_prev": false
}
```

---

## 🔐 Модуль аутентификации

### POST /api/v1/auth/login

**Описание**: Аутентификация пользователя

#### Request Body

```json
{
  "email": "user@example.com",
  "password": "SecurePass123!",
  "device_info": {
    "device_id": "550e8400-e29b-41d4",
    "platform": "ios",
    "app_version": "1.2.3"
  }
}
```

#### Валидация

| Поле | Тип | Обязательное | Валидация |
|------|-----|--------------|-----------|
| email | string | ✅ | Email format, max 255 chars |
| password | string | ✅ | Min 8 chars, max 128 chars |
| device_info | object | ❌ | Optional device tracking |
| device_info.device_id | string | ❌ | UUID format |
| device_info.platform | string | ❌ | Enum: ios, android, web |
| device_info.app_version | string | ❌ | Semver format |

#### Success Response (200 OK)

```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "Bearer",
    "expires_in": 3600,
    "user": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "email": "user@example.com",
      "full_name": "Иван Иванов",
      "roles": ["applicant", "executor"],
      "is_verified": true,
      "last_login": "2025-10-09T12:00:00Z"
    }
  },
  "meta": {
    "timestamp": "2025-10-09T12:00:00Z",
    "request_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

#### Error Responses

| Код | HTTP Status | Описание |
|-----|-------------|----------|
| AUTH_001 | 401 | Invalid credentials |
| AUTH_002 | 403 | Account locked |
| AUTH_003 | 403 | Account not verified |
| AUTH_004 | 429 | Too many login attempts |
| VAL_501 | 400 | Invalid email format |
| VAL_502 | 400 | Password too short |

#### Пример ошибки (401)

```json
{
  "success": false,
  "error": {
    "code": "AUTH_001",
    "message": "Invalid credentials",
    "details": "The email or password you entered is incorrect",
    "field": null,
    "timestamp": "2025-10-09T12:00:00Z",
    "request_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

---

### POST /api/v1/auth/refresh

**Описание**: Обновление access token

#### Request Body

```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

#### Success Response (200 OK)

```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "Bearer",
    "expires_in": 3600
  }
}
```

---

### POST /api/v1/auth/logout

**Описание**: Выход из системы

#### Headers

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

#### Request Body (optional)

```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "everywhere": false
}
```

#### Success Response (204 No Content)

```
(empty body)
```

---

## 👤 Модуль управления пользователями

### GET /api/v1/users

**Описание**: Получение списка пользователей

#### Query Parameters

| Параметр | Тип | Обязательный | Описание | Значение по умолчанию |
|----------|-----|--------------|----------|----------------------|
| page | integer | ❌ | Номер страницы | 1 |
| per_page | integer | ❌ | Записей на странице | 20 |
| role | string | ❌ | Фильтр по роли | - |
| is_active | boolean | ❌ | Только активные | true |
| search | string | ❌ | Поиск по имени/email | - |
| sort | string | ❌ | Поле сортировки | created_at |
| order | string | ❌ | Направление (asc/desc) | desc |

#### Success Response (200 OK)

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "email": "user@example.com",
        "full_name": "Иван Иванов",
        "phone": "+998901234567",
        "roles": ["applicant", "executor"],
        "is_active": true,
        "is_verified": true,
        "rating": 4.8,
        "specializations": [
          {
            "id": 1,
            "name": "Электрика",
            "level": "expert"
          },
          {
            "id": 2,
            "name": "Сантехника",
            "level": "intermediate"
          }
        ],
        "buildings": [
          {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "name": "ЖК Центральный",
            "address": "ул. Ленина, д. 1",
            "role": "manager"
          }
        ],
        "stats": {
          "requests_total": 150,
          "requests_completed": 145,
          "avg_completion_time": 4.2
        },
        "created_at": "2025-01-15T10:00:00Z",
        "updated_at": "2025-10-09T12:00:00Z",
        "last_login": "2025-10-09T11:00:00Z"
      }
    ],
    "pagination": {
      "page": 1,
      "per_page": 20,
      "total": 150,
      "total_pages": 8,
      "has_next": true,
      "has_prev": false
    }
  }
}
```

---

### POST /api/v1/users

**Описание**: Создание нового пользователя

#### Request Body

```json
{
  "email": "newuser@example.com",
  "password": "SecurePass123!",
  "full_name": "Петр Петров",
  "phone": "+998901234567",
  "roles": ["applicant"],
  "language": "ru",
  "timezone": "Asia/Tashkent",
  "buildings": [
    {
      "building_id": "123e4567-e89b-12d3-a456-426614174000",
      "apartment": "42"
    }
  ],
  "metadata": {
    "source": "telegram",
    "telegram_id": 123456789
  }
}
```

#### Валидация

| Поле | Тип | Обязательное | Валидация |
|------|-----|--------------|-----------|
| email | string | ✅ | Unique, email format, max 255 |
| password | string | ✅ | Min 8, max 128, complexity rules |
| full_name | string | ✅ | Min 2, max 255 |
| phone | string | ❌ | E.164 format, unique |
| roles | array | ✅ | Min 1, valid roles |
| language | string | ❌ | Enum: ru, uz, en |
| timezone | string | ❌ | Valid IANA timezone |
| buildings | array | ❌ | Valid building IDs |
| metadata | object | ❌ | Max 10KB JSON |

#### Success Response (201 Created)

```json
{
  "success": true,
  "data": {
    "id": "650e8400-e29b-41d4-a716-446655440000",
    "email": "newuser@example.com",
    "full_name": "Петр Петров",
    "verification_required": true,
    "verification_sent_to": "newuser@example.com",
    "created_at": "2025-10-09T12:00:00Z"
  }
}
```

#### Error Responses

| Код | HTTP Status | Описание |
|-----|-------------|----------|
| USER_101 | 409 | Email already exists |
| USER_102 | 409 | Phone already exists |
| USER_103 | 400 | Invalid role specified |
| BUILD_301 | 404 | Building not found |
| VAL_503 | 400 | Password complexity requirements not met |

---

## 📋 Модуль управления заявками

### GET /api/v1/requests

**Описание**: Получение списка заявок

#### Query Parameters

| Параметр | Тип | Обязательный | Описание | Значение по умолчанию |
|----------|-----|--------------|----------|----------------------|
| page | integer | ❌ | Номер страницы | 1 |
| per_page | integer | ❌ | Записей на странице | 20 |
| status | string | ❌ | Фильтр по статусу | - |
| priority | string | ❌ | Фильтр по приоритету | - |
| executor_id | uuid | ❌ | Фильтр по исполнителю | - |
| applicant_id | uuid | ❌ | Фильтр по заявителю | - |
| building_id | uuid | ❌ | Фильтр по зданию | - |
| date_from | datetime | ❌ | Дата создания от | - |
| date_to | datetime | ❌ | Дата создания до | - |
| search | string | ❌ | Поиск по номеру/описанию | - |

#### Success Response (200 OK)

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "request_number": "251009-001",
        "title": "Протечка в ванной комнате",
        "description": "Течет труба под раковиной, нужен срочный ремонт",
        "status": "in_progress",
        "priority": "high",
        "category": {
          "id": 2,
          "name": "Сантехника",
          "sla_hours": 4
        },
        "applicant": {
          "id": "550e8400-e29b-41d4-a716-446655440000",
          "full_name": "Иван Иванов",
          "phone": "+998901234567"
        },
        "executor": {
          "id": "650e8400-e29b-41d4-a716-446655440000",
          "full_name": "Петр Петров",
          "specialization": "Сантехника",
          "rating": 4.8
        },
        "location": {
          "building_id": "123e4567-e89b-12d3-a456-426614174000",
          "building_name": "ЖК Центральный",
          "address": "ул. Ленина, д. 1",
          "entrance": "1",
          "floor": "5",
          "apartment": "42",
          "coordinates": {
            "lat": 41.311081,
            "lng": 69.240562
          }
        },
        "media": [
          {
            "id": "750e8400-e29b-41d4-a716-446655440000",
            "type": "image",
            "url": "https://storage.example.com/media/750e8400.jpg",
            "thumbnail": "https://storage.example.com/media/750e8400_thumb.jpg",
            "size": 2048576,
            "uploaded_at": "2025-10-09T10:00:00Z"
          }
        ],
        "timeline": {
          "created_at": "2025-10-09T10:00:00Z",
          "assigned_at": "2025-10-09T10:15:00Z",
          "started_at": "2025-10-09T11:00:00Z",
          "completed_at": null,
          "deadline": "2025-10-09T14:00:00Z",
          "sla_deadline": "2025-10-09T14:00:00Z"
        },
        "metrics": {
          "response_time_minutes": 15,
          "time_to_start_minutes": 60,
          "time_in_progress_minutes": 60,
          "is_sla_met": true,
          "reassignment_count": 0
        },
        "comments_count": 3,
        "rating": null,
        "created_at": "2025-10-09T10:00:00Z",
        "updated_at": "2025-10-09T12:00:00Z"
      }
    ],
    "pagination": {
      "page": 1,
      "per_page": 20,
      "total": 450,
      "total_pages": 23,
      "has_next": true,
      "has_prev": false
    },
    "stats": {
      "total": 450,
      "by_status": {
        "new": 12,
        "assigned": 25,
        "in_progress": 38,
        "clarification": 5,
        "completed": 350,
        "cancelled": 20
      },
      "by_priority": {
        "urgent": 15,
        "high": 45,
        "medium": 280,
        "low": 110
      }
    }
  }
}
```

---

### POST /api/v1/requests

**Описание**: Создание новой заявки

#### Request Body

```json
{
  "title": "Не работает лифт",
  "description": "Лифт застрял на 3 этаже, не открываются двери",
  "category_id": 5,
  "priority": "urgent",
  "location": {
    "building_id": "123e4567-e89b-12d3-a456-426614174000",
    "entrance": "2",
    "floor": "3",
    "apartment": null
  },
  "contact_phone": "+998901234567",
  "preferred_date": "2025-10-10",
  "preferred_time": "10:00-12:00",
  "media_ids": [
    "750e8400-e29b-41d4-a716-446655440000"
  ],
  "additional_info": {
    "people_trapped": 2,
    "emergency": true
  }
}
```

#### Валидация

| Поле | Тип | Обязательное | Валидация |
|------|-----|--------------|-----------|
| title | string | ✅ | Min 5, max 255 chars |
| description | string | ✅ | Min 10, max 2000 chars |
| category_id | integer | ✅ | Valid category ID |
| priority | string | ❌ | Enum: low, medium, high, urgent |
| location.building_id | uuid | ✅ | Valid building ID |
| location.entrance | string | ❌ | Max 10 chars |
| location.floor | string | ❌ | Max 10 chars |
| location.apartment | string | ❌ | Max 20 chars |
| contact_phone | string | ❌ | E.164 format |
| preferred_date | date | ❌ | Future date, max 30 days |
| preferred_time | string | ❌ | Time range format |
| media_ids | array | ❌ | Max 10 items, valid media IDs |
| additional_info | object | ❌ | Max 5KB JSON |

#### Success Response (201 Created)

```json
{
  "success": true,
  "data": {
    "request_number": "251009-002",
    "title": "Не работает лифт",
    "status": "new",
    "priority": "urgent",
    "category": {
      "id": 5,
      "name": "Лифты",
      "sla_hours": 2
    },
    "sla_deadline": "2025-10-09T14:15:00Z",
    "assignment_status": "pending",
    "assignment_message": "Заявка поставлена в очередь на автоматическое назначение",
    "created_at": "2025-10-09T12:15:00Z"
  },
  "meta": {
    "assignment_mode": "async",
    "estimated_assignment_time": "2025-10-09T12:16:00Z",
    "notification_sent": true
  }
}
```

**Примечание**: Назначение исполнителя выполняется асинхронно через Operations Service.
После назначения будет отправлено событие `request.assigned` и уведомление заявителю.

#### Error Responses

| Код | HTTP Status | Описание |
|-----|-------------|----------|
| REQ_201 | 400 | Invalid category |
| REQ_202 | 400 | Invalid priority |
| REQ_203 | 429 | Too many requests from user |
| BUILD_302 | 404 | Building not found |
| BUILD_303 | 403 | No access to this building |

---

### PATCH /api/v1/requests/{request_number}

**Описание**: Обновление заявки

#### Path Parameters

- `request_number` (string, required) - Номер заявки в формате YYMMDD-NNN

#### Request Body

```json
{
  "status": "in_progress",
  "executor_id": "650e8400-e29b-41d4-a716-446655440000",
  "priority": "high",
  "comment": "Начал работу, требуется замена детали",
  "estimated_completion": "2025-10-09T15:00:00Z"
}
```

#### Валидация переходов статусов

**✅ УТВЕРЖДЕНО**: Матрица переходов утверждена 10 октября 2025 (решение Q2.1)

**Доступные статусы**:
- `new` - Новая заявка
- `in_progress` - В работе
- `purchase` - Требуется закуп материалов
- `clarification` - Требуется уточнение у заявителя
- `completed` - Выполнена (ожидает подтверждения)
- `confirmed` - Подтверждена заявителем (финальный)
- `cancelled` - Отменена (финальный)

**Матрица разрешенных переходов**:

| Из статуса | В статус | Условия | Примечание |
|------------|----------|---------|------------|
| new | in_progress | Требуется executor_id | Назначение исполнителя |
| new | clarification | Требуется comment | Нужны уточнения до начала |
| new | cancelled | Требуется comment | Отмена до начала работы |
| in_progress | purchase | Требуется comment | Требуются материалы |
| in_progress | completed | - | Работа выполнена |
| in_progress | clarification | Требуется comment | Нужны уточнения от заявителя |
| in_progress | cancelled | Требуется comment | Отмена в процессе |
| purchase | in_progress | - | Материалы закуплены, продолжение |
| clarification | in_progress | - | Уточнения получены, продолжение |
| clarification | cancelled | Требуется comment | Отмена после уточнений |
| completed | confirmed | - | Заявитель подтвердил |
| completed | in_progress | Требуется comment | Заявитель не принял работу |

**Правила**:
- ❌ Автовозврата из "clarification" НЕТ (ручное уточнение)
- ✅ Возврат из "completed" в "in_progress" РАЗРЕШЕН (если заявитель не принял)
- ❌ Автоотмена неактивных заявок НЕ производится
- ⚠️ Напоминания об актуализации: раз в неделю для статусов clarification/purchase
- 🔒 Финальные статусы (нельзя изменить): confirmed, cancelled

#### Success Response (200 OK)

```json
{
  "success": true,
  "data": {
    "request_number": "251009-002",
    "status": "in_progress",
    "status_changed": true,
    "previous_status": "assigned",
    "executor": {
      "id": "650e8400-e29b-41d4-a716-446655440000",
      "full_name": "Петр Петров"
    },
    "updated_at": "2025-10-09T12:30:00Z",
    "timeline": {
      "started_at": "2025-10-09T12:30:00Z",
      "estimated_completion": "2025-10-09T15:00:00Z"
    }
  }
}
```

#### Error Responses

| Код | HTTP Status | Описание |
|-----|-------------|----------|
| REQ_204 | 404 | Request not found |
| REQ_205 | 400 | Invalid status transition |
| REQ_206 | 403 | No permission to update |
| REQ_207 | 409 | Request already completed |
| USER_104 | 404 | Executor not found |

---

## 🏢 Модуль Building Assets

### GET /api/v1/buildings

**Описание**: Получение списка зданий

#### Query Parameters

| Параметр | Тип | Обязательный | Описание | Значение по умолчанию |
|----------|-----|--------------|----------|----------------------|
| complex_id | uuid | ❌ | Фильтр по комплексу | - |
| city | string | ❌ | Фильтр по городу | - |
| district | string | ❌ | Фильтр по району | - |
| is_active | boolean | ❌ | Только активные | true |
| has_coordinates | boolean | ❌ | Только с координатами | - |
| near_lat | float | ❌ | Широта для поиска рядом | - |
| near_lng | float | ❌ | Долгота для поиска рядом | - |
| radius_km | float | ❌ | Радиус поиска (км) | 5 |

#### Success Response (200 OK)

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "complex": {
          "id": "023e4567-e89b-12d3-a456-426614174000",
          "name": "ЖК Центральный"
        },
        "name": "Корпус 1",
        "type": "residential",
        "address": {
          "full": "г. Ташкент, ул. Ленина, д. 1",
          "city": "Ташкент",
          "district": "Мирабадский район",
          "street": "ул. Ленина",
          "building_number": "1",
          "postal_code": "100000"
        },
        "coordinates": {
          "lat": 41.311081,
          "lng": 69.240562
        },
        "structure": {
          "floors": 16,
          "entrances": 4,
          "apartments": 256,
          "parking_spaces": 300,
          "commercial_units": 12
        },
        "amenities": [
          "parking",
          "playground",
          "gym",
          "security_24_7"
        ],
        "management": {
          "company": "УК Центральная",
          "phone": "+998711234567",
          "email": "info@uk-central.uz",
          "working_hours": "09:00-18:00"
        },
        "stats": {
          "total_residents": 820,
          "active_requests": 15,
          "completed_requests_month": 145,
          "avg_request_time_hours": 4.5
        },
        "is_active": true,
        "created_at": "2024-01-15T10:00:00Z",
        "updated_at": "2025-10-09T12:00:00Z"
      }
    ],
    "pagination": {
      "page": 1,
      "per_page": 20,
      "total": 45,
      "total_pages": 3,
      "has_next": true,
      "has_prev": false
    }
  }
}
```

---

### POST /api/v1/buildings/{building_id}/apartments

**Описание**: Добавление квартиры в здание

#### Path Parameters

- `building_id` (uuid, required) - ID здания

#### Request Body

```json
{
  "number": "42",
  "entrance": "1",
  "floor": 5,
  "type": "2_room",
  "area_sqm": 65.5,
  "rooms": 2,
  "layout": "improved",
  "residents": [
    {
      "user_id": "550e8400-e29b-41d4-a716-446655440000",
      "is_owner": true,
      "move_in_date": "2024-06-15"
    }
  ],
  "metadata": {
    "balcony": true,
    "renovation": "euro"
  }
}
```

#### Валидация

| Поле | Тип | Обязательное | Валидация |
|------|-----|--------------|-----------|
| number | string | ✅ | Unique per building, max 20 |
| entrance | string | ✅ | Valid entrance for building |
| floor | integer | ✅ | 1 <= floor <= building.floors |
| type | string | ❌ | Enum: studio, 1_room, 2_room, 3_room, 4_room+ |
| area_sqm | float | ❌ | 10 <= area <= 1000 |
| rooms | integer | ❌ | 0 <= rooms <= 10 |
| layout | string | ❌ | Enum: standard, improved, custom |
| residents | array | ❌ | Valid user IDs |
| metadata | object | ❌ | Max 5KB JSON |

#### Success Response (201 Created)

```json
{
  "success": true,
  "data": {
    "id": "823e4567-e89b-12d3-a456-426614174000",
    "building_id": "123e4567-e89b-12d3-a456-426614174000",
    "number": "42",
    "entrance": "1",
    "floor": 5,
    "full_address": "ЖК Центральный, корп. 1, под. 1, кв. 42",
    "residents_count": 1,
    "created_at": "2025-10-09T12:45:00Z"
  }
}
```

---

### GET /api/v1/buildings/search

**Описание**: Поиск зданий по адресу или координатам

#### Query Parameters

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| q | string | ❌ | Текстовый поиск по адресу |
| lat | float | ❌ | Широта |
| lng | float | ❌ | Долгота |
| radius_km | float | ❌ | Радиус поиска |
| limit | integer | ❌ | Макс. результатов (default: 10) |

#### Success Response (200 OK)

```json
{
  "success": true,
  "data": {
    "query": "Ленина 1",
    "results": [
      {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "name": "ЖК Центральный, корпус 1",
        "address": "г. Ташкент, ул. Ленина, д. 1",
        "distance_km": 0.5,
        "match_score": 0.95,
        "coordinates": {
          "lat": 41.311081,
          "lng": 69.240562
        }
      }
    ],
    "total_found": 1,
    "search_radius_km": 5
  }
}
```

---

## 🔒 Модуль авторизации и прав доступа

### GET /api/v1/permissions/check

**Описание**: Проверка прав доступа

#### Query Parameters

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| resource | string | ✅ | Тип ресурса |
| resource_id | string | ❌ | ID ресурса |
| action | string | ✅ | Действие |

#### Headers

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

#### Success Response (200 OK)

```json
{
  "success": true,
  "data": {
    "allowed": true,
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "resource": "request",
    "resource_id": "251009-001",
    "action": "update",
    "roles": ["executor"],
    "reason": "User is assigned executor for this request"
  }
}
```

#### Forbidden Response (403)

```json
{
  "success": false,
  "error": {
    "code": "PERM_401",
    "message": "Access denied",
    "details": "You don't have permission to update this request",
    "required_roles": ["executor", "manager"],
    "user_roles": ["applicant"]
  }
}
```

---

## 🔄 Webhooks

### Webhook Events

Core Service отправляет webhooks для следующих событий:

| Событие | Описание |
|---------|----------|
| user.created | Новый пользователь зарегистрирован |
| user.verified | Email пользователя подтвержден |
| user.updated | Данные пользователя обновлены |
| request.created | Создана новая заявка |
| request.status_changed | Изменен статус заявки |
| request.assigned | Заявка назначена исполнителю |
| request.completed | Заявка выполнена |
| building.created | Добавлено новое здание |
| apartment.resident_added | Добавлен жилец |

### Webhook Payload

```json
{
  "id": "evt_2YqQwFkLPtN6QzK5x8Fb",
  "type": "request.status_changed",
  "created_at": "2025-10-09T12:30:00Z",
  "data": {
    "request_number": "251009-001",
    "old_status": "new",
    "new_status": "assigned",
    "executor_id": "650e8400-e29b-41d4-a716-446655440000",
    "changed_by": "550e8400-e29b-41d4-a716-446655440000"
  },
  "metadata": {
    "version": "1.0",
    "retry_count": 0,
    "idempotency_key": "req_251009-001_status_1696852200"
  }
}
```

### Webhook Security

Все webhooks подписываются с использованием HMAC-SHA256:

```
X-Webhook-Signature: sha256=b0344c61d8db38e0451e5d4e8b881b52e967f423e3fc9ff5b5fd27e78d621d6f
```

Проверка подписи:
```python
import hmac
import hashlib

def verify_webhook(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)
```

---

## 📊 Rate Limiting

### Лимиты по endpoint'ам

| Endpoint | Лимит | Окно |
|----------|-------|------|
| POST /auth/login | 5 | 15 min |
| POST /auth/register | 3 | 1 hour |
| GET /users | 100 | 1 min |
| POST /requests | 10 | 1 hour |
| GET /requests | 100 | 1 min |
| * (default) | 60 | 1 min |

### Rate Limit Headers

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1696852800
```

### Rate Limit Exceeded (429)

```json
{
  "success": false,
  "error": {
    "code": "RATE_LIMIT",
    "message": "Too many requests",
    "details": "Rate limit exceeded. Please retry after 45 seconds",
    "retry_after": 45,
    "reset_at": "2025-10-09T12:31:45Z"
  }
}
```

---

## 🔧 Общие правила валидации

### Строковые поля

- **Обязательные строки**: не пустые, обрезаются пробелы
- **Email**: RFC 5322 compliant, lowercase, max 255
- **Phone**: E.164 format, начинается с +998 для Узбекистана
- **UUID**: версия 4, lowercase
- **Даты**: ISO 8601 формат (YYYY-MM-DDTHH:mm:ssZ)

### Числовые поля

- **Pagination**: page >= 1, per_page: 1-100
- **Координаты**: lat: -90 to 90, lng: -180 to 180
- **Рейтинг**: 1.0 to 5.0, шаг 0.1

### Файлы и медиа

- **Изображения**: JPEG, PNG, WebP, max 10MB
- **Документы**: PDF, DOC, DOCX, max 20MB
- **Максимум файлов**: 10 per request

---

## 📝 Примеры интеграции

### Python (requests)

```python
import requests
from typing import Dict, Any

class CoreServiceClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        })

    def create_request(self, data: Dict[str, Any]) -> Dict[str, Any]:
        response = self.session.post(
            f'{self.base_url}/api/v1/requests',
            json=data
        )
        response.raise_for_status()
        return response.json()

    def get_request(self, request_number: str) -> Dict[str, Any]:
        response = self.session.get(
            f'{self.base_url}/api/v1/requests/{request_number}'
        )
        response.raise_for_status()
        return response.json()

# Использование
client = CoreServiceClient('https://api.example.com', 'your_api_key')

# Создание заявки
new_request = client.create_request({
    'title': 'Протечка крана',
    'description': 'Течет кран в кухне, нужен ремонт',
    'category_id': 2,
    'priority': 'high',
    'location': {
        'building_id': '123e4567-e89b-12d3-a456-426614174000',
        'apartment': '42'
    }
})

print(f"Создана заявка: {new_request['data']['request_number']}")
```

### JavaScript/TypeScript (axios)

```typescript
import axios, { AxiosInstance } from 'axios';

interface RequestData {
  title: string;
  description: string;
  category_id: number;
  priority?: 'low' | 'medium' | 'high' | 'urgent';
  location: {
    building_id: string;
    apartment?: string;
  };
}

class CoreServiceClient {
  private client: AxiosInstance;

  constructor(baseURL: string, apiKey: string) {
    this.client = axios.create({
      baseURL,
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json'
      }
    });

    // Interceptor для обработки ошибок
    this.client.interceptors.response.use(
      response => response.data,
      error => {
        if (error.response?.data?.error) {
          throw new Error(error.response.data.error.message);
        }
        throw error;
      }
    );
  }

  async createRequest(data: RequestData) {
    const response = await this.client.post('/api/v1/requests', data);
    return response.data;
  }

  async getRequest(requestNumber: string) {
    const response = await this.client.get(`/api/v1/requests/${requestNumber}`);
    return response.data;
  }
}

// Использование
const client = new CoreServiceClient('https://api.example.com', 'your_api_key');

const newRequest = await client.createRequest({
  title: 'Протечка крана',
  description: 'Течет кран в кухне, нужен ремонт',
  category_id: 2,
  priority: 'high',
  location: {
    building_id: '123e4567-e89b-12d3-a456-426614174000',
    apartment: '42'
  }
});

console.log(`Создана заявка: ${newRequest.request_number}`);
```

---

## 📚 Дополнительная документация

- [OpenAPI спецификация](./openapi/core_service.yaml)
- [Postman коллекция](./postman/core_service.json)
- [GraphQL схема](./graphql/core_service.graphql) (planned)
- [gRPC proto файлы](./proto/core_service.proto) (planned)

---

**Последнее обновление**: 09.10.2025
**Версия API**: 1.0.0
**Автор**: Architecture Team