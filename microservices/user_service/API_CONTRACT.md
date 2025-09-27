# User Service REST API Contract

**Version**: 1.0
**Base URL**: `http://user-service:8001/api/v1`
**Service**: User Service
**For Integration With**: Auth Service, Media Service, Request Service

## Authentication

All endpoints require either:
- **Service Token**: `Authorization: Bearer <service_token>` (for inter-service calls)
- **User JWT**: `Authorization: Bearer <user_jwt>` (for user-facing calls)

## Core User Endpoints

### GET /users/by-telegram/{telegram_id}
**Purpose**: Get user by Telegram ID (primary Auth Service integration point)

**Request**:
```http
GET /api/v1/users/by-telegram/123456789
Authorization: Bearer <service_token>
```

**Response** (200 OK):
```json
{
  "id": 1,
  "telegram_id": 123456789,
  "username": "john_doe",
  "first_name": "John",
  "last_name": "Doe",
  "phone": "+1234567890",
  "email": "john@example.com",
  "language_code": "ru",
  "status": "approved",
  "is_active": true,
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T12:00:00Z",
  "profile": {
    "id": 1,
    "user_id": 1,
    "birth_date": "1990-01-01",
    "passport_series": "AA",
    "passport_number": "1234567",
    "home_address": "123 Main St",
    "apartment_address": null,
    "yard_address": null,
    "address_type": "home",
    "specialization": ["electrical", "plumbing"],
    "bio": "Experienced electrician",
    "avatar_url": "https://example.com/avatar.jpg",
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T12:00:00Z"
  },
  "roles": [
    {
      "id": 1,
      "role_key": "executor",
      "role_data": {"specializations": ["electrical"]},
      "is_active_role": true,
      "assigned_at": "2024-01-01T00:00:00Z",
      "assigned_by": 1,
      "expires_at": null,
      "is_active": true
    }
  ],
  "verification_status": "approved",
  "document_count": 3,
  "access_rights": {
    "access_level": "standard",
    "service_permissions": {
      "can_create_requests": true,
      "can_view_all_requests": false,
      "can_manage_users": false,
      "can_access_analytics": false,
      "can_manage_shifts": false,
      "can_export_data": false
    },
    "building_access": ["building_a"],
    "is_active": true
  }
}
```

**Response** (404 Not Found):
```json
{
  "detail": "User not found"
}
```

### GET /users/{user_id}
**Purpose**: Get user by ID

**Request**:
```http
GET /api/v1/users/1
Authorization: Bearer <service_token>
```

**Response**: Same as `/users/by-telegram/{telegram_id}`

### POST /users
**Purpose**: Create new user

**Request**:
```http
POST /api/v1/users
Authorization: Bearer <service_token>
Content-Type: application/json

{
  "telegram_id": 123456789,
  "username": "john_doe",
  "first_name": "John",
  "last_name": "Doe",
  "phone": "+1234567890",
  "email": "john@example.com",
  "language_code": "ru"
}
```

**Response** (201 Created): Full user object (same format as GET)

### PATCH /users/{user_id}
**Purpose**: Update user information

**Request**:
```http
PATCH /api/v1/users/1
Authorization: Bearer <service_token>
Content-Type: application/json

{
  "status": "approved",
  "is_active": true
}
```

**Response** (200 OK): Updated user object

## Role Management Endpoints

### GET /users/{user_id}/roles
**Purpose**: Get user roles (for Auth Service permission checks)

**Request**:
```http
GET /api/v1/users/1/roles
Authorization: Bearer <service_token>
```

**Response** (200 OK):
```json
[
  {
    "id": 1,
    "role_key": "executor",
    "role_data": {"specializations": ["electrical"]},
    "is_active_role": true,
    "assigned_at": "2024-01-01T00:00:00Z",
    "assigned_by": 1,
    "expires_at": null,
    "is_active": true
  }
]
```

### POST /users/{user_id}/roles
**Purpose**: Assign role to user

