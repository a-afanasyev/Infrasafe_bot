# 🗺️ Карта зависимостей между сервисами

**Версия**: 1.0
**Дата**: 8 октября 2025
**Статус**: Актуальна для архитектуры v1.1.0

---

## 1. Граф зависимостей

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND LAYER                          │
├──────────────┬──────────────────┬──────────────────────────────┤
│   WebApp     │  Telegram Bot    │        Admin Panel           │
└──────┬───────┴────────┬─────────┴──────────┬───────────────────┘
       │                │                     │
       ▼                ▼                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                          API GATEWAY                            │
└─────────────────────────────────────────────────────────────────┘
                               │
       ┌───────────────────────┼───────────────────────┐
       ▼                       ▼                       ▼
┌──────────────┐      ┌──────────────┐       ┌──────────────┐
│     Core     │◄────►│  Operations  │◄─────►│Communication │
│   Service    │      │   Service    │       │     Hub      │
└──────┬───────┘      └──────┬───────┘       └──────┬───────┘
       │                     │                       │
       │    ┌────────────────┼───────────────┐      │
       ▼    ▼                ▼               ▼      ▼
┌──────────────┐      ┌──────────────┐       ┌──────────────┐
│   Analytics  │      │ Integration  │       │Media Storage │
│   Service    │      │     Hub      │       │   Service    │
└──────────────┘      └──────┬───────┘       └──────────────┘
                             │
                      ┌──────▼───────┐
                      │   AI/ML      │
                      │Service [OPT] │
                      └──────────────┘

Легенда:
──► Критическая зависимость (сервис не работает без нее)
--► Опциональная зависимость (graceful degradation)
◄─► Двунаправленная зависимость
```

---

## 2. Матрица зависимостей

### 2.1 Исходящие зависимости (что использует каждый сервис)

| Сервис | Критические зависимости | Опциональные зависимости | Тип взаимодействия |
|--------|-------------------------|---------------------------|-------------------|
| **Core Service** | - | Analytics, Integration Hub | REST API, Events |
| **Operations Service** | Core Service | AI/ML Service, Integration Hub | REST API, Events |
| **Communication Hub** | Core Service | Media Storage | REST API, WebSocket |
| **Media Storage** | - | - | REST API |
| **Analytics Service** | Core Service | Все сервисы (для сбора метрик) | Events, REST API |
| **Integration Hub** | - | Core Service (для обновления данных) | REST API, Webhooks |
| **AI/ML Service** | Core Service, Operations Service | Analytics Service | REST API |
| **Telegram Bot** | Communication Hub, Core Service | Media Storage | REST API, WebSocket |

### 2.2 Входящие зависимости (кто использует каждый сервис)

| Сервис | Критически зависят | Опционально зависят | Предоставляемые API |
|--------|-------------------|---------------------|---------------------|
| **Core Service** | Operations, Communication Hub, AI/ML | Analytics, Bot | Auth, Users, Requests, Assets |
| **Operations Service** | - | Bot, Analytics | Shifts, Assignments |
| **Communication Hub** | Bot | Core Service (для уведомлений) | Notifications, WebSocket |
| **Media Storage** | - | Communication Hub, Bot | Upload, Processing, CDN |
| **Analytics Service** | - | Admin Panel | Reports, Metrics, Dashboards |
| **Integration Hub** | - | Core, Operations | External APIs, Geocoding |
| **AI/ML Service** | - | Operations | Optimization, Predictions |

---

## 3. Детальное описание зависимостей

### 3.1 Core Service

**Роль**: Фундамент системы, единый источник истины для пользователей, заявок и зданий

**Критические потребители**:
- **Operations Service** - получение данных о заявках для назначения
- **Communication Hub** - данные пользователей для уведомлений
- **AI/ML Service** - исторические данные для обучения

**API endpoints для других сервисов**:
```
POST /api/v1/auth/verify - проверка токенов
GET  /api/v1/users/{id} - данные пользователя
GET  /api/v1/requests/{id} - данные заявки
GET  /api/v1/assets/buildings/{id} - данные здания
```

**События публикуемые**:
- `user.created`, `user.updated`
- `request.created`, `request.updated`
- `asset.updated`

### 3.2 Operations Service

**Роль**: Управление операционной деятельностью

**Критические зависимости**:
- **Core Service** - данные о заявках и исполнителях

**Опциональные зависимости**:
- **AI/ML Service** - оптимизация назначений (fallback к базовым алгоритмам)
- **Integration Hub** - геоданные для маршрутизации

**Fallback стратегия при недоступности AI/ML**:
```
Если AI/ML недоступен:
  → Использовать базовый алгоритм назначения
  → Учитывать: специализацию, расстояние, загрузку
  → Результат: назначение за 100ms вместо 500ms
