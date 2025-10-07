# Integration Service - API Documentation

**Version**: 1.0.0
**Base URL**: `http://localhost:8009/api/v1`
**Protocol**: HTTP/REST
**Authentication**: Service-to-Service Token + Tenant ID

---

## 📋 Table of Contents

1. [Authentication](#authentication)
2. [Common Headers](#common-headers)
3. [Google Sheets API](#google-sheets-api)
4. [Geocoding API](#geocoding-api)
5. [Building Directory API](#building-directory-api)
6. [Health & Monitoring](#health--monitoring)
7. [Error Codes](#error-codes)
8. [Rate Limiting](#rate-limiting)
9. [Examples](#examples)

---

## 🔐 Authentication

### Required Headers

All API requests must include:

```http
X-Management-Company-ID: <tenant_id>
X-Request-ID: <unique_request_id>  (optional but recommended)
```

### Service Token (Optional)

For service-to-service calls:

```http
X-Service-Token: <service_api_key>
```

---

## 📌 Common Headers

| Header | Required | Description |
|--------|----------|-------------|
| `Content-Type` | Yes | `application/json` |
| `X-Management-Company-ID` | Yes | Tenant identifier for multi-tenancy |
| `X-Request-ID` | No | Unique request ID for tracing |
| `X-Service-Token` | No | Service authentication token |
| `Accept` | No | Response format (default: `application/json`) |

---

## 📊 Google Sheets API

### 1. Read from Spreadsheet

**Endpoint**: `POST /sheets/read`

**Description**: Read data from Google Sheets range

**Request Body**:
```json
{
  "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
  "range_name": "Sheet1!A1:C10",
  "value_render_option": "FORMATTED_VALUE"
}
```

**Parameters**:
- `spreadsheet_id` (string, required): Google Spreadsheet ID
- `range_name` (string, required): Range in A1 notation (e.g., "Sheet1!A1:C10")
- `value_render_option` (string, optional): How values should be rendered
  - `FORMATTED_VALUE` (default): Formatted values
  - `UNFORMATTED_VALUE`: Raw values
  - `FORMULA`: Formula strings

**Response** (200 OK):
```json
{
  "success": true,
  "values": [
    ["Name", "Email", "Phone"],
    ["John Doe", "john@example.com", "+1234567890"],
    ["Jane Smith", "jane@example.com", "+0987654321"]
  ],
  "row_count": 3,
  "column_count": 3,
  "range_name": "Sheet1!A1:C10"
}
```

**cURL Example**:
```bash
curl -X POST http://localhost:8009/api/v1/sheets/read \
  -H "Content-Type: application/json" \
  -H "X-Management-Company-ID: company-123" \
  -d '{
    "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
    "range_name": "Sheet1!A1:C10"
  }'
```

---

### 2. Write to Spreadsheet

**Endpoint**: `POST /sheets/write`

**Description**: Write data to Google Sheets range

**Request Body**:
```json
{
  "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
  "range_name": "Sheet1!A1:C2",
  "values": [
    ["Name", "Email", "Phone"],
    ["New User", "new@example.com", "+1111111111"]
  ],
  "value_input_option": "USER_ENTERED"
}
```

**Parameters**:
- `spreadsheet_id` (string, required): Google Spreadsheet ID
- `range_name` (string, required): Target range
- `values` (array, required): 2D array of values to write
- `value_input_option` (string, optional): How values should be interpreted
  - `USER_ENTERED` (default): Parse as if user typed (formulas work)
  - `RAW`: Store values as-is

**Response** (200 OK):
```json
{
  "success": true,
  "updated_cells": 6,
  "updated_rows": 2,
  "updated_columns": 3,
  "range_name": "Sheet1!A1:C2"
}
```

---

### 3. Append Rows

**Endpoint**: `POST /sheets/append`

**Description**: Append rows to the end of a spreadsheet range

**Request Body**:
```json
{
  "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
  "range_name": "Sheet1!A:C",
  "values": [
    ["Appended User", "append@example.com", "+2222222222"]
  ],
  "value_input_option": "USER_ENTERED"
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "updated_rows": 1,
  "updated_cells": 3,
  "appended_range": "Sheet1!A11:C11"
}
```

---

### 4. Batch Operations

**Endpoint**: `POST /sheets/batch`

**Description**: Perform multiple operations in a single request

**Request Body**:
```json
{
  "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
  "operations": [
    {
      "range": "Sheet1!A1:C1",
      "values": [["Name", "Email", "Phone"]]
    },
    {
      "range": "Sheet1!A2:C2",
      "values": [["User 1", "user1@test.com", "+123"]]
    }
  ],
  "value_input_option": "USER_ENTERED"
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "operations_count": 2,
  "total_updated_cells": 6,
  "results": [
    {"range": "Sheet1!A1:C1", "updated_cells": 3},
    {"range": "Sheet1!A2:C2", "updated_cells": 3}
  ]
}
```

---

### 5. Get Spreadsheet Metadata

**Endpoint**: `GET /sheets/metadata/{spreadsheet_id}`

**Description**: Get spreadsheet metadata (title, worksheets, etc.)

**Response** (200 OK):
```json
{
  "success": true,
  "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
  "title": "My Spreadsheet",
  "worksheets": [
    {"id": 0, "title": "Sheet1", "row_count": 1000, "column_count": 26},
    {"id": 1, "title": "Sheet2", "row_count": 500, "column_count": 10}
  ],
  "created_time": "2025-01-01T00:00:00Z",
  "modified_time": "2025-10-07T12:00:00Z"
}
```

---

### 6. Health Check

**Endpoint**: `GET /sheets/health`

**Description**: Check Google Sheets adapter health

**Response** (200 OK):
```json
{
  "status": "healthy",
  "service": "google_sheets",
  "rate_limit_remaining": 95,
  "rate_limit_reset_in": 45.2
}
```

---

## 🗺️ Geocoding API

### 1. Forward Geocoding (Address → Coordinates)

**Endpoint**: `POST /geocoding/geocode`

**Description**: Convert address to geographic coordinates

**Request Body**:
```json
{
  "address": "Ташкент, улица Амира Темура, 42",
  "language": "ru",
  "region": "UZ",
  "provider": "auto"
}
```

**Parameters**:
- `address` (string, required): Address to geocode
- `language` (string, optional): Language code (default: "ru")
- `region` (string, optional): Region bias (default: "UZ")
- `provider` (string, optional): Provider selection
  - `auto` (default): Try Google first, fallback to Yandex
  - `google`: Use Google Maps only
  - `yandex`: Use Yandex Maps only

**Response** (200 OK):
```json
{
  "success": true,
  "address": "улица Амира Темура, 42, Ташкент, Узбекистан",
  "latitude": 41.311081,
  "longitude": 69.240562,
  "formatted_address": "улица Амира Темура, 42, Ташкент 100000, Узбекистан",
  "confidence": 0.9,
  "location_type": "ROOFTOP",
  "place_id": "ChIJtest123",
  "address_components": [
    {"long_name": "42", "short_name": "42", "types": ["street_number"]},
    {"long_name": "улица Амира Темура", "short_name": "ул. Амира Темура", "types": ["route"]},
    {"long_name": "Ташкент", "short_name": "Ташкент", "types": ["locality"]}
  ],
  "used_provider": "google",
  "attempted_providers": ["google"],
  "response_time_ms": 150
}
```

**Confidence Levels**:
- `1.0`: ROOFTOP (highest accuracy)
- `0.9`: RANGE_INTERPOLATED (very accurate)
- `0.7`: GEOMETRIC_CENTER (good accuracy)
- `0.5`: APPROXIMATE (low accuracy)

---

### 2. Reverse Geocoding (Coordinates → Address)

**Endpoint**: `POST /geocoding/reverse`

**Description**: Convert coordinates to address

**Request Body**:
```json
{
  "latitude": 41.311081,
  "longitude": 69.240562,
  "language": "ru",
  "provider": "auto"
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "address": "улица Амира Темура, 42, Ташкент 100000, Узбекистан",
  "latitude": 41.311081,
  "longitude": 69.240562,
  "formatted_address": "улица Амира Темура, 42, Ташкент 100000, Узбекистан",
  "place_id": "ChIJtest123",
  "address_components": [...],
  "used_provider": "google",
  "response_time_ms": 120
}
```

---

### 3. Calculate Distance

**Endpoint**: `POST /geocoding/distance`

**Description**: Calculate distance between two points using Haversine formula

**Request Body**:
```json
{
  "origin_lat": 41.311081,
  "origin_lng": 69.240562,
  "dest_lat": 41.299496,
  "dest_lng": 69.239663
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "distance_meters": 1289.7,
  "distance_km": 1.29,
  "origin": {
    "latitude": 41.311081,
    "longitude": 69.240562
  },
  "destination": {
    "latitude": 41.299496,
    "longitude": 69.239663
  }
}
```

---

### 4. Batch Geocoding

**Endpoint**: `POST /geocoding/batch`

**Description**: Geocode multiple addresses in one request

**Request Body**:
```json
{
  "addresses": [
    "Ташкент, улица Амира Темура, 42",
    "Ташкент, площадь Независимости, 1"
  ],
  "language": "ru",
  "provider": "auto"
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "results": [
    {
      "address": "Ташкент, улица Амира Темура, 42",
      "latitude": 41.311081,
      "longitude": 69.240562,
      "success": true
    },
    {
      "address": "Ташкент, площадь Независимости, 1",
      "latitude": 41.313611,
      "longitude": 69.279722,
      "success": true
    }
  ],
  "success_count": 2,
  "failure_count": 0
}
```

---

### 5. Geocoding Health Check

**Endpoint**: `GET /geocoding/health`

**Description**: Check geocoding service health

**Response** (200 OK):
```json
{
  "status": "healthy",
  "providers": {
    "google": {
      "healthy": true,
      "rate_limit_remaining": 45,
      "last_error": null
    },
    "yandex": {
      "healthy": true,
      "rate_limit_remaining": 48,
      "last_error": null
    }
  }
}
```

---

## 🏢 Building Directory API

### 1. Get Building by ID

**Endpoint**: `GET /buildings/{building_id}`

**Description**: Get building details by ID

**Response** (200 OK):
```json
{
  "success": true,
  "building": {
    "id": "building-123",
    "name": "Residential Complex Amir Temur",
    "address": "улица Амира Темура, 42, Ташкент",
    "coordinates": {
      "latitude": 41.311081,
      "longitude": 69.240562
    },
    "type": "residential",
    "floors": 12,
    "apartments": 96,
    "year_built": 2018
  },
  "cached": false,
  "response_time_ms": 150
}
```

---

### 2. Search Buildings

**Endpoint**: `GET /buildings/search`

**Description**: Search buildings by query

**Query Parameters**:
- `q` (string, required): Search query
- `limit` (int, optional): Results per page (default: 10, max: 100)
- `offset` (int, optional): Pagination offset (default: 0)
- `city` (string, optional): Filter by city
- `type` (string, optional): Filter by building type

**Example**: `GET /buildings/search?q=Amir+Temur&limit=10&city=Tashkent`

**Response** (200 OK):
```json
{
  "success": true,
  "results": [
    {
      "id": "building-123",
      "name": "Residential Complex Amir Temur",
      "address": "улица Амира Темура, 42",
      "score": 0.95
    },
    {
      "id": "building-124",
      "name": "Amir Temur Plaza",
      "address": "улица Амира Темура, 108",
      "score": 0.87
    }
  ],
  "total": 2,
  "limit": 10,
  "offset": 0,
  "has_more": false
}
```

---

### 3. Validate Building

**Endpoint**: `POST /buildings/validate`

**Description**: Validate building address and coordinates

**Request Body**:
```json
{
  "building_id": "building-123",
  "address": "улица Амира Темура, 42, Ташкент",
  "coordinates": {
    "latitude": 41.311081,
    "longitude": 69.240562
  }
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "valid": true,
  "building_id": "building-123",
  "confidence": 0.95,
  "validation_details": {
    "address_match": true,
    "coordinates_match": true,
    "distance_meters": 0.5
  }
}
```

---

### 4. Extract Coordinates

**Endpoint**: `POST /buildings/extract-coordinates`

**Description**: Extract coordinates from building address

**Request Body**:
```json
{
  "address": "улица Амира Темура, 42, Ташкент"
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "coordinates": {
    "latitude": 41.311081,
    "longitude": 69.240562
  },
  "confidence": 0.9,
  "source": "building_directory"
}
```

---

## 🏥 Health & Monitoring

### 1. Health Check

**Endpoint**: `GET /health`

**Description**: Basic health check

**Response** (200 OK):
```json
{
  "status": "healthy",
  "service": "Integration Service",
  "version": "1.0.0",
  "timestamp": "2025-10-07T12:00:00Z",
  "uptime_seconds": 3600
}
```

---

### 2. Detailed Health Check

**Endpoint**: `GET /health/detailed`

**Description**: Detailed health check with all adapters

**Response** (200 OK):
```json
{
  "status": "healthy",
  "service": "Integration Service",
  "version": "1.0.0",
  "timestamp": "2025-10-07T12:00:00Z",
  "adapters": {
    "google_sheets": {
      "status": "healthy",
      "rate_limit_remaining": 95,
      "last_request": "2025-10-07T11:59:30Z"
    },
    "google_maps": {
      "status": "healthy",
      "rate_limit_remaining": 45,
      "last_request": "2025-10-07T11:58:00Z"
    },
    "yandex_maps": {
      "status": "healthy",
      "rate_limit_remaining": 50,
      "last_request": null
    },
    "building_directory": {
      "status": "healthy",
      "rate_limit_remaining": 98,
      "cache_hit_rate": 0.75
    }
  },
  "database": {
    "status": "healthy",
    "connection_pool": {
      "size": 10,
      "used": 2,
      "available": 8
    }
  },
  "redis": {
    "status": "healthy",
    "connected": true,
    "memory_used_mb": 45.2
  }
}
```

---

### 3. Prometheus Metrics

**Endpoint**: `GET /metrics`

**Description**: Prometheus metrics endpoint

**Response** (200 OK):
```
# HELP integration_requests_total Total API requests
# TYPE integration_requests_total counter
integration_requests_total{service="google_sheets",operation="read",status="success"} 150

# HELP integration_request_duration_seconds Request duration
# TYPE integration_request_duration_seconds histogram
integration_request_duration_seconds_bucket{service="google_maps",operation="geocode",le="0.1"} 45
...
```

---

## ⚠️ Error Codes

### Standard Error Response

```json
{
  "success": false,
  "error": {
    "code": "INVALID_REQUEST",
    "message": "Missing required parameter: address",
    "details": {
      "parameter": "address",
      "expected": "string",
      "received": "null"
    }
  },
  "request_id": "req-123",
  "timestamp": "2025-10-07T12:00:00Z"
}
```

### Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `INVALID_REQUEST` | 400 | Invalid request parameters |
| `UNAUTHORIZED` | 401 | Missing or invalid authentication |
| `FORBIDDEN` | 403 | Insufficient permissions |
| `NOT_FOUND` | 404 | Resource not found |
| `RATE_LIMIT_EXCEEDED` | 429 | Rate limit exceeded |
| `INTERNAL_ERROR` | 500 | Internal server error |
| `SERVICE_UNAVAILABLE` | 503 | External service unavailable |
| `GATEWAY_TIMEOUT` | 504 | External service timeout |

---

## 🚦 Rate Limiting

### Rate Limits

| Service | Limit | Window |
|---------|-------|--------|
| Google Sheets | 100 req/min | 60 seconds |
| Google Maps | 50 req/min | 60 seconds |
| Yandex Maps | 50 req/min | 60 seconds |
| Building Directory | 100 req/min | 60 seconds |

### Rate Limit Headers

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1696684800
```

### Rate Limit Error

```json
{
  "success": false,
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit exceeded for google_sheets",
    "details": {
      "limit": 100,
      "window_seconds": 60,
      "reset_at": "2025-10-07T12:01:00Z",
      "retry_after_seconds": 45.2
    }
  }
}
```

---

## 📝 Examples

### Python Example

```python
import httpx

async def geocode_address(address: str) -> dict:
    """Geocode address using Integration Service"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://integration-service:8009/api/v1/geocoding/geocode",
            json={
                "address": address,
                "language": "ru",
                "region": "UZ"
            },
            headers={
                "X-Management-Company-ID": "company-123",
                "X-Request-ID": "req-456"
            }
        )
        return response.json()

# Usage
result = await geocode_address("Ташкент, улица Амира Темура, 42")
print(f"Coordinates: {result['latitude']}, {result['longitude']}")
```

### JavaScript Example

```javascript
async function readSpreadsheet(spreadsheetId, range) {
  const response = await fetch('http://integration-service:8009/api/v1/sheets/read', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Management-Company-ID': 'company-123'
    },
    body: JSON.stringify({
      spreadsheet_id: spreadsheetId,
      range_name: range
    })
  });

  return await response.json();
}

// Usage
const data = await readSpreadsheet('1BxiMVs...', 'Sheet1!A1:C10');
console.log('Rows:', data.values.length);
```

---

**API Version**: 1.0.0
**Last Updated**: October 7, 2025
**Status**: ✅ Production Ready