**Request**:
```http
POST /api/v1/users/1/roles
Authorization: Bearer <service_token>
Content-Type: application/json

{
  "role_key": "manager",
  "role_data": {"department": "maintenance"},
  "expires_at": null
}
```

**Response** (201 Created): Created role object

## Service Integration Endpoints

### POST /internal/validate-service-token
**Purpose**: Validate service-to-service token

**Request**:
```http
POST /api/v1/internal/validate-service-token
Content-Type: application/json

{
  "token": "service_token_here",
  "service_name": "auth-service"
}
```

**Response** (200 OK):
```json
{
  "valid": true,
  "service_name": "auth-service",
  "permissions": ["read_users", "write_users"],
  "expires_at": "2024-12-31T23:59:59Z"
}
```

### GET /users/stats/overview
**Purpose**: Get user statistics (for Auth Service admin endpoints)

**Request**:
```http
GET /api/v1/users/stats/overview
Authorization: Bearer <service_token>
```

**Response** (200 OK):
```json
{
  "total_users": 150,
  "active_users": 120,
  "status_distribution": {
    "pending": 10,
    "approved": 120,
    "blocked": 15,
    "archived": 5
  },
  "role_distribution": {
    "applicant": 50,
    "executor": 70,
    "manager": 25,
    "admin": 5
  },
  "monthly_registrations": 12
}
```

## Error Responses

All endpoints may return these error responses:

### 400 Bad Request
```json
{
  "detail": "Validation error",
  "errors": [
    {
      "field": "telegram_id",
      "message": "Telegram ID must be positive"
    }
  ]
}
```

### 401 Unauthorized
```json
{
  "detail": "Authentication required"
}
```

### 403 Forbidden
```json
{
  "detail": "Insufficient permissions"
}
```

### 404 Not Found
```json
{
  "detail": "User not found"
}
```

### 500 Internal Server Error
```json
{
  "detail": "Internal server error",
  "service": "user-service"
}
```

## Data Types Reference

### User Status Values
- `pending` - Newly registered, awaiting verification
- `approved` - Verified and active
- `blocked` - Temporarily suspended
- `archived` - Permanently disabled

### Role Keys
- `applicant` - Can create requests
- `executor` - Can execute requests
- `manager` - Can manage requests and users
- `admin` - Full system access
- `superadmin` - Ultimate system access

### Address Types
- `home` - Home address
- `apartment` - Apartment building
- `yard` - Yard/courtyard area

### Verification Status
- `not_started` - No verification submitted
- `pending` - Documents submitted, awaiting review
- `approved` - Verification complete
- `rejected` - Verification failed
- `expired` - Verification expired, needs renewal

## Rate Limiting

- **Per Service**: 1000 requests/minute
- **Per Endpoint**: 100 requests/minute
- **Headers**: `X-RateLimit-Remaining`, `X-RateLimit-Reset`

## Pagination

List endpoints support pagination:

**Query Parameters**:
- `page` (default: 1)
- `page_size` (default: 50, max: 200)

**Response Headers**:
- `X-Total-Count`: Total number of items
- `X-Page-Count`: Total number of pages

## Service Discovery

**Health Check**: `GET /health`
**Service Info**: `GET /info`
**Metrics**: `GET /metrics` (Prometheus format)

## Example Integration Flows

### Auth Service Login Flow
1. `POST /api/v1/auth/login` (Auth Service)
2. `GET /api/v1/users/by-telegram/{id}` (User Service)
3. `POST /api/v1/sessions` (Auth Service)

### Permission Check Flow
1. `POST /api/v1/auth/check-permission` (Auth Service)
2. `GET /api/v1/users/{id}/roles` (User Service)
3. Return permission result

### User Registration Flow
1. `POST /api/v1/users` (User Service)
2. `POST /api/v1/users/{id}/roles` (User Service)
3. `POST /api/v1/auth/register-session` (Auth Service)