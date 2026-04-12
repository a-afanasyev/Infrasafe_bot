# Security Remediation & Deployment Readiness — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Устранить все CRITICAL/HIGH/MEDIUM уязвимости и довести проект до production-ready состояния.

**Architecture:** 5 фаз: экстренная ротация секретов -> критические баги безопасности -> high-priority hardening -> medium-priority validation -> стабилизация (тесты, мониторинг, CI/CD). Каждая фаза — самостоятельный деплой-кандидат.

**Tech Stack:** Python 3.11, aiogram 3, FastAPI, SQLAlchemy, Alembic, React/Vite/TypeScript, Docker, Caddy, PostgreSQL, Redis.

**Canonical Deployment Path:** `docker-compose.production.yml` is the SINGLE authoritative
production compose file. All security/resource fixes target this file ONLY. The other compose
files serve different purposes:

| File | Purpose | Modify in this plan? |
| --- | --- | --- |
| `docker-compose.production.yml` | **Production (canonical)** | YES — all prod fixes here |
| `docker-compose.yml` | Local development | Only if dev-specific fix |
| `docker-compose.prod.unified.yml` | Legacy unified deployment | Fix CRIT-4 (Dockerfile.dev), then deprecate |
| `docker-compose.prod.yml` | Legacy prod override | Do not use — conflicts with production.yml |
| `docker-compose.unified.yml` | Dev unified | Only dev port binding fix |
| `docker-compose.dev.yml` | Dev override | Only dev port binding fix |

Tasks that reference "production compose" always mean `docker-compose.production.yml` unless
explicitly stated otherwise.

---

## Phase 0: Emergency — Credential Rotation & Git Cleanup

> **Блокирует всё остальное.** Токены в git-истории доступны прямо сейчас.

### Task 0.1: Rotate All Leaked Credentials

**Files:**
- Modify: `.gitignore`
- Delete from tracking: `env.copy`, `env.copy.dev`, `ssl/cert.pem`, `ssl/key.pem`

- [ ] **Step 1: Revoke Telegram bot tokens**

Open @BotFather, `/revoke` for both bots:
- `BOT_TOKEN` (main bot)
- `MEDIA_BOT_TOKEN` (media bot)

Generate new tokens. Update `.env` on production server.

- [ ] **Step 2: Rotate all other secrets on production**

```bash
# On production server:
# Generate new secrets
openssl rand -hex 32  # → new INVITE_SECRET
openssl rand -hex 32  # → new JWT_SECRET
openssl rand -hex 32  # → new POSTGRES_PASSWORD
openssl rand -hex 16  # → new REDIS_PASSWORD
# Generate new admin password (min 12 chars)
# Update .env with all new values
# Restart all services
```

- [ ] **Step 3: Remove tracked secret files from git**

```bash
git rm --cached env.copy env.copy.dev ssl/cert.pem ssl/key.pem
```

- [ ] **Step 4: Update .gitignore**

Add to `.gitignore`:
```
env.copy
env.copy.dev
ssl/
```

- [ ] **Step 5: Commit gitignore + removals**

```bash
git add .gitignore
git commit -m "security: remove leaked credentials from tracking, update .gitignore"
```

- [ ] **Step 6: Rewrite git history (if repo is shared)**

```bash
# WARNING: requires all collaborators to re-clone
# --invert-paths is a single flag that inverts ALL --path arguments
git filter-repo --invert-paths --path env.copy --path env.copy.dev --path ssl/cert.pem --path ssl/key.pem --force
git push --force --all
```

- [ ] **Step 7: Update .dockerignore**

Add entries for files that should never enter Docker images:
```
env.copy
env.copy.dev
env.*.example
ssl/
audit/
scans/
auth_scan.json
scan_report.txt
*.db
```

- [ ] **Step 8: Commit .dockerignore**

```bash
git add .dockerignore
git commit -m "security: harden .dockerignore against secret leakage"
```

---

### Task 0.2: Verify Frontend Dependencies Are Patched

> **Note:** `frontend/package.json` already has `axios: ^1.13.6` and `vite: ^7.3.1`.
> The `^` ranges may or may not resolve to patched versions depending on lock file state.
> No `test` script exists in `package.json` — only `dev`, `build`, `lint`, `preview`.

**Files:**
- Verify: `frontend/package-lock.json` (resolved versions)

- [ ] **Step 1: Audit current resolved versions**

```bash
cd frontend && npm audit --production
```

If 0 vulnerabilities: skip to Step 3.
If vulnerabilities found: run `npm audit fix` to update lock file.

- [ ] **Step 2: If needed, fix and verify**

```bash
npm audit fix
npm audit --production
```

Expected: 0 vulnerabilities (production deps).

- [ ] **Step 3: Verify build still works (no test script exists)**

```bash
npm run build
```

Expected: clean build, no errors.

- [ ] **Step 4: Commit (only if lock file changed)**

```bash
git add package.json package-lock.json
git commit -m "security: update frontend dependencies to patch known CVEs"
```

---

## Phase 1: Critical Security Fixes — Before Deploy

### Task 1.1: Fix Invite Nonce Wildcard Injection + TOCTOU Race Condition

> **Context:** `invite_service.py:239` uses `AuditLog.details.cast(String).contains(f'"nonce":"{nonce}"')`.
> SQLAlchemy `.contains()` translates to `LIKE '%...%'` in PostgreSQL. The f-string injects the nonce
> value directly into the LIKE pattern — `_` and `%` characters in the nonce become wildcards.
> Combined with a TOCTOU race condition (separate check and mark transactions), this allows
> invite token reuse.
>
> **Fix approach:** Replace the LIKE-on-JSON-text pattern with a dedicated `invite_nonces` table
> with a UNIQUE constraint on `nonce`. Use atomic INSERT (unique violation = already used).
> **Delete** the old `is_nonce_used()` and `mark_nonce_used()` methods entirely.

**Files:**
- Create: `alembic/versions/005_add_invite_nonces_table.py`
- Create: `uk_management_bot/database/models/invite_nonce.py` (or add to existing models)
- Modify: `uk_management_bot/services/invite_service.py` — delete `is_nonce_used()` (lines 224-247), delete `mark_nonce_used()`, rewrite `validate_invite_token()` (lines 197-211)
- Create: `tests/test_invite_nonce.py`

- [ ] **Step 1: Verify current Alembic head**

```bash
docker exec uk-management-bot python -m alembic heads
```

Expected: single head `004`. If different, adjust `down_revision` in step 3 accordingly.

- [ ] **Step 2: Write failing test for atomic nonce check**

```python
# tests/test_invite_nonce.py
import pytest
from unittest.mock import MagicMock, patch
from uk_management_bot.services.invite_service import InviteService

class TestInviteNonceAtomicity:
    def test_nonce_with_underscore_not_treated_as_wildcard(self):
        """Nonce containing '_' must match exactly, not as LIKE wildcard."""
        service = InviteService(db=MagicMock())
        nonce = "abc_def_ghi"
        # After fix: should use exact equality via UNIQUE constraint, not LIKE
        # This test verifies the nonce is not reusable due to LIKE wildcards
        pass  # Will be fleshed out after model creation

    def test_concurrent_nonce_use_blocked_by_unique_constraint(self):
        """Two concurrent uses of the same nonce must fail one."""
        pass  # Integration test requiring real DB session
```

- [ ] **Step 3: Run test to verify it fails**

```bash
docker exec uk-management-bot pytest tests/test_invite_nonce.py -v
```

- [ ] **Step 4: Create Alembic migration for invite_nonces table**

Use `alembic revision` to generate with correct hash, or create manually:

```python
# alembic/versions/005_add_invite_nonces_table.py
"""Add invite_nonces table for atomic nonce validation."""

from alembic import op
import sqlalchemy as sa

# Use alembic revision --autogenerate to get proper hash-based revision ID
revision = "005"
down_revision = "004"  # VERIFY with `alembic heads` in Step 1

def upgrade():
    op.create_table(
        "invite_nonces",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nonce", sa.String(64), nullable=False, unique=True),
        sa.Column("used_by", sa.BigInteger, nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("invite_payload", sa.JSON, nullable=True),
    )
    op.create_index("ix_invite_nonces_nonce", "invite_nonces", ["nonce"], unique=True)
    # Migrate existing nonce data from AuditLog
    op.execute("""
        INSERT INTO invite_nonces (nonce, used_by, used_at, invite_payload)
        SELECT
            (details::json->>'nonce')::varchar(64),
            (details::json->>'used_by')::bigint,
            created_at,
            details::json
        FROM audit_logs
        WHERE action = 'invite_used'
          AND details::json->>'nonce' IS NOT NULL
        ON CONFLICT (nonce) DO NOTHING
    """)

def downgrade():
    op.drop_table("invite_nonces")
```

