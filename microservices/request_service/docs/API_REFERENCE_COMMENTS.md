# 📋 Request Service API Reference - Comments, Ratings & Materials

**Version**: 1.0.0  
**Base URL**: `http://localhost:8003/api/v1`  
**Last Updated**: 6 October 2025

---

## 📋 Table of Contents

- [Comments API](#comments-api)
- [Ratings API](#ratings-api)
- [Materials API](#materials-api)

---

## 💬 Comments API

Base URL: `/api/v1/requests/{request_number}/comments`

---

### GET `/api/v1/requests/{request_number}/comments`

**Получение всех комментариев к заявке**

Возвращает список комментариев с поддержкой фильтрации по типу (обычные/системные).

**Path Parameters**:
- `request_number` (string, required): Номер заявки

**Query Parameters**:
- `include_internal` (boolean, optional): Включить внутренние комментарии (default: false)
- `include_system` (boolean, optional): Включить системные комментарии (status changes) (default: true)
- `limit` (integer, optional): Количество комментариев (default: 50)
- `offset` (integer, optional): Смещение для пагинации

**Response** (200 OK):
```json
{
  "request_number": "251006-001",
  "total_comments": 5,
  "comments": [
    {
      "id": "comment_uuid_1",
      "comment_text": "Начинаю работу, буду на месте через 30 минут",
      "author_user_id": 15,
      "author_name": "Иван Петров",
      "is_status_change": false,
      "is_internal": false,
      "media_file_ids": [],
      "created_at": "2025-10-06T14:00:00Z"
    },
    {
      "id": "comment_uuid_2",
      "comment_text": "Статус изменен: новая → назначена",
      "author_user_id": 1,
      "author_name": "System",
      "is_status_change": true,
      "old_status": "новая",
      "new_status": "назначена",
      "is_internal": false,
      "created_at": "2025-10-06T13:00:00Z"
    },
    {
      "id": "comment_uuid_3",
      "comment_text": "Внутренняя заметка менеджера: приоритетная заявка",
      "author_user_id": 1,
      "is_status_change": false,
      "is_internal": true,
      "created_at": "2025-10-06T12:30:00Z"
    }
  ]
}
```

**cURL Example**:
```bash
curl -X GET "http://localhost:8003/api/v1/requests/251006-001/comments?include_internal=true" \
  -H "Authorization: Bearer <service_token>"
```

---

### POST `/api/v1/requests/{request_number}/comments`

**Добавление комментария к заявке**

Создает новый комментарий с опциональными медиа-вложениями.

**Path Parameters**:
- `request_number` (string, required): Номер заявки

**Request Body**:
```json
{
  "comment_text": "Обнаружена дополнительная проблема - поврежден сифон",
  "author_user_id": 15,
  "is_internal": false,
  "media_file_ids": ["media_003", "media_004"]
}
```

**Request Body Schema**:
- `comment_text` (string, required): Текст комментария
- `author_user_id` (integer, required): ID автора (User Service)
- `is_internal` (boolean, optional): Внутренний комментарий (видят только менеджеры) (default: false)
- `media_file_ids` (array[string], optional): ID медиафайлов из Media Service

**Response** (201 Created):
```json
{
  "id": "comment_uuid_5",
  "request_number": "251006-001",
  "comment_text": "Обнаружена дополнительная проблема - поврежден сифон",
  "author_user_id": 15,
  "author_name": "Иван Петров",
  "is_internal": false,
  "is_status_change": false,
  "media_file_ids": ["media_003", "media_004"],
  "created_at": "2025-10-06T15:30:00Z"
}
```

**cURL Example**:
```bash
curl -X POST "http://localhost:8003/api/v1/requests/251006-001/comments" \
  -H "Authorization: Bearer <service_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "comment_text": "Обнаружена дополнительная проблема",
    "author_user_id": 15,
    "media_file_ids": ["media_003"]
  }'
```

**Media Attachments**:
- Поддерживаются фото, видео, документы
- Файлы загружаются через Media Service
- ID файлов передаются в `media_file_ids`
- Максимум 10 файлов на комментарий

---

### PUT `/api/v1/requests/{request_number}/comments/{comment_id}`

**Обновление комментария**

Редактирует текст существующего комментария. Можно редактировать только собственные комментарии.

**Path Parameters**:
- `request_number` (string, required): Номер заявки
- `comment_id` (string, required): UUID комментария

**Request Body**:
```json
{
  "comment_text": "Обнаружена дополнительная проблема - поврежден сифон (обновлено)",
  "updated_by": 15
}
```

**Response** (200 OK):
```json
{
  "id": "comment_uuid_5",
  "comment_text": "Обнаружена дополнительная проблема - поврежден сифон (обновлено)",
  "updated_at": "2025-10-06T16:00:00Z",
  "is_edited": true
}
```

**cURL Example**:
```bash
curl -X PUT "http://localhost:8003/api/v1/requests/251006-001/comments/comment_uuid_5" \
  -H "Authorization: Bearer <service_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "comment_text": "Обнаружена дополнительная проблема - поврежден сифон (обновлено)",
    "updated_by": 15
  }'
```

**Validation Rules**:
- Можно редактировать только свои комментарии
- Нельзя редактировать системные комментарии (status changes)
- Менеджеры могут редактировать любые комментарии

---

### DELETE `/api/v1/requests/{request_number}/comments/{comment_id}`

**Удаление комментария (soft delete)**

Помечает комментарий как удаленный. Удаленные комментарии не отображаются, но сохраняются для audit.

**Path Parameters**:
- `request_number` (string, required): Номер заявки
- `comment_id` (string, required): UUID комментария

**Query Parameters**:
- `deleted_by` (integer, required): ID пользователя

**Response** (200 OK):
```json
{
  "id": "comment_uuid_5",
  "is_deleted": true,
  "deleted_at": "2025-10-06T16:30:00Z",
  "deleted_by": 15
}
```

**cURL Example**:
```bash
curl -X DELETE "http://localhost:8003/api/v1/requests/251006-001/comments/comment_uuid_5?deleted_by=15" \
  -H "Authorization: Bearer <service_token>"
```

---

## ⭐ Ratings API

Base URL: `/api/v1/requests/{request_number}/ratings`

---

### POST `/api/v1/requests/{request_number}/ratings`

**Добавление оценки к заявке**

Пользователь оценивает качество выполненной работы по шкале 1-5 звезд с опциональным текстовым отзывом.

**Path Parameters**:
- `request_number` (string, required): Номер заявки

**Request Body**:
```json
{
  "rating": 5,
  "feedback": "Отличная работа! Быстро и качественно, все чисто убрал",
  "author_user_id": 42
}
```

**Request Body Schema**:
- `rating` (integer, required): Оценка от 1 до 5
- `feedback` (string, optional): Текстовый отзыв
- `author_user_id` (integer, required): ID пользователя (обычно applicant)

**Response** (201 Created):
```json
{
  "id": "rating_uuid_1",
  "request_number": "251006-001",
  "rating": 5,
  "feedback": "Отличная работа! Быстро и качественно, все чисто убрал",
  "author_user_id": 42,
  "executor_id": 15,
  "created_at": "2025-10-06T18:00:00Z"
}
```

**cURL Example**:
```bash
curl -X POST "http://localhost:8003/api/v1/requests/251006-001/ratings" \
  -H "Authorization: Bearer <service_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "rating": 5,
    "feedback": "Отличная работа!",
    "author_user_id": 42
  }'
```

**Validation Rules**:
- Заявка должна быть в статусе "выполнена"
- Один пользователь может оставить только одну оценку на заявку
- Rating должен быть от 1 до 5 (включительно)
- Feedback опционален, но рекомендуется для ratings < 4

**Side Effects**:
- Обновляется средний рейтинг исполнителя в User Service
- Создается запись в analytics для tracking
- Исполнитель получает уведомление о новой оценке

---

### GET `/api/v1/requests/{request_number}/ratings`

**Получение всех оценок заявки**

**Path Parameters**:
- `request_number` (string, required): Номер заявки

**Response** (200 OK):
```json
{
  "request_number": "251006-001",
  "total_ratings": 1,
  "average_rating": 5.0,
  "ratings": [
    {
      "id": "rating_uuid_1",
      "rating": 5,
      "feedback": "Отличная работа! Быстро и качественно, все чисто убрал",
      "author_user_id": 42,
      "author_name": "Анна Иванова",
      "created_at": "2025-10-06T18:00:00Z"
    }
  ]
}
```

**cURL Example**:
```bash
curl -X GET "http://localhost:8003/api/v1/requests/251006-001/ratings" \
  -H "Authorization: Bearer <service_token>"
```

---

### GET `/api/v1/ratings/executor/{executor_id}`

**Статистика оценок исполнителя**

Возвращает агрегированную статистику оценок конкретного исполнителя.

**Path Parameters**:
- `executor_id` (integer, required): ID исполнителя

**Query Parameters**:
- `period_days` (integer, optional): Период для статистики в днях (default: 30)

**Response** (200 OK):
```json
{
  "executor_id": 15,
  "period_days": 30,
  "total_ratings": 45,
  "average_rating": 4.7,
  "rating_distribution": {
    "5": 32,
    "4": 10,
    "3": 2,
    "2": 1,
    "1": 0
  },
  "with_feedback_count": 38,
  "positive_feedback_percentage": 95.6,
  "recent_ratings": [
    {
      "request_number": "251006-001",
      "rating": 5,
      "feedback": "Отличная работа!",
      "created_at": "2025-10-06T18:00:00Z"
    }
  ],
  "performance_trend": "improving"
}
```

**cURL Example**:
```bash
curl -X GET "http://localhost:8003/api/v1/ratings/executor/15?period_days=30" \
  -H "Authorization: Bearer <service_token>"
```

---

## 🔧 Materials API

Base URL: `/api/v1/requests/{request_number}/materials`

---

### POST `/api/v1/requests/{request_number}/materials`

**Добавление материала к заявке**

Добавляет запись о материале, необходимом для выполнения работы.

**Path Parameters**:
- `request_number` (string, required): Номер заявки

**Request Body**:
```json
{
  "material_name": "Труба ПВХ 32мм",
  "description": "Канализационная труба, белая, 1 метр",
  "category": "сантехника",
  "quantity": 2.0,
  "unit": "метр",
  "unit_price": 25000.0,
  "supplier": "СтройМаркет",
  "added_by": 15
}
```

**Request Body Schema**:
- `material_name` (string, required): Название материала
- `description` (string, optional): Подробное описание
- `category` (string, optional): Категория материала
- `quantity` (float, required): Количество
- `unit` (string, required): Единица измерения (метр, штука, кг, литр)
- `unit_price` (float, required): Цена за единицу (в сумах)
- `supplier` (string, optional): Поставщик
- `added_by` (integer, required): ID пользователя, добавившего материал

**Response** (201 Created):
```json
{
  "id": "material_uuid_1",
  "request_number": "251006-001",
  "material_name": "Труба ПВХ 32мм",
  "description": "Канализационная труба, белая, 1 метр",
  "category": "сантехника",
  "quantity": 2.0,
  "unit": "метр",
  "unit_price": 25000.0,
  "total_cost": 50000.0,
  "supplier": "СтройМаркет",
  "status": "requested",
  "created_at": "2025-10-06T14:30:00Z"
}
```

**Automatic Total Cost Calculation**:
```python
total_cost = quantity * unit_price  # Вычисляется автоматически
```

**cURL Example**:
```bash
curl -X POST "http://localhost:8003/api/v1/requests/251006-001/materials" \
  -H "Authorization: Bearer <service_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "material_name": "Труба ПВХ 32мм",
    "quantity": 2.0,
    "unit": "метр",
    "unit_price": 25000.0,
    "added_by": 15
  }'
```

---

### GET `/api/v1/requests/{request_number}/materials`

**Получение списка материалов заявки**

Возвращает все материалы с расчетом общей стоимости.

**Path Parameters**:
- `request_number` (string, required): Номер заявки

**Query Parameters**:
- `status` (string, optional): Фильтр по статусу (requested, ordered, delivered, cancelled)

**Response** (200 OK):
```json
{
  "request_number": "251006-001",
  "total_materials": 3,
  "total_cost": 155000.0,
  "materials": [
    {
      "id": "material_uuid_1",
      "material_name": "Труба ПВХ 32мм",
      "quantity": 2.0,
      "unit": "метр",
      "unit_price": 25000.0,
      "total_cost": 50000.0,
      "status": "delivered",
      "supplier": "СтройМаркет",
      "ordered_at": "2025-10-06T14:30:00Z",
      "delivered_at": "2025-10-06T16:00:00Z"
    },
    {
      "id": "material_uuid_2",
      "material_name": "Прокладки резиновые",
      "quantity": 5.0,
      "unit": "штука",
      "unit_price": 5000.0,
      "total_cost": 25000.0,
      "status": "delivered",
      "delivered_at": "2025-10-06T16:00:00Z"
    },
    {
      "id": "material_uuid_3",
      "material_name": "Сифон для раковины",
      "quantity": 1.0,
      "unit": "штука",
      "unit_price": 80000.0,
      "total_cost": 80000.0,
      "status": "ordered",
      "ordered_at": "2025-10-06T15:00:00Z",
      "estimated_delivery": "2025-10-07T10:00:00Z"
    }
  ],
  "cost_breakdown": {
    "requested": 80000.0,
    "ordered": 80000.0,
    "delivered": 75000.0,
    "total": 155000.0
  }
}
```

**cURL Example**:
```bash
curl -X GET "http://localhost:8003/api/v1/requests/251006-001/materials" \
  -H "Authorization: Bearer <service_token>"
```

---

### GET `/api/v1/requests/{request_number}/materials/cost-summary`

**Получение сводки по стоимости материалов**

Возвращает детальную разбивку стоимости материалов по категориям и статусам.

**Path Parameters**:
- `request_number` (string, required): Номер заявки

**Response** (200 OK):
```json
{
  "request_number": "251006-001",
  "total_cost": 155000.0,
  "breakdown_by_status": {
    "requested": 80000.0,
    "ordered": 80000.0,
    "delivered": 75000.0,
    "cancelled": 0.0
  },
  "breakdown_by_category": {
    "сантехника": 155000.0
  },
  "breakdown_by_supplier": {
    "СтройМаркет": 155000.0
  },
  "statistics": {
    "total_items": 3,
    "avg_item_cost": 51666.67,
    "most_expensive_item": {
      "name": "Сифон для раковины",
      "cost": 80000.0
    }
  },
  "payment_status": {
    "total_to_pay": 155000.0,
    "paid": 0.0,
    "pending": 155000.0
  }
}
```

**cURL Example**:
```bash
curl -X GET "http://localhost:8003/api/v1/requests/251006-001/materials/cost-summary" \
  -H "Authorization: Bearer <service_token>"
```

---

### PUT `/api/v1/requests/{request_number}/materials/{material_id}`

**Обновление материала**

Обновляет информацию о материале (количество, цену, статус).

**Path Parameters**:
- `request_number` (string, required): Номер заявки
- `material_id` (string, required): UUID материала

**Request Body** (все поля optional):
```json
{
  "quantity": 3.0,
  "unit_price": 23000.0,
  "status": "ordered",
  "supplier": "ТехноСнаб",
  "ordered_at": "2025-10-06T15:00:00Z",
  "estimated_delivery": "2025-10-07T10:00:00Z"
}
```

**Response** (200 OK):
```json
{
  "id": "material_uuid_1",
  "material_name": "Труба ПВХ 32мм",
  "quantity": 3.0,
  "unit_price": 23000.0,
  "total_cost": 69000.0,
  "status": "ordered",
  "supplier": "ТехноСнаб",
  "ordered_at": "2025-10-06T15:00:00Z",
  "estimated_delivery": "2025-10-07T10:00:00Z",
  "updated_at": "2025-10-06T15:30:00Z"
}
```

**cURL Example**:
```bash
curl -X PUT "http://localhost:8003/api/v1/requests/251006-001/materials/material_uuid_1" \
  -H "Authorization: Bearer <service_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "quantity": 3.0,
    "status": "ordered"
  }'
```

**Total Cost Auto-Recalculation**:
- При изменении `quantity` или `unit_price` → `total_cost` пересчитывается автоматически
- Обновляется общая стоимость заявки (`materials_cost`)

---

### PATCH `/api/v1/requests/{request_number}/materials/{material_id}/status`

**Обновление статуса материала**

Изменяет статус материала в workflow: requested → ordered → delivered → cancelled

**Path Parameters**:
- `request_number` (string, required): Номер заявки
- `material_id` (string, required): UUID материала

**Request Body**:
```json
{
  "new_status": "delivered",
  "delivered_at": "2025-10-07T10:00:00Z",
  "delivery_notes": "Доставлено в полном объеме",
  "updated_by": 15
}
```

**Response** (200 OK):
```json
{
  "id": "material_uuid_1",
  "old_status": "ordered",
  "new_status": "delivered",
  "delivered_at": "2025-10-07T10:00:00Z",
  "delivery_notes": "Доставлено в полном объеме",
  "updated_at": "2025-10-07T10:00:00Z"
}
```

**Material Status Workflow**:
```
requested → ordered → delivered
    ↓          ↓         
cancelled  cancelled
```

**cURL Example**:
```bash
curl -X PATCH "http://localhost:8003/api/v1/requests/251006-001/materials/material_uuid_1/status" \
  -H "Authorization: Bearer <service_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "new_status": "delivered",
    "delivered_at": "2025-10-07T10:00:00Z"
  }'
```

---

### POST `/api/v1/requests/{request_number}/materials/bulk`

**Массовое добавление материалов**

Добавляет несколько материалов за один запрос (полезно для больших списков).

**Path Parameters**:
- `request_number` (string, required): Номер заявки

**Request Body**:
```json
{
  "materials": [
    {
      "material_name": "Труба ПВХ 32мм",
      "quantity": 2.0,
      "unit": "метр",
      "unit_price": 25000.0
    },
    {
      "material_name": "Прокладки резиновые",
      "quantity": 5.0,
      "unit": "штука",
      "unit_price": 5000.0
    },
    {
      "material_name": "Сифон для раковины",
      "quantity": 1.0,
      "unit": "штука",
      "unit_price": 80000.0
    }
  ],
  "added_by": 15
}
```

**Response** (201 Created):
```json
{
  "success": true,
  "request_number": "251006-001",
  "total_added": 3,
  "materials": [
    {
      "id": "material_uuid_1",
      "material_name": "Труба ПВХ 32мм",
      "total_cost": 50000.0
    },
    {
      "id": "material_uuid_2",
      "material_name": "Прокладки резиновые",
      "total_cost": 25000.0
    },
    {
      "id": "material_uuid_3",
      "material_name": "Сифон для раковины",
      "total_cost": 80000.0
    }
  ],
  "total_cost": 155000.0
}
```

**cURL Example**:
```bash
curl -X POST "http://localhost:8003/api/v1/requests/251006-001/materials/bulk" \
  -H "Authorization: Bearer <service_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "materials": [
      {"material_name": "Труба ПВХ 32мм", "quantity": 2, "unit": "метр", "unit_price": 25000},
      {"material_name": "Прокладки", "quantity": 5, "unit": "штука", "unit_price": 5000}
    ],
    "added_by": 15
  }'
```

**Transaction Safety**:
- Все материалы добавляются в одной транзакции
- Если ошибка в одном материале → rollback всех
- `materials_cost` заявки обновляется атомарно

---

### GET `/api/v1/materials/by-category`

**Группировка материалов по категориям**

Возвращает статистику использования материалов по категориям за указанный период.

**Query Parameters**:
- `date_from` (datetime, optional): Начальная дата
- `date_to` (datetime, optional): Конечная дата
- `min_usage_count` (integer, optional): Минимальное количество использований (default: 1)

**Response** (200 OK):
```json
{
  "period": {
    "from": "2025-09-01T00:00:00Z",
    "to": "2025-10-06T23:59:59Z",
    "days": 36
  },
  "categories": [
    {
      "category": "сантехника",
      "total_items": 127,
      "total_cost": 18500000.0,
      "avg_cost_per_request": 145669.29,
      "most_used_materials": [
        {
          "material_name": "Труба ПВХ 32мм",
          "usage_count": 45,
          "total_quantity": 87.5,
          "avg_price": 25000.0
        },
        {
          "material_name": "Прокладки резиновые",
          "usage_count": 67,
          "total_quantity": 234.0,
          "avg_price": 5000.0
        }
      ]
    },
    {
      "category": "электрика",
      "total_items": 89,
      "total_cost": 12300000.0,
      "avg_cost_per_request": 138202.25,
      "most_used_materials": [
        {
          "material_name": "Розетка двойная",
          "usage_count": 34,
          "total_quantity": 45.0,
          "avg_price": 15000.0
        }
      ]
    }
  ],
  "grand_total": 30800000.0
}
```

**cURL Example**:
```bash
curl -X GET "http://localhost:8003/api/v1/materials/by-category?date_from=2025-09-01T00:00:00Z" \
  -H "Authorization: Bearer <service_token>"
```

---

### DELETE `/api/v1/requests/{request_number}/materials/{material_id}`

**Удаление материала**

Удаляет материал из заявки (обычно если добавлен ошибочно).

**Path Parameters**:
- `request_number` (string, required): Номер заявки
- `material_id` (string, required): UUID материала

**Query Parameters**:
- `deleted_by` (integer, required): ID пользователя
- `reason` (string, optional): Причина удаления

**Response** (200 OK):
```json
{
  "id": "material_uuid_1",
  "material_name": "Труба ПВХ 32мм",
  "deleted": true,
  "deleted_at": "2025-10-06T17:00:00Z",
  "deleted_by": 15,
  "reason": "Добавлено ошибочно, нашли подходящую трубу на объекте",
  "refund_amount": 50000.0
}
```

**cURL Example**:
```bash
curl -X DELETE "http://localhost:8003/api/v1/requests/251006-001/materials/material_uuid_1?deleted_by=15&reason=Ошибочно%20добавлено" \
  -H "Authorization: Bearer <service_token>"
```

**Side Effects**:
- Обновляется `materials_cost` заявки (вычитается стоимость удаленного материала)
- Создается audit log entry
- Если статус материала был "ordered" → возможно нужна отмена заказа

---

## 📖 Material Status Workflow

### Lifecycle

```
┌──────────┐
│requested │ (материал запрошен)
└──────────┘
     │
     │ order
     ▼
┌─────────┐
│ ordered │ (заказан у поставщика)
└─────────┘
     │
     │ deliver
     ▼
┌──────────┐
│delivered │ (доставлен на объект)
└──────────┘

Альтернативный путь:
requested ──cancel──> cancelled
ordered   ──cancel──> cancelled
```

### Status Descriptions

**requested**:
- Материал добавлен в список
- Ожидает заказа
- Можно редактировать количество и цену

**ordered**:
- Заказ размещен у поставщика
- Ожидается доставка
- Можно отменить с согласованием

**delivered**:
- Материал доставлен
- Готов к использованию
- Terminal state (успешный)

**cancelled**:
- Материал отменен
- Не будет использован
- Terminal state (отмененный)

---

## 🔍 Common Use Cases

### Use Case 1: Добавление комментария с фото

```bash
# Шаг 1: Загрузить фото в Media Service
curl -X POST "http://localhost:8004/api/v1/media/upload" \
  -H "Authorization: Bearer <token>" \
  -F "file=@photo.jpg" \
  -F "category=request_photo"
# Response: {"file_id": "media_123"}

# Шаг 2: Добавить комментарий со ссылкой на фото
curl -X POST "http://localhost:8003/api/v1/requests/251006-001/comments" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "comment_text": "Фото проблемы прилагаю",
    "author_user_id": 42,
    "media_file_ids": ["media_123"]
  }'
```

---

### Use Case 2: Tracking материалов от запроса до доставки

```bash
# Шаг 1: Добавить материал
curl -X POST ".../materials" -d '{"material_name": "Труба", ...}'
# Response: {"id": "mat_1", "status": "requested"}

# Шаг 2: Заказать материал
curl -X PATCH ".../materials/mat_1/status" -d '{"new_status": "ordered"}'

# Шаг 3: Отметить доставку
curl -X PATCH ".../materials/mat_1/status" -d '{
  "new_status": "delivered",
  "delivered_at": "2025-10-07T10:00:00Z"
}'

# Шаг 4: Проверить total cost
curl -X GET ".../materials/cost-summary"
```

---

### Use Case 3: Внутренний комментарий менеджера

```bash
# Создать internal comment (видят только менеджеры)
curl -X POST "http://localhost:8003/api/v1/requests/251006-001/comments" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "comment_text": "VIP клиент - приоритетное обслуживание",
    "author_user_id": 1,
    "is_internal": true
  }'
```

---

## 📖 See Also

- [API_REFERENCE_CORE.md](API_REFERENCE_CORE.md) - Core Requests API
- [API_REFERENCE_INTEGRATION.md](API_REFERENCE_INTEGRATION.md) - Bot, Search, Export API
- [REQUEST_SERVICE_DOCUMENTATION.md](REQUEST_SERVICE_DOCUMENTATION.md) - Полная документация


