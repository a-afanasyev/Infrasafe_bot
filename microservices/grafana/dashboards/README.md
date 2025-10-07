# Grafana Dashboards

This directory contains Grafana dashboard JSON configurations for monitoring microservices.

---

## 📊 Available Dashboards

### 1. Building Directory Monitoring
**File**: `building-directory.json`
**UID**: `building-directory-001`
**Tags**: `building-directory`, `request-service`, `microservices`

#### Panels Included

1. **Building Directory Request Rate** (Time Series)
   - Tracks requests per second by operation and status
   - Query: `rate(building_directory_requests_total[5m])`

2. **Response Time (p95/p99)** (Gauge)
   - Shows 95th and 99th percentile response times
   - Thresholds: Green <100ms, Yellow <500ms, Red >500ms
   - Query: `histogram_quantile(0.95, rate(building_directory_request_duration_seconds_bucket[5m]))`

3. **Cache Operations Distribution** (Pie Chart)
   - Visualizes cache hits, misses, sets, and errors
   - Query: `building_cache_operations_total`

4. **Cache Hit Rate** (Gauge)
   - Displays current cache hit rate percentage
   - Thresholds: Red <50%, Yellow <70%, Green ≥70%
   - Query: `rate(building_cache_operations_total{operation="hit"}[5m]) / rate(building_cache_operations_total[5m])`

5. **Validation Results** (Stacked Bars)
   - Shows validation outcomes over time
   - Query: `building_validations_total`

6. **Active Connections** (Time Series)
   - Tracks concurrent connections to Building Directory API
   - Query: `building_directory_active_connections`

7. **Error Rate by Type** (Time Series)
   - Monitors errors categorized by type (timeout, http_error, parse_error)
   - Query: `rate(building_directory_errors_total[5m])`

8. **Coordinate Extraction by Source** (Pie Chart)
   - Visualizes coordinate extraction success by source (nested, flat, missing)
   - Query: `coordinate_extractions_total`

#### Refresh Rate
- **Default**: 5 seconds
- **Time Range**: Last 15 minutes

---

## 🚀 Quick Start

### Step 1: Access Grafana

```bash
# Grafana is running on port 3000
open http://localhost:3000

# Default credentials (if not changed):
# Username: admin
# Password: admin
```

### Step 2: Import Dashboard

#### Method A: Via UI (Recommended)

1. Login to Grafana
2. Click **"+"** in the left sidebar
3. Select **"Import"**
4. Click **"Upload JSON file"**
5. Select `building-directory.json`
6. Click **"Import"**

#### Method B: Copy-Paste JSON

1. Login to Grafana
2. Click **"+"** → **"Import"**
3. Paste the contents of `building-directory.json` into the text box
4. Click **"Load"**
5. Select **Prometheus** as the data source
6. Click **"Import"**

#### Method C: Via API

```bash
# Using curl
curl -X POST http://localhost:3000/api/dashboards/db \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_API_KEY>" \
  -d @building-directory.json

# Or using HTTP file
http POST :3000/api/dashboards/db < building-directory.json
```

### Step 3: Configure Data Source

Ensure Prometheus data source is configured:

1. Go to **Configuration** → **Data Sources**
2. Click **"Add data source"**
3. Select **Prometheus**
4. Set URL to: `http://prometheus:9090` (internal Docker network)
5. Click **"Save & Test"**

---

## 📈 Using the Dashboard

### Key Metrics to Monitor

#### 1. **Request Rate**
- **Normal**: 0-100 req/s
- **High Load**: 100-1000 req/s
- **Critical**: >1000 req/s

#### 2. **Response Time**
- **Good**: p95 <100ms
- **Acceptable**: p95 <200ms
- **Poor**: p95 >500ms
- **Critical**: p95 >1s

#### 3. **Cache Hit Rate**
- **Target**: >70%
- **Warning**: 50-70%
- **Critical**: <50%

#### 4. **Error Rate**
- **Good**: <1%
- **Warning**: 1-5%
- **Critical**: >5%

---

## 🔔 Alert Configuration