```

### 3.3 Communication Hub

**Роль**: Централизованная отправка уведомлений

**Критические зависимости**:
- **Core Service** - данные пользователей и контекст

**Опциональные зависимости**:
- **Media Storage** - отправка файлов в уведомлениях

**Приоритеты обработки**:
- **Urgent** (9-10): критические уведомления
- **Regular** (4-8): обычные уведомления
- **Batch** (1-3): массовые рассылки

### 3.4 Media Storage Service

**Роль**: Хранение и обработка медиафайлов

**Критические зависимости**: НЕТ

**Потребители**:
- **Communication Hub** - файлы для уведомлений
- **Telegram Bot** - загрузка/выгрузка медиа
- **Core Service** - аватары пользователей, документы

### 3.5 Analytics Service

**Роль**: Сбор метрик и генерация отчетов

**Критические зависимости**:
- **Core Service** - базовые данные для аналитики

**Источники данных**:
- События от всех сервисов через Event Bus
- Периодические запросы к API сервисов
- Логи и метрики производительности

**Особенности**:
- Read-only доступ ко всем сервисам
- Асинхронная обработка
- Не блокирует работу других сервисов

### 3.6 Integration Hub

**Роль**: Интеграция с внешними системами

**Критические зависимости**: НЕТ

**Взаимодействия**:
- **Core Service** - обновление справочника зданий
- **Operations Service** - геоданные для оптимизации

**Внешние интеграции**:
- Building Directory API
- Google Maps / Yandex Maps
- Google Sheets
- Payment Gateways

### 3.7 AI/ML Service [ОПЦИОНАЛЬНЫЙ]

**Роль**: Интеллектуальная оптимизация и прогнозирование

**Критические зависимости**:
- **Core Service** - исторические данные
- **Operations Service** - текущее состояние

**Особенности**:
- Может быть полностью отключен
- Все потребители имеют fallback
- Независимый deployment и scaling

---

## 4. Протоколы взаимодействия

### 4.1 Синхронное взаимодействие

| Протокол | Использование | Timeout | Retry |
|----------|---------------|---------|--------|
| **REST API** | Основной протокол между сервисами | 5-10 сек | 3 попытки |
| **gRPC** | AI/ML Service (низкая латентность) | 2-5 сек | 2 попытки |
| **WebSocket** | Real-time уведомления в Communication Hub | - | Auto-reconnect |

### 4.2 Асинхронное взаимодействие

| Механизм | Использование | Гарантии доставки |
|----------|---------------|-------------------|
| **Message Queue** | Задачи и команды между сервисами | At-least-once |
| **Event Bus** | Публикация событий | At-least-once |
| **Webhooks** | Уведомления от внешних систем | Best-effort |

---

## 5. Fallback сценарии

### 5.1 При недоступности Core Service

| Сервис | Влияние | Fallback |
|--------|---------|----------|
| **Operations** | ❌ Критично - не может работать | Кеш последних данных (5 мин) |
| **Communication Hub** | ❌ Критично - нет данных пользователей | Отложенная отправка |
| **AI/ML** | ❌ Критично - нет данных для анализа | Использование кешированных моделей |
| **Analytics** | ⚠️ Деградация - нет свежих данных | Работа с последним снапшотом |

### 5.2 При недоступности Operations Service

| Сервис | Влияние | Fallback |
|--------|---------|----------|
| **Core** | ✅ Не влияет | - |
| **Bot** | ⚠️ Нет управления сменами | Информирование пользователя |
| **Analytics** | ✅ Не критично | Пропуск метрик смен |

### 5.3 При недоступности Communication Hub

| Сервис | Влияние | Fallback |
|--------|---------|----------|
| **Core** | ✅ Не влияет | Логирование неотправленных уведомлений |
| **Operations** | ✅ Не влияет | Работа без уведомлений |
| **Bot** | ⚠️ Нет push-уведомлений | Показ в интерфейсе бота |

### 5.4 При недоступности AI/ML Service

| Сервис | Влияние | Fallback |
|--------|---------|----------|
| **Operations** | ✅ Не критично | Базовые алгоритмы назначения |
| **Analytics** | ✅ Не критично | Простая статистика без ML |

---

## 6. Критические пути

### 6.1 Создание заявки

```
User → Bot → Core Service → Event Bus
                ↓              ↓
         [Сохранение]   Operations Service
                           (назначение)
                               ↓
                        Communication Hub
                          (уведомления)
