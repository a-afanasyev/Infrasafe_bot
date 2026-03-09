# Web Dashboard + TWA Expansion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Расширить UK Management Bot веб-дашбордом для менеджеров (канбан + колл-центр) и Telegram Mini App для жителей (создание заявок, статусы, чат).

**Architecture:** Два контейнера — `app` (бот, без изменений) и `api` (новый FastAPI + uvicorn + async SQLAlchemy + WebSocket). Общая PostgreSQL, Redis db0 для FSM, db1 для Pub/Sub. Один `frontend` контейнер (React, Vite) для веб-дашборда и TWA.

**Tech Stack:** Python 3.11, FastAPI, uvicorn, async SQLAlchemy, python-jose (JWT), passlib (bcrypt), slowapi (rate limiting), Redis Pub/Sub, React 18 + TypeScript, Vite, Zustand, React Query, shadcn/ui, Tailwind CSS, @dnd-kit/core, @twa-dev/sdk, Recharts.

**Design doc:** `docs/plans/2026-03-10-web-twa-expansion-design.md`

---

## Phase 1: Foundation — Alembic + DB Migrations + API Container

### Task 1: Настроить Alembic

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/versions/` (директория)

**Step 1: Добавить зависимости в requirements.txt**

```
# JWT + Auth
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4

# Rate limiting
slowapi>=0.1.9
```

Дописать в конец `requirements.txt`.

**Step 2: Инициализировать Alembic**

```bash
cd /path/to/UK
alembic init alembic
```

**Step 3: Настроить `alembic/env.py`**

Заменить содержимое `alembic/env.py`:

```python
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from uk_management_bot.database.session import Base
from uk_management_bot.database.models import *  # noqa: F401,F403
from uk_management_bot.config.settings import settings

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

**Step 4: Проверить что Alembic видит модели**

```bash
alembic current
```

Ожидаемо: `INFO  [alembic.runtime.migration] Context impl PostgreSQLImpl.`

**Step 5: Commit**

```bash
git add alembic/ alembic.ini requirements.txt
git commit -m "chore: setup alembic and add jwt/passlib/slowapi deps"
```

---

### Task 2: Миграция — добавить поля в users

**Files:**
- Create: `alembic/versions/001_add_auth_fields_to_users.py`

**Step 1: Создать миграцию**

```bash
alembic revision --autogenerate -m "add_auth_fields_to_users"
```

**Step 2: Проверить сгенерированный файл**

Убедиться что в `upgrade()` есть `op.add_column` для полей: `password_hash`, `email`, `password_reset_token`, `password_reset_expires_at`. Если autogenerate не поймал — добавить вручную:

```python
def upgrade() -> None:
    op.add_column('users', sa.Column('password_hash', sa.String(255), nullable=True))
    op.add_column('users', sa.Column('email', sa.String(255), nullable=True))
    op.add_column('users', sa.Column('password_reset_token', sa.String(64), nullable=True))
    op.add_column('users', sa.Column('password_reset_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

def downgrade() -> None:
    op.drop_index('ix_users_email', 'users')
    op.drop_column('users', 'password_reset_expires_at')
    op.drop_column('users', 'password_reset_token')
    op.drop_column('users', 'email')
    op.drop_column('users', 'password_hash')
```

**Step 3: Обновить модель User**

В `uk_management_bot/database/models/user.py` добавить поля:

```python
# Web auth fields
password_hash = Column(String(255), nullable=True)
email = Column(String(255), nullable=True, unique=True, index=True)
password_reset_token = Column(String(64), nullable=True)
password_reset_expires_at = Column(DateTime(timezone=True), nullable=True)
```

**Step 4: Применить миграцию**

```bash
alembic upgrade head
```

Ожидаемо: `Running upgrade  -> 001_add_auth_fields_to_users`

**Step 5: Commit**

```bash
git add alembic/versions/ uk_management_bot/database/models/user.py
git commit -m "feat(db): add auth fields to users (password_hash, email, reset)"
```

---

### Task 3: Миграция — requests.source, request_comments поля, notifications.request_number, refresh_tokens

**Files:**
- Create: `alembic/versions/002_add_web_fields.py`

**Step 1: Создать миграцию**

```bash
alembic revision -m "add_web_fields"
```

**Step 2: Заполнить миграцию**

```python
import sqlalchemy as sa
from alembic import op

def upgrade() -> None:
    # requests.source
    op.add_column('requests', sa.Column('source', sa.String(20), nullable=True, server_default='bot'))
    op.create_index('ix_requests_source', 'requests', ['source'])

    # request_comments
    op.add_column('request_comments', sa.Column('is_internal', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('request_comments', sa.Column('media_files', sa.JSON(), nullable=True))

    # notifications.request_number (уже есть таблица, добавляем FK-поле)
    op.add_column('notifications', sa.Column(
        'request_number_fk', sa.String(10), sa.ForeignKey('requests.request_number'), nullable=True
    ))

    # refresh_tokens — новая таблица
    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('device_info', sa.Text(), nullable=True),
    )
    op.create_index('ix_refresh_tokens_user_id', 'refresh_tokens', ['user_id'])
    op.create_index('ix_refresh_tokens_token_hash', 'refresh_tokens', ['token_hash'])

def downgrade() -> None:
    op.drop_table('refresh_tokens')
    op.drop_column('notifications', 'request_number_fk')
    op.drop_column('request_comments', 'media_files')
    op.drop_column('request_comments', 'is_internal')
    op.drop_index('ix_requests_source', 'requests')
    op.drop_column('requests', 'source')
```

**Step 3: Обновить модели**

`uk_management_bot/database/models/request.py` — добавить:
```python
source = Column(String(20), default='bot', nullable=True)
```

`uk_management_bot/database/models/request_comment.py` — добавить:
```python
is_internal = Column(Boolean, default=False, nullable=False)
media_files = Column(JSON, default=list, nullable=True)
```

`uk_management_bot/database/models/notification.py` — добавить:
```python
request_number_fk = Column(String(10), ForeignKey('requests.request_number'), nullable=True)
```

**Step 4: Создать модель RefreshToken**

Создать файл `uk_management_bot/database/models/refresh_token.py`:

```python
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.sql import func
from uk_management_bot.database.session import Base

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    device_info = Column(Text, nullable=True)

    @property
    def is_valid(self) -> bool:
        from datetime import datetime, timezone
        return self.revoked_at is None and self.expires_at > datetime.now(timezone.utc)
```

Добавить импорт в `uk_management_bot/database/models/__init__.py`:
```python
from .refresh_token import RefreshToken
```

**Step 5: Применить**

```bash
alembic upgrade head
```

**Step 6: Commit**

```bash
git add alembic/versions/ uk_management_bot/database/models/
git commit -m "feat(db): add source/is_internal/refresh_tokens for web API"
```

---

### Task 4: Создать структуру api-пакета

**Files:**
- Create: `uk_management_bot/api/__init__.py`
- Create: `uk_management_bot/api/main.py`
- Create: `uk_management_bot/api/dependencies.py`
- Create: `uk_management_bot/api/auth/` (пакет)
- Create: `uk_management_bot/api/requests/` (пакет)
- Create: `uk_management_bot/api/callcenter/` (пакет)
- Create: `uk_management_bot/api/notifications/` (пакет)
- Create: `uk_management_bot/api/profile/` (пакет)
- Create: `uk_management_bot/api/ws/` (пакет)

**Step 1: Создать директории**

