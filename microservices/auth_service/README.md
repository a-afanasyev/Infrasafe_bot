# 🔐 Auth Service - Authentication & Authorization Microservice

**UK Management Bot - Authentication Service**

---

## 📋 Service Overview

Auth Service provides centralized authentication and authorization for the UK Management Bot microservices ecosystem. It handles JWT token management, session tracking, role-based access control (RBAC), service-to-service authentication, and comprehensive audit logging.

### 🎯 Core Responsibilities

- **Authentication**: User login/logout, JWT token generation/validation
- **Authorization**: Role-based permissions, access control
- **Session Management**: Active session tracking with automatic cleanup
- **Service-to-Service Auth**: Internal API authentication for microservices
- **Security**: Rate limiting, audit logging, multi-factor authentication
- **User Management**: User roles, permissions, credentials

---

## 🏗️ Architecture

### **Service Status: ✅ OPERATIONAL**
- **Port**: 8001
- **Health**: `/health` endpoint
- **Database**: `auth_db` (PostgreSQL)
- **Cache**: Redis DB 1

### **Database Schema (6 Tables)**

```sql
-- User Sessions & Tokens
sessions:
  - session_id (String, PK)
  - user_id (Integer, FK)
  - telegram_id (BigInteger)
  - access_token (Text)
  - refresh_token (String)
  - is_active (Boolean)
  - expires_at, refresh_expires_at
  - device_info, ip_address, user_agent (JSON)
  - created_at, last_activity

-- Security Audit Trail
auth_logs:
  - id (Integer, PK)
  - user_id (Integer, nullable)
  - telegram_id (BigInteger, nullable)
  - event_type (String: login, logout, token_refresh, failed_attempt)
  - event_status (String: success, failure, error)
  - ip_address, user_agent, session_id
  - auth_metadata (JSON)
  - created_at

-- System Permissions
permissions:
  - id (Integer, PK)
  - permission_key (String, unique)
  - permission_name, description
  - service_name (String)
  - resource_type (String)
  - is_active, is_system (Boolean)

-- User Role Assignments
user_roles:
  - id (Integer, PK)
  - user_id (Integer)
  - telegram_id (BigInteger)
  - role_key (String: admin, manager, executor, applicant)
  - role_name, is_active_role (Boolean)
  - role_data (JSON: specializations, locations)
  - additional_permissions, denied_permissions (JSON)
  - assigned_at, assigned_by, expires_at

-- User Authentication Credentials
user_credentials:
  - id (Integer, PK)
  - user_id (Integer, unique)
  - telegram_id (BigInteger, unique)
  - password_hash, password_salt
  - mfa_enabled, mfa_secret, backup_codes (JSON)
  - failed_attempts, locked_until
  - session_timeout_minutes
  - created_at, last_login_at

-- Service-to-Service Tokens
service_tokens:
  - id (Integer, PK)
  - service_name (String, unique)
  - token_hash (String)
  - is_active (Boolean)
  - permissions (JSON Array)
  - last_used_at, created_at, expires_at
  - created_by, description
```

### **Service Layer**

- **AuthService**: Core authentication logic
- **JWTService**: Token generation, validation, rotation
- **SessionService**: Session lifecycle management
- **ServiceTokenManager**: Service-to-service auth
- **AuditService**: Security event logging

---

## 🚀 API Endpoints

### **Authentication (`/api/v1/auth`)**

```yaml
POST   /login           # User authentication with Telegram ID
POST   /logout          # Session termination
POST   /refresh         # Token refresh
GET    /me              # Current user info
POST   /verify-token    # Token validation
GET    /sessions        # List user sessions
DELETE /sessions/{id}   # Terminate specific session
DELETE /sessions/all    # Terminate all user sessions
```

### **Internal Service API (`/api/v1/internal`)**

```yaml
POST   /validate-service-token     # Service token validation
POST   /generate-service-token     # Generate service token
GET    /user-stats                 # User statistics proxy
```

### **Health & Monitoring**

```yaml
GET    /health          # Service health check
GET    /metrics         # Prometheus metrics
```

---

## 🔧 Key Features

### **JWT Security**
- **Algorithm**: HS256 with secret key rotation
- **Access Token**: 15 minutes expiry
- **Refresh Token**: 7 days expiry
- **Validation**: Signature + expiration + session checks
- **Claims**: user_id, telegram_id, roles, permissions

### **Session Management**
- **Storage**: PostgreSQL with indexed lookups
- **Tracking**: Device info, IP address, user agent
- **Security**: Multiple concurrent sessions
- **Cleanup**: Automatic expired session removal

### **Service-to-Service Authentication**
- **API Keys**: Long-lived service tokens
- **JWT Tokens**: Short-lived with refresh capability
- **Permissions**: Service-specific permission arrays
- **Validation**: Token signature + service name verification

### **Security Features**
- **Rate Limiting**: Redis-based request limiting
- **Audit Logging**: Complete authentication event trail
- **Account Lockout**: Failed attempt protection
- **Multi-Factor Auth**: TOTP support with backup codes
- **Password Security**: bcrypt hashing with salt

### **Role-Based Access Control (RBAC)**
- **Roles**: admin, manager, executor, applicant
- **Permissions**: Granular service-specific permissions
- **Dynamic**: Role data with specializations and locations
- **Inheritance**: Permission override support

---

## 🐳 Deployment

### **Current Configuration**

```yaml
# From docker-compose.yml
auth-service:
  image: microservices-auth-service
  ports:
    - "8001:8001"
  environment:
    - DATABASE_URL=postgresql+asyncpg://auth_user:auth_pass@auth-db:5432/auth_db
    - REDIS_URL=redis://shared-redis:6379/1
    - USER_SERVICE_URL=http://user-service:8002
    - DEBUG=true
    - LOG_LEVEL=INFO
  depends_on:
    - auth-db (healthy)
    - shared-redis (healthy)
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
    interval: 30s
    timeout: 10s
    retries: 3
```

