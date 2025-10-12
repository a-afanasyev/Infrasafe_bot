# 📋 API Контракты - Communication Hub

**Версия**: 1.0.0
**Дата**: 09.10.2025
**Статус**: Детальная спецификация

---

## 📌 Общие соглашения

### WebSocket подключение

```javascript
// Подключение
ws://api.example.com/ws/v1/notifications?token=JWT_TOKEN

// Формат сообщений
{
  "type": "notification",
  "event": "request.status_changed",
  "data": {...},
  "timestamp": "2025-10-09T12:00:00Z"
}
```

### Priority Queues

| Очередь | Приоритет | SLA | Retry Policy |
|---------|-----------|-----|--------------|
| urgent | P0 | 1 min | 3 attempts, 10s interval |
| regular | P1 | 5 min | 5 attempts, exp backoff |
| batch | P2 | 1 hour | 10 attempts, exp backoff |

---

## 📧 Модуль отправки уведомлений

### POST /api/v1/notifications/send

**Описание**: Отправка уведомления через выбранные каналы

#### Request Body

```json
{
  "recipient_id": "550e8400-e29b-41d4-a716-446655440000",
  "template": "request_status_changed",
  "priority": "regular",
  "channels": ["telegram", "email", "push"],
  "data": {
    "request_number": "251009-001",
    "old_status": "new",
    "new_status": "in_progress",
    "executor_name": "Петр Петров",
    "estimated_time": "2025-10-09T14:00:00Z"
  },
  "options": {
    "schedule_at": null,
    "expire_at": "2025-10-10T12:00:00Z",
    "deduplication_key": "req_251009-001_status_in_progress",
    "batch_group": null,
    "locale": "ru"
  },
  "fallback": {
    "channels": ["sms"],
    "after_minutes": 30
  }
}
```

#### Валидация

| Поле | Тип | Обязательное | Валидация |
|------|-----|--------------|-----------|
| recipient_id | uuid | ✅ | Valid user ID |
| template | string | ✅ | Valid template name |
| priority | string | ❌ | Enum: urgent, regular, batch |
| channels | array | ✅ | Min 1, valid channels |
| data | object | ✅ | Template-specific data |
| options.schedule_at | datetime | ❌ | Future time, max 30 days |
| options.expire_at | datetime | ❌ | After schedule_at |
| options.deduplication_key | string | ❌ | Max 255 chars |
| options.batch_group | string | ❌ | For batch processing |
| options.locale | string | ❌ | Enum: ru, uz, en |
| fallback.channels | array | ❌ | Backup channels |
| fallback.after_minutes | integer | ❌ | 1-1440 (24 hours) |

#### Success Response (202 Accepted)

```json
{
  "success": true,
  "data": {
    "notification_id": "ntf_2YqQwFkLPtN6QzK5x8Fb",
    "status": "queued",
    "channels_queued": [
      {
        "channel": "telegram",
        "status": "queued",
        "queue": "regular",
        "estimated_delivery": "2025-10-09T12:05:00Z"
      },
      {
        "channel": "email",
        "status": "queued",
        "queue": "regular",
        "estimated_delivery": "2025-10-09T12:05:00Z"
      },
      {
        "channel": "push",
        "status": "queued",
        "queue": "regular",
        "estimated_delivery": "2025-10-09T12:02:00Z"
      }
    ],
    "deduplication_key": "req_251009-001_status_in_progress",
    "created_at": "2025-10-09T12:00:00Z"
  }
}
```

#### Error Responses

| Код | HTTP Status | Описание |
|-----|-------------|----------|
| NOTIF_001 | 404 | Recipient not found |
| NOTIF_002 | 400 | Invalid template |
| NOTIF_003 | 400 | Missing template data |
| NOTIF_004 | 409 | Duplicate notification (deduplication) |
| NOTIF_005 | 429 | Rate limit exceeded |

---

### POST /api/v1/notifications/broadcast

**Описание**: Массовая рассылка уведомлений

#### Request Body