```bash
mkdir -p uk_management_bot/api/auth
mkdir -p uk_management_bot/api/requests
mkdir -p uk_management_bot/api/callcenter
mkdir -p uk_management_bot/api/notifications
mkdir -p uk_management_bot/api/profile
mkdir -p uk_management_bot/api/ws
touch uk_management_bot/api/__init__.py
touch uk_management_bot/api/auth/__init__.py
touch uk_management_bot/api/requests/__init__.py
touch uk_management_bot/api/callcenter/__init__.py
touch uk_management_bot/api/notifications/__init__.py
touch uk_management_bot/api/profile/__init__.py
touch uk_management_bot/api/ws/__init__.py
```

**Step 2: Создать `uk_management_bot/api/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from uk_management_bot.api.auth.router import router as auth_router
from uk_management_bot.api.requests.router import router as requests_router
from uk_management_bot.api.callcenter.router import router as callcenter_router
from uk_management_bot.api.notifications.router import router as notifications_router
from uk_management_bot.api.profile.router import router as profile_router
from uk_management_bot.api.ws.router import router as ws_router
from uk_management_bot.config.settings import settings

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    yield
    # shutdown


app = FastAPI(
    title="UK Management API",
    version="2.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
allowed_origins = [
    "https://web.telegram.org",
]
if settings.DEBUG:
    allowed_origins.extend(["http://localhost:3000", "http://localhost:5173"])
else:
    # Добавить production URL фронтенда через env
    if hasattr(settings, 'FRONTEND_URL') and settings.FRONTEND_URL:
        allowed_origins.append(settings.FRONTEND_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_router, prefix="/api/v2/auth", tags=["auth"])
app.include_router(requests_router, prefix="/api/v2/requests", tags=["requests"])
app.include_router(callcenter_router, prefix="/api/v2/callcenter", tags=["callcenter"])
app.include_router(notifications_router, prefix="/api/v2/notifications", tags=["notifications"])
app.include_router(profile_router, prefix="/api/v2/profile", tags=["profile"])
app.include_router(ws_router, prefix="/ws/v2", tags=["websocket"])


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "api"}
```

**Step 3: Создать `uk_management_bot/api/dependencies.py`**

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from uk_management_bot.database.session import AsyncSessionLocal
from uk_management_bot.api.auth.service import verify_access_token
from uk_management_bot.database.models.user import User
from sqlalchemy import select
from typing import AsyncGenerator

security = HTTPBearer()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    payload = verify_access_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if user.status == "blocked":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account blocked")

    return user


