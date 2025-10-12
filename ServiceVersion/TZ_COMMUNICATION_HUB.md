# Техническое задание: Communication Hub

## 1. Общее описание

### 1.1 Назначение
Communication Hub - централизованный сервис для всех исходящих коммуникаций системы, включающий уведомления, чат-боты, WebSocket соединения и многоканальную доставку сообщений.

### 1.2 Цели
- Единая точка для всех исходящих коммуникаций (OUT)
- Многоканальная доставка сообщений
- Real-time взаимодействие через WebSocket
- Гарантированная доставка критичных уведомлений
- Управление чат-ботами и интерактивными интерфейсами

### 1.3 Ключевые характеристики
- **Порт**: 8003
- **Тип нагрузки**: Write-heavy, высокая конкурентность
- **Критичность**: Высокая для urgent уведомлений
- **Масштабирование**: Горизонтальное

## 2. Функциональные требования

### 2.1 Модуль уведомлений

#### 2.1.1 Notification Types
- **Urgent** (Priority 9-10): Новые заявки, экстренные ситуации
- **Regular** (Priority 4-8): Обновления статуса, комментарии
- **Batch** (Priority 1-3): Дайджесты, отчеты, массовые рассылки

#### 2.1.2 Delivery Channels (Q5.1)

**Принято решение**: Фокус на Telegram, email только для отчетов менеджерам

**Поддерживаемые каналы**:

**MVP (Phase 1)**:
- **Telegram**: ✅ Основной канал для всех пользователей
  - Real-time уведомления
  - Все типы событий
  - Rich media поддержка
  - Inline кнопки

- **Email**: ✅ Только для менеджеров и админов
  - Отчеты и дайджесты
  - Критичные алерты
  - Аналитика и метрики
  - Еженедельные/месячные сводки

**Не поддерживается в MVP**:
- ❌ SMS - убрано из плана
- ❌ Push notifications - нет мобильного приложения в MVP
- ❌ In-App notifications - только для WebApp в будущем

**Будущее (Phase 2+)**:
- WebSocket для WebApp
- Push для мобильного приложения
- Возможно SMS для критичных событий

#### 2.1.3 Notification Features
- Шаблонизация сообщений
- Многоязычность (RU/UZ/EN)
- Персонализация контента
- Rich media (изображения, файлы, кнопки)
- Tracking доставки и прочтения
- Retry механизм с exponential backoff

**Частота и группировка уведомлений**:

**Real-time** (немедленно):
- Новая заявка назначена
- Статус заявки изменен
- Новый комментарий
- Экстренная заявка

**Дайджесты** (группировка):
- Email отчеты для менеджеров: ежедневно в 09:00
- Еженедельные сводки: понедельник 10:00
- Месячные отчеты: 1-е число месяца 09:00

**Тихие часы**:
- Не настраиваются в MVP
- Все уведомления приходят немедленно
- Пользователь может отключить звук в Telegram

#### 2.1.4 Template Engine
- Mustache/Handlebars синтаксис
- Динамические переменные
- Условная логика
- Локализация
- Версионирование шаблонов
- A/B тестирование

#### 2.1.5 Delivery Guarantees
- At-least-once delivery для urgent
- Best-effort для regular
- Batch с rate limiting
- Idempotency для предотвращения дубликатов
- Dead Letter Queue для failed messages

### 2.2 Telegram Bot Module

#### 2.2.1 Bot Capabilities
- Команды и меню
- Inline keyboards
- Callback queries
- File upload/download
- Voice messages
- Location sharing
- Inline mode

#### 2.2.2 Bot Features
- Conversation flows (FSM)
- Context management
- Session storage
- Middleware pipeline
- Error handling
- Rate limiting per user

#### 2.2.3 User Interaction
- Natural language understanding (basic)
- Quick replies
- Persistent menu
- Deep linking
- User preferences
- Language selection

#### 2.2.4 Bot Commands
```
/start - Начало работы
/help - Помощь
/menu - Главное меню
/requests - Мои заявки
/create - Создать заявку
/status - Статус заявки
/profile - Профиль
/settings - Настройки
/language - Язык
/notifications - Настройки уведомлений
```