- [ ] **Step 5: Add InviteNonce model**

Add to the appropriate models file:
```python
class InviteNonce(Base):
    __tablename__ = "invite_nonces"
    id = Column(Integer, primary_key=True)
    nonce = Column(String(64), nullable=False, unique=True, index=True)
    used_by = Column(BigInteger, nullable=True)
    used_at = Column(DateTime(timezone=True), server_default=func.now())
    invite_payload = Column(JSON, nullable=True)
```

- [ ] **Step 6: Replace LIKE-based nonce check with atomic INSERT and DELETE old methods**

In `uk_management_bot/services/invite_service.py`:

**DELETE** entirely: `is_nonce_used()` method (lines 224-247).
**DELETE** entirely: `mark_nonce_used()` method.

**ADD** new atomic method:
```python
def _use_nonce_atomically(self, nonce: str, used_by: int, payload: dict) -> bool:
    """Atomically check and mark nonce as used. Returns True if successful, False if already used."""
    try:
        invite_nonce = InviteNonce(
            nonce=nonce,
            used_by=used_by,
            invite_payload=payload,
        )
        self.db.add(invite_nonce)
        self.db.flush()  # Triggers unique constraint check
        return True
    except IntegrityError:
        self.db.rollback()
        return False
```

**REWRITE** `validate_invite_token()` (lines 197-211) — replace the check-then-mark pattern:
```python
# OLD (lines 197-211):
# if self.is_nonce_used(nonce):
#     raise ValueError("Token already used")
# ... later ...
# self.mark_nonce_used(nonce, mark_used_by, payload)

# NEW:
if not self._use_nonce_atomically(nonce, mark_used_by, payload):
    raise ValueError("Token already used")
```

- [ ] **Step 7: Run test to verify it passes**

```bash
docker exec uk-management-bot pytest tests/test_invite_nonce.py -v
```

- [ ] **Step 8: Commit**

```bash
git add alembic/ uk_management_bot/services/invite_service.py uk_management_bot/database/ tests/
git commit -m "security: fix invite nonce wildcard injection and TOCTOU race condition (CRIT-2)"
```

---

### Task 1.2: Remove Dev JWT Fallback & Add iss/aud Validation

**Files:**
- Modify: `uk_management_bot/api/auth/service.py:17-23,39,53`
- Create: `tests/test_auth_service_security.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_auth_service_security.py
import pytest
from unittest.mock import patch

def test_missing_jwt_secret_raises_in_production():
    """Without JWT_SECRET and INVITE_SECRET, startup must fail even if DEBUG=True."""
    with patch("uk_management_bot.config.settings.JWT_SECRET", ""), \
         patch("uk_management_bot.config.settings.INVITE_SECRET", ""), \
         patch("uk_management_bot.config.settings.DEBUG", True):
        with pytest.raises(RuntimeError, match="JWT_SECRET or INVITE_SECRET must be set"):
            # Re-import to trigger module-level code
            import importlib
            import uk_management_bot.api.auth.service as svc
            importlib.reload(svc)

def test_jwt_contains_issuer_and_audience():
    """Tokens must include iss and aud claims."""
    from uk_management_bot.api.auth.service import create_access_token, verify_access_token
    token = create_access_token(user_id=1, roles=["applicant"])
    payload = verify_access_token(token)
    assert payload["iss"] == "uk-management"
    assert payload["aud"] == "uk-management-api"
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
docker exec uk-management-bot pytest tests/test_auth_service_security.py -v
```

- [ ] **Step 3: Fix auth/service.py**

`uk_management_bot/api/auth/service.py` — remove dev fallback (lines 17-23):
```python
SECRET_KEY = settings.JWT_SECRET or settings.INVITE_SECRET
if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET or INVITE_SECRET must be set in all environments")
```

Add iss/aud to `create_access_token()` (around line 39):
```python
payload = {
    "sub": str(user_id),
    "roles": roles,
    "exp": expire,
    "iss": "uk-management",
    "aud": "uk-management-api",
}
```

Add iss/aud validation to `verify_access_token()` (around line 53):
```python
return jwt.decode(
    token, SECRET_KEY, algorithms=[ALGORITHM],
    audience="uk-management-api",
    issuer="uk-management",
)
```

- [ ] **Step 4: Run test — expect PASS**

```bash
docker exec uk-management-bot pytest tests/test_auth_service_security.py -v
```

- [ ] **Step 5: Commit**

```bash
git add uk_management_bot/api/auth/service.py tests/test_auth_service_security.py
git commit -m "security: remove dev JWT fallback, add iss/aud claim validation (HIGH-4, MED-1)"
```

---

### Task 1.3: Fix Production Docker Configs

**Files:**
- Modify: `docker-compose.prod.unified.yml:9`
- Modify: `Dockerfile.api:16`

- [ ] **Step 1: Fix prod compose to use production Dockerfile**

`docker-compose.prod.unified.yml` line 9: change `Dockerfile.dev` → `Dockerfile`:
```yaml
bot:
  build:
    context: .
    dockerfile: Dockerfile
```

- [ ] **Step 2: Replace COPY . . in Dockerfile.api with explicit copies**

`Dockerfile.api` line 16 — replace `COPY . .` with:
```dockerfile
COPY uk_management_bot/ ./uk_management_bot/
COPY alembic/ ./alembic/
COPY alembic.ini .
```

- [ ] **Step 3: Verify build**

```bash
# Use the same compose file that was modified (prod.unified)
docker compose -f docker-compose.prod.unified.yml build --no-cache bot
# Also verify the main production compose (uses Dockerfile by default — should still work)
docker compose -f docker-compose.production.yml build --no-cache api app
```

Expected: all build successfully.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.prod.unified.yml Dockerfile.api
git commit -m "security: fix prod Dockerfile.dev usage, restrict COPY scope in API image (CRIT-4, HIGH-1)"
```

---

### Task 1.4: Add Alembic Migration to Entrypoint (API Only)

> **Race condition risk:** If both bot and API run `alembic upgrade head` on startup,
> two processes may attempt the same migration concurrently, causing errors.
> **Solution:** Only the API container runs migrations. The bot waits for the API healthcheck
> (already configured via `depends_on: api: condition: service_healthy` pattern — add if missing).
> Alternatively, use a one-shot init container.

**Files:**
- Create: `scripts/entrypoint-api.sh` (migration + start)
- Create: `scripts/entrypoint-bot.sh` (wait for DB readiness, no migration)
- Modify: `Dockerfile.api:26`
- Modify: `Dockerfile:67`
- Modify: `uk_management_bot/main.py:162`

- [ ] **Step 1: Create API entrypoint (runs migrations)**

```bash
#!/bin/sh
# scripts/entrypoint-api.sh — ONLY the API container runs migrations
set -e

echo "Running database migrations..."
python -m alembic upgrade head
echo "Migrations complete."

echo "Starting API..."
exec "$@"
```

- [ ] **Step 2: Create bot entrypoint (no migrations)**

```bash
#!/bin/sh
# scripts/entrypoint-bot.sh — bot does NOT run migrations (API does)
set -e

