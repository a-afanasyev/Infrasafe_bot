# Applicant Registration — WebApp + Bot Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an open applicant self-registration form as a Telegram Mini App (React `/register`) backed by a new async API, keep the existing bot onboarding as the parallel scheme, and retire the dead `uk-web-registration` service.

**Architecture:** New async FastAPI router `uk_management_bot/api/registration/` on `uk-management-api`: `POST /start` (verifies signed `initData` → mints a 30-min registration-ticket JWT + returns Telegram prefill + apartment catalog) and `POST /applicant` (gated by the ticket → upserts a pending applicant + a pending `UserApartment` via the existing async `core.request_apartment` → notifies managers). The React `/register` page is launched by a WebApp button on the bot's new-user welcome. Approval is unchanged (existing manager flows). Identity is WebApp-only (`telegram_id` from `initData`).

**Tech Stack:** FastAPI + SQLAlchemy AsyncSession + python-jose JWT + slowapi rate-limit; aiogram 3 (bot button); React + Vite + axios + i18next (frontend); pytest + vitest.

**Spec:** `docs/superpowers/specs/2026-05-30-applicant-registration-dual-scheme-design.md`

**Reference skills:** @superpowers:test-driven-development for every backend/frontend task.

**Test commands:**
- Backend: `docker exec uk-management-bot pytest <path> -v`
- Frontend: see Task 8 — the frontend currently has **no** test runner; the
  RegisterPage vitest test is gated behind an optional test-tooling setup step.

