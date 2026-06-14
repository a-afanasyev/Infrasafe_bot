import hmac
import hashlib
import json
import time
import uuid
from urllib.parse import urlencode
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from uk_management_bot.api.main import app
from uk_management_bot.api.dependencies import get_db
from uk_management_bot.config.settings import settings


@pytest_asyncio.fixture
async def async_db(address_async_db):
    """Reuse the existing rolled-back AsyncSession fixture (tests/conftest.py) — its
    savepoint/rollback isolation already tolerates core.request_apartment's internal
    commit. Aliased here so registration tests read clearly. Do NOT spin up a new
    engine; schema lives in the migrated container DB and tests run via docker exec."""
    return address_async_db


@pytest_asyncio.fixture
async def api_client(async_db):
    """ASGI httpx client bound to the rolled-back async_db session.

    Each client gets a unique ``X-Real-IP`` so slowapi's per-IP limiter
    (``client_ip_key`` honors a client-supplied ``X-Real-IP`` when no
    trusted-proxy allowlist is configured — the dev/test default) buckets every
    test into its own window instead of collapsing all ASGI requests into one
    127.0.0.1 bucket. ``slowapi.Limiter`` has no ``.enabled`` toggle in the
    installed version, so this header-isolation approach replaces disabling the
    limiter."""
    async def _override_get_db():
        yield async_db
    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    headers = {"X-Real-IP": f"10.0.0.{uuid.uuid4().int % 254 + 1}-{uuid.uuid4().hex}"}
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        yield client
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def fake_initdata():
    """Factory -> a VALID signed Telegram WebApp initData string for a telegram_id.
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
    async def _make(telegram_id: int, status: str = "pending"):
        u = User(telegram_id=telegram_id, status=status)
        async_db.add(u); await async_db.flush()
        return u
    return _make


@pytest.fixture
def seed_apartment(async_db):
    from uk_management_bot.database.models.yard import Yard
    from uk_management_bot.database.models.building import Building
    from uk_management_bot.database.models.apartment import Apartment
    async def _make(number: str = "12", yard_name: str = "Двор-1", address: str = "ул. Ленина 1",
                    building_active: bool = True, yard_active: bool = True):
        # Yard.name is UNIQUE — keep callers isolated by suffixing a short uuid so
        # repeated seeds in the same outer transaction don't collide.
        y = Yard(name=f"{yard_name}-{uuid.uuid4().hex[:8]}", is_active=yard_active)
        async_db.add(y); await async_db.flush()
        b = Building(address=address, yard_id=y.id, is_active=building_active)
        async_db.add(b); await async_db.flush()
        a = Apartment(apartment_number=number, building_id=b.id, is_active=True)
        async_db.add(a); await async_db.flush()
        return a
    return _make