```json
{
  "audience": {
    "type": "filter",
    "filters": {
      "roles": ["applicant"],
      "buildings": ["123e4567-e89b-12d3-a456-426614174000"],
      "is_active": true,
      "has_telegram": true
    }
  },
  "template": "maintenance_announcement",
  "channels": ["telegram", "email"],
  "data": {
    "title": "Плановое отключение воды",
    "date": "2025-10-15",
    "time": "09:00-13:00",
    "affected_entrances": ["1", "2"],
    "contact_phone": "+998711234567"
  },
  "options": {
    "batch_size": 100,
    "delay_between_batches_seconds": 10,
    "priority": "batch",
    "schedule_at": "2025-10-14T18:00:00Z"
  }
}
```

#### Валидация

| Поле | Тип | Обязательное | Валидация |
|------|-----|--------------|-----------|
| audience.type | string | ✅ | Enum: all, filter, list |
| audience.filters | object | Conditional | Required if type=filter |
| audience.user_ids | array | Conditional | Required if type=list, max 1000 |
| template | string | ✅ | Broadcast-enabled template |
| channels | array | ✅ | Min 1 channel |
| data | object | ✅ | Template data |
| options.batch_size | integer | ❌ | 1-500, default 100 |
| options.delay_between_batches_seconds | integer | ❌ | 0-300, default 10 |

#### Success Response (202 Accepted)

```json
{
  "success": true,
  "data": {
    "broadcast_id": "brd_3ZrRxGmMQtO7RnL6y9Gc",
    "status": "processing",
    "estimated_recipients": 450,
    "batches": 5,
    "scheduled_at": "2025-10-14T18:00:00Z",
    "estimated_completion": "2025-10-14T18:10:00Z",
    "tracking_url": "/api/v1/broadcasts/brd_3ZrRxGmMQtO7RnL6y9Gc"
  }
}
```

---

## 🤖 Telegram Bot API

### POST /api/v1/telegram/send_message

**Описание**: Отправка сообщения через Telegram Bot

#### Request Body

```json
{
  "chat_id": 123456789,
  "text": "Ваша заявка #251009-001 принята в работу",
  "parse_mode": "HTML",
  "reply_markup": {
    "inline_keyboard": [
      [
        {
          "text": "Посмотреть статус",
          "callback_data": "request:status:251009-001"
        },
        {
          "text": "Связаться с исполнителем",
          "callback_data": "request:contact:251009-001"
        }
      ]
    ]
  },
  "options": {
    "disable_notification": false,
    "protect_content": false,
    "reply_to_message_id": null
  }
}
```

#### Валидация

| Поле | Тип | Обязательное | Валидация |
|------|-----|--------------|-----------|
| chat_id | integer/string | ✅ | Valid Telegram chat ID |
| text | string | ✅ | 1-4096 chars |
| parse_mode | string | ❌ | Enum: HTML, Markdown, MarkdownV2 |
| reply_markup | object | ❌ | Valid Telegram keyboard |
| options | object | ❌ | Telegram options |

#### Success Response (200 OK)

```json
{
  "success": true,
  "data": {
    "message_id": 12345,
    "chat_id": 123456789,
    "date": 1696852200,
    "text": "Ваша заявка #251009-001 принята в работу",
    "delivered": true
  }
}
```

---

### POST /api/v1/telegram/send_media

**Описание**: Отправка медиафайлов через Telegram

#### Request Body

```json
{
  "chat_id": 123456789,
  "type": "photo",
  "media": [
    {
      "url": "https://storage.example.com/media/750e8400.jpg",
      "caption": "Фото выполненных работ",
      "parse_mode": "HTML"
    },
    {
      "url": "https://storage.example.com/media/850e8400.jpg",
      "caption": "Результат ремонта"
    }
  ],
  "reply_markup": {
    "inline_keyboard": [
      [
        {
          "text": "✅ Принять работу",
          "callback_data": "request:accept:251009-001"
        }
      ]
    ]
  }
}
```

#### Success Response (200 OK)

```json
{
  "success": true,
  "data": {
    "messages": [
      {
        "message_id": 12346,
        "type": "photo",
        "file_id": "AgACAgIAAxkBAAI..."
      },
      {
        "message_id": 12347,
        "type": "photo",
        "file_id": "AgACAgIAAxkBAAJ..."
      }
    ],
    "chat_id": 123456789,
    "delivered": true
  }
}
```

---

### POST /api/v1/telegram/webhooks/process

**Описание**: Обработка webhook от Telegram

#### Request Body (от Telegram)

