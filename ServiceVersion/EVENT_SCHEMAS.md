# 📨 Event Schemas - RabbitMQ События

**Версия**: 1.0.0
**Дата**: 09.10.2025
**Статус**: Детальная спецификация

---

## 📌 Общая архитектура событий

### Message Broker Configuration

```yaml
# RabbitMQ Configuration
exchanges:
  - name: core.events
    type: topic
    durable: true
  - name: operations.events
    type: topic
    durable: true
  - name: notifications.events
    type: topic
    durable: true
  - name: analytics.events
    type: topic
    durable: true
  - name: integration.events
    type: topic
    durable: true

queues:
  # Core Service queues
  - name: core.request.commands
    durable: true
    bindings:
      - exchange: core.events
        routing_key: request.command.*

  # Operations Service queues
  - name: operations.shift.events
    durable: true
    bindings:
      - exchange: operations.events
        routing_key: shift.*
  - name: operations.assignment.events
    durable: true
    bindings:
      - exchange: operations.events
        routing_key: assignment.*

  # Notification Service queues
  - name: notifications.request.events
    durable: true
    bindings:
      - exchange: core.events
        routing_key: request.*
  - name: notifications.user.events
    durable: true
    bindings:
      - exchange: core.events
        routing_key: user.*
  - name: notifications.shift.events
    durable: true
    bindings:
      - exchange: operations.events
        routing_key: shift.*

  # Analytics Service queues
  - name: analytics.all.events
    durable: true
    bindings:
      - exchange: core.events
        routing_key: #
      - exchange: operations.events
        routing_key: #
      - exchange: integration.events
        routing_key: #
  - name: analytics.report.commands
    durable: true
    bindings:
      - exchange: analytics.events
        routing_key: report.generate

  # Integration Service queues
  - name: integration.payment.commands
    durable: true
    bindings:
      - exchange: integration.events
        routing_key: payment.*
  - name: integration.sync.commands
    durable: true
    bindings:
      - exchange: integration.events
        routing_key: sync.*

dead_letter:
  exchange: dlx.events
  queue: dlq.failed.events
  ttl: 86400000  # 24 hours
```

### Базовая структура события

```json
{
  "event_id": "evt_2YqQwFkLPtN6QzK5x8Fb",
  "event_type": "request.status.changed",
  "version": "1.0",
  "timestamp": "2025-10-09T12:00:00.123Z",
  "source": {
    "service": "core-service",
    "instance_id": "core-01",
    "version": "1.2.3"
  },
  "correlation_id": "req_251009-001",
  "causation_id": "evt_1XpPvEkKOsN5PmJ4w7Ea",
  "metadata": {
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "tenant_id": "tenant_001",
    "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
    "span_id": "00f067aa0ba902b7"
  },
  "data": {
    // Event-specific payload
  }
}
```

---

## 📋 Core Service События

### request.created

**Описание**: Новая заявка создана

**Exchange**: `core.events`
**Routing Key**: `request.created`

```json
{
  "event_id": "evt_2YqQwFkLPtN6QzK5x8Fb",
  "event_type": "request.created",
  "version": "1.0",
  "timestamp": "2025-10-09T12:00:00.123Z",
  "source": {
    "service": "core-service",
    "instance_id": "core-01",
    "version": "1.2.3"
  },
  "correlation_id": "req_251009-001",
  "metadata": {
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "tenant_id": "tenant_001"
  },
  "data": {
    "request_number": "251009-001",
    "title": "Протечка в ванной комнате",
    "description": "Течет труба под раковиной, нужен срочный ремонт",
    "category": {
      "id": 2,
      "name": "Сантехника",
      "sla_hours": 4
    },
    "priority": "high",
    "applicant": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "full_name": "Иван Иванов",
      "phone": "+998901234567",
      "email": "user@example.com"
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
    "preferred_date": "2025-10-10",
    "preferred_time": "10:00-12:00",
    "media_count": 2,
    "created_at": "2025-10-09T12:00:00Z",
    "sla_deadline": "2025-10-09T16:00:00Z"
  }
}
```

### request.status.changed

