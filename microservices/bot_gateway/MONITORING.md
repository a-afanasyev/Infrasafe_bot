# Bot Gateway Service - Monitoring & Observability
**UK Management Bot - Sprint 19-22**

Complete monitoring and observability solution for Bot Gateway Service using Prometheus, Grafana, and Jaeger.

---

## 📊 Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Quick Start](#quick-start)
4. [Metrics](#metrics)
5. [Dashboards](#dashboards)
6. [Distributed Tracing](#distributed-tracing)
7. [Alerting](#alerting)
8. [Troubleshooting](#troubleshooting)

---

## 🎯 Overview

The monitoring stack provides comprehensive observability into the Bot Gateway Service:

- **Prometheus** - Metrics collection and storage
- **Grafana** - Metrics visualization and dashboards
- **Jaeger** - Distributed tracing
- **Alertmanager** - Alert routing and management
- **Node Exporter** - System-level metrics
- **Redis Exporter** - Redis metrics
- **Postgres Exporter** - PostgreSQL metrics
- **cAdvisor** - Container metrics

### Key Features

✅ **50+ Custom Metrics** - Comprehensive application instrumentation
✅ **3 Pre-built Dashboards** - Overview, Services, Performance
✅ **15+ Alert Rules** - Proactive issue detection
✅ **Distributed Tracing** - End-to-end request tracking
✅ **Multi-service Monitoring** - All microservices in one place
✅ **Historical Data** - 30-day retention for analysis

---

## 🏗 Architecture

```
┌─────────────────┐
│  Bot Gateway    │─────┐
│    Service      │     │
└─────────────────┘     │
                        │ /metrics
┌─────────────────┐     │
│  Auth Service   │─────┤
└─────────────────┘     │
                        │
┌─────────────────┐     │
│ Request Service │─────┤
└─────────────────┘     │
                        │
         ⋮              ↓
                  ┌──────────┐      ┌──────────┐      ┌──────────┐
                  │Prometheus│─────→│ Grafana  │←────→│   User   │
                  └──────────┘      └──────────┘      └──────────┘
                        │
                        ↓
                  ┌──────────┐
                  │Alertmgr  │─────→ Slack/Email
                  └──────────┘

Distributed Tracing:
┌─────────────────┐      ┌──────────┐      ┌──────────┐
│  Bot Gateway    │─────→│  Jaeger  │←────→│   User   │
│  (OpenTelemetry)│      │   Agent  │      └──────────┘
└─────────────────┘      └──────────┘
```

---

## 🚀 Quick Start

### 1. Start Monitoring Stack

```bash
# Start Bot Gateway + Monitoring services
docker-compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d

# Check all services are running
docker-compose ps
```

### 2. Access Dashboards

| Service | URL | Credentials |
|---------|-----|-------------|
| **Grafana** | http://localhost:3000 | admin / admin |
| **Prometheus** | http://localhost:9090 | - |
| **Jaeger UI** | http://localhost:16686 | - |
| **Alertmanager** | http://localhost:9093 | - |

### 3. View Metrics Endpoint

```bash
# Bot Gateway metrics
curl http://localhost:8000/metrics

# Sample output:
# bot_gateway_messages_total{message_type="text",user_role="applicant",language="ru"} 1234
# bot_gateway_message_processing_duration_seconds_bucket{le="0.1"} 980
# bot_gateway_active_sessions{user_role="applicant"} 45
```

### 4. Test Alert

```bash
# Generate high error rate to trigger alert
for i in {1..100}; do
  curl -X POST http://localhost:8000/webhook -H "Content-Type: application/json" -d '{"invalid": "data"}'
done

# Check Alertmanager: http://localhost:9093/#/alerts
```

---

## 📈 Metrics

### Application Metrics

#### Message Metrics
- `bot_gateway_messages_total` - Total messages by type, role, language
- `bot_gateway_message_processing_duration_seconds` - Processing time histogram
- `bot_gateway_commands_total` - Command execution counter
- `bot_gateway_callbacks_total` - Callback query counter

#### FSM State Metrics
- `bot_gateway_fsm_state_transitions_total` - State transition counter
- `bot_gateway_active_fsm_sessions` - Active FSM sessions gauge

#### Error Metrics
- `bot_gateway_errors_total` - Error counter by type and severity
- `bot_gateway_exceptions_total` - Unhandled exception counter

#### Performance Metrics
- `bot_gateway_middleware_duration_seconds` - Middleware execution time
- `bot_gateway_event_loop_lag_seconds` - Event loop lag histogram

#### Service Integration Metrics
- `bot_gateway_service_requests_total` - Backend service request counter
- `bot_gateway_service_request_duration_seconds` - Service response time
- `bot_gateway_service_errors_total` - Service error counter
- `bot_gateway_service_circuit_breaker_state` - Circuit breaker status (0=closed, 1=open, 2=half-open)

#### Authentication Metrics
- `bot_gateway_auth_attempts_total` - Authentication attempt counter
- `bot_gateway_active_sessions` - Active session gauge
- `bot_gateway_session_duration_seconds` - Session duration histogram

#### Rate Limiting Metrics
- `bot_gateway_rate_limit_hits_total` - Rate limit hit counter
- `bot_gateway_rate_limit_blocks_total` - Rate limit block counter

#### Redis Metrics
- `bot_gateway_redis_operations_total` - Redis operation counter
- `bot_gateway_redis_operation_duration_seconds` - Redis latency
- `bot_gateway_redis_connection_pool_size` - Connection pool gauge

#### Resource Metrics
- `bot_gateway_memory_usage_bytes` - Memory usage by type
- `bot_gateway_cpu_usage_percent` - CPU usage percentage

### Business Metrics

#### Request Management
- `bot_gateway_requests_created_total` - Requests created via bot
- `bot_gateway_requests_viewed_total` - Requests viewed
- `bot_gateway_requests_updated_total` - Request updates

#### Shift Management
- `bot_gateway_shifts_viewed_total` - Shifts viewed
- `bot_gateway_shifts_taken_total` - Shifts taken by specialization
- `bot_gateway_shifts_released_total` - Shifts released
- `bot_gateway_availability_updates_total` - Availability updates

#### Admin Panel
- `bot_gateway_admin_actions_total` - Admin action counter
- `bot_gateway_admin_searches_total` - Admin search counter
- `bot_gateway_broadcasts_sent_total` - Broadcast message counter
- `bot_gateway_broadcast_recipients` - Recipients per broadcast histogram

#### User Activity
- `bot_gateway_active_users` - Active users by time window and role
- `bot_gateway_user_actions_total` - User action counter

---

## 📊 Dashboards

### 1. Bot Gateway - Overview
**Purpose:** High-level service health and activity

**Panels:**
- Message rate by type and role
- Message processing duration (95th percentile)
- Active sessions and FSM sessions
- Error rate
- Command execution rate
- Callback query rate
- Rate limit blocks
- FSM state transitions

**Use Cases:**
- Daily health check
- Identify traffic patterns
- Detect anomalies

**Access:** Grafana → Bot Gateway → Overview

---

### 2. Bot Gateway - Service Integration
**Purpose:** Monitor backend service interactions

**Panels:**
- Service request rate
- Service response time (95th percentile)
- Per-service request breakdown (Auth, Request, User, Shift)
- Service error rate by service
- Service error table (last 1h)
- Circuit breaker states
- Individual service panels

**Use Cases:**
- Troubleshoot slow responses
- Identify failing services
- Monitor circuit breaker status

**Access:** Grafana → Bot Gateway → Service Integration

---

### 3. Bot Gateway - Performance & Resources
**Purpose:** System performance and resource usage

**Panels:**
- Memory usage (RSS, heap, external)
- CPU usage
- Event loop lag (95th, 99th percentile)
- Redis operations rate
- Redis operation latency
- Redis connection pool
- Middleware duration
- Session duration distribution

**Use Cases:**
- Capacity planning
- Performance optimization
- Memory leak detection
- Redis bottleneck identification

**Access:** Grafana → Bot Gateway → Performance & Resources

---

## 🔍 Distributed Tracing

### Overview

Distributed tracing with Jaeger provides end-to-end visibility into request flows across microservices.

**Automatically instrumented:**
- HTTP requests (aiohttp, httpx)
- Redis operations
- Database queries (SQLAlchemy)

### Accessing Traces

1. **Open Jaeger UI:** http://localhost:16686
2. **Select Service:** `Bot Gateway Service`
3. **Search by:**
   - Operation name (e.g., `/webhook`, `process_message`)
   - Time range
   - Duration (find slow requests)
   - Tags (user_id, message_type, etc.)

### Example Trace Structure

```
Bot Gateway: /webhook [200ms]
├─ Auth Middleware [10ms]
│  └─ Auth Service: POST /api/v1/auth/verify [5ms]
├─ Request Handler [180ms]
│  ├─ Redis: GET user:123 [2ms]
│  ├─ Request Service: GET /api/v1/requests [50ms]
│  │  └─ PostgreSQL: SELECT * FROM requests [40ms]
│  └─ Telegram: sendMessage [120ms]
└─ Metrics Middleware [10ms]
```

### Custom Spans

Add custom spans in your code:

```python
from app.core.tracing import create_span, add_span_attribute

# Create custom span
with create_span("complex_operation") as span:
    add_span_attribute("user_id", user_id)
    add_span_attribute("operation_type", "assignment")

    # Your code here
    result = await process_assignment(request_id)

    add_span_attribute("result_status", result.status)
```

---

## 🚨 Alerting

### Alert Rules

| Alert | Severity | Threshold | Duration | Description |
|-------|----------|-----------|----------|-------------|
| **HighErrorRate** | warning | >1 err/sec | 5m | Elevated error rate |
| **CriticalErrorRate** | critical | >5 err/sec | 2m | Very high error rate |
| **HighMessageLatency** | warning | >2s (p95) | 5m | Slow message processing |
| **HighServiceErrorRate** | warning | >0.5 err/sec | 5m | Backend service errors |
| **CircuitBreakerOpen** | critical | state=1 | 1m | Service circuit breaker open |
| **ExcessiveRateLimitBlocks** | warning | >10/sec | 5m | High rate limit blocking |
| **HighMemoryUsage** | warning | >1GB | 5m | Memory usage elevated |
| **CriticalMemoryUsage** | critical | >2GB | 2m | Very high memory usage |
| **HighEventLoopLag** | warning | >100ms (p95) | 5m | Event loop blocking |
| **RedisConnectionPoolExhausted** | warning | <2 available | 2m | Redis pool depleted |
| **HighRedisLatency** | warning | >100ms (p95) | 5m | Redis slow responses |
| **NoActiveSessions** | warning | 0 sessions | 10m | No user activity |
| **ExcessiveFSMSessions** | warning | >1000 | 5m | Possible memory leak |
| **ServiceRequestTimeout** | critical | >10s (p95) | 3m | Service timeouts |
| **HighAuthFailureRate** | warning | >1/sec | 5m | Authentication issues |
| **HighWebhookFailureRate** | warning | >0.5/sec | 3m | Webhook processing failures |

### Alert Routing

**Critical Alerts:**
- Slack: #bot-gateway-critical
- Webhook: notification-service
- Repeat: Every 5 minutes
- Immediate notification (0s wait)

**Warning Alerts:**
- Slack: #bot-gateway-warnings
- Repeat: Every 1 hour
- Batched (30s wait)

**Resolved Alerts:**
- All receivers notified when resolved

### Testing Alerts

```bash
# Simulate high error rate
curl -X POST http://localhost:9093/api/v1/alerts -H "Content-Type: application/json" -d '[
  {
    "labels": {
      "alertname": "HighErrorRate",
      "severity": "warning",
      "service": "bot-gateway"
    },
    "annotations": {
      "summary": "Test alert",
      "description": "This is a test alert"
    }
  }
]'
```

### Configuring Slack Webhooks

1. Create Slack webhook: https://api.slack.com/messaging/webhooks
2. Update `monitoring/alertmanager/alertmanager.yml`:
   ```yaml
   global:
     slack_api_url: 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'
   ```
3. Restart Alertmanager:
   ```bash
   docker-compose restart alertmanager
   ```

---

## 🔧 Troubleshooting

### Common Issues

#### 1. No Metrics Appearing

**Problem:** Grafana shows no data

**Solution:**
```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets

# Verify Bot Gateway metrics endpoint
curl http://localhost:8000/metrics

# Check Prometheus logs
docker-compose logs prometheus

# Restart services
docker-compose restart bot-gateway prometheus
```

---

#### 2. Jaeger Not Receiving Traces

**Problem:** No traces in Jaeger UI

**Solution:**
```bash
# Check tracing is enabled in .env
TRACING_ENABLED=true
JAEGER_HOST=jaeger
JAEGER_PORT=6831

# Check Jaeger connectivity
nc -zv jaeger 6831

# Check Bot Gateway logs for tracing initialization
docker-compose logs bot-gateway | grep tracing

# Restart Bot Gateway
docker-compose restart bot-gateway
```

---

#### 3. Alerts Not Firing

**Problem:** Expected alerts not appearing in Alertmanager

**Solution:**
```bash
# Check alert rules are loaded
curl http://localhost:9090/api/v1/rules

# Test alert rule manually in Prometheus
# Go to: http://localhost:9090/graph
# Query: rate(bot_gateway_errors_total[5m]) > 1

# Check Alertmanager config
docker-compose exec alertmanager amtool check-config /etc/alertmanager/alertmanager.yml

# Reload Alertmanager config
curl -X POST http://localhost:9093/-/reload
```

---

#### 4. High Memory Usage in Prometheus

**Problem:** Prometheus consuming too much memory

**Solution:**
```bash
# Reduce retention period (default 30d)
# Edit docker-compose.monitoring.yml:
command:
  - '--storage.tsdb.retention.time=7d'  # Changed from 30d

# Reduce scrape frequency
# Edit monitoring/prometheus/prometheus.yml:
global:
  scrape_interval: 30s  # Changed from 15s

docker-compose restart prometheus
```

---

#### 5. Grafana Dashboards Not Loading

**Problem:** Dashboards empty or not visible

**Solution:**
```bash
# Check provisioning directory mounted
docker-compose exec grafana ls -la /etc/grafana/provisioning/dashboards

# Verify datasource configured
curl http://admin:admin@localhost:3000/api/datasources

# Restart Grafana
docker-compose restart grafana

# Check Grafana logs
docker-compose logs grafana | grep provisioning
```

---

### Performance Tuning

#### Prometheus

```yaml
# Optimize for high-cardinality metrics
global:
  scrape_interval: 15s
  evaluation_interval: 15s

# Limit series
--storage.tsdb.max-block-duration=2h
--storage.tsdb.min-block-duration=2h
```

#### Jaeger

```yaml
# Use Elasticsearch for production
environment:
  - SPAN_STORAGE_TYPE=elasticsearch
  - ES_SERVER_URLS=http://elasticsearch:9200
```

---

## 📚 Additional Resources

### Prometheus
- [Query Language (PromQL)](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Recording Rules](https://prometheus.io/docs/prometheus/latest/configuration/recording_rules/)
- [Best Practices](https://prometheus.io/docs/practices/naming/)

### Grafana
- [Dashboard Best Practices](https://grafana.com/docs/grafana/latest/best-practices/)
- [Variables](https://grafana.com/docs/grafana/latest/variables/)
- [Templating](https://grafana.com/docs/grafana/latest/dashboards/variables/)

### Jaeger
- [Architecture](https://www.jaegertracing.io/docs/latest/architecture/)
- [Client Libraries](https://www.jaegertracing.io/docs/latest/client-libraries/)
- [Sampling](https://www.jaegertracing.io/docs/latest/sampling/)

### OpenTelemetry
- [Python SDK](https://opentelemetry.io/docs/instrumentation/python/)
- [Instrumentation](https://opentelemetry.io/docs/instrumentation/python/automatic/)

---

## 🎓 Best Practices

1. **Use meaningful metric names** - Follow Prometheus naming conventions
2. **Add labels sparingly** - High cardinality kills performance
3. **Set appropriate retention** - Balance storage vs history needs
4. **Create actionable alerts** - Only alert on issues requiring human intervention
5. **Use dashboards for exploration** - Not for monitoring (use alerts)
6. **Trace critical paths** - Don't trace everything, be selective
7. **Monitor the monitors** - Set up Prometheus/Grafana/Jaeger health checks
8. **Document your metrics** - Explain what each metric means
9. **Review alerts regularly** - Remove noisy or useless alerts
10. **Test alert paths** - Ensure notifications reach the right people

---

**Last Updated:** 2025-10-07
**Version:** 1.0.0
**Sprint:** 19-22 Week 4
