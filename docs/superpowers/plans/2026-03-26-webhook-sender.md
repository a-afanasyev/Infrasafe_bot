# Webhook Sender — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Отправлять подписанные HMAC-SHA256 webhook-уведомления о building событиях из UK в InfraSafe.

**Source spec:** `UK-WEBHOOK-SENDER-SERVICE-TZ.md`

**Scope:** Phase 1 — building CRUD webhooks only. Out of scope (Phase 2):
- Request webhooks (`request.created`, `request.status_changed`) — requires separate router wiring and payload design
- Initial sync script (spec section 6) — one-time migration linking existing UK buildings to InfraSafe

### Architecture Decision: Outbox vs Redis Pub/Sub transport

ТЗ (`UK-WEBHOOK-SENDER-SERVICE-TZ.md`, sections 2.1, 4.1) задаёт схему `router → Redis Pub/Sub → webhook-sender → InfraSafe`. План **сознательно** заменяет Redis-транспорт на **Transactional Outbox** по следующим причинам:

1. **Гарантия доставки**: Redis Pub/Sub — fire-and-forget. При рестарте webhook-sender события теряются. Outbox хранит pending записи в PostgreSQL — ничего не теряется.
2. **Атомарность**: Outbox-запись создаётся в той же транзакции что и building CRUD. Redis publish — отдельная операция вне транзакции.
3. **Упрощение**: Не нужен отдельный subscriber loop, нет race condition при reconnect к Redis.

Redis Pub/Sub `buildings:updates` **остаётся** — но только для WebSocket push во фронтенд (как `requests:updates` и `shifts:updates`).

> **TODO:** После реализации — обновить ТЗ (`UK-WEBHOOK-SENDER-SERVICE-TZ.md`), чтобы описание архитектуры соответствовало фактической реализации.

### Decision: event_id при retry

ТЗ section 8.2 содержит противоречие: строка 681 говорит «тот же event_id», строка 682 — «пересоздать event_id». **Решение:** outbox хранит стабильный `event_id`. При retry отправляется тот же `event_id` с новой подписью (новый timestamp). InfraSafe вернёт `200 Already processed` если уже обработал — это корректное поведение (идемпотентная доставка).

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0 (async), PostgreSQL 15, httpx (уже в deps), alembic.

---

## Docker naming convention

В этом плане:
- `docker compose build/up/restart` — используют **service name**: `api`, `postgres`, `redis`
- `docker exec` — использует **container_name**: `uk-management-api`, `uk-postgres`

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `uk_management_bot/database/models/webhook_outbox.py` | SQLAlchemy model: outbox table |
| Create | `alembic/versions/003_add_webhook_outbox.py` | DB migration |
| Create | `uk_management_bot/services/webhook_sender.py` | `queue_webhook()`, `sign_payload()`, `send_webhook()`, `process_outbox()` |
| Create | `uk_management_bot/tests/test_webhook_sender.py` | Unit tests |
| Modify | `uk_management_bot/config/settings.py` | 5 env vars for InfraSafe integration |
| Modify | `uk_management_bot/services/redis_pubsub.py` | Add `buildings:updates` channel (for frontend WS only) |
| Modify | `uk_management_bot/api/addresses/router.py` | Call `queue_webhook()` + `publish_building_event()` in building CRUD |
| Modify | `uk_management_bot/api/main.py` | Start outbox processor in lifespan |
| Modify | `docker-compose.yml` | Add env vars to `api` service |

---

### Task 1: Settings — env-переменные InfraSafe

**Files:**
- Modify: `uk_management_bot/config/settings.py` — after `USE_REDIS_RATE_LIMIT` setting
- Modify: `docker-compose.yml` — `api.environment` section

- [ ] **Step 1: Add InfraSafe settings**

В `uk_management_bot/config/settings.py`, после `USE_REDIS_RATE_LIMIT`, добавить:

