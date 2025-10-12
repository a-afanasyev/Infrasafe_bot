# 🔐 Auth Service - Integration Guide

**Version**: 1.0.0
**Date**: 4 October 2025
**Service**: Auth Service (Port 8001)

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Authentication Flows](#authentication-flows)
3. [Service-to-Service Authentication](#service-to-service-authentication)
4. [API Entry Points](#api-entry-points)
5. [Integration Examples](#integration-examples)
6. [Error Handling](#error-handling)
7. [Security Best Practices](#security-best-practices)

---

## 🎯 Overview

Auth Service provides centralized authentication and authorization for the UK Management Bot microservices architecture.

### Key Features:
- ✅ JWT-based user authentication (HS256)
- ✅ HMAC-based service-to-service authentication
- ✅ Session management with Redis
- ✅ Role-Based Access Control (RBAC)
- ✅ MFA support
- ✅ Service token validation and revocation
- ✅ Audit logging

### Architecture:
```
┌─────────────────┐
│   Bot Gateway   │
│  (Telegram Bot) │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────┐
│  Auth Service   │────▶│  User Service│
│   (Port 8001)   │     │  (Port 8002) │
└────────┬────────┘     └──────────────┘
         │
         ▼
┌─────────────────┐
│     Redis       │
│  (Sessions &    │
│  Rate Limiting) │
└─────────────────┘
```

---

## 🔄 Authentication Flows

### 1. User Authentication Flow (Telegram Login)

**Use Case**: Telegram user logs into the system

```mermaid
sequenceDiagram
    participant User
    participant BotGW as Bot Gateway
    participant Auth as Auth Service
    participant UserSvc as User Service
    participant Redis

    User->>BotGW: /start or callback
    BotGW->>Auth: POST /api/v1/auth/login
    Note over BotGW,Auth: {telegram_id, username, device_info}

    Auth->>UserSvc: GET /api/v1/users/telegram/{id}
    UserSvc-->>Auth: User data

    Auth->>Redis: Create session
    Auth->>Auth: Generate JWT tokens
    Auth-->>BotGW: {access_token, refresh_token, session_id}

    BotGW->>BotGW: Store tokens
    BotGW-->>User: Welcome message
```

**Example Request**:
```bash
curl -X POST http://auth-service:8001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "telegram_id": 123456789,
    "username": "john_doe",
    "device_info": {
      "device_type": "mobile",
      "platform": "iOS",
      "app_version": "1.0.0"
    }
  }'
```

**Example Response**:
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
    "created_at": "2025-10-04T17:15:00Z"
  },
  "tokens": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0MiIsInNlc3Npb25faWQiOiI1NTBlODQwMC1lMjliLTQxZDQtYTcxNi00NDY2NTU0NDAwMDAiLCJ0eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzI4MDYzMzAwfQ.signature",
    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0MiIsInNlc3Npb25faWQiOiI1NTBlODQwMC1lMjliLTQxZDQtYTcxNi00NDY2NTU0NDAwMDAiLCJ0eXBlIjoicmVmcmVzaCIsImV4cCI6MTcyODY2ODEwMH0.signature",
    "token_type": "bearer",
    "expires_in": 900,
    "session_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

---

### 2. Token Refresh Flow

**Use Case**: Access token expired, need to get a new one

```mermaid
sequenceDiagram
    participant BotGW as Bot Gateway
    participant Auth as Auth Service
    participant Redis

    BotGW->>Auth: POST /api/v1/auth/refresh
    Note over BotGW,Auth: {refresh_token}

    Auth->>Auth: Validate refresh token
    Auth->>Redis: Check session active
    Redis-->>Auth: Session valid

    Auth->>Auth: Generate new access token
    Auth-->>BotGW: {access_token, expires_in}
```

**Example Request**:
```bash
curl -X POST http://auth-service:8001/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{
    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  }'
```

**Example Response**:
```json
{
  "success": true,
  "message": "Token refreshed successfully",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.new_payload.new_signature",
  "token_type": "bearer",
  "expires_in": 900
}
```

---

### 3. Token Validation Flow

**Use Case**: Validate user's access token before processing request

```mermaid
sequenceDiagram
    participant Client
    participant Service as Any Service
    participant Auth as Auth Service

    Client->>Service: Request with Authorization header
    Service->>Auth: POST /api/v1/auth/validate
    Note over Service,Auth: {token}

    Auth->>Auth: Verify JWT signature
    Auth->>Auth: Check expiration
    Auth-->>Service: {valid: true, user_data}

    Service->>Service: Process request
    Service-->>Client: Response
```

**Example Request**:
```bash
curl -X POST http://auth-service:8001/api/v1/auth/validate \
  -H "Content-Type: application/json" \
  -d '{
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  }'
```

**Example Response**:
```json
{
  "valid": true,
  "user_id": 42,
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "telegram_id": "123456789",
  "username": "john_doe",
  "roles": ["user", "executor"],
  "expires_at": "2025-10-04T18:15:00Z"
}
```

---

### 4. Logout Flow

**Use Case**: User logs out, invalidate session

```mermaid
sequenceDiagram
    participant User
    participant BotGW as Bot Gateway
    participant Auth as Auth Service
    participant Redis

    User->>BotGW: /logout command
    BotGW->>Auth: POST /api/v1/auth/logout
    Note over BotGW,Auth: Authorization: Bearer {token}

    Auth->>Auth: Extract session_id from token
    Auth->>Redis: Invalidate session
    Auth->>Redis: Revoke all tokens for session
    Auth-->>BotGW: {success: true}

    BotGW->>BotGW: Clear stored tokens
    BotGW-->>User: Logged out successfully
```

**Example Request**:
```bash
curl -X POST http://auth-service:8001/api/v1/auth/logout \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

**Example Response**:
```json
{
  "success": true,
  "message": "Logged out successfully"
}
```

---

## 🔐 Service-to-Service Authentication

### Overview

Services authenticate with each other using **HMAC-SHA256** signatures. Each service has:
- A unique **Service Name** (e.g., `request-service`, `shift-service`)
- A **Static API Key** (stored in environment variables)

### HMAC Authentication Flow

```mermaid
sequenceDiagram
    participant ReqSvc as Request Service
    participant Auth as Auth Service
    participant Redis

    Note over ReqSvc: Generate HMAC signature
    ReqSvc->>ReqSvc: timestamp = current_time()
    ReqSvc->>ReqSvc: message = service_name + timestamp
    ReqSvc->>ReqSvc: signature = HMAC-SHA256(api_key, message)

    ReqSvc->>Auth: POST /api/v1/internal/validate-service-credentials
    Note over ReqSvc,Auth: Headers:<br/>X-Service-Name: request-service<br/>X-Service-API-Key: {api_key}<br/>X-Timestamp: {timestamp}<br/>X-Signature: {signature}

    Auth->>Auth: Lookup service API key
    Auth->>Auth: Verify signature
    Auth->>Auth: Check timestamp (max 5 min old)
    Auth->>Redis: Check service not revoked

    Auth-->>ReqSvc: {valid: true, service_name}
```

### HMAC Signature Generation

**Python Example**:
```python
import hmac
import hashlib
import time
from typing import Dict

def generate_service_auth_headers(
    service_name: str,
    api_key: str
) -> Dict[str, str]:
    """Generate HMAC authentication headers for service-to-service calls."""

    # Current timestamp
    timestamp = str(int(time.time()))

    # Message to sign: service_name + timestamp
    message = f"{service_name}{timestamp}"

    # Generate HMAC-SHA256 signature
    signature = hmac.new(
        api_key.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    return {
        "X-Service-Name": service_name,
        "X-Service-API-Key": api_key,
        "X-Timestamp": timestamp,
        "X-Signature": signature,
        "Content-Type": "application/json"
    }

# Usage
headers = generate_service_auth_headers(
    service_name="request-service",
    api_key="request-service-api-key-change-in-production"
)
```

**Example Request**:
```bash
# Generate signature
SERVICE_NAME="request-service"
API_KEY="request-service-api-key-change-in-production"
TIMESTAMP=$(date +%s)
MESSAGE="${SERVICE_NAME}${TIMESTAMP}"
SIGNATURE=$(echo -n "$MESSAGE" | openssl dgst -sha256 -hmac "$API_KEY" | cut -d' ' -f2)

# Make request
curl -X POST http://auth-service:8001/api/v1/internal/validate-service-credentials \
  -H "X-Service-Name: $SERVICE_NAME" \
  -H "X-Service-API-Key: $API_KEY" \
  -H "X-Timestamp: $TIMESTAMP" \
  -H "X-Signature: $SIGNATURE" \
  -H "Content-Type: application/json"
```

**Example Response**:
```json
{
  "valid": true,
  "service_name": "request-service",
  "permissions": ["users:read", "requests:write"],
  "authenticated_at": "2025-10-04T17:30:00Z"
}
```

---

### Service Token Generation

**Use Case**: Generate a long-lived JWT for service-to-service calls (alternative to HMAC)

**Example Request**:
```bash
curl -X POST http://auth-service:8001/api/v1/internal/generate-service-token \
  -H "X-Service-Name: request-service" \
  -H "X-Service-API-Key: request-service-api-key-change-in-production" \
  -H "X-Timestamp: $(date +%s)" \
  -H "X-Signature: {calculated_signature}" \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "request-service",
    "permissions": ["users:read", "requests:write", "requests:read"],
    "expires_in": 86400
  }'
```

**Example Response**:
```json
{
  "success": true,
  "service_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzZXJ2aWNlX25hbWUiOiJyZXF1ZXN0LXNlcnZpY2UiLCJwZXJtaXNzaW9ucyI6WyJ1c2VyczpyZWFkIiwicmVxdWVzdHM6d3JpdGUiXSwiZXhwIjoxNzI4MTUwNjAwfQ.signature",
  "token_type": "service",
  "expires_in": 86400,
  "expires_at": "2025-10-05T17:30:00Z"
}
```

---

### Service Revocation

**Use Case**: Immediately block a compromised service

**Example Request**:
```bash
curl -X POST http://auth-service:8001/api/v1/internal/revoke-service \
  -H "X-Service-Name: admin-service" \
  -H "X-Service-API-Key: {admin_api_key}" \
  -H "X-Timestamp: $(date +%s)" \
  -H "X-Signature: {signature}" \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "request-service",
    "reason": "Security incident - API key compromised"
  }'
```

**Example Response**:
```json
{
  "success": true,
  "message": "Service revoked successfully",
  "service_name": "request-service",
  "revoked_at": "2025-10-04T17:35:00Z",
  "reason": "Security incident - API key compromised"
}
```

---

## 📍 API Entry Points

### Public Endpoints (No Authentication Required)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/docs` | OpenAPI documentation |
| `POST` | `/api/v1/auth/login` | User login (Telegram) |

### User Authentication Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/v1/auth/login` | None | Telegram user login |
| `POST` | `/api/v1/auth/logout` | Bearer | Logout current session |
| `POST` | `/api/v1/auth/refresh` | Refresh Token | Get new access token |
| `POST` | `/api/v1/auth/validate` | None | Validate JWT token |
| `POST` | `/api/v1/auth/check-permissions` | Bearer | Check user permissions |

### Password Authentication Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/v1/auth/password/login` | None | Login with password |
| `POST` | `/api/v1/auth/password/set` | Bearer | Set/update password |
| `POST` | `/api/v1/auth/password/reset-request` | None | Request password reset |
| `POST` | `/api/v1/auth/password/reset-confirm` | Token | Confirm password reset |

### MFA Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/v1/auth/mfa/setup` | Bearer | Setup MFA (TOTP) |
| `POST` | `/api/v1/auth/mfa/verify` | Bearer | Verify MFA code |
| `POST` | `/api/v1/auth/mfa/disable` | Bearer + MFA | Disable MFA |
| `POST` | `/api/v1/auth/mfa/backup-codes` | Bearer | Generate backup codes |

### Session Management Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/api/v1/sessions/current` | Bearer | Get current session |
| `GET` | `/api/v1/sessions/list` | Bearer | List all user sessions |
| `DELETE` | `/api/v1/sessions/{session_id}` | Bearer | Invalidate specific session |
| `DELETE` | `/api/v1/sessions/all` | Bearer | Invalidate all sessions |

### Permission Management Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/api/v1/permissions/user/{user_id}` | Service | Get user permissions |
| `POST` | `/api/v1/permissions/check` | Service | Batch permission check |
| `PUT` | `/api/v1/permissions/user/{user_id}` | Service | Update user permissions |

### Internal Service Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/v1/internal/validate-service-credentials` | HMAC | Validate service credentials |
| `POST` | `/api/v1/internal/generate-service-token` | HMAC | Generate service JWT |
| `POST` | `/api/v1/internal/revoke-service` | HMAC | Revoke service access |
| `GET` | `/api/v1/internal/audit-logs` | HMAC | Get audit logs |

---

## 💡 Integration Examples

### Example 1: Bot Gateway Authentication Flow

**Scenario**: User sends `/start` command to Telegram bot

```python
# bot_gateway/handlers/start.py
from aiogram import Router, types
from aiogram.filters import Command
import httpx

router = Router()

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    """Handle /start command - authenticate user."""

    # Prepare login data
    login_data = {
        "telegram_id": message.from_user.id,
        "username": message.from_user.username,
        "device_info": {
            "device_type": "telegram",
            "platform": "mobile",
            "app_version": "1.0.0"
        }
    }

    # Call Auth Service
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://auth-service:8001/api/v1/auth/login",
            json=login_data,
            timeout=10.0
        )

        if response.status_code == 200:
            data = response.json()

            # Store tokens in bot's state (Redis or in-memory)
            await store_user_tokens(
                user_id=message.from_user.id,
                access_token=data["tokens"]["access_token"],
                refresh_token=data["tokens"]["refresh_token"],
                session_id=data["session"]["session_id"]
            )

            await message.answer(
                f"Добро пожаловать, {message.from_user.first_name}!\n"
                f"Вы успешно авторизованы."
            )
        else:
            await message.answer(
                "Ошибка авторизации. Пожалуйста, попробуйте позже."
            )
```

---

### Example 2: Request Service Calling User Service

**Scenario**: Request Service needs to get user data from User Service

```python
# request_service/services/user_client.py
import httpx
from typing import Optional, Dict
from config import settings

class UserServiceClient:
    """Client for User Service with service authentication."""

    def __init__(self):
        self.base_url = settings.user_service_url
        self.service_name = "request-service"
        self.api_key = settings.service_api_key

    def _get_service_headers(self) -> Dict[str, str]:
        """Generate HMAC authentication headers."""
        import hmac
        import hashlib
        import time

        timestamp = str(int(time.time()))
        message = f"{self.service_name}{timestamp}"
        signature = hmac.new(
            self.api_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()

        return {
            "X-Service-Name": self.service_name,
            "X-Service-API-Key": self.api_key,
            "X-Timestamp": timestamp,
            "X-Signature": signature,
            "Content-Type": "application/json"
        }

    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user data from User Service."""

        async with httpx.AsyncClient() as client:
            # First, validate our service credentials with Auth Service
            auth_response = await client.post(
                f"{settings.auth_service_url}/api/v1/internal/validate-service-credentials",
                headers=self._get_service_headers()
            )

            if auth_response.status_code != 200:
                raise Exception("Service authentication failed")

            # Now call User Service with service token
            user_response = await client.get(
                f"{self.base_url}/api/v1/users/{user_id}",
                headers=self._get_service_headers()
            )

            if user_response.status_code == 200:
                return user_response.json()

            return None

# Usage
user_client = UserServiceClient()
user_data = await user_client.get_user(42)
```

---

### Example 3: Middleware for Token Validation

**Scenario**: Protect API endpoints with JWT validation

```python
# request_service/middleware/auth.py
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import httpx
from typing import Dict

security = HTTPBearer()

async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict:
    """Verify JWT token with Auth Service."""

    token = credentials.credentials

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://auth-service:8001/api/v1/auth/validate",
            json={"token": token},
            timeout=5.0
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired token"
            )

        data = response.json()

        if not data.get("valid"):
            raise HTTPException(
                status_code=401,
                detail="Token validation failed"
            )

        return data

# Usage in endpoint
from fastapi import APIRouter, Depends

router = APIRouter()

@router.get("/api/v1/requests/{request_id}")
async def get_request(
    request_id: str,
    user_data: Dict = Depends(verify_token)
):
    """Get request by ID - requires authentication."""

    user_id = user_data["user_id"]
    roles = user_data["roles"]

    # Check permissions
    if "admin" not in roles and "manager" not in roles:
        raise HTTPException(403, "Insufficient permissions")

    # ... process request
    return {"request_id": request_id, "user_id": user_id}
```

---

### Example 4: Automatic Token Refresh

**Scenario**: Automatically refresh expired access token

```python
# bot_gateway/utils/auth_client.py
import httpx
from typing import Optional, Dict
import asyncio

class AuthClient:
    """Client for Auth Service with automatic token refresh."""

    def __init__(self, auth_service_url: str):
        self.auth_service_url = auth_service_url
        self._tokens: Dict[int, Dict] = {}  # user_id -> tokens

    async def get_valid_token(self, user_id: int) -> Optional[str]:
        """Get valid access token, refresh if expired."""

        if user_id not in self._tokens:
            return None

        tokens = self._tokens[user_id]
        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]

        # Try to use access token
        async with httpx.AsyncClient() as client:
            validate_response = await client.post(
                f"{self.auth_service_url}/api/v1/auth/validate",
                json={"token": access_token}
            )

            # Token is valid
            if validate_response.status_code == 200:
                data = validate_response.json()
                if data.get("valid"):
                    return access_token

            # Token expired, try to refresh
            refresh_response = await client.post(
                f"{self.auth_service_url}/api/v1/auth/refresh",
                json={"refresh_token": refresh_token}
            )

            if refresh_response.status_code == 200:
                data = refresh_response.json()
                new_access_token = data["access_token"]

                # Update stored token
                self._tokens[user_id]["access_token"] = new_access_token

                return new_access_token

            # Refresh failed, user needs to login again
            del self._tokens[user_id]
            return None

    async def login(self, telegram_id: int, username: str) -> bool:
        """Login user and store tokens."""

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.auth_service_url}/api/v1/auth/login",
                json={
                    "telegram_id": telegram_id,
                    "username": username,
                    "device_info": {"device_type": "telegram"}
                }
            )

            if response.status_code == 200:
                data = response.json()
                user_id = data["user_id"]

                self._tokens[user_id] = {
                    "access_token": data["tokens"]["access_token"],
                    "refresh_token": data["tokens"]["refresh_token"],
                    "session_id": data["session"]["session_id"]
                }

                return True

            return False
```

---

## ⚠️ Error Handling

### Common Error Responses

#### 401 Unauthorized
```json
{
  "detail": "Invalid or expired token",
  "error_code": "TOKEN_INVALID"
}
```

#### 403 Forbidden
```json
{
  "detail": "Insufficient permissions",
  "error_code": "PERMISSION_DENIED",
  "required_permissions": ["admin"],
  "user_permissions": ["user", "executor"]
}
```

#### 429 Too Many Requests
```json
{
  "detail": "Rate limit exceeded",
  "error_code": "RATE_LIMIT_EXCEEDED",
  "retry_after": 60,
  "limit": 100,
  "window": 60
}
```

#### 500 Internal Server Error
```json
{
  "detail": "Authentication service unavailable",
  "error_code": "SERVICE_ERROR"
}
```

### Error Handling Example

```python
import httpx
from fastapi import HTTPException

async def safe_auth_request(url: str, **kwargs):
    """Make auth request with error handling."""

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, **kwargs, timeout=10.0)

            # Success
            if response.status_code == 200:
                return response.json()

            # Rate limited
            elif response.status_code == 429:
                data = response.json()
                retry_after = data.get("retry_after", 60)
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limited. Retry after {retry_after} seconds"
                )

            # Unauthorized
            elif response.status_code == 401:
                raise HTTPException(
                    status_code=401,
                    detail="Authentication failed"
                )

            # Other errors
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=response.json().get("detail", "Unknown error")
                )

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Auth service timeout"
        )

    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Auth service unavailable"
        )
```

---

## 🔒 Security Best Practices

### 1. Token Storage

**❌ DO NOT**:
- Store tokens in local storage (web)
- Log tokens to console or files
- Send tokens in URL parameters
- Share tokens between services

**✅ DO**:
- Store tokens in secure, encrypted storage
- Use httpOnly cookies for web applications
- Rotate tokens regularly
- Implement token expiration

### 2. HMAC Signature Security

**❌ DO NOT**:
- Hardcode API keys in source code
- Use the same API key for all environments
- Accept signatures older than 5 minutes
- Skip signature verification

**✅ DO**:
- Store API keys in environment variables or secrets manager
- Use different API keys for dev/staging/production
- Implement timestamp validation (max 5 min drift)
- Always verify signatures before processing

### 3. Service-to-Service Communication

```python
# ✅ GOOD: Always validate service credentials
headers = generate_service_auth_headers(service_name, api_key)
response = await client.post(url, headers=headers)

# ❌ BAD: Trusting internal network without authentication
response = await client.post(url)  # No authentication!
```

### 4. Rate Limiting

**Configure per-service limits**:
```python
# config.py
RATE_LIMITS = {
    "auth": {
        "login": "10/minute",
        "refresh": "20/minute",
        "validate": "100/minute"
    },
    "service": {
        "validate": "1000/minute",
        "generate_token": "10/minute"
    }
}
```

### 5. Audit Logging

**Always log authentication events**:
```python
await audit_service.log_event(
    event_type="user_login",
    user_id=user_id,
    ip_address=request.client.host,
    user_agent=request.headers.get("User-Agent"),
    details={
        "telegram_id": telegram_id,
        "success": True
    }
)
```

### 6. Token Revocation

**Implement emergency revocation**:
```bash
# Revoke all sessions for user
POST /api/v1/sessions/all
Authorization: Bearer {admin_token}

{
  "user_id": 42,
  "reason": "Account compromised"
}

# Revoke service access
POST /api/v1/internal/revoke-service
X-Service-Name: admin-service
X-Signature: {signature}

{
  "service_name": "compromised-service",
  "reason": "API key leaked"
}
```

---

## 📚 Additional Resources

- [API Reference](API_REFERENCE.md) - Complete API documentation
- [Testing Guide](RUN_TESTS.md) - How to test Auth Service
- [README](README.md) - Service overview and setup
- [Security Plan](SECURITY_IMPROVEMENTS_PLAN.md) - Security enhancements

---

## 🆘 Support

**Issues**: Report at UK Management Bot repository
**Contact**: Auth Service Team
**Documentation**: [DOCUMENTATION_INDEX.md](DOCUMENTATION_INDEX.md)

---

**Last Updated**: 4 October 2025
**Version**: 1.0.0