echo "Starting bot..."
exec "$@"
```

- [ ] **Step 3: Add entrypoint to API Dockerfile only**

Add before `CMD` in `Dockerfile.api`:
```dockerfile
COPY scripts/entrypoint-api.sh /app/entrypoint.sh
USER root
RUN chmod +x /app/entrypoint.sh
USER appuser

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "uk_management_bot.api.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
```

- [ ] **Step 4: Add entrypoint to bot Dockerfile (no migration)**

Add before `CMD` in `Dockerfile`:
```dockerfile
COPY scripts/entrypoint-bot.sh /app/entrypoint.sh
USER root
RUN chmod +x /app/entrypoint.sh
USER app

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "uk_management_bot/main.py"]
```

> **Note:** Keep `CMD ["python", "uk_management_bot/main.py"]` to match existing behavior
> (current Dockerfile line 67). Do NOT change to `python -m` — different `sys.path` semantics.

- [ ] **Step 5: Add bot dependency on API in production compose**

In `docker-compose.production.yml`, make the bot wait for the API (which runs migrations):
```yaml
app:
  depends_on:
    postgres: { condition: service_healthy }
    redis: { condition: service_healthy }
    api: { condition: service_healthy }   # ← API runs migrations first
```

- [ ] **Step 6: Remove create_all() AND legacy runtime migration from main.py**

`uk_management_bot/main.py` — remove two blocks that mutate DB at runtime:

**Block 1** (lines 160-163) — `create_all()`:
```python
# DELETE:
# import uk_management_bot.database.models
# Base.metadata.create_all(bind=engine)
# logger.info("База данных инициализирована")

# REPLACE WITH:
logger.info("Database schema managed via Alembic (API entrypoint)")
```

**Block 2** (lines 174-183) — legacy runtime migration:
```python
# DELETE ENTIRELY:
# from uk_management_bot.database.migrations.fix_manager_confirmed_legacy import migrate_legacy_manager_confirmed
# migration_db = SessionLocal()
# migrated = migrate_legacy_manager_confirmed(migration_db)
# ...
# migration_db.close()
```

> **Why:** This legacy data migration (`fix_manager_confirmed_legacy`) runs on every bot startup
> and mutates rows in the DB. After moving to Alembic-managed entrypoint, this must be a one-time
> Alembic data migration instead. If the migration has already run in production (check
> `SELECT count(*) FROM requests WHERE manager_confirmed IS NOT NULL`), it can simply be deleted.
> Otherwise, convert it to an Alembic `op.execute()` data migration before removing from main.py.

- [ ] **Step 7: Build and verify startup order**

```bash
docker compose -f docker-compose.production.yml build app api
docker compose -f docker-compose.production.yml up -d
# API starts first, runs migrations
docker logs uk-management-api --tail 10
# Expected: "Running database migrations..." → "Migrations complete." → "Starting API..."
# Bot starts after API is healthy
docker logs uk-management-bot --tail 10
# Expected: "Starting bot..." (no migration output)
```

- [ ] **Step 8: Commit**

```bash
git add scripts/entrypoint-api.sh scripts/entrypoint-bot.sh Dockerfile Dockerfile.api \
  uk_management_bot/main.py docker-compose.production.yml
git commit -m "feat: API-only alembic migration in entrypoint, remove create_all() (no race)"
```

---

### Task 1.5: Rewrite Init Scripts (Multiple Issues)

> **Problems in `scripts/init_postgres.sql`:**
> 1. Line 11: `CREATE DATABASE IF NOT EXISTS` — **invalid PostgreSQL syntax** (MySQL-only).
>    PostgreSQL requires `SELECT 'CREATE DATABASE ...' WHERE NOT EXISTS (...)` or PL/pgSQL.
> 2. Lines 22-30: `CREATE USER uk_bot WITH PASSWORD 'uk_bot_password'` — hardcoded password.
> 3. Lines 66+: Full schema DDL duplicates what SQLAlchemy models + Alembic already manage.
>
> **Problems in `scripts/init_postgres.sh`:**
> 1. Line 48: Hardcoded `'uk_bot_password'` in CREATE USER fallback.
> 2. Redundant checks — the `postgres:15-alpine` image already creates `POSTGRES_USER`
>    with `POSTGRES_PASSWORD` and the database `POSTGRES_DB` before init scripts run.
>
> **Fix:** The init scripts should ONLY do what the Postgres image + Alembic cannot:
> extensions, permissions, and default privileges. No schema DDL. No user/db creation.

**Files:**
- Rewrite: `scripts/init_postgres.sql`
- Rewrite: `scripts/init_postgres.sh`

- [ ] **Step 1: Rewrite init_postgres.sql — extensions and permissions only**

```sql
-- UK Management Bot — PostgreSQL Init (runs as superuser)
-- The postgres image already creates POSTGRES_USER, POSTGRES_PASSWORD, and POSTGRES_DB.
-- This script only sets up extensions and grants.

-- NOTE: This runs inside the POSTGRES_DB database context (docker-entrypoint handles \c).

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Permissions for the app user (POSTGRES_USER is available as a psql variable)
-- Tables and sequences are created by Alembic, not here.
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO current_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO current_user;
```

Delete ALL the `CREATE TABLE` DDL (lines 66+). Schema is managed by Alembic.
Delete `CREATE DATABASE IF NOT EXISTS` (line 11). The image handles this.
Delete `CREATE USER` block (lines 22-30). The image handles this.

- [ ] **Step 2: Rewrite init_postgres.sh — remove hardcoded passwords**

```bash
#!/bin/bash
set -e

echo "Starting PostgreSQL initialization..."

# The postgres:15-alpine image already created:
# - Database: $POSTGRES_DB
# - User: $POSTGRES_USER with password $POSTGRES_PASSWORD
# We only need to verify and set up extensions.

until pg_isready -U "$POSTGRES_USER" -h localhost; do
    sleep 2
done

echo "PostgreSQL is ready. Setting up extensions..."
psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /docker-entrypoint-initdb.d/01-init_postgres.sql

echo "Init complete."
```

Remove all hardcoded `'uk_bot_password'` strings. Remove all `CREATE USER` fallbacks.

- [ ] **Step 3: Verify init scripts work with docker compose**

```bash
# Remove existing volume to test fresh init
docker compose down -v
docker compose up -d postgres
docker logs uk-postgres --tail 20
```

Expected: no `CREATE DATABASE IF NOT EXISTS` errors, extensions created, no hardcoded passwords.

- [ ] **Step 4: Commit**

```bash
git add scripts/init_postgres.sql scripts/init_postgres.sh
git commit -m "security: rewrite init scripts — remove hardcoded passwords, invalid SQL, DDL duplication"
```

---

### Task 1.6: Setup Backup Cron

**Files:**
- Create: `scripts/crontab.production`

- [ ] **Step 1: Create crontab file**

```crontab
# UK Management — Database Backup
# Daily at 03:00 UTC
0 3 * * * /opt/uk-management/scripts/backup-db.sh >> /var/log/uk-backup.log 2>&1
```

- [ ] **Step 2: Document installation in deployment docs**

Add to deployment checklist:
```
crontab scripts/crontab.production
```

- [ ] **Step 3: Commit**

```bash
git add scripts/crontab.production
git commit -m "ops: add production crontab for automated daily backups"
```

---

## Phase 2: High Priority — Before Live Traffic

### Task 2.1: Standardize & Extend Rate Limiting

> **Current architecture problem:** Two separate `Limiter` instances exist:
> - `api/main.py:23` — `limiter = Limiter(key_func=get_remote_address)`, set as `app.state.limiter`
> - `api/auth/router.py:24` — **second** `limiter = Limiter(key_func=get_remote_address)`
>
> These are independent objects. If slowapi uses the app-level limiter for error handling
> (`app.state.limiter`) but auth routes use their own, rate limit exceeded errors may not
> be handled correctly.
>
> **Fix:** Standardize on ONE limiter instance (from `api/main.py`). All routers import it.

**Files:**
- Modify: `uk_management_bot/api/auth/router.py:5-6,24` (remove local limiter, import shared)
- Modify: `uk_management_bot/api/requests/router.py` (import shared limiter, add to POST/PATCH)
- Modify: `uk_management_bot/api/shifts/router.py` (import shared limiter, add to POST/PATCH)
- Modify: `uk_management_bot/api/profile/router.py` (import shared limiter, add to POST)
- Modify: `uk_management_bot/api/main.py:150` (add to media upload)
- Create: `tests/test_rate_limiting.py`

- [ ] **Step 1: Write failing test for /set-password rate limit**

```python
# tests/test_rate_limiting.py
import pytest
from httpx import AsyncClient