```json
{
  "update_id": 10000,
  "message": {
    "message_id": 1365,
    "from": {
      "id": 123456789,
      "is_bot": false,
      "first_name": "Иван",
      "username": "ivan_user",
      "language_code": "ru"
    },
    "chat": {
      "id": 123456789,
      "first_name": "Иван",
      "username": "ivan_user",
      "type": "private"
    },
    "date": 1696852200,
    "text": "/start"
  }
}
```

#### Success Response (200 OK)

```json
{
  "success": true,
  "data": {
    "update_id": 10000,
    "processed": true,
    "action": "command_start",
    "user_registered": true,
    "response_sent": true
  }
}
```

---

## 📧 Email Service

### POST /api/v1/email/send

**Описание**: Отправка email

#### Request Body

```json
{
  "to": ["user@example.com"],
  "cc": [],
  "bcc": [],
  "subject": "Заявка #251009-001 выполнена",
  "template": "request_completed",
  "data": {
    "user_name": "Иван",
    "request_number": "251009-001",
    "completion_date": "09.10.2025",
    "executor_name": "Петр Петров",
    "rating_link": "https://example.com/rate/251009-001"
  },
  "attachments": [
    {
      "filename": "invoice.pdf",
      "content_type": "application/pdf",
      "content": "base64_encoded_content"
    }
  ],
  "options": {
    "priority": "normal",
    "track_opens": true,
    "track_clicks": true
  }
}
```

#### Валидация

| Поле | Тип | Обязательное | Валидация |
|------|-----|--------------|-----------|
| to | array | ✅ | Min 1, valid emails, max 50 |
| cc | array | ❌ | Valid emails, max 10 |
| bcc | array | ❌ | Valid emails, max 10 |
| subject | string | ✅ | 1-200 chars |
| template | string | ✅ | Valid email template |
| data | object | ✅ | Template variables |
| attachments | array | ❌ | Max 5, total size < 10MB |
| options.priority | string | ❌ | Enum: low, normal, high |

#### Success Response (202 Accepted)

```json
{
  "success": true,
  "data": {
    "email_id": "eml_4AtSyHnNRuP8SoM7z0Hd",
    "status": "queued",
    "recipients": {
      "to": ["user@example.com"],
      "cc": [],
      "bcc": []
    },
    "scheduled_send": "2025-10-09T12:01:00Z",
    "provider": "sendgrid",
    "tracking": {
      "opens": true,
      "clicks": true
    }
  }
}
```

---

## 📱 Push Notifications [FUTURE - Phase 2+]

**⚠️ Статус**: НЕ реализовано в MVP (решение Q5.1 от 10.10.2025)

**Решение**: Push notifications не включены в MVP из-за отсутствия мобильного приложения.

**Планируется**: Phase 2+ при разработке мобильного приложения

### ~~POST /api/v1/push/send~~ [ОТЛОЖЕНО]

<details>
<summary>Спецификация для будущей реализации (свернуто)</summary>

**Описание**: Отправка push-уведомления (будущее)

#### Request Body

```json
{
  "tokens": ["ExponentPushToken[xxx]"],
  "title": "Новая заявка",
  "body": "Поступила новая заявка",
  "data": {
    "type": "new_request",
    "request_number": "251009-002"
  }
}
```

</details>

---

## 💬 SMS Service [FUTURE - Phase 2+]

**⚠️ Статус**: НЕ реализовано в MVP (решение Q5.1 от 10.10.2025)

**Решение**: SMS убран из плана MVP. Возможная реализация в Phase 2+ при необходимости.

**Причина**: Фокус на Telegram для всех пользователей + Email только для менеджеров/админов

### ~~POST /api/v1/sms/send~~ [ОТЛОЖЕНО]

<details>
<summary>Спецификация для будущей реализации (свернуто)</summary>

**Описание**: Отправка SMS (будущее)

#### Request Body

```json
{
  "phone": "+998901234567",
  "text": "Ваша заявка #251009-001 выполнена.",
  "sender": "UK_CENTRAL",
  "options": {
    "priority": "normal"
  }
}
```

</details>

---

## 🔔 WebSocket Events

### Connection