> **Commit policy (project rule — overrides the skill's "frequent commits"):**
> never run `git commit` without the user's explicit request. Every step labelled
> "Stage / checkpoint" means `git add` the listed files as a checkpoint; the
> suggested commit message is kept for when the user authorizes the commit. Do NOT
> run `git commit` unprompted. (The `# git commit -m "..."` lines below are the
> messages to use *when* the user says to commit.)

---

## File Structure

**Test harness (create — Task 0):**
- `uk_management_bot/tests/api/__init__.py`
- `uk_management_bot/tests/api/conftest.py` — `api_client` (httpx ASGITransport), `async_db`, `seed_apartment`, `seed_user`, `fake_initdata`
  (the `uk_management_bot/tests/api/` directory does NOT exist yet — Task 0 creates it)

**Backend (create):**
- `uk_management_bot/api/registration/__init__.py`
- `uk_management_bot/api/registration/tickets.py` — `create_registration_ticket` / `verify_registration_ticket`
- `uk_management_bot/api/registration/schemas.py` — request/response models
- `uk_management_bot/api/registration/catalog.py` — async apartment-catalog query
- `uk_management_bot/api/registration/notify.py` — direct-Telegram manager notification
- `uk_management_bot/api/registration/router.py` — `POST /start`, `POST /applicant`
- Tests: `uk_management_bot/tests/api/test_registration_tickets.py`, `test_registration_start.py`, `test_registration_applicant.py`

**Backend (modify):**
- `uk_management_bot/api/main.py` — include the new router

**Frontend (create):**
- `frontend/src/pages/RegisterPage.tsx`
- `frontend/src/hooks/useRegistration.ts`
- Tests: `frontend/src/pages/__tests__/RegisterPage.test.tsx` (OPTIONAL — needs test tooling, see Task 8 Step 6)

**Frontend (modify):**
- `frontend/src/App.tsx` — add public `/register` route
- `frontend/src/i18n/locales/{ru,uz}.json` — `register.*` keys

**Bot (modify):**
- `uk_management_bot/handlers/base.py` — WebApp button on new-user welcome

**Infra / cleanup:**
- `docker-compose.yml` — remove `web` service
- Delete `uk_management_bot/web/`
- Tests cleanup under `uk_management_bot/tests/` (preserve the nonce service test)

---

## Task 0: API test harness & fixtures (prerequisite)

**Why:** Existing API tests in `uk_management_bot/tests/` call router/service functions
directly — there is **no** httpx HTTP harness and none of the fixtures the
registration tests need (`api_client`, `async_db`, `seed_apartment`, `seed_user`,
`fake_initdata`). Tasks 4 & 6 assert HTTP status codes, so build this first.

**Files:**
- Create: `uk_management_bot/tests/api/__init__.py` (empty)
- Create: `uk_management_bot/tests/api/conftest.py`

- [ ] **Step 1: Create the harness conftest**

```python
# uk_management_bot/tests/api/conftest.py
import hmac, hashlib, json, time
from urllib.parse import urlencode
import pytest, pytest_asyncio
from httpx import AsyncClient, ASGITransport

from uk_management_bot.api.main import app
from uk_management_bot.api.dependencies import get_db
from uk_management_bot.config.settings import settings


@pytest_asyncio.fixture
async def async_db(address_async_db):
    """Reuse the existing rolled-back AsyncSession fixture (tests/conftest.py:46) —
    its savepoint/rollback isolation already tolerates core.request_apartment's
    internal commit. Aliased here so registration tests read clearly.
    (If `address_async_db`'s shape differs, adapt — but do NOT spin up a new engine;
    schema lives in the migrated container DB and tests run via `docker exec`.)"""
    return address_async_db


@pytest_asyncio.fixture
async def api_client(async_db):
    async def _override_get_db():
        yield async_db
    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def fake_initdata():
    """Factory → a VALID signed Telegram WebApp initData string for a telegram_id.
    Mirrors verify_twa_init_data: secret = HMAC-SHA256(key='WebAppData', msg=BOT_TOKEN);
    hash = HMAC-SHA256(key=secret, msg=data_check_string)."""
    def _make(telegram_id: int, first_name: str = "Test"):
        user = json.dumps({"id": telegram_id, "first_name": first_name}, separators=(",", ":"))
        fields = {"auth_date": str(int(time.time())), "user": user}
        dcs = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
        secret = hmac.new(b"WebAppData", settings.BOT_TOKEN.encode(), hashlib.sha256).digest()
        fields["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
        return urlencode(fields)
    return _make


@pytest.fixture
def seed_user(async_db):
    from uk_management_bot.database.models.user import User
    created = []
    async def _make(telegram_id: int, status: str = "pending"):
        u = User(telegram_id=telegram_id, status=status)
        async_db.add(u); await async_db.flush()
        created.append(u); return u
    return _make


@pytest.fixture
def seed_apartment(async_db):
    from uk_management_bot.database.models.yard import Yard
    from uk_management_bot.database.models.building import Building
    from uk_management_bot.database.models.apartment import Apartment
    async def _make(number: str = "12", yard_name: str = "Двор-1", address: str = "ул. Ленина 1",
                    building_active: bool = True, yard_active: bool = True):
        y = Yard(name=yard_name, is_active=yard_active); async_db.add(y); await async_db.flush()
        b = Building(address=address, yard_id=y.id, is_active=building_active)
        async_db.add(b); await async_db.flush()
        a = Apartment(apartment_number=number, building_id=b.id, is_active=True)
        async_db.add(a); await async_db.flush()
        return a
    return _make


@pytest.fixture(autouse=True)
def _disable_rate_limit():
    """slowapi keys all ASGI test requests into one bucket (no unique X-Real-IP),
    so >3 calls to the 3/min /applicant endpoint would 429. Disable the limiter for
    registration API tests. A dedicated rate-limit test (if ever added) can flip it
    back on for its scope."""
    from uk_management_bot.api.rate_limit import limiter
    prev = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = prev
```

> Verify `limiter.enabled` is the correct slowapi toggle for the installed version;
> if not, set a unique `X-Real-IP` header per test in `api_client` instead.

> IMPLEMENTER NOTES: (1) `seed_user`/`seed_apartment` are async factories — call with
> `await` in tests, or make them `pytest_asyncio` fixtures. (2) Verify the
> Yard/Building/Apartment constructors' required fields against the models and add
> any NOT NULL fields. (3) `verify_twa_init_data` parses initData with `parse_qs`/
> `unquote`; confirm the `user` value survives `urlencode` round-trip (it will, since
> urlencode percent-encodes it). (4) If `address_async_db` already exposes a usable
> session, you may alias `async_db = address_async_db` instead of re-deriving.

- [ ] **Step 2: Sanity-check the transport** — add a temporary test:

```python
# uk_management_bot/tests/api/test_harness_smoke.py
import pytest
from sqlalchemy import text

@pytest.mark.asyncio
async def test_harness_db_and_http(api_client, async_db):
    # DB session must be live (not a no-op alias) ...
    assert (await async_db.execute(text("SELECT 1"))).scalar() == 1
    # ... and the ASGI transport must reach the app.
    assert (await api_client.get("/health")).status_code == 200
```

Run: `docker exec uk-management-bot pytest uk_management_bot/tests/api/test_harness_smoke.py -v`
Expected: PASS (proves BOTH the DB session and ASGITransport work — hitting only
`/health`, which doesn't touch the DB, would mask a broken `async_db`). Delete this
smoke test after.

- [ ] **Step 3: Stage / checkpoint (commit on user request)**

```bash
git add uk_management_bot/tests/api/__init__.py uk_management_bot/tests/api/conftest.py
# git commit -m "test(api): add httpx ASGI harness + initData/seed fixtures for registration tests"
```

---

## Task 1: Registration ticket JWT helpers

**Files:**
- Create: `uk_management_bot/api/registration/__init__.py` (empty)
- Create: `uk_management_bot/api/registration/tickets.py`
- Test: `uk_management_bot/tests/api/test_registration_tickets.py`

Mirrors the MFA-token pattern (`api/auth/service.py:150` `create_mfa_token`) but with `purpose="register"` and `sub=telegram_id` — a SEPARATE function (do not reuse the MFA token).

- [ ] **Step 1: Write the failing test**

```python
# uk_management_bot/tests/api/test_registration_tickets.py
import pytest
from uk_management_bot.api.registration.tickets import (
    create_registration_ticket, verify_registration_ticket,
)

@pytest.mark.unit
def test_roundtrip_returns_telegram_id():
    tok = create_registration_ticket(123456789)
    assert verify_registration_ticket(tok) == 123456789

@pytest.mark.unit
def test_rejects_garbage():
    assert verify_registration_ticket("not-a-jwt") is None

@pytest.mark.unit
def test_rejects_mfa_token():
    # An MFA token (purpose=mfa) must NOT validate as a registration ticket.
    from uk_management_bot.api.auth.service import create_mfa_token
    assert verify_registration_ticket(create_mfa_token(5)) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec uk-management-bot pytest uk_management_bot/tests/api/test_registration_tickets.py -v`
Expected: FAIL — `ModuleNotFoundError: api.registration.tickets`.

- [ ] **Step 3: Write minimal implementation**

```python
# uk_management_bot/api/registration/tickets.py
"""Short-lived JWT proving a verified Telegram identity during registration.

Separate from the MFA token: purpose="register", sub=telegram_id. Reuses the
shared SECRET_KEY/ALGORITHM/issuer from api.auth.service.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt, JWTError

from uk_management_bot.api.auth.service import SECRET_KEY, ALGORITHM

ISSUER = "uk-management"
PURPOSE = "register"
TICKET_TTL_MINUTES = 30


def create_registration_ticket(telegram_id: int) -> str:
    payload = {
        "sub": str(telegram_id),
        "purpose": PURPOSE,
        "iss": ISSUER,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=TICKET_TTL_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_registration_ticket(token: str) -> Optional[int]:
    """Return the telegram_id if the ticket is valid and purpose=register, else None."""
    try:
        payload = jwt.decode(
            token, SECRET_KEY, algorithms=[ALGORITHM],
            issuer=ISSUER, options={"verify_aud": False},
        )
    except JWTError:
        return None
    if payload.get("purpose") != PURPOSE:
        return None
    sub = payload.get("sub")
    try:
        return int(sub)
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker exec uk-management-bot pytest uk_management_bot/tests/api/test_registration_tickets.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Stage / checkpoint (commit on user request)**

```bash
git add uk_management_bot/api/registration/__init__.py uk_management_bot/api/registration/tickets.py uk_management_bot/tests/api/test_registration_tickets.py
# git commit -m "feat(registration): add registration-ticket JWT helpers"
```

---

## Task 2: Schemas

**Files:**
- Create: `uk_management_bot/api/registration/schemas.py`
- Test: (covered by endpoint tests; no standalone test)

- [ ] **Step 1: Write the schemas**

```python
# uk_management_bot/api/registration/schemas.py
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class StartIn(BaseModel):
    init_data: str = Field(..., min_length=1)


class ApartmentOut(BaseModel):
    id: int
    yard_name: Optional[str] = None
    building_address: Optional[str] = None
    apartment_number: str


class Prefill(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None


class StartOut(BaseModel):
    registration_ticket: str
    prefill: Prefill
    apartments: list[ApartmentOut]


class RegisterApplicantIn(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    phone: str = Field(..., min_length=1, max_length=20)
    apartment_id: int


class RegistrationResult(BaseModel):
    status: str  # always "pending"
```

- [ ] **Step 2: Stage / checkpoint (commit on user request)**

```bash
git add uk_management_bot/api/registration/schemas.py
# git commit -m "feat(registration): add request/response schemas"
```

---

## Task 3: Apartment catalog query

**Files:**
- Create: `uk_management_bot/api/registration/catalog.py`
- Test: `uk_management_bot/tests/api/test_registration_start.py` (catalog portion)

Reuse the join shape already used in `api/addresses/router.py:825` (Apartment ⨝ Building ⨝ Yard).

- [ ] **Step 1: Write the failing test** (seeded yard/building/apartment → catalog returns the row)

```python
# uk_management_bot/tests/api/test_registration_start.py
import pytest
from uk_management_bot.api.registration.catalog import list_apartments

@pytest.mark.asyncio
async def test_list_apartments_returns_active_rows(async_db, seed_apartment):
    await seed_apartment(number="12", yard_name="Двор-1", address="ул. Ленина 1")
    rows = await list_apartments(async_db)
    assert any(a.apartment_number == "12" and a.yard_name == "Двор-1" for a in rows)
```

> NOTE for implementer: reuse the project's existing async-db + seed fixtures
> (see `uk_management_bot/tests/api/` conftest). If a seed fixture for apartments
> does not exist, add a minimal one creating Yard→Building→Apartment.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec uk-management-bot pytest uk_management_bot/tests/api/test_registration_start.py::test_list_apartments_returns_active_rows -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# uk_management_bot/api/registration/catalog.py
from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.api.registration.schemas import ApartmentOut


async def list_apartments(db: AsyncSession) -> list[ApartmentOut]:
    """Active apartments with their building/yard labels, for the registration selector."""
    result = await db.execute(
        select(
            Apartment.id, Apartment.apartment_number,
            Building.address, Yard.name,
        )
        .join(Building, Apartment.building_id == Building.id)
        .join(Yard, Building.yard_id == Yard.id)
        .where(
            Apartment.is_active.is_(True),
            Building.is_active.is_(True),
            Yard.is_active.is_(True),
        )
        .order_by(Yard.name, Building.address, Apartment.apartment_number)
    )
    return [
        ApartmentOut(
            id=row[0], apartment_number=str(row[1]),
            building_address=row[2], yard_name=row[3],
        )
        for row in result.all()
    ]


async def is_apartment_selectable(db: AsyncSession, apartment_id: int) -> bool:
    """True iff the apartment exists AND its apartment/building/yard are all active
    (i.e. it would appear in list_apartments). Honors catalog membership, since
    core.request_apartment only checks Apartment.is_active, not the parents."""
    result = await db.execute(
        select(Apartment.id)
        .join(Building, Apartment.building_id == Building.id)
        .join(Yard, Building.yard_id == Yard.id)
        .where(
            Apartment.id == apartment_id,
            Apartment.is_active.is_(True),
            Building.is_active.is_(True),
            Yard.is_active.is_(True),
        )
    )
    return result.first() is not None
```

> `is_active` exists on Apartment, Building AND Yard — filter all three for parity
> with the bot (a hidden building/yard must not surface its apartments).

- [ ] **Step 4: Run test to verify it passes**

Run: `docker exec uk-management-bot pytest uk_management_bot/tests/api/test_registration_start.py::test_list_apartments_returns_active_rows -v`
Expected: PASS.

- [ ] **Step 5: Stage / checkpoint (commit on user request)**

```bash
git add uk_management_bot/api/registration/catalog.py uk_management_bot/tests/api/test_registration_start.py
# git commit -m "feat(registration): add apartment catalog query"
```

---

## Task 4: `POST /start` endpoint

**Files:**
- Create: `uk_management_bot/api/registration/router.py`
- Modify: `uk_management_bot/api/main.py` (include router — done in Task 7, but a thin include here lets the test run)
- Test: `uk_management_bot/tests/api/test_registration_start.py`

Behaviour: verify `init_data` (`verify_twa_init_data`, `api/auth/service.py`) → `telegram_id`; blocked→403, approved→409; else mint ticket + return prefill (name from initData; phone only from existing pending `User.phone`) + catalog. Rate-limit `10/minute`.

- [ ] **Step 1: Write failing tests**

```python
# append to uk_management_bot/tests/api/test_registration_start.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_start_invalid_initdata_401(api_client: AsyncClient):
    r = await api_client.post("/api/v2/registration/start", json={"init_data": "bad"})
    assert r.status_code == 401

@pytest.mark.asyncio
async def test_start_new_user_returns_ticket_and_catalog(api_client, fake_initdata, seed_apartment):
    r = await api_client.post("/api/v2/registration/start", json={"init_data": fake_initdata(99001)})
    assert r.status_code == 200
    body = r.json()
    assert body["registration_ticket"]
    assert isinstance(body["apartments"], list)

@pytest.mark.asyncio
async def test_start_approved_user_409(api_client, fake_initdata, seed_user):
    await seed_user(telegram_id=99002, status="approved")
    r = await api_client.post("/api/v2/registration/start", json={"init_data": fake_initdata(99002)})
    assert r.status_code == 409
```

> `fake_initdata(telegram_id)` helper: build a valid signed initData string with
> `verify_twa_init_data`'s HMAC scheme (secret = HMAC-SHA256("WebAppData", BOT_TOKEN)),
> `auth_date=now`, `user={"id": telegram_id, "first_name": "Test"}`. Add it to the
> test conftest so `/applicant` tests reuse it.

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec uk-management-bot pytest uk_management_bot/tests/api/test_registration_start.py -v`
Expected: FAIL — endpoint/route missing.

- [ ] **Step 3: Implement `POST /start`**

```python
# uk_management_bot/api/registration/router.py
from __future__ import annotations
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.api.auth.service import verify_twa_init_data
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.user import User
from uk_management_bot.api.registration.tickets import create_registration_ticket
from uk_management_bot.api.registration.catalog import list_apartments, is_apartment_selectable
from uk_management_bot.api.registration.schemas import StartIn, StartOut, Prefill

logger = logging.getLogger(__name__)
router = APIRouter()


def _resolve_telegram_id(init_data: str) -> tuple[int, dict]:
    data = verify_twa_init_data(init_data, settings.BOT_TOKEN)
    if not data or not data.get("id"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid initData")
    return int(data["id"]), data


@router.post("/start", response_model=StartOut)
@limiter.limit("10/minute")
async def start(request: Request, body: StartIn, db: AsyncSession = Depends(get_db)):
    telegram_id, tg = _resolve_telegram_id(body.init_data)

    existing = (await db.execute(
        select(User).where(User.telegram_id == telegram_id)
    )).scalar_one_or_none()
    if existing and existing.status == "blocked":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован")
    if existing and existing.status == "approved":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Уже зарегистрирован")

    prefill = Prefill(
        first_name=tg.get("first_name"),
        last_name=tg.get("last_name"),
        phone=existing.phone if existing else None,  # initData has no phone
    )
    return StartOut(
        registration_ticket=create_registration_ticket(telegram_id),
        prefill=prefill,
        apartments=await list_apartments(db),
    )
```

Add a thin include in `api/main.py` (full wiring in Task 7):

```python
from uk_management_bot.api.registration.router import router as registration_router
app.include_router(registration_router, prefix="/api/v2/registration", tags=["registration"])
```

> `_resolve_telegram_id` returns a tuple `(telegram_id, data)` and the caller
> unpacks both — annotated `-> tuple[int, dict]`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec uk-management-bot pytest uk_management_bot/tests/api/test_registration_start.py -v`
Expected: PASS.

- [ ] **Step 5: Stage / checkpoint (commit on user request)**

```bash
git add uk_management_bot/api/registration/router.py uk_management_bot/api/main.py uk_management_bot/tests/api/test_registration_start.py
# git commit -m "feat(registration): POST /start — verify initData, mint ticket, return prefill+catalog"
```

---

## Task 5: Manager notification helper

**Files:**
- Create: `uk_management_bot/api/registration/notify.py`
- Test: `uk_management_bot/tests/api/test_registration_applicant.py` (notify portion, mocked HTTP)

Direct Telegram `sendMessage` (cf. `api/auth/service.py:send_otp_via_bot`), to `settings.ADMIN_USER_IDS`. Non-fatal on error.

- [ ] **Step 1: Write the failing test**

```python
# uk_management_bot/tests/api/test_registration_applicant.py
import pytest
from unittest.mock import AsyncMock, patch
from uk_management_bot.api.registration.notify import notify_managers_new_registration

@pytest.mark.asyncio
async def test_notify_swallows_errors(monkeypatch):
    monkeypatch.setattr("uk_management_bot.config.settings.settings.ADMIN_USER_IDS", [111])
    with patch("uk_management_bot.api.registration.notify._send", new=AsyncMock(side_effect=Exception("boom"))):
        # must not raise
        await notify_managers_new_registration(telegram_id=5, full_name="Иван", apartment_label="Двор-1, кв 12")
```

- [ ] **Step 2: Run → FAIL** (`docker exec uk-management-bot pytest uk_management_bot/tests/api/test_registration_applicant.py::test_notify_swallows_errors -v`)

- [ ] **Step 3: Implement**

```python
# uk_management_bot/api/registration/notify.py
from __future__ import annotations
import logging
import httpx

from uk_management_bot.config.settings import settings

logger = logging.getLogger(__name__)


async def _send(chat_id: int, text: str) -> None:
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(url, json={"chat_id": chat_id, "text": text})


async def notify_managers_new_registration(*, telegram_id: int, full_name: str, apartment_label: str) -> None:
    """Best-effort: tell admins a new applicant registered. Never raises."""
    if not settings.ADMIN_USER_IDS:
        logger.warning("ADMIN_USER_IDS not set — registration notification skipped")
        return
    text = f"🆕 Новая регистрация заявителя\n{full_name}\nКвартира: {apartment_label}\nTG: {telegram_id}"
    for admin_id in settings.ADMIN_USER_IDS:
        try:
            await _send(admin_id, text)
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id} about registration: {e}")
```

- [ ] **Step 4: Run → PASS**

- [ ] **Step 5: Stage / checkpoint (commit on user request)**

```bash
git add uk_management_bot/api/registration/notify.py uk_management_bot/tests/api/test_registration_applicant.py
# git commit -m "feat(registration): manager notification via direct Telegram sendMessage"
```

---

## Task 6: `POST /applicant` endpoint

**Files:**
- Modify: `uk_management_bot/api/registration/router.py`
- Test: `uk_management_bot/tests/api/test_registration_applicant.py`

Gated by `Authorization: Bearer <registration_ticket>`. Validates phone/name/apartment; upserts pending applicant (async, NOT AuthService which is sync); creates apartment link via `core.request_apartment`; catches `IntegrityError` (race) and `AddressConflict` → 409; notifies after commit; returns `{status:"pending"}`. Rate-limit `3/minute`.

- [ ] **Step 1: Write failing tests**

```python
# append to test_registration_applicant.py
import pytest

def _bearer(tid):
    from uk_management_bot.api.registration.tickets import create_registration_ticket
    return {"Authorization": f"Bearer {create_registration_ticket(tid)}"}

@pytest.mark.asyncio
async def test_applicant_no_ticket_401(api_client):
    r = await api_client.post("/api/v2/registration/applicant",
                              json={"full_name": "Иван Иванов", "phone": "+998901112233", "apartment_id": 1})
    assert r.status_code == 401

@pytest.fixture
def mock_notify(monkeypatch):
    """Never hit the real Telegram API in tests."""
    from unittest.mock import AsyncMock
    m = AsyncMock()
    monkeypatch.setattr(
        "uk_management_bot.api.registration.router.notify_managers_new_registration", m)
    return m

@pytest.mark.asyncio
async def test_applicant_creates_pending(api_client, async_db, seed_apartment, mock_notify):
    from sqlalchemy import select
    from uk_management_bot.database.models.user import User
    from uk_management_bot.database.models.user_apartment import UserApartment
    from uk_management_bot.utils.auth_helpers import parse_roles_safe

    apt_id = (await seed_apartment()).id
    r = await api_client.post("/api/v2/registration/applicant",
        headers=_bearer(99100),
        json={"full_name": "Иван Иванов", "phone": "+998901112233", "apartment_id": apt_id})
    assert r.status_code == 200 and r.json()["status"] == "pending"

    user = (await async_db.execute(select(User).where(User.telegram_id == 99100))).scalar_one()
    assert user.status == "pending"
    assert user.active_role == "applicant"
    assert "applicant" in parse_roles_safe(user.roles)
    assert user.phone == "+998901112233"
    ua = (await async_db.execute(
        select(UserApartment).where(UserApartment.user_id == user.id))).scalar_one()
    assert ua.status == "pending" and ua.apartment_id == apt_id


@pytest.mark.asyncio
async def test_applicant_double_submit_idempotent(api_client, async_db, seed_apartment, mock_notify):
    """A second submit (same user + apartment) is a no-op, not a 500 — covers the
    existing-user path and the apartment UniqueConstraint."""
    from sqlalchemy import select, func
    from uk_management_bot.database.models.user import User
    from uk_management_bot.database.models.user_apartment import UserApartment
    apt_id = (await seed_apartment()).id
    payload = {"full_name": "Иван Иванов", "phone": "+998901112233", "apartment_id": apt_id}
    r1 = await api_client.post("/api/v2/registration/applicant", headers=_bearer(99200), json=payload)
    r2 = await api_client.post("/api/v2/registration/applicant", headers=_bearer(99200), json=payload)
    assert r1.status_code == 200
    assert r2.status_code == 200          # existing pending link → idempotent, no duplicate, no 500
    user = (await async_db.execute(select(User).where(User.telegram_id == 99200))).scalar_one()
    count = (await async_db.execute(
        select(func.count()).select_from(UserApartment).where(UserApartment.user_id == user.id)
    )).scalar()
    assert count == 1


@pytest.mark.asyncio
async def test_applicant_inactive_building_400(api_client, async_db, seed_apartment, mock_notify):
    """Apartment active but its building inactive → not in catalog → 400, no user created."""
    from sqlalchemy import select
    from uk_management_bot.database.models.user import User
    apt_id = (await seed_apartment(building_active=False)).id
    r = await api_client.post("/api/v2/registration/applicant",
        headers=_bearer(99400),
        json={"full_name": "Иван", "phone": "+998901112233", "apartment_id": apt_id})
    assert r.status_code == 400
    assert (await async_db.execute(select(User).where(User.telegram_id == 99400))).scalar_one_or_none() is None

@pytest.mark.asyncio
async def test_applicant_unknown_apartment_rolls_back_user(api_client, async_db, mock_notify):
    """Unknown/inactive apartment → 400, and NO half-registered pending user remains."""
    from sqlalchemy import select
    from uk_management_bot.database.models.user import User
    r = await api_client.post("/api/v2/registration/applicant",
        headers=_bearer(99300),
        json={"full_name": "Иван", "phone": "+998901112233", "apartment_id": 999999})
    assert r.status_code == 400
    leftover = (await async_db.execute(select(User).where(User.telegram_id == 99300))).scalar_one_or_none()
    assert leftover is None

@pytest.mark.asyncio
async def test_applicant_bad_phone_400(api_client, seed_apartment, mock_notify):
    apt_id = (await seed_apartment()).id
    r = await api_client.post("/api/v2/registration/applicant",
        headers=_bearer(99101),
        json={"full_name": "Иван", "phone": "xxx", "apartment_id": apt_id})
    assert r.status_code in (400, 422)

```

- [ ] **Step 2: Run → FAIL**

- [ ] **Step 3: Implement**

```python
# add to uk_management_bot/api/registration/router.py
import json
from fastapi import Header
from sqlalchemy.exc import IntegrityError

from uk_management_bot.api.registration.tickets import verify_registration_ticket
from uk_management_bot.api.registration.schemas import RegisterApplicantIn, RegistrationResult
from uk_management_bot.api.registration.notify import notify_managers_new_registration
from uk_management_bot.services.addresses import core as address_core
from uk_management_bot.services.addresses.exceptions import (
    AddressConflict, AddressNotFound, AddressValidationError,
)
from uk_management_bot.utils.validators import Validator
from uk_management_bot.utils.auth_helpers import parse_roles_safe
from uk_management_bot.database.models.user_apartment import UserApartment


def _ticket_telegram_id(authorization: str | None) -> int:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing registration ticket")
    tid = verify_registration_ticket(authorization.split(" ", 1)[1])
    if tid is None:
        raise HTTPException(status_code=401, detail="Invalid or expired registration ticket")
    return tid


@router.post("/applicant", response_model=RegistrationResult)
@limiter.limit("3/minute")
async def register_applicant(
    request: Request,
    body: RegisterApplicantIn,
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    telegram_id = _ticket_telegram_id(authorization)

    ok, msg = Validator.validate_phone(body.phone)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    phone = body.phone.strip()
    if not phone.startswith("+"):          # parity with bot onboarding (onboarding.py)
        phone = "+" + phone
    full_name = body.full_name.strip()
    if not full_name:
        raise HTTPException(status_code=400, detail="ФИО обязательно")

    # Honor "apartment must be selectable from the catalog": core.request_apartment
    # only checks Apartment.is_active, so pre-check active building + yard too.
    if not await is_apartment_selectable(db, body.apartment_id):
        raise HTTPException(status_code=400, detail="Квартира недоступна для выбора")

    def _apply_applicant_fields(u: User) -> None:
        u.first_name = full_name.split()[0]
        u.last_name = " ".join(full_name.split()[1:])
        u.phone = phone
        u.active_role = "applicant"
        r = set(parse_roles_safe(u.roles)); r.add("applicant")  # safe: JSON / CSV / None
        u.roles = json.dumps(sorted(r))
        # NB: never write the deprecated user.role column (CLAUDE.md)

    # --- upsert pending applicant (async; AuthService is sync, do not use it) ---
    user = (await db.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
    if user and user.status == "blocked":
        raise HTTPException(status_code=403, detail="Пользователь заблокирован")
    if user and user.status == "approved":
        raise HTTPException(status_code=409, detail="Уже зарегистрирован")
    if user is None:
        user = User(telegram_id=telegram_id, status="pending")
        db.add(user)
    _apply_applicant_fields(user)
    try:
        await db.flush()   # NOT commit — one tx; core.request_apartment commits both
    except IntegrityError:
        # concurrent submit inserted this telegram_id first (User.telegram_id is UNIQUE)
        # → adopt the existing row and re-apply fields
        await db.rollback()
        user = (await db.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one()
        if user.status == "blocked":
            raise HTTPException(status_code=403, detail="Пользователь заблокирован")
        if user.status == "approved":
            raise HTTPException(status_code=409, detail="Уже зарегистрирован")
        _apply_applicant_fields(user)
        await db.flush()

    # --- apartment link ---
    # Idempotent resubmit: if a link to THIS apartment already exists, do NOT discard
    # the profile-field updates made above (spec §9.1 — idempotent pending update).
    existing_ua = (await db.execute(select(UserApartment).where(
        UserApartment.user_id == user.id,
        UserApartment.apartment_id == body.apartment_id,
    ))).scalar_one_or_none()
    if existing_ua is not None:
        if existing_ua.status == "pending":
            await db.commit()        # persist updated phone/name/roles; request already exists
            return RegistrationResult(status="pending")   # no re-notify (already in the queue)
        if existing_ua.status == "approved":
            await db.rollback()
            raise HTTPException(status_code=409, detail="Вы уже подтверждены как житель этой квартиры")
        await db.rollback()          # rejected
        raise HTTPException(status_code=409, detail="Предыдущая заявка отклонена. Обратитесь к администратору.")

    # No existing link → create via the existing async core (commits the whole tx).
    try:
        await address_core.request_apartment(db, user_id=user.id, apartment_id=body.apartment_id)
    except AddressConflict as e:                              # rare: link appeared in a race
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    except (AddressNotFound, AddressValidationError) as e:    # unknown / invalid apartment
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except IntegrityError:                                    # concurrent duplicate apartment race
        await db.rollback()
        return RegistrationResult(status="pending")           # prior submit already created it → no-op

    # --- notify managers AFTER the commit (best-effort, never raises) ---
    await notify_managers_new_registration(
        telegram_id=telegram_id, full_name=full_name, apartment_label=f"apt #{body.apartment_id}",
    )
    return RegistrationResult(status="pending")
```

> Verify import paths: `AddressConflict` and `request_apartment` live in
> `uk_management_bot/services/addresses/core.py`. If `Validator.validate_phone`
> returns a different tuple shape, adjust.

- [ ] **Step 4: Run → PASS**

Run: `docker exec uk-management-bot pytest uk_management_bot/tests/api/test_registration_applicant.py -v`

- [ ] **Step 5: Stage / checkpoint (commit on user request)**

```bash
git add uk_management_bot/api/registration/router.py uk_management_bot/tests/api/test_registration_applicant.py
# git commit -m "feat(registration): POST /applicant — pending applicant + apartment + notify"
```

---

## Task 7: Finalize router wiring + full-suite check

**Files:**
- Modify: `uk_management_bot/api/main.py` (confirm the include from Task 4 is present & ordered with the other routers)

- [ ] **Step 1:** Ensure `app.include_router(registration_router, prefix="/api/v2/registration", tags=["registration"])` sits alongside the other `include_router` calls (`main.py:149-162`).
- [ ] **Step 2:** Run the full backend suite — Run: `docker exec uk-management-bot pytest -q` — Expected: all pass (no regressions; prior baseline 2756 passed + new tests).
- [ ] **Step 3: Stage / checkpoint (commit on user request)** (if any wiring change)

```bash
git add uk_management_bot/api/main.py
# git commit -m "chore(registration): wire registration router"
```

---

## Task 8: React `/register` page + hook + i18n

**Files:**
- Create: `frontend/src/hooks/useRegistration.ts`
- Create: `frontend/src/pages/RegisterPage.tsx`
- Modify: `frontend/src/App.tsx` (public route)
- Modify: `frontend/src/i18n/locales/{ru,uz}.json`
- Test: `frontend/src/pages/__tests__/RegisterPage.test.tsx`

- [ ] **Step 1: Add the route** in `App.tsx` (public, next to `/resident-board`):

```tsx
<Route path="/register" element={<PageErrorBoundary><RegisterPage /></PageErrorBoundary>} />
```
(plus `import RegisterPage from './pages/RegisterPage'`)

- [ ] **Step 2: Hook** — `useRegistration.ts`: read initData via `useTelegramSDK()`, `start()` POSTs `/api/v2/registration/start`, `submit()` POSTs `/api/v2/registration/applicant` with `Authorization: Bearer <ticket>`. Use a plain axios instance with `baseURL = import.meta.env.BASE_URL.replace(/\/$/, '')` (mirror `twaClient.ts`).

```ts
// frontend/src/hooks/useRegistration.ts
import axios from 'axios'
import { useTelegramSDK } from '../twa/hooks/useTelegramSDK'

const BASE_URL = import.meta.env.VITE_API_URL ?? import.meta.env.BASE_URL.replace(/\/$/, '')
const http = axios.create({ baseURL: BASE_URL })

export function useRegistration() {
  const tg = useTelegramSDK()
  const initData: string | undefined = tg?.initData

  async function start() {
    const { data } = await http.post('/api/v2/registration/start', { init_data: initData })
    return data as { registration_ticket: string; prefill: any; apartments: any[] }
  }
  async function submit(ticket: string, payload: { full_name: string; phone: string; apartment_id: number }) {
    const { data } = await http.post('/api/v2/registration/applicant', payload, {
      headers: { Authorization: `Bearer ${ticket}` },
    })
    return data as { status: string }
  }
  return { initData, start, submit }
}
```

- [ ] **Step 3: Page** — `RegisterPage.tsx`: on mount, if no `initData` show "откройте через Telegram"; else call `start()`, prefill, render apartment `<select>` + name + phone; on submit call `submit()`; show pending screen; handle 409 (redirect) and 401 (re-run start). Use existing UI components (shadcn) and i18n `t('register.*')`.

- [ ] **Step 4: i18n** — add a `register` block to `ru.json` and `uz.json` (`title`, `name`, `phone`, `apartment`, `submit`, `pending_title`, `pending_body`, `open_in_telegram`, `already_registered`).

- [ ] **Step 5: Verify build/typecheck** (the frontend has NO test runner) —
  `cd frontend && npx tsc --noEmit && npm run build` — Expected: no type errors,
  build succeeds. This is the hard gate for Task 8; functional UX is verified
  manually in Task 11.

- [ ] **Step 6 (OPTIONAL): vitest unit test.** `frontend/package.json` currently has
  NO `vitest`, `@testing-library/react`, or `jsdom`/`happy-dom`, and no `test`
  script. Only do this if adding frontend test tooling is in scope:
  - `cd frontend && npm i -D vitest @testing-library/react @testing-library/jest-dom jsdom`
  - add `"test": "vitest"` to `package.json` scripts and a `test: { environment: 'jsdom' }`
    block to `vite.config.ts`
  - write `frontend/src/pages/__tests__/RegisterPage.test.tsx` mocking `useTelegramSDK`
    (no initData → "open in Telegram" message; initData present + mocked axios `start`
    → apartment selector renders)
  - `npx vitest run src/pages/__tests__/RegisterPage.test.tsx` → PASS
  If frontend test tooling is OUT of scope, SKIP — Task 11 covers the UX.

- [ ] **Step 7: Stage / checkpoint** (commit on user request — see Commit policy)

```bash
git add frontend/src/pages/RegisterPage.tsx frontend/src/hooks/useRegistration.ts frontend/src/App.tsx frontend/src/i18n/locales/ru.json frontend/src/i18n/locales/uz.json
# (+ test file & config only if Step 6 was done)
# git commit -m "feat(web): applicant registration page (Telegram Mini App) at /register"
```

---

## Task 9: Bot WebApp button on new-user welcome

**Files:**
- Modify: `uk_management_bot/handlers/base.py` (`handle_regular_start`, new-user branch ~line 175)
- Test: `uk_management_bot/tests/handlers/test_base_register_button.py`

Add a `WebAppInfo` button "Регистрация (форма)" → `{FRONTEND_URL}/uk/register` to the onboarding keyboard for new pending users (alongside the existing phone/apartment buttons). In-chat onboarding stays.

- [ ] **Step 1: Write failing test** — assert that for a new pending user the welcome keyboard contains a button whose `web_app.url` ends with `/register`.
- [ ] **Step 2: Run → FAIL**
- [ ] **Step 3: Implement** — build the URL from `settings.FRONTEND_URL` (e.g. `f"{settings.FRONTEND_URL}/uk/register"`); guard if `FRONTEND_URL` empty (omit button). Use `aiogram.types.WebAppInfo`.
- [ ] **Step 4: Run → PASS** (`docker exec uk-management-bot pytest uk_management_bot/tests/handlers/test_base_register_button.py -v`)
- [ ] **Step 5: Rebuild bot + smoke** — `docker compose build uk-management-bot && docker compose up -d uk-management-bot && docker logs uk-management-bot --tail 20`
- [ ] **Step 6: Stage / checkpoint (commit on user request)**

```bash
git add uk_management_bot/handlers/base.py uk_management_bot/tests/handlers/test_base_register_button.py
# git commit -m "feat(bot): add WebApp registration button to new-user welcome"
```

---

## Task 10: Retire `uk-web-registration`

**Files:**
- Modify: `docker-compose.yml` (remove `web` service block + its `8000:8000` publish)
- Delete: `uk_management_bot/web/` (main.py, limiter.py, api/invite.py, templates/, static/, __init__.py)
- Tests cleanup under `uk_management_bot/tests/`

- [ ] **Step 1: Preserve the nonce service test.** In `test_invite_sec020.py`, the test `test_validate_invite_raises_token_already_used_error_on_race_loser` exercises `InviteService._use_nonce_atomically` (service-level, NOT web). Move it into a new/existing service test module, e.g. `uk_management_bot/tests/services/test_invite_service_nonce.py`. Run it to confirm it still passes.
- [ ] **Step 2: Delete web-only tests** — `test_invite_register.py`, `test_invite_register_role.py`, `test_web_debug_routes_guard.py`, and the remaining (web-endpoint) parts of `test_invite_sec020.py`.
- [ ] **Step 3: Delete `uk_management_bot/web/`.**
- [ ] **Step 4: Remove the `web` service** from `docker-compose.yml` (the block with `container_name: uk-web-registration` and `- "8000:8000"`).
- [ ] **Step 5: Remove the other references to the `web` service:**
  - `nginx.conf:7` — the repo's LOCAL nginx has `server web:8000;` (the registration
    upstream). Remove that `upstream`/`server` block and any `location` proxying to
    it. NOTE: this is the repo's local `nginx.conf`, **NOT** the prod edge
    `infrasafe-nginx` (don't touch prod).
  - `pyproject.toml:11` — coverage `omit` lists `"uk_management_bot/web/*"`; drop that line.
  - Broad grep for stragglers:
    `grep -rn "uk_management_bot.web\|web-registration\|web/main\|web:8000\|web/api/invite" uk_management_bot docker-compose.yml nginx.conf pyproject.toml`
    — fix/remove anything remaining.
- [ ] **Step 6: Run full suite** — `docker exec uk-management-bot pytest -q` — Expected: all pass.
- [ ] **Step 7: Stage / checkpoint (commit on user request)**

```bash
git add -A
# git commit -m "chore(registration): retire dead uk-web-registration service (removes :8000 exposure)"
```

---

## Task 11: Manual verification (Telegram WebApp)

- [ ] Rebuild api+frontend locally; open the bot as a NEW user → tap "Регистрация (форма)".
- [ ] Form opens inside Telegram; name prefilled; apartment selector populated.
- [ ] Submit → "заявка отправлена, ожидайте"; admins receive a notification.
- [ ] Manager approves (existing flow: user approval + apartment moderation) → resident logs in via normal TWA/web login.
- [ ] Re-open the form as the now-approved user → `409` → redirected into the app.
- [ ] Open `/register` outside Telegram → "откройте через Telegram" (no initData).
- [ ] Use the telegram-qa MCP for the end-to-end walkthrough where possible.

---

## Notes for the implementer
- Approval is UNCHANGED — do not modify any approval entrypoint (see spec §4.4). A web-registered applicant is approved exactly like a bot-onboarded one (two existing steps).
- `AuthService` and `InviteService` are SYNC (`Session`); the registration endpoints are ASYNC (`AsyncSession`) — never call the sync services from the async endpoint. `core.request_apartment` IS async and is the correct apartment-write path.
- Identity is WebApp-only: `telegram_id` always comes from verified `initData` (`/start`) → ticket → `/applicant`. Never trust a telegram_id from a request body.
- No invite token on the web form (invites stay bot-only).
- **Intentional divergence from spec §6 component list:** the spec names
  `api/registration/service.py` (`RegistrationService`) and two frontend hooks
  (`useRegistrationStart`/`useRegisterApplicant`). This plan keeps the backend
  logic in `router.py` + `catalog.py`/`notify.py` (the endpoints are thin enough
  that a separate service class is YAGNI) and uses a single `useRegistration.ts`
  hook. Same behaviour, fewer files. If the logic grows, extract a service later.
