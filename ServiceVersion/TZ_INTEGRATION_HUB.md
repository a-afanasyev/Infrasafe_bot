# Техническое задание: Integration Hub

## 1. Общее описание

### 1.1 Назначение
Integration Hub - централизованный сервис для интеграции с внешними системами, обработки входящих данных (IN), кеширования внешних API и управления webhook-интеграциями.

### 1.2 Цели
- Единая точка интеграции с внешними API
- Кеширование данных из внешних источников
- Обработка входящих webhook-запросов
- Синхронизация данных между системами
- Rate limiting и retry механизмы для внешних API

### 1.3 Ключевые характеристики
- **Порт**: 8006
- **Тип нагрузки**: Write-heavy (60% запись в кеш), real-time processing
- **Критичность**: Средняя
- **Масштабирование**: Горизонтальное
- **Кеширование**: Redis для быстрого доступа

## 2. Функциональные требования

### 2.1 Модуль внешних API

#### 2.1.1 Supported External APIs
- **Building Directory API**
  - Получение информации о зданиях
  - Поиск по адресу
  - Обновление данных о зданиях

- **Google Services**
  - Google Maps (геокодирование, маршруты)
  - Google Sheets (синхронизация данных)
  - Google Calendar (интеграция расписаний)

- **Yandex Services**
  - Yandex Maps (геокодирование, маршруты)
  - Yandex Geocoder (адресная информация)

- **Payment Gateways**
  - Local payment systems

- **SMS Gateways**
  - Local SMS providers

- **Weather APIs**
  - OpenWeatherMap
  - Weather.com

#### 2.1.2 API Client Features
- Connection pooling
- Automatic retry с exponential backoff
- Circuit breaker pattern
- Rate limiting соблюдение
- Response caching
- Request/Response logging
- Error handling
- Timeout management

#### 2.1.3 Authentication Methods
- API Key
- OAuth 2.0
- JWT Bearer
- Basic Auth
- Custom headers
- Certificate-based

#### 2.1.4 Data Transformation
- Response mapping
- Data validation
- Format conversion
- Field normalization
- Type coercion
- Default values

### 2.2 Модуль кеширования

#### 2.2.1 Caching Strategy
- **Cache-aside pattern** - для редко меняющихся данных
- **Write-through** - для критичных данных
- **Write-behind** - для bulk операций
- **Refresh-ahead** - для предиктивной загрузки

#### 2.2.2 Cache Layers
```
L1: In-memory cache (application level)
    ├── TTL: 1 minute
    └── Size: 100MB

L2: Redis cache (distributed)
    ├── TTL: 5-60 minutes (configurable)
    └── Size: 10GB

L3: Database cache tables
    ├── TTL: 1-24 hours
    └── Size: unlimited
```

#### 2.2.3 Cache Keys Structure
```
{service}:{entity}:{id}:{version}
Examples:
building:info:123:v1
google:geocode:address_hash:v2
weather:current:city_id:v1
```

#### 2.2.4 Cache Invalidation
- TTL-based expiration
- Event-based invalidation
- Manual purge
- Partial invalidation
- Cache warming
- Versioning

### 2.3 Модуль webhook

#### 2.3.1 Webhook Endpoints
```
POST /webhooks/building-directory
POST /webhooks/payment-gateway
POST /webhooks/sms-delivery
POST /webhooks/calendar-sync
POST /webhooks/custom/{provider}
```

#### 2.3.2 Webhook Security
- Signature verification (HMAC-SHA256)
- IP whitelisting
- Rate limiting
- Replay attack protection
- SSL/TLS only
- Token validation

#### 2.3.3 Webhook Processing
```
1. Receive webhook
2. Verify signature
3. Validate payload
4. Queue for processing
5. Send acknowledgment
6. Process asynchronously
7. Transform data
8. Publish events
9. Update cache
10. Log transaction
```

#### 2.3.4 Webhook Features
- Automatic retries from sender
- Idempotency handling
- Dead letter queue
- Event deduplication
- Batch webhook support
- Webhook forwarding

### 2.4 Модуль синхронизации

#### 2.4.1 Sync Types
- **One-way sync** - External → Internal
- **Two-way sync** - Bidirectional
- **Incremental sync** - Delta changes only
- **Full sync** - Complete dataset
- **Real-time sync** - Event-driven
- **Scheduled sync** - Cron-based

#### 2.4.2 Google Sheets Sync
```python
Features:
- Bidirectional sync
- Conflict resolution
- Batch updates
- Change tracking
- Version control
- Rollback capability
```

#### 2.4.3 Building Directory Sync
```python
Features:
- Daily full sync
- Real-time updates via webhook
- Data validation
- Mapping rules
- Error recovery
```

#### 2.4.4 Conflict Resolution
- Last-write-wins
- Source-of-truth priority
- Manual resolution queue
- Merge strategies
- Conflict logging

### 2.5 Модуль геокодирования

#### 2.5.1 Geocoding Features
- Address to coordinates
- Coordinates to address
- Batch geocoding
- Place search
- Address validation
- Distance calculation