### Recommended Alerts

#### 1. Low Cache Hit Rate
```yaml
alert: BuildingCacheHitRateLow
expr: |
  rate(building_cache_operations_total{operation="hit"}[5m])
  /
  rate(building_cache_operations_total[5m])
  < 0.5
for: 10m
severity: warning
annotations:
  summary: "Building Directory cache hit rate below 50%"
  description: "Cache hit rate is {{ $value | humanizePercentage }}, expected >70%"
```

#### 2. High Response Time
```yaml
alert: BuildingDirectorySlowResponses
expr: |
  histogram_quantile(0.95,
    rate(building_directory_request_duration_seconds_bucket[5m])
  ) > 1.0
for: 5m
severity: critical
annotations:
  summary: "Building Directory p95 response time >1s"
  description: "Current p95: {{ $value | humanizeDuration }}"
```

#### 3. High Error Rate
```yaml
alert: BuildingDirectoryHighErrorRate
expr: |
  rate(building_directory_errors_total[5m])
  /
  rate(building_directory_requests_total[5m])
  > 0.05
for: 5m
severity: critical
annotations:
  summary: "Building Directory error rate >5%"
  description: "Current error rate: {{ $value | humanizePercentage }}"
```

#### 4. Validation Failures Spike
```yaml
alert: BuildingValidationFailuresHigh
expr: |
  rate(building_validations_total{result!="valid"}[5m])
  /
  rate(building_validations_total[5m])
  > 0.10
for: 10m
severity: warning
annotations:
  summary: "Building validation failure rate >10%"
  description: "Check building data quality"
```

---

## 🛠️ Customization

### Changing Refresh Rate

Edit the `refresh` field in the JSON:
```json
{
  "refresh": "5s"  // Options: "5s", "10s", "30s", "1m", "5m"
}
```

### Modifying Thresholds

Update threshold values in panel configurations:
```json
{
  "thresholds": {
    "mode": "absolute",
    "steps": [
      {"color": "green", "value": null},
      {"color": "yellow", "value": 0.5},
      {"color": "red", "value": 0.7}
    ]
  }
}
```

### Adding Variables

Add template variables for filtering:
```json
{
  "templating": {
    "list": [
      {
        "name": "operation",
        "type": "query",
        "query": "label_values(building_directory_requests_total, operation)"
      }
    ]
  }
}
```

---

## 📖 Troubleshooting

### Dashboard Not Loading

**Issue**: Dashboard shows "No Data"

**Solutions**:
1. Check Prometheus is running: `docker-compose ps prometheus`
2. Verify data source: Configuration → Data Sources → Test
3. Check metrics are being collected: `curl http://localhost:8003/metrics | grep building`
4. Verify time range is appropriate (last 15 minutes)

### Metrics Not Showing

**Issue**: Specific panels show no data

**Solutions**:
1. Check metric exists: `curl http://localhost:9090/api/v1/label/__name__/values`
2. Verify query syntax in Prometheus: `http://localhost:9090/graph`
3. Check for data in selected time range
4. Review Request Service logs for errors

### Incorrect Values

**Issue**: Metrics show unexpected values

**Solutions**:
1. Verify rate() function time range matches refresh rate
2. Check for counter resets (service restarts)
3. Review metric labels are correct
4. Validate calculation logic in PromQL queries

---

## 🔗 Related Documentation

- [Prometheus Metrics Documentation](../request_service/BUILDING_DIRECTORY_METRICS_CACHING_REPORT.md)
- [Grafana Official Docs](https://grafana.com/docs/)
- [Prometheus Query Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/)
- [Building Directory Client](../request_service/app/clients/building_directory_client.py)

---

## 📝 Dashboard Maintenance

### Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-10-07 | Initial dashboard with 8 panels |

### Update Procedure

1. Export current dashboard from Grafana UI
2. Save JSON to this directory
3. Update version number and changelog
4. Commit to repository
5. Document breaking changes

---

**Last Updated**: October 7, 2025
**Maintainer**: DevOps Team
**Contact**: See project documentation