### 2.3 WebSocket Module

#### 2.3.1 Real-time Events
- Request updates
- Status changes
- New comments
- Assignment notifications
- System announcements
- Typing indicators
- Online presence

#### 2.3.2 Connection Management
- Authentication via JWT
- Heartbeat/Ping-Pong
- Auto-reconnection
- Connection pooling
- Load balancing
- Graceful shutdown

#### 2.3.3 Channels/Rooms
- User-specific channels
- Request channels
- Broadcast channels
- Private messaging
- Group chats
- System notifications

#### 2.3.4 Message Protocol
```json
{
  "type": "event|message|notification|presence",
  "channel": "channel_id",
  "event": "event_name",
  "data": {},
  "timestamp": "ISO8601",
  "id": "message_id"
}
```

### 2.4 Email Module

#### 2.4.1 Email Types
- Transactional emails
- Marketing campaigns
- Newsletters
- Reports and digests
- Password reset
- Verification emails

#### 2.4.2 Email Features
- HTML and plain text versions
- Attachments
- Inline images
- Email tracking (open, click)
- Unsubscribe management
- Bounce handling

#### 2.4.3 Email Providers
- Primary: SendGrid/Mailgun
- Fallback: Amazon SES
- Local: SMTP server
- Dev/Test: Mailhog

### 2.5 SMS Module

#### 2.5.1 SMS Types
- OTP codes
- Critical alerts
- Appointment reminders
- Status updates

#### 2.5.2 SMS Features
- Multiple providers support
- Fallback routing
- Delivery reports
- Short links
- Cost optimization

#### 2.5.3 SMS Providers
- Twilio (primary)
- MessageBird (fallback)
- Local operators API

### 2.6 Push Notifications Module

#### 2.6.1 Platforms
- Web Push (PWA)
- iOS (APNS)
- Android (FCM)
- Desktop notifications

#### 2.6.2 Features
- Silent notifications
- Rich notifications
- Actions/Buttons
- Badges
- Sound customization
- Priority levels

## 3. API Specifications

### 3.1 RESTful API

#### Notifications Endpoints
```
POST   /api/v1/notifications/send
POST   /api/v1/notifications/batch
GET    /api/v1/notifications
GET    /api/v1/notifications/{id}
GET    /api/v1/notifications/{id}/status
POST   /api/v1/notifications/{id}/retry
DELETE /api/v1/notifications/{id}
```

#### Templates Endpoints
```
GET    /api/v1/templates
GET    /api/v1/templates/{id}
POST   /api/v1/templates
PUT    /api/v1/templates/{id}
DELETE /api/v1/templates/{id}
POST   /api/v1/templates/{id}/preview
POST   /api/v1/templates/{id}/test
```

#### Subscriptions Endpoints
```
GET    /api/v1/subscriptions
POST   /api/v1/subscriptions
PUT    /api/v1/subscriptions/{id}
DELETE /api/v1/subscriptions/{id}
POST   /api/v1/subscriptions/preferences
```

#### Bot Endpoints
```
POST   /api/v1/bot/webhook
POST   /api/v1/bot/send-message
POST   /api/v1/bot/send-file
GET    /api/v1/bot/status
POST   /api/v1/bot/broadcast
```

### 3.2 WebSocket API
```
ws://localhost:8003/ws
wss://domain.com/ws

Events:
- connection.open
- connection.close
- message.send
- message.receive
- notification.new
- presence.update
- typing.start
- typing.stop
```

## 4. Асинхронные задачи

### 4.1 Очереди и приоритеты

#### URGENT Queue (Priority 9-10)
- `comm.notify.urgent` - Критичные уведомления
- `comm.telegram.urgent` - Срочные Telegram сообщения
- `comm.sms.otp` - OTP коды

#### REGULAR Queue (Priority 4-8)
- `comm.notify.regular` - Обычные уведомления
- `comm.email.transactional` - Транзакционные email
- `comm.push.notification` - Push уведомления