#### 2.5.2 Provider Fallback
```
Primary: Google Maps
  ├── Fallback 1: Yandex Maps
  └── Fallback 2: OpenStreetMap
```

#### 2.5.3 Geocoding Cache
- Address → Coordinates: 30 days TTL
- Coordinates → Address: 30 days TTL
- Distance matrix: 7 days TTL
- Place details: 24 hours TTL

## 3. API Specifications

### 3.1 RESTful API

#### External API Proxy Endpoints
```
GET    /api/v1/external/building/{building_id}
POST   /api/v1/external/geocode
GET    /api/v1/external/weather/{location}
POST   /api/v1/external/payment/charge
GET    /api/v1/external/sheets/{spreadsheet_id}
```

#### Cache Management Endpoints
```
GET    /api/v1/cache/stats
GET    /api/v1/cache/{key}
DELETE /api/v1/cache/{key}
POST   /api/v1/cache/purge
POST   /api/v1/cache/warm
```

#### Webhook Management Endpoints
```
GET    /api/v1/webhooks
POST   /api/v1/webhooks/register
PUT    /api/v1/webhooks/{id}
DELETE /api/v1/webhooks/{id}
GET    /api/v1/webhooks/{id}/logs
POST   /api/v1/webhooks/{id}/test
```

#### Sync Endpoints
```
POST   /api/v1/sync/trigger
GET    /api/v1/sync/status
GET    /api/v1/sync/history
POST   /api/v1/sync/rollback
GET    /api/v1/sync/conflicts
POST   /api/v1/sync/resolve
```

## 4. Асинхронные задачи

### 4.1 Очереди и приоритеты

#### HIGH Priority (8-10)
- `integration.webhook.process` - Обработка webhooks
- `integration.payment.process` - Платежные операции

#### MEDIUM Priority (4-7)
- `integration.api.fetch` - Запросы к внешним API
- `integration.geocode` - Геокодирование
- `integration.sync.incremental` - Инкрементальная синхронизация

#### LOW Priority (1-3)
- `integration.sync.full` - Полная синхронизация
- `integration.cache.warm` - Прогрев кеша
- `integration.cleanup` - Очистка старых данных

### 4.2 Scheduled Tasks

```python
# Каждые 15 минут
'sync-google-sheets': {
    'task': 'integration.sync.google_sheets',
    'schedule': crontab(minute='*/15'),
}

# Каждый час
'refresh-building-cache': {
    'task': 'integration.cache.refresh_buildings',
    'schedule': crontab(minute=0),
}

# Ежедневно в 02:00
'full-building-sync': {
    'task': 'integration.sync.buildings_full',
    'schedule': crontab(hour=2, minute=0),
}

# Каждые 5 минут
'process-failed-webhooks': {
    'task': 'integration.webhook.retry_failed',
    'schedule': crontab(minute='*/5'),
}
```

## 5. База данных и хранение

### 5.1 PostgreSQL Schema

#### External_APIs Table
- id
- name
- base_url
- auth_type
- credentials (encrypted)
- rate_limit
- timeout
- is_active
- created_at
- updated_at

#### API_Requests_Log Table
- id
- api_id
- endpoint
- method
- request_headers
- request_body
- response_status
- response_headers
- response_body
- duration_ms
- error_message
- created_at

#### Webhooks Table
- id
- provider
- endpoint
- secret
- events (Array)
- is_active
- last_received_at
- created_at

#### Webhook_Events Table
- id
- webhook_id
- event_id (unique)
- payload
- signature
- status
- attempts
- processed_at
- error_message
- created_at

#### Sync_Jobs Table
- id
- source
- destination
- type (full, incremental)
- status
- started_at
- completed_at
- records_processed
- records_failed
- error_log
- metadata

#### Cache_Entries Table
- key (PK)
- value
- ttl
- hits_count
- last_accessed
- created_at
- expires_at

### 5.2 Redis Structure

#### Cache Namespaces
```
building:*        - Building data
geocode:*         - Geocoding results
weather:*         - Weather data
sheets:*          - Google Sheets data
api:response:*    - API responses
rate:limit:*      - Rate limiting counters
webhook:dedup:*   - Webhook deduplication
```

#### Redis Data Types
- Strings: Simple key-value pairs
- Hashes: Structured objects
- Sets: Unique collections
- Sorted Sets: Rankings/priorities
- Lists: Queues
- Streams: Event logs

## 6. Внешние API интеграции

### 6.1 Building Directory API
```python
Endpoints:
GET  /buildings - List buildings
GET  /buildings/{id} - Get building
POST /buildings/search - Search buildings
PUT  /buildings/{id} - Update building

Rate Limit: 100 req/min
Cache TTL: 5 minutes
Retry: 3 attempts with exponential backoff
```

### 6.2 Google Maps API
```python
Services:
- Geocoding API
- Distance Matrix API
- Places API
- Roads API

Rate Limit: 10 QPS
Cache TTL: 30 days for geocoding
Cost optimization through caching
```

