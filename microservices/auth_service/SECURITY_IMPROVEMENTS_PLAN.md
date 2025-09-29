# 🔐 Auth Service Security Improvements Plan
**UK Management Bot - Устранение Security Limitations**

---

## 🚨 ТЕКУЩИЕ ПРОБЛЕМЫ

### ❌ **Token Revocation: Impossible without storage**
### ❌ **Key Rotation: Not implemented**
### ❌ **Token Audit: No database logging**
### ❌ **Monitoring: No usage metrics**

---

## 🛠️ ПЛАН УСТРАНЕНИЯ

### **1. TOKEN REVOCATION - Реализация отзыва токенов**

#### **1.1 Создать SQLAlchemy модель для хранения токенов**
```python
# auth_service/models/service_token.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class ServiceToken(Base):
    __tablename__ = "service_tokens"

    id = Column(Integer, primary_key=True)
    service_name = Column(String(50), nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False)  # SHA-256 hash
    is_active = Column(Boolean, default=True, nullable=False)
    permissions = Column(JSON, nullable=False, default=list)

    # Metadata
    issued_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    last_used_at = Column(DateTime)

    # Tracking
    created_by = Column(String(100))  # User/service that created token
    revoked_at = Column(DateTime)
    revoked_by = Column(String(100))
    revoked_reason = Column(Text)

    # Usage tracking
    usage_count = Column(Integer, default=0)
    last_ip = Column(String(45))  # IPv6 compatible

    # Indexes
    __table_args__ = (
        Index('idx_service_tokens_active', 'service_name', 'is_active'),
        Index('idx_service_tokens_hash', 'token_hash'),
        Index('idx_service_tokens_expires', 'expires_at'),
    )
```

#### **1.2 Обновить ServiceTokenManager для persistence**
```python
# auth_service/services/service_token.py
import hashlib
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from models.service_token import ServiceToken

class ServiceTokenManager:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.secret_key = settings.jwt_secret_key

    async def generate_service_token(
        self,
        service_name: str,
        permissions: list = None,
        created_by: str = None
    ) -> dict:
        """Generate and store service token"""

        # 1. Generate JWT token
        payload = {
            "service_name": service_name,
            "permissions": permissions or [],
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(days=30)
        }
        token = jwt.encode(payload, self.secret_key, algorithm="HS256")

        # 2. Store token in database
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        db_token = ServiceToken(
            service_name=service_name,
            token_hash=token_hash,
            is_active=True,
            permissions=permissions or [],
            issued_at=datetime.utcnow(),
            expires_at=payload["exp"],
            created_by=created_by
        )

        self.db.add(db_token)
        await self.db.commit()

        # 3. Log token generation
        await self._log_token_event("token_generated", service_name, token_hash)

        return {
            "token": token,
            "token_id": db_token.id,
            "expires_at": payload["exp"],
            "permissions": permissions or []
        }

    async def revoke_token(self, token: str, revoked_by: str, reason: str = None) -> bool:
        """Revoke service token"""
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        # Find and revoke token
        db_token = await self.db.query(ServiceToken).filter_by(
            token_hash=token_hash,
            is_active=True
        ).first()

        if not db_token:
            return False

        db_token.is_active = False
        db_token.revoked_at = datetime.utcnow()
        db_token.revoked_by = revoked_by
        db_token.revoked_reason = reason

        await self.db.commit()

        # Log revocation
        await self._log_token_event("token_revoked", db_token.service_name, token_hash)

        return True

    async def validate_service_token(self, token: str, ip_address: str = None) -> dict:
        """Validate service token with database check"""
        try:
            # 1. Decode JWT
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])

            # 2. Check token in database
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            db_token = await self.db.query(ServiceToken).filter_by(
                token_hash=token_hash,
                is_active=True
            ).first()

            if not db_token:
                await self._log_token_event("token_validation_failed", payload.get("service_name"), token_hash)
                return None

            # 3. Check expiration
            if datetime.utcnow() > db_token.expires_at:
                # Auto-revoke expired token
                db_token.is_active = False
                await self.db.commit()
                return None

            # 4. Update usage statistics
            db_token.usage_count += 1
            db_token.last_used_at = datetime.utcnow()
            if ip_address:
                db_token.last_ip = ip_address
            await self.db.commit()

            return {
                "service_name": db_token.service_name,
                "permissions": db_token.permissions,
                "token_id": db_token.id
            }

        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
```