async def test_set_password_rate_limited(client: AsyncClient, auth_headers):
    """POST /set-password should be rate-limited to 5/minute."""
    for i in range(6):
        resp = await client.post("/api/v2/auth/set-password", headers=auth_headers, json={"password": "test"})
    assert resp.status_code == 429
```

- [ ] **Step 2: Run test — expect FAIL (no 429 returned)**

- [ ] **Step 3: Consolidate to single limiter instance**

**First:** Remove the duplicate limiter from `auth/router.py`.

In `uk_management_bot/api/auth/router.py`:
```python
# DELETE these lines (5-6, 24):
# from slowapi import Limiter
# from slowapi.util import get_remote_address
# limiter = Limiter(key_func=get_remote_address)

# ADD this import instead:
from uk_management_bot.api.rate_limit import limiter
```

**Create a shared module** `uk_management_bot/api/rate_limit.py` to avoid circular imports:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
```

Update `api/main.py:23` to import from the shared module:
```python
from uk_management_bot.api.rate_limit import limiter
# ... later ...
app.state.limiter = limiter
```

- [ ] **Step 4: Add rate limits to all routers**

Each router file gets the same import:
```python
from fastapi import Request
from uk_management_bot.api.rate_limit import limiter
```

Pattern for each router — add `request: Request` parameter + `@limiter.limit()`:

**auth/router.py** — add to `/set-password`:
```python
@router.post("/set-password")
@limiter.limit("5/minute")
async def set_password(request: Request, ...):
```

**requests/router.py** — add to POST create, PATCH update:
```python
@router.post("/")
@limiter.limit("20/minute")
async def create_request(request: Request, ...):

@router.patch("/{request_number}")
@limiter.limit("30/minute")
async def update_request(request: Request, ...):
```

**shifts/router.py** — add to POST/PATCH:
```python
@router.post("/")
@limiter.limit("10/minute")

@router.patch("/{shift_id}")
@limiter.limit("20/minute")
```

**profile/router.py** — add to document upload:
```python
@router.post("/documents")
@limiter.limit("10/minute")
```

**api/main.py** — media upload:
```python
@app.post("/api/v2/media/upload")
@limiter.limit("10/minute")
```

- [ ] **Step 4: Run test — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add uk_management_bot/api/ tests/test_rate_limiting.py
git commit -m "security: add rate limiting to all mutating API endpoints (HIGH-2, HIGH-3)"
```

---

### Task 2.2: Move JWT from localStorage to httpOnly Cookies

> **Большое изменение.** Затрагивает бэкенд (установка cookies) и фронтенд (убрать localStorage).

**Files:**
- Modify: `uk_management_bot/api/auth/router.py` (set cookies on login/refresh, add logout cookie-clearing)
- Modify: `uk_management_bot/api/dependencies.py:44-67` (read token from cookie, replace `HTTPBearer` dependency)
- Modify: `frontend/src/stores/authStore.ts` (remove localStorage token storage)
- Modify: `frontend/src/api/client.ts` (add `withCredentials: true`, remove Authorization header)
- Modify: `frontend/src/hooks/useWebSocket.ts` (remove token from URL — server reads cookie from WS upgrade)
- Modify: `frontend/src/twa/twaClient.ts` (adapt for cookie-based auth)
- Create: `tests/test_cookie_auth.py`

> **CSRF note:** Cookie-based auth introduces CSRF risk. `SameSite=Lax` protects most cases
> (blocks cross-site POST), but does NOT protect against:
> - Same-site subdomain attacks (if attacker controls `*.your-domain.com`)
> - GET-based state changes (ensure ALL mutations are POST/PATCH/DELETE, never GET)
>
> **Recommended:** Add a lightweight double-submit CSRF token:
> 1. On login, set a non-httpOnly cookie `csrf_token=<random>` alongside the httpOnly auth cookies
> 2. Frontend reads `csrf_token` from `document.cookie` and sends it as `X-CSRF-Token` header
> 3. Backend middleware compares the header value to the cookie value
>
> This is simple to implement and defends against subdomain attacks. Add as a sub-step of Step 2.
>
> **Login schema:** The current `PasswordLogin` schema uses `email` field (not `username`).
> See `uk_management_bot/api/auth/schemas.py:25-26`. All code examples below must use `email`.

- [ ] **Step 1: Write failing test for cookie-based auth**

```python
# tests/test_cookie_auth.py
import pytest
from httpx import AsyncClient

async def test_login_sets_httponly_cookie(client: AsyncClient):
    # NOTE: schema is PasswordLogin(email=..., password=...) — NOT username
    resp = await client.post("/api/v2/auth/login", json={"email": "admin@example.com", "password": "testpass"})
    assert resp.status_code == 200
    # Response body should contain user data but NOT tokens
    body = resp.json()
    assert "user" in body
    assert "access_token" not in body  # tokens are in cookies only
    # Verify httpOnly cookie is set
    set_cookie = resp.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie
    assert "SameSite=Lax" in set_cookie
```

- [ ] **Step 2: Implement cookie-based auth on backend**

In `uk_management_bot/api/auth/router.py`, after generating tokens:
```python
from fastapi.responses import JSONResponse

@router.post("/login")
async def login(...):
    # ... existing token generation ...
    # Keep tokens in body for TWA/mobile backward compat, but also set cookies for browser flow
    response = JSONResponse(content={
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": user_data,
    })
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/v2/auth/refresh",
    )
    return response
```

Update `get_current_user` in `uk_management_bot/api/dependencies.py` (NOT `auth/dependencies.py` — that file does not exist). The current function uses `HTTPAuthorizationCredentials = Depends(security)` via FastAPI's `HTTPBearer`. Replace with `Request`-based extraction:

```python
# uk_management_bot/api/dependencies.py — replace the existing get_current_user
from fastapi import Request, HTTPException

async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)):
    # 1. Try httpOnly cookie first
    token = request.cookies.get("access_token")
    # 2. Fallback to Authorization header (for TWA / backward compat)
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = verify_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    # ... rest of existing user lookup logic ...
```

Also remove/comment out the old `security = HTTPBearer()` declaration that is no longer needed.

Add a **logout endpoint** that clears cookies:
```python
# uk_management_bot/api/auth/router.py — add or update logout endpoint
@router.post("/logout")
async def logout(request: Request, db: AsyncSession = Depends(get_db)):
    # ... existing refresh token revocation logic ...
    response = JSONResponse(content={"ok": True})
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/api/v2/auth/refresh")
    return response
```

- [ ] **Step 3: Update frontend API client**

`frontend/src/api/client.ts`:
```typescript
const apiClient = axios.create({
    baseURL: BASE_URL,
    withCredentials: true,  // Send cookies
})

// Remove Authorization header interceptor for cookie-based flow
// Keep it only for TWA flow where cookies may not work
```

- [ ] **Step 4: Update authStore**

`frontend/src/stores/authStore.ts` — remove `localStorage.setItem('access_token', ...)`:
```typescript
login: async (user) => {
    // Cookies are set by server, no localStorage needed
    set({ user, isAuthenticated: true })
},
logout: async () => {
    await apiClient.post('/api/v2/auth/logout')
    // Server clears cookies in response
    set({ user: null, isAuthenticated: false })
},
```

- [ ] **Step 5: Fix WebSocket to use cookie-based auth (NOT token in URL)**

httpOnly cookies are NOT accessible via JavaScript — but the browser automatically sends cookies
with the WebSocket upgrade request (same-origin). So the fix is simple:

**Frontend** — `frontend/src/hooks/useWebSocket.ts`:
```typescript
// OLD: new WebSocket(`${WS_URL}/ws/v2/${endpoint}?token=${token}`)
// NEW: browser sends httpOnly cookie automatically with upgrade request
const ws = new WebSocket(`${WS_URL}/ws/v2/${endpoint}`)
```

Remove all `localStorage.getItem('access_token')` calls from this file. Remove the `token` variable.

**Backend** — update both WebSocket handlers in `uk_management_bot/api/ws/router.py` (NOT `api/main.py`).
The real handlers are `kanban_ws` (line 23) and `shifts_ws` (line 66). Both currently use
`token: str = Query(...)` which forces the token into the URL.

Change both handlers from Query param to cookie-first with Query fallback:
```python
# uk_management_bot/api/ws/router.py — update BOTH kanban_ws and shifts_ws