```javascript
const ws = new WebSocket('wss://api.example.com/ws/v1/notifications?token=JWT_TOKEN');

ws.onopen = (event) => {
  console.log('Connected');

  // Subscribe to events
  ws.send(JSON.stringify({
    action: 'subscribe',
    events: ['request.*', 'shift.*'],
    filters: {
      user_id: '550e8400-e29b-41d4-a716-446655440000'
    }
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  handleNotification(data);
};
```

### Event Types

#### Request Status Changed

```json
{
  "type": "event",
  "event": "request.status_changed",
  "data": {
    "request_number": "251009-001",
    "old_status": "new",
    "new_status": "assigned",
    "executor": {
      "id": "650e8400-e29b-41d4-a716-446655440000",
      "name": "Петр Петров",
      "phone": "+998901234567"
    },
    "estimated_arrival": "2025-10-09T13:00:00Z"
  },
  "timestamp": "2025-10-09T12:00:00Z",
  "id": "evt_7DwVbKqQUxS1VrP0c3Kg"
}
```

#### New Message

```json
{
  "type": "event",
  "event": "message.new",
  "data": {
    "message_id": "msg_8ExWcLrRVyT2WsQ1d4Lh",
    "request_number": "251009-001",
    "from": {
      "id": "650e8400-e29b-41d4-a716-446655440000",
      "name": "Петр Петров",
      "role": "executor"
    },
    "text": "Приеду через 30 минут",
    "attachments": []
  },
  "timestamp": "2025-10-09T12:30:00Z",
  "id": "evt_9FyXdMsSWzU3XtR2e5Mi"
}
```

#### Heartbeat

```json
{
  "type": "ping",
  "timestamp": "2025-10-09T12:00:00Z"
}
```

Client should respond:
```json
{
  "type": "pong",
  "timestamp": "2025-10-09T12:00:00Z"
}
```

---

## 📊 Notification Templates

### Template Structure

```json
{
  "template_id": "request_status_changed",
  "name": "Изменение статуса заявки",
  "channels": {
    "telegram": {
      "text": "📋 Заявка #{{request_number}}\n\nСтатус изменен: {{old_status}} → {{new_status}}\n\n👷 Исполнитель: {{executor_name}}\n📱 Телефон: {{executor_phone}}\n\n⏰ Прибудет: {{estimated_arrival}}",
      "parse_mode": "HTML",
      "buttons": [
        {
          "text": "Подробнее",
          "callback_data": "request:details:{{request_number}}"
        }
      ]
    },
    "email": {
      "subject": "Заявка #{{request_number}} - изменение статуса",
      "html_template": "request_status_changed.html",
      "text_template": "request_status_changed.txt"
    },
    "push": {
      "title": "Заявка #{{request_number}}",
      "body": "Статус изменен на {{new_status}}",
      "sound": "default"
    },
    "sms": {
      "text": "Заявка #{{request_number}} {{new_status}}. Исполнитель: {{executor_name}} {{executor_phone}}"
    }
  },
  "variables": [
    {
      "name": "request_number",
      "type": "string",
      "required": true
    },
    {
      "name": "old_status",
      "type": "string",
      "required": true
    },
    {
      "name": "new_status",
      "type": "string",
      "required": true
    },
    {
      "name": "executor_name",
      "type": "string",
      "required": false
    },
    {
      "name": "executor_phone",
      "type": "string",
      "required": false
    },
    {
      "name": "estimated_arrival",
      "type": "datetime",
      "required": false
    }
  ]
}
```

### Available Templates

**⚠️ ВАЖНО**: Финальный набор каналов и приоритетов требует утверждения бизнесом (см. вопрос Q5.1 в OPEN_QUESTIONS_REGISTRY.md).
Каналы и частота отправки будут настроены после решения открытых вопросов.

| Template ID | Description | Channels* | Priority | Configurable |
|-------------|-------------|-----------|----------|--------------|
| request_created | Новая заявка создана | TBD | Regular | ✅ |
| request_assigned | Заявка назначена | TBD | Regular | ✅ |
| request_status_changed | Изменение статуса | TBD | Regular | ✅ |
| request_completed | Заявка выполнена | TBD | Regular | ✅ |
| request_cancelled | Заявка отменена | TBD | Regular | ✅ |
| request_urgent | Срочная заявка | TBD | Urgent | ✅ |
| shift_reminder | Напоминание о смене | TBD | Regular | ✅ |
| shift_started | Смена началась | TBD | Regular | ✅ |
| maintenance_announcement | Объявление о работах | TBD | Batch | ✅ |
| payment_reminder | Напоминание об оплате | TBD | Regular | ✅ |
| verification_code | Код подтверждения | SMS, Email | Urgent | ❌ |