**Описание**: Изменение статуса заявки

**Exchange**: `core.events`
**Routing Key**: `request.status.changed`

```json
{
  "event_id": "evt_3ZrRxGmMQtO7RnL6y9Gc",
  "event_type": "request.status.changed",
  "version": "1.0",
  "timestamp": "2025-10-09T12:15:00.456Z",
  "source": {
    "service": "core-service",
    "instance_id": "core-01",
    "version": "1.2.3"
  },
  "correlation_id": "req_251009-001",
  "causation_id": "evt_2YqQwFkLPtN6QzK5x8Fb",
  "metadata": {
    "user_id": "650e8400-e29b-41d4-a716-446655440000",
    "tenant_id": "tenant_001"
  },
  "data": {
    "request_number": "251009-001",
    "old_status": "new",
    "new_status": "assigned",
    "reason": "Auto-assigned by dispatcher",
    "executor": {
      "id": "650e8400-e29b-41d4-a716-446655440000",
      "full_name": "Петр Петров",
      "phone": "+998901234567",
      "specialization": "Сантехника",
      "rating": 4.8
    },
    "assignment_metadata": {
      "algorithm": "basic",  // "basic" | "genetic" | "manual" - зависит от доступности AI/ML
      "algorithm_version": "1.0",
      "score": 0.92,  // Опционально, если алгоритм поддерживает scoring
      "factors": {
        "specialization_match": 1.0,
        "distance_km": 2.5,
        "current_load": 3,
        "rating": 4.8
      },
      "fallback_used": false  // true если AI/ML недоступен
    },
    "estimated_arrival": "2025-10-09T13:00:00Z",
    "changed_at": "2025-10-09T12:15:00Z"
  }
}
```

### request.assigned

**Описание**: Заявка назначена исполнителю

**Exchange**: `core.events`
**Routing Key**: `request.assigned`

```json
{
  "event_id": "evt_4AtSyHnNRuP8SoM7z0Hd",
  "event_type": "request.assigned",
  "version": "1.0",
  "timestamp": "2025-10-09T12:15:00.789Z",
  "source": {
    "service": "core-service",
    "instance_id": "core-01",
    "version": "1.2.3"
  },
  "correlation_id": "req_251009-001",
  "metadata": {
    "user_id": "system",
    "tenant_id": "tenant_001"
  },
  "data": {
    "request_number": "251009-001",
    "executor_id": "650e8400-e29b-41d4-a716-446655440000",
    "executor_name": "Петр Петров",
    "executor_phone": "+998901234567",
    "assignment_type": "automatic",
    "assignment_reason": "Best match by smart dispatcher",
    "previous_executor_id": null,
    "reassignment": false,
    "estimated_arrival": "2025-10-09T13:00:00Z",
    "estimated_completion": "2025-10-09T14:30:00Z",
    "assigned_at": "2025-10-09T12:15:00Z"
  }
}
```

### request.completed

**Описание**: Заявка выполнена

**Exchange**: `core.events`
**Routing Key**: `request.completed`

```json
{
  "event_id": "evt_5BuTzIoOSvQ9TpN8a1Ie",
  "event_type": "request.completed",
  "version": "1.0",
  "timestamp": "2025-10-09T14:30:00.123Z",
  "source": {
    "service": "core-service",
    "instance_id": "core-02",
    "version": "1.2.3"
  },
  "correlation_id": "req_251009-001",
  "metadata": {
    "user_id": "650e8400-e29b-41d4-a716-446655440000",
    "tenant_id": "tenant_001"
  },
  "data": {
    "request_number": "251009-001",
    "executor_id": "650e8400-e29b-41d4-a716-446655440000",
    "completion_note": "Заменена прокладка, течь устранена",
    "media_count": 3,
    "materials_used": [
      {
        "name": "Прокладка резиновая",
        "quantity": 1,
        "unit": "шт"
      }
    ],
    "metrics": {
      "time_to_assign_minutes": 15,
      "time_to_start_minutes": 60,
      "time_to_complete_minutes": 150,
      "sla_met": true,
      "sla_deadline": "2025-10-09T16:00:00Z"
    },
    "completed_at": "2025-10-09T14:30:00Z",
    "auto_close_at": "2025-10-12T14:30:00Z"
  }
}
```