```python
    # InfraSafe webhook integration
    INFRASAFE_WEBHOOK_ENABLED = os.getenv("INFRASAFE_WEBHOOK_ENABLED", "false").lower() == "true"
    INFRASAFE_WEBHOOK_URL = os.getenv("INFRASAFE_WEBHOOK_URL", "")
    INFRASAFE_WEBHOOK_SECRET = os.getenv("INFRASAFE_WEBHOOK_SECRET", "")
    INFRASAFE_WEBHOOK_TIMEOUT = int(os.getenv("INFRASAFE_WEBHOOK_TIMEOUT", "10"))
    INFRASAFE_WEBHOOK_MAX_RETRIES = int(os.getenv("INFRASAFE_WEBHOOK_MAX_RETRIES", "3"))
```

- [ ] **Step 2: Add env vars to docker-compose.yml**

В `docker-compose.yml`, секция `api.environment` (после `PYTHONUNBUFFERED=1`), добавить:

```yaml
      - INFRASAFE_WEBHOOK_ENABLED=${INFRASAFE_WEBHOOK_ENABLED:-false}
      - INFRASAFE_WEBHOOK_URL=${INFRASAFE_WEBHOOK_URL:-}
      - INFRASAFE_WEBHOOK_SECRET=${INFRASAFE_WEBHOOK_SECRET:-}
```

- [ ] **Step 3: Verify settings load**

Run: `docker exec uk-management-api python -c "from uk_management_bot.config.settings import settings; print(settings.INFRASAFE_WEBHOOK_ENABLED)"`
Expected: `False`

- [ ] **Step 4: Commit**

```bash
git add uk_management_bot/config/settings.py docker-compose.yml
git commit -m "feat(webhook): add InfraSafe webhook env settings"
```

---

### Task 2: Outbox model + migration

**Files:**
- Create: `uk_management_bot/database/models/webhook_outbox.py`
- Create: `alembic/versions/003_add_webhook_outbox.py`

- [ ] **Step 1: Create outbox model**

Create `uk_management_bot/database/models/webhook_outbox.py`:

```python
"""Webhook outbox — transactional outbox pattern for reliable webhook delivery."""
from sqlalchemy import Column, Integer, String, DateTime, JSON, Text, Index
from sqlalchemy.sql import func
from uk_management_bot.database.session import Base


class WebhookOutbox(Base):
    __tablename__ = "webhook_outbox"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String(36), nullable=False, unique=True, index=True)
    event = Column(String(50), nullable=False, index=True)       # e.g. "building.created"
    endpoint = Column(String(200), nullable=False)                # e.g. "/api/webhooks/uk/building"
    payload = Column(JSON, nullable=False)                        # full webhook payload
    status = Column(String(20), nullable=False, default="pending", index=True)  # pending/sent/failed
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    retry_after = Column(DateTime(timezone=True), nullable=True)  # earliest next retry time
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True), nullable=True)

    # Composite index for outbox processor query: WHERE status='pending' ORDER BY created_at
    __table_args__ = (
        Index("ix_webhook_outbox_status_created", "status", "created_at"),
    )

    def __repr__(self):
        return f"<WebhookOutbox(id={self.id}, event={self.event}, status={self.status})>"
```

- [ ] **Step 2: Create alembic migration**

Create `alembic/versions/003_add_webhook_outbox.py`:

```python
"""add webhook outbox table

Revision ID: 003
Revises: 002
Create Date: 2026-03-26
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'webhook_outbox',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('event_id', sa.String(36), nullable=False, unique=True, index=True),
        sa.Column('event', sa.String(50), nullable=False, index=True),
        sa.Column('endpoint', sa.String(200), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending', index=True),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('retry_after', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_webhook_outbox_status_created', 'webhook_outbox', ['status', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_webhook_outbox_status_created', table_name='webhook_outbox')
    op.drop_table('webhook_outbox')
```

- [ ] **Step 3: Run migration**

Run: `docker exec uk-management-api alembic upgrade head`
Expected: `INFO  [alembic.runtime.migration] Running upgrade 002 -> 003, add webhook outbox table`

- [ ] **Step 4: Verify table and indexes exist**

