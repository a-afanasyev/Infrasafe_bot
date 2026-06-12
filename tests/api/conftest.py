"""
Shared fixtures for API tests.

Uses an in-memory aiosqlite database and overrides FastAPI dependencies
so that tests run without Docker / PostgreSQL / JWT tokens.
"""
import os

# PR-5: сохранить реальный postgres-DATABASE_URL процесса для PG-гонок
# (test_webhook_outbox_pg_concurrency) ДО того, как tests/services/conftest.py
# перетрёт env на sqlite. Conftest'ы аргументов импортируются в порядке
# аргументов — при каноническом `pytest tests/api tests/services` этот файл
# грузится первым. Пробрасываем через отдельную env-переменную (tests/api —
# НЕ пакет, импортировать conftest напрямую нельзя); POSTGRES_TEST_URL можно
# задать и снаружи как явный override.
if "POSTGRES_TEST_URL" not in os.environ and os.getenv("DATABASE_URL", "").startswith("postgresql"):
    os.environ["POSTGRES_TEST_URL"] = os.environ["DATABASE_URL"]

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.user_apartment import UserApartment

from uk_management_bot.api.main import app
from uk_management_bot.api.dependencies import get_db, get_current_user

# ── In-memory async engine ──────────────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite://"

_test_manager: User | None = None


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session_factory(db_engine):
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    return factory


@pytest_asyncio.fixture
async def db_session(db_session_factory):
    async with db_session_factory() as session:
        yield session


# ── Seed a manager user ─────────────────────────────────────────────

@pytest_asyncio.fixture
async def manager_user(db_session: AsyncSession):
    global _test_manager
    user = User(
        telegram_id=999999,
        username="testmanager",
        first_name="Test",
        last_name="Manager",
        role="manager",
        roles='["manager"]',
        status="approved",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    _test_manager = user
    return user


# ── Seed a regular user (for moderation tests) ──────────────────────

@pytest_asyncio.fixture
async def resident_user(db_session: AsyncSession):
    user = User(
        telegram_id=888888,
        username="testresident",
        first_name="Resident",
        last_name="User",
        role="applicant",
        roles='["applicant"]',
        status="approved",
        phone="+79001234567",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# ── FastAPI test client with dependency overrides ────────────────────

@pytest_asyncio.fixture
async def client(db_session_factory, manager_user):
    """HTTP client with overridden DB and auth dependencies."""

    async def override_get_db():
        async with db_session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    async def override_get_current_user():
        return manager_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ── Reset the public-board TTL cache between tests ──────────────────
# /api/v2/public/board memoizes its payload in a module-level variable;
# without this reset a cached result leaks across tests.

@pytest.fixture(autouse=True)
def _reset_public_board_cache():
    import uk_management_bot.api.public.router as public_router
    public_router._board_cache = None
    yield
    public_router._board_cache = None


# ── Reset the slowapi rate-limiter between tests ────────────────────
# The limiter is a module-level singleton with shared counters (Redis in
# the dev container, in-memory in CI). Without a reset, per-IP counters
# accumulate across tests — all requests share one client identity — so a
# test asserting a first-request 200 flakes into 429 once an earlier test
# has spent the quota. Reset both before and after to isolate every test.

@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from uk_management_bot.api.rate_limit import limiter
    try:
        limiter.reset()
    except Exception:
        pass
    yield
    try:
        limiter.reset()
    except Exception:
        pass