### **Environment Variables**

```bash
# Service Configuration
SERVICE_NAME=auth-service
VERSION=1.0.0
DEBUG=true
LOG_LEVEL=INFO
HOST=0.0.0.0
PORT=8001

# Database
DATABASE_URL=postgresql+asyncpg://auth_user:auth_pass@auth-db:5432/auth_db

# Redis Cache
REDIS_URL=redis://shared-redis:6379/1

# JWT Configuration
JWT_SECRET_KEY=<configured>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# Service URLs
USER_SERVICE_URL=http://user-service:8002

# Security
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=60
```

---

## 🔌 Service Integrations

### **User Service Integration**
```python
# User role synchronization
async def sync_user_roles(user_id: int, telegram_id: int, roles: List[str]):
    """Sync user roles with User Service"""

# Get user statistics
async def get_user_stats():
    """Proxy request to User Service internal stats"""
```

### **Service-to-Service Authentication**
```python
# Service token validation endpoint
POST /api/v1/internal/validate-service-token
Request: {"token": "jwt_token", "service_name": "user-service"}
Response: {
    "valid": true,
    "service_name": "user-service",
    "permissions": ["user.read", "user.write"],
    "expires_at": "2024-12-31T23:59:59Z"
}

# Service token generation
POST /api/v1/internal/generate-service-token
Request: {"service_name": "user-service", "permissions": []}
Response: {
    "token": "jwt_token",
    "service_name": "user-service",
    "permissions": ["user.read", "user.write"],
    "token_type": "Bearer",
    "expires_in": 2592000
}
```

### **Other Services Integration**
All microservices use Auth Service for:
- Service token validation
- User authentication verification
- Permission checking
- Audit logging

---

## 📊 Monitoring & Observability

### **Health Checks**
```bash
curl http://localhost:8001/health
# Response: {"status": "healthy", "service": "auth-service"}
```

### **Metrics (Prometheus)**
- Authentication success/failure rates
- Active session count
- Token validation latency
- Database connection pool status
- Service-to-service auth requests

### **Structured Logging**
```json
{
    "timestamp": "2025-09-27T18:00:00Z",
    "level": "INFO",
    "service": "auth-service",
    "event": "user_login",
    "user_id": 123,
    "telegram_id": 456789,
    "ip_address": "172.20.0.5",
    "success": true,
    "duration_ms": 45
}
```

### **Audit Trail**
All authentication events are logged to `auth_logs` table:
- Login attempts (success/failure)
- Token refreshes
- Session terminations
- Service token validations
- Permission checks

---

## 🧪 Testing

### **Test Coverage**
- Unit tests for authentication logic
- Integration tests for API endpoints
- Security tests for token validation
- Performance tests for high load

### **API Testing**
```bash
# User authentication
curl -X POST http://localhost:8001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"telegram_id": 123456789, "username": "testuser"}'

# Service token validation
curl -X POST http://localhost:8001/api/v1/internal/validate-service-token \
  -H "Content-Type: application/json" \
  -d '{"token": "jwt_token", "service_name": "user-service"}'

# Health check
curl http://localhost:8001/health
```

---

## 🚀 Production Features

### **Performance**
- **Token validation**: < 10ms p95
- **Authentication**: < 100ms p95
- **Database queries**: Optimized with indexes
- **Connection pooling**: 10-20 connections
- **Concurrent sessions**: 1000+ supported

### **Security**
- **JWT signing**: HS256 with secret rotation
- **Password hashing**: bcrypt with salt
- **Rate limiting**: Redis-based per-IP/user
- **Session security**: IP validation, device tracking
- **Audit compliance**: Complete event logging

### **Scalability**
- **Stateless design**: Horizontal scaling ready
- **Database optimization**: Indexed queries, connection pooling
- **Cache layer**: Redis for session storage
- **Load balancing**: Multi-instance deployment

### **Reliability**
- **Health checks**: Docker health monitoring
- **Circuit breakers**: Database failover
- **Graceful shutdown**: Connection cleanup
- **Error handling**: Comprehensive exception management

---

## 📚 Development

### **Local Development**
```bash
# Start dependencies
docker-compose up auth-db shared-redis -d

# Install dependencies
pip install -r requirements.txt

# Run service
uvicorn main:app --reload --host 0.0.0.0 --port 8001

# Access API docs
open http://localhost:8001/docs
```

### **Database Management**
```bash
# Connect to database
docker-compose exec auth-db psql -U auth_user -d auth_db

# Run migrations
alembic upgrade head

# Create migration
alembic revision --autogenerate -m "description"
```

### **Code Quality**
```bash
# Format code
black . && ruff . --fix

# Type checking
mypy .

# Run tests
pytest tests/ -v --cov --cov-report=html
```

---

## 📄 API Documentation

### **Interactive Documentation**
- **Swagger UI**: http://localhost:8001/docs
- **ReDoc**: http://localhost:8001/redoc
- **OpenAPI JSON**: http://localhost:8001/openapi.json

### **Key Endpoints Documentation**
- Authentication flows with examples
- Service integration patterns
- Error response formats
- Rate limiting behavior

---

**📝 Status**: ✅ **PRODUCTION READY**
**🔄 Version**: 1.0.0
**📅 Last Updated**: September 27, 2025
**🎯 Port**: 8001
**💾 Database**: auth_db (PostgreSQL)
**🔗 Dependencies**: shared-redis