#### BATCH Queue (Priority 1-3)
- `comm.notify.batch` - Массовые рассылки
- `comm.email.newsletter` - Новостные рассылки
- `comm.report.daily` - Ежедневные отчеты

### 4.2 Retry Strategy
```
Attempt 1: immediate
Attempt 2: +30 seconds
Attempt 3: +2 minutes
Attempt 4: +5 minutes
Attempt 5: +15 minutes
Attempt 6: +1 hour
Attempt 7: +4 hours
Attempt 8: +12 hours
After: Dead Letter Queue
```

### 4.3 Rate Limiting
- Telegram: 30 msg/sec per bot
- Email: 100 msg/min
- SMS: 10 msg/sec
- Push: 1000 msg/sec
- Per user: 60 msg/hour

## 5. Message Processing

### 5.1 Message Pipeline
```
1. Receive message request
2. Validate recipient and channel
3. Load and render template
4. Apply personalization
5. Check rate limits
6. Queue for delivery
7. Deliver via channel
8. Handle response/errors
9. Update delivery status
10. Trigger webhooks
```

### 5.2 Batch Processing
```
1. Collect messages in batch
2. Group by channel and priority
3. Apply deduplication
4. Sort by priority
5. Process in chunks
6. Track progress
7. Handle failures
8. Generate report
```

### 5.3 Delivery Optimization
- Channel preference detection
- Optimal time delivery
- Frequency capping
- Engagement tracking
- Channel fallback

## 6. События и интеграции

### 6.1 Публикуемые события
```
notification.sent
notification.delivered
notification.failed
notification.opened
notification.clicked
template.used
subscription.created
subscription.updated
bot.message.received
bot.command.executed
websocket.connected
websocket.disconnected
```

### 6.2 Подписки на события
```
core.request.created
core.request.updated
core.user.created
operations.shift.assigned
operations.assignment.created
analytics.report.generated
```

### 6.3 Webhooks для внешних систем
- Delivery status callbacks
- Engagement tracking
- Unsubscribe notifications
- Bounce notifications

## 7. Безопасность

### 7.1 Аутентификация
- JWT для WebSocket
- API keys для внешних систем
- Telegram bot token validation
- Webhook signature verification

### 7.2 Авторизация
- Channel-based permissions
- Template access control
- Rate limiting per user/IP
- Subscription management

### 7.3 Data Protection
- Encryption in transit (TLS)
- PII masking in logs
- Message retention policies
- GDPR compliance

### 7.4 Anti-Spam
- Content filtering
- Reputation scoring
- Blacklist/Whitelist
- Captcha for suspicious activity

## 8. Производительность

### 8.1 Требования
- Message processing: < 50ms
- WebSocket latency: < 100ms
- Concurrent connections: 10,000
- Messages per second: 1,000
- Delivery time (urgent): < 2 seconds

### 8.2 Оптимизации
- Connection pooling
- Message batching
- Template caching
- Async I/O
- Circuit breakers

### 8.3 Кеширование
- Templates: 1 hour
- User preferences: 15 min
- Channel configs: 5 min
- Rate limit counters: Redis
- WebSocket sessions: In-memory

## 9. База данных

### 9.1 Схема данных

#### Notifications Table
- id
- user_id
- channel (telegram, email, sms, push)
- type (urgent, regular, batch)
- template_id
- template_data (JSON)
- status (queued, sending, sent, delivered, failed)
- attempts
- priority
- scheduled_at
- sent_at
- delivered_at
- opened_at
- clicked_at
- error_message
- created_at

#### Templates Table
- id
- name
- channel
- type
- subject
- content_html
- content_text
- variables (JSON)
- language
- version
- is_active
- created_at
- updated_at

#### Subscriptions Table
- id
- user_id
- channel
- address (email, phone, telegram_id)
- preferences (JSON)
- is_active
- verified_at
- unsubscribed_at
- created_at

#### Bot_Sessions Table
- id
- user_id
- telegram_id
- state
- context (JSON)
- last_activity
- created_at
- updated_at

#### WebSocket_Connections Table
- id
- user_id
- connection_id
- ip_address
- user_agent
- channels (JSON)
- connected_at
- disconnected_at
- last_ping