### request.cancelled

**Описание**: Заявка отменена

**Exchange**: `core.events`
**Routing Key**: `request.cancelled`

```json
{
  "event_id": "evt_6CvUaJpPTwR0UqO9b2Jf",
  "event_type": "request.cancelled",
  "version": "1.0",
  "timestamp": "2025-10-09T11:00:00.456Z",
  "source": {
    "service": "core-service",
    "instance_id": "core-01",
    "version": "1.2.3"
  },
  "correlation_id": "req_251009-002",
  "metadata": {
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "tenant_id": "tenant_001"
  },
  "data": {
    "request_number": "251009-002",
    "cancelled_by": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Иван Иванов",
      "role": "applicant"
    },
    "reason": "Проблема решена самостоятельно",
    "status_before_cancellation": "new",
    "was_assigned": false,
    "executor_id": null,
    "cancelled_at": "2025-10-09T11:00:00Z"
  }
}
```

### request.rated

**Описание**: Заявка оценена пользователем

**Exchange**: `core.events`
**Routing Key**: `request.rated`

```json
{
  "event_id": "evt_7DwVbKqQUxS1VrP0c3Kg",
  "event_type": "request.rated",
  "version": "1.0",
  "timestamp": "2025-10-09T15:00:00.789Z",
  "source": {
    "service": "core-service",
    "instance_id": "core-01",
    "version": "1.2.3"
  },
  "correlation_id": "req_251009-001",
  "metadata": {
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "tenant_id": "tenant_001"
  },
  "data": {
    "request_number": "251009-001",
    "executor_id": "650e8400-e29b-41d4-a716-446655440000",
    "rating": 5,
    "comment": "Отличная работа, все быстро и аккуратно",
    "rated_by": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Иван Иванов"
    },
    "executor_stats": {
      "total_ratings": 145,
      "average_rating": 4.8,
      "rating_change": 0.01
    },
    "rated_at": "2025-10-09T15:00:00Z"
  }
}
```

---

## 👤 User Service События

### user.created

**Описание**: Новый пользователь зарегистрирован

**Exchange**: `core.events`
**Routing Key**: `user.created`

```json
{
  "event_id": "evt_8ExWcLrRVyT2WsQ1d4Lh",
  "event_type": "user.created",
  "version": "1.0",
  "timestamp": "2025-10-09T10:00:00.123Z",
  "source": {
    "service": "core-service",
    "instance_id": "core-01",
    "version": "1.2.3"
  },
  "metadata": {
    "user_id": "system",
    "tenant_id": "tenant_001"
  },
  "data": {
    "user_id": "750e8400-e29b-41d4-a716-446655440000",
    "email": "newuser@example.com",
    "full_name": "Сергей Сергеев",
    "phone": "+998901234568",
    "roles": ["applicant"],
    "registration_source": "telegram",
    "telegram_id": 987654321,
    "language": "ru",
    "timezone": "Asia/Tashkent",
    "verification_required": true,
    "verification_sent": true,
    "created_at": "2025-10-09T10:00:00Z"
  }
}
```

### user.verified

**Описание**: Email/телефон пользователя подтвержден

**Exchange**: `core.events`
**Routing Key**: `user.verified`

```json
{
  "event_id": "evt_9FyXdMsSWzU3XtR2e5Mi",
  "event_type": "user.verified",
  "version": "1.0",
  "timestamp": "2025-10-09T10:30:00.456Z",
  "source": {
    "service": "core-service",
    "instance_id": "core-01",
    "version": "1.2.3"
  },
  "metadata": {
    "user_id": "750e8400-e29b-41d4-a716-446655440000",
    "tenant_id": "tenant_001"
  },
  "data": {
    "user_id": "750e8400-e29b-41d4-a716-446655440000",
    "verification_type": "email",
    "verification_method": "code",
    "attempts": 1,
    "verified_at": "2025-10-09T10:30:00Z"
  }
}
```

### user.role.changed