#### **1.3 Добавить API endpoints для управления токенами**
```python
# auth_service/api/v1/service_tokens.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

router = APIRouter()

class TokenRevocationRequest(BaseModel):
    token: str
    reason: str

@router.post("/revoke")
async def revoke_service_token(
    request: TokenRevocationRequest,
    admin_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Revoke service token"""
    token_manager = ServiceTokenManager(db)

    success = await token_manager.revoke_token(
        token=request.token,
        revoked_by=admin_user["username"],
        reason=request.reason
    )

    if not success:
        raise HTTPException(status_code=404, detail="Token not found or already revoked")

    return {"success": True, "message": "Token revoked successfully"}

@router.get("/list/{service_name}")
async def list_service_tokens(
    service_name: str,
    admin_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List active tokens for service"""
    tokens = await db.query(ServiceToken).filter_by(
        service_name=service_name,
        is_active=True
    ).all()

    return [
        {
            "id": token.id,
            "issued_at": token.issued_at,
            "expires_at": token.expires_at,
            "last_used_at": token.last_used_at,
            "usage_count": token.usage_count,
            "permissions": token.permissions
        }
        for token in tokens
    ]
```

---

### **2. KEY ROTATION - Ротация ключей**

#### **2.1 Создать модель для хранения ключей**
```python
# auth_service/models/jwt_key.py
class JWTKey(Base):
    __tablename__ = "jwt_keys"

    id = Column(Integer, primary_key=True)
    key_id = Column(String(32), unique=True, nullable=False)  # UUID
    algorithm = Column(String(10), nullable=False, default="HS256")
    secret_key = Column(Text, nullable=False)  # Encrypted

    # Status
    is_active = Column(Boolean, default=False)
    is_primary = Column(Boolean, default=False)  # Current signing key

    # Lifecycle
    created_at = Column(DateTime, nullable=False)
    activated_at = Column(DateTime)
    retired_at = Column(DateTime)

    # Rotation schedule
    rotate_after_days = Column(Integer, default=90)
    next_rotation = Column(DateTime)
```

#### **2.2 Реализовать ротацию ключей**
```python
# auth_service/services/key_rotation.py
import uuid
import secrets
from cryptography.fernet import Fernet

class KeyRotationManager:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.encryption_key = settings.key_encryption_key

    async def rotate_jwt_keys(self) -> dict:
        """Rotate JWT signing keys"""

        # 1. Generate new key
        new_secret = secrets.token_urlsafe(64)
        key_id = str(uuid.uuid4())

        # 2. Encrypt secret for storage
        f = Fernet(self.encryption_key)
        encrypted_secret = f.encrypt(new_secret.encode())

        # 3. Create new key record
        new_key = JWTKey(
            key_id=key_id,
            secret_key=encrypted_secret.decode(),
            is_active=True,
            created_at=datetime.utcnow(),
            next_rotation=datetime.utcnow() + timedelta(days=90)
        )

        # 4. Deactivate old primary key
        old_primary = await self.db.query(JWTKey).filter_by(is_primary=True).first()
        if old_primary:
            old_primary.is_primary = False
            old_primary.retired_at = datetime.utcnow()

        # 5. Set new key as primary
        new_key.is_primary = True
        new_key.activated_at = datetime.utcnow()

        self.db.add(new_key)
        await self.db.commit()

        # 6. Update settings with new key
        settings.jwt_secret_key = new_secret
        settings.jwt_key_id = key_id

        return {
            "key_id": key_id,
            "rotated_at": datetime.utcnow(),
            "next_rotation": new_key.next_rotation
        }

    async def get_active_keys(self) -> list:
        """Get all active keys for validation"""
        keys = await self.db.query(JWTKey).filter_by(is_active=True).all()

        f = Fernet(self.encryption_key)
        return [
            {
                "key_id": key.key_id,
                "secret": f.decrypt(key.secret_key.encode()).decode(),
                "is_primary": key.is_primary
            }
            for key in keys
        ]

# Scheduled task for automatic rotation
from celery import Celery

@celery.task
async def auto_rotate_keys():
    """Automatic key rotation task"""
    db = get_db_session()
    key_manager = KeyRotationManager(db)

    # Check if rotation needed
    primary_key = await db.query(JWTKey).filter_by(is_primary=True).first()
    if primary_key and datetime.utcnow() >= primary_key.next_rotation:
        result = await key_manager.rotate_jwt_keys()
        logger.info(f"JWT keys rotated: {result}")
```