```

**Критические зависимости**: Core Service
**Опциональные**: Operations (можно назначить позже), Communication (можно без уведомлений)

### 6.2 Принятие смены

```
Executor → Bot → Operations Service → Core Service
                        ↓                  ↓
                  [Создание смены]   [Обновление статуса]
                        ↓
                 Communication Hub
                   (уведомления)
```

**Критические зависимости**: Operations Service, Core Service
**Опциональные**: Communication Hub

### 6.3 Генерация отчета

```
Manager → Bot/Admin → Analytics Service → Core Service
                           ↓                    ↓
                     [Сбор данных]        [Базовые данные]
                           ↓
                    [Генерация отчета]
                           ↓
                     Media Storage
                    (сохранение файла)
```

**Критические зависимости**: Analytics Service, Core Service
**Опциональные**: Media Storage (можно отдать inline)

---

## 7. Порядок запуска сервисов

### 7.1 Последовательность старта

| Порядок | Сервис | Зависит от | Критичность |
|---------|--------|------------|-------------|
| 1 | Message Queue | - | Инфраструктура |
| 2 | Redis Cache | - | Инфраструктура |
| 3 | Databases | - | Инфраструктура |
| 4 | Media Storage | - | Независимый |
| 5 | Integration Hub | - | Независимый |
| 6 | Core Service | DB, Cache | Критический |
| 7 | Operations Service | Core Service | Важный |
| 8 | Communication Hub | Core Service | Важный |
| 9 | Analytics Service | Core Service | Опциональный |
| 10 | Telegram Bot | Core, Communication | Frontend |
| 11 | AI/ML Service | Core, Operations | Опциональный |

### 7.2 Минимальный набор для MVP

✅ **Обязательные**:
1. Core Service
2. Operations Service
3. Communication Hub
4. Telegram Bot

⚠️ **Желательные**:
5. Media Storage
6. Integration Hub

🔄 **Опциональные**:
7. Analytics Service
8. AI/ML Service

---

## 8. Мониторинг зависимостей

### 8.1 Метрики здоровья

| Метрика | Threshold | Alert Level |
|---------|-----------|-------------|
| Service-to-service latency | > 2 сек | Warning |
| Failed dependency calls | > 5% | Critical |
| Circuit breaker open | - | Warning |
| Fallback activation rate | > 10% | Info |

### 8.2 Health Check endpoints

Каждый сервис должен предоставлять:
```
GET /health - базовая проверка
GET /health/ready - готовность к работе
GET /health/dependencies - статус зависимостей
```

Пример ответа `/health/dependencies`:
```json
{
  "status": "degraded",
  "dependencies": {
    "core_service": {
      "status": "healthy",
      "latency_ms": 45
    },
    "ai_ml_service": {
      "status": "unavailable",
      "fallback": "active",
      "last_error": "connection timeout"
    }
  }
}
```

---

## 9. Управление версиями API

### 9.1 Стратегия версионирования

| Правило | Описание |
|---------|----------|
| **URL versioning** | `/api/v1/`, `/api/v2/` |
| **Backward compatibility** | Минимум 6 месяцев |
| **Deprecation notice** | За 3 месяца |
| **Breaking changes** | Только в major версиях |

### 9.2 Совместимость между сервисами

| Consumer | Provider | Supported Versions |
|----------|----------|-------------------|
| Operations v1 | Core Service | v1, v2 |
| Bot v1 | Core Service | v1 |
| AI/ML v1 | Core Service | v1, v2 |
| Analytics v1 | All Services | v1, v2 |

---

## 10. Заключение

Карта зависимостей показывает:

✅ **Минимальные связи** - каждый сервис имеет 1-2 критические зависимости
✅ **Graceful degradation** - AI/ML полностью опциональный
✅ **Независимые сервисы** - Media Storage, Integration Hub автономны
✅ **Четкие fallback** - определены для всех критических путей

⚠️ **Точка отказа** - Core Service критичен для большинства операций
💡 **Рекомендация** - обеспечить HA для Core Service в первую очередь

---

**Документ подготовлен**: Архитектурная команда
**Последнее обновление**: 8 октября 2025
**Следующий пересмотр**: При изменении архитектуры