**Описание**: Изменение роли пользователя

**Exchange**: `core.events`
**Routing Key**: `user.role.changed`

```json
{
  "event_id": "evt_0GzYeNtTXaV4YuS3f6Nj",
  "event_type": "user.role.changed",
  "version": "1.0",
  "timestamp": "2025-10-09T11:00:00.789Z",
  "source": {
    "service": "core-service",
    "instance_id": "core-01",
    "version": "1.2.3"
  },
  "metadata": {
    "user_id": "admin",
    "tenant_id": "tenant_001"
  },
  "data": {
    "user_id": "750e8400-e29b-41d4-a716-446655440000",
    "old_roles": ["applicant"],
    "new_roles": ["applicant", "executor"],
    "added_roles": ["executor"],
    "removed_roles": [],
    "reason": "Прошел обучение и верификацию",
    "changed_by": {
      "id": "admin",
      "name": "System Administrator"
    },
    "changed_at": "2025-10-09T11:00:00Z"
  }
}
```

---

## 🏢 Building Assets События

### building.created

**Описание**: Новое здание добавлено

**Exchange**: `core.events`
**Routing Key**: `building.created`

```json
{
  "event_id": "evt_1HaZfOuUYbW5ZvT4g7Ok",
  "event_type": "building.created",
  "version": "1.0",
  "timestamp": "2025-10-09T09:00:00.123Z",
  "source": {
    "service": "core-service",
    "instance_id": "core-01",
    "version": "1.2.3"
  },
  "metadata": {
    "user_id": "admin",
    "tenant_id": "tenant_001"
  },
  "data": {
    "building_id": "923e4567-e89b-12d3-a456-426614174000",
    "complex_id": "023e4567-e89b-12d3-a456-426614174000",
    "name": "Корпус 3",
    "address": {
      "full": "г. Ташкент, ул. Ленина, д. 3",
      "city": "Ташкент",
      "district": "Мирабадский район",
      "street": "ул. Ленина",
      "building_number": "3"
    },
    "coordinates": {
      "lat": 41.311181,
      "lng": 69.240662
    },
    "structure": {
      "floors": 20,
      "entrances": 4,
      "apartments": 320
    },
    "created_at": "2025-10-09T09:00:00Z"
  }
}
```

### apartment.resident.added

**Описание**: Добавлен жилец квартиры

**Exchange**: `core.events`
**Routing Key**: `apartment.resident.added`

```json
{
  "event_id": "evt_2IbAgPvVZcX6AwU5h8Pl",
  "event_type": "apartment.resident.added",
  "version": "1.0",
  "timestamp": "2025-10-09T10:15:00.456Z",
  "source": {
    "service": "core-service",
    "instance_id": "core-01",
    "version": "1.2.3"
  },
  "metadata": {
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "tenant_id": "tenant_001"
  },
  "data": {
    "apartment_id": "823e4567-e89b-12d3-a456-426614174000",
    "building_id": "123e4567-e89b-12d3-a456-426614174000",
    "apartment_number": "42",
    "resident": {
      "user_id": "550e8400-e29b-41d4-a716-446655440000",
      "full_name": "Иван Иванов",
      "is_owner": true,
      "move_in_date": "2025-10-09"
    },
    "total_residents": 3,
    "added_at": "2025-10-09T10:15:00Z"
  }
}
```

---

## 📅 Operations Service События

### shift.created

**Описание**: Создана новая смена

**Exchange**: `operations.events`
**Routing Key**: `shift.created`

```json
{
  "event_id": "evt_3JcBhQwWadY7BxV6i9Qm",
  "event_type": "shift.created",
  "version": "1.0",
  "timestamp": "2025-10-09T08:00:00.123Z",
  "source": {
    "service": "operations-service",
    "instance_id": "ops-01",
    "version": "1.1.0"
  },
  "metadata": {
    "user_id": "admin",
    "tenant_id": "tenant_001"
  },
  "data": {
    "shift_id": "shf_4KdCiRxXbeZ8CyW7j0Rn",
    "executor_id": "650e8400-e29b-41d4-a716-446655440000",
    "date": "2025-10-10",
    "start_time": "09:00:00",
    "end_time": "18:00:00",
    "specialization": "Сантехника",
    "buildings": [
      "123e4567-e89b-12d3-a456-426614174000",
      "223e4567-e89b-12d3-a456-426614174000"
    ],
    "max_requests": 15,
    "created_at": "2025-10-09T08:00:00Z"
  }
}
```