Run: `docker exec uk-postgres psql -U uk_bot -d uk_management -c "\d webhook_outbox"`
Expected: table columns listed, including `retry_after`

Run: `docker exec uk-postgres psql -U uk_bot -d uk_management -c "\di ix_webhook_outbox_*"`
Expected: `ix_webhook_outbox_status_created` index listed

- [ ] **Step 5: Commit**

```bash
git add uk_management_bot/database/models/webhook_outbox.py alembic/versions/003_add_webhook_outbox.py
git commit -m "feat(webhook): add webhook_outbox table and migration"
```

---

### Task 3: Webhook sender service

**Files:**
- Create: `uk_management_bot/services/webhook_sender.py`
- Create: `uk_management_bot/tests/test_webhook_sender.py`

- [ ] **Step 1: Write tests**

Create `uk_management_bot/tests/test_webhook_sender.py`:

```python
"""Tests for webhook sender service — Phase 1: building webhooks only."""
import hashlib
import hmac
import json
import time
import pytest

from uk_management_bot.services.webhook_sender import (
    sign_payload,
    build_building_payload,
)


class TestSignPayload:
    def test_sign_produces_valid_format(self):
        """Signature header must be t=<timestamp>,v1=<hex>."""
        body = '{"event":"test"}'
        secret = "test-secret-key-32chars-minimum!!"
        result = sign_payload(body, secret)
        assert result.startswith("t=")
        assert ",v1=" in result

    def test_sign_is_hmac_sha256(self):
        """Signature must be verifiable with HMAC-SHA256."""
        body = '{"event":"test"}'
        secret = "test-secret"
        header = sign_payload(body, secret)
        # Parse
        parts = dict(p.split("=", 1) for p in header.split(","))
        timestamp = parts["t"]
        sig = parts["v1"]
        # Verify
        message = f"{timestamp}.{body}"
        expected = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
        assert sig == expected

    def test_sign_timestamp_is_recent(self):
        """Timestamp must be within 5 seconds of now."""
        body = '{"event":"test"}'
        header = sign_payload(body, "secret")
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts = int(parts["t"])
        assert abs(ts - int(time.time())) < 5


class TestBuildBuildingPayload:
    def test_building_created_payload(self):
        """building.created maps address->name, yard_name->town."""
        result = build_building_payload("building.created", {
            "id": 1,
            "address": "Yangi Olmazor, 12V",
            "yard_name": "Фаза 1(LOT 4)",
        })
        assert result["event"] == "building.created"
        assert result["building"]["id"] == 1
        assert result["building"]["name"] == "Yangi Olmazor, 12V"
        assert result["building"]["address"] == "Yangi Olmazor, 12V"
        assert result["building"]["town"] == "Фаза 1(LOT 4)"
        assert "event_id" in result
        assert "timestamp" in result
        assert result["timestamp"].endswith("Z")

    def test_building_deleted_payload(self):
        """building.deleted includes the same structure."""
        result = build_building_payload("building.deleted", {
            "id": 5,
            "address": "Test",
            "yard_name": "Yard",
        })
        assert result["event"] == "building.deleted"
        assert result["building"]["id"] == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec uk-management-api python -m pytest uk_management_bot/tests/test_webhook_sender.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'uk_management_bot.services.webhook_sender'`

- [ ] **Step 3: Implement webhook_sender.py**

Create `uk_management_bot/services/webhook_sender.py`:

```python
"""
Webhook sender — Transactional Outbox pattern for InfraSafe integration.

Architecture decision: uses PostgreSQL outbox instead of Redis Pub/Sub as transport.
See docs/superpowers/plans/2026-03-26-webhook-sender.md for rationale.

Usage from router:
    await queue_webhook(db, "building.created", "/api/webhooks/uk/building", {
        "id": building.id, "address": building.address, "yard_name": yard.name,
    })

Outbox processor runs as background task (every 10 seconds), picks pending records,
signs with HMAC-SHA256, sends to InfraSafe with exponential backoff, marks as sent/failed.
"""
import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import datetime, timezone, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.webhook_outbox import WebhookOutbox

logger = logging.getLogger(__name__)

# Exponential backoff delays per spec: 2s, 4s, 8s
BACKOFF_DELAYS = [2, 4, 8]


# ── Payload builders ──────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_building_payload(event: str, data: dict) -> dict:
    """Build InfraSafe building webhook payload. Maps address->name, yard_name->town."""
    return {
        "event_id": str(uuid.uuid4()),
        "event": event,
        "timestamp": _now_iso(),
        "building": {
            "id": data["id"],
            "name": data.get("address", ""),
            "address": data.get("address", ""),
            "town": data.get("yard_name", ""),
        },
    }


# ── HMAC signing ──────────────────────────────────────────


def sign_payload(body: str, secret: str) -> str:
    """Generate HMAC-SHA256 signature header: t=<unix>,v1=<hex>."""
    timestamp = str(int(time.time()))
    message = f"{timestamp}.{body}"
    sig = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={sig}"


# ── Queue (write to outbox) ──────────────────────────────


async def queue_webhook(
    db: AsyncSession,
    event: str,
    endpoint: str,
    data: dict,
) -> None:
    """Write a webhook event to the outbox table. Call inside the same db session/transaction.

    IMPORTANT: caller must call db.flush() before this if the entity ID
    is auto-generated (e.g. building.id after db.add() but before db.commit()).
    """
    if not settings.INFRASAFE_WEBHOOK_ENABLED:
        return

    if event.startswith("building."):
        payload = build_building_payload(event, data)
    else:
        payload = {
            "event_id": str(uuid.uuid4()),
            "event": event,
            "timestamp": _now_iso(),
            "data": data,
        }

    outbox = WebhookOutbox(
        event_id=payload["event_id"],
        event=event,
        endpoint=endpoint,
        payload=payload,
    )
    db.add(outbox)
    # NOTE: commit happens in the caller (router) — outbox record is part of the same transaction.
    logger.debug("Queued webhook %s (event_id=%s)", event, payload["event_id"])


# ── Send (HTTP POST with HMAC) ───────────────────────────


async def send_webhook(
    url: str, payload: dict, secret: str, client: httpx.AsyncClient,
) -> tuple[bool, str, bool, int]:
    """Sign and send one webhook.

    Returns: (success, error_message, retryable, retry_after_seconds)
    - retry_after_seconds: for 429, parsed from Retry-After header or default 60s per spec
    """
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    signature = sign_payload(body, secret)

    try:
        resp = await client.post(
            url,
            content=body.encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-webhook-signature": signature,
            },
        )
        if resp.status_code == 200:
            return True, "", False, 0
        if resp.status_code in (400, 401, 403):
            return False, f"HTTP {resp.status_code}: {resp.text[:200]}", False, 0  # permanent
        if resp.status_code == 429:
            # Per spec: respect Retry-After header, default 60 seconds
            retry_after = 60
            ra_header = resp.headers.get("Retry-After")
            if ra_header:
                try:
                    retry_after = int(ra_header)
                except ValueError:
                    retry_after = 60
            return False, "HTTP 429 rate limited", True, retry_after
        if resp.status_code == 503:
            return False, "HTTP 503 integration disabled", False, 0  # permanent per spec
        return False, f"HTTP {resp.status_code}", True, 0
    except httpx.TimeoutException:
        return False, "timeout", True, 0
    except Exception as e:
        return False, str(e)[:200], True, 0


# ── Outbox processor (periodic task) ─────────────────────


async def process_outbox() -> None:
    """
    Poll webhook_outbox for pending records, send them, mark as sent/failed.
    Called by lifespan background task every 10 seconds.

    Retry logic per spec (UK-WEBHOOK-SENDER-SERVICE-TZ.md section 8.1):
    - Exponential backoff: 2s, 4s, 8s between attempts
    - HTTP 429: respect Retry-After header, default 60s
    - HTTP 400/401/403/503: permanent failure, don't retry
    - Max 3 attempts total
    """
    if not settings.INFRASAFE_WEBHOOK_ENABLED:
        return

    base_url = settings.INFRASAFE_WEBHOOK_URL.rstrip("/")
    secret = settings.INFRASAFE_WEBHOOK_SECRET
    max_retries = settings.INFRASAFE_WEBHOOK_MAX_RETRIES
    timeout = settings.INFRASAFE_WEBHOOK_TIMEOUT

    if not base_url or not secret:
        return

    now = datetime.now(timezone.utc)

    from uk_management_bot.database.session import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        # Fetch up to 50 pending records that are ready for (re)try
        from sqlalchemy import or_
        result = await db.execute(
            select(WebhookOutbox)
            .where(
                WebhookOutbox.status == "pending",
                or_(
                    WebhookOutbox.retry_after.is_(None),
                    WebhookOutbox.retry_after <= now,
                ),
            )
            .order_by(WebhookOutbox.created_at)
            .limit(50)
        )
        pending = result.scalars().all()

        if not pending:
            return

        logger.info("Processing %d pending webhooks", len(pending))

        async with httpx.AsyncClient(timeout=timeout) as client:
            for entry in pending:
                url = f"{base_url}{entry.endpoint}"
                ok, error, retryable, retry_after_secs = await send_webhook(
                    url, entry.payload, secret, client,
                )

                if ok:
                    entry.status = "sent"
                    entry.sent_at = datetime.now(timezone.utc)
                    entry.attempts += 1
                    logger.info("Webhook sent: %s -> %s (event_id=%s)", entry.event, url, entry.event_id)
                else:
                    entry.attempts += 1
                    entry.last_error = error
                    if not retryable or entry.attempts >= max_retries:
                        entry.status = "failed"
                        logger.error(
                            "Webhook failed (permanent=%s, attempts=%d): %s %s — %s",
                            not retryable, entry.attempts, entry.event, entry.event_id, error,
                        )
                    else:
                        # Set retry_after: use 429 Retry-After or exponential backoff
                        if retry_after_secs > 0:
                            delay = retry_after_secs
                        else:
                            idx = min(entry.attempts - 1, len(BACKOFF_DELAYS) - 1)
                            delay = BACKOFF_DELAYS[idx]
                        entry.retry_after = datetime.now(timezone.utc) + timedelta(seconds=delay)
                        logger.warning(
                            "Webhook attempt %d/%d failed, retry in %ds: %s — %s",
                            entry.attempts, max_retries, delay, entry.event, error,
                        )

        await db.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec uk-management-api python -m pytest uk_management_bot/tests/test_webhook_sender.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add uk_management_bot/services/webhook_sender.py uk_management_bot/tests/test_webhook_sender.py
git commit -m "feat(webhook): add webhook sender with outbox pattern and tests"
```