*Каналы будут определены на основе:
- Пользовательских предпочтений
- Типа события
- Времени суток
- Бизнес-правил (Q5.1)

---

## 📈 Notification Analytics

### GET /api/v1/notifications/stats

**Описание**: Статистика по уведомлениям

#### Query Parameters

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| date_from | date | ❌ | Начало периода |
| date_to | date | ❌ | Конец периода |
| channel | string | ❌ | Фильтр по каналу |
| template | string | ❌ | Фильтр по шаблону |
| user_id | uuid | ❌ | Фильтр по пользователю |

#### Success Response (200 OK)

```json
{
  "success": true,
  "data": {
    "period": {
      "from": "2025-10-01T00:00:00Z",
      "to": "2025-10-09T23:59:59Z"
    },
    "summary": {
      "total_sent": 15420,
      "total_delivered": 15350,
      "total_failed": 70,
      "delivery_rate": 99.55
    },
    "by_channel": {
      "telegram": {
        "sent": 8500,
        "delivered": 8490,
        "failed": 10,
        "delivery_rate": 99.88,
        "avg_delivery_time_seconds": 2
      },
      "email": {
        "sent": 4200,
        "delivered": 4180,
        "failed": 20,
        "delivery_rate": 99.52,
        "opened": 3200,
        "clicked": 1500,
        "open_rate": 76.19,
        "click_rate": 35.71
      },
      "push": {
        "sent": 2500,
        "delivered": 2460,
        "failed": 40,
        "delivery_rate": 98.40,
        "clicked": 1800,
        "click_rate": 72.00
      },
      "sms": {
        "sent": 220,
        "delivered": 220,
        "failed": 0,
        "delivery_rate": 100.00,
        "cost_total": 4.40
      }
    },
    "by_template": {
      "request_status_changed": {
        "sent": 5200,
        "channels": {
          "telegram": 3500,
          "email": 1200,
          "push": 500
        }
      },
      "request_created": {
        "sent": 3100,
        "channels": {
          "telegram": 2000,
          "email": 800,
          "push": 300
        }
      }
    },
    "failures": {
      "by_reason": {
        "invalid_token": 25,
        "user_blocked": 15,
        "channel_unavailable": 10,
        "rate_limited": 10,
        "template_error": 5,
        "other": 5
      }
    }
  }
}
```

---

## 🔄 Queue Management

### GET /api/v1/queues/status

**Описание**: Статус очередей уведомлений

#### Success Response (200 OK)

```json
{
  "success": true,
  "data": {
    "queues": {
      "urgent": {
        "pending": 2,
        "processing": 1,
        "consumers": 5,
        "avg_wait_time_seconds": 0.5,
        "avg_processing_time_seconds": 0.2
      },
      "regular": {
        "pending": 45,
        "processing": 10,
        "consumers": 10,
        "avg_wait_time_seconds": 3,
        "avg_processing_time_seconds": 0.5
      },
      "batch": {
        "pending": 320,
        "processing": 50,
        "consumers": 5,
        "avg_wait_time_seconds": 120,
        "avg_processing_time_seconds": 2,
        "next_batch_at": "2025-10-09T13:00:00Z"
      }
    },
    "dead_letter_queue": {
      "count": 12,
      "oldest": "2025-10-09T10:00:00Z"
    },
    "system": {
      "uptime_seconds": 86400,
      "processed_last_hour": 1250,
      "failed_last_hour": 5,
      "success_rate": 99.60
    }
  }
}
```

---

## 🎯 Примеры интеграции

### Python - Отправка уведомления