### shift.started

**Описание**: Смена началась

**Exchange**: `operations.events`
**Routing Key**: `shift.started`

```json
{
  "event_id": "evt_5LeDjSyYcfA9DzY8k1So",
  "event_type": "shift.started",
  "version": "1.0",
  "timestamp": "2025-10-10T09:00:00.456Z",
  "source": {
    "service": "operations-service",
    "instance_id": "ops-01",
    "version": "1.1.0"
  },
  "metadata": {
    "user_id": "650e8400-e29b-41d4-a716-446655440000",
    "tenant_id": "tenant_001"
  },
  "data": {
    "shift_id": "shf_4KdCiRxXbeZ8CyW7j0Rn",
    "executor_id": "650e8400-e29b-41d4-a716-446655440000",
    "actual_start_time": "2025-10-10T09:00:00Z",
    "location": {
      "lat": 41.311081,
      "lng": 69.240562
    },
    "assigned_requests": 3,
    "pending_requests": 2
  }
}
```

### shift.transfer.requested

**Описание**: Запрос на передачу смены

**Exchange**: `operations.events`
**Routing Key**: `shift.transfer.requested`

```json
{
  "event_id": "evt_6MfEkTzZdgB0EaZ9l2Tp",
  "event_type": "shift.transfer.requested",
  "version": "1.0",
  "timestamp": "2025-10-09T15:00:00.789Z",
  "source": {
    "service": "operations-service",
    "instance_id": "ops-01",
    "version": "1.1.0"
  },
  "metadata": {
    "user_id": "650e8400-e29b-41d4-a716-446655440000",
    "tenant_id": "tenant_001"
  },
  "data": {
    "transfer_id": "trf_7NgFlUaAehC1FbA0m3Uq",
    "shift_id": "shf_4KdCiRxXbeZ8CyW7j0Rn",
    "from_executor_id": "650e8400-e29b-41d4-a716-446655440000",
    "to_executor_id": "750e8400-e29b-41d4-a716-446655440000",
    "shift_date": "2025-10-15",
    "reason": "Больничный",
    "requires_approval": true,
    "approval_deadline": "2025-10-12T18:00:00Z",
    "requested_at": "2025-10-09T15:00:00Z"
  }
}
```

### assignment.optimized

**Описание**: Выполнена оптимизация назначений

**Exchange**: `operations.events`
**Routing Key**: `assignment.optimized`

```json
{
  "event_id": "evt_8OhGmVbBfiD2GcB1n4Vr",
  "event_type": "assignment.optimized",
  "version": "1.0",
  "timestamp": "2025-10-09T12:00:00.123Z",
  "source": {
    "service": "operations-service",
    "instance_id": "ops-01",
    "version": "1.1.0"
  },
  "metadata": {
    "user_id": "system",
    "tenant_id": "tenant_001"
  },
  "data": {
    "optimization_id": "opt_9PiHnWcCgjE3HdC2o5Ws",
    "algorithm": "round_robin",  // "round_robin" | "load_balanced" | "genetic" | "simulated_annealing"
    "algorithm_version": "1.0",
    "ml_service_available": false,  // Показывает доступность AI/ML сервиса
    "requests_optimized": 25,
    "executors_involved": 8,
    "metrics": {
      "avg_distance_before_km": 8.5,
      "avg_distance_after_km": 5.2,
      "distance_reduction_percent": 38.8,
      "load_balance_score": 0.92,
      "specialization_match_score": 0.95
    },
    "optimization_reason": "scheduled",  // "scheduled" | "manual" | "threshold_reached"
    "changes": [
      {
        "request_number": "251009-003",
        "old_executor_id": "650e8400-e29b-41d4-a716-446655440000",
        "new_executor_id": "750e8400-e29b-41d4-a716-446655440000",
        "reason": "Better route optimization"
      }
    ],
    "optimized_at": "2025-10-09T12:00:00Z"
  }
}
```