---

### Task 4: Redis Pub/Sub — buildings channel (for frontend WebSocket only)

**Files:**
- Modify: `uk_management_bot/services/redis_pubsub.py` — append after existing functions

- [ ] **Step 1: Add buildings channel**

Append to `uk_management_bot/services/redis_pubsub.py` (after the last function):

```python

BUILDINGS_CHANNEL = "buildings:updates"


async def publish_building_event(event_type: str, data: dict) -> None:
    """Publish building event to Redis Pub/Sub for real-time frontend updates.

    NOTE: This is for frontend WebSocket push only, NOT for webhook delivery
    (webhooks use PostgreSQL outbox — see webhook_sender.py).
    """
    try:
        client = await get_pubsub_redis()
        message = json.dumps({"type": event_type, "data": data})
        await client.publish(BUILDINGS_CHANNEL, message)
    except Exception:
        logger.warning("Failed to publish building event %s", event_type, exc_info=True)


async def subscribe_to_buildings():
    """Returns a dedicated Redis Pub/Sub subscriber for building events."""
    url = getattr(settings, 'REDIS_PUBSUB_URL', 'redis://redis:6379/1')
    client = aioredis.from_url(url, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe(BUILDINGS_CHANNEL)
    return pubsub, client
```

- [ ] **Step 2: Commit**

