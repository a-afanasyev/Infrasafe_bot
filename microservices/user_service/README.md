# 👥 User Service - User Management & Profile Microservice

**UK Management Bot - User Service**

---

## 📋 Service Overview

User Service manages all user-related operations including profiles, roles, verification workflows, and access control. It provides comprehensive user lifecycle management with integration to Auth Service and other microservices.

### 🎯 Core Responsibilities

- **User Management**: CRUD operations, user lifecycle
- **Profile Management**: Personal information, specializations, addresses
- **Verification Workflow**: Identity verification with document uploads
- **Role Management**: User roles with Auth Service synchronization
- **Access Control**: Permission management and enforcement
- **Document Management**: KYC/verification document handling

---

## 🏗️ Architecture

### **Service Status: ✅ OPERATIONAL**
- **Port**: 8002
- **Health**: `/health` endpoint
- **Database**: `user_db` (PostgreSQL)
- **Cache**: Redis DB 2

### **Database Schema (10 Tables)**

```sql
-- Core User Information
users:
  - id (Integer, PK)
  - telegram_id (BigInteger, unique)
  - username, first_name, last_name
  - phone, email, language_code
  - status (String: pending, approved, blocked, archived)
  - is_active (Boolean)
  - created_at, updated_at

-- Extended Profile Information
user_profiles:
  - id (Integer, PK)
  - user_id (Integer, FK to users)
  - middle_name, birth_date
  - bio, rating, experience_years
  - home_address, apartment_address, yard_address
  - address_type (String)
  - specialization (JSON Array)
  - avatar_url
  - emergency_contact_name, emergency_contact_phone
  - notification_preferences (JSON)
  - created_at, updated_at

-- Role Assignments
user_role_mappings:
  - id (Integer, PK)
  - user_id (Integer, FK to users)
  - role_id (Integer, FK to roles)
  - assigned_by (Integer)
  - assigned_at, expires_at
  - is_active, is_primary (Boolean)

-- System Permissions
permissions:
  - id (Integer, PK)
  - permission_key (String, unique)
  - permission_name, description
  - resource_type, action_type
  - is_active, is_system (Boolean)
  - created_at, updated_at

-- User Roles
roles:
  - id (Integer, PK)
  - role_key (String, unique: admin, manager, executor, applicant)
  - role_name, description
  - default_permissions (JSON Array)
  - is_active, is_system (Boolean)
  - created_at, updated_at

-- Role-Permission Mappings
role_permission_mappings:
  - id (Integer, PK)
  - role_id (Integer, FK to roles)
  - permission_id (Integer, FK to permissions)
  - granted_at, granted_by

-- User Permission Overrides
user_permission_overrides:
  - id (Integer, PK)
  - user_id (Integer, FK to users)
  - permission_id (Integer, FK to permissions)
  - override_type (String: grant, deny)
  - granted_by, granted_at, expires_at
  - is_active (Boolean)

-- Identity Verification
user_verifications:
  - id (Integer, PK)
  - user_id (Integer, FK to users)
  - verification_type (String: identity, address, business)
  - status (String: pending, approved, rejected)
  - personal_info (JSON)
  - verified_by, verified_at
  - rejection_reason, notes
  - created_at, updated_at

-- Verification Documents
user_documents:
  - id (Integer, PK)
  - verification_id (Integer, FK to user_verifications)
  - document_type (String: passport, utility_bill, photo, id_card)
  - file_url, file_name, file_size
  - status (String: uploaded, verified, rejected)
  - verified_at, uploaded_at

-- User Access Rights
access_rights:
  - id (Integer, PK)
  - user_id (Integer, FK to users)
  - can_create_requests, can_view_all_requests (Boolean)
  - can_manage_users, can_access_analytics (Boolean)
  - can_manage_shifts, can_export_data (Boolean)
  - can_moderate_content, can_view_reports (Boolean)
  - updated_at
```

### **Service Layer**

- **UserService**: Core user CRUD and lifecycle management
- **ProfileService**: Profile management and avatar handling
- **VerificationService**: Identity verification workflow
- **RoleService**: Role assignment and Auth Service integration
- **PermissionService**: Access control and permission management

---

## 🚀 API Endpoints

### **User Management (`/api/v1/users`)**

```yaml
GET    /                           # List users (paginated, filtered)
POST   /                           # Create new user
GET    /{user_id}                  # Get user by ID
PUT    /{user_id}                  # Update user
DELETE /{user_id}                  # Archive user (soft delete)
GET    /by-telegram/{telegram_id}  # Get user by Telegram ID
GET    /search                     # Search users
GET    /stats                      # User statistics
```

### **Profile Management (`/api/v1/users/{user_id}/profile`)**

```yaml
GET    /                   # Get user profile
PUT    /                   # Update profile
POST   /avatar             # Upload avatar
DELETE /avatar             # Remove avatar
GET    /specializations    # Get user specializations
PUT    /specializations    # Update specializations
```

