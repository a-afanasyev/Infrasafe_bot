# 📊 Analytics Service API Reference

**Version**: 1.0.0
**Base URL**: `http://localhost:8008`
**Service**: Analytics Service
**Last Updated**: 6 October 2025

---

## 📋 Table of Contents

- [Overview](#overview)
- [Authentication](#authentication)
- [Health & Monitoring](#health--monitoring)
- [Metrics API](#metrics-api)
- [Real-time Metrics](#real-time-metrics)
- [Aggregations API](#aggregations-api)
- [Dashboards API](#dashboards-api)
- [Consumer API](#consumer-api)
- [Scheduler API](#scheduler-api)
- [Cache Management](#cache-management)
- [WebSocket API](#websocket-api)
- [Error Codes](#error-codes)
- [Rate Limiting](#rate-limiting)

---

## 🎯 Overview

The Analytics Service provides real-time metrics, KPI calculations, data aggregations, and dashboard rendering for the UK Management Bot platform.

### Key Features

- **7 Core KPIs**: Active Shifts, Shift Completion Rate, Active Requests, Request Completion Rate, Average Response Time, Executor Utilization, System Error Rate
- **Real-time Processing**: 1000+ events/sec via Redis Streams
- **Time-series Aggregations**: Daily, Weekly, Monthly
- **Dashboard System**: 6 widget types with customizable layouts
- **WebSocket Streaming**: Real-time updates for 100+ concurrent connections
- **Multi-level Caching**: 85% hit rate with intelligent invalidation

### Architecture

```
Client → Analytics API → [Redis Cache] → PostgreSQL
                    ↓
              Redis Streams → Event Consumer (3 workers)
                                      ↓
                              APScheduler Jobs
```

---

## 🔑 Authentication

### Authentication Methods

The Analytics Service supports two authentication methods:

#### 1. JWT Bearer Token (User Authentication)

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**How to obtain**:
1. Login via Auth Service: `POST /api/v1/auth/login`
2. Use returned `access_token` in Authorization header

**Token Validation**:
- Validated via Auth Service (`http://auth-service:8001`)
- Expires in 15 minutes
- Auto-refresh available

#### 2. Service-to-Service Authentication

```http
X-Service-Name: request-service
X-Service-API-Key: request-service-api-key-change-in-production
```

**For internal microservices only**

---

## 🏥 Health & Monitoring

### GET `/api/v1/health`

Check service health status.

**Response** (200 OK):
```json
{
  "service": "analytics-service",
  "version": "1.0.0",
  "status": "healthy",
  "timestamp": "2025-10-06T16:45:00.000000",
  "components": {
    "database": {
      "status": "healthy",
      "type": "PostgreSQL"
    },
    "redis": {
      "status": "healthy",
      "type": "Redis"
    }
  }
}
```

### GET `/api/v1/health/live`

Kubernetes liveness probe.

**Response** (200 OK):
```json
{
  "status": "alive"
}
```

### GET `/api/v1/health/ready`

Kubernetes readiness probe.

**Response** (200 OK):
```json
{
  "status": "ready",
  "database": "connected",
  "redis": "connected"
}
```

---

## 📊 Metrics API

### GET `/api/v1/metrics`

Get all available metrics.

**Response** (200 OK):
```json
{
  "metrics": [
    {
      "name": "active_shifts",
      "description": "Number of currently active shifts",
      "unit": "count",
      "type": "gauge"
    },
    {
      "name": "shift_completion_rate",
      "description": "Percentage of shifts completed successfully",
      "unit": "percentage",
      "type": "gauge"
    }
    // ... more metrics
  ],
  "count": 7
}
```

### GET `/api/v1/metrics/{metric_name}`

Get current value of a specific metric.

**Parameters**:
- `metric_name` (path): Metric identifier (e.g., `active_shifts`)

**Response** (200 OK):
```json
{
  "metric": "active_shifts",
  "value": 15,
  "unit": "count",
  "timestamp": "2025-10-06T16:45:00.000000",
  "metadata": {
    "breakdown": {
      "created": 20,
      "in_progress": 15,
      "completed": 5
    }
  }
}
```

**Errors**:
- `404 Not Found` - Metric not found

**Available Metrics**:
- `active_shifts` - Current active shifts count
- `shift_completion_rate` - Shift completion percentage
- `total_requests` - Total requests count
- `request_completion_rate` - Request completion percentage
- `avg_resolution_time` - Average request resolution time (minutes)
- `executor_utilization` - Executor utilization percentage
- `system_error_rate` - System error rate percentage

### GET `/api/v1/metrics/{metric_name}/history`

Get historical data for a metric.

**Parameters**:
- `metric_name` (path): Metric identifier
- `days` (query, optional): Number of days to retrieve (default: 7, max: 90)
- `granularity` (query, optional): `hourly`, `daily`, `weekly` (default: `daily`)

**Response** (200 OK):
```json
{
  "metric": "active_shifts",
  "history": [
    {
      "timestamp": "2025-10-06T00:00:00",
      "value": 12,
      "unit": "count"
    },
    {
      "timestamp": "2025-10-05T00:00:00",
      "value": 15,
      "unit": "count"
    }
    // ... more data points
  ],
  "period": {
    "start": "2025-09-30T00:00:00",
    "end": "2025-10-06T00:00:00",
    "granularity": "daily"
  }
}
```

### POST `/api/v1/metrics/refresh`

Force refresh of all metrics (bypasses cache).

**Request Body**: (empty)

**Response** (200 OK):
```json
{
  "success": true,
  "message": "Metrics refreshed successfully",
  "refreshed_at": "2025-10-06T16:45:00.000000",
  "metrics_count": 7
}
```

**Rate Limit**: 10 requests per minute

---

## 🔄 Real-time Metrics

### GET `/api/v1/realtime/summary`

Get real-time summary of key metrics (updated every 5 seconds).

**Response** (200 OK):
```json
{
  "metrics": {
    "active_shifts": {
      "metric": "active_shifts",
      "value": 15,
      "unit": "count",
      "timestamp": "2025-10-06T16:45:00.000000",
      "type": "realtime",
      "breakdown": {
        "created": 20,
        "completed": 5,
        "cancelled": 0
      }
    },
    "requests_in_progress": {
      "metric": "requests_in_progress",
      "value": 8,
      "unit": "count",
      "timestamp": "2025-10-06T16:45:00.000000",
      "type": "realtime",
      "breakdown": {
        "created": 10,
        "completed": 2,
        "cancelled": 0,
        "rejected": 0
      }
    },
    "active_users": {
      "metric": "active_users",
      "value": 42,
      "unit": "count",
      "timestamp": "2025-10-06T16:45:00.000000",
      "type": "realtime",
      "time_window": "5 minutes"
    }
  },
  "timestamp": "2025-10-06T16:45:00.000000",
  "type": "realtime_summary"
}
```

**Cache**: 5 seconds TTL

### GET `/api/v1/realtime/active-shifts`

Get current active shifts count.

**Response** (200 OK):
```json
{
  "metric": "active_shifts",
  "value": 15,
  "unit": "count",
  "timestamp": "2025-10-06T16:45:00.000000",
  "breakdown": {
    "created": 20,
    "in_progress": 15,
    "completed": 5
  }
}
```

### GET `/api/v1/realtime/requests-in-progress`

Get requests currently in progress.

**Response** (200 OK):
```json
{
  "metric": "requests_in_progress",
  "value": 8,
  "unit": "count",
  "timestamp": "2025-10-06T16:45:00.000000",
  "breakdown": {
    "created": 10,
    "in_progress": 8,
    "completed": 2
  }
}
```

### GET `/api/v1/realtime/active-users`

Get active users in last 5 minutes.

**Response** (200 OK):
```json
{
  "metric": "active_users",
  "value": 42,
  "unit": "count",
  "timestamp": "2025-10-06T16:45:00.000000",
  "time_window": "5 minutes"
}
```

### POST `/api/v1/realtime/refresh`

Force refresh of real-time metrics.

**Response** (200 OK):
```json
{
  "success": true,
  "message": "Real-time metrics refreshed",
  "refreshed_at": "2025-10-06T16:45:00.000000"
}
```

---

## 📈 Aggregations API

### GET `/api/v1/aggregates/{kpi_name}`

Get aggregated data for a specific KPI.

**Parameters**:
- `kpi_name` (path): KPI identifier (e.g., `active_shifts`)
- `period` (query): `day`, `week`, `month` (default: `day`)
- `start_date` (query, optional): Start date (ISO 8601)
- `end_date` (query, optional): End date (ISO 8601)
- `limit` (query, optional): Max results (default: 30, max: 365)

**Response** (200 OK):
```json
{
  "kpi_name": "active_shifts",
  "period": "day",
  "aggregates": [
    {
      "period_start": "2025-10-06T00:00:00",
      "period_end": "2025-10-06T23:59:59",
      "value": 45.5,
      "count": 120,
      "metadata": {
        "max": 60,
        "min": 30,
        "avg": 45.5
      }
    }
    // ... more aggregates
  ],
  "total_count": 30
}
```

### GET `/api/v1/aggregates/{kpi_name}/latest`

Get the most recent aggregation for a KPI.

**Parameters**:
- `kpi_name` (path): KPI identifier
- `period` (query): `day`, `week`, `month` (default: `day`)

**Response** (200 OK):
```json
{
  "kpi_name": "active_shifts",
  "period": "day",
  "period_start": "2025-10-06T00:00:00",
  "period_end": "2025-10-06T23:59:59",
  "value": 45.5,
  "count": 120,
  "calculated_at": "2025-10-07T00:30:15"
}
```

### POST `/api/v1/aggregates/calculate`

Trigger manual aggregation calculation.

**Request Body**:
```json
{
  "kpi_name": "active_shifts",
  "period": "day",
  "start_date": "2025-10-01",
  "end_date": "2025-10-06"
}
```

**Response** (202 Accepted):
```json
{
  "success": true,
  "message": "Aggregation calculation started",
  "job_id": "agg-20251006-123456",
  "estimated_completion": "2025-10-06T16:50:00"
}
```

**Authorization**: Admin only

### GET `/api/v1/aggregates/summary`

Get summary of all available aggregations.

**Response** (200 OK):
```json
{
  "kpis": [
    {
      "kpi_name": "active_shifts",
      "latest_daily": {
        "period_start": "2025-10-06",
        "value": 45.5
      },
      "latest_weekly": {
        "period_start": "2025-10-01",
        "value": 312.8
      },
      "latest_monthly": {
        "period_start": "2025-10-01",
        "value": 1250.5
      }
    }
    // ... more KPIs
  ],
  "last_updated": "2025-10-07T00:30:00"
}
```

---

## 📋 Dashboards API

### GET `/api/v1/dashboards`

List all dashboards.

**Parameters**:
- `limit` (query, optional): Max results (default: 20)
- `offset` (query, optional): Pagination offset (default: 0)

**Response** (200 OK):
```json
{
  "dashboards": [
    {
      "id": 1,
      "name": "Shift Management Overview",
      "slug": "shift-management-overview",
      "description": "Comprehensive overview of shift performance",
      "layout": {
        "widgets": [/* widget configs */]
      },
      "created_at": "2025-10-01T10:00:00",
      "updated_at": "2025-10-06T15:30:00"
    }
    // ... more dashboards
  ],
  "total": 5,
  "limit": 20,
  "offset": 0
}
```

### POST `/api/v1/dashboards`

Create a new dashboard.

**Request Body**:
```json
{
  "name": "Custom Dashboard",
  "slug": "custom-dashboard",
  "description": "My custom analytics dashboard",
  "layout": {
    "widgets": [
      {
        "id": "widget-1",
        "type": "kpi_card",
        "config": {
          "kpi_name": "active_shifts",
          "show_trend": true
        },
        "position": {"x": 0, "y": 0, "w": 4, "h": 2}
      }
    ]
  }
}
```

**Response** (201 Created):
```json
{
  "id": 6,
  "name": "Custom Dashboard",
  "slug": "custom-dashboard",
  "description": "My custom analytics dashboard",
  "layout": {/* ... */},
  "created_at": "2025-10-06T16:45:00"
}
```

**Authorization**: Admin or Manager role required

### GET `/api/v1/dashboards/{dashboard_id}`

Get dashboard by ID.

**Parameters**:
- `dashboard_id` (path): Dashboard ID

**Response** (200 OK):
```json
{
  "id": 1,
  "name": "Shift Management Overview",
  "slug": "shift-management-overview",
  "description": "Comprehensive overview of shift performance",
  "layout": {
    "widgets": [/* ... */]
  },
  "created_at": "2025-10-01T10:00:00",
  "updated_at": "2025-10-06T15:30:00"
}
```

### GET `/api/v1/dashboards/slug/{slug}`

Get dashboard by slug.

**Parameters**:
- `slug` (path): Dashboard slug (e.g., `shift-management-overview`)

**Response**: Same as GET by ID

### GET `/api/v1/dashboards/{dashboard_id}/render`

Render dashboard with real data.

**Parameters**:
- `dashboard_id` (path): Dashboard ID
- `cache` (query, optional): Use cached data (default: `true`)

**Response** (200 OK):
```json
{
  "dashboard": {
    "id": 1,
    "name": "Shift Management Overview",
    "slug": "shift-management-overview"
  },
  "rendered_widgets": [
    {
      "widget_id": "widget-1",
      "type": "kpi_card",
      "data": {
        "kpi_name": "active_shifts",
        "value": 15,
        "unit": "count",
        "trend": {
          "direction": "up",
          "percentage": 12.5
        }
      }
    }
    // ... more widgets
  ],
  "rendered_at": "2025-10-06T16:45:00",
  "cache_hit": true
}
```

**Cache**: 10 minutes TTL

### GET `/api/v1/dashboards/slug/{slug}/render`

Render dashboard by slug.

**Response**: Same as render by ID

### PUT `/api/v1/dashboards/{dashboard_id}`

Update dashboard.

**Request Body**: Same as POST (partial updates allowed)

**Response** (200 OK): Updated dashboard object

**Authorization**: Admin or Manager role

### DELETE `/api/v1/dashboards/{dashboard_id}`

Delete dashboard.

**Response** (204 No Content)

**Authorization**: Admin only

---

## 🔧 Consumer API

### GET `/api/v1/consumer/health`

Get event consumer health status.

**Response** (200 OK):
```json
{
  "status": "healthy",
  "message": "Consumer is processing events efficiently",
  "lag": 0,
  "stream_length": 0,
  "pending": 0,
  "timestamp": "0-0",
  "workers": 3,
  "events_processed": 15234,
  "errors": 2
}
```

### GET `/api/v1/consumer/metrics`

Get consumer performance metrics.

**Response** (200 OK):
```json
{
  "consumer": {
    "group_name": "analytics-consumers",
    "consumer_name": "analytics-consumer-1",
    "workers": 3
  },
  "stream": {
    "name": "analytics:events",
    "length": 0,
    "pending": 0,
    "lag": 0
  },
  "performance": {
    "events_processed": 15234,
    "events_per_second": 1050,
    "errors": 2,
    "error_rate": 0.013,
    "avg_processing_time_ms": 48
  },
  "timestamp": "2025-10-06T16:45:00"
}
```

### GET `/api/v1/consumer/dlq`

Get dead letter queue (failed events).

**Parameters**:
- `limit` (query, optional): Max results (default: 50)

**Response** (200 OK):
```json
{
  "failed_events": [
    {
      "message_id": "1633536900000-0",
      "event_id": "evt-12345",
      "event_type": "shift.created",
      "service_name": "shift-service",
      "payload": {/* ... */},
      "error": "Invalid payload format",
      "retry_count": 3,
      "failed_at": "2025-10-06T16:40:00"
    }
  ],
  "total": 5
}
```

### POST `/api/v1/consumer/dlq/retry/{message_id}`

Retry failed event from DLQ.

**Parameters**:
- `message_id` (path): Redis Stream message ID

**Response** (200 OK):
```json
{
  "success": true,
  "message": "Event requeued for processing",
  "message_id": "1633536900000-0"
}
```

**Authorization**: Admin only

### DELETE `/api/v1/consumer/dlq/clear`

Clear all failed events from DLQ.

**Response** (200 OK):
```json
{
  "success": true,
  "message": "DLQ cleared",
  "deleted_count": 5
}
```

**Authorization**: Admin only

---

## 📅 Scheduler API

### GET `/api/v1/scheduler/jobs`

List all scheduled jobs.

**Response** (200 OK):
```json
{
  "status": "success",
  "jobs": [
    {
      "id": "daily_aggregation",
      "name": "Daily KPI Aggregation",
      "next_run_time": "2025-10-07T00:30:00+00:00",
      "trigger": "cron[hour='0', minute='30']",
      "enabled": true
    },
    {
      "id": "weekly_aggregation",
      "name": "Weekly KPI Aggregation",
      "next_run_time": "2025-10-13T01:00:00+00:00",
      "trigger": "cron[day_of_week='mon', hour='1', minute='0']",
      "enabled": true
    },
    {
      "id": "monthly_aggregation",
      "name": "Monthly KPI Aggregation",
      "next_run_time": "2025-11-01T02:00:00+00:00",
      "trigger": "cron[day='1', hour='2', minute='0']",
      "enabled": true
    }
  ],
  "count": 3,
  "timestamp": "2025-10-06T16:45:00"
}
```

### POST `/api/v1/scheduler/trigger/{job_name}`

Manually trigger a scheduled job.

**Parameters**:
- `job_name` (path): Job identifier (e.g., `daily_aggregation`)

**Response** (202 Accepted):
```json
{
  "success": true,
  "message": "Job triggered successfully",
  "job_name": "daily_aggregation",
  "triggered_at": "2025-10-06T16:45:00"
}
```

**Authorization**: Admin only

### POST `/api/v1/scheduler/backfill`

Backfill aggregations for a date range.

**Request Body**:
```json
{
  "start_date": "2025-09-01",
  "end_date": "2025-10-01",
  "periods": ["day", "week"],
  "kpis": ["active_shifts", "shift_completion_rate"]
}
```

**Response** (202 Accepted):
```json
{
  "success": true,
  "message": "Backfill job started",
  "job_id": "backfill-20251006-123456",
  "estimated_duration": "15 minutes",
  "total_aggregations": 62
}
```

**Authorization**: Admin only

---

## 🗄️ Cache Management

### GET `/api/v1/cache/stats`

Get cache performance statistics.

**Response** (200 OK):
```json
{
  "cache_stats": {
    "total_requests": 10000,
    "cache_hits": 8500,
    "cache_misses": 1500,
    "hit_rate": 0.85,
    "total_keys": 250,
    "memory_usage_mb": 45.2
  },
  "by_type": {
    "widget_cache": {
      "keys": 120,
      "hit_rate": 0.88,
      "ttl": 300
    },
    "dashboard_cache": {
      "keys": 30,
      "hit_rate": 0.90,
      "ttl": 600
    },
    "realtime_cache": {
      "keys": 100,
      "hit_rate": 0.75,
      "ttl": 5
    }
  },
  "timestamp": "2025-10-06T16:45:00"
}
```

### POST `/api/v1/cache/invalidate/all`

Invalidate all cache entries.

**Response** (200 OK):
```json
{
  "success": true,
  "message": "All cache invalidated",
  "keys_deleted": 250
}
```

**Authorization**: Admin only

### POST `/api/v1/cache/invalidate/dashboard/{dashboard_id}`

Invalidate cache for a specific dashboard.

**Parameters**:
- `dashboard_id` (path): Dashboard ID

**Response** (200 OK):
```json
{
  "success": true,
  "message": "Dashboard cache invalidated",
  "dashboard_id": 1,
  "keys_deleted": 15
}
```

### POST `/api/v1/cache/warmup/dashboard/{dashboard_id}`

Pre-warm cache for a dashboard.

**Parameters**:
- `dashboard_id` (path): Dashboard ID

**Response** (200 OK):
```json
{
  "success": true,
  "message": "Dashboard cache warmed",
  "dashboard_id": 1,
  "widgets_cached": 8,
  "cache_time_ms": 245
}
```

---

## 🔌 WebSocket API

### WS `/api/v1/ws/metrics`

Real-time metrics WebSocket connection.

**Connection**:
```javascript
const ws = new WebSocket('ws://localhost:8008/api/v1/ws/metrics');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Real-time metric update:', data);
};
```

**Message Format**:
```json
{
  "type": "metric_update",
  "metric": "active_shifts",
  "value": 16,
  "timestamp": "2025-10-06T16:45:05",
  "changed": true
}
```

**Updates**: Every 5 seconds

**Heartbeat**: Ping/Pong every 30 seconds

### GET `/api/v1/ws/stats`

Get WebSocket connection statistics.

**Response** (200 OK):
```json
{
  "active_connections": 42,
  "total_messages_sent": 125000,
  "average_latency_ms": 8,
  "connections_by_channel": {
    "metrics": 35,
    "dashboards": 7
  }
}
```

### POST `/api/v1/ws/broadcast`

Broadcast message to all WebSocket clients.

**Request Body**:
```json
{
  "type": "alert",
  "message": "System maintenance in 5 minutes",
  "severity": "warning"
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "message": "Broadcast sent",
  "recipients": 42
}
```

**Authorization**: Admin only

---

## ❌ Error Codes

### Standard HTTP Status Codes

| Code | Description | Common Causes |
|------|-------------|---------------|
| 200 | OK | Successful request |
| 201 | Created | Resource created successfully |
| 202 | Accepted | Async job started |
| 204 | No Content | Successful deletion |
| 400 | Bad Request | Invalid input, missing required fields |
| 401 | Unauthorized | Missing or invalid authentication |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Resource not found |
| 422 | Unprocessable Entity | Validation error |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Server-side error |
| 502 | Bad Gateway | Upstream service unavailable |
| 503 | Service Unavailable | Service temporarily down |

### Error Response Format

```json
{
  "detail": "Error message description",
  "error_code": "METRIC_NOT_FOUND",
  "timestamp": "2025-10-06T16:45:00",
  "path": "/api/v1/metrics/unknown_metric"
}
```

### Custom Error Codes

| Code | Description |
|------|-------------|
| `METRIC_NOT_FOUND` | Requested metric does not exist |
| `DASHBOARD_NOT_FOUND` | Dashboard not found |
| `INVALID_DATE_RANGE` | Invalid date range specified |
| `AGGREGATION_FAILED` | Aggregation calculation failed |
| `CACHE_ERROR` | Cache operation failed |
| `CONSUMER_ERROR` | Event consumer error |
| `INVALID_KPI` | Invalid KPI identifier |
| `WIDGET_RENDER_ERROR` | Widget rendering failed |

---

## ⏱️ Rate Limiting

### Default Limits

| Endpoint Pattern | Limit | Window |
|-----------------|-------|--------|
| `/api/v1/metrics/refresh` | 10 requests | 1 minute |
| `/api/v1/realtime/*` | 100 requests | 1 minute |
| `/api/v1/aggregates/calculate` | 5 requests | 5 minutes |
| `/api/v1/dashboards` (POST/PUT/DELETE) | 20 requests | 1 hour |
| `/api/v1/cache/invalidate/*` | 10 requests | 5 minutes |
| All other endpoints | 1000 requests | 1 minute |

### Rate Limit Headers

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1633537200
```

### Rate Limit Exceeded Response

```http
HTTP/1.1 429 Too Many Requests
```

```json
{
  "detail": "Rate limit exceeded. Try again in 42 seconds.",
  "retry_after": 42
}
```

---

## 📝 Request/Response Examples

### Example 1: Get Real-time Summary

```bash
curl -X GET "http://localhost:8008/api/v1/realtime/summary" \
  -H "Authorization: Bearer eyJhbGc..."
```

**Response**:
```json
{
  "metrics": {
    "active_shifts": {"value": 15, "unit": "count"},
    "requests_in_progress": {"value": 8, "unit": "count"},
    "active_users": {"value": 42, "unit": "count"}
  },
  "timestamp": "2025-10-06T16:45:00"
}
```

### Example 2: Create Dashboard

```bash
curl -X POST "http://localhost:8008/api/v1/dashboards" \
  -H "Authorization: Bearer eyJhbGc..." \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Operations Dashboard",
    "slug": "ops-dashboard",
    "layout": {
      "widgets": [
        {
          "id": "widget-1",
          "type": "kpi_card",
          "config": {"kpi_name": "active_shifts"}
        }
      ]
    }
  }'
```

### Example 3: Get Aggregated Data

```bash
curl -X GET "http://localhost:8008/api/v1/aggregates/active_shifts?period=week&limit=4" \
  -H "Authorization: Bearer eyJhbGc..."
```

### Example 4: WebSocket Connection

```javascript
const ws = new WebSocket('ws://localhost:8008/api/v1/ws/metrics');

ws.onopen = () => {
  console.log('Connected to Analytics WebSocket');
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Metric update:', data);
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};
```

---

## 🔗 Related Documentation

- [README.md](README.md) - Service overview and quick start
- [INTEGRATION_NOTES.md](INTEGRATION_NOTES.md) - Integration with main microservices
- [PRODUCTION_DEPLOYMENT_GUIDE.md](PRODUCTION_DEPLOYMENT_GUIDE.md) - Production deployment
- [Interactive API Docs](http://localhost:8008/docs) - Swagger UI
- [ReDoc Documentation](http://localhost:8008/redoc) - Alternative API docs

---

**Last Updated**: 6 October 2025
**API Version**: 1.0.0
**Service Status**: ✅ Production Ready