### 6.3 Google Sheets API
```python
Operations:
- Read ranges
- Write ranges
- Batch update
- Create spreadsheet

Rate Limit: 100 requests per 100 seconds
Batch operations for efficiency
Change detection через revision ID
```

### 6.4 Payment Gateway API
```python
Operations:
- Create charge
- Refund payment
- List transactions
- Webhook notifications

Security: PCI compliance
Idempotency keys
Webhook signature verification
```

## 7. Безопасность

### 7.1 API Security
- Encrypted credential storage
- Secret rotation
- API key management
- OAuth token refresh
- Certificate pinning

### 7.2 Data Security
- PII masking in logs
- Encryption at rest
- Secure webhook endpoints
- Request signing
- Response validation

### 7.3 Access Control
- Service-to-service auth
- Rate limiting per service
- IP whitelisting
- Audit logging

## 8. Производительность

### 8.1 Требования
- API response (cached): < 50ms
- API response (fresh): < 2s
- Webhook processing: < 500ms
- Sync operation: < 5 min for 10k records
- Cache hit ratio: > 80%

### 8.2 Оптимизации
- Connection pooling
- Response compression
- Batch operations
- Parallel processing
- Smart caching
- Query optimization

### 8.3 Rate Limiting
- Per API provider limits
- Internal service limits
- User-based limits
- Endpoint-specific limits
- Burst allowance

## 9. Отказоустойчивость (Q6.2)

**Принято решение**: Integration Hub частично критичен

**Graceful Degradation по интеграциям**:

| Интеграция | Критичность | Fallback |
|-----------|-------------|----------|
| Building Directory API | Средняя | Работа из Redis кеша адресов |
| Geocoding API | Низкая | Использование сохраненных координат |
| External Auth (OAuth) | Средняя | Локальная авторизация |
| Payment Gateway | Высокая | Очередь платежей, отложенная обработка |
| Analytics/Monitoring | Низкая | Пропуск метрик |

**SLA восстановления**:
- Критичные интеграции: 1 сутки
- Некритичные: 3 суток

**Кеширование** для offline работы:
- Адреса зданий: 24 часа
- Геокодирование: 7 дней
- Статические справочники: 30 дней

## 10. Мониторинг

### 10.1 Метрики
- API call success rate
- Response times
- Cache hit ratio
- Webhook processing time
- Sync job duration
- Error rates by provider

### 9.2 Алерты
- API failures (> 5%)
- Rate limit exceeded
- Webhook signature failures
- Sync job failures
- Cache memory usage (> 80%)
- High latency (> 2s)

### 9.3 Dashboards
- API health status
- Cache performance
- Webhook activity
- Sync status
- Cost tracking (paid APIs)
- Rate limit usage

## 10. Error Handling

### 10.1 Retry Strategies
```python
Exponential Backoff:
1st retry: 1 second
2nd retry: 2 seconds
3rd retry: 4 seconds
4th retry: 8 seconds
5th retry: 16 seconds
Max retries: 5
```

### 10.2 Circuit Breaker
```python
States:
- Closed: Normal operation
- Open: Failures exceeded threshold
- Half-Open: Testing recovery

Thresholds:
- Error rate: > 50%
- Timeout: 5 seconds
- Recovery time: 30 seconds
```

### 10.3 Fallback Mechanisms
- Cache fallback for API failures
- Alternative provider routing
- Graceful degradation
- Default values
- Queue for later processing

## 11. Тестирование

### 11.1 Unit Tests
- API client methods
- Cache operations
- Data transformations
- Webhook validation

### 11.2 Integration Tests
- External API calls
- Webhook processing
- Sync operations
- Cache invalidation

### 11.3 Performance Tests
- High volume API calls
- Cache stress test
- Webhook bombardment
- Concurrent sync jobs

### 11.4 Reliability Tests
- API failure scenarios
- Network issues
- Rate limit handling
- Circuit breaker behavior

## 12. Документация

### 12.1 API Documentation
- Integration guides
- Authentication setup
- Webhook configuration
- Error codes
- Rate limits

### 12.2 Provider Documentation
- Supported providers
- Configuration examples
- Troubleshooting guides
- Best practices

## 13. Compliance

### 13.1 Data Compliance
- GDPR compliance
- Data residency
- Right to be forgotten
- Data retention policies

### 13.2 API Compliance
- Terms of service adherence
- Rate limit compliance
- License requirements
- Attribution requirements

## 14. Cost Optimization

### 14.1 API Cost Management
- Usage tracking
- Cost alerts
- Quota management
- Provider comparison

### 14.2 Optimization Strategies
- Aggressive caching
- Batch operations
- Off-peak scheduling
- Provider switching

## 15. Roadmap

### Phase 1 (MVP)
- Building Directory integration
- Google Maps geocoding
- Basic caching
- Simple webhooks

### Phase 2
- Google Sheets sync
- Payment gateway
- Advanced caching
- Webhook management UI

### Phase 3
- Multi-provider support
- Cost optimization
- Advanced sync features
- API marketplace