# Geocoding API Documentation

## Overview

Geocoding API provides REST endpoints for address-to-coordinates and coordinates-to-address conversion using Google Maps and Yandex Maps providers with automatic fallback.

## Base URL

```
http://localhost:8003/api/v1/geocoding
```

## Authentication

All endpoints require tenant authentication via `X-Tenant-ID` header.

## Endpoints

### 1. Forward Geocoding (Address → Coordinates)

Convert address to geographic coordinates.

**Endpoint:** `POST /api/v1/geocoding/forward`

**Request:**
```json
{
  "address": "улица Пушкина 10, Ташкент",
  "provider": "auto"  // Optional: "auto", "google_maps", "yandex_maps"
}
```

**Response (200 OK):**
```json
{
  "latitude": 41.311081,
  "longitude": 69.240562,
  "formatted_address": "улица Пушкина 10, Ташкент, Узбекистан",
  "provider": "google_maps"
}
```

**cURL Example:**
```bash
curl -X POST "http://localhost:8003/api/v1/geocoding/forward" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: uk_company_1" \
  -d '{
    "address": "улица Пушкина 10, Ташкент",
    "provider": "auto"
  }'
```

---

### 2. Reverse Geocoding (Coordinates → Address)

Convert geographic coordinates to address.

**Endpoint:** `POST /api/v1/geocoding/reverse`

**Request:**
```json
{
  "latitude": 41.311081,
  "longitude": 69.240562,
  "provider": "auto"  // Optional: "auto", "google_maps", "yandex_maps"
}
```

**Response (200 OK):**
```json
{
  "formatted_address": "улица Пушкина 10, Ташкент, Узбекистан",
  "street": "улица Пушкина",
  "house_number": "10",
  "city": "Ташкент",
  "postal_code": "100000",
  "country": "Узбекистан",
  "provider": "google_maps"
}
```

**cURL Example:**
```bash
curl -X POST "http://localhost:8003/api/v1/geocoding/reverse" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: uk_company_1" \
  -d '{
    "latitude": 41.311081,
    "longitude": 69.240562,
    "provider": "auto"
  }'
```

---

### 3. Provider Health Check

Check health status of all geocoding providers.

**Endpoint:** `GET /api/v1/geocoding/health`

**Response (200 OK):**
```json
{
  "google_maps": {
    "healthy": true,
    "last_check": "2025-10-07T18:30:00Z",
    "error": null
  },
  "yandex_maps": {
    "healthy": false,
    "last_check": "2025-10-07T18:29:45Z",
    "error": "API key invalid"
  }
}
```

**cURL Example:**
```bash
curl -X GET "http://localhost:8003/api/v1/geocoding/health" \
  -H "X-Tenant-ID: uk_company_1"
```

---

## Provider Selection

The `provider` parameter supports three values:

- **`auto`** (default): Automatic provider selection with fallback
  - Tries Google Maps first
  - Falls back to Yandex Maps if Google fails

- **`google_maps`**: Force use Google Maps API
  - Higher accuracy for international addresses
  - Requires valid Google Maps API key

- **`yandex_maps`**: Force use Yandex Maps API
  - Better coverage for CIS countries
  - Requires valid Yandex Maps API key

## Error Responses

### 404 Not Found
Address or coordinates not found.

```json
{
  "detail": "Address not found: invalid address"
}
```

### 422 Validation Error
Invalid request parameters.

```json
{
  "error": "Validation Error",
  "detail": [
    {
      "loc": ["body", "latitude"],
      "msg": "ensure this value is greater than or equal to -90",
      "type": "value_error.number.not_ge"
    }
  ]
}
```

### 500 Internal Server Error
Geocoding operation failed.

```json
{
  "detail": "Geocoding failed: All providers unavailable"
}
```

---

## Configuration

Required environment variables in `.env`:

```bash
# Google Maps API Key
GOOGLE_MAPS_API_KEY=your_google_maps_api_key

# Yandex Maps API Key (optional)
YANDEX_MAPS_API_KEY=your_yandex_maps_api_key

# Tenant ID
MANAGEMENT_COMPANY_ID=uk_company_1
```

---

## Usage Examples

### Python (requests)

```python
import requests

BASE_URL = "http://localhost:8003/api/v1/geocoding"
HEADERS = {
    "Content-Type": "application/json",
    "X-Tenant-ID": "uk_company_1"
}

# Forward geocoding
response = requests.post(
    f"{BASE_URL}/forward",
    headers=HEADERS,
    json={
        "address": "улица Пушкина 10, Ташкент",
        "provider": "auto"
    }
)
coordinates = response.json()
print(f"Latitude: {coordinates['latitude']}")
print(f"Longitude: {coordinates['longitude']}")

# Reverse geocoding
response = requests.post(
    f"{BASE_URL}/reverse",
    headers=HEADERS,
    json={
        "latitude": 41.311081,
        "longitude": 69.240562,
        "provider": "auto"
    }
)
address = response.json()
print(f"Address: {address['formatted_address']}")
```

### JavaScript (fetch)

```javascript
const BASE_URL = "http://localhost:8003/api/v1/geocoding";
const headers = {
  "Content-Type": "application/json",
  "X-Tenant-ID": "uk_company_1"
};

// Forward geocoding
const forwardGeocode = async (address) => {
  const response = await fetch(`${BASE_URL}/forward`, {
    method: "POST",
    headers: headers,
    body: JSON.stringify({
      address: address,
      provider: "auto"
    })
  });
  return await response.json();
};

// Reverse geocoding
const reverseGeocode = async (lat, lon) => {
  const response = await fetch(`${BASE_URL}/reverse`, {
    method: "POST",
    headers: headers,
    body: JSON.stringify({
      latitude: lat,
      longitude: lon,
      provider: "auto"
    })
  });
  return await response.json();
};

// Usage
const coords = await forwardGeocode("улица Пушкина 10, Ташкент");
console.log(`Coordinates: ${coords.latitude}, ${coords.longitude}`);

const address = await reverseGeocode(41.311081, 69.240562);
console.log(`Address: ${address.formatted_address}`);
```

---

## Interactive API Documentation

When running in development mode, access interactive API docs at:

- **Swagger UI**: http://localhost:8003/docs
- **ReDoc**: http://localhost:8003/redoc

---

## Features

✅ **Multi-provider support** - Google Maps and Yandex Maps
✅ **Automatic fallback** - Seamless switching on provider failure
✅ **Tenant isolation** - Multi-tenant support via headers
✅ **Health monitoring** - Provider health status endpoint
✅ **Structured responses** - Pydantic models with validation
✅ **Full documentation** - OpenAPI/Swagger integration
✅ **Error handling** - Comprehensive error responses

---

## Architecture

```
┌─────────────────┐
│   REST Client   │
└────────┬────────┘
         │ HTTP Request
         ↓
┌─────────────────────────┐
│   Geocoding Router      │
│  /api/v1/geocoding/*    │
└────────┬────────────────┘
         │
         ↓
┌─────────────────────────┐
│  GeocodingService       │
│  - Provider selection   │
│  - Fallback logic       │
└────────┬────────────────┘
         │
    ┌────┴─────┐
    ↓          ↓
┌────────┐  ┌────────┐
│ Google │  │ Yandex │
│  Maps  │  │  Maps  │
└────────┘  └────────┘
```

---

## Support

For issues or questions, see:
- Integration Service documentation: `/microservices/integration_service/README.md`
- API endpoints: http://localhost:8003/docs (when running)
