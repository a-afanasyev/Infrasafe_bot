# 📋 Request Service API Reference - Bot Integration, Search & Export

**Version**: 1.0.0  
**Base URL**: `http://localhost:8003/api/v1`  
**Last Updated**: 6 October 2025

---

## 📋 Table of Contents

- [Bot Integration API](#bot-integration-api)
- [Search API](#search-api)
- [Analytics API](#analytics-api)
- [Export API](#export-api)
- [Internal API](#internal-api)

---

## 🤖 Bot Integration API

Base URL: `/api/v1/bot`

**Специальные endpoints для интеграции с Telegram ботом**. Принимают данные в формате бота (русские поля) и конвертируют во внутренний формат.

---

### POST `/api/v1/bot/requests/create`

**Создание заявки из Telegram бота**

Принимает данные в bot-специфичном формате и создает заявку.

**Request Body** (Bot Format):
```json
{
  "user_id": "123456789",
  "title": "Заявка на ремонт",
  "description": "Описание проблемы от пользователя",
  "address": "ул. Примерная, д. 1",
  "apartment": "123",
  "category": "сантехника",
  "priority": "обычный",
  "phone": "+998901234567",
  "contact_name": "Иван Иванов",
  "is_emergency": false,
  "estimated_cost": 100000,
  "preferred_time": "2025-10-06T10:00:00"
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "request_number": "251006-015",
  "status": "новая",
  "message": "Заявка 251006-015 успешно создана",
  "bot_message": "✅ Ваша заявка принята!\n\nНомер заявки: 251006-015\nСтатус: новая\nКатегория: сантехника\nПриоритет: обычный\n\nМы назначим исполнителя в течение 1-2 часов."
}
```

**Field Mapping** (Bot → Internal):
```python
{
    "user_id" → "applicant_user_id",  # Telegram ID → User ID
    "category" → "category",           # Russian → Russian enum
    "priority" → "priority",           # Russian → Russian enum
    "apartment" → "apartment_number",  # Bot field → DB field
    "phone" → добавляется в description,
    "contact_name" → добавляется в description,
    "is_emergency" → auto-sets priority="аварийный",
    "preferred_time" → сохраняется в metadata
}
```

**cURL Example**:
```bash
curl -X POST "http://localhost:8003/api/v1/bot/requests/create" \
  -H "Authorization: Bearer <service_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "123456789",
    "title": "Протечка",
    "address": "Чиланзар, дом 45",
    "category": "сантехника"
  }'
```

**Side Effects**:
- Отправляется подтверждение в Telegram бот
- Создается request в стандартном формате
- Логируется bot interaction для analytics

---

### PUT `/api/v1/bot/requests/{request_number}/update`

**Обновление заявки из бота**

**Path Parameters**:
- `request_number` (string, required): Номер заявки

**Request Body**:
```json
{
  "user_id": "123456789",
  "title": "Обновленный заголовок",
  "description": "Обновленное описание",
  "priority": "срочный"
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "request_number": "251006-015",
  "updated_fields": ["title", "description", "priority"],
  "message": "Заявка обновлена",
  "bot_message": "✅ Заявка 251006-015 обновлена\n\nОбновлены поля: заголовок, описание, приоритет"
}
```

---

### POST `/api/v1/bot/comments`

**Добавление комментария из бота**

**Request Body**:
```json
{
  "request_number": "251006-015",
  "user_id": "123456789",
  "text": "Когда приедет мастер?",
  "photo_ids": []
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "comment_id": "comment_uuid_10",
  "message": "Комментарий добавлен",
  "bot_message": "💬 Ваш комментарий добавлен к заявке 251006-015"
}
```

---

### GET `/api/v1/bot/search`

**Поиск заявок для бота**

Поиск заявок пользователя с результатом в bot-friendly формате.

**Query Parameters**:
- `user_id` (string, required): Telegram ID пользователя
- `status` (string, optional): Фильтр по статусу
- `limit` (integer, optional): Количество результатов (default: 10)

**Response** (200 OK):
```json
{
  "success": true,
  "user_id": "123456789",
  "total": 5,
  "requests": [
    {
      "number": "251006-001",
      "title": "Протечка в ванной",
      "status": "в работе",
      "executor_name": "Иван Петров",
      "created": "6 окт, 10:30",
      "priority_emoji": "🔴",
      "category_emoji": "🚿"
    },
    {
      "number": "251005-042",
      "title": "Замена лампочки",
      "status": "выполнена",
      "executor_name": "Петр Сидоров",
      "created": "5 окт, 14:00",
      "rating": 5,
      "priority_emoji": "🟢",
      "category_emoji": "💡"
    }
  ],
  "bot_formatted_message": "📋 Ваши заявки (5):\n\n🔴 251006-001 - Протечка в ванной\n📊 Статус: в работе\n👷 Мастер: Иван Петров\n📅 6 окт, 10:30\n\n..."
}
```

**cURL Example**:
```bash
curl -X GET "http://localhost:8003/api/v1/bot/search?user_id=123456789&status=в работе" \
  -H "Authorization: Bearer <service_token>"
```

---

## 🔍 Search API

Base URL: `/api/v1/search`

---

### GET `/api/v1/search`

**Полнотекстовый поиск по заявкам**

Выполняет full-text search по title, description и комментариям с поддержкой фильтров.

**Query Parameters**:
- `q` (string, required): Поисковый запрос
- `status` (string, optional): Фильтр по статусу
- `category` (string, optional): Фильтр по категории
- `date_from` (datetime, optional): Начальная дата
- `date_to` (datetime, optional): Конечная дата
- `limit` (integer, optional): Количество результатов (default: 20)
- `offset` (integer, optional): Смещение для пагинации

**Response** (200 OK):
```json
{
  "query": "протечка",
  "total_found": 47,
  "search_time_ms": 45,
  "results": [
    {
      "request_number": "251006-001",
      "title": "Протечка в ванной комнате",
      "description": "Под раковиной протекает труба...",
      "status": "в работе",
      "category": "сантехника",
      "match_score": 0.95,
      "match_fields": ["title", "description"],
      "highlight": {
        "title": "<mark>Протечка</mark> в ванной комнате",
        "description": "Под раковиной <mark>протекает</mark> труба..."
      },
      "created_at": "2025-10-06T10:30:00Z"
    },
    {
      "request_number": "251005-023",
      "title": "Ремонт водопровода",
      "description": "Большая протечка на кухне",
      "status": "выполнена",
      "category": "сантехника",
      "match_score": 0.87,
      "match_fields": ["description"],
      "highlight": {
        "description": "Большая <mark>протечка</mark> на кухне"
      },
      "created_at": "2025-10-05T14:00:00Z"
    }
  ],
  "aggregations": {
    "by_status": {"в работе": 5, "выполнена": 42},
    "by_category": {"сантехника": 47}
  }
}
```

**cURL Example**:
```bash
curl -X GET "http://localhost:8003/api/v1/search?q=протечка&status=в работе&limit=10" \
  -H "Authorization: Bearer <service_token>"
```

**Search Features**:
- ✅ **Full-text search** по title, description, comments
- ✅ **Relevance ranking** (match_score)
- ✅ **Highlighting** найденных слов
- ✅ **Фильтрация** по status, category, dates
- ✅ **Aggregations** для faceted search

---

### POST `/api/v1/search/advanced`

**Расширенный поиск с множественными условиями**

Комплексный поиск с AND/OR логикой и диапазонами.

**Request Body**:
```json
{
  "filters": {
    "text_query": "протечка труба",
    "statuses": ["новая", "назначена", "в работе"],
    "categories": ["сантехника"],
    "priorities": ["срочный", "аварийный"],
    "date_range": {
      "from": "2025-10-01T00:00:00Z",
      "to": "2025-10-06T23:59:59Z"
    },
    "has_media": true,
    "has_materials": false,
    "executor_assigned": null,
    "min_cost": 50000,
    "max_cost": 200000
  },
  "sort_by": "created_at",
  "sort_order": "desc",
  "limit": 20,
  "offset": 0
}
```

**Response** (200 OK):
```json
{
  "total_found": 12,
  "filters_applied": 8,
  "results": [...],
  "execution_plan": {
    "indexes_used": ["idx_requests_status", "idx_requests_category", "idx_requests_created_at"],
    "query_time_ms": 23
  }
}
```

**cURL Example**:
```bash
curl -X POST "http://localhost:8003/api/v1/search/advanced" \
  -H "Authorization: Bearer <service_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "filters": {
      "text_query": "протечка",
      "statuses": ["в работе"],
      "priorities": ["срочный"]
    },
    "limit": 10
  }'
```

---

## 📊 Analytics API

Base URL: `/api/v1/analytics`

---

### GET `/api/v1/analytics`

**Общая аналитика заявок**

Возвращает comprehensive analytics по заявкам за указанный период.

**Query Parameters**:
- `date_from` (datetime, optional): Начальная дата (default: 30 days ago)
- `date_to` (datetime, optional): Конечная дата (default: now)
- `group_by` (string, optional): Группировка (day, week, month)

**Response** (200 OK):
```json
{
  "period": {
    "from": "2025-09-06T00:00:00Z",
    "to": "2025-10-06T23:59:59Z",
    "days": 30
  },
  "summary": {
    "total_requests": 1547,
    "completed_requests": 1245,
    "completion_rate": 80.5,
    "avg_completion_time_hours": 18.5,
    "avg_rating": 4.3
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
  "trends": {
    "daily_average": 51.6,
    "weekly_growth": 5.2,
    "peak_day": "Понедельник",
    "peak_hours": [9, 10, 14, 15]
  },
  "geographic_distribution": {
    "Чиланзар": 387,
    "Юнусабад": 312,
    "Мирзо-Улугбек": 245,
    "Другие": 603
  }
}
```

**cURL Example**:
```bash
curl -X GET "http://localhost:8003/api/v1/analytics?date_from=2025-09-01T00:00:00Z&group_by=week" \
  -H "Authorization: Bearer <service_token>"
```

---

### GET `/api/v1/analytics/executor-stats`

**Статистика по исполнителям**

Рейтинг и производительность исполнителей.

**Query Parameters**:
- `period_days` (integer, optional): Период в днях (default: 30)
- `min_requests` (integer, optional): Минимум заявок для включения в рейтинг (default: 5)
- `sort_by` (string, optional): Сортировка (rating, completed, speed) (default: rating)

**Response** (200 OK):
```json
{
  "period_days": 30,
  "total_executors": 45,
  "top_performers": [
    {
      "executor_id": 15,
      "executor_name": "Иван Петров",
      "total_requests": 87,
      "completed_requests": 85,
      "completion_rate": 97.7,
      "avg_rating": 4.8,
      "avg_completion_time_hours": 12.3,
      "specialization": ["сантехника", "вентиляция"],
      "total_revenue": 8500000.0
    },
    {
      "executor_id": 23,
      "executor_name": "Сергей Иванов",
      "total_requests": 76,
      "completed_requests": 73,
      "completion_rate": 96.1,
      "avg_rating": 4.6,
      "avg_completion_time_hours": 14.1,
      "specialization": ["сантехника"],
      "total_revenue": 6800000.0
    }
  ],
  "category_leaders": {
    "сантехника": {"executor_id": 15, "score": 98.5},
    "электрика": {"executor_id": 34, "score": 97.2},
    "уборка": {"executor_id": 45, "score": 96.8}
  }
}
```

**cURL Example**:
```bash
curl -X GET "http://localhost:8003/api/v1/analytics/executor-stats?period_days=30&sort_by=rating" \
  -H "Authorization: Bearer <service_token>"
```

---

### GET `/api/v1/analytics/trends`

**Анализ трендов**

Временные тренды создания и выполнения заявок.

**Query Parameters**:
- `period_days` (integer, optional): Период для анализа (default: 90)
- `granularity` (string, optional): Детализация (day, week, month) (default: day)

**Response** (200 OK):
```json
{
  "period_days": 90,
  "granularity": "day",
  "trend_analysis": {
    "overall_trend": "growing",
    "growth_rate_percentage": 5.2,
    "seasonal_pattern": "weekday_peaks",
    "forecast_next_week": 380
  },
  "daily_data": [
    {
      "date": "2025-10-06",
      "created": 52,
      "completed": 48,
      "avg_completion_time": 17.5,
      "avg_rating": 4.4
    },
    {
      "date": "2025-10-05",
      "created": 48,
      "completed": 51,
      "avg_completion_time": 18.2,
      "avg_rating": 4.3
    }
  ],
  "peak_analysis": {
    "busiest_day_of_week": "Понедельник",
    "busiest_hours": [9, 10, 14, 15],
    "lowest_hours": [0, 1, 2, 3, 22, 23]
  }
}
```

**cURL Example**:
```bash
curl -X GET "http://localhost:8003/api/v1/analytics/trends?period_days=90&granularity=week" \
  -H "Authorization: Bearer <service_token>"
```

---

## 📤 Export API

Base URL: `/api/v1/export`

---

### GET `/api/v1/export/excel/{request_number}`

**Экспорт заявки в Excel**

Создает Excel файл с полной информацией о заявке (request + comments + ratings + materials).

**Path Parameters**:
- `request_number` (string, required): Номер заявки

**Query Parameters**:
- `include_comments` (boolean, optional): Включить комментарии (default: true)
- `include_materials` (boolean, optional): Включить материалы (default: true)
- `include_photos` (boolean, optional): Включить фото как вложения (default: false)

**Response** (200 OK):
```
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename="request_251006-001.xlsx"

<Excel file binary data>
```

**Excel Structure**:
- **Sheet 1**: Основная информация о заявке
- **Sheet 2**: Комментарии (если `include_comments=true`)
- **Sheet 3**: Материалы (если `include_materials=true`)
- **Sheet 4**: Рейтинги и отзывы

**cURL Example**:
```bash
curl -X GET "http://localhost:8003/api/v1/export/excel/251006-001?include_comments=true" \
  -H "Authorization: Bearer <service_token>" \
  --output request_251006-001.xlsx
```

---

### GET `/api/v1/export/csv`

**Экспорт списка заявок в CSV**

Экспортирует отфильтрованный список заявок в CSV формат.

**Query Parameters** (те же что и для `/requests`):
- `status` (string, optional): Фильтр по статусу
- `category` (string, optional): Фильтр по категории
- `date_from` (datetime, optional): Начальная дата
- `date_to` (datetime, optional): Конечная дата
- `executor_id` (integer, optional): Фильтр по исполнителю

**Response** (200 OK):
```
Content-Type: text/csv; charset=utf-8
Content-Disposition: attachment; filename="requests_export_2025-10-06.csv"

request_number,title,status,category,priority,address,executor_id,created_at
251006-001,Протечка в ванной,в работе,сантехника,срочный,"Чиланзар, дом 45",15,2025-10-06T10:30:00Z
251006-002,Не работает розетка,назначена,электрика,обычный,"Юнусабад, дом 78",23,2025-10-06T11:00:00Z
...
```

**cURL Example**:
```bash
curl -X GET "http://localhost:8003/api/v1/export/csv?status=выполнена&date_from=2025-10-01" \
  -H "Authorization: Bearer <service_token>" \
  --output requests_export.csv
```

---

### POST `/api/v1/export/bulk-export`

**Массовый экспорт заявок**

Экспортирует множество заявок в один Excel файл с множественными sheets.

**Request Body**:
```json
{
  "request_numbers": ["251006-001", "251006-002", "251006-003"],
  "format": "excel",
  "include_comments": true,
  "include_materials": true,
  "include_ratings": true
}
```

**Response** (200 OK):
```
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename="requests_bulk_export_2025-10-06.xlsx"

<Excel file with multiple sheets>
```

**Excel Structure**:
- **Sheet "Заявки"**: Список всех заявок
- **Sheet "251006-001"**: Детали первой заявки
- **Sheet "251006-002"**: Детали второй заявки
- **Sheet "Материалы"**: Сводка по всем материалам
- **Sheet "Статистика"**: Агрегированная статистика

**cURL Example**:
```bash
curl -X POST "http://localhost:8003/api/v1/export/bulk-export" \
  -H "Authorization: Bearer <service_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "request_numbers": ["251006-001", "251006-002"],
    "format": "excel"
  }' \
  --output bulk_export.xlsx
```

---

### GET `/api/v1/export/template`

**Получение шаблона для импорта заявок**

Возвращает Excel шаблон для массового импорта заявок.

**Response** (200 OK):
```
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename="request_import_template.xlsx"

<Excel template with headers and sample data>
```

**Template Columns**:
- title, description, category, priority, address, apartment_number, applicant_user_id

**cURL Example**:
```bash
curl -X GET "http://localhost:8003/api/v1/export/template" \
  -H "Authorization: Bearer <service_token>" \
  --output import_template.xlsx
```

---

## 🔧 Internal API

Base URL: `/api/v1/internal`

**Endpoints для межсервисного взаимодействия и мониторинга.**

---

### GET `/api/v1/internal/stats`

**Внутренняя статистика сервиса**

Детальная статистика для мониторинга и debugging.

**Response** (200 OK):
```json
{
  "service_name": "request-service",
  "version": "1.0.0",
  "uptime_seconds": 86400,
  "requests": {
    "total": 1547,
    "last_24h": 52,
    "last_hour": 3
  },
  "database": {
    "pool_size": 10,
    "active_connections": 3,
    "idle_connections": 7,
    "query_count_24h": 15234,
    "slow_queries_24h": 2
  },
  "redis": {
    "connected": true,
    "hit_rate": 89.5,
    "keys_count": 156,
    "memory_used_mb": 12.5
  },
  "request_numbers": {
    "today_prefix": "251006",
    "current_counter": 15,
    "generation_method": "redis",
    "redis_ttl_seconds": 43200
  },
  "service_health": {
    "auth_service": "healthy",
    "user_service": "healthy",
    "media_service": "healthy",
    "notification_service": "healthy"
  }
}
```

**cURL Example**:
```bash
curl -X GET "http://localhost:8003/api/v1/internal/stats" \
  -H "Authorization: Bearer <service_token>"
```

---

### POST `/api/v1/internal/sync-data`

**Синхронизация данных с монолитом**

Запускает процесс синхронизации данных с legacy монолитом (dual-write mode).

**Request Body**:
```json
{
  "sync_type": "full",
  "direction": "bidirectional",
  "request_numbers": [],
  "dry_run": false
}
```

**Request Body Schema**:
- `sync_type` (string, required): Тип синхронизации (full, incremental, selective)
- `direction` (string, required): Направление (to_monolith, from_monolith, bidirectional)
- `request_numbers` (array, optional): Конкретные заявки для selective sync
- `dry_run` (boolean, optional): Тестовый запуск без изменений (default: false)

**Response** (200 OK):
```json
{
  "sync_id": "sync_uuid_1",
  "sync_type": "full",
  "direction": "bidirectional",
  "started_at": "2025-10-06T20:00:00Z",
  "status": "in_progress",
  "progress": {
    "total_requests": 1547,
    "processed": 0,
    "successful": 0,
    "failed": 0
  },
  "estimated_completion": "2025-10-06T20:15:00Z"
}
```

**cURL Example**:
```bash
curl -X POST "http://localhost:8003/api/v1/internal/sync-data" \
  -H "Authorization: Bearer <service_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "sync_type": "incremental",
    "direction": "bidirectional"
  }'
```

---

### GET `/api/v1/internal/health-detailed`

**Детальная проверка здоровья сервиса**

Расширенный health check с проверкой всех зависимостей.

**Response** (200 OK):
```json
{
  "status": "healthy",
  "service": "request-service",
  "version": "1.0.0",
  "timestamp": "2025-10-06T18:00:00Z",
  "checks": {
    "database": {
      "status": "healthy",
      "response_time_ms": 2,
      "pool_available": 7
    },
    "redis": {
      "status": "healthy",
      "response_time_ms": 1,
      "connected": true
    },
    "auth_service": {
      "status": "healthy",
      "response_time_ms": 15,
      "reachable": true
    },
    "user_service": {
      "status": "healthy",
      "response_time_ms": 12,
      "reachable": true
    },
    "media_service": {
      "status": "healthy",
      "response_time_ms": 18,
      "reachable": true
    },
    "notification_service": {
      "status": "healthy",
      "response_time_ms": 10,
      "reachable": true
    }
  },
  "overall_health_score": 100.0,
  "issues": []
}
```

**cURL Example**:
```bash
curl -X GET "http://localhost:8003/api/v1/internal/health-detailed" \
  -H "Authorization: Bearer <service_token>"
```

**Degraded Example** (если есть проблемы):
```json
{
  "status": "degraded",
  "overall_health_score": 75.0,
  "checks": {
    "redis": {
      "status": "unhealthy",
      "error": "Connection timeout",
      "fallback_active": true
    }
  },
  "issues": [
    {
      "component": "redis",
      "severity": "warning",
      "message": "Redis unavailable, using PostgreSQL fallback for request numbering"
    }
  ]
}
```

---

### POST `/api/v1/internal/cache-clear`

**Очистка кэша**

Очищает Redis кэш сервиса (для debugging или после обновлений).

**Request Body**:
```json
{
  "cache_types": ["request_numbers", "analytics", "search_results"],
  "force": false
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "cleared_caches": ["request_numbers", "analytics", "search_results"],
  "keys_deleted": 156,
  "execution_time_ms": 45
}
```

**cURL Example**:
```bash
curl -X POST "http://localhost:8003/api/v1/internal/cache-clear" \
  -H "Authorization: Bearer <service_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "cache_types": ["analytics"]
  }'
```

---

## 🔍 Common Integration Patterns

### Pattern 1: Complete Request Flow (Bot → Service)

```bash
# Step 1: Пользователь создает заявку через бота
POST /api/v1/bot/requests/create
{
  "user_id": "123456789",
  "title": "Протечка",
  "category": "сантехника"
}
# Response: request_number = "251006-001"

# Step 2: AI автоматически назначает исполнителя
POST /api/v1/ai/auto-assign
{
  "request_number": "251006-001"
}
# Response: executor_id = 15

# Step 3: Исполнитель добавляет комментарий
POST /api/v1/requests/251006-001/comments
{
  "comment_text": "Начинаю работу",
  "author_user_id": 15
}

# Step 4: Исполнитель добавляет материалы
POST /api/v1/requests/251006-001/materials/bulk
{
  "materials": [{"material_name": "Труба", "quantity": 2, ...}]
}

# Step 5: Исполнитель завершает работу
PATCH /api/v1/requests/251006-001/status
{
  "new_status": "выполнена"
}

# Step 6: Заявитель оценивает работу
POST /api/v1/requests/251006-001/ratings
{
  "rating": 5,
  "feedback": "Отлично!"
}
```

---

### Pattern 2: Manager Dashboard Analytics

```bash
# Step 1: Получить статистику за месяц
GET /api/v1/analytics?date_from=2025-09-01&date_to=2025-10-01

# Step 2: Получить топ исполнителей
GET /api/v1/analytics/executor-stats?period_days=30&sort_by=rating

# Step 3: Получить тренды
GET /api/v1/analytics/trends?period_days=90&granularity=week

# Step 4: Экспортировать в Excel
GET /api/v1/export/csv?date_from=2025-09-01&status=выполнена
```

---

### Pattern 3: Advanced Search & Filter

```bash
# Step 1: Полнотекстовый поиск
GET /api/v1/search?q=протечка&limit=20

# Step 2: Расширенный поиск с фильтрами
POST /api/v1/search/advanced
{
  "filters": {
    "text_query": "протечка труба",
    "statuses": ["в работе"],
    "priorities": ["срочный", "аварийный"],
    "has_media": true
  }
}

# Step 3: Экспорт результатов
POST /api/v1/export/bulk-export
{
  "request_numbers": ["251006-001", "251006-002", ...],
  "format": "excel"
}
```

---

## 📖 See Also

- [API_REFERENCE_CORE.md](API_REFERENCE_CORE.md) - Core Requests API
- [API_REFERENCE_ASSIGNMENTS.md](API_REFERENCE_ASSIGNMENTS.md) - Assignments API
- [API_REFERENCE_COMMENTS.md](API_REFERENCE_COMMENTS.md) - Comments, Ratings, Materials
- [REQUEST_SERVICE_DOCUMENTATION.md](REQUEST_SERVICE_DOCUMENTATION.md) - Полная документация
- [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) - Руководство по интеграциям