---

## 📊 Analytics События

### analytics.report.generated

**Описание**: Сгенерирован аналитический отчет

**Exchange**: `analytics.events`
**Routing Key**: `analytics.report.generated`

```json
{
  "event_id": "evt_0QjIoXdDhkF4IeD3p6Xt",
  "event_type": "analytics.report.generated",
  "version": "1.0",
  "timestamp": "2025-10-09T00:00:00.123Z",
  "source": {
    "service": "analytics-service",
    "instance_id": "analytics-01",
    "version": "1.0.0"
  },
  "metadata": {
    "user_id": "system",
    "tenant_id": "tenant_001"
  },
  "data": {
    "report_id": "rpt_1RkJpYeDilG5JfE4q7Yu",
    "report_type": "daily_summary",
    "period": {
      "from": "2025-10-08T00:00:00Z",
      "to": "2025-10-08T23:59:59Z"
    },
    "metrics": {
      "total_requests": 145,
      "completed_requests": 132,
      "cancelled_requests": 8,
      "pending_requests": 5,
      "avg_completion_time_hours": 3.2,
      "sla_compliance_percent": 94.5,
      "customer_satisfaction": 4.6
    },
    "available_formats": ["pdf", "excel", "json"],
    "download_url": "https://api.example.com/reports/rpt_1RkJpYeDilG5JfE4q7Yu",
    "expires_at": "2025-10-16T00:00:00Z"
  }
}
```

---

## 💰 Integration События

### payment.received

**Описание**: Получен платеж

**Exchange**: `integration.events`
**Routing Key**: `payment.received`

```json
{
  "event_id": "evt_2SlKqZfEjmH6KgF5r8Zv",
  "event_type": "payment.received",
  "version": "1.0",
  "timestamp": "2025-10-09T14:00:00.456Z",
  "source": {
    "service": "integration-service",
    "instance_id": "integration-01",
    "version": "1.0.0"
  },
  "metadata": {
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "tenant_id": "tenant_001"
  },
  "data": {
    "payment_id": "pay_3TmLrAgFknI7LhG6s9Aw",
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "amount": 150000,
    "currency": "UZS",
    "purpose": "Оплата за обслуживание октябрь 2025",
    "payment_method": "card",
    "provider": "payme",
    "provider_transaction_id": "64f7b3d0e4b0123456789abc",
    "status": "success",
    "metadata": {
      "building_id": "123e4567-e89b-12d3-a456-426614174000",
      "apartment": "42",
      "period": "2025-10"
    },
    "received_at": "2025-10-09T14:00:00Z"
  }
}
```

### external.sync.completed

**Описание**: Завершена синхронизация с внешней системой

**Exchange**: `integration.events`
**Routing Key**: `external.sync.completed`

```json
{
  "event_id": "evt_4UnMsBgGloJ8MiH7t0Bx",
  "event_type": "external.sync.completed",
  "version": "1.0",
  "timestamp": "2025-10-09T03:00:00.789Z",
  "source": {
    "service": "integration-service",
    "instance_id": "integration-01",
    "version": "1.0.0"
  },
  "metadata": {
    "user_id": "system",
    "tenant_id": "tenant_001"
  },
  "data": {
    "sync_id": "sync_5VoNtChHmpK9NjI8u1Cy",
    "external_system": "1c_accounting",
    "sync_type": "residents",
    "direction": "import",
    "records_processed": 450,
    "records_created": 12,
    "records_updated": 38,
    "records_failed": 2,
    "errors": [
      {
        "record_id": "ext_123",
        "error": "Invalid phone format"
      },
      {
        "record_id": "ext_456",
        "error": "Duplicate email"
      }
    ],
    "duration_seconds": 45,
    "next_sync_at": "2025-10-10T03:00:00Z"
  }
}
```

---

## 🔧 Обработка событий

### Python Consumer Example

