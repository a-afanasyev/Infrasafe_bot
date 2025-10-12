# 🔐 Auth Service API Reference

**Version**: 1.0.1
**Base URL**: `http://localhost:8001`
**Last Updated**: 4 October 2025

---

## 📋 Table of Contents

- [Authentication](#authentication)
- [Internal Service API](#internal-service-api)
- [Permissions & RBAC](#permissions--rbac)
- [Sessions](#sessions)
- [Rate Limiting](#rate-limiting)
- [Health & Monitoring](#health--monitoring)
- [Error Codes](#error-codes)
- [Authentication Flow](#authentication-flow)

---

## 🔑 Authentication

### POST `/api/v1/auth/login`

Authenticate user with Telegram ID and create a new session.

**Request Body**:
```json
{
  "telegram_id": 123456789,
  "username": "testuser",
  "device_info": {
    "device_type": "mobile",
    "platform": "iOS"
  }
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "message": "Login successful",
  "user_id": 42,
  "session": {
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "user_id": 42,
    "telegram_id": "123456789",
    "is_active": true,
    "expires_at": "2025-10-04T18:15:00Z",
    "refresh_expires_at": "2025-10-11T18:00:00Z",
    "device_info": {"device_type": "mobile", "platform": "iOS"},
    "ip_address": "172.20.0.5",
    "created_at": "2025-10-04T18:00:00Z",
    "last_activity": "2025-10-04T18:00:00Z"
  },
  "tokens": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "abc123def456...",
    "token_type": "bearer",
    "expires_in": 900,
    "session_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

**Errors**:
- `401 Unauthorized` - User not found
- `500 Internal Server Error` - Authentication failed

**Rate Limit**: 10 requests per minute per IP

**Notes**:
- Creates audit log entry for login attempt
- IP address and user agent captured automatically
- Access token expires in 15 minutes
- Refresh token expires in 7 days

---

### POST `/api/v1/auth/refresh`

Refresh access token using a valid refresh token.

**Request Body**:
```json
{
  "refresh_token": "abc123def456..."
}
```

**Response** (200 OK):
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "xyz789ghi012...",
  "token_type": "bearer",
  "expires_in": 900,
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Errors**:
- `401 Unauthorized` - Invalid or expired refresh token
- `401 Unauthorized` - Session inactive or not found

**Rate Limit**: 30 requests per minute per user

**Notes**:
- Both access and refresh tokens are rotated
- Old refresh token is invalidated
- Session must be active

---

### POST `/api/v1/auth/logout`

Logout user and invalidate session(s).

**Request Headers**:
```
Authorization: Bearer <access_token>
```

**Request Body**:
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "all_sessions": false
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "message": "Logged out successfully"
}
```

**Logout from all sessions**:
```json
{
  "all_sessions": true
}
```

**Response**:
```json
{
  "success": true,
  "message": "Logged out from all sessions"
}
```

**Errors**:
- `400 Bad Request` - Session ID required (when all_sessions=false)
- `401 Unauthorized` - Authentication required (when all_sessions=true)
- `404 Not Found` - Session not found

**Rate Limit**: 10 requests per minute per user

---

### GET `/api/v1/auth/me`

Get current authenticated user information.

**Request Headers**:
```
Authorization: Bearer <access_token>
```

**Response** (200 OK):
```json
{
  "user_id": 42,
  "telegram_id": "123456789",
  "roles": ["executor", "manager"],
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "session_expires_at": "2025-10-04T18:15:00Z"
}
```

**Errors**:
- `401 Unauthorized` - Authentication required
- `401 Unauthorized` - Invalid token
- `401 Unauthorized` - Session expired

**Rate Limit**: 60 requests per minute per user

**Notes**:
- Updates session last_activity timestamp
- Returns roles for RBAC permission checking

---

### POST `/api/v1/auth/service-token` ❌ DISABLED

**Status**: `410 Gone` - Permanently disabled for security

Legacy service token endpoint. Use static API key authentication instead.

**Error Response**:
```json
{
  "detail": "Legacy service token endpoint disabled. Use static API key authentication instead."
}
```

---

## 🔧 Internal Service API

### POST `/api/v1/internal/validate-service-credentials`

Validate service credentials using HMAC-based authentication (Primary method).

**Request Headers**:
```
X-Service-Name: request-service
X-Service-API-Key: request-service-api-key-change-in-production
```

**Response** (200 OK):
```json
{
  "valid": true,
  "service_name": "request-service",
  "permissions": [
    "requests:read",
    "requests:write",
    "notifications:send"
  ],
  "expires_at": "2026-12-31T23:59:59Z"
}
```

**Response** (401 Unauthorized - Invalid credentials):
```json
{
  "valid": false,
  "service_name": null,
  "permissions": [],
  "error": "Invalid service credentials"
}
```

**Response** (403 Forbidden - Service revoked):
```json
{
  "valid": false,
  "service_name": "request-service",
  "permissions": [],
  "error": "Service has been revoked",
  "revoked_at": "2025-10-04T12:00:00Z",
  "revoked_by": "admin_123"
}
```

**Rate Limit**: 1000 requests per minute per service

**Security**:
- HMAC SHA-256 validation (no timing attacks)
- Redis-based revocation checking
- Complete audit trail in Redis

---

### POST `/api/v1/internal/validate-service-token`

Validate service token using JWT or API key (Legacy fallback with HMAC).

**Request Body**:
```json
{
  "token": "api-key-or-jwt-token",
  "service_name": "user-service"
}
```

**Response** (200 OK):
```json
{
  "valid": true,
  "service_name": "user-service",
  "permissions": [
    "users:read",
    "users:write",
    "users:validate"
  ],
  "expires_at": "2026-12-31T23:59:59Z"
}
```

**Errors**:
- `401 Unauthorized` - Invalid token
- `403 Forbidden` - Service revoked

**Rate Limit**: 1000 requests per minute per service

**Notes**:
- Falls back to HMAC validation for security
- Maintains backward compatibility
- Logs all validation attempts

---

### POST `/api/v1/internal/generate-service-token` ❌ DISABLED

**Status**: `410 Gone` - Permanently disabled

JWT self-minting disabled to prevent privilege escalation vulnerabilities.

**Error Response**:
```json
{
  "detail": "JWT self-minting disabled for security. Use static API keys configured in environment."
}
```

---

### POST `/api/v1/internal/revoke-service`

Revoke service access (Admin only).

**Request Headers**:
```
Authorization: Bearer <admin_access_token>
```

**Request Body**:
```json
{
  "service_name": "compromised-service",
  "reason": "Security breach detected"
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "service_name": "compromised-service",
  "revoked_at": "2025-10-04T18:00:00Z",
  "revoked_by": "admin_123",
  "reason": "Security breach detected"
}
```

**Errors**:
- `401 Unauthorized` - Admin authentication required
- `403 Forbidden` - Insufficient permissions
- `404 Not Found` - Service not found

**Rate Limit**: 10 requests per minute per admin

**Notes**:
- Immediate effect via Redis
- All future validation attempts will fail
- Audit log created

---

### POST `/api/v1/internal/restore-service`

Restore previously revoked service (Admin only).

**Request Headers**:
```
Authorization: Bearer <admin_access_token>
```

**Request Body**:
```json
{
  "service_name": "compromised-service"
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "service_name": "compromised-service",
  "restored_at": "2025-10-04T19:00:00Z",
  "restored_by": "admin_123"
}
```

**Errors**:
- `401 Unauthorized` - Admin authentication required
- `403 Forbidden` - Insufficient permissions
- `404 Not Found` - Service not found or not revoked

**Rate Limit**: 10 requests per minute per admin

---

### GET `/api/v1/internal/service-status`

Get overview of all services and their status (Admin only).

**Request Headers**:
```
Authorization: Bearer <admin_access_token>
```

**Response** (200 OK):
```json
{
  "services": {
    "request-service": {
      "permissions": ["requests:read", "requests:write"],
      "is_revoked": false,
      "last_used": "2025-10-04T18:01:32Z",
      "total_validations": 1523
    },
    "user-service": {
      "permissions": ["users:read", "users:write", "users:validate"],
      "is_revoked": false,
      "last_used": "2025-10-04T18:02:15Z",
      "total_validations": 2847
    },
    "compromised-service": {
      "permissions": [],
      "is_revoked": true,
      "revoked_at": "2025-10-04T12:00:00Z",
      "revoked_by": "admin_123",
      "reason": "Security breach"
    }
  },
  "total_services": 3,
  "active_services": 2,
  "revoked_services": 1
}
```

**Errors**:
- `401 Unauthorized` - Admin authentication required
- `403 Forbidden` - Insufficient permissions

**Rate Limit**: 30 requests per minute per admin

---

### GET `/api/v1/internal/auth-audit`

Get authentication audit logs (Admin only).

**Request Headers**:
```
Authorization: Bearer <admin_access_token>
```

**Query Parameters**:
- `service_name` (optional) - Filter by service
- `start_date` (optional) - ISO format datetime
- `end_date` (optional) - ISO format datetime
- `limit` (optional, default=100) - Max results
- `offset` (optional, default=0) - Pagination

**Response** (200 OK):
```json
{
  "logs": [
    {
      "timestamp": "2025-10-04T18:00:00Z",
      "service_name": "request-service",
      "event_type": "validation",
      "success": true,
      "ip_address": "172.20.0.5",
      "metadata": {"method": "hmac"}
    },
    {
      "timestamp": "2025-10-04T17:59:45Z",
      "service_name": "compromised-service",
      "event_type": "revocation",
      "success": true,
      "revoked_by": "admin_123",
      "reason": "Security breach"
    }
  ],
  "total": 2456,
  "limit": 100,
  "offset": 0
}
```

**Errors**:
- `401 Unauthorized` - Admin authentication required
- `403 Forbidden` - Insufficient permissions

**Rate Limit**: 30 requests per minute per admin

---

### GET `/api/v1/internal/user-stats`

Get user statistics (proxy to User Service).

**Request Headers**:
```
Authorization: Bearer <service_token>
```

**Response** (200 OK):
```json
{
  "total_users": 1523,
  "active_users": 1245,
  "users_by_role": {
    "admin": 5,
    "manager": 42,
    "executor": 856,
    "applicant": 620
  }
}
```

**Errors**:
- `401 Unauthorized` - Service authentication required
- `503 Service Unavailable` - User Service unavailable

**Rate Limit**: 60 requests per minute per service

---

## 👥 Permissions & RBAC

### GET `/api/v1/permissions`

List all permissions.

**Request Headers**:
```
Authorization: Bearer <access_token>
```

**Query Parameters**:
- `service_name` (optional) - Filter by service
- `is_active` (optional) - Filter by active status
- `limit` (optional, default=100)
- `offset` (optional, default=0)

**Response** (200 OK):
```json
{
  "permissions": [
    {
      "id": 1,
      "permission_key": "requests:read",
      "permission_name": "Read Requests",
      "description": "View request details",
      "service_name": "request-service",
      "resource_type": "request",
      "is_active": true,
      "is_system": true
    }
  ],
  "total": 45,
  "limit": 100,
  "offset": 0
}
```

**Errors**:
- `401 Unauthorized` - Authentication required

**Rate Limit**: 60 requests per minute per user

---

### POST `/api/v1/permissions`

Create new permission (Admin only).

**Request Headers**:
```
Authorization: Bearer <admin_access_token>
```

**Request Body**:
```json
{
  "permission_key": "custom:action",
  "permission_name": "Custom Action",
  "description": "Perform custom action",
  "service_name": "custom-service",
  "resource_type": "custom",
  "is_active": true,
  "is_system": false
}
```

**Response** (201 Created):
```json
{
  "id": 46,
  "permission_key": "custom:action",
  "permission_name": "Custom Action",
  "description": "Perform custom action",
  "service_name": "custom-service",
  "resource_type": "custom",
  "is_active": true,
  "is_system": false
}
```

**Errors**:
- `401 Unauthorized` - Admin authentication required
- `403 Forbidden` - Insufficient permissions
- `409 Conflict` - Permission key already exists

**Rate Limit**: 20 requests per minute per admin

---

### GET `/api/v1/permissions/users/{user_id}/roles`

Get user's roles.

**Request Headers**:
```
Authorization: Bearer <access_token>
```

**Response** (200 OK):
```json
{
  "roles": [
    {
      "id": 123,
      "user_id": 42,
      "telegram_id": "123456789",
      "role_key": "executor",
      "role_name": "Executor",
      "is_active_role": true,
      "role_data": {
        "specializations": ["plumbing", "electrical"],
        "locations": ["district_1", "district_2"]
      },
      "additional_permissions": ["requests:urgent"],
      "denied_permissions": [],
      "assigned_at": "2025-01-15T10:00:00Z",
      "assigned_by": 1,
      "expires_at": null
    }
  ]
}
```

**Errors**:
- `401 Unauthorized` - Authentication required
- `403 Forbidden` - Insufficient permissions (can only view own roles unless admin)
- `404 Not Found` - User not found

**Rate Limit**: 60 requests per minute per user

---

### POST `/api/v1/permissions/check`

Check if user has specific permission.

**Request Headers**:
```
Authorization: Bearer <access_token>
```

**Request Body**:
```json
{
  "user_id": 42,
  "permission_key": "requests:write",
  "resource_id": "250918-001"
}
```

**Response** (200 OK):
```json
{
  "has_permission": true,
  "user_id": 42,
  "permission_key": "requests:write",
  "granted_by": ["executor"],
  "checked_at": "2025-10-04T18:00:00Z"
}
```

**Response** (Permission denied):
```json
{
  "has_permission": false,
  "user_id": 42,
  "permission_key": "admin:delete",
  "reason": "User does not have admin role",
  "checked_at": "2025-10-04T18:00:00Z"
}
```

**Errors**:
- `401 Unauthorized` - Authentication required

**Rate Limit**: 100 requests per minute per user

---

## 🔐 Sessions

### GET `/api/v1/sessions`

List user's active sessions.

**Request Headers**:
```
Authorization: Bearer <access_token>
```

**Response** (200 OK):
```json
{
  "sessions": [
    {
      "session_id": "550e8400-e29b-41d4-a716-446655440000",
      "user_id": 42,
      "telegram_id": "123456789",
      "is_active": true,
      "expires_at": "2025-10-04T18:15:00Z",
      "refresh_expires_at": "2025-10-11T18:00:00Z",
      "device_info": {"device_type": "mobile", "platform": "iOS"},
      "ip_address": "172.20.0.5",
      "created_at": "2025-10-04T18:00:00Z",
      "last_activity": "2025-10-04T18:05:00Z"
    },
    {
      "session_id": "660e8400-e29b-41d4-a716-446655440001",
      "user_id": 42,
      "telegram_id": "123456789",
      "is_active": true,
      "expires_at": "2025-10-04T19:30:00Z",
      "refresh_expires_at": "2025-10-11T19:15:00Z",
      "device_info": {"device_type": "desktop", "platform": "Web"},
      "ip_address": "172.20.0.6",
      "created_at": "2025-10-04T19:15:00Z",
      "last_activity": "2025-10-04T19:15:00Z"
    }
  ],
  "total": 2
}
```

**Errors**:
- `401 Unauthorized` - Authentication required

**Rate Limit**: 30 requests per minute per user

---

### DELETE `/api/v1/sessions/{session_id}`

Terminate specific session.

**Request Headers**:
```
Authorization: Bearer <access_token>
```

**Response** (200 OK):
```json
{
  "success": true,
  "message": "Session terminated",
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Errors**:
- `401 Unauthorized` - Authentication required
- `403 Forbidden` - Can only terminate own sessions
- `404 Not Found` - Session not found

**Rate Limit**: 20 requests per minute per user

---

### DELETE `/api/v1/sessions`

Terminate all user sessions.

**Request Headers**:
```
Authorization: Bearer <access_token>
```

**Response** (200 OK):
```json
{
  "success": true,
  "message": "All sessions terminated",
  "terminated_count": 3
}
```

**Errors**:
- `401 Unauthorized` - Authentication required

**Rate Limit**: 10 requests per minute per user

---

### GET `/api/v1/sessions/cleanup/expired`

Cleanup expired sessions (Admin only, typically called by scheduler).

**Request Headers**:
```
Authorization: Bearer <admin_access_token>
```

**Response** (200 OK):
```json
{
  "success": true,
  "cleaned_sessions": 142,
  "cleaned_at": "2025-10-04T18:00:00Z"
}
```

**Errors**:
- `401 Unauthorized` - Admin authentication required
- `403 Forbidden` - Insufficient permissions

**Rate Limit**: 10 requests per minute

---

## ⏱️ Rate Limiting

### GET `/api/v1/rate-limit/clients`

Get all rate-limited clients (Admin only).

**Request Headers**:
```
Authorization: Bearer <admin_access_token>
```

**Response** (200 OK):
```json
{
  "clients": [
    {
      "client_ip": "172.20.0.5",
      "request_count": 95,
      "window_start": "2025-10-04T18:00:00Z",
      "window_end": "2025-10-04T18:01:00Z",
      "is_blocked": false
    },
    {
      "client_ip": "192.168.1.100",
      "request_count": 150,
      "window_start": "2025-10-04T18:00:00Z",
      "window_end": "2025-10-04T18:01:00Z",
      "is_blocked": true,
      "blocked_until": "2025-10-04T18:10:00Z"
    }
  ],
  "total": 2
}
```

**Errors**:
- `401 Unauthorized` - Admin authentication required
- `403 Forbidden` - Insufficient permissions

**Rate Limit**: 30 requests per minute per admin

---

### DELETE `/api/v1/rate-limit/client/{client_ip}`

Clear rate limit for specific client (Admin only).

**Request Headers**:
```
Authorization: Bearer <admin_access_token>
```

**Response** (200 OK):
```json
{
  "success": true,
  "message": "Rate limit cleared",
  "client_ip": "192.168.1.100"
}
```

**Errors**:
- `401 Unauthorized` - Admin authentication required
- `403 Forbidden` - Insufficient permissions

**Rate Limit**: 20 requests per minute per admin

---

## 🏥 Health & Monitoring

### GET `/health`

Health check endpoint.

**Response** (200 OK):
```json
{
  "status": "healthy",
  "service": "auth-service",
  "version": "1.0.1",
  "timestamp": "2025-10-04T18:00:00Z",
  "uptime_seconds": 86400
}
```

**Response** (503 Service Unavailable):
```json
{
  "status": "unhealthy",
  "service": "auth-service",
  "error": "Database connection failed"
}
```

**Rate Limit**: None (health checks excluded)

---

### GET `/ready`

Readiness check endpoint.

**Response** (200 OK):
```json
{
  "ready": true,
  "database": "connected",
  "redis": "connected",
  "dependencies": {
    "user-service": "available"
  }
}
```

**Response** (503 Service Unavailable):
```json
{
  "ready": false,
  "database": "connected",
  "redis": "disconnected",
  "dependencies": {
    "user-service": "unavailable"
  }
}
```

**Rate Limit**: None

---

### GET `/info`

Service information endpoint.

**Response** (200 OK):
```json
{
  "service": "auth-service",
  "version": "1.0.1",
  "description": "Authentication and Authorization Service",
  "api_version": "v1",
  "endpoints": 34,
  "documentation": "http://localhost:8001/docs"
}
```

**Rate Limit**: None

---

## ❌ Error Codes

### HTTP Status Codes

| Code | Description | Common Causes |
|------|-------------|---------------|
| 200 | OK | Request successful |
| 201 | Created | Resource created successfully |
| 400 | Bad Request | Invalid request parameters |
| 401 | Unauthorized | Missing or invalid authentication |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Resource not found |
| 409 | Conflict | Resource already exists |
| 410 | Gone | Endpoint permanently disabled |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Server error |
| 503 | Service Unavailable | Service or dependency unavailable |

### Error Response Format

```json
{
  "detail": "Error message",
  "error_code": "AUTH_001",
  "timestamp": "2025-10-04T18:00:00Z",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Common Error Codes

| Code | Message | Resolution |
|------|---------|------------|
| `AUTH_001` | Invalid credentials | Verify Telegram ID |
| `AUTH_002` | Token expired | Refresh token |
| `AUTH_003` | Invalid token | Login again |
| `AUTH_004` | Session not found | Login again |
| `AUTH_005` | Permission denied | Check user roles |
| `AUTH_006` | Rate limit exceeded | Wait before retrying |
| `AUTH_007` | Service revoked | Contact administrator |

---

## 🔄 Authentication Flow

### User Authentication Flow

```
1. Client sends POST /api/v1/auth/login
   └─> telegram_id, username, device_info

2. Auth Service validates with User Service
   └─> Check if user exists and is active

3. Auth Service creates session
   └─> Store in PostgreSQL with device info

4. Auth Service generates JWT tokens
   ├─> Access token (15 min expiry)
   └─> Refresh token (7 day expiry)

5. Client receives tokens + session info
   └─> Store tokens securely

6. Client uses access token for API calls
   └─> Authorization: Bearer <access_token>

7. Token expires → Client uses refresh token
   └─> POST /api/v1/auth/refresh

8. New tokens issued, old refresh token invalidated
   └─> Repeat from step 6

9. Logout → POST /api/v1/auth/logout
   └─> Session invalidated in database
```

### Service-to-Service Authentication Flow

```
1. Service sends request with headers
   ├─> X-Service-Name: request-service
   └─> X-Service-API-Key: static-api-key

2. Auth Service validates with StaticKeyService
   ├─> HMAC SHA-256 validation
   └─> Check Redis revocation list

3. Response with permissions
   └─> Service can proceed with request

4. Admin revokes service (if compromised)
   └─> POST /api/v1/internal/revoke-service

5. All future validations fail immediately
   └─> Redis provides instant revocation
```

---

## 📊 Rate Limits Summary

| Endpoint Category | Limit | Window |
|-------------------|-------|--------|
| Login | 10 req/min | Per IP |
| Token Refresh | 30 req/min | Per user |
| Logout | 10 req/min | Per user |
| User Info | 60 req/min | Per user |
| Service Auth | 1000 req/min | Per service |
| Permission Check | 100 req/min | Per user |
| Admin Operations | 10-30 req/min | Per admin |
| Health Checks | Unlimited | - |

---

## 🔗 Related Documentation

- [README.md](README.md) - Service overview and setup
- [SECURITY_IMPROVEMENTS_PLAN.md](SECURITY_IMPROVEMENTS_PLAN.md) - Security enhancements
- [Swagger UI](http://localhost:8001/docs) - Interactive API documentation
- [ReDoc](http://localhost:8001/redoc) - Alternative API documentation

---

**Maintained by**: Development Team
**Last Review**: 4 October 2025
**Version**: 1.0.1