---

### **3. TOKEN AUDIT - Логирование токенов**

#### **3.1 Создать модель для аудита токенов**
```python
# auth_service/models/token_audit.py
class TokenAuditLog(Base):
    __tablename__ = "token_audit_logs"

    id = Column(Integer, primary_key=True)

    # Token info
    token_hash = Column(String(64), nullable=False, index=True)
    service_name = Column(String(50), nullable=False)

    # Event details
    event_type = Column(String(50), nullable=False)  # generated, validated, revoked, expired
    event_status = Column(String(20), nullable=False)  # success, failure, error

    # Context
    ip_address = Column(String(45))
    user_agent = Column(Text)
    request_id = Column(String(36))  # UUID for tracing

    # Additional data
    permissions_requested = Column(JSON)
    validation_result = Column(JSON)
    error_details = Column(Text)

    # Timestamp
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Indexes
    __table_args__ = (
        Index('idx_token_audit_service', 'service_name', 'created_at'),
        Index('idx_token_audit_hash', 'token_hash', 'created_at'),
        Index('idx_token_audit_event', 'event_type', 'created_at'),
    )
```

#### **3.2 Реализовать аудит сервис**
```python
# auth_service/services/token_audit.py
class TokenAuditService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_token_event(
        self,
        event_type: str,
        token_hash: str,
        service_name: str,
        event_status: str = "success",
        **kwargs
    ):
        """Log token-related event"""

        audit_log = TokenAuditLog(
            token_hash=token_hash,
            service_name=service_name,
            event_type=event_type,
            event_status=event_status,
            ip_address=kwargs.get("ip_address"),
            user_agent=kwargs.get("user_agent"),
            request_id=kwargs.get("request_id"),
            permissions_requested=kwargs.get("permissions"),
            validation_result=kwargs.get("result"),
            error_details=kwargs.get("error"),
            created_at=datetime.utcnow()
        )

        self.db.add(audit_log)
        await self.db.commit()

    async def get_token_usage_stats(self, service_name: str, days: int = 30) -> dict:
        """Get token usage statistics"""
        since = datetime.utcnow() - timedelta(days=days)

        stats = await self.db.execute(
            """
            SELECT
                event_type,
                event_status,
                COUNT(*) as count,
                DATE(created_at) as date
            FROM token_audit_logs
            WHERE service_name = :service_name
            AND created_at >= :since
            GROUP BY event_type, event_status, DATE(created_at)
            ORDER BY date DESC
            """,
            {"service_name": service_name, "since": since}
        )

        return [dict(row) for row in stats.fetchall()]

    async def detect_suspicious_activity(self, hours: int = 24) -> list:
        """Detect suspicious token activity"""
        since = datetime.utcnow() - timedelta(hours=hours)

        # Multiple failed validations from same IP
        suspicious = await self.db.execute(
            """
            SELECT
                ip_address,
                service_name,
                COUNT(*) as failed_attempts,
                MAX(created_at) as last_attempt
            FROM token_audit_logs
            WHERE event_type = 'token_validation_failed'
            AND created_at >= :since
            GROUP BY ip_address, service_name
            HAVING COUNT(*) >= 10
            ORDER BY failed_attempts DESC
            """,
            {"since": since}
        )

        return [dict(row) for row in suspicious.fetchall()]
```

---

### **4. MONITORING - Метрики и мониторинг**