```python
import json
import asyncio
from typing import Dict, Any, Callable
import aio_pika
from datetime import datetime

class EventConsumer:
    def __init__(self, amqp_url: str):
        self.amqp_url = amqp_url
        self.handlers: Dict[str, Callable] = {}

    def register_handler(self, event_type: str, handler: Callable):
        """Регистрация обработчика для типа события"""
        self.handlers[event_type] = handler

    async def connect(self):
        """Подключение к RabbitMQ"""
        self.connection = await aio_pika.connect_robust(self.amqp_url)
        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=10)

    async def consume(self, queue_name: str):
        """Начать потребление сообщений из очереди"""
        queue = await self.channel.declare_queue(
            queue_name,
            durable=True
        )

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    await self.process_message(message)

    async def process_message(self, message: aio_pika.IncomingMessage):
        """Обработка отдельного сообщения"""
        try:
            # Парсинг JSON
            event = json.loads(message.body.decode())

            # Валидация базовой структуры
            if not self._validate_event(event):
                print(f"Invalid event structure: {event}")
                return

            event_type = event['event_type']

            # Вызов соответствующего обработчика
            if event_type in self.handlers:
                await self.handlers[event_type](event)
            else:
                print(f"No handler for event type: {event_type}")

        except Exception as e:
            print(f"Error processing message: {e}")
            # Можно отправить в DLQ или залогировать

    def _validate_event(self, event: Dict[str, Any]) -> bool:
        """Валидация структуры события"""
        required_fields = [
            'event_id', 'event_type', 'version',
            'timestamp', 'source', 'data'
        ]
        return all(field in event for field in required_fields)

# Обработчики событий
async def handle_request_created(event: Dict[str, Any]):
    """Обработка создания заявки"""
    data = event['data']
    print(f"New request created: {data['request_number']}")

    # Отправить уведомления
    await send_notification(
        user_id=data['applicant']['id'],
        template='request_created',
        data=data
    )

    # Запустить автоназначение
    if data['priority'] == 'urgent':
        await trigger_auto_assignment(data['request_number'])

async def handle_request_completed(event: Dict[str, Any]):
    """Обработка завершения заявки"""
    data = event['data']
    print(f"Request completed: {data['request_number']}")

    # Обновить метрики исполнителя
    await update_executor_metrics(
        executor_id=data['executor_id'],
        completion_time=data['metrics']['time_to_complete_minutes']
    )

    # Отправить запрос на оценку
    await send_rating_request(
        user_id=data['applicant']['id'],
        request_number=data['request_number']
    )

async def handle_shift_transfer_requested(event: Dict[str, Any]):
    """Обработка запроса на передачу смены"""
    data = event['data']
    print(f"Shift transfer requested: {data['transfer_id']}")

    # Уведомить менеджера
    await notify_manager(
        transfer_id=data['transfer_id'],
        from_executor=data['from_executor_id'],
        to_executor=data['to_executor_id']
    )

    # Создать задачу на одобрение
    await create_approval_task(
        transfer_id=data['transfer_id'],
        deadline=data['approval_deadline']
    )

# Главная функция
async def main():
    # Создание консьюмера
    consumer = EventConsumer('amqp://guest:guest@localhost/')

    # Регистрация обработчиков
    consumer.register_handler('request.created', handle_request_created)
    consumer.register_handler('request.completed', handle_request_completed)
    consumer.register_handler('shift.transfer.requested', handle_shift_transfer_requested)

    # Подключение и начало потребления
    await consumer.connect()

    # Запуск нескольких консьюмеров для разных очередей
    await asyncio.gather(
        consumer.consume('notifications.request.events'),
        consumer.consume('operations.shift.events')
    )

if __name__ == '__main__':
    asyncio.run(main())
```

### TypeScript Producer Example