```bash
git add uk_management_bot/services/redis_pubsub.py
git commit -m "feat(webhook): add buildings:updates Redis Pub/Sub channel for frontend WS"
```

---

### Task 5: Wire up router — building CRUD events

**Files:**
- Modify: `uk_management_bot/api/addresses/router.py` — building CRUD endpoints

- [ ] **Step 1: Add imports to router.py**

At the top of `uk_management_bot/api/addresses/router.py` (after existing imports), add:

```python
from uk_management_bot.services.webhook_sender import queue_webhook
from uk_management_bot.services.redis_pubsub import publish_building_event
```

- [ ] **Step 2: Add webhook + pubsub calls to create_building**

In `create_building`, find the existing `db.add(building)` line. Replace the section from `db.add(building)` through `await db.commit()` with:

```python
    db.add(building)
    await db.flush()  # assigns building.id without committing
    # Webhook outbox — same transaction as building create
    await queue_webhook(db, "building.created", "/api/webhooks/uk/building", {
        "id": building.id, "address": building.address, "yard_name": yard.name,
    })
    await db.commit()  # commits BOTH building and outbox record atomically
    await db.refresh(building)
```

After `await db.refresh(building)`, add Pub/Sub notify:

```python
    await publish_building_event("building.created", {
        "id": building.id, "address": building.address, "yard_name": yard.name,
    })
```

- [ ] **Step 3: Add webhook + pubsub calls to update_building**

In `update_building`, insert **before** the existing `await db.commit()`:

```python
    # Webhook outbox — same transaction as building update
    yard_result_wh = await db.execute(select(Yard.name).where(Yard.id == building.yard_id))
    yard_name_wh = yard_result_wh.scalar_one_or_none() or ""
    await queue_webhook(db, "building.updated", "/api/webhooks/uk/building", {
        "id": building.id, "address": building.address, "yard_name": yard_name_wh,
    })
    # existing: await db.commit()  <-- commits BOTH building update and outbox record
```

After `await db.refresh(building)`, add Pub/Sub notify:

```python
    await publish_building_event("building.updated", {
        "id": building.id, "address": building.address, "yard_name": yard_name_wh,
    })
```

- [ ] **Step 4: Add webhook + pubsub calls to delete_building**

In `delete_building`, after `building.is_active = False` and before `await db.commit()`, add:

```python
    # Fetch yard name before commit
    yard_result = await db.execute(select(Yard.name).where(Yard.id == building.yard_id))
    yard_name = yard_result.scalar_one_or_none() or ""
    # Webhook outbox — same transaction as soft-delete
    await queue_webhook(db, "building.deleted", "/api/webhooks/uk/building", {
        "id": building.id, "address": building.address, "yard_name": yard_name,
    })
    # existing: await db.commit()  <-- commits BOTH soft-delete and outbox record
```

After `await db.commit()`, add Pub/Sub notify:

```python
    await publish_building_event("building.deleted", {
        "id": building.id, "address": building.address, "yard_name": yard_name,
    })
```

- [ ] **Step 5: Rebuild and verify no errors**

Run: `docker compose build api && docker compose up -d api`
Run: `docker logs uk-management-api --tail 10`
Expected: no import errors, API starts successfully

- [ ] **Step 6: Commit**

```bash
git add uk_management_bot/api/addresses/router.py
git commit -m "feat(webhook): publish building events from addresses router"
```

---

### Task 6: Start outbox processor in API lifespan

**Files:**
- Modify: `uk_management_bot/api/main.py` — lifespan function

- [ ] **Step 1: Wire process_outbox into lifespan**

Replace the lifespan function in `uk_management_bot/api/main.py`:

```python
import asyncio


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup — launch outbox processor
    from uk_management_bot.services.webhook_sender import process_outbox
    from uk_management_bot.config.settings import settings

    async def _outbox_loop():
        while True:
            try:
                await process_outbox()
            except Exception:
                import logging
                logging.getLogger(__name__).exception("Outbox processor error")
            await asyncio.sleep(10)

    task = None
    if settings.INFRASAFE_WEBHOOK_ENABLED:
        task = asyncio.create_task(_outbox_loop())
        import logging
        logging.getLogger(__name__).info("Webhook outbox processor started (10s interval)")
    yield
    # shutdown
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
```