#### Message_Queue Table
- id
- queue_name
- priority
- payload (JSON)
- attempts
- max_attempts
- next_attempt_at
- created_at
- processed_at

### 9.2 Индексы
- notifications(user_id, status, created_at)
- notifications(channel, status)
- templates(channel, is_active)
- subscriptions(user_id, channel)
- bot_sessions(telegram_id, state)
- message_queue(queue_name, priority, next_attempt_at)

## 10. Мониторинг

### 10.1 Метрики
- Messages sent/delivered/failed per channel
- Delivery rate and latency
- Template usage
- WebSocket connections
- Queue lengths
- Error rates

### 10.2 Алерты
- High failure rate (> 5%)
- Queue backlog (> 1000 messages)
- Channel provider errors
- WebSocket connection drops
- Rate limit exceeded

### 10.3 Dashboards
- Real-time message flow
- Channel performance
- User engagement
- Error analysis
- Cost tracking (SMS/Email)

## 11. Интеграции

### 11.1 Messaging Providers
- Telegram Bot API
- SendGrid/Mailgun (Email)
- Twilio (SMS)
- Firebase Cloud Messaging (Push)
- OneSignal (Multi-channel)

### 11.2 Analytics
- Google Analytics (email tracking)
- Mixpanel (user engagement)
- Custom analytics service

### 11.3 Storage
- Redis (sessions, rate limiting)
- S3/MinIO (attachments)
- CDN (images, files)

## 12. Тестирование

### 12.1 Unit Tests
- Template rendering
- Message formatting
- Rate limiting logic
- Retry logic

### 12.2 Integration Tests
- Channel delivery
- WebSocket connections
- Bot conversations
- Webhook processing

### 12.3 Load Tests
- 10,000 concurrent WebSocket connections
- 1,000 messages/second
- Batch processing 100,000 messages

### 12.4 E2E Tests
- Full notification flow
- Bot interaction scenarios
- Multi-channel delivery
- Failure scenarios

## 13. Локализация

### 13.1 Поддерживаемые языки
- Русский (ru) - основной
- Узбекский (uz)
- Английский (en)

### 13.2 Локализация включает
- Шаблоны сообщений
- Bot команды и ответы
- Email темы
- Дата/время форматы
- Числовые форматы

## 14. Ограничения

### 14.1 Системные
- Max message size: 1MB
- Max attachments: 10MB
- Max recipients per batch: 10,000
- WebSocket message size: 64KB
- Template variables: 100

### 14.2 Rate Limits
- Per user: 60 messages/hour
- Per channel: defined by provider
- Batch size: 1,000 messages
- WebSocket messages: 100/minute

## 15. Отказоустойчивость и Disaster Recovery (Q6.2)

### 15.1 Graceful Degradation

**Принято решение**: Communication Hub некритичен для работы системы

**При недоступности Communication Hub**:
- Core Service продолжает работать
- Operations Service продолжает назначения
- Уведомления сохраняются в очередь
- При восстановлении - отправка накопленных уведомлений

**SLA**:
- Целевая доступность: 99.5%
- Время восстановления: не более 3 суток (некритично)
- Уведомление пользователей: при действиях в боте
- Массовая рассылка о недоступности: НЕТ

### 15.2 Dead Letter Queue
- Failed уведомления → DLQ
- Retry: 3 попытки с exponential backoff (1m, 5m, 15m)
- После 3 неудач → логирование + алерт админам
- Ручная повторная отправка из админки

### 15.3 Backup Strategy
- Message queue persistence
- Template versioning
- Session backup
- Delivery logs retention: 30 days

### 15.4 Failover
- Multiple provider support
- Channel fallback
- Queue persistence
- Circuit breakers

## 16. Roadmap

### Phase 1 (MVP)
- Telegram bot
- Basic notifications
- Email support
- WebSocket basic

### Phase 2
- SMS integration
- Push notifications
- Rich templates
- Advanced bot features

### Phase 3
- Multi-channel orchestration
- A/B testing
- Analytics integration
- Voice notifications