def require_roles(*roles: str):
    """Decorator factory: require_roles('manager', 'admin')"""
    async def checker(user: User = Depends(get_current_user)) -> User:
        import json
        user_roles = json.loads(user.roles) if user.roles else [user.role]
        if not any(r in user_roles for r in roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user
    return checker
```

**Step 4: Создать заглушки роутеров**

Для каждого из `auth/router.py`, `requests/router.py`, `callcenter/router.py`, `notifications/router.py`, `profile/router.py`, `ws/router.py` создать минимальный файл:

```python
# auth/router.py (аналогично для остальных, менять prefix не нужно)
from fastapi import APIRouter
router = APIRouter()
```

**Step 5: Запустить и проверить**

```bash
cd uk_management_bot
python -c "from api.main import app; print('OK')"
```

Ожидаемо: `OK`

**Step 6: Commit**

```bash
git add uk_management_bot/api/
git commit -m "feat(api): scaffold api package structure with FastAPI app"
```

---

### Task 5: Добавить api-сервис в Docker Compose

**Files:**
- Modify: `docker-compose.yml`
- Create: `Dockerfile.api`

**Step 1: Создать `Dockerfile.api`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "uk_management_bot.api.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
```

**Step 2: Добавить сервис в `docker-compose.yml`**

После блока `app:` добавить:

```yaml
  api:
    build:
      context: .
      dockerfile: Dockerfile.api
    container_name: uk-management-api
    restart: unless-stopped
    env_file:
      - .env
    environment:
      - DATABASE_URL=postgresql://uk_bot:uk_bot_password@postgres:5432/uk_management
      - REDIS_URL=redis://redis:6379/0
      - REDIS_PUBSUB_URL=redis://redis:6379/1
      - LOG_LEVEL=INFO
      - PYTHONUNBUFFERED=1
    ports:
      - "8080:8080"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - uk-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 20s
```

Также добавить `FRONTEND_URL` и `REDIS_PUBSUB_URL` в список переменных settings:

В `uk_management_bot/config/settings.py` добавить:
```python
FRONTEND_URL: str = ""
REDIS_PUBSUB_URL: str = "redis://redis:6379/1"
```

**Step 3: Проверить сборку**

```bash
docker compose build api
docker compose up api -d
curl http://localhost:8080/health
```

Ожидаемо: `{"status":"healthy","service":"api"}`

**Step 4: Commit**

```bash
git add Dockerfile.api docker-compose.yml uk_management_bot/config/settings.py
git commit -m "feat(docker): add api service container with uvicorn"
```

---

## Phase 2: JWT Auth

### Task 6: JWT утилиты и сервис авторизации

**Files:**
- Create: `uk_management_bot/api/auth/service.py`
- Create: `uk_management_bot/api/auth/schemas.py`
- Create: `tests/api/test_auth_service.py`

**Step 1: Написать тест**

Создать `tests/api/test_auth_service.py`:

```python
import pytest
from datetime import datetime, timezone, timedelta
from uk_management_bot.api.auth.service import (
    create_access_token, verify_access_token,
    hash_password, verify_password,
    verify_twa_init_data,
)

def test_access_token_roundtrip():
    token = create_access_token(user_id=42, roles=["manager"])
    payload = verify_access_token(token)
    assert payload["sub"] == "42"
    assert payload["roles"] == ["manager"]

def test_expired_token_returns_none():
    token = create_access_token(user_id=1, roles=["applicant"], expires_delta=timedelta(seconds=-1))
    assert verify_access_token(token) is None

def test_password_hash_and_verify():
    hashed = hash_password("MySecret123")
    assert verify_password("MySecret123", hashed) is True
    assert verify_password("WrongPassword", hashed) is False

def test_twa_init_data_invalid_hash():
    result = verify_twa_init_data("user=%7B%22id%22%3A123%7D&hash=badhash", "fake_bot_token")
    assert result is None
```

**Step 2: Запустить тест — убедиться что падает**

```bash
pytest tests/api/test_auth_service.py -v
```

Ожидаемо: `ImportError` или `ModuleNotFoundError`

**Step 3: Реализовать `uk_management_bot/api/auth/service.py`**

```python
import hashlib
import hmac
import json
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import unquote, parse_qsl

from jose import jwt, JWTError
from passlib.context import CryptContext

from uk_management_bot.config.settings import settings

SECRET_KEY = settings.INVITE_SECRET  # переиспользуем существующий секрет
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(
    user_id: int,
    roles: list[str],
    expires_delta: Optional[timedelta] = None,
) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {"sub": str(user_id), "roles": roles, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def create_refresh_token_value() -> str:
    """Генерирует случайный refresh token (hex строку)."""
    import secrets
    return secrets.token_hex(32)


def hash_token(token: str) -> str:
    """SHA-256 хеш для хранения refresh token в БД."""
    return hashlib.sha256(token.encode()).hexdigest()


def verify_telegram_widget(data: dict) -> bool:
    """
    Верификация Telegram Login Widget данных.
    https://core.telegram.org/widgets/login#checking-authorization
    """
    received_hash = data.pop("hash", None)
    if not received_hash:
        return False
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret_key = hashlib.sha256(settings.BOT_TOKEN.encode()).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_hash, received_hash)


def verify_twa_init_data(init_data: str, bot_token: str) -> Optional[dict]:
    """
    Верификация Telegram Mini App initData.
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        return None

    # Парсим user из initData
    user_str = parsed.get("user")
    if user_str:
        try:
            return json.loads(unquote(user_str))
        except json.JSONDecodeError:
            return None
    return parsed
```

**Step 4: Запустить тест**

```bash
pytest tests/api/test_auth_service.py -v
```

Ожидаемо: 4 PASSED

**Step 5: Commit**

```bash
git add uk_management_bot/api/auth/service.py tests/api/
git commit -m "feat(api): add jwt auth service with twa initdata verification"
```

---

### Task 7: Auth роутер — все эндпоинты

**Files:**
- Modify: `uk_management_bot/api/auth/router.py`
- Create: `uk_management_bot/api/auth/schemas.py`

**Step 1: Создать `uk_management_bot/api/auth/schemas.py`**

```python
from pydantic import BaseModel, EmailStr
from typing import Optional


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TelegramWidgetLogin(BaseModel):
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str


class TWALogin(BaseModel):
    init_data: str


class PasswordLogin(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class SetPasswordRequest(BaseModel):
    password: str
    confirm_password: str
```

**Step 2: Реализовать `uk_management_bot/api/auth/router.py`**

```python
import json
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from slowapi import Limiter
from slowapi.util import get_remote_address

from uk_management_bot.api.auth.schemas import (
    TokenResponse, TelegramWidgetLogin, TWALogin,
    PasswordLogin, RefreshRequest, SetPasswordRequest,
)
from uk_management_bot.api.auth.service import (
    verify_telegram_widget, verify_twa_init_data,
    verify_password, hash_password,
    create_access_token, create_refresh_token_value, hash_token,
    REFRESH_TOKEN_EXPIRE_DAYS,
)
from uk_management_bot.api.dependencies import get_db, get_current_user
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.refresh_token import RefreshToken
from uk_management_bot.config.settings import settings

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


def _build_token_response(user: User) -> dict:
    roles = json.loads(user.roles) if user.roles else [user.role]
    access_token = create_access_token(user.id, roles)
    refresh_value = create_refresh_token_value()
    return {"access_token": access_token, "refresh_value": refresh_value, "roles": roles}


async def _save_refresh_token(db: AsyncSession, user_id: int, token_value: str, device_info: str = "") -> None:
    expires = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    rt = RefreshToken(
        user_id=user_id,
        token_hash=hash_token(token_value),
        expires_at=expires,
        device_info=device_info,
    )
    db.add(rt)
    await db.commit()


@router.post("/telegram-widget", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login_telegram_widget(request: Request, data: TelegramWidgetLogin, db: AsyncSession = Depends(get_db)):
    data_dict = data.model_dump()
    if not verify_telegram_widget(data_dict):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Telegram auth data")

    result = await db.execute(select(User).where(User.telegram_id == data.id))
    user = result.scalar_one_or_none()
    if not user or user.status != "approved":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not approved")

    tokens = _build_token_response(user)
    await _save_refresh_token(db, user.id, tokens["refresh_value"])
    return TokenResponse(access_token=tokens["access_token"], refresh_token=tokens["refresh_value"])


@router.post("/twa", response_model=TokenResponse)
@limiter.limit("20/minute")
async def login_twa(request: Request, data: TWALogin, db: AsyncSession = Depends(get_db)):
    user_data = verify_twa_init_data(data.init_data, settings.BOT_TOKEN)
    if not user_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid initData")

    telegram_id = user_data.get("id")
    if not telegram_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No user id in initData")

    result = await db.execute(select(User).where(User.telegram_id == int(telegram_id)))
    user = result.scalar_one_or_none()
    if not user or user.status != "approved":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not approved")

    tokens = _build_token_response(user)
    await _save_refresh_token(db, user.id, tokens["refresh_value"])
    return TokenResponse(access_token=tokens["access_token"], refresh_token=tokens["refresh_value"])


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login_password(request: Request, data: PasswordLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user or not user.password_hash or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if user.status != "approved":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not approved")

    tokens = _build_token_response(user)
    await _save_refresh_token(db, user.id, tokens["refresh_value"])
    return TokenResponse(access_token=tokens["access_token"], refresh_token=tokens["refresh_value"])


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    token_hash = hash_token(data.refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    rt = result.scalar_one_or_none()

    if not rt or not rt.is_valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    # Rotate: revoke old, issue new
    rt.revoked_at = datetime.now(timezone.utc)
    user_result = await db.execute(select(User).where(User.id == rt.user_id))
    user = user_result.scalar_one()

    tokens = _build_token_response(user)
    await _save_refresh_token(db, user.id, tokens["refresh_value"])
    await db.commit()
    return TokenResponse(access_token=tokens["access_token"], refresh_token=tokens["refresh_value"])


@router.post("/logout")
async def logout(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    token_hash = hash_token(data.refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    rt = result.scalar_one_or_none()
    if rt:
        rt.revoked_at = datetime.now(timezone.utc)
        await db.commit()
    return {"ok": True}


@router.post("/set-password")
async def set_password(data: SetPasswordRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if data.password != data.confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passwords do not match")
    if len(data.password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password too short (min 8)")

    result = await db.execute(select(User).where(User.id == user.id))
    db_user = result.scalar_one()
    db_user.password_hash = hash_password(data.password)
    await db.commit()
    return {"ok": True}
```

**Step 3: Запустить API и проверить эндпоинты**

```bash
uvicorn uk_management_bot.api.main:app --reload --port 8080
curl http://localhost:8080/docs
```

Ожидаемо: Swagger UI с 6 auth эндпоинтами.

**Step 4: Commit**

```bash
git add uk_management_bot/api/auth/
git commit -m "feat(api): implement auth endpoints (twa, widget, password, refresh, logout)"
```

---

## Phase 3: REST API для заявок

### Task 8: Schemas для заявок

**Files:**
- Create: `uk_management_bot/api/requests/schemas.py`

```python
from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime


class RequestCard(BaseModel):
    request_number: str
    status: str
    category: str
    urgency: Optional[str]
    source: Optional[str]
    description: Optional[str]
    address: Optional[str]
    apartment_id: Optional[int]
    executor_id: Optional[int]
    executor_name: Optional[str]
    created_at: datetime
    updated_at: datetime
    manager_confirmed: bool

    model_config = {"from_attributes": True}


class KanbanColumn(BaseModel):
    status: str
    count: int
    requests: List[RequestCard]


class KanbanResponse(BaseModel):
    columns: List[KanbanColumn]


class CreateRequestBody(BaseModel):
    category: str
    urgency: str
    description: str
    apartment_id: Optional[int] = None
    address: Optional[str] = None
    source: str = "web"
    media_files: Optional[List[str]] = None


class UpdateRequestBody(BaseModel):
    status: Optional[str] = None
    executor_id: Optional[int] = None
    notes: Optional[str] = None
    completion_report: Optional[str] = None
    manager_confirmed: Optional[bool] = None
    manager_confirmation_notes: Optional[str] = None


class CommentBody(BaseModel):
    text: str
    is_internal: bool = False
    media_files: Optional[List[str]] = None


class CommentOut(BaseModel):
    id: int
    user_id: int
    author_name: Optional[str]
    comment_type: str
    comment_text: str
    is_internal: bool
    created_at: datetime

    model_config = {"from_attributes": True}
```

---

### Task 9: Requests роутер

**Files:**
- Modify: `uk_management_bot/api/requests/router.py`

```python
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from uk_management_bot.api.dependencies import get_db, get_current_user
from uk_management_bot.api.requests.schemas import (
    RequestCard, KanbanResponse, KanbanColumn,
    CreateRequestBody, UpdateRequestBody,
    CommentBody, CommentOut,
)
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_comment import RequestComment
from uk_management_bot.database.models.user import User
from uk_management_bot.services.redis_pubsub import publish_request_event

router = APIRouter()

KANBAN_STATUSES = ["Новая", "В работе", "Закуп", "Уточнение", "Выполнена", "Исполнено", "Принято", "Отменена"]


@router.get("/kanban", response_model=KanbanResponse)
async def get_kanban(
    yard_id: Optional[int] = Query(None),
    executor_id: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Request)
    if yard_id:
        query = query.filter(Request.yard_id == yard_id)
    if executor_id:
        query = query.filter(Request.executor_id == executor_id)
    if category:
        query = query.filter(Request.category == category)

    result = await db.execute(query.order_by(Request.created_at.desc()).limit(500))
    requests = result.scalars().all()

    columns = []
    for st in KANBAN_STATUSES:
        st_requests = [r for r in requests if r.status == st]
        columns.append(KanbanColumn(
            status=st,
            count=len(st_requests),
            requests=[RequestCard.model_validate(r) for r in st_requests],
        ))
    return KanbanResponse(columns=columns)


@router.get("", response_model=list[RequestCard])
async def list_requests(
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    executor_id: Optional[int] = Query(None),
    source: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Request)
    if status:
        query = query.filter(Request.status == status)
    if category:
        query = query.filter(Request.category == category)
    if executor_id:
        query = query.filter(Request.executor_id == executor_id)
    if source:
        query = query.filter(Request.source == source)

    result = await db.execute(query.order_by(Request.created_at.desc()).offset(offset).limit(limit))
    return [RequestCard.model_validate(r) for r in result.scalars().all()]


@router.get("/{request_number}", response_model=RequestCard)
async def get_request(
    request_number: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Request).where(Request.request_number == request_number))
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    return RequestCard.model_validate(req)


@router.post("", response_model=RequestCard, status_code=201)
async def create_request(
    body: CreateRequestBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from datetime import date
    today = date.today().strftime("%y%m%d")
    count_result = await db.execute(
        select(func.count(Request.request_number)).where(
            Request.request_number.like(f"{today}-%")
        )
    )
    count = count_result.scalar() or 0
    request_number = f"{today}-{(count + 1):03d}"

    req = Request(
        request_number=request_number,
        user_id=user.id,
        category=body.category,
        urgency=body.urgency,
        description=body.description,
        apartment_id=body.apartment_id,
        address=body.address,
        status="Новая",
        source=body.source,
        media_files=body.media_files or [],
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)

    await publish_request_event("request.created", RequestCard.model_validate(req).model_dump(mode="json"))
    return RequestCard.model_validate(req)


@router.patch("/{request_number}", response_model=RequestCard)
async def update_request(
    request_number: str,
    body: UpdateRequestBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Request).where(Request.request_number == request_number))
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    old_status = req.status
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(req, field, value)

    await db.commit()
    await db.refresh(req)

    event_data = {"number": request_number, "old_status": old_status, "new_status": req.status}
    await publish_request_event("request.status_changed", event_data)
    return RequestCard.model_validate(req)


@router.get("/{request_number}/comments", response_model=list[CommentOut])
async def get_comments(
    request_number: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    import json as _json
    user_roles = _json.loads(user.roles) if user.roles else [user.role]
    is_manager = any(r in user_roles for r in ["manager", "admin"])

    query = select(RequestComment).where(RequestComment.request_number == request_number)
    if not is_manager:
        query = query.where(RequestComment.is_internal == False)  # noqa

    result = await db.execute(query.order_by(RequestComment.created_at.asc()))
    return result.scalars().all()


@router.post("/{request_number}/comments", response_model=CommentOut, status_code=201)
async def add_comment(
    request_number: str,
    body: CommentBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    comment = RequestComment(
        request_number=request_number,
        user_id=user.id,
        comment_type="clarification",
        comment_text=body.text,
        is_internal=body.is_internal,
        media_files=body.media_files or [],
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return comment
```

**Commit:**

```bash
git add uk_management_bot/api/requests/
git commit -m "feat(api): implement requests CRUD + kanban endpoint"
```

---

### Task 10: Колл-центр роутер

**Files:**
- Modify: `uk_management_bot/api/callcenter/router.py`
- Create: `uk_management_bot/api/callcenter/schemas.py`

**`schemas.py`:**

```python
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class ResidentSearchResult(BaseModel):
    id: int
    telegram_id: int
    full_name: Optional[str]
    phone: Optional[str]
    address: Optional[str]
    requests_count: int

    model_config = {"from_attributes": True}


class CallCenterCreateRequest(BaseModel):
    category: str
    urgency: str
    description: str
    # Если найден житель
    user_id: Optional[int] = None
    apartment_id: Optional[int] = None
    # Если не найден — вручную
    caller_name: Optional[str] = None
    caller_phone: Optional[str] = None
    address: Optional[str] = None
```

**`router.py`:**

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func

from uk_management_bot.api.dependencies import get_db, require_roles
from uk_management_bot.api.callcenter.schemas import ResidentSearchResult, CallCenterCreateRequest
from uk_management_bot.api.requests.schemas import RequestCard
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.request import Request
from datetime import date

router = APIRouter()


@router.get("/search-resident", response_model=list[ResidentSearchResult])
async def search_resident(
    q: str = Query(..., min_length=2),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    result = await db.execute(
        select(User).where(
            or_(
                User.phone.ilike(f"%{q}%"),
                User.first_name.ilike(f"%{q}%"),
                User.last_name.ilike(f"%{q}%"),
            )
        ).limit(10)
    )
    users = result.scalars().all()
    out = []
    for u in users:
        count_result = await db.execute(
            select(func.count(Request.request_number)).where(Request.user_id == u.id)
        )
        full_name = " ".join(filter(None, [u.first_name, u.last_name]))
        out.append(ResidentSearchResult(
            id=u.id,
            telegram_id=u.telegram_id,
            full_name=full_name,
            phone=u.phone,
            address=None,  # можно расширить через UserApartment join
            requests_count=count_result.scalar() or 0,
        ))
    return out


@router.post("/requests", response_model=RequestCard, status_code=201)
async def create_call_center_request(
    body: CallCenterCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    today = date.today().strftime("%y%m%d")
    count_result = await db.execute(
        select(func.count(Request.request_number)).where(
            Request.request_number.like(f"{today}-%")
        )
    )
    count = count_result.scalar() or 0
    request_number = f"{today}-{(count + 1):03d}"

    notes = None
    if body.caller_name or body.caller_phone:
        notes = f"Звонок: {body.caller_name or ''} {body.caller_phone or ''}".strip()

    req = Request(
        request_number=request_number,
        user_id=body.user_id or user.id,
        category=body.category,
        urgency=body.urgency,
        description=body.description,
        apartment_id=body.apartment_id,
        address=body.address,
        status="Новая",
        source="call_center",
        notes=notes,
        media_files=[],
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return RequestCard.model_validate(req)
```

**Commit:**

```bash
git add uk_management_bot/api/callcenter/
git commit -m "feat(api): add call center search and request creation"
```

---

### Task 11: Notifications и Profile роутеры

**Files:**
- Modify: `uk_management_bot/api/notifications/router.py`
- Modify: `uk_management_bot/api/profile/router.py`

**`notifications/router.py`:**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uk_management_bot.api.dependencies import get_db, get_current_user
from uk_management_bot.database.models.notification import Notification
from uk_management_bot.database.models.user import User
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

router = APIRouter()

class NotificationOut(BaseModel):
    id: int
    notification_type: str
    title: Optional[str]
    content: Optional[str]
    is_read: bool
    request_number_fk: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}


@router.get("", response_model=list[NotificationOut])
async def list_notifications(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
    )
    return result.scalars().all()


@router.patch("/{notification_id}/read")
async def mark_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
        )
    )
    n = result.scalar_one_or_none()
    if n:
        n.is_read = True
        await db.commit()
    return {"ok": True}
```

**`profile/router.py`:**

```python
from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uk_management_bot.api.dependencies import get_db, get_current_user
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_verification import UserDocument
from pydantic import BaseModel
from typing import Optional
import json

router = APIRouter()


class ProfileOut(BaseModel):
    id: int
    telegram_id: int
    first_name: Optional[str]
    last_name: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    language: str
    status: str
    verification_status: str
    roles: Optional[str]
    active_role: Optional[str]
    model_config = {"from_attributes": True}


@router.get("", response_model=ProfileOut)
async def get_profile(user: User = Depends(get_current_user)):
    return user


@router.patch("")
async def update_profile(
    language: Optional[str] = None,
    email: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(User).where(User.id == user.id))
    db_user = result.scalar_one()
    if language:
        db_user.language = language
    if email:
        db_user.email = email
    await db.commit()
    return {"ok": True}


@router.post("/documents")
async def upload_document(
    document_type: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Сохранить через Media Service или как Telegram file_id
    # Здесь — заглушка, реальная логика через MediaServiceClient
    content = await file.read()
    # TODO: интегрировать с MediaServiceClient
    return {"ok": True, "document_type": document_type, "filename": file.filename}
```

**Commit:**

```bash
git add uk_management_bot/api/notifications/ uk_management_bot/api/profile/
git commit -m "feat(api): add notifications and profile endpoints"
```

---

## Phase 4: Redis Pub/Sub + WebSocket

### Task 12: Redis Pub/Sub сервис

**Files:**
- Create: `uk_management_bot/services/redis_pubsub.py`
- Create: `tests/services/test_redis_pubsub.py`

**`services/redis_pubsub.py`:**

```python
import json
import redis.asyncio as aioredis
from uk_management_bot.config.settings import settings

CHANNEL = "requests:updates"
_redis_client = None


async def get_pubsub_redis():
    global _redis_client
    if _redis_client is None:
        url = getattr(settings, 'REDIS_PUBSUB_URL', 'redis://redis:6379/1')
        _redis_client = aioredis.from_url(url, decode_responses=True)
    return _redis_client


async def publish_request_event(event_type: str, data: dict) -> None:
    """Публикует событие в Redis Pub/Sub канал. Вызывается из API после изменения заявки."""
    try:
        client = await get_pubsub_redis()
        message = json.dumps({"type": event_type, "data": data})
        await client.publish(CHANNEL, message)
    except Exception:
        pass  # Pub/Sub — best effort, не прерывать основной поток


async def subscribe_to_requests():
    """Возвращает Redis Pub/Sub подписчика для WebSocket handler."""
    client = await get_pubsub_redis()
    pubsub = client.pubsub()
    await pubsub.subscribe(CHANNEL)
    return pubsub
```

**Commit:**

```bash
git add uk_management_bot/services/redis_pubsub.py
git commit -m "feat(services): add redis pub/sub for request events"
```

---

### Task 13: WebSocket роутер

**Files:**
- Modify: `uk_management_bot/api/ws/router.py`

```python
import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from uk_management_bot.api.auth.service import verify_access_token
from uk_management_bot.services.redis_pubsub import subscribe_to_requests

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        self.active.discard(ws) if hasattr(self.active, 'discard') else None
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, message: str):
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


@router.websocket("/kanban")
async def kanban_ws(websocket: WebSocket, token: str = Query(...)):
    payload = verify_access_token(token)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(websocket)

    pubsub = await subscribe_to_requests()
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"])
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
    finally:
        await pubsub.unsubscribe()
```

**Step: Проверить WebSocket**

```bash
# В отдельном терминале запустить api
uvicorn uk_management_bot.api.main:app --port 8080

# Получить токен через /api/v2/auth/login
# Подключиться через websocat или браузер DevTools
# websocat "ws://localhost:8080/ws/v2/kanban?token=<ACCESS_TOKEN>"
```

**Commit:**

```bash
git add uk_management_bot/api/ws/ uk_management_bot/services/redis_pubsub.py
git commit -m "feat(api): add websocket kanban endpoint with redis pub/sub"
```

---

## Phase 5: Frontend — Web Dashboard

### Task 14: Создать React проект

**Files:**
- Create: `frontend/` (новая директория)

**Step 1: Создать проект**

```bash
cd /path/to/UK
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
```

**Step 2: Установить зависимости**

```bash
npm install \
  @tanstack/react-query axios zustand \
  react-router-dom \
  @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities \
  recharts \
  @twa-dev/sdk \
  class-variance-authority clsx tailwind-merge lucide-react

npm install -D tailwindcss postcss autoprefixer @types/node
npx tailwindcss init -p
```

**Step 3: Настроить Tailwind в `frontend/tailwind.config.ts`**

```ts
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: {} },
  plugins: [],
}
```

**Step 4: Базовая структура**

```
frontend/src/
  api/          # axios client + react-query hooks
  components/
    ui/         # shadcn components
    kanban/
    auth/
    requests/
    callcenter/
    twa/
  pages/
    LoginPage.tsx
    DashboardPage.tsx   # Kanban
    RequestsPage.tsx
    StaffPage.tsx
    ReportsPage.tsx
    twa/
      TWAHomePage.tsx
      TWARequestsPage.tsx
      TWACreatePage.tsx
  stores/       # zustand
  hooks/
  types/
  utils/
    isTWA.ts
  App.tsx
  main.tsx
```

**Step 5: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): scaffold react+ts+vite project with deps"
```

---

### Task 15: API клиент и Auth store

**Files:**
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/stores/authStore.ts`

**`frontend/src/api/client.ts`:**

```typescript
import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8080'

export const apiClient = axios.create({ baseURL: BASE_URL })

// Автоматически добавлять JWT токен
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Автоматически обновлять токен при 401
apiClient.interceptors.response.use(
  (r) => r,
  async (error) => {
    if (error.response?.status === 401) {
      const refreshToken = localStorage.getItem('refresh_token')
      if (refreshToken) {
        try {
          const { data } = await axios.post(`${BASE_URL}/api/v2/auth/refresh`, {
            refresh_token: refreshToken,
          })
          localStorage.setItem('access_token', data.access_token)
          localStorage.setItem('refresh_token', data.refresh_token)
          error.config.headers.Authorization = `Bearer ${data.access_token}`
          return apiClient(error.config)
        } catch {
          localStorage.clear()
          window.location.href = '/login'
        }
      }
    }
    return Promise.reject(error)
  }
)
```

**`frontend/src/stores/authStore.ts`:**

```typescript
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { apiClient } from '../api/client'

interface AuthState {
  user: { id: number; roles: string[]; first_name?: string } | null
  isAuthenticated: boolean
  login: (access_token: string, refresh_token: string) => Promise<void>
  logout: () => Promise<void>
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,
      login: async (access_token, refresh_token) => {
        localStorage.setItem('access_token', access_token)
        localStorage.setItem('refresh_token', refresh_token)
        const { data } = await apiClient.get('/api/v2/profile')
        set({ user: data, isAuthenticated: true })
      },
      logout: async () => {
        const refresh_token = localStorage.getItem('refresh_token')
        if (refresh_token) {
          await apiClient.post('/api/v2/auth/logout', { refresh_token }).catch(() => {})
        }
        localStorage.clear()
        set({ user: null, isAuthenticated: false })
      },
    }),
    { name: 'auth-store' }
  )
)
```

**Commit:**

```bash
git add frontend/src/api/ frontend/src/stores/
git commit -m "feat(frontend): add api client with jwt auto-refresh and auth store"
```

---

### Task 16: Страница входа

**Files:**
- Create: `frontend/src/pages/LoginPage.tsx`

```tsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiClient } from '../api/client'
import { useAuthStore } from '../stores/authStore'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const { login } = useAuthStore()
  const navigate = useNavigate()

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    try {
      const { data } = await apiClient.post('/api/v2/auth/login', { email, password })
      await login(data.access_token, data.refresh_token)
      navigate('/dashboard')
    } catch {
      setError('Неверные учётные данные')
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="bg-white p-8 rounded-2xl shadow-lg w-full max-w-sm">
        <h1 className="text-2xl font-bold mb-6 text-center">UK Management</h1>

        {/* Telegram Login Widget — подключается через script tag */}
        <div id="telegram-login-widget" className="mb-4" />

        <div className="flex items-center gap-2 my-4">
          <hr className="flex-1" /> <span className="text-gray-400 text-sm">или</span> <hr className="flex-1" />
        </div>

        <form onSubmit={handleLogin} className="space-y-3">
          <input
            className="w-full border rounded-lg px-3 py-2 text-sm"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <input
            className="w-full border rounded-lg px-3 py-2 text-sm"
            type="password"
            placeholder="Пароль"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {error && <p className="text-red-500 text-sm">{error}</p>}
          <button className="w-full bg-blue-600 text-white py-2 rounded-lg font-medium hover:bg-blue-700">
            Войти
          </button>
        </form>
      </div>
    </div>
  )
}
```

**Commit:**

```bash
git add frontend/src/pages/LoginPage.tsx
git commit -m "feat(frontend): add login page (password + telegram widget placeholder)"
```

---

### Task 17: Kanban-доска

**Files:**
- Create: `frontend/src/components/kanban/KanbanBoard.tsx`
- Create: `frontend/src/components/kanban/KanbanColumn.tsx`
- Create: `frontend/src/components/kanban/RequestCard.tsx`
- Create: `frontend/src/hooks/useKanban.ts`
- Create: `frontend/src/hooks/useWebSocket.ts`

**`frontend/src/hooks/useWebSocket.ts`:**

```typescript
import { useEffect, useRef } from 'react'

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8080'

export function useWebSocket(onMessage: (event: { type: string; data: unknown }) => void) {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>()

  const connect = () => {
    const token = localStorage.getItem('access_token')
    if (!token) return

    const ws = new WebSocket(`${WS_URL}/ws/v2/kanban?token=${token}`)
    wsRef.current = ws

    ws.onmessage = (e) => {
      try {
        const parsed = JSON.parse(e.data)
        onMessage(parsed)
      } catch {}
    }

    ws.onclose = () => {
      reconnectTimer.current = setTimeout(connect, 3000)
    }
  }

  useEffect(() => {
    connect()
    return () => {
      wsRef.current?.close()
      clearTimeout(reconnectTimer.current)
    }
  }, [])
}
```

**`frontend/src/hooks/useKanban.ts`:**

```typescript
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import { useWebSocket } from './useWebSocket'

export interface RequestCard {
  request_number: string
  status: string
  category: string
  urgency: string | null
  source: string | null
  description: string | null
  executor_id: number | null
  created_at: string
  manager_confirmed: boolean
}

export interface KanbanColumn {
  status: string
  count: number
  requests: RequestCard[]
}

export function useKanban(filters: Record<string, string | undefined> = {}) {
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery<{ columns: KanbanColumn[] }>({
    queryKey: ['kanban', filters],
    queryFn: () => apiClient.get('/api/v2/requests/kanban', { params: filters }).then((r) => r.data),
    staleTime: 30_000,
  })

  useWebSocket((event) => {
    // При любом событии инвалидировать кеш — простой подход
    if (['request.created', 'request.status_changed', 'request.assigned', 'request.updated'].includes(event.type)) {
      queryClient.invalidateQueries({ queryKey: ['kanban'] })
    }
  })

  return { columns: data?.columns ?? [], isLoading }
}
```

**`frontend/src/components/kanban/RequestCard.tsx`:**

```tsx
import type { RequestCard as TCard } from '../../hooks/useKanban'

const URGENCY_COLOR: Record<string, string> = {
  Обычная: 'bg-green-100 text-green-700',
  Средняя: 'bg-yellow-100 text-yellow-700',
  Срочная: 'bg-orange-100 text-orange-700',
  Критическая: 'bg-red-100 text-red-700',
}

const SOURCE_ICON: Record<string, string> = {
  bot: '🤖', twa: '📱', web: '🌐', call_center: '📞',
}

interface Props {
  card: TCard
  onClick: () => void
}

export default function RequestCard({ card, onClick }: Props) {
  const urgencyClass = URGENCY_COLOR[card.urgency ?? ''] ?? 'bg-gray-100 text-gray-600'

  return (
    <div
      onClick={onClick}
      className="bg-white border rounded-xl p-3 cursor-pointer hover:shadow-md transition-shadow mb-2"
    >
      <div className="flex justify-between items-start mb-1">
        <span className="font-mono text-xs text-gray-500">{card.request_number}</span>
        <span className="text-xs">{SOURCE_ICON[card.source ?? ''] ?? ''}</span>
      </div>
      <p className="text-sm font-medium mb-1">{card.category}</p>
      <p className="text-xs text-gray-500 line-clamp-2">{card.description}</p>
      <div className="mt-2 flex gap-1 flex-wrap">
        {card.urgency && (
          <span className={`text-xs px-2 py-0.5 rounded-full ${urgencyClass}`}>{card.urgency}</span>
        )}
        {card.manager_confirmed && (
          <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">✓ Подтверждено</span>
        )}
      </div>
    </div>
  )
}
```

**`frontend/src/components/kanban/KanbanColumn.tsx`:**

```tsx
import { useDroppable } from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable'
import RequestCard from './RequestCard'
import type { KanbanColumn as TColumn } from '../../hooks/useKanban'

interface Props {
  column: TColumn
  onCardClick: (number: string) => void
}

export default function KanbanColumn({ column, onCardClick }: Props) {
  const { setNodeRef, isOver } = useDroppable({ id: column.status })

  return (
    <div className={`flex flex-col min-w-[220px] max-w-[240px] rounded-xl bg-gray-50 p-2 ${isOver ? 'ring-2 ring-blue-400' : ''}`}>
      <div className="flex items-center justify-between mb-2 px-1">
        <span className="font-semibold text-sm">{column.status}</span>
        <span className="bg-gray-200 text-gray-600 text-xs rounded-full px-2 py-0.5">{column.count}</span>
      </div>
      <div ref={setNodeRef} className="flex-1 min-h-[120px]">
        <SortableContext items={column.requests.map((r) => r.request_number)} strategy={verticalListSortingStrategy}>
          {column.requests.map((card) => (
            <RequestCard key={card.request_number} card={card} onClick={() => onCardClick(card.request_number)} />
          ))}
        </SortableContext>
      </div>
    </div>
  )
}
```

**`frontend/src/components/kanban/KanbanBoard.tsx`:**

```tsx
import { useState } from 'react'
import { DndContext, DragEndEvent, closestCenter } from '@dnd-kit/core'
import { useKanban } from '../../hooks/useKanban'
import KanbanColumn from './KanbanColumn'
import { apiClient } from '../../api/client'
import { useQueryClient } from '@tanstack/react-query'

interface Props {
  onCardClick: (requestNumber: string) => void
}

export default function KanbanBoard({ onCardClick }: Props) {
  const { columns, isLoading } = useKanban()
  const queryClient = useQueryClient()

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event
    if (!over || active.id === over.id) return

    const requestNumber = String(active.id)
    const newStatus = String(over.id)

    // Оптимистичное обновление
    queryClient.setQueryData(['kanban', {}], (old: { columns: typeof columns } | undefined) => {
      if (!old) return old
      return {
        columns: old.columns.map((col) => ({
          ...col,
          requests: col.status === newStatus
            ? [...col.requests, ...old.columns.flatMap(c => c.requests.filter(r => r.request_number === requestNumber))]
            : col.requests.filter((r) => r.request_number !== requestNumber),
        })),
      }
    })

    try {
      await apiClient.patch(`/api/v2/requests/${requestNumber}`, { status: newStatus })
    } catch {
      queryClient.invalidateQueries({ queryKey: ['kanban'] })
    }
  }

  if (isLoading) return <div className="p-8 text-center text-gray-400">Загрузка...</div>

  return (
    <DndContext collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <div className="flex gap-3 overflow-x-auto pb-4 h-full">
        {columns.map((col) => (
          <KanbanColumn key={col.status} column={col} onCardClick={onCardClick} />
        ))}
      </div>
    </DndContext>
  )
}
```

**Commit:**

```bash
git add frontend/src/components/kanban/ frontend/src/hooks/
git commit -m "feat(frontend): add kanban board with dnd, websocket updates"
```

---

### Task 18: Dashboard страница + колл-центр модал

**Files:**
- Create: `frontend/src/pages/DashboardPage.tsx`
- Create: `frontend/src/components/callcenter/CallCenterModal.tsx`

**`CallCenterModal.tsx`** (сокращённо, полная структура):

```tsx
import { useState } from 'react'
import { apiClient } from '../../api/client'

interface Props { isOpen: boolean; onClose: () => void }

export default function CallCenterModal({ isOpen, onClose }: Props) {
  const [query, setQuery] = useState('')
  const [residents, setResidents] = useState<Array<{ id: number; full_name: string; phone: string }>>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [form, setForm] = useState({ category: '', urgency: 'Обычная', description: '', address: '' })
  const [loading, setLoading] = useState(false)

  const search = async () => {
    const { data } = await apiClient.get('/api/v2/callcenter/search-resident', { params: { q: query } })
    setResidents(data)
  }

  const submit = async () => {
    setLoading(true)
    try {
      await apiClient.post('/api/v2/callcenter/requests', {
        ...form,
        user_id: selected || undefined,
      })
      onClose()
    } finally {
      setLoading(false)
    }
  }

  if (!isOpen) return null
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl p-6 w-full max-w-lg shadow-xl">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-bold">📞 Создание заявки по звонку</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">✕</button>
        </div>

        <div className="flex gap-2 mb-3">
          <input className="flex-1 border rounded-lg px-3 py-2 text-sm" placeholder="Телефон или ФИО" value={query} onChange={(e) => setQuery(e.target.value)} />
          <button onClick={search} className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm">Найти</button>
        </div>

        {residents.length > 0 && (
          <div className="mb-3 space-y-1">
            {residents.map((r) => (
              <div key={r.id} onClick={() => setSelected(r.id)} className={`border rounded-lg p-2 cursor-pointer text-sm ${selected === r.id ? 'border-blue-500 bg-blue-50' : ''}`}>
                <span className="font-medium">{r.full_name}</span> · {r.phone}
              </div>
            ))}
          </div>
        )}

        <select className="w-full border rounded-lg px-3 py-2 text-sm mb-2" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
          <option value="">Категория...</option>
          {['Электрика', 'Сантехника', 'Отопление', 'Уборка', 'Безопасность', 'Техобслуживание'].map(c => <option key={c}>{c}</option>)}
        </select>

        <select className="w-full border rounded-lg px-3 py-2 text-sm mb-2" value={form.urgency} onChange={(e) => setForm({ ...form, urgency: e.target.value })}>
          {['Обычная', 'Средняя', 'Срочная', 'Критическая'].map(u => <option key={u}>{u}</option>)}
        </select>

        <textarea className="w-full border rounded-lg px-3 py-2 text-sm mb-4" rows={3} placeholder="Описание проблемы" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-sm border rounded-lg">Отмена</button>
          <button onClick={submit} disabled={loading || !form.category || !form.description} className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg disabled:opacity-50">
            {loading ? 'Создаю...' : 'Создать заявку'}
          </button>
        </div>
      </div>
    </div>
  )
}
```

**`DashboardPage.tsx`:**

```tsx
import { useState } from 'react'
import KanbanBoard from '../components/kanban/KanbanBoard'
import CallCenterModal from '../components/callcenter/CallCenterModal'

export default function DashboardPage() {
  const [callCenterOpen, setCallCenterOpen] = useState(false)
  const [selectedRequest, setSelectedRequest] = useState<string | null>(null)

  return (
    <div className="flex flex-col h-screen">
      <div className="flex items-center gap-3 px-4 py-3 border-b bg-white">
        <h1 className="font-bold text-lg">UK Management</h1>
        <nav className="flex gap-2 ml-4">
          <a href="/dashboard" className="text-sm font-medium text-blue-600">Канбан</a>
          <a href="/requests" className="text-sm text-gray-500 hover:text-gray-800">Заявки</a>
          <a href="/staff" className="text-sm text-gray-500 hover:text-gray-800">Сотрудники</a>
          <a href="/reports" className="text-sm text-gray-500 hover:text-gray-800">Отчёты</a>
        </nav>
        <div className="ml-auto flex gap-2">
          <button onClick={() => setCallCenterOpen(true)} className="bg-green-600 text-white px-3 py-1.5 rounded-lg text-sm font-medium">
            📞 Создать по звонку
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-hidden p-4">
        <KanbanBoard onCardClick={setSelectedRequest} />
      </div>

      <CallCenterModal isOpen={callCenterOpen} onClose={() => setCallCenterOpen(false)} />
    </div>
  )
}
```

**Commit:**

```bash
git add frontend/src/pages/DashboardPage.tsx frontend/src/components/callcenter/
git commit -m "feat(frontend): add dashboard page with kanban and call center modal"
```

---

## Phase 6: Telegram Mini App

### Task 19: TWA точка входа и авторизация

**Files:**
- Create: `frontend/src/utils/isTWA.ts`
- Create: `frontend/src/hooks/useTWAAuth.ts`

**`frontend/src/utils/isTWA.ts`:**

```typescript
export const isTWA = (): boolean =>
  typeof window !== 'undefined' && !!window.Telegram?.WebApp?.initData

export const getTWAInitData = (): string =>
  window.Telegram?.WebApp?.initData ?? ''
```

**`frontend/src/hooks/useTWAAuth.ts`:**

```typescript
import { useEffect } from 'react'
import { useAuthStore } from '../stores/authStore'
import { apiClient } from '../api/client'
import { isTWA, getTWAInitData } from '../utils/isTWA'

export function useTWAAuth() {
  const { isAuthenticated, login } = useAuthStore()

  useEffect(() => {
    if (isTWA() && !isAuthenticated) {
      const init_data = getTWAInitData()
      apiClient.post('/api/v2/auth/twa', { init_data })
        .then(({ data }) => login(data.access_token, data.refresh_token))
        .catch(console.error)
    }
  }, [])

  return { isAuthenticated }
}
```

**Commit:**

```bash
git add frontend/src/utils/ frontend/src/hooks/useTWAAuth.ts
git commit -m "feat(twa): add twa detection and auto-auth hook"
```

---

### Task 20: TWA страницы — Home, Список заявок, Создание заявки

Создать `frontend/src/pages/twa/TWAHomePage.tsx`:

```tsx
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../../api/client'
import { useTWAAuth } from '../../hooks/useTWAAuth'
import { useNavigate } from 'react-router-dom'

export default function TWAHomePage() {
  useTWAAuth()
  const navigate = useNavigate()

  const { data: requests } = useQuery({
    queryKey: ['my-requests'],
    queryFn: () => apiClient.get('/api/v2/requests?limit=5').then(r => r.data),
  })

  const activeRequests = (requests ?? []).filter((r: { status: string }) =>
    !['Принято', 'Отменена'].includes(r.status)
  )

  return (
    <div className="p-4 pb-20">
      <h1 className="text-xl font-bold mb-4">Мои заявки</h1>

      {activeRequests.map((req: { request_number: string; status: string; category: string }) => (
        <div key={req.request_number} onClick={() => navigate(`/twa/requests/${req.request_number}`)}
          className="bg-white border rounded-xl p-3 mb-2 cursor-pointer">
          <div className="flex justify-between">
            <span className="font-mono text-xs text-gray-500">{req.request_number}</span>
            <span className={`text-xs px-2 py-0.5 rounded-full ${req.status === 'Выполнена' ? 'bg-orange-100 text-orange-700' : 'bg-blue-100 text-blue-700'}`}>
              {req.status}
            </span>
          </div>
          <p className="text-sm font-medium mt-1">{req.category}</p>
        </div>
      ))}

      <button onClick={() => navigate('/twa/create')}
        className="fixed bottom-20 left-4 right-4 bg-blue-600 text-white py-3 rounded-xl font-medium text-center">
        + Создать заявку
      </button>
    </div>
  )
}
```

Создать `frontend/src/pages/twa/TWACreatePage.tsx` — 4-шаговый wizard (аналогично дизайну в секции 3 дизайн-документа). Каждый шаг — отдельный `useState` с номером шага, данные накапливаются в `formData`.

**Commit:**

```bash
git add frontend/src/pages/twa/
git commit -m "feat(twa): add twa home page and request creation wizard"
```

---

### Task 21: TWA страница деталей заявки + приёмка

Создать `frontend/src/pages/twa/TWARequestDetailPage.tsx` с:
- Статус-таймлайн (`Новая → В работе → ... → Принято`)
- Список комментариев (`GET /api/v2/requests/{number}/comments`)
- Форма ввода нового сообщения
- Если `status === 'Выполнена' && manager_confirmed === true` — блок приёмки со звёздочками

```tsx
// Блок приёмки (вставить в компонент при условии)
{showAcceptance && (
  <div className="fixed bottom-0 left-0 right-0 bg-white border-t p-4">
    <p className="font-medium mb-2">Оцените работу</p>
    <div className="flex gap-2 mb-3">
      {[1,2,3,4,5].map(n => (
        <button key={n} onClick={() => setRating(n)}
          className={`text-2xl ${n <= rating ? 'text-yellow-400' : 'text-gray-300'}`}>★</button>
      ))}
    </div>
    <div className="flex gap-2">
      <button onClick={handleReturn} className="flex-1 border py-2 rounded-xl text-sm">↩ Вернуть</button>
      <button onClick={handleAccept} className="flex-1 bg-blue-600 text-white py-2 rounded-xl text-sm">✓ Принять</button>
    </div>
  </div>
)}
```

**Commit:**

```bash
git add frontend/src/pages/twa/TWARequestDetailPage.tsx
git commit -m "feat(twa): add request detail with chat and acceptance flow"
```

---

## Phase 7: Docker + Production

### Task 22: Frontend Dockerfile и docker-compose интеграция

**Files:**
- Create: `frontend/Dockerfile`
- Create: `frontend/nginx.conf`
- Modify: `docker-compose.yml`

**`frontend/Dockerfile`:**

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

**`frontend/nginx.conf`:**

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://api:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /ws/ {
        proxy_pass http://api:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

**Добавить в `docker-compose.yml`:**

```yaml
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: uk-frontend
    restart: unless-stopped
    ports:
      - "3000:80"
    depends_on:
      - api
    networks:
      - uk-network
```

**Step: Сборка и проверка**

```bash
docker compose build frontend
docker compose up frontend api -d
curl http://localhost:3000
```

**Commit:**

```bash
git add frontend/Dockerfile frontend/nginx.conf docker-compose.yml
git commit -m "feat(docker): add frontend container with nginx proxy to api"
```

---

### Task 23: Финальная проверка и smoke tests

**Step 1: Запустить все сервисы**

```bash
docker compose up -d
docker compose ps
```

Ожидаемо: все сервисы `healthy`.

**Step 2: Smoke тесты API**

```bash
# Health
curl http://localhost:8080/health

# Login (создать тестового юзера с email через psql сначала)
curl -X POST http://localhost:8080/api/v2/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com","password":"testpass123"}'

# Kanban (с токеном)
curl http://localhost:8080/api/v2/requests/kanban \
  -H "Authorization: Bearer <TOKEN>"

# WebSocket
# websocat "ws://localhost:8080/ws/v2/kanban?token=<TOKEN>"
```

**Step 3: Запустить все тесты**

```bash
pytest tests/ -v
```

**Step 4: Финальный commit**

```bash
git add .
git commit -m "feat: complete web dashboard + twa expansion MVP"
```

---

## Итого

| Фаза | Задачи | Ключевой результат |
|------|--------|--------------------|
| 1. Foundation | Task 1-5 | Alembic, миграции, api-контейнер |
| 2. Auth | Task 6-7 | JWT + TWA initData + пароль |
| 3. REST API | Task 8-11 | Заявки, канбан, колл-центр, профиль |
| 4. Real-time | Task 12-13 | Redis Pub/Sub + WebSocket |
| 5. Web Dashboard | Task 14-18 | React, канбан UI, колл-центр |
| 6. TWA | Task 19-21 | Mini App для жителей |
| 7. Production | Task 22-23 | Docker, финальные тесты |

**Предупреждения:**
- Не запускать `alembic upgrade head` без бэкапа production БД
- TWA требует HTTPS — использовать ngrok или reverse proxy при разработке
- `INVITE_SECRET` переиспользуется как JWT SECRET — при необходимости добавить отдельную переменную `JWT_SECRET`