- [ ] **Step 2: Rebuild and verify**

Run: `docker compose build api && docker compose up -d api`
Run: `docker logs uk-management-api --tail 10`
Expected: no errors. If `INFRASAFE_WEBHOOK_ENABLED=false`, log should NOT contain "outbox processor started".

- [ ] **Step 3: Commit**

```bash
git add uk_management_bot/api/main.py
git commit -m "feat(webhook): start outbox processor in API lifespan"
```

---

### Task 7: Integration test (manual, end-to-end)

**Preconditions:**
- UK stack running: `docker compose up -d` (services: api, postgres, redis)
- InfraSafe stack running at `http://localhost:3000` (separate project at `/Users/andreyafanasyev/Code/Infrasafe`)
- `INFRASAFE_WEBHOOK_SECRET` in UK `.env` matches `UK_WEBHOOK_SECRET` in InfraSafe config
- Auth credentials known for UK API (email/password)

- [ ] **Step 1: Set env vars and restart**

Add to UK `.env`:

```env
INFRASAFE_WEBHOOK_ENABLED=true
INFRASAFE_WEBHOOK_URL=http://host.docker.internal:3000
INFRASAFE_WEBHOOK_SECRET=<same-as-UK_WEBHOOK_SECRET-in-InfraSafe>
```

Run: `docker compose up -d api`
Check: `docker logs uk-management-api --tail 5` — should see "Webhook outbox processor started"

- [ ] **Step 2: Create a building via API**

```bash
# Get auth token
TOKEN=$(curl -s -X POST http://localhost:8085/api/v2/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@test.com","password":"..."}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Create building
curl -X POST http://localhost:8085/api/v2/addresses/buildings \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"address":"Test Webhook Building","yard_id":1,"entrance_count":1,"floor_count":5}'
```

- [ ] **Step 3: Verify outbox record was created**

Run: `docker exec uk-postgres psql -U uk_bot -d uk_management -c "SELECT id, event, status, attempts, retry_after, created_at FROM webhook_outbox ORDER BY id DESC LIMIT 5;"`
Expected: one row with `event=building.created`, `status=pending` (or `sent` if InfraSafe is running and processed it)

- [ ] **Step 4: Verify InfraSafe received the webhook**

Run: `docker exec infrasafe-postgres-1 psql -U postgres -d infrasafe -c "SELECT * FROM integration_log ORDER BY created_at DESC LIMIT 1;"`
Expected: row with `event_type=building.created`

- [ ] **Step 5: Test retry with exponential backoff — stop InfraSafe, create building**

```bash
# Stop InfraSafe
cd /Users/andreyafanasyev/Code/Infrasafe && docker compose -f docker-compose.dev.yml stop app

# Create another building
curl -X POST http://localhost:8085/api/v2/addresses/buildings \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"address":"Test Retry Building","yard_id":1,"entrance_count":1,"floor_count":3}'

# Wait ~15 seconds for 1-2 retry attempts with backoff
sleep 15

# Check outbox — should be pending with attempts > 0 and retry_after set
docker exec uk-postgres psql -U uk_bot -d uk_management -c \
  "SELECT id, event, status, attempts, retry_after, last_error FROM webhook_outbox WHERE status = 'pending' ORDER BY id DESC LIMIT 5;"

# Restart InfraSafe
cd /Users/andreyafanasyev/Code/Infrasafe && docker compose -f docker-compose.dev.yml start app

# Wait for next outbox poll cycle
sleep 15

# Verify retry succeeded — status should be 'sent'
docker exec uk-postgres psql -U uk_bot -d uk_management -c \
  "SELECT id, event, status, attempts, sent_at FROM webhook_outbox ORDER BY id DESC LIMIT 5;"
```