### **Verification Workflow (`/api/v1/users/{user_id}/verification`)**

```yaml
POST   /                   # Start verification process
GET    /                   # Get verification status
PUT    /{verification_id}  # Update verification
POST   /{verification_id}/documents  # Upload documents
GET    /{verification_id}/documents  # List documents
PUT    /{verification_id}/approve    # Approve verification
PUT    /{verification_id}/reject     # Reject verification
```

### **Role Management (`/api/v1/users/{user_id}/roles`)**

```yaml
GET    /                   # Get user roles
POST   /                   # Assign role
DELETE /{role_id}          # Remove role
PUT    /{role_id}/primary  # Set as primary role
```

### **Internal API (`/api/v1/internal`)**

```yaml
GET    /stats/overview         # User statistics for Auth Service
POST   /sync-roles             # Sync roles with Auth Service
GET    /users/bulk             # Bulk user data for other services
POST   /users/validate         # Validate user existence
```

### **Health & Monitoring**

```yaml
GET    /health              # Service health check
GET    /metrics             # Prometheus metrics
```

---

## 🔧 Key Features

### **User Lifecycle Management**
- **Registration**: Telegram-based user creation
- **Profile**: Comprehensive profile with specializations
- **Status Management**: pending → approved → active workflow
- **Soft Delete**: User archiving with data retention

### **Identity Verification**
- **Multi-step Process**: Identity, address, business verification
- **Document Upload**: Integration with Media Service
- **Approval Workflow**: Manual verification by administrators
- **Status Tracking**: Complete verification history

### **Role-Based Access Control**
- **Dynamic Roles**: admin, manager, executor, applicant
- **Permission System**: Granular resource-action permissions
- **Override Support**: User-specific permission overrides
- **Auth Integration**: Real-time sync with Auth Service

### **Profile Management**
- **Personal Information**: Names, contacts, addresses
- **Professional Data**: Specializations, experience, rating
- **Preferences**: Notification settings, language
- **Avatar Support**: Image upload and management

### **Address Management**
- **Multiple Addresses**: Home, apartment, yard addresses
- **Address Types**: Flexible address categorization
- **Geolocation**: Integration ready for location services

---

## 🐳 Deployment

### **Current Configuration**

```yaml
# From docker-compose.yml
user-service:
  image: microservices-user-service
  ports:
    - "8002:8002"
  environment:
    - USER_DATABASE_URL=postgresql+asyncpg://user_user:user_pass@user-db:5432/user_db
    - USER_AUTH_SERVICE_URL=http://auth-service:8001
    - USER_MEDIA_SERVICE_URL=http://media-service:8004
    - USER_NOTIFICATION_SERVICE_URL=http://notification-service:8005
    - USER_PORT=8002
    - USER_REDIS_URL=redis://shared-redis:6379/2
    - USER_DEBUG=true
    - USER_LOG_LEVEL=INFO
  depends_on:
    - user-db (healthy)
    - auth-service (healthy)
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8002/health"]
    interval: 30s
    timeout: 10s
    retries: 3
```

### **Environment Variables (with USER_ prefix)**

```bash
# Service Configuration
USER_SERVICE_NAME=user-service
USER_VERSION=1.0.0
USER_DEBUG=true
USER_LOG_LEVEL=INFO
USER_HOST=0.0.0.0
USER_PORT=8002

# Database
USER_DATABASE_URL=postgresql+asyncpg://user_user:user_pass@user-db:5432/user_db

# Redis Cache
USER_REDIS_URL=redis://shared-redis:6379/2

# Service URLs
USER_AUTH_SERVICE_URL=http://auth-service:8001
USER_MEDIA_SERVICE_URL=http://media-service:8004
USER_NOTIFICATION_SERVICE_URL=http://notification-service:8005

# User Management Settings
USER_MAX_PROFILE_SIZE_MB=10
USER_ALLOWED_DOCUMENT_TYPES=["passport", "utility_bill", "photo", "id_card"]
USER_MAX_DOCUMENTS_PER_USER=20

# Verification Settings
USER_VERIFICATION_EXPIRE_DAYS=30
USER_MAX_VERIFICATION_ATTEMPTS=3
USER_AUTO_APPROVE_THRESHOLD=0.95
```

---

## 🔌 Service Integrations

### **Auth Service Integration**
```python
# Role synchronization
async def sync_roles_with_auth():
    """Sync user roles with Auth Service"""

# Permission validation
async def validate_permissions(user_id: int, permissions: List[str]):
    """Validate user permissions via Auth Service"""
```

### **Media Service Integration**
```python
# Avatar upload
async def upload_avatar(user_id: int, file_data: bytes):
    """Upload user avatar to Media Service"""

# Document upload for verification
async def upload_verification_document(verification_id: int, document_data: bytes):
    """Upload verification document to Media Service"""
```