```typescript
import amqplib from 'amqplib';
import { v4 as uuidv4 } from 'uuid';

interface Event {
  event_id: string;
  event_type: string;
  version: string;
  timestamp: string;
  source: {
    service: string;
    instance_id: string;
    version: string;
  };
  correlation_id?: string;
  causation_id?: string;
  metadata: {
    user_id: string;
    tenant_id: string;
    trace_id?: string;
    span_id?: string;
  };
  data: any;
}

class EventProducer {
  private connection: amqplib.Connection | null = null;
  private channel: amqplib.Channel | null = null;
  private readonly serviceName: string;
  private readonly instanceId: string;
  private readonly serviceVersion: string;

  constructor(serviceName: string, instanceId: string, serviceVersion: string) {
    this.serviceName = serviceName;
    this.instanceId = instanceId;
    this.serviceVersion = serviceVersion;
  }

  async connect(amqpUrl: string): Promise<void> {
    this.connection = await amqplib.connect(amqpUrl);
    this.channel = await this.connection.createChannel();

    // Declare exchanges
    await this.channel.assertExchange('core.events', 'topic', { durable: true });
    await this.channel.assertExchange('operations.events', 'topic', { durable: true });
  }

  async publishEvent(
    exchange: string,
    routingKey: string,
    eventType: string,
    data: any,
    metadata: Partial<Event['metadata']>,
    correlationId?: string,
    causationId?: string
  ): Promise<void> {
    if (!this.channel) {
      throw new Error('Not connected to RabbitMQ');
    }

    const event: Event = {
      event_id: `evt_${uuidv4().replace(/-/g, '')}`,
      event_type: eventType,
      version: '1.0',
      timestamp: new Date().toISOString(),
      source: {
        service: this.serviceName,
        instance_id: this.instanceId,
        version: this.serviceVersion
      },
      correlation_id: correlationId,
      causation_id: causationId,
      metadata: {
        user_id: metadata.user_id || 'system',
        tenant_id: metadata.tenant_id || 'default',
        trace_id: metadata.trace_id,
        span_id: metadata.span_id
      },
      data
    };

    const message = Buffer.from(JSON.stringify(event));

    await this.channel.publish(
      exchange,
      routingKey,
      message,
      {
        persistent: true,
        contentType: 'application/json',
        timestamp: Date.now(),
        messageId: event.event_id
      }
    );

    console.log(`Event published: ${eventType} to ${exchange}/${routingKey}`);
  }

  async close(): Promise<void> {
    if (this.channel) await this.channel.close();
    if (this.connection) await this.connection.close();
  }
}

// Использование
async function createRequest(requestData: any, userId: string) {
  const producer = new EventProducer('core-service', 'core-01', '1.2.3');

  try {
    await producer.connect('amqp://localhost');

    // Публикация события создания заявки
    await producer.publishEvent(
      'core.events',
      'request.created',
      'request.created',
      {
        request_number: requestData.request_number,
        title: requestData.title,
        description: requestData.description,
        category: requestData.category,
        priority: requestData.priority,
        applicant: requestData.applicant,
        location: requestData.location,
        created_at: new Date().toISOString()
      },
      {
        user_id: userId,
        tenant_id: 'tenant_001'
      },
      requestData.request_number // correlation_id
    );

    // Если заявка срочная, публикуем дополнительное событие
    if (requestData.priority === 'urgent') {
      await producer.publishEvent(
        'core.events',
        'request.urgent',
        'request.urgent',
        requestData,
        {
          user_id: userId,
          tenant_id: 'tenant_001'
        },
        requestData.request_number
      );
    }

  } finally {
    await producer.close();
  }
}
```

---

## 📊 Мониторинг событий

### Метрики для Prometheus

```yaml
# Event metrics
event_published_total:
  type: counter
  labels: [service, event_type, exchange]
  help: Total number of events published

event_consumed_total:
  type: counter
  labels: [service, event_type, queue]
  help: Total number of events consumed

event_processing_duration_seconds:
  type: histogram
  labels: [service, event_type]
  help: Event processing duration

event_processing_errors_total:
  type: counter
  labels: [service, event_type, error_type]
  help: Total number of event processing errors

queue_depth:
  type: gauge
  labels: [queue_name]
  help: Current queue depth

dlq_messages_total:
  type: counter
  labels: [queue_name]
  help: Total messages in dead letter queue
```

---

**Последнее обновление**: 09.10.2025
**Версия**: 1.0.0
**Автор**: Architecture Team