#### **4.1 Добавить Prometheus metrics**
```python
# auth_service/monitoring/metrics.py
from prometheus_client import Counter, Histogram, Gauge, generate_latest
import time

# Metrics definitions
token_operations_total = Counter(
    'auth_service_token_operations_total',
    'Total token operations',
    ['operation', 'service_name', 'status']
)

token_validation_duration = Histogram(
    'auth_service_token_validation_duration_seconds',
    'Token validation duration',
    ['service_name']
)

active_tokens_gauge = Gauge(
    'auth_service_active_tokens',
    'Number of active tokens',
    ['service_name']
)

failed_validations_total = Counter(
    'auth_service_failed_validations_total',
    'Total failed token validations',
    ['service_name', 'reason']
)

class TokenMetrics:
    @staticmethod
    def record_token_generated(service_name: str):
        token_operations_total.labels(
            operation='generated',
            service_name=service_name,
            status='success'
        ).inc()

    @staticmethod
    def record_token_validation(service_name: str, duration: float, success: bool):
        token_validation_duration.labels(service_name=service_name).observe(duration)

        status = 'success' if success else 'failure'
        token_operations_total.labels(
            operation='validated',
            service_name=service_name,
            status=status
        ).inc()

        if not success:
            failed_validations_total.labels(
                service_name=service_name,
                reason='invalid_token'
            ).inc()

    @staticmethod
    def record_token_revoked(service_name: str):
        token_operations_total.labels(
            operation='revoked',
            service_name=service_name,
            status='success'
        ).inc()

    @staticmethod
    async def update_active_tokens_count(db: AsyncSession):
        """Update active tokens gauge"""
        counts = await db.execute(
            """
            SELECT service_name, COUNT(*) as count
            FROM service_tokens
            WHERE is_active = true
            GROUP BY service_name
            """
        )

        for row in counts.fetchall():
            active_tokens_gauge.labels(service_name=row.service_name).set(row.count)
```

#### **4.2 Добавить /metrics endpoint**
```python
# auth_service/main.py
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from monitoring.metrics import TokenMetrics

@app.get("/metrics")
async def get_metrics(db: AsyncSession = Depends(get_db)):
    """Prometheus metrics endpoint"""

    # Update dynamic metrics
    await TokenMetrics.update_active_tokens_count(db)

    # Generate metrics
    metrics_data = generate_latest()

    return Response(
        content=metrics_data,
        media_type=CONTENT_TYPE_LATEST
    )
```

#### **4.3 Интеграция с middleware**
```python
# auth_service/middleware/metrics_middleware.py
import time
from monitoring.metrics import TokenMetrics

class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Track token validation requests
        if request.url.path.startswith("/api/v1/internal/validate"):
            start_time = time.time()

            response = await call_next(request)

            duration = time.time() - start_time
            success = response.status_code == 200

            # Extract service name from request
            service_name = request.headers.get("X-Service-Name", "unknown")

            TokenMetrics.record_token_validation(service_name, duration, success)

            return response

        return await call_next(request)
```

---

## 📋 ПЛАН РЕАЛИЗАЦИИ (6-8 недель)

### **Неделя 1-2: Token Storage & Revocation**
- [ ] Создать SQLAlchemy модели (ServiceToken, JWTKey, TokenAuditLog)
- [ ] Обновить ServiceTokenManager для persistence
- [ ] Добавить API endpoints для управления токенами
- [ ] Тестирование revocation functionality

### **Неделя 3-4: Key Rotation**
- [ ] Реализовать KeyRotationManager
- [ ] Добавить encryption для хранения ключей
- [ ] Создать scheduled task для автоматической ротации
- [ ] Тестирование key rotation

### **Неделя 5-6: Audit & Monitoring**
- [ ] Реализовать TokenAuditService
- [ ] Добавить comprehensive logging
- [ ] Интегрировать Prometheus metrics
- [ ] Создать Grafana dashboards

### **Неделя 7-8: Security Hardening**
- [ ] Добавить anomaly detection
- [ ] Реализовать rate limiting для token endpoints
- [ ] Security testing & penetration testing
- [ ] Documentation и deployment

---

## 🎯 РЕЗУЛЬТАТ

После реализации Auth Service будет иметь:

### ✅ **Token Revocation**
- Возможность отзывать токены в real-time
- Централизованное управление токенами
- API для администрирования

### ✅ **Key Rotation**
- Автоматическая ротация ключей каждые 90 дней
- Encrypted storage ключей
- Graceful transition между ключами

### ✅ **Token Audit**
- Полное логирование всех token операций
- Статистика использования
- Обнаружение подозрительной активности

### ✅ **Monitoring**
- Prometheus metrics для всех token операций
- Grafana dashboards
- Alerts на аномальную активность

### 🔐 **Production-Ready Security**
- Enterprise-grade token management
- Compliance с security best practices
- Масштабируемая архитектура

---

**📅 Дата создания**: 29 сентября 2025
**⏱️ Время реализации**: 6-8 недель
**🎯 Приоритет**: 🔴 КРИТИЧЕСКИЙ (Security)
**👥 Команда**: Backend Developer + Security Engineer + DevOps