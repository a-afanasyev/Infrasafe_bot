# Integration Service - Architecture Documentation
**UK Management Bot - Integration Service**

**Version**: 1.0.0
**Created**: October 7, 2025
**Status**: Design Phase - Sprint 19-22

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Architecture Diagram](#architecture-diagram)
3. [Database Schema](#database-schema)
4. [Event Schema](#event-schema)
5. [API Design](#api-design)
6. [Integration Adapters](#integration-adapters)
7. [Security](#security)
8. [Performance](#performance)
9. [Deployment](#deployment)

---

## 🎯 Overview

### Purpose

Integration Service acts as a **centralized gateway** for all external integrations in the UK Management Bot system. It provides:

- ✅ **Unified Interface**: Single point of access for external services
- ✅ **Multi-Provider Support**: Google Sheets, Google Maps, Yandex Maps, Webhooks
- ✅ **Rate Limiting**: Prevents quota exhaustion
- ✅ **Response Caching**: Reduces API calls and costs
- ✅ **Event-Driven**: Publishes integration events to message bus
- ✅ **Comprehensive Logging**: Full audit trail for debugging

### Key Features

| Feature | Description |
|---------|-------------|
| **Multi-Tenancy** | Tenant isolation via `management_company_id` |
| **Provider Fallback** | Automatic failover to backup providers |
| **Rate Limiting** | Per-minute, per-hour, per-day quotas |
| **Response Caching** | Redis + PostgreSQL cache layers |
| **Webhook Support** | Receive events from external services |
| **Health Monitoring** | Track service availability and performance |
| **Cost Tracking** | Monitor API usage costs |

---

## 🏗️ Architecture Diagram

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Integration Service                         │
│                         (Port 8006)                              │
└─────────────────────────────────────────────────────────────────┘
                                │
                ┌───────────────┼───────────────┐
                │               │               │
                ▼               ▼               ▼
         ┌──────────┐    ┌──────────┐    ┌──────────┐
         │ Request  │    │  Shift   │    │   User   │
         │ Service  │    │ Service  │    │ Service  │
         └──────────┘    └──────────┘    └──────────┘
                                │
                ┌───────────────┼───────────────┐
                ▼               ▼               ▼
    ┌────────────────┐  ┌────────────┐  ┌─────────────┐
    │ Google Sheets  │  │  Geocoding │  │  Webhooks   │
    │   Adapter      │  │  Adapter   │  │   Handler   │
    └────────────────┘  └────────────┘  └─────────────┘
                ▼               ▼               ▼
    ┌────────────────┐  ┌────────────┐  ┌─────────────┐
    │ Google Sheets  │  │Google Maps │  │  External   │
    │      API       │  │Yandex Maps │  │  Services   │
    └────────────────┘  └────────────┘  └─────────────┘
                                │
                                ▼
                    ┌─────────────────────┐
                    │   Message Bus       │
                    │  (Integration       │
                    │   Events)           │
                    └─────────────────────┘
                                │
                ┌───────────────┼───────────────┐
                ▼               ▼               ▼
        ┌──────────┐    ┌──────────┐    ┌──────────┐
        │Analytics │    │   Alert  │    │  Logging │
        │ Service  │    │ Service  │    │ Service  │
        └──────────┘    └──────────┘    └──────────┘
```

### Component Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   Integration Service Core                       │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   FastAPI    │  │ Middleware   │  │  Exception   │         │
│  │ Application  │  │   Stack      │  │   Handlers   │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│                                                                  │
│  ┌─────────────────────────────────────────────────────┐       │
│  │                  API Endpoints                       │       │
│  │  - /services (External Service CRUD)                │       │
│  │  - /sheets (Google Sheets Operations)               │       │
│  │  - /geocoding (Geocoding Operations)                │       │
│  │  - /webhooks (Webhook Management)                   │       │
│  │  - /logs (Integration Logs Query)                   │       │
│  │  - /cache (Cache Management)                        │       │
│  └─────────────────────────────────────────────────────┘       │
│                                                                  │
│  ┌─────────────────────────────────────────────────────┐       │
│  │                Business Logic Layer                  │       │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐          │       │
│  │  │  Google  │  │Geocoding │  │ Webhook  │          │       │
│  │  │  Sheets  │  │  Service │  │  Service │          │       │
│  │  │ Adapter  │  └──────────┘  └──────────┘          │       │
│  │  └──────────┘                                        │       │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐          │       │
│  │  │  Rate    │  │  Cache   │  │  Event   │          │       │
│  │  │ Limiting │  │  Manager │  │ Publisher│          │       │
│  │  └──────────┘  └──────────┘  └──────────┘          │       │
│  └─────────────────────────────────────────────────────┘       │
│                                                                  │
│  ┌─────────────────────────────────────────────────────┐       │
│  │                   Data Layer                         │       │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐          │       │
│  │  │   ORM    │  │  Redis   │  │  Event   │          │       │
│  │  │(SQLAlch) │  │  Cache   │  │  Bus     │          │       │
│  │  └──────────┘  └──────────┘  └──────────┘          │       │
│  └─────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────┘
                                │
                ┌───────────────┼───────────────┐
                ▼               ▼               ▼
        ┌─────────────┐  ┌──────────┐  ┌─────────────┐
        │ PostgreSQL  │  │  Redis   │  │  RabbitMQ   │
        │(integration │  │  Cache   │  │ (Events)    │
        │     _db)    │  │          │  │             │
        └─────────────┘  └──────────┘  └─────────────┘
```

---

## 💾 Database Schema

### Entity-Relationship Diagram

```
┌─────────────────────────────────────────────────────────┐
│                   external_services                      │
├─────────────────────────────────────────────────────────┤
│ PK  id (UUID)                                           │
│     management_company_id (VARCHAR)                     │
│     service_name (VARCHAR)                              │
│     service_type (VARCHAR)                              │
│     display_name (VARCHAR)                              │
│     base_url (VARCHAR)                                  │
│     api_key (TEXT)                                      │
│     credentials (JSON)                                  │
│     config (JSON)                                       │
│     is_active (BOOLEAN)                                 │
│     health_status (VARCHAR)                             │
│     last_health_check (TIMESTAMP)                       │
│     rate_limit_per_minute (INTEGER)                     │
│     rate_limit_per_day (INTEGER)                        │
│     priority (INTEGER)                                  │
│     fallback_service_id (UUID)                          │
│     created_at, updated_at                              │
└─────────────────────────────────────────────────────────┘
                        │
                        │ FK (service_id)
                        ▼
┌─────────────────────────────────────────────────────────┐
│                   integration_logs                       │
├─────────────────────────────────────────────────────────┤
│ PK  id (UUID)                                           │
│     management_company_id (VARCHAR)                     │
│ FK  service_id (UUID) → external_services.id           │
│     service_name (VARCHAR)                              │
│     operation (VARCHAR)                                 │
│     endpoint (VARCHAR)                                  │
│     http_method (VARCHAR)                               │
│     request_headers (JSON)                              │
│     request_body (JSON)                                 │
│     response_status_code (INTEGER)                      │
│     response_body (JSON)                                │
│     started_at (TIMESTAMP)                              │
│     completed_at (TIMESTAMP)                            │
│     duration_ms (INTEGER)                               │
│     status (VARCHAR)                                    │
│     error_message (TEXT)                                │
│     retry_count (INTEGER)                               │
│     estimated_cost (FLOAT)                              │
└─────────────────────────────────────────────────────────┘
                        │
                        │ FK (service_id)
                        ▼
┌─────────────────────────────────────────────────────────┐
│                    api_rate_limits                       │
├─────────────────────────────────────────────────────────┤
│ PK  id (UUID)                                           │
│     management_company_id (VARCHAR)                     │
│ FK  service_id (UUID) → external_services.id           │
│     service_name (VARCHAR)                              │
│     window_type (VARCHAR)                               │
│     window_start (TIMESTAMP)                            │
│     window_end (TIMESTAMP)                              │
│     request_count (INTEGER)                             │
│     max_requests (INTEGER)                              │
│     remaining_requests (INTEGER)                        │
│     is_rate_limited (BOOLEAN)                           │
│     total_cost (FLOAT)                                  │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                   integration_cache                      │
├─────────────────────────────────────────────────────────┤
│ PK  id (UUID)                                           │
│     management_company_id (VARCHAR)                     │
│ UK  cache_key (VARCHAR) - UNIQUE                        │
│ FK  service_id (UUID) → external_services.id           │
│     service_name (VARCHAR)                              │
│     operation (VARCHAR)                                 │
│     request_hash (VARCHAR)                              │
│     response_data (JSON)                                │
│     ttl_seconds (INTEGER)                               │
│     expires_at (TIMESTAMP)                              │
│     hit_count (INTEGER)                                 │
│     cache_status (VARCHAR)                              │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                    webhook_configs                       │
├─────────────────────────────────────────────────────────┤
│ PK  id (UUID)                                           │
│     management_company_id (VARCHAR)                     │
│     webhook_name (VARCHAR)                              │
│     webhook_url (VARCHAR)                               │
│     webhook_token (VARCHAR)                             │
│     source_service (VARCHAR)                            │
│ FK  source_service_id (UUID) → external_services.id    │
│     event_types (JSON)                                  │
│     secret_key (TEXT)                                   │
│     is_active (BOOLEAN)                                 │
│     total_received (INTEGER)                            │
│     total_successful (INTEGER)                          │
│     total_failed (INTEGER)                              │
└─────────────────────────────────────────────────────────┘
```

### Table Details

#### 1. **external_services** (Service Configuration)

**Purpose**: Store configuration for external services

**Key Indexes**:
- `ix_external_services_tenant_service` on `(management_company_id, service_name)`

**Example Data**:
```json
{
  "id": "uuid-123",
  "management_company_id": "uk_company_1",
  "service_name": "google_maps",
  "service_type": "geocoding",
  "display_name": "Google Maps API",
  "base_url": "https://maps.googleapis.com/maps/api",
  "api_key": "encrypted_key",
  "is_active": true,
  "health_status": "healthy",
  "rate_limit_per_minute": 60,
  "priority": 100
}
```

#### 2. **integration_logs** (Request/Response Logs)

**Purpose**: Full audit trail of all integration calls

**Key Indexes**:
- `ix_integration_logs_service_operation` on `(service_name, operation, started_at)`

**Retention Policy**: 90 days (configurable)

#### 3. **webhook_configs** (Webhook Configuration)

**Purpose**: Configure incoming webhooks from external services

**Security**: Token-based authentication, signature verification

#### 4. **api_rate_limits** (Rate Limit Tracking)

**Purpose**: Track API usage against quotas

**Window Types**: minute, hour, day, month

#### 5. **integration_cache** (Response Cache)

**Purpose**: Cache API responses to reduce calls

**TTL**: 5-60 minutes (configurable per operation)

---

## 📡 Event Schema

### Event Types (10 Total)

| Event Type | Description | Subscribers |
|------------|-------------|-------------|
| `integration.service.registered` | Service registered | Analytics, Notification |
| `integration.request.sent` | Request sent to API | Analytics, Logging |
| `integration.request.completed` | Request completed | Analytics, Cache |
| `integration.request.failed` | Request failed | Analytics, Alert |
| `integration.webhook.received` | Webhook received | Target services |
| `integration.rate_limit.exceeded` | Rate limit hit | Alert, Notification |
| `integration.cache.hit` | Cache hit | Analytics |
| `integration.cache.miss` | Cache miss | Analytics |
| `integration.health.degraded` | Service unhealthy | Alert, Notification |
| `integration.health.recovered` | Service recovered | Notification |

### Event Flow Diagram

```
┌────────────┐     Event     ┌─────────────┐     Event     ┌──────────┐
│Integration │──────────────→│  RabbitMQ   │──────────────→│Analytics │
│  Service   │               │  Exchange   │               │ Service  │
└────────────┘               └─────────────┘               └──────────┘
                                    │
                                    ├──────────────→┌──────────┐
                                    │               │  Alert   │
                                    │               │ Service  │
                                    │               └──────────┘
                                    │
                                    └──────────────→┌──────────┐
                                                    │   Log    │
                                                    │ Service  │
                                                    └──────────┘
```

---

## 🔌 Integration Adapters

### 1. Google Sheets Adapter

**Operations**:
- ✅ Read range
- ✅ Write range
- ✅ Append rows
- ✅ Batch operations

**Rate Limiting**: 100 requests/minute per tenant

**Caching**: TTL 5 minutes for read operations

### 2. Geocoding Adapter

**Providers**:
- Google Maps API (primary)
- Yandex Maps API (fallback)

**Operations**:
- ✅ Geocode (address → coordinates)
- ✅ Reverse geocode (coordinates → address)
- ✅ Distance calculation

**Rate Limiting**: 50 requests/minute per tenant

**Caching**: TTL 60 minutes (addresses rarely change)

### 3. Webhook Handler

**Supported Sources**:
- GitHub
- Stripe
- Telegram
- Custom webhooks

**Security**:
- ✅ Token authentication
- ✅ Signature verification (HMAC-SHA256)
- ✅ IP whitelisting

---

## 🔒 Security

### Multi-Tenancy Isolation

```python
# Every request requires tenant header
X-Management-Company-Id: uk_company_1
```

All database queries filtered by `management_company_id`

### Authentication

- **Internal Services**: Service-to-service tokens
- **External Webhooks**: Token + signature verification
- **Admin API**: JWT Bearer tokens

### Data Encryption

- ✅ API keys encrypted at rest (AES-256)
- ✅ Secrets stored in environment variables
- ✅ HTTPS/TLS for all external API calls

---

## ⚡ Performance

### Caching Strategy

**Two-Layer Cache**:

1. **Redis** (L1): Fast in-memory cache, TTL 5 minutes
2. **PostgreSQL** (L2): Persistent cache, TTL 60 minutes

**Cache Hit Rate Target**: 70-80%

### Rate Limiting

**Algorithm**: Token bucket with Redis backing

**Limits** (per tenant):
- Google Sheets: 100 req/min
- Geocoding: 50 req/min
- Webhooks: 200 req/min

### Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| API Response Time | < 200ms | 95th percentile, cached |
| API Response Time | < 500ms | 95th percentile, uncached |
| Cache Hit Rate | > 70% | For read operations |
| Database Query Time | < 50ms | 95th percentile |
| Event Publishing | < 10ms | Async, non-blocking |

---

## 🚀 Deployment

### Docker Configuration

**Image**: `uk-management/integration-service:latest`
**Port**: 8006
**Health Check**: `/health`

### Environment Variables

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@host/integration_db

# Redis
REDIS_URL=redis://redis:6379/3

# External Services
GOOGLE_SHEETS_CREDENTIALS_PATH=/secrets/google_sheets.json
GOOGLE_MAPS_API_KEY=<encrypted>
YANDEX_MAPS_API_KEY=<encrypted>

# Message Bus
RABBITMQ_URL=amqp://user:pass@rabbitmq:5672/

# Service Config
MANAGEMENT_COMPANY_ID=uk_company_1
DEBUG=false
LOG_LEVEL=INFO
```

### Resource Requirements

| Resource | Development | Production |
|----------|-------------|------------|
| CPU | 0.5 cores | 2 cores |
| Memory | 512 MB | 2 GB |
| Storage | 1 GB | 20 GB |

---

## 📊 Monitoring

### Prometheus Metrics

```
# Request metrics
integration_requests_total{service, operation, status}
integration_request_duration_seconds{service, operation}

# Cache metrics
integration_cache_hits_total{service, operation}
integration_cache_misses_total{service, operation}

# Rate limit metrics
integration_rate_limits_exceeded_total{service}
integration_rate_limit_utilization{service}

# Health metrics
integration_service_health{service, status}
```

### Grafana Dashboards

- **Integration Overview**: Request rates, latency, errors
- **Cache Performance**: Hit rates, evictions
- **Rate Limits**: Usage, quota exhaustion
- **Cost Tracking**: API call costs by service

---

## 📝 Next Steps

**Task 1.1** ✅ **COMPLETED** - Architecture design
**Task 1.2** ⏳ **NEXT** - Base service structure
**Task 1.3** ⏳ **PENDING** - Google Sheets adapter
**Task 1.4** ⏳ **PENDING** - Geocoding integration
**Task 1.5** ⏳ **PENDING** - Docker & production config
**Task 1.6** ⏳ **PENDING** - Tests & documentation

---

**Last Updated**: October 7, 2025
**Author**: Claude Code (Sprint 19-22)
**Status**: ✅ Architecture Design Complete