```python
import asyncio
import aiohttp
from typing import Dict, Any, List

class CommunicationHubClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

    async def send_notification(
        self,
        recipient_id: str,
        template: str,
        data: Dict[str, Any],
        channels: List[str] = ['telegram'],
        priority: str = 'regular'
    ) -> Dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f'{self.base_url}/api/v1/notifications/send',
                json={
                    'recipient_id': recipient_id,
                    'template': template,
                    'channels': channels,
                    'data': data,
                    'priority': priority
                },
                headers=self.headers
            ) as response:
                return await response.json()

    async def broadcast(
        self,
        template: str,
        data: Dict[str, Any],
        filters: Dict[str, Any]
    ) -> Dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f'{self.base_url}/api/v1/notifications/broadcast',
                json={
                    'audience': {
                        'type': 'filter',
                        'filters': filters
                    },
                    'template': template,
                    'channels': ['telegram', 'email'],
                    'data': data,
                    'options': {
                        'priority': 'batch'
                    }
                },
                headers=self.headers
            ) as response:
                return await response.json()

# Использование
async def main():
    client = CommunicationHubClient(
        'https://api.example.com',
        'your_api_key'
    )

    # Отправка уведомления о статусе заявки
    result = await client.send_notification(
        recipient_id='550e8400-e29b-41d4-a716-446655440000',
        template='request_status_changed',
        data={
            'request_number': '251009-001',
            'old_status': 'new',
            'new_status': 'in_progress',
            'executor_name': 'Петр Петров',
            'executor_phone': '+998901234567'
        },
        channels=['telegram', 'email', 'push'],
        priority='regular'
    )

    print(f"Notification sent: {result['data']['notification_id']}")

    # Массовая рассылка
    broadcast_result = await client.broadcast(
        template='maintenance_announcement',
        data={
            'title': 'Плановое отключение воды',
            'date': '2025-10-15',
            'time': '09:00-13:00'
        },
        filters={
            'buildings': ['123e4567-e89b-12d3-a456-426614174000'],
            'roles': ['applicant']
        }
    )

    print(f"Broadcast sent to {broadcast_result['data']['estimated_recipients']} users")

asyncio.run(main())
```

### JavaScript - WebSocket подключение

```javascript
class NotificationWebSocket {
  constructor(url, token) {
    this.url = url;
    this.token = token;
    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 1000;
    this.heartbeatInterval = null;
  }

  connect() {
    this.ws = new WebSocket(`${this.url}?token=${this.token}`);

    this.ws.onopen = () => {
      console.log('WebSocket connected');
      this.reconnectAttempts = 0;

      // Subscribe to events
      this.subscribe(['request.*', 'shift.*']);

      // Start heartbeat
      this.startHeartbeat();
    };

    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'ping') {
        this.ws.send(JSON.stringify({
          type: 'pong',
          timestamp: new Date().toISOString()
        }));
      } else if (data.type === 'event') {
        this.handleEvent(data);
      }
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    this.ws.onclose = () => {
      console.log('WebSocket disconnected');
      this.stopHeartbeat();
      this.reconnect();
    };
  }

  subscribe(events) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        action: 'subscribe',
        events: events
      }));
    }
  }

  handleEvent(data) {
    console.log('Received event:', data.event, data.data);

    switch(data.event) {
      case 'request.status_changed':
        this.onRequestStatusChanged(data.data);
        break;
      case 'message.new':
        this.onNewMessage(data.data);
        break;
      // ... другие события
    }
  }

  onRequestStatusChanged(data) {
    // Обработка изменения статуса заявки
    console.log(`Request ${data.request_number} status changed: ${data.old_status} → ${data.new_status}`);
  }

  onNewMessage(data) {
    // Обработка нового сообщения
    console.log(`New message in request ${data.request_number}: ${data.text}`);
  }

  startHeartbeat() {
    this.heartbeatInterval = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({
          type: 'ping',
          timestamp: new Date().toISOString()
        }));
      }
    }, 30000);
  }

  stopHeartbeat() {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  reconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      console.log(`Reconnecting... Attempt ${this.reconnectAttempts}`);

      setTimeout(() => {
        this.connect();
      }, this.reconnectDelay * this.reconnectAttempts);
    } else {
      console.error('Max reconnection attempts reached');
    }
  }

  disconnect() {
    this.stopHeartbeat();
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}

// Использование
const notifications = new NotificationWebSocket(
  'wss://api.example.com/ws/v1/notifications',
  'your_jwt_token'
);

notifications.connect();
```

---

**Последнее обновление**: 09.10.2025
**Версия API**: 1.0.0
**Автор**: Architecture Team