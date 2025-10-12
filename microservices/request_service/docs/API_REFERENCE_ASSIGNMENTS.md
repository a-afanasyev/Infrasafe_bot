# 📋 Request Service API Reference - Assignments & Workflow API

**Version**: 1.0.0  
**Base URL**: `http://localhost:8003/api/v1`  
**Last Updated**: 6 October 2025

---

## 📋 Table of Contents

- [Assignments API](#assignments-api)
- [AI-Powered Assignment](#ai-powered-assignment)
- [Geocoding API](#geocoding-api)

---

## 👥 Assignments API

Base URL: `/api/v1/assignments`

---

### POST `/api/v1/assignments/assign/{request_number}`

**Назначение исполнителя на заявку (ручное назначение)**

**Path Parameters**:
- `request_number` (string, required): Номер заявки

**Request Body**:
```json
{
  "executor_id": 15,
  "assigned_by": 1,
  "assignment_type": "manual",
  "specialization_required": "сантехник",
  "assignment_reason": "Опыт работы в этом районе"
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "assignment_id": "assignment_uuid_1",
  "request_number": "251006-001",
  "executor_id": 15,
  "assigned_by": 1,
  "assignment_type": "manual",
  "is_active": true,
  "created_at": "2025-10-06T13:00:00Z",
  "notification_sent": true
}
```

**cURL Example**:
```bash
curl -X POST "http://localhost:8003/api/v1/assignments/assign/251006-001" \
  -H "Authorization: Bearer <service_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "executor_id": 15,
    "assigned_by": 1,
    "assignment_type": "manual"
  }'
```

---

### POST `/api/v1/assignments/reassign/{request_number}`

**Переназначение заявки другому исполнителю**

Переназначает заявку от текущего исполнителя к новому. Деактивирует старое assignment, создает новое.

**Path Parameters**:
- `request_number` (string, required): Номер заявки

**Request Body**:
```json
{
  "new_executor_id": 23,
  "reassignment_reason": "Первый исполнитель занят другой аварией",
  "assigned_by": 1
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "request_number": "251006-001",
  "old_executor_id": 15,
  "new_executor_id": 23,
  "reassignment_reason": "Первый исполнитель занят другой аварией",
  "assignment_history": [
    {
      "id": "assignment_uuid_1",
      "executor_id": 15,
      "is_active": false,
      "deactivated_at": "2025-10-06T14:00:00Z",
      "deactivation_reason": "reassignment"
    },
    {
      "id": "assignment_uuid_2",
      "executor_id": 23,
      "is_active": true,
      "created_at": "2025-10-06T14:00:00Z"
    }
  ],
  "notifications_sent": {
    "old_executor": true,
    "new_executor": true
  }
}
```

**cURL Example**:
```bash
curl -X POST "http://localhost:8003/api/v1/assignments/reassign/251006-001" \
  -H "Authorization: Bearer <service_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "new_executor_id": 23,
    "reassignment_reason": "Первый исполнитель занят другой аварией",
    "assigned_by": 1
  }'
```

**Side Effects**:
- Старое assignment деактивируется (`is_active = false`)
- Создается новое assignment
- Отправляются уведомления обоим исполнителям
- Создается audit comment в заявке

---

### POST `/api/v1/assignments/bulk-assign`

**Массовое назначение заявок**

Назначает несколько заявок за один запрос. Использует transaction - либо все успешно, либо rollback.

**Request Body**:
```json
{
  "assignments": [
    {
      "request_number": "251006-001",
      "executor_id": 15
    },
    {
      "request_number": "251006-002",
      "executor_id": 23
    },
    {
      "request_number": "251006-003",
      "executor_id": 15
    }
  ],
  "assigned_by": 1,
  "assignment_type": "manual"
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "total_assignments": 3,
  "successful": 3,
  "failed": 0,
  "results": [
    {
      "request_number": "251006-001",
      "success": true,
      "executor_id": 15
    },
    {
      "request_number": "251006-002",
      "success": true,
      "executor_id": 23
    },
    {
      "request_number": "251006-003",
      "success": true,
      "executor_id": 15
    }
  ],
  "execution_time_ms": 450
}
```

**cURL Example**:
```bash
curl -X POST "http://localhost:8003/api/v1/assignments/bulk-assign" \
  -H "Authorization: Bearer <service_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "assignments": [
      {"request_number": "251006-001", "executor_id": 15},
      {"request_number": "251006-002", "executor_id": 23}
    ],
    "assigned_by": 1
  }'
```

**Transaction Guarantee**:
- Все assignments выполняются в одной транзакции
- Если хоть один fails → rollback всех
- All-or-nothing semantics

---

### GET `/api/v1/assignments/suggestions/{request_number}`

**Получение AI рекомендаций по назначению исполнителя**

Возвращает список рекомендованных исполнителей с оценками (scores) на основе AI алгоритма.

**Path Parameters**:
- `request_number` (string, required): Номер заявки

**Query Parameters**:
- `limit` (integer, optional): Количество рекомендаций (default: 5, max: 20)
- `min_score` (float, optional): Минимальный score (default: 0.5)

**Response** (200 OK):
```json
{
  "request_number": "251006-001",
  "suggestions": [
    {
      "executor_id": 15,
      "executor_name": "Иван Петров",
      "score": 0.92,
      "confidence": "high",
      "factors": {
        "specialization_match": 0.95,
        "geographic_proximity": 0.88,
        "current_workload": 0.91,
        "rating": 0.94,
        "urgency_alignment": 0.93
      },
      "explanation": "Высокая специализация сантехника, близко к объекту (2.3км), низкая текущая нагрузка",
      "distance_km": 2.3,
      "current_active_requests": 2,
      "avg_rating": 4.7,
      "estimated_response_time_minutes": 30
    },
    {
      "executor_id": 23,
      "executor_name": "Сергей Иванов",
      "score": 0.87,
      "confidence": "high",
      "factors": {
        "specialization_match": 0.90,
        "geographic_proximity": 0.75,
        "current_workload": 0.95,
        "rating": 0.88,
        "urgency_alignment": 0.87
      },
      "explanation": "Сантехник, немного дальше (4.5км), очень низкая нагрузка",
      "distance_km": 4.5,
      "current_active_requests": 1,
      "avg_rating": 4.4,
      "estimated_response_time_minutes": 45
    }
  ],
  "algorithm": "ai_weighted_scoring",
  "weights": {
    "specialization": 0.35,
    "geography": 0.25,
    "workload": 0.20,
    "rating": 0.15,
    "urgency": 0.05
  },
  "processing_time_ms": 120
}
```

**cURL Example**:
```bash
curl -X GET "http://localhost:8003/api/v1/assignments/suggestions/251006-001?limit=5" \
  -H "Authorization: Bearer <service_token>"
```

**Algorithm Details**:
- **specialization_match** (35%): Соответствие специализации исполнителя категории заявки
- **geographic_proximity** (25%): Близость к месту работы
- **current_workload** (20%): Текущая загрузка исполнителя
- **rating** (15%): Средний рейтинг исполнителя
- **urgency_alignment** (5%): Соответствие доступности срочности

---

### GET `/api/v1/assignments/workload/{executor_id}`

**Анализ загрузки исполнителя**

Возвращает детальную информацию о текущей и прогнозируемой загрузке исполнителя.

**Path Parameters**:
- `executor_id` (integer, required): ID исполнителя

**Query Parameters**:
- `include_forecast` (boolean, optional): Включить прогноз на неделю (default: false)

**Response** (200 OK):
```json
{
  "executor_id": 15,
  "current_workload": {
    "active_requests": 3,
    "assigned_requests": 5,
    "total_requests": 8,
    "capacity_percentage": 80.0,
    "status": "high_load"
  },
  "request_breakdown": {
    "by_status": {
      "назначена": 2,
      "в работе": 3,
      "заказаны материалы": 1,
      "ожидает оплаты": 2
    },
    "by_priority": {
      "срочный": 2,
      "высокий": 3,
      "обычный": 3
    },
    "by_category": {
      "сантехника": 6,
      "обслуживание": 2
    }
  },
  "performance_metrics": {
    "avg_completion_time_hours": 12.5,
    "completion_rate": 95.0,
    "avg_rating": 4.7,
    "total_completed": 87
  },
  "availability": {
    "is_available": false,
    "next_available_slot": "2025-10-07T09:00:00Z",
    "reason": "At capacity (8/10 requests)"
  },
  "weekly_forecast": {
    "predicted_new_assignments": 5,
    "predicted_completions": 6,
    "expected_capacity_next_week": 70.0
  }
}
```

**cURL Example**:
```bash
curl -X GET "http://localhost:8003/api/v1/assignments/workload/15?include_forecast=true" \
  -H "Authorization: Bearer <service_token>"
```

---

### GET `/api/v1/assignments/history/{request_number}`

**История назначений заявки**

Возвращает полную историю всех назначений и переназначений заявки.

**Path Parameters**:
- `request_number` (string, required): Номер заявки

**Response** (200 OK):
```json
{
  "request_number": "251006-001",
  "total_assignments": 2,
  "current_assignment": {
    "id": "assignment_uuid_2",
    "executor_id": 23,
    "assigned_by": 1,
    "assignment_type": "manual",
    "is_active": true,
    "created_at": "2025-10-06T14:00:00Z"
  },
  "history": [
    {
      "id": "assignment_uuid_1",
      "executor_id": 15,
      "assigned_by": 1,
      "assignment_type": "manual",
      "is_active": false,
      "created_at": "2025-10-06T13:00:00Z",
      "deactivated_at": "2025-10-06T14:00:00Z",
      "deactivation_reason": "reassignment",
      "duration_minutes": 60
    },
    {
      "id": "assignment_uuid_2",
      "executor_id": 23,
      "assigned_by": 1,
      "assignment_type": "manual",
      "is_active": true,
      "created_at": "2025-10-06T14:00:00Z",
      "deactivated_at": null
    }
  ]
}
```

**cURL Example**:
```bash
curl -X GET "http://localhost:8003/api/v1/assignments/history/251006-001" \
  -H "Authorization: Bearer <service_token>"
```

---

### POST `/api/v1/assignments/accept/{assignment_id}`

**Принятие назначения исполнителем**

Исполнитель подтверждает, что готов выполнить работу.

**Path Parameters**:
- `assignment_id` (string, required): UUID назначения

**Request Body**:
```json
{
  "executor_id": 15,
  "estimated_start_time": "2025-10-06T15:00:00Z",
  "notes": "Приму заявку, приеду через час"
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "assignment_id": "assignment_uuid_1",
  "accepted_at": "2025-10-06T14:30:00Z",
  "estimated_start_time": "2025-10-06T15:00:00Z",
  "notification_sent": true
}
```

**cURL Example**:
```bash
curl -X POST "http://localhost:8003/api/v1/assignments/accept/assignment_uuid_1" \
  -H "Authorization: Bearer <service_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "executor_id": 15,
    "estimated_start_time": "2025-10-06T15:00:00Z"
  }'
```

---

### POST `/api/v1/assignments/reject/{assignment_id}`

**Отклонение назначения исполнителем**

Исполнитель отказывается от назначения. Заявка возвращается в статус "новая" для повторного назначения.

**Path Parameters**:
- `assignment_id` (string, required): UUID назначения

**Request Body**:
```json
{
  "executor_id": 15,
  "rejection_reason": "Нет необходимых инструментов",
  "suggest_alternative": 23
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "assignment_id": "assignment_uuid_1",
  "rejected_at": "2025-10-06T14:15:00Z",
  "rejection_reason": "Нет необходимых инструментов",
  "request_status_reset_to": "новая",
  "alternative_suggestion": {
    "executor_id": 23,
    "reason": "Suggested by rejecting executor"
  }
}
```

**cURL Example**:
```bash
curl -X POST "http://localhost:8003/api/v1/assignments/reject/assignment_uuid_1" \
  -H "Authorization: Bearer <service_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "executor_id": 15,
    "rejection_reason": "Нет необходимых инструментов"
  }'
```

---

### GET `/api/v1/assignments/active/{executor_id}`

**Активные назначения исполнителя**

Возвращает все активные заявки, назначенные конкретному исполнителю.

**Path Parameters**:
- `executor_id` (integer, required): ID исполнителя

**Query Parameters**:
- `include_completed` (boolean, optional): Включить завершенные за сегодня (default: false)

**Response** (200 OK):
```json
{
  "executor_id": 15,
  "active_assignments": 3,
  "requests": [
    {
      "request_number": "251006-001",
      "title": "Протечка в ванной",
      "status": "в работе",
      "priority": "срочный",
      "address": "Чиланзар, дом 45",
      "assigned_at": "2025-10-06T13:00:00Z",
      "duration_so_far_minutes": 120
    },
    {
      "request_number": "251006-005",
      "title": "Замена крана",
      "status": "назначена",
      "priority": "обычный",
      "address": "Юнусабад, дом 12",
      "assigned_at": "2025-10-06T14:30:00Z",
      "duration_so_far_minutes": 30
    },
    {
      "request_number": "251006-008",
      "title": "Проверка счетчика",
      "status": "назначена",
      "priority": "низкий",
      "address": "Мирзо-Улугбек, дом 89",
      "assigned_at": "2025-10-06T15:00:00Z",
      "duration_so_far_minutes": 0
    }
  ],
  "workload_summary": {
    "capacity_used": 80.0,
    "estimated_completion_time": "2025-10-07T09:00:00Z"
  }
}
```

**cURL Example**:
```bash
curl -X GET "http://localhost:8003/api/v1/assignments/active/15" \
  -H "Authorization: Bearer <service_token>"
```

---

## 🤖 AI-Powered Assignment

Base URL: `/api/v1/ai`

---

### POST `/api/v1/ai/auto-assign`

**Автоматическое назначение с использованием AI**

AI анализирует заявку и автоматически назначает лучшего исполнителя на основе weighted scoring алгоритма.

**Request Body**:
```json
{
  "request_number": "251006-001",
  "min_score_threshold": 0.7,
  "auto_notify": true,
  "assigned_by": 1
}
```

**Request Body Schema**:
- `request_number` (string, required): Номер заявки
- `min_score_threshold` (float, optional): Минимальный score для назначения (default: 0.7)
- `auto_notify` (boolean, optional): Отправить уведомление автоматически (default: true)
- `assigned_by` (integer, optional): ID пользователя (default: system user)

**Response** (200 OK):
```json
{
  "success": true,
  "request_number": "251006-001",
  "assigned_executor": {
    "executor_id": 15,
    "executor_name": "Иван Петров",
    "score": 0.92,
    "confidence": "high",
    "estimated_arrival_time": "2025-10-06T15:00:00Z"
  },
  "algorithm_details": {
    "algorithm_used": "weighted_scoring_v2",
    "factors_evaluated": {
      "specialization_match": 0.95,
      "geographic_proximity": 0.88,
      "current_workload": 0.91,
      "executor_rating": 0.94,
      "urgency_alignment": 0.93
    },
    "alternatives_considered": 5,
    "processing_time_ms": 89
  },
  "assignment_id": "assignment_uuid_1",
  "notification_sent": true
}
```

**cURL Example**:
```bash
curl -X POST "http://localhost:8003/api/v1/ai/auto-assign" \
  -H "Authorization: Bearer <service_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "request_number": "251006-001",
    "min_score_threshold": 0.7
  }'
```

**AI Algorithm Details**:

```python
# Weighted scoring formula
score = (
    specialization_match * 0.35 +  # 35% вес
    geographic_proximity * 0.25 +   # 25% вес
    workload_balance * 0.20 +       # 20% вес
    executor_rating * 0.15 +        # 15% вес
    urgency_alignment * 0.05        # 5% вес
)

# Пороги confidence
score >= 0.9 → "high" confidence
score >= 0.7 → "medium" confidence
score >= 0.5 → "low" confidence
score < 0.5  → не назначается
```

**Error Responses**:
- `400 Bad Request` - Заявка уже назначена или в неподходящем статусе
- `404 Not Found` - Заявка не найдена
- `503 Service Unavailable` - AI Service недоступен (используется fallback)

---

### POST `/api/v1/ai/batch-suggestions`

**Массовое получение рекомендаций для нескольких заявок**

Получает AI рекомендации для списка заявок за один запрос. Оптимизирован для bulk операций.

**Request Body**:
```json
{
  "request_numbers": ["251006-001", "251006-002", "251006-003"],
  "limit_per_request": 3,
  "min_score_threshold": 0.6
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "total_requests": 3,
  "suggestions": {
    "251006-001": [
      {"executor_id": 15, "score": 0.92},
      {"executor_id": 23, "score": 0.87},
      {"executor_id": 45, "score": 0.81}
    ],
    "251006-002": [
      {"executor_id": 23, "score": 0.89},
      {"executor_id": 34, "score": 0.85}
    ],
    "251006-003": [
      {"executor_id": 15, "score": 0.88}
    ]
  },
  "processing_time_ms": 250
}
```

**cURL Example**:
```bash
curl -X POST "http://localhost:8003/api/v1/ai/batch-suggestions" \
  -H "Authorization: Bearer <service_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "request_numbers": ["251006-001", "251006-002"],
    "limit_per_request": 3
  }'
```

---

### POST `/api/v1/ai/optimize-assignments`

**Оптимизация существующих назначений**

AI анализирует все активные назначения и предлагает оптимизации (переназначения) для улучшения общей эффективности.

**Request Body**:
```json
{
  "optimize_for": "geographic",
  "include_reassignments": true,
  "max_reassignments": 5
}
```

**Request Body Schema**:
- `optimize_for` (string, optional): Критерий оптимизации (geographic, workload, rating, balanced)
- `include_reassignments` (boolean, optional): Включить предложения переназначений (default: true)
- `max_reassignments` (integer, optional): Максимум переназначений (default: 10)

**Response** (200 OK):
```json
{
  "success": true,
  "current_state": {
    "total_active_requests": 45,
    "avg_distance_km": 5.7,
    "workload_balance_score": 0.73,
    "geographic_efficiency": 0.68
  },
  "optimized_state": {
    "projected_avg_distance_km": 3.2,
    "projected_workload_balance": 0.89,
    "projected_geographic_efficiency": 0.92,
    "improvement_percentage": 35.3
  },
  "recommendations": [
    {
      "request_number": "251006-003",
      "current_executor": 45,
      "recommended_executor": 23,
      "reason": "Сократит расстояние с 8.5км до 1.2км",
      "score_improvement": 0.15,
      "impact": "high"
    },
    {
      "request_number": "251006-007",
      "current_executor": 15,
      "recommended_executor": 34,
      "reason": "Балансировка нагрузки (executor 15 перегружен)",
      "score_improvement": 0.08,
      "impact": "medium"
    }
  ],
  "total_recommendations": 5,
  "processing_time_ms": 450
}
```

**cURL Example**:
```bash
curl -X POST "http://localhost:8003/api/v1/ai/optimize-assignments" \
  -H "Authorization: Bearer <service_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "optimize_for": "balanced",
    "max_reassignments": 5
  }'
```

---

## 🗺️ Geocoding API

Base URL: `/api/v1/geocoding`

---

### POST `/api/v1/geocoding/geocode`

**Преобразование адреса в координаты**

Конвертирует текстовый адрес в GPS координаты с использованием геокодера.

**Request Body**:
```json
{
  "address": "Чиланзар, район 12, дом 45",
  "prefer_local": true,
  "language": "ru"
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "address": "Чиланзар, район 12, дом 45",
  "latitude": 41.2995,
  "longitude": 69.2401,
  "confidence": 0.95,
  "geocoder": "nominatim",
  "normalized_address": "Chilanzar District 12, Building 45, Tashkent, Uzbekistan",
  "district": "Чиланзар",
  "city": "Ташкент",
  "processing_time_ms": 120
}
```

**cURL Example**:
```bash
curl -X POST "http://localhost:8003/api/v1/geocoding/geocode" \
  -H "Authorization: Bearer <service_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "address": "Чиланзар, район 12, дом 45",
    "prefer_local": true
  }'
```

---

### POST `/api/v1/geocoding/reverse`

**Преобразование координат в адрес**

Получает адрес по GPS координатам (reverse geocoding).

**Request Body**:
```json
{
  "latitude": 41.2995,
  "longitude": 69.2401,
  "language": "ru"
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "latitude": 41.2995,
  "longitude": 69.2401,
  "address": "Чиланзар, район 12, дом 45",
  "district": "Чиланзар",
  "city": "Ташкент",
  "country": "Узбекистан",
  "confidence": 0.92,
  "geocoder": "nominatim"
}
```

**cURL Example**:
```bash
curl -X POST "http://localhost:8003/api/v1/geocoding/reverse" \
  -H "Authorization: Bearer <service_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "latitude": 41.2995,
    "longitude": 69.2401
  }'
```

---

### POST `/api/v1/geocoding/batch-geocode`

**Массовое геокодирование адресов**

Геокодирует несколько адресов за один запрос.

**Request Body**:
```json
{
  "addresses": [
    "Чиланзар, район 12, дом 45",
    "Юнусабад, дом 78",
    "Мирзо-Улугбек, квартал 5, дом 23"
  ],
  "prefer_local": true
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "total": 3,
  "successful": 3,
  "failed": 0,
  "results": [
    {
      "address": "Чиланзар, район 12, дом 45",
      "latitude": 41.2995,
      "longitude": 69.2401,
      "confidence": 0.95
    },
    {
      "address": "Юнусабад, дом 78",
      "latitude": 41.3425,
      "longitude": 69.2887,
      "confidence": 0.88
    },
    {
      "address": "Мирзо-Улугбек, квартал 5, дом 23",
      "latitude": 41.3156,
      "longitude": 69.3286,
      "confidence": 0.91
    }
  ],
  "processing_time_ms": 340
}
```

**cURL Example**:
```bash
curl -X POST "http://localhost:8003/api/v1/geocoding/batch-geocode" \
  -H "Authorization: Bearer <service_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "addresses": [
      "Чиланзар, район 12, дом 45",
      "Юнусабад, дом 78"
    ]
  }'
```

---

### GET `/api/v1/geocoding/districts`

**Получение списка районов города**

Возвращает список всех районов Ташкента с координатами центров.

**Response** (200 OK):
```json
{
  "districts": [
    {
      "name": "Чиланзар",
      "name_en": "Chilanzar",
      "center_latitude": 41.2829,
      "center_longitude": 69.2036,
      "bounds": {
        "north": 41.3100,
        "south": 41.2550,
        "east": 69.2400,
        "west": 69.1650
      }
    },
    {
      "name": "Юнусабад",
      "name_en": "Yunusabad",
      "center_latitude": 41.3425,
      "center_longitude": 69.2887,
      "bounds": {
        "north": 41.3650,
        "south": 41.3200,
        "east": 69.3100,
        "west": 69.2650
      }
    }
  ],
  "total": 12
}
```

**cURL Example**:
```bash
curl -X GET "http://localhost:8003/api/v1/geocoding/districts" \
  -H "Authorization: Bearer <service_token>"
```

---

## 📖 See Also

- [API_REFERENCE_COMMENTS.md](API_REFERENCE_COMMENTS.md) - Comments, Ratings, Materials API
- [API_REFERENCE_INTEGRATION.md](API_REFERENCE_INTEGRATION.md) - Bot, Search, Export API
- [REQUEST_SERVICE_DOCUMENTATION.md](REQUEST_SERVICE_DOCUMENTATION.md) - Полная техническая документация
- [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) - Руководство по интеграциям