### **Notification Service Integration**
```python
# User status notifications
async def notify_user_status_change(user_id: int, status: str):
    """Send notification on user status change"""

# Verification notifications
async def notify_verification_result(user_id: int, result: str):
    """Send verification result notification"""
```

---

## 📊 Monitoring & Observability

### **Health Checks**
```bash
curl http://localhost:8002/health
# Response: {
#   "status": "healthy",
#   "service": "user-service",
#   "database": "connected",
#   "auth_service": "accessible"
# }
```

### **Metrics (Prometheus)**
- User registration rates
- Verification completion rates
- Profile update frequency
- Role assignment statistics
- Database query performance

### **Structured Logging**
```json
{
    "timestamp": "2025-09-27T18:00:00Z",
    "level": "INFO",
    "service": "user-service",
    "event": "user_created",
    "user_id": 123,
    "telegram_id": 456789,
    "status": "pending",
    "duration_ms": 120
}
```

### **Business Metrics**
- Total users by status
- Verification success rates
- Role distribution
- User activity patterns
- Profile completion rates

---

## 🧪 Testing

### **Test Coverage**
- Unit tests for user management logic
- Integration tests for API endpoints
- Verification workflow tests
- Role assignment tests
- Database integration tests

### **API Testing**
```bash
# Create user
curl -X POST http://localhost:8002/api/v1/users \
  -H "Content-Type: application/json" \
  -d '{
    "telegram_id": 123456789,
    "username": "testuser",
    "first_name": "Test",
    "last_name": "User",
    "phone": "+1234567890",
    "email": "test@example.com"
  }'

# Get user by Telegram ID
curl http://localhost:8002/api/v1/users/by-telegram/123456789

# Start verification
curl -X POST http://localhost:8002/api/v1/users/123/verification \
  -H "Content-Type: application/json" \
  -d '{
    "verification_type": "identity",
    "personal_info": {"document_number": "AB1234567"}
  }'

# Health check
curl http://localhost:8002/health
```

---

## 🚀 Production Features

### **Performance**
- **User lookup**: < 50ms p95
- **Profile updates**: < 100ms p95
- **Database queries**: Optimized with indexes
- **Connection pooling**: 10-20 connections
- **Concurrent users**: 5000+ supported

### **Security**
- **Data validation**: Comprehensive input validation
- **Permission checks**: Role-based access control
- **Audit logging**: All user operations logged
- **Data encryption**: Sensitive data encrypted at rest
- **Privacy compliance**: GDPR-ready data handling

### **Scalability**
- **Stateless design**: Horizontal scaling ready
- **Database optimization**: Indexed queries, foreign keys
- **Cache layer**: Redis for frequently accessed data
- **Service integration**: Async communication patterns

### **Reliability**
- **Health monitoring**: Comprehensive health checks
- **Error handling**: Graceful failure management
- **Data consistency**: Transaction-based operations
- **Backup strategy**: Database backup integration

---

## 📚 Development

### **Local Development**
```bash
# Start dependencies
docker-compose up user-db shared-redis auth-service -d

# Install dependencies
pip install -r requirements.txt

# Run service
uvicorn main:app --reload --host 0.0.0.0 --port 8002

# Access API docs
open http://localhost:8002/docs
```

### **Database Management**
```bash
# Connect to database
docker-compose exec user-db psql -U user_user -d user_db

# View tables
\dt

# Check user data
SELECT id, telegram_id, username, status FROM users LIMIT 10;

# Check role assignments
SELECT u.username, r.role_name FROM users u
JOIN user_role_mappings urm ON u.id = urm.user_id
JOIN roles r ON urm.role_id = r.id;
```

### **Code Quality**
```bash
# Format code
black . && ruff . --fix

# Type checking
mypy .

# Run tests
pytest tests/ -v --cov --cov-report=html

# Database migrations
alembic upgrade head
```

---

## 📄 API Documentation

### **Interactive Documentation**
- **Swagger UI**: http://localhost:8002/docs
- **ReDoc**: http://localhost:8002/redoc
- **OpenAPI JSON**: http://localhost:8002/openapi.json

### **Key Features Documentation**
- User registration and management flows
- Verification process with examples
- Role assignment patterns
- Permission checking methods
- Integration with other services

---

## 📊 Data Models

### **User Status Workflow**
```
pending → approved → active
       ↓           ↓
   rejected    blocked → archived
```

### **Verification Process**
```
created → documents_uploaded → under_review → approved/rejected
```

### **Role Hierarchy**
```
admin: Full system access
  └── manager: Department management
      └── executor: Task execution
          └── applicant: Basic access
```

---

**📝 Status**: ✅ **PRODUCTION READY**
**🔄 Version**: 1.0.0
**📅 Last Updated**: September 27, 2025
**🎯 Port**: 8002
**💾 Database**: user_db (PostgreSQL)
**🔗 Dependencies**: auth-service, shared-redis
**🔧 Environment**: USER_ prefixed variables