@router.websocket("/kanban")
async def kanban_ws(websocket: WebSocket, token: str = Query(default=None)):
    # Prefer httpOnly cookie (sent automatically with upgrade request)
    actual_token = websocket.cookies.get("access_token") or token
    if not actual_token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    payload = verify_access_token(actual_token)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    # ... rest unchanged ...

@router.websocket("/shifts")
async def shifts_ws(websocket: WebSocket, token: str = Query(default=None)):
    actual_token = websocket.cookies.get("access_token") or token
    # ... same pattern ...
```

- [ ] **Step 6: Run all tests**

```bash
docker exec uk-management-bot pytest tests/test_cookie_auth.py -v
cd frontend && npm test -- --run
```

- [ ] **Step 7: Commit**

```bash
git add uk_management_bot/api/auth/ frontend/src/ tests/
git commit -m "security: migrate JWT from localStorage to httpOnly cookies (CRIT-frontend-1, HIGH-3)"
```

---

### Task 2.3: Add HSTS & CSP to Caddyfile

**Files:**
- Modify: `Caddyfile:27-33`

- [ ] **Step 1: Update Caddyfile headers**

```
header {
    Strict-Transport-Security "max-age=31536000; includeSubDomains"
    X-Frame-Options "DENY"
    X-Content-Type-Options "nosniff"
    Referrer-Policy "strict-origin-when-cross-origin"
    Permissions-Policy "camera=(), microphone=(), geolocation=()"
    Content-Security-Policy "default-src 'self'; script-src 'self' https://telegram.org; style-src 'self' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; connect-src 'self' wss: ws:; img-src 'self' data: blob: https:; frame-src https://oauth.telegram.org; frame-ancestors 'self' https://web.telegram.org; base-uri 'self'; form-action 'self'; upgrade-insecure-requests"
    -Server
}
```

- [ ] **Step 2: Commit**

```bash
git add Caddyfile
git commit -m "security: add HSTS and CSP headers to Caddyfile (HIGH-6, HIGH-4)"
```

---

### Task 2.4: Consolidate CSP to Single Layer (Caddy) + Fix Frontend nginx

> **Problem:** CSP headers are set in 3 places: Caddyfile, frontend/nginx.conf, web/main.py.
> Multiple CSP layers are fragile — the browser uses the MOST restrictive intersection, and
> conflicting headers cause unpredictable behavior.
>
> **Solution:** Set CSP only in Caddy (the TLS-terminating reverse proxy). Remove CSP from
> frontend/nginx.conf (it's behind Caddy). Keep web/main.py CSP only if that web service
> is accessed directly (not via Caddy).

**Files:**
- Modify: `frontend/nginx.conf:15` (remove CSP, keep only HSTS for defense-in-depth)
- Note: Caddyfile CSP is already set in Task 2.3 above

- [ ] **Step 1: Remove CSP from frontend nginx (Caddy handles it)**

In `frontend/nginx.conf`, remove the CSP `add_header` line and replace with just HSTS:
```nginx
# CSP is set at Caddy layer — do NOT duplicate here
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header X-Content-Type-Options "nosniff" always;
```

- [ ] **Step 2: Build frontend and verify no breakage**

```bash
cd frontend && npm run build
```

- [ ] **Step 3: Test with Caddy CSP**

After deploying, open Chrome DevTools Console and check for CSP violation reports.
If violations appear for `style-src` in Caddy's CSP, add `'unsafe-inline'` to `style-src`
**only in the Caddyfile** (shadcn/ui may need it for inline styles).

- [ ] **Step 4: Commit**

```bash
git add frontend/nginx.conf
git commit -m "security: consolidate CSP to Caddy layer, remove duplicate from frontend nginx"
```

---

### Task 2.5: Add File Type Validation to Document Upload

**Files:**
- Modify: `uk_management_bot/api/profile/router.py:83-104`
- Create: `tests/test_document_upload_validation.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_document_upload_validation.py
import pytest
from io import BytesIO

async def test_upload_rejects_invalid_document_type(client, auth_headers):
    resp = await client.post(
        "/api/v2/profile/documents",
        headers=auth_headers,
        files={"file": ("test.pdf", BytesIO(b"%PDF-1.4 test"), "application/pdf")},
        data={"document_type": "malicious_type"},
    )
    assert resp.status_code == 400

async def test_upload_rejects_executable_file(client, auth_headers):
    resp = await client.post(
        "/api/v2/profile/documents",
        headers=auth_headers,
        files={"file": ("test.exe", BytesIO(b"MZ..."), "application/x-msdownload")},
        data={"document_type": "passport"},
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Implement validation**

In `uk_management_bot/api/profile/router.py`:
```python
ALLOWED_DOCUMENT_TYPES = {"passport", "license", "insurance", "medical", "contract"}
ALLOWED_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

@router.post("/documents")
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
    document_type: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    if document_type not in ALLOWED_DOCUMENT_TYPES:
        raise HTTPException(400, f"Invalid document_type. Allowed: {', '.join(ALLOWED_DOCUMENT_TYPES)}")
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(400, f"File type not allowed. Allowed: {', '.join(ALLOWED_MIME_TYPES)}")
    # ... existing size check ...
```

- [ ] **Step 3: Run tests**

- [ ] **Step 4: Commit**

```bash
git add uk_management_bot/api/profile/router.py tests/test_document_upload_validation.py
git commit -m "security: add file type and document_type validation on upload (HIGH-7)"
```

---

### Task 2.6: Pin Base Image Versions & Add CPU Limits

**Files:**
- Modify: `frontend/Dockerfile:10`
- Modify: `media_service/frontend/Dockerfile:1`
- Modify: `docker-compose.production.yml`

- [ ] **Step 1: Pin nginx version**

`frontend/Dockerfile` line 10:
```dockerfile
FROM nginx:1.27-alpine
```

`media_service/frontend/Dockerfile` line 1:
```dockerfile
FROM nginx:1.27-alpine
```

- [ ] **Step 2: Add CPU limits to production compose**

Add `cpus` to each service in `docker-compose.production.yml`:
```yaml
deploy:
  resources:
    limits:
      memory: 512M
      cpus: "1.0"
```

For frontend/caddy/redis (lighter services):
```yaml
deploy:
  resources:
    limits:
      memory: 128M
      cpus: "0.5"
```

- [ ] **Step 3: Commit**

```bash
git add frontend/Dockerfile media_service/frontend/Dockerfile docker-compose.production.yml
git commit -m "ops: pin nginx image versions, add CPU limits to production compose (HIGH-6, MED-4)"
```

---

### Task 2.7: Fix Media Proxy API Key & Media Service Security

**Files:**
- Modify: `uk_management_bot/api/main.py:150-173`
- Modify: `media_service/app/core/config.py:42-43`
- Modify: `media_service/app/main.py:111-115`

- [ ] **Step 1: Add API key header to media proxy calls**

In `uk_management_bot/api/main.py`, around lines 150-173:
```python
headers = {}
if settings.MEDIA_SERVICE_API_KEY:
    headers["X-API-Key"] = settings.MEDIA_SERVICE_API_KEY

async with httpx.AsyncClient(timeout=30, headers=headers) as client:
    resp = await client.post(
        f"{media_url}/api/v1/media/upload",
        files={"file": (file.filename, await file.read(), file.content_type)},
        data={...},
    )
```

Same for the GET proxy on line 173.

- [ ] **Step 2: Remove CORS wildcard default in media service**

`media_service/app/core/config.py`:
```python
allowed_origins: str = Field(default="", description="Comma-separated allowed origins. Required in production.")
```

- [ ] **Step 3: Remove grace mode in media service**

`media_service/app/main.py` lines 111-115 — remove the `if not settings.api_keys_list: return` block. Always require API key (exempt only `/health`).

- [ ] **Step 4: Commit**

```bash
git add uk_management_bot/api/main.py media_service/app/core/config.py media_service/app/main.py
git commit -m "security: fix media proxy API key, remove CORS wildcard and grace mode (HIGH-1, HIGH-5)"
```

---

## Phase 3: Medium Priority — Input Validation & Hardening

### Task 3.1: Add Category & Rating Validation

> **Note on rating:** The `UpdateRequestBody` schema (lines 61-76) does NOT currently have a `rating`
> field. However, `router.py:344` allows applicants to update `{"status", "rating"}` via `setattr()`.
> This means `rating` bypasses schema validation entirely — it's extracted from the raw dict and
> set directly on the model. The fix must EITHER:
> (a) Add `rating: Optional[int]` to `UpdateRequestBody` with a validator, OR
> (b) Validate rating in the router before `setattr()`.
> Option (a) is cleaner.

**Files:**
- Modify: `uk_management_bot/api/requests/schemas.py:44-59` (category validator)
- Modify: `uk_management_bot/api/requests/schemas.py:61-76` (add rating field + validator to UpdateRequestBody)
- Modify: `uk_management_bot/api/requests/router.py:344` (use schema-validated rating)
- Create: `tests/test_request_validation.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_request_validation.py
import pytest
from uk_management_bot.api.requests.schemas import CreateRequestBody, UpdateRequestBody

def test_create_request_rejects_invalid_category():
    with pytest.raises(ValueError, match="category"):
        CreateRequestBody(category="hacking", urgency="low", description="test")

def test_update_request_rejects_rating_out_of_range():
    """rating field must be added to UpdateRequestBody first."""
    with pytest.raises(ValueError, match="rating"):
        UpdateRequestBody(rating=10)

def test_update_request_rejects_negative_rating():
    with pytest.raises(ValueError, match="rating"):
        UpdateRequestBody(rating=-1)

def test_update_request_accepts_valid_rating():
    body = UpdateRequestBody(rating=4)
    assert body.rating == 4
```

- [ ] **Step 2: Implement validators**

In `uk_management_bot/api/requests/schemas.py`:

Add to `CreateRequestBody`:
```python
@field_validator("category")
@classmethod
def validate_category(cls, v: str) -> str:
    from uk_management_bot.config.settings import settings
    valid = settings.REQUEST_CATEGORIES
    if v not in valid:
        raise ValueError(f"category must be one of: {valid}")
    return v
```

Add `rating` field to `UpdateRequestBody` (it currently has no such field):
```python
class UpdateRequestBody(BaseModel):
    # ... existing fields ...
    rating: Optional[int] = None

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v):
        if v is not None and (not isinstance(v, int) or v < 1 or v > 5):
            raise ValueError("rating must be an integer between 1 and 5")
        return v
```

- [ ] **Step 3: Run tests — expect PASS**

- [ ] **Step 4: Commit**

```bash
git add uk_management_bot/api/requests/schemas.py uk_management_bot/api/requests/router.py tests/test_request_validation.py
git commit -m "security: add category allowlist and rating range validation (MED-6, HIGH-8)"
```

---

### Task 3.2: Validate request_number Before Proxy Forwarding

**Files:**
- Modify: `uk_management_bot/api/main.py:173`

- [ ] **Step 1: Add regex validation**

```python
import re

REQUEST_NUMBER_PATTERN = re.compile(r"^\d{6}-\d{3}$")

@app.get("/api/v2/media/request/{request_number}")
async def proxy_media_list(request_number: str, ...):
    if not REQUEST_NUMBER_PATTERN.match(request_number):
        raise HTTPException(400, "Invalid request number format. Expected: YYMMDD-NNN")
    ...
```

- [ ] **Step 2: Commit**

```bash
git add uk_management_bot/api/main.py
git commit -m "security: validate request_number format before media proxy (MED-4)"
```

---

### Task 3.3: Fix SQL Interpolation in Migration Script

> **Severity note:** The column names come from a hardcoded Python list (not user input),
> so this is NOT exploitable at runtime. Downgraded from CRIT to MED — defense-in-depth fix
> to prevent the pattern from being copy-pasted into exploitable contexts.

**Files:**
- Modify: `uk_management_bot/database/migrations/add_address_directory.py:124-132`

- [ ] **Step 1: Parameterize the information_schema query**

```python
# Line 124-128: replace f-string with parameterized query
result = conn.execute(
    text("SELECT column_name FROM information_schema.columns WHERE table_name = :tbl AND column_name = :col"),
    {"tbl": "users", "col": column}
)
```

Keep the DDL with explicit allowlist check (DDL cannot use bind params for identifiers):
```python
ALLOWED_LEGACY_COLUMNS = frozenset({"address", "home_address", "apartment_address", "yard_address", "address_type"})
if column in ALLOWED_LEGACY_COLUMNS:
    conn.execute(text(f'ALTER TABLE users DROP COLUMN IF EXISTS "{column}"'))
```

- [ ] **Step 2: Commit**

```bash
git add uk_management_bot/database/migrations/add_address_directory.py
git commit -m "security: parameterize SQL in migration script (MED — defense in depth)"
```

---

### Task 3.4: Fix CSP in Web Main (Bot Web Interface)

**Files:**
- Modify: `uk_management_bot/web/main.py:49`

- [ ] **Step 1: Replace unsafe-inline with stricter CSP**

```python
response.headers["Content-Security-Policy"] = (
    "default-src 'self'; "
    "frame-ancestors 'self' https://web.telegram.org https://telegram.org; "
    "script-src 'self' https://telegram.org; "
    "style-src 'self' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: https:; "
    "connect-src 'self' https:; "
    "base-uri 'self'; "
    "form-action 'self'"
)
```

- [ ] **Step 2: Commit**

```bash
git add uk_management_bot/web/main.py
git commit -m "security: remove unsafe-inline from bot web interface CSP (MED-5)"
```

---

### Task 3.5: Move Bot Username to Environment Variable

**Files:**
- Modify: `uk_management_bot/config/settings.py` (add `BOT_USERNAME`)
- Modify: `uk_management_bot/services/invite_service.py:98`
- Modify: `uk_management_bot/api/shifts/router.py:232`
- Modify: `frontend/src/pages/LoginPage.tsx:10`
- Modify: `.env.production.template`

- [ ] **Step 1: Add to settings**

```python
BOT_USERNAME = os.getenv("BOT_USERNAME", "infrasafebot")
```

- [ ] **Step 2: Replace hardcoded values in backend**

`invite_service.py:98`: replace `"infrasafebot"` with `settings.BOT_USERNAME`
`shifts/router.py:232`: same

- [ ] **Step 3: Replace hardcoded value in frontend**

`LoginPage.tsx:10`:
```typescript
const BOT_USERNAME = import.meta.env.VITE_BOT_USERNAME ?? 'infrasafebot'
```

- [ ] **Step 4: Add to env template**

```
BOT_USERNAME=your_bot_username
```

- [ ] **Step 5: Commit**

```bash
git add uk_management_bot/config/settings.py uk_management_bot/services/invite_service.py \
  uk_management_bot/api/shifts/router.py frontend/src/pages/LoginPage.tsx .env.production.template
git commit -m "refactor: move bot username to env var (LOW-1)"
```

---

### Task 3.6: Fix Structured Logger (Selective Redaction)

**Files:**
- Modify: `uk_management_bot/utils/structured_logger.py:62-82`
- Create: `tests/test_structured_logger.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_structured_logger.py
import logging
from uk_management_bot.utils.structured_logger import SecurityFilter

def test_security_filter_redacts_only_values():
    f = SecurityFilter()
    record = logging.LogRecord("test", logging.INFO, "", 0, "User login with token=abc123xyz", (), None)
    f.filter(record)
    assert "abc123xyz" not in record.getMessage()
    assert "login" in record.getMessage()  # Context preserved

def test_security_filter_preserves_auth_middleware_message():
    f = SecurityFilter()
    record = logging.LogRecord("test", logging.INFO, "", 0, "Auth middleware initialized", (), None)
    f.filter(record)
    assert "Auth middleware initialized" in record.getMessage()  # NOT redacted
```

- [ ] **Step 2: Implement selective redaction**

```python
import re

class SecurityFilter(logging.Filter):
    REDACT_PATTERNS = [
        re.compile(r"(password|token|secret|bearer|api.key)\s*[=:]\s*\S+", re.IGNORECASE),
        re.compile(r"(Authorization:\s*Bearer\s+)\S+", re.IGNORECASE),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for pattern in self.REDACT_PATTERNS:
            msg = pattern.sub(lambda m: m.group().split("=")[0] + "=[REDACTED]" if "=" in m.group() else m.group().split(":")[0] + ": [REDACTED]", msg)
        record.msg = msg
        record.args = ()
        return True
```

- [ ] **Step 3: Run test — expect PASS**

- [ ] **Step 4: Commit**

```bash
git add uk_management_bot/utils/structured_logger.py tests/test_structured_logger.py
git commit -m "fix: selective log redaction instead of blanket replacement (MED-7)"
```

---

### Task 3.7: Fix Redis & Port Configuration Across Compose Files

> **Scope per canonical deployment path:**
> - `docker-compose.production.yml` — already correct (Redis has `--requirepass`, no exposed ports)
> - `docker-compose.yml` — dev compose: fix Redis healthcheck + bind ports to loopback
> - `docker-compose.prod.yml` — legacy override: do NOT fix, mark as deprecated
> - `docker-compose.unified.yml` — dev unified: bind ports to loopback

**Files:**
- Modify: `docker-compose.yml:152,164` (fix Redis healthcheck for password-aware mode)
- Modify: `docker-compose.yml:137,170` (bind Postgres/Redis to loopback in dev)
- Modify: `docker-compose.unified.yml:139-140,159-160` (bind to loopback)

- [ ] **Step 1: Fix dev compose Redis healthcheck**

`docker-compose.yml` line 164:
```yaml
healthcheck:
  test: ["CMD-SHELL", "redis-cli ${REDIS_PASSWORD:+-a $REDIS_PASSWORD} ping"]
```

- [ ] **Step 2: Bind dev ports to loopback (dev compose files only)**

`docker-compose.yml` — Postgres (line 137) and Redis (line 170):
```yaml
ports:
  - "127.0.0.1:5432:5432"
# ...
  - "127.0.0.1:6379:6379"
```

`docker-compose.unified.yml` — same pattern:
```yaml
ports:
  - "127.0.0.1:${POSTGRES_PORT:-5432}:5432"
# ...
  - "127.0.0.1:${REDIS_PORT:-6379}:6379"
```

> `docker-compose.production.yml` already has no exposed Postgres/Redis ports — correct.
> `docker-compose.prod.yml` is legacy and NOT part of the canonical path — skip.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml docker-compose.unified.yml
git commit -m "security: bind dev DB/Redis ports to loopback, fix Redis healthcheck"
```

---

### Task 3.8: Harden Production Settings Validation

**Files:**
- Modify: `uk_management_bot/config/settings.py`

- [ ] **Step 1: Add stricter validation for production**

Add after existing validation block:
```python
if not DEBUG:
    # All secrets must be explicitly set in production
    if not JWT_SECRET:
        raise ValueError("JWT_SECRET must be set in production")
    if JWT_SECRET == INVITE_SECRET:
        raise ValueError("JWT_SECRET and INVITE_SECRET must be different")
    if not REDIS_URL or "redis://" not in REDIS_URL:
        raise ValueError("Valid REDIS_URL required in production")
    if ADMIN_PASSWORD and len(ADMIN_PASSWORD) < 12:
        raise ValueError("ADMIN_PASSWORD must be at least 12 characters in production")
```

- [ ] **Step 2: Update .env.production.template with missing vars**

Add to template:
```
MEDIA_SERVICE_URL=http://media:8001
MEDIA_SERVICE_API_KEY=             # openssl rand -hex 32
MEDIA_SERVICE_ENABLED=true
BOT_USERNAME=your_bot_username
```

- [ ] **Step 3: Commit**

```bash
git add uk_management_bot/config/settings.py .env.production.template
git commit -m "security: stricter production settings validation, document missing env vars (MED)"
```

---

### Task 3.9: Add Client-Side Type Validation for Telegram Widget

> **Backend hash validation already implemented.** `verify_telegram_widget()` exists at
> `uk_management_bot/api/auth/service.py:67` and is called from `router.py:50`.
> Tests exist at `test_service.py:135-191`. No backend changes needed.
>
> Only the frontend needs a type guard for the `window.onTelegramAuth` callback.

**Files:**
- Modify: `frontend/src/pages/LoginPage.tsx:23-36`

- [ ] **Step 1: Add client-side type validation for TelegramUser**

`frontend/src/pages/LoginPage.tsx`:
```typescript
interface TelegramUser {
    id: number
    first_name: string
    last_name?: string
    username?: string
    photo_url?: string
    auth_date: number
    hash: string
}

function isTelegramUser(data: unknown): data is TelegramUser {
    if (!data || typeof data !== 'object') return false
    const obj = data as Record<string, unknown>
    return typeof obj.id === 'number' && typeof obj.hash === 'string' && typeof obj.auth_date === 'number'
}

// In the onTelegramAuth callback:
;(window as any).onTelegramAuth = async (tgUser: unknown) => {
    if (!isTelegramUser(tgUser)) {
        setError('Invalid Telegram data')
        return
    }
    // ... existing API call with validated tgUser ...
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/LoginPage.tsx
git commit -m "security: add client-side type guard for Telegram widget callback"
```

---

### Task 3.10: Fix Error Message Leakage in Frontend Toasts

**Files:**
- Modify: multiple hooks in `frontend/src/hooks/` and `frontend/src/twa/hooks/`

- [ ] **Step 1: Create a safe error extraction utility**

```typescript
// frontend/src/utils/errorMessage.ts
import { AxiosError } from 'axios'

export function safeErrorMessage(error: unknown, fallback: string): string {
    if (error instanceof AxiosError) {
        // Only show server-provided user-facing detail
        const detail = error.response?.data?.detail
        if (typeof detail === 'string' && detail.length < 200) {
            return detail
        }
    }
    return fallback
}
```

- [ ] **Step 2: Replace error.message in toast calls**

Find-and-replace pattern across hooks:
```typescript
// OLD:
toast.error(t('toast.failed'), { description: error.message })

// NEW:
toast.error(t('toast.failed'), { description: safeErrorMessage(error, t('toast.genericError')) })
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/utils/errorMessage.ts frontend/src/hooks/ frontend/src/twa/hooks/
git commit -m "security: sanitize error messages in UI toasts, hide internal details (MED-10)"
```

---

## Phase 4: Stabilization — Observability & Testing

### Task 4.1: Integrate Sentry Error Tracking

**Files:**
- Modify: `requirements.txt` (add `sentry-sdk[fastapi]`)
- Modify: `uk_management_bot/main.py` (init Sentry for bot)
- Modify: `uk_management_bot/api/main.py` (init Sentry for API)
- Modify: `uk_management_bot/config/settings.py` (add `SENTRY_DSN`)
- Modify: `.env.production.template`

- [ ] **Step 1: Add dependency**

```
sentry-sdk[fastapi]>=2.0.0
```

- [ ] **Step 2: Add SENTRY_DSN to settings**

```python
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
```

- [ ] **Step 3: Init in bot main.py**

```python
if settings.SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(dsn=settings.SENTRY_DSN, traces_sample_rate=0.1, environment="production" if not settings.DEBUG else "development")
```

- [ ] **Step 4: Init in API main.py (with FastAPI integration)**

```python
if settings.SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    sentry_sdk.init(dsn=settings.SENTRY_DSN, integrations=[FastApiIntegration()], traces_sample_rate=0.1)
```

- [ ] **Step 5: Update env template**

```
SENTRY_DSN=                         # https://xxx@sentry.io/yyy (optional)
```

- [ ] **Step 6: Commit**

```bash
git add requirements.txt uk_management_bot/main.py uk_management_bot/api/main.py \
  uk_management_bot/config/settings.py .env.production.template
git commit -m "ops: integrate Sentry error tracking for bot and API"
```

---

### Task 4.2: Write Rollback Procedure

**Files:**
- Create: `docs/ROLLBACK.md`

- [ ] **Step 1: Write rollback documentation**

```markdown
# Rollback Procedure

## Release Tagging Convention

Every production deploy must be tagged:
```bash
git tag -a v1.2.3 -m "Release 1.2.3"
docker compose -f docker-compose.production.yml build
# Tag images with the same version
docker tag uk-management-bot:latest uk-management-bot:v1.2.3
docker tag uk-management-api:latest uk-management-api:v1.2.3
```

## Quick Rollback (to previous release)

1. Identify last known-good release tag:
   ```bash
   git tag --sort=-creatordate | head -5
   ```

2. Checkout the release (NOT `HEAD~1` — that creates detached HEAD):
   ```bash
   git checkout v1.2.2  # specific known-good tag
   ```

3. Rebuild and restart:
   ```bash
   docker compose -f docker-compose.production.yml build
   docker compose -f docker-compose.production.yml up -d
   ```

4. Verify:
   ```bash
   curl -s https://your-domain.com/health | jq .
   docker logs uk-management-api --tail 20
   docker logs uk-management-bot --tail 20
   ```

5. Return to main branch after fix:
   ```bash
   git checkout main
   ```

## Database Rollback

**IMPORTANT:** Schema rollback and data rollback are separate concerns.

### Schema-only rollback (migration revert)
Only safe if the new migration was additive (new columns/tables):
```bash
docker exec uk-management-api python -m alembic current  # note revision
docker exec uk-management-api python -m alembic downgrade -1
```

### Data restore from backup
If migration was destructive (dropped/renamed columns) or data is corrupted:
```bash
# 1. Stop app and API (keep DB running)
docker compose -f docker-compose.production.yml stop app api

# 2. Restore from the pre-deploy backup
gunzip < /opt/uk-management/backups/uk_management_PRE_DEPLOY.sql.gz | \
  docker exec -i uk-postgres psql -U $POSTGRES_USER -d $POSTGRES_DB

# 3. Run migrations for the rollback target version
docker exec uk-management-api python -m alembic upgrade head

# 4. Restart services
docker compose -f docker-compose.production.yml up -d app api
```

## Pre-Deploy Backup (mandatory)

Before every deploy, create a tagged backup:
```bash
docker exec uk-postgres pg_dump -U $POSTGRES_USER $POSTGRES_DB | \
  gzip > /opt/uk-management/backups/uk_management_PRE_DEPLOY_$(date +%Y%m%d_%H%M%S).sql.gz
```
```

- [ ] **Step 2: Commit**

```bash
git add docs/ROLLBACK.md
git commit -m "docs: add rollback procedure for production deployments"
```

---

### Task 4.3: Increase Test Coverage — Services Layer (30% → 80%)

> Самая трудоёмкая задача. Разбить на подзадачи по сервису.

**Files:**
- Create: `tests/services/test_request_service.py`
- Create: `tests/services/test_invite_service.py`
- Create: `tests/services/test_user_service.py`
- Create: `tests/services/test_shift_assignment_service.py`
- Create: `tests/services/test_auth_service.py`
- Create: `tests/services/test_notification_service.py`
- Create: `tests/services/test_metrics_manager.py`

- [ ] **Step 1: List all service modules and their public methods**

```bash
docker exec uk-management-bot python -c "
import inspect, uk_management_bot.services as s
for name in dir(s):
    obj = getattr(s, name)
    if inspect.isclass(obj):
        methods = [m for m in dir(obj) if not m.startswith('_')]
        print(f'{name}: {methods}')
"
```

- [ ] **Step 2: Write tests for each service, focusing on business logic paths**

Follow TDD: write test -> verify fail -> implement missing behavior if any -> verify pass.

Target: minimum 3 test cases per public method (happy path, error case, edge case).

- [ ] **Step 3: Run coverage check**

```bash
docker exec uk-management-bot pytest tests/services/ --cov=uk_management_bot/services --cov-report=term-missing
```

Target: >=80% coverage on `uk_management_bot/services/`.

- [ ] **Step 4: Commit in batches (one per service file)**

---

### Task 4.4: Increase Test Coverage — API Layer (23% → 80%)

**Files:**
- Create: `tests/api/test_auth_endpoints.py`
- Create: `tests/api/test_requests_endpoints.py`
- Create: `tests/api/test_shifts_endpoints.py`
- Create: `tests/api/test_profile_endpoints.py`
- Create: `tests/api/test_notifications_endpoints.py`
- Create: `tests/api/conftest.py` (shared TestClient fixture)

- [ ] **Step 1: Create shared test fixture with TestClient**

```python
# tests/api/conftest.py
import pytest
from httpx import AsyncClient, ASGITransport
from uk_management_bot.api.main import app

@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

@pytest.fixture
async def auth_client(client):
    """Client authenticated via cookies (after Task 2.2 cookie migration).
    Falls back to header-based auth if cookies not yet implemented."""
    # NOTE: PasswordLogin schema uses `email`, not `username`
    resp = await client.post("/api/v2/auth/login", json={"email": "admin@example.com", "password": "testpass"})
    assert resp.status_code == 200
    # After Task 2.2: cookies are set automatically on the client
    # Before Task 2.2: extract token from response body
    if "access_token" in resp.json():
        token = resp.json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"
    return client
```

- [ ] **Step 2: Write endpoint tests following TDD**

Target: every endpoint has at least: auth test (401 without token), happy path test, validation test (400 on bad input).

- [ ] **Step 3: Run coverage**

```bash
docker exec uk-management-bot pytest tests/api/ --cov=uk_management_bot/api --cov-report=term-missing
```

Target: >=80%.

- [ ] **Step 4: Commit in batches**

---

### Task 4.5: Create Deployment Checklist

**Files:**
- Create: `docs/DEPLOYMENT_CHECKLIST.md`

- [ ] **Step 1: Write checklist**

```markdown
# Production Deployment Checklist

## Pre-Deploy
- [ ] All tests pass: `docker exec uk-management-bot pytest`
- [ ] Frontend build clean: `cd frontend && npm run build`
- [ ] No secrets in code: `git grep -i "password\|token\|secret" -- "*.py" "*.ts" "*.yml"`
- [ ] .env on server has all vars from .env.production.template
- [ ] DEBUG=false in .env
- [ ] JWT_SECRET != INVITE_SECRET
- [ ] ADMIN_PASSWORD >= 12 chars
- [ ] REDIS_PASSWORD set

## Deploy
1. `git pull origin main`
2. `docker compose -f docker-compose.production.yml build`
3. `docker compose -f docker-compose.production.yml up -d`
4. Verify migrations: `docker logs uk-management-bot | grep "migrations"`
5. Verify health: `curl -s https://your-domain.com/health | jq .`
6. Check logs: `docker logs uk-management-bot --tail 50`
7. Check API: `docker logs uk-management-api --tail 50`

## Post-Deploy
- [ ] Verify bot responds in Telegram
- [ ] Verify frontend loads
- [ ] Verify WebSocket connection
- [ ] Check backup cron: `crontab -l | grep backup`
```

- [ ] **Step 2: Commit**

```bash
git add docs/DEPLOYMENT_CHECKLIST.md
git commit -m "docs: add production deployment checklist"
```

---

### Task 4.6: Setup Off-Site Backups (Optional)

**Files:**
- Modify: `scripts/backup-db.sh` (add S3/rsync upload step)

- [ ] **Step 1: Add upload step to backup script**

```bash
# At end of backup-db.sh:
if command -v aws &> /dev/null && [ -n "$S3_BACKUP_BUCKET" ]; then
    aws s3 cp "$BACKUP_FILE" "s3://$S3_BACKUP_BUCKET/uk-management/"
    echo "Backup uploaded to S3"
fi
```

- [ ] **Step 2: Add S3 vars to env template**

```
S3_BACKUP_BUCKET=                   # Optional: S3 bucket for off-site backups
```

- [ ] **Step 3: Commit**

```bash
git add scripts/backup-db.sh .env.production.template
git commit -m "ops: add optional S3 off-site backup support"
```

---

## Summary — Execution Order

| Phase | Tasks | Est. Effort | Blocks Deploy? |
|-------|-------|-------------|----------------|
| 0 | 0.1, 0.2 | 1 hour | **YES — do today** |
| 1 | 1.1–1.6 | 1 day | **YES** |
| 2 | 2.1–2.7 | 2–3 days | **YES (before live traffic)** |
| 3 | 3.1–3.10 | 2–3 days | No (but recommended) |
| 4 | 4.1–4.6 | 3–5 days | No (stabilization) |

Total: ~8–13 days of